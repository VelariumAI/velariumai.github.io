"""Gauntlet reporting."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from vcse.gauntlet.case import GauntletCase
from vcse.gauntlet.evaluator import CaseEvaluation
from vcse.gauntlet.metrics import GauntletMetrics
from vcse.gauntlet.runner import GauntletCaseResult


def render_gauntlet_summary(
    metrics: GauntletMetrics,
    cases: list[GauntletCase],
    results: list[GauntletCaseResult],
    evaluations: list[CaseEvaluation],
) -> str:
    lines = [
        f"status: {metrics.overall_status}",
        f"total_cases: {metrics.total_cases}",
        f"passed: {metrics.passed}",
        f"failed: {metrics.failed}",
        f"critical_failures: {metrics.critical_failures}",
        f"accuracy: {metrics.accuracy}",
        f"verified_accuracy: {metrics.verified_accuracy}",
        f"inconclusive_rate: {metrics.inconclusive_rate}",
        f"contradiction_detection_rate: {metrics.contradiction_detection_rate}",
        f"false_verified_count: {metrics.false_verified_count}",
        f"avg_runtime: {metrics.avg_runtime}",
        f"avg_nodes_expanded: {metrics.avg_nodes_expanded}",
        f"avg_depth: {metrics.avg_depth}",
        f"avg_proof_trace_length: {metrics.avg_proof_trace_length}",
        "failure_by_category:",
    ]
    if metrics.failure_by_category:
        for category, count in sorted(metrics.failure_by_category.items()):
            lines.append(f"  {category}: {count}")
    else:
        lines.append("  none: 0")

    critical_rows = [
        (case, result, evaluation)
        for case, result, evaluation in zip(cases, results, evaluations)
        if evaluation.outcome == "CRITICAL_FAIL"
    ]
    lines.append("critical_failures_list:")
    if critical_rows:
        for case, result, evaluation in critical_rows[:10]:
            lines.append(
                f"  - {case.id} [{case.category}] expected={case.expected_status} got={result.status} reasons={'; '.join(evaluation.reasons)}"
            )
    else:
        lines.append("  - none")

    failing_rows = [
        (case, result, evaluation)
        for case, result, evaluation in zip(cases, results, evaluations)
        if evaluation.outcome != "PASS"
    ]
    lines.append("top_failing_cases:")
    if failing_rows:
        for case, result, evaluation in failing_rows[:10]:
            lines.append(
                f"  - {case.id} [{evaluation.outcome}] expected={case.expected_status} got={result.status}"
            )
    else:
        lines.append("  - none")

    return "\n".join(lines)


def render_gauntlet_json(
    metrics: GauntletMetrics,
    cases: list[GauntletCase],
    results: list[GauntletCaseResult],
    evaluations: list[CaseEvaluation],
    debug: bool = False,
) -> str:
    rows: list[dict[str, Any]] = []
    for case, result, evaluation in zip(cases, results, evaluations):
        row = {
            "case": asdict(case),
            "result": {
                "case_id": result.case_id,
                "category": result.category,
                "mode": result.mode,
                "status": result.status,
                "answer": result.answer,
                "proof_trace": list(result.proof_trace),
                "artifact": result.artifact,
                "search_stats": result.search_stats,
                "ts3_stats": result.ts3_stats,
                "runtime_ms": result.runtime_ms,
            },
            "evaluation": asdict(evaluation),
        }
        if debug:
            row["result"]["raw_result"] = result.raw_result
        rows.append(row)
    return json.dumps(
        {
            "metrics": asdict(metrics),
            "cases": rows,
        },
        sort_keys=True,
    )
