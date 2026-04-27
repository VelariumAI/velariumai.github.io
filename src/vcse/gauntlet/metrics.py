"""Gauntlet metrics."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcse.gauntlet.case import GauntletCase
from vcse.gauntlet.evaluator import CaseEvaluation
from vcse.gauntlet.runner import GauntletCaseResult


@dataclass(frozen=True)
class GauntletMetrics:
    overall_status: str
    total_cases: int
    passed: int
    failed: int
    critical_failures: int
    accuracy: float
    verified_accuracy: float
    inconclusive_rate: float
    contradiction_detection_rate: float
    false_verified_count: int
    avg_runtime: float
    avg_nodes_expanded: float
    avg_depth: float
    avg_proof_trace_length: float
    failure_by_category: dict[str, int] = field(default_factory=dict)


def compute_metrics(
    cases: list[GauntletCase],
    results: list[GauntletCaseResult],
    evaluations: list[CaseEvaluation],
) -> GauntletMetrics:
    total = len(cases)
    passed = sum(1 for item in evaluations if item.outcome == "PASS")
    failed = sum(1 for item in evaluations if item.outcome == "FAIL")
    critical = sum(1 for item in evaluations if item.outcome == "CRITICAL_FAIL")

    false_verified = sum(
        1
        for case, result in zip(cases, results)
        if case.expected_status not in {"VERIFIED", "VERIFIED_ARTIFACT"}
        and result.status in {"VERIFIED", "VERIFIED_ARTIFACT"}
    )

    verified_expected = [
        idx for idx, case in enumerate(cases) if case.expected_status in {"VERIFIED", "VERIFIED_ARTIFACT"}
    ]
    verified_passed = sum(1 for idx in verified_expected if evaluations[idx].outcome == "PASS")

    contradiction_expected = [
        idx
        for idx, case in enumerate(cases)
        if case.expected_status in {"CONTRADICTORY", "CONTRADICTORY_ARTIFACT"}
    ]
    contradiction_detected = sum(
        1
        for idx in contradiction_expected
        if results[idx].status in {"CONTRADICTORY", "CONTRADICTORY_ARTIFACT"}
    )

    inconclusive_count = sum(
        1
        for result in results
        if result.status in {"INCONCLUSIVE", "INCONCLUSIVE_ARTIFACT"}
    )

    runtimes = [item.runtime_ms for item in results]
    nodes = [float((item.search_stats or {}).get("nodes_expanded", 0)) for item in results]
    depths = [float((item.search_stats or {}).get("max_depth_reached", 0)) for item in results]
    proofs = [float(len(item.proof_trace)) for item in results]

    failure_by_category: dict[str, int] = {}
    for case, evaluation in zip(cases, evaluations):
        if evaluation.outcome == "PASS":
            continue
        failure_by_category[case.category] = failure_by_category.get(case.category, 0) + 1

    overall_status = "PASSED"
    if false_verified > 0 or critical > 0 or failed > 0:
        overall_status = "FAILED"

    return GauntletMetrics(
        overall_status=overall_status,
        total_cases=total,
        passed=passed,
        failed=failed,
        critical_failures=critical,
        accuracy=_rate(passed, total),
        verified_accuracy=_rate(verified_passed, len(verified_expected)),
        inconclusive_rate=_rate(inconclusive_count, total),
        contradiction_detection_rate=_rate(contradiction_detected, len(contradiction_expected)),
        false_verified_count=false_verified,
        avg_runtime=_avg(runtimes),
        avg_nodes_expanded=_avg(nodes),
        avg_depth=_avg(depths),
        avg_proof_trace_length=_avg(proofs),
        failure_by_category=failure_by_category,
    )


def _rate(n: int, d: int) -> float:
    return n / d if d else 0.0


def _avg(items: list[float]) -> float:
    return sum(items) / len(items) if items else 0.0
