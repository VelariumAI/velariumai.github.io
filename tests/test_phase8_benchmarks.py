import json
import os
import subprocess
import sys
from pathlib import Path

from vcse.benchmark import BenchmarkCaseError, run_benchmark


def write_jsonl(path: Path, cases: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(case) for case in cases) + "\n")


def logic_case(expected_status: str = "VERIFIED", expected_answer: str | None = None) -> dict:
    return {
        "id": "logic_001",
        "facts": [
            {"subject": "Socrates", "relation": "is_a", "object": "Man"},
            {"subject": "Man", "relation": "is_a", "object": "Mortal"},
        ],
        "constraints": [],
        "goal": {"subject": "Socrates", "relation": "is_a", "object": "Mortal"},
        "expected_status": expected_status,
        "expected_answer": expected_answer or "Socrates is_a Mortal",
    }


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "vcse.cli", *args],
        capture_output=True,
        env=env,
        text=True,
    )


def test_benchmark_runner_loads_jsonl_and_computes_status_and_answer_accuracy(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    write_jsonl(path, [logic_case()])

    summary = run_benchmark(path)

    assert summary["cases_total"] == 1
    assert summary["cases_passed"] == 1
    assert summary["accuracy"] == 1.0
    assert summary["status_accuracy"] == 1.0
    assert summary["answer_accuracy"] == 1.0
    assert summary["verified_rate"] == 1.0
    assert summary["avg_nodes_expanded"] >= 1
    assert summary["avg_search_depth"] >= 1
    assert summary["avg_proof_trace_length"] == 3.0
    assert summary["status_counts"]["VERIFIED"] == 1


def test_benchmark_runner_reports_answer_accuracy_separately(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    write_jsonl(path, [logic_case(expected_answer="wrong")])

    summary = run_benchmark(path)

    assert summary["status_accuracy"] == 1.0
    assert summary["answer_accuracy"] == 0.0
    assert summary["cases_passed"] == 0
    assert summary["accuracy"] == 0.0


def test_invalid_case_reports_structured_error(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    write_jsonl(path, [{"id": "bad", "facts": "not-a-list", "expected_status": "VERIFIED"}])

    try:
        run_benchmark(path)
    except BenchmarkCaseError as exc:
        assert exc.error_type == "INVALID_CASE"
        assert "facts must be a list" in exc.reason
    else:
        raise AssertionError("expected BenchmarkCaseError")


def test_benchmark_json_cli_emits_valid_json(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    write_jsonl(path, [logic_case()])

    result = run_cli("benchmark", str(path), "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["cases_total"] == 1
    assert payload["status_counts"]["VERIFIED"] == 1


def test_benchmark_command_exits_nonzero_on_failed_benchmark_unless_allowed(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    write_jsonl(path, [logic_case(expected_status="CONTRADICTORY")])

    failed = run_cli("benchmark", str(path))
    allowed = run_cli("benchmark", str(path), "--allow-fail")

    assert failed.returncode == 1
    assert "status: BENCHMARK_FAILED" in failed.stdout
    assert allowed.returncode == 0
    assert "status: BENCHMARK_FAILED" in allowed.stdout
