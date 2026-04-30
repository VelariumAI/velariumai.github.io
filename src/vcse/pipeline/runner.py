"""Deterministic automated pack pipeline runner."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vcse.adapters.registry import get_adapter
from vcse.compiler import CompilerError, KnowledgeCompiler, compile_report_to_dict
from vcse.packs.index import PackIndex
from vcse.pipeline.models import (
    PIPELINE_FAILED,
    PIPELINE_PASSED,
    PipelineConfig,
    PipelineRunReport,
    PipelineStageReport,
)


class PipelineError(ValueError):
    """Raised when the pipeline config or execution is invalid."""


class PackPipelineRunner:
    def __init__(self, *, output_root: Path | None = None, run_id: str | None = None) -> None:
        self.output_root = Path(output_root) if output_root is not None else Path(".vcse") / "pipeline_runs"
        self.explicit_run_id = run_id

    def run(self, config_path: Path) -> PipelineRunReport:
        config = self._load_config(config_path)
        run_id = self.explicit_run_id or self._default_run_id(config.pipeline_id)
        output_dir = self.output_root / run_id
        if output_dir.exists():
            raise PipelineError(f"pipeline run output already exists: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=False)

        stages: list[PipelineStageReport] = []
        reasons: list[str] = []

        pack_dir = config.compiler_output_root / config.compiler_pack_id
        pre_pack_snapshot = self._snapshot_existing_packs(config.compiler_output_root, exclude=pack_dir)

        normalized_rows: list[dict[str, Any]] = []
        try:
            adapter = get_adapter(config.adapter_type)
            normalized_rows = adapter.run(config.adapter_source)
            normalized_path = output_dir / "normalized.jsonl"
            normalized_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in normalized_rows))
            stages.append(
                PipelineStageReport(
                    stage="adapter",
                    status="STAGE_PASSED",
                    details={"record_count": len(normalized_rows), "output": str(normalized_path)},
                    reasons=[],
                )
            )
        except Exception as exc:
            stages.append(
                PipelineStageReport(
                    stage="adapter",
                    status="STAGE_FAILED",
                    details={},
                    reasons=[str(exc)],
                )
            )
            reasons.append(f"adapter failed: {exc}")
            return self._finalize(config, run_id, output_dir, stages, reasons)

        compile_source = output_dir / "normalized.jsonl"
        try:
            compiler = KnowledgeCompiler()
            compile_report = compiler.compile(
                source_path=compile_source,
                mapping_path=config.compiler_mapping,
                domain_spec_path=config.domain,
                output_pack_id=config.compiler_pack_id,
                output_root=config.compiler_output_root,
                benchmark_output=config.compiler_benchmark_output,
            )
            compile_payload = compile_report_to_dict(compile_report)
            (output_dir / "compile_report.json").write_text(json.dumps(compile_payload, indent=2, sort_keys=True) + "\n")
            stages.append(
                PipelineStageReport(
                    stage="compiler",
                    status="STAGE_PASSED",
                    details=compile_payload,
                    reasons=[],
                )
            )
        except (CompilerError, Exception) as exc:
            stages.append(
                PipelineStageReport(
                    stage="compiler",
                    status="STAGE_FAILED",
                    details={},
                    reasons=[str(exc)],
                )
            )
            reasons.append(f"compiler failed: {exc}")
            return self._finalize(config, run_id, output_dir, stages, reasons)

        try:
            PackIndex().build_index([config.compiler_output_root])
            details = {
                "status": "INDEXED",
                "scan_dir": str(config.compiler_output_root),
                "pack_id": config.compiler_pack_id,
            }
            stages.append(PipelineStageReport(stage="index", status="STAGE_PASSED", details=details, reasons=[]))
        except Exception as exc:
            stages.append(PipelineStageReport(stage="index", status="STAGE_FAILED", details={}, reasons=[str(exc)]))
            reasons.append(f"index failed: {exc}")
            return self._finalize(config, run_id, output_dir, stages, reasons)

        pack_path = config.compiler_output_root / config.compiler_pack_id
        if config.validation_validate_pack:
            validate_payload = self._validate_pack(pack_path)
            (output_dir / "validation_report.json").write_text(json.dumps(validate_payload, indent=2, sort_keys=True) + "\n")
            status = "STAGE_PASSED" if validate_payload.get("passed", False) else "STAGE_FAILED"
            stage_reasons = list(validate_payload.get("errors", [])) if status == "STAGE_FAILED" else []
            stages.append(
                PipelineStageReport(
                    stage="validation",
                    status=status,
                    details=validate_payload,
                    reasons=stage_reasons,
                )
            )
            if status != "STAGE_PASSED":
                reasons.append("validation failed")
                return self._finalize(config, run_id, output_dir, stages, reasons)

        if config.validation_review_pack:
            review_payload = self._review_pack(pack_path)
            (output_dir / "review_report.json").write_text(json.dumps(review_payload, indent=2, sort_keys=True) + "\n")
            stages.append(
                PipelineStageReport(
                    stage="review",
                    status="STAGE_PASSED",
                    details=review_payload,
                    reasons=[],
                )
            )

        benchmark_payload = self._benchmark_report(config.compiler_benchmark_output)
        (output_dir / "benchmark_report.json").write_text(json.dumps(benchmark_payload, indent=2, sort_keys=True) + "\n")
        stages.append(
            PipelineStageReport(
                stage="benchmark",
                status="STAGE_PASSED",
                details=benchmark_payload,
                reasons=[],
            )
        )

        mutation_reasons = self._detect_mutation(
            before=pre_pack_snapshot,
            after=self._snapshot_existing_packs(config.compiler_output_root, exclude=pack_dir),
        )
        if mutation_reasons:
            reasons.extend(mutation_reasons)

        return self._finalize(config, run_id, output_dir, stages, reasons)

    def _load_config(self, config_path: Path) -> PipelineConfig:
        source = Path(config_path)
        if not source.exists():
            raise PipelineError(f"pipeline config not found: {source}")
        suffix = source.suffix.lower()
        if suffix in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore[import-not-found]
            except Exception as exc:
                raise PipelineError("PyYAML is required for YAML pipeline configs") from exc
            payload = yaml.safe_load(source.read_text())
        elif suffix == ".json":
            payload = json.loads(source.read_text())
        else:
            raise PipelineError(f"unsupported pipeline config format: {suffix or '<none>'}")
        if not isinstance(payload, dict):
            raise PipelineError("pipeline config root must be an object")

        required_top = ["pipeline_id", "domain", "adapter", "compiler", "validation", "runtime_store"]
        missing_top = [field for field in required_top if field not in payload]
        if missing_top:
            raise PipelineError(f"pipeline config missing required fields: {', '.join(missing_top)}")

        adapter = self._require_object(payload, "adapter")
        compiler = self._require_object(payload, "compiler")
        validation = self._require_object(payload, "validation")
        runtime_store = self._require_object(payload, "runtime_store")

        config = PipelineConfig(
            pipeline_id=self._require_non_empty_str(payload, "pipeline_id"),
            domain=self._repo_path(self._require_non_empty_str(payload, "domain")),
            adapter_type=self._require_non_empty_str(adapter, "type"),
            adapter_source=self._repo_path(self._require_non_empty_str(adapter, "source")),
            compiler_mapping=self._repo_path(self._require_non_empty_str(compiler, "mapping")),
            compiler_pack_id=self._require_non_empty_str(compiler, "pack_id"),
            compiler_output_root=self._repo_path(self._require_non_empty_str(compiler, "output_root")),
            compiler_benchmark_output=self._repo_path(self._require_non_empty_str(compiler, "benchmark_output")),
            validation_validate_pack=bool(validation.get("validate_pack", False)),
            validation_review_pack=bool(validation.get("review_pack", False)),
            runtime_store_compile=bool(runtime_store.get("compile", False)),
        )

        if config.runtime_store_compile:
            raise PipelineError("runtime_store.compile=true is not supported in automated pipeline")
        if config.adapter_type not in {"json", "jsonl", "csv"}:
            raise PipelineError(f"invalid adapter.type: {config.adapter_type}")
        if not config.domain.exists():
            raise PipelineError(f"domain not found: {config.domain}")
        if not config.adapter_source.exists():
            raise PipelineError(f"adapter source not found: {config.adapter_source}")
        if not config.compiler_mapping.exists():
            raise PipelineError(f"compiler mapping not found: {config.compiler_mapping}")

        return config

    def _require_object(self, payload: dict[str, Any], key: str) -> dict[str, Any]:
        value = payload.get(key)
        if not isinstance(value, dict):
            raise PipelineError(f"pipeline field '{key}' must be an object")
        return value

    def _require_non_empty_str(self, payload: dict[str, Any], key: str) -> str:
        if key not in payload:
            raise PipelineError(f"missing required field '{key}'")
        value = str(payload[key]).strip()
        if not value:
            raise PipelineError(f"field '{key}' must be non-empty")
        return value

    def _repo_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            raise PipelineError(f"config paths must be repo-relative: {value}")
        return path

    def _validate_pack(self, pack_path: Path) -> dict[str, Any]:
        claims_path = pack_path / "claims.jsonl"
        provenance_path = pack_path / "provenance.jsonl"
        if not claims_path.exists():
            raise PipelineError(f"missing claims.jsonl in {pack_path}")
        if not provenance_path.exists():
            raise PipelineError(f"missing provenance.jsonl in {pack_path}")
        claims = [json.loads(line) for line in claims_path.read_text().splitlines() if line.strip()]
        provenance_rows = [json.loads(line) for line in provenance_path.read_text().splitlines() if line.strip()]
        errors: list[str] = []
        seen_keys: set[str] = set()
        for idx, claim in enumerate(claims, start=1):
            key = "|".join([str(claim.get("subject", "")), str(claim.get("relation", "")), str(claim.get("object", ""))])
            if key in seen_keys:
                errors.append(f"duplicate claim at line {idx}: {key}")
            seen_keys.add(key)
            prov = claim.get("provenance")
            if not isinstance(prov, dict):
                errors.append(f"missing provenance object at line {idx}")
                continue
            required = ["source_type", "source_id", "location", "evidence_text", "confidence", "trust_level"]
            missing = [field for field in required if not str(prov.get(field, "")).strip()]
            if missing:
                errors.append(f"incomplete provenance at line {idx}: missing {','.join(missing)}")
        if len(provenance_rows) != len(claims):
            errors.append("provenance.jsonl length must match claims.jsonl length")
        payload = {
            "status": "VALID" if not errors else "INVALID",
            "pack_path": str(pack_path),
            "passed": not errors,
            "errors": errors,
            "claim_count": len(claims),
            "provenance_count": len(provenance_rows),
        }
        false_verified_count = int(self._read_pack_false_verified_count(pack_path))
        payload["false_verified_count"] = false_verified_count
        if false_verified_count > 0:
            errors = list(payload.get("errors", []))
            errors.append("false_verified_count > 0")
            payload["errors"] = errors
            payload["passed"] = False
            payload["status"] = "INVALID"
        return payload

    def _review_pack(self, pack_path: Path) -> dict[str, Any]:
        from vcse.cli import run_pack_review

        text = run_pack_review(str(pack_path), json_output=True)
        return json.loads(text)

    def _benchmark_report(self, benchmark_path: Path) -> dict[str, Any]:
        if not benchmark_path.exists():
            return {"status": "BENCHMARK_MISSING", "benchmark_path": str(benchmark_path), "benchmark_count": 0}
        count = 0
        for line in benchmark_path.read_text().splitlines():
            if line.strip():
                count += 1
        return {
            "status": "BENCHMARK_READY",
            "benchmark_path": str(benchmark_path),
            "benchmark_count": count,
        }

    def _read_pack_false_verified_count(self, pack_path: Path) -> int:
        metrics_path = pack_path / "metrics.json"
        if not metrics_path.exists():
            return 0
        payload = json.loads(metrics_path.read_text())
        if not isinstance(payload, dict):
            return 0
        return int(payload.get("false_verified_count", 0) or 0)

    def _snapshot_existing_packs(self, packs_root: Path, *, exclude: Path) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        root = Path(packs_root)
        if not root.exists():
            return snapshot
        excluded = exclude.resolve()
        for pack_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            if pack_dir.resolve() == excluded:
                continue
            for file_path in sorted(path for path in pack_dir.rglob("*") if path.is_file()):
                rel = str(file_path.relative_to(root))
                snapshot[rel] = self._sha256(file_path.read_bytes())
        return snapshot

    def _detect_mutation(self, *, before: dict[str, str], after: dict[str, str]) -> list[str]:
        reasons: list[str] = []
        for rel, digest in before.items():
            next_digest = after.get(rel)
            if next_digest is None:
                reasons.append(f"hidden mutation: deleted existing pack artifact {rel}")
            elif next_digest != digest:
                reasons.append(f"hidden mutation: modified existing pack artifact {rel}")
        return reasons

    def _finalize(
        self,
        config: PipelineConfig,
        run_id: str,
        output_dir: Path,
        stages: list[PipelineStageReport],
        reasons: list[str],
    ) -> PipelineRunReport:
        status = PIPELINE_PASSED if not reasons and all(stage.status == "STAGE_PASSED" for stage in stages) else PIPELINE_FAILED
        report = PipelineRunReport(
            status=status,
            pipeline_id=config.pipeline_id,
            run_id=run_id,
            pack_id=config.compiler_pack_id,
            stages=stages,
            output_dir=str(output_dir),
            reasons=sorted(set(reasons)),
        )
        (output_dir / "pipeline_report.json").write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")
        return report

    def _default_run_id(self, pipeline_id: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"{pipeline_id}_{stamp}"

    def _sha256(self, payload: bytes) -> str:
        import hashlib

        return hashlib.sha256(payload).hexdigest()
