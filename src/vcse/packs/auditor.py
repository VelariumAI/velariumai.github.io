"""Pack auditing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vcse.benchmark import run_benchmark
from vcse.gauntlet import (
    GauntletEvaluator,
    GauntletRunConfig,
    GauntletRunner,
    compute_metrics,
    load_gauntlet_cases,
)
from vcse.packs.activator import PackActivator
from vcse.packs.errors import PackError
from vcse.packs.loader import load_manifest
from vcse.packs.registry import PackRegistry
from vcse.packs.validator import PackValidator


@dataclass(frozen=True)
class AuditReport:
    claims_count: int
    constraints_count: int
    templates_count: int
    dsl_artifacts_count: int
    provenance_coverage_percent: float
    contradiction_count: int
    benchmark_status: str
    gauntlet_status: str
    dependency_status: str
    hash_integrity_status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "claims_count": self.claims_count,
            "constraints_count": self.constraints_count,
            "templates_count": self.templates_count,
            "dsl_artifacts_count": self.dsl_artifacts_count,
            "provenance_coverage_percent": self.provenance_coverage_percent,
            "contradiction_count": self.contradiction_count,
            "benchmark_status": self.benchmark_status,
            "gauntlet_status": self.gauntlet_status,
            "dependency_status": self.dependency_status,
            "hash_integrity_status": self.hash_integrity_status,
        }


class PackAuditor:
    def __init__(self, validator: PackValidator | None = None, registry: PackRegistry | None = None) -> None:
        self.validator = validator or PackValidator()
        self.registry = registry or PackRegistry()

    def audit(self, target: str | Path) -> AuditReport:
        pack_path = self._resolve_target_path(target)
        validation = self.validator.validate(pack_path)
        if validation.manifest is None:
            raise PackError("INVALID_PACK", "unable to load pack manifest")
        manifest, root = load_manifest(pack_path)

        claims_count = _line_count(root, manifest.artifacts.get("claims", []))
        constraints_count = _line_count(root, manifest.artifacts.get("constraints", []))
        templates_count = _line_count(root, manifest.artifacts.get("templates", []))
        dsl_count = len(manifest.artifacts.get("dsl", []))
        provenance_lines = _line_count(root, manifest.artifacts.get("provenance", []) + manifest.provenance)
        provenance_coverage = 100.0 if claims_count == 0 else min(100.0, (provenance_lines / claims_count) * 100.0)
        contradiction_count = _line_count(root, manifest.artifacts.get("conflicts", []))

        benchmark_status = "NOT_PRESENT"
        if manifest.benchmarks:
            statuses = []
            activation = PackActivator(self.registry).activate([f"{manifest.id}@{manifest.version}"])
            for rel_path in manifest.benchmarks:
                summary = run_benchmark(root / rel_path, dsl_bundle=activation.dsl_bundle)
                statuses.append(summary.get("status", "BENCHMARK_FAILED"))
            benchmark_status = "PASS" if all(item == "BENCHMARK_COMPLETE" for item in statuses) else "FAIL"

        gauntlet_status = "NOT_PRESENT"
        if manifest.gauntlet_cases:
            outcomes = []
            for rel_path in manifest.gauntlet_cases:
                cases = load_gauntlet_cases(root / rel_path)
                results = GauntletRunner().run(cases, GauntletRunConfig())
                evaluations = [GauntletEvaluator().evaluate(case, result) for case, result in zip(cases, results)]
                metrics = compute_metrics(cases, results, evaluations)
                outcomes.append(metrics.false_verified_count == 0 and metrics.failed == 0)
            gauntlet_status = "PASS" if all(outcomes) else "FAIL"

        dependency_status = "OK"
        if manifest.dependencies:
            try:
                PackActivator(self.registry).activate([f"{manifest.id}@{manifest.version}"])
            except Exception:
                dependency_status = "FAIL"

        hash_status = "PASS" if validation.passed else "FAIL"
        return AuditReport(
            claims_count=claims_count,
            constraints_count=constraints_count,
            templates_count=templates_count,
            dsl_artifacts_count=dsl_count,
            provenance_coverage_percent=round(provenance_coverage, 2),
            contradiction_count=contradiction_count,
            benchmark_status=benchmark_status,
            gauntlet_status=gauntlet_status,
            dependency_status=dependency_status,
            hash_integrity_status=hash_status,
        )

    def _resolve_target_path(self, target: str | Path) -> Path:
        maybe_path = Path(target)
        if maybe_path.exists():
            return maybe_path
        record = self.registry.find(str(target), None)
        if record is None:
            raise PackError("PACK_NOT_FOUND", f"pack not found: {target}")
        return Path(str(record["install_path"]))


def _line_count(root: Path, rel_paths: list[str]) -> int:
    count = 0
    for rel_path in rel_paths:
        path = root / rel_path
        if not path.exists():
            continue
        count += sum(1 for line in path.read_text().splitlines() if line.strip())
    return count
