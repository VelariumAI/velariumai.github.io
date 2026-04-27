"""JSONL benchmark runner with text-input support."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from vcse.engine import CaseValidationError, build_search, filter_bundle_for_query, state_from_case
from vcse.memory.serialization import PathLike


class BenchmarkCaseError(ValueError):
    def __init__(self, error_type: str, reason: str) -> None:
        super().__init__(f"{error_type}: {reason}")
        self.error_type = error_type
        self.reason = reason


STATUSES = ("VERIFIED", "CONTRADICTORY", "INCONCLUSIVE", "UNSATISFIABLE", "NEEDS_CLARIFICATION")


def run_benchmark(
    path: PathLike,
    enable_ts3: bool = False,
    search_backend: str = "beam",
    dsl_bundle=None,
    enable_index: bool = False,
    top_k_rules: int = 20,
    top_k_packs: int = 5,
) -> dict[str, Any]:
    cases = _load_cases(Path(path))
    results: list[dict[str, Any]] = []

    for case in cases:
        started = time.perf_counter()
        result = _run_case(
            case,
            enable_ts3=enable_ts3,
            search_backend=search_backend,
            dsl_bundle=dsl_bundle,
            enable_index=enable_index,
            top_k_rules=top_k_rules,
            top_k_packs=top_k_packs,
        )
        runtime_ms = (time.perf_counter() - started) * 1000
        results.append({**result, "runtime_ms": runtime_ms})

    return _summary(results)


def _run_case(
    case: dict[str, Any],
    enable_ts3: bool = False,
    search_backend: str = "beam",
    dsl_bundle=None,
    enable_index: bool = False,
    top_k_rules: int = 20,
    top_k_packs: int = 5,
) -> dict[str, Any]:
    """Run a single benchmark case."""
    case_id = case.get("id")
    input_text = case.get("input")

    # Check if this is a text-input case
    if input_text and "expected_status" in case:
        return _run_text_case(
            case_id,
            input_text,
            case,
            enable_ts3=enable_ts3,
            search_backend=search_backend,
            dsl_bundle=dsl_bundle,
            enable_index=enable_index,
            top_k_rules=top_k_rules,
            top_k_packs=top_k_packs,
        )

    # Otherwise use original JSON case format
    try:
        state = state_from_case(case)
    except CaseValidationError as exc:
        raise BenchmarkCaseError(exc.error_type, exc.reason) from exc
    active_bundle = dsl_bundle
    if enable_index and dsl_bundle is not None:
        goal_text = ""
        relation_hints: set[str] = set()
        goal = case.get("goal")
        if isinstance(goal, dict):
            goal_text = " ".join(str(goal.get(key, "")) for key in ("subject", "relation", "object"))
            relation = str(goal.get("relation", "")).strip().lower()
            if relation:
                relation_hints.add(relation)
        active_bundle, _ = filter_bundle_for_query(
            dsl_bundle,
            goal_text,
            relation_hints=relation_hints,
            top_k_rules=top_k_rules,
            top_k_packs=top_k_packs,
        )
    if active_bundle is not None:
        from vcse.memory.relations import RelationSchema
        for schema in getattr(active_bundle, "relation_schemas", []):
            name = str(schema.get("name", "")).strip()
            if not name:
                continue
            if state.get_relation_schema(name) is None:
                properties = set(schema.get("properties", []))
                state.add_relation_schema(
                    RelationSchema(
                        name=name,
                        transitive="transitive" in properties,
                        symmetric="symmetric" in properties,
                        reflexive="reflexive" in properties,
                        functional="functional" in properties,
                    )
                )
    search_result = build_search(
        enable_ts3=enable_ts3,
        search_backend=search_backend,
        dsl_bundle=active_bundle,
    ).run(state)
    evaluation = search_result.evaluation
    status = evaluation.status.value
    expected_status = case.get("expected_status")
    has_expected_answer = "expected_answer" in case
    expected_answer = case.get("expected_answer")
    status_ok = expected_status == status
    answer_ok = True if not has_expected_answer else expected_answer == evaluation.answer
    passed = status_ok and answer_ok

    return {
        "id": case_id,
        "status": status,
        "answer": evaluation.answer,
        "expected_status": expected_status,
        "expected_answer": expected_answer,
        "status_ok": status_ok,
        "answer_ok": answer_ok,
        "passed": passed,
        "nodes_expanded": search_result.nodes_expanded,
        "search_depth": search_result.max_depth_reached,
        "proof_trace_length": len(evaluation.proof_trace),
        "parse_stats": None,
    }


def _run_text_case(
    case_id: str,
    input_text: str,
    case: dict[str, Any],
    enable_ts3: bool = False,
    search_backend: str = "beam",
    dsl_bundle=None,
    enable_index: bool = False,
    top_k_rules: int = 20,
    top_k_packs: int = 5,
) -> dict[str, Any]:
    """Run a text-input case through the interaction layer."""
    from vcse.interaction.session import Session
    from vcse.interaction.response_modes import ResponseMode

    session = Session.create(
        dsl_bundle=dsl_bundle,
        enable_indexing=enable_index,
        top_k_rules=top_k_rules,
        top_k_packs=top_k_packs,
    )
    expected_status = case.get("expected_status")
    expected_answer = case.get("expected_answer")

    # Ingest and solve
    frames = session.ingest(input_text)
    result = session.solve(
        enable_ts3=enable_ts3,
        search_backend=search_backend,
    )

    # Determine output
    if result is None:
        status = "NO_RESULT"
        answer = None
    elif hasattr(result, "user_message"):
        status = "NEEDS_CLARIFICATION"
        answer = None
    elif hasattr(result, "evaluation"):
        status = result.evaluation.status.value
        answer = result.evaluation.answer
    else:
        status = "UNKNOWN"
        answer = None

    # Check status
    status_ok = expected_status == status

    # Check answer
    answer_ok = True
    if expected_answer is not None and answer is not None:
        answer_ok = _compare_answers(expected_answer, answer)
    elif expected_answer is not None and answer is None:
        answer_ok = False

    passed = status_ok and answer_ok

    # Check for expected clarification content
    clarification_ok = True
    if expected_status == "NEEDS_CLARIFICATION":
        expected_clar = case.get("expected_clarification_contains", "")
        if hasattr(result, "user_message") and expected_clar:
            clarification_ok = expected_clar.lower() in result.user_message.lower()
        elif hasattr(result, "user_message"):
            clarification_ok = True
        else:
            clarification_ok = False
        passed = passed and clarification_ok

    return {
        "id": case_id,
        "status": status,
        "answer": answer,
        "expected_status": expected_status,
        "expected_answer": expected_answer,
        "status_ok": status_ok,
        "answer_ok": answer_ok,
        "passed": passed,
        "nodes_expanded": 0,
        "search_depth": 0,
        "proof_trace_length": 0,
        "parse_stats": {
            "parse_status": frames.status.value if frames else None,
            "frame_count": len(frames.frames) if frames else 0,
            "confidence": frames.confidence if frames else 0.0,
        },
    }


def _compare_answers(expected: dict[str, Any], actual: str | None) -> bool:
    """Compare expected answer to actual answer."""
    if actual is None:
        return expected is None

    # For simple string comparison
    if isinstance(expected, str):
        return expected.lower() in actual.lower()

    # For structured comparison
    if isinstance(expected, dict):
        subject = expected.get("subject", "")
        relation = expected.get("relation", "")
        obj = expected.get("object", "")

        actual_lower = actual.lower()
        return (subject.lower() in actual_lower or subject == "") and \
               (relation.lower() in actual_lower or relation == "") and \
               (obj.lower() in actual_lower or obj == "")

    return False


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

    # Calculate parse accuracy for text cases
    parse_stats_results = [r for r in results if r.get("parse_stats")]
    parse_accuracy = 0.0
    if parse_stats_results:
        parse_passed = sum(1 for r in parse_stats_results
                         if r["parse_stats"]["parse_status"] in ("PARSED", "PARTIAL"))
        parse_accuracy = _rate(parse_passed, len(parse_stats_results))

    return {
        "status": "BENCHMARK_COMPLETE" if cases_passed == total else "BENCHMARK_FAILED",
        "cases_total": total,
        "cases_passed": cases_passed,
        "accuracy": _rate(cases_passed, total),
        "status_accuracy": _rate(status_passed, total),
        "answer_accuracy": _rate(answer_passed, total),
        "parse_accuracy": parse_accuracy,
        "verified_rate": _rate(status_counts.get("VERIFIED", 0), total),
        "contradictory_rate": _rate(status_counts.get("CONTRADICTORY", 0), total),
        "inconclusive_rate": _rate(status_counts.get("INCONCLUSIVE", 0), total),
        "unsatisfiable_rate": _rate(status_counts.get("UNSATISFIABLE", 0), total),
        "needs_clarification_rate": _rate(status_counts.get("NEEDS_CLARIFICATION", 0), total),
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
        f"parse_accuracy: {summary.get('parse_accuracy', 'N/A')}",
        f"verified_rate: {summary['verified_rate']}",
        f"contradictory_rate: {summary['contradictory_rate']}",
        f"inconclusive_rate: {summary['inconclusive_rate']}",
        f"unsatisfiable_rate: {summary['unsatisfiable_rate']}",
        f"needs_clarification_rate: {summary.get('needs_clarification_rate', 0.0)}",
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
