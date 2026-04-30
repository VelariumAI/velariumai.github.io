"""Deterministic knowledge compiler for domain-spec-driven pack generation."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from vcse.compiler.models import COMPILE_PASSED, CompileReport, CompilerMapping
from vcse.domain.loader import load_domain_spec


class CompilerError(ValueError):
    """Raised for compiler validation and input errors."""


class KnowledgeCompiler:
    def compile(
        self,
        source_path: Path,
        mapping_path: Path,
        domain_spec_path: Path,
        output_pack_id: str,
        output_root: Path,
        benchmark_output: Path | None = None,
    ) -> CompileReport:
        source_path = Path(source_path)
        mapping_path = Path(mapping_path)
        domain_spec_path = Path(domain_spec_path)
        output_root = Path(output_root)

        spec = load_domain_spec(domain_spec_path)
        mapping = self._load_mapping(mapping_path)
        self.validate_mapping(mapping, domain_spec_path)

        records = self._load_records(source_path)
        claims: list[dict[str, Any]] = []
        provenance_rows: list[dict[str, Any]] = []
        benchmark_rows: list[dict[str, Any]] = []
        seen_claim_keys: set[str] = set()
        duplicate_count = 0

        template_by_relation = {item.relation: item for item in spec.benchmark_templates}

        for row_index, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                raise CompilerError(f"source row {row_index} must be an object")
            record_id = str(record.get("id", f"row_{row_index}"))
            subject_raw = record.get(mapping.entity_field)
            if subject_raw is None or str(subject_raw).strip() == "":
                continue
            subject = str(subject_raw).strip()

            for mapping_alias, source_field in mapping.fields.items():
                relation = mapping.relation_map[mapping_alias]
                value = record.get(source_field)
                for object_value in self._expand_value(value):
                    claim_key = self._claim_key(subject, relation, object_value)
                    if claim_key in seen_claim_keys:
                        duplicate_count += 1
                        continue
                    seen_claim_keys.add(claim_key)

                    claim = {
                        "claim_key": claim_key,
                        "subject": subject,
                        "relation": relation,
                        "object": object_value,
                        "qualifiers": {"inference_type": "explicit"},
                        "provenance": {
                            "source_type": "structured_record",
                            "source_id": mapping.source_id,
                            "location": f"{mapping.source_id}/{record_id}",
                            "evidence_text": f"{subject} {relation} {object_value}",
                            "confidence": 1.0,
                            "trust_level": "unrated",
                        },
                    }
                    claims.append(claim)

                    provenance_rows.append(
                        {
                            "claim_key": claim_key,
                            "source_id": mapping.source_id,
                            "source_record_id": record_id,
                            "domain_id": mapping.domain_id,
                            "compiler": "knowledge_compiler_v1",
                            "relation": relation,
                            "field": source_field,
                            "value": object_value,
                        }
                    )

                    template = template_by_relation.get(relation)
                    if template is not None:
                        benchmark_rows.append(
                            {
                                "id": f"{output_pack_id}_{len(benchmark_rows) + 1:06d}",
                                "question": template.template.format(subject=subject, object=object_value),
                                "expected_subject": subject,
                                "expected_relation": relation,
                                "expected_object": object_value,
                                "source_claim_key": claim_key,
                            }
                        )

        output_dir = output_root / output_pack_id
        if output_dir.exists() and any(output_dir.iterdir()):
            raise CompilerError(f"output pack path must be new/empty: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=False)

        self._write_json(output_dir / "pack.json", self._pack_metadata(output_pack_id, mapping.domain_id, len(claims), len(provenance_rows)))
        self._write_jsonl(output_dir / "claims.jsonl", claims)
        self._write_jsonl(output_dir / "provenance.jsonl", provenance_rows)
        self._write_json(output_dir / "metrics.json", {
            "claim_count": len(claims),
            "input_record_count": len(records),
            "duplicate_count": duplicate_count,
            "provenance_count": len(provenance_rows),
            "benchmark_count": len(benchmark_rows),
            "false_verified_count": 0,
        })
        self._write_json(output_dir / "trust_report.json", {
            "status": "TRUST_PENDING",
            "false_verified_count": 0,
            "decisions": [],
            "conflicts": [],
            "staleness": [],
        })

        if benchmark_output is not None:
            benchmark_output = Path(benchmark_output)
            benchmark_output.parent.mkdir(parents=True, exist_ok=True)
            self._write_jsonl(benchmark_output, benchmark_rows)

        return CompileReport(
            status=COMPILE_PASSED,
            domain_id=mapping.domain_id,
            source_id=mapping.source_id,
            pack_id=output_pack_id,
            input_record_count=len(records),
            claim_count=len(claims),
            duplicate_count=duplicate_count,
            provenance_count=len(provenance_rows),
            benchmark_count=len(benchmark_rows),
            output_path=str(output_dir),
            reasons=[],
        )

    def validate_mapping(self, mapping: CompilerMapping, domain_spec_path: Path) -> None:
        spec = load_domain_spec(domain_spec_path)
        relation_names = {item.relation for item in spec.relations}
        if mapping.domain_id != spec.domain_id:
            raise CompilerError(
                f"mapping domain_id '{mapping.domain_id}' does not match spec domain_id '{spec.domain_id}'"
            )
        if not mapping.source_id.strip():
            raise CompilerError("mapping source_id must be non-empty")
        if not mapping.entity_field.strip():
            raise CompilerError("mapping entity_field must be non-empty")
        if not mapping.fields:
            raise CompilerError("mapping.fields must be non-empty")
        if set(mapping.fields.keys()) != set(mapping.relation_map.keys()):
            raise CompilerError("mapping fields and relation_map keys must match")
        for key, relation in sorted(mapping.relation_map.items()):
            if relation not in relation_names:
                raise CompilerError(f"unknown relation '{relation}' for mapping key '{key}'")

    def _load_mapping(self, mapping_path: Path) -> CompilerMapping:
        if not mapping_path.exists():
            raise CompilerError(f"mapping not found: {mapping_path}")
        try:
            payload = json.loads(mapping_path.read_text())
        except json.JSONDecodeError as exc:
            raise CompilerError(f"malformed mapping JSON: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise CompilerError("mapping root must be an object")
        required = ["domain_id", "source_id", "entity_field", "fields", "relation_map"]
        missing = [field for field in required if field not in payload]
        if missing:
            raise CompilerError(f"mapping missing required fields: {', '.join(missing)}")
        fields = payload["fields"]
        relation_map = payload["relation_map"]
        if not isinstance(fields, dict) or not isinstance(relation_map, dict):
            raise CompilerError("mapping.fields and mapping.relation_map must be objects")
        return CompilerMapping(
            domain_id=str(payload["domain_id"]).strip(),
            source_id=str(payload["source_id"]).strip(),
            entity_field=str(payload["entity_field"]).strip(),
            fields={str(k): str(v) for k, v in fields.items()},
            relation_map={str(k): str(v) for k, v in relation_map.items()},
        )

    def _load_records(self, source_path: Path) -> list[dict[str, Any]]:
        if not source_path.exists():
            raise CompilerError(f"source not found: {source_path}")
        suffix = source_path.suffix.lower()
        if suffix == ".jsonl":
            rows: list[dict[str, Any]] = []
            for idx, line in enumerate(source_path.read_text().splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise CompilerError(f"malformed JSONL at line {idx}: {exc.msg}") from exc
                rows.append(item)
            return rows
        if suffix == ".json":
            try:
                payload = json.loads(source_path.read_text())
            except json.JSONDecodeError as exc:
                raise CompilerError(f"malformed source JSON: {exc.msg}") from exc
            if not isinstance(payload, list):
                raise CompilerError("source JSON root must be a list")
            return payload
        raise CompilerError(f"unsupported source format: {suffix or '<none>'}")

    def _expand_value(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            expanded: list[str] = []
            for item in value:
                if item is None:
                    continue
                rendered = str(item).strip()
                if rendered:
                    expanded.append(rendered)
            return expanded
        rendered = str(value).strip()
        if not rendered:
            return []
        return [rendered]

    def _claim_key(self, subject: str, relation: str, object_value: str) -> str:
        return f"{subject}|{relation}|{object_value}"

    def _pack_metadata(self, pack_id: str, domain_id: str, claim_count: int, provenance_count: int) -> dict[str, Any]:
        return {
            "id": pack_id,
            "version": "1.0.0",
            "domain": domain_id,
            "lifecycle_status": "candidate",
            "claim_count": claim_count,
            "provenance_count": provenance_count,
            "conflict_count": 0,
            "constraint_count": 0,
            "template_count": 0,
            "metrics": {},
        }

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def _write_jsonl(self, path: Path, rows: list[dict[str, Any]]) -> None:
        ordered_rows = sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))
        path.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in ordered_rows))


def compile_report_to_dict(report: CompileReport) -> dict[str, Any]:
    return asdict(report)
