"""JSONL benchmark runner."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from vcse.engine import CaseValidationError, build_search, state_from_case
from vcse.memory.serialization import PathLike


class BenchmarkCaseError(ValueError):
    def __init__(self, error_type: str, reason: str) -> None:
        super().__init__(f"{error_type}: {reason}")
        self.error_type = error_type
        self.reason = reason


STATUSES = ("VERIFIED", "CONTRADICTORY", "INCONCLUSIVE", "UNSATISFIABLE")


def run_benchmark(path: PathLike) -> dict[str, Any]:
    cases = _load_cases(Path(path))
    results: list[dict[str, Any]] = []

    for case in cases:
        started = time.perf_counter()
        try:
            state = state_from_case(case)
        except CaseValidationError as exc:
            raise BenchmarkCaseError(exc.error_type, exc.reason) from exc
        search_result = build_search().run(state)
        runtime_ms = (time.perf_counter() - started) * 1000
        evaluation = search_result.evaluation
        status = evaluation.status.value
        expected_status = case.get("expected_status")
        has_expected_answer = "expected_answer" in case
        expected_answer = case.get("expected_answer")
        status_ok = expected_status == status
        answer_ok = True if not has_expected_answer else expected_answer == evaluation.answer
        passed = status_ok and answer_ok
        results.append(
            {
                "id": case.get("id"),
                "status": status,
                "answer": evaluation.answer,
                "expected_status": expected_status,
                "expected_answer": expected_answer,
                "status_ok": status_ok,
                "answer_ok": answer_ok,
                "passed": passed,
                "runtime_ms": runtime_ms,
                "nodes_expanded": search_result.nodes_expanded,
                "search_depth": search_result.max_depth_reached,
                "proof_trace_length": len(evaluation.proof_trace),
            }
        )

    return _summary(results)


def _load_cases(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        raise BenchmarkCaseError("FILE_ERROR", str(exc)) from exc

    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BenchmarkCaseError(
                "MALFORMED_JSON", f"line {line_number}: {exc.msg}"
            ) from exc
        if not isinstance(case, dict):
            raise BenchmarkCaseError(
                "INVALID_CASE", f"line {line_number} root must be an object"
            )
        cases.append(case)
    return cases


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    cases_passed = sum(1 for result in results if result["passed"])
    status_passed = sum(1 for result in results if result["status_ok"])
    answer_passed = sum(1 for result in results if result["answer_ok"])
    status_counts = {status: 0 for status in STATUSES}
    for result in results:
        status_counts[result["status"]] = status_counts.get(result["status"], 0) + 1

    return {
        "status": "BENCHMARK_COMPLETE" if cases_passed == total else "BENCHMARK_FAILED",
        "cases_total": total,
        "cases_passed": cases_passed,
        "accuracy": _rate(cases_passed, total),
        "status_accuracy": _rate(status_passed, total),
        "answer_accuracy": _rate(answer_passed, total),
        "verified_rate": _rate(status_counts.get("VERIFIED", 0), total),
        "contradictory_rate": _rate(status_counts.get("CONTRADICTORY", 0), total),
        "inconclusive_rate": _rate(status_counts.get("INCONCLUSIVE", 0), total),
        "unsatisfiable_rate": _rate(status_counts.get("UNSATISFIABLE", 0), total),
        "avg_runtime_ms": _avg(result["runtime_ms"] for result in results),
        "avg_nodes_expanded": _avg(result["nodes_expanded"] for result in results),
        "avg_search_depth": _avg(result["search_depth"] for result in results),
        "avg_proof_trace_length": _avg(result["proof_trace_length"] for result in results),
        "status_counts": status_counts,
        "cases": results,
    }


def format_benchmark_text(summary: dict[str, Any]) -> str:
    lines = [
        f"status: {summary['status']}",
        f"cases: {summary['cases_total']}",
        f"cases_total: {summary['cases_total']}",
        f"cases_passed: {summary['cases_passed']}",
        f"accuracy: {summary['accuracy']}",
        f"status_accuracy: {summary['status_accuracy']}",
        f"answer_accuracy: {summary['answer_accuracy']}",
        f"verified_rate: {summary['verified_rate']}",
        f"contradictory_rate: {summary['contradictory_rate']}",
        f"inconclusive_rate: {summary['inconclusive_rate']}",
        f"unsatisfiable_rate: {summary['unsatisfiable_rate']}",
        f"avg_runtime_ms: {summary['avg_runtime_ms']}",
        f"avg_nodes_expanded: {summary['avg_nodes_expanded']}",
        f"avg_search_depth: {summary['avg_search_depth']}",
        f"avg_proof_trace_length: {summary['avg_proof_trace_length']}",
        "status_counts:",
    ]
    for status, count in summary["status_counts"].items():
        lines.append(f"  {status}: {count}")
    return "\n".join(lines)


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _avg(values) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0
