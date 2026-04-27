import os
import json
import subprocess
import sys
from pathlib import Path


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


def test_cli_logic_demo_outputs_verified_trace() -> None:
    result = run_cli("demo", "logic")

    assert result.returncode == 0
    assert "status: VERIFIED" in result.stdout
    assert "answer: Socrates is_a Mortal" in result.stdout
    assert "proof_trace:" in result.stdout
    assert "- Socrates is_a Mortal" in result.stdout


def test_cli_arithmetic_demo_outputs_verified() -> None:
    result = run_cli("demo", "arithmetic")

    assert result.returncode == 0
    assert "status: VERIFIED" in result.stdout
    assert "answer: x satisfies constraints" in result.stdout


def test_cli_contradiction_demo_outputs_contradictory_without_answer() -> None:
    result = run_cli("demo", "contradiction")

    assert result.returncode == 0
    assert "status: CONTRADICTORY" in result.stdout
    assert "answer: null" in result.stdout
    assert "x equals both 3 and 4" in result.stdout


def test_cli_run_accepts_json_file(tmp_path: Path) -> None:
    case_file = tmp_path / "case.json"
    case_file.write_text(
        json.dumps(
            {
                "facts": [
                    {"subject": "Socrates", "relation": "is_a", "object": "Man"},
                    {"subject": "Man", "relation": "is_a", "object": "Mortal"},
                ],
                "constraints": [],
                "goal": {
                    "subject": "Socrates",
                    "relation": "is_a",
                    "object": "Mortal",
                },
            }
        )
    )

    result = run_cli("run", str(case_file))

    assert result.returncode == 0
    assert "status: VERIFIED" in result.stdout
    assert "answer: Socrates is_a Mortal" in result.stdout


def test_cli_run_malformed_json_fails_with_structured_error(tmp_path: Path) -> None:
    case_file = tmp_path / "bad.json"
    case_file.write_text("{not json")

    result = run_cli("run", str(case_file))

    assert result.returncode == 2
    assert "status: ERROR" in result.stderr
    assert "error_type: MALFORMED_JSON" in result.stderr
    assert "traceback" not in result.stderr.lower()


def test_cli_benchmark_accepts_jsonl_file(tmp_path: Path) -> None:
    benchmark_file = tmp_path / "cases.jsonl"
    benchmark_file.write_text(
        json.dumps(
            {
                "id": "logic_001",
                "facts": [
                    {"subject": "Socrates", "relation": "is_a", "object": "Man"},
                    {"subject": "Man", "relation": "is_a", "object": "Mortal"},
                ],
                "constraints": [],
                "goal": {
                    "subject": "Socrates",
                    "relation": "is_a",
                    "object": "Mortal",
                },
                "expected_status": "VERIFIED",
            }
        )
        + "\n"
    )

    result = run_cli("benchmark", str(benchmark_file))

    assert result.returncode == 0
    assert "status: BENCHMARK_COMPLETE" in result.stdout
    assert "cases: 1" in result.stdout
    assert "accuracy: 1.0" in result.stdout


def test_cli_does_not_require_gpu_or_external_service() -> None:
    result = run_cli("demo", "logic")

    assert result.returncode == 0
    combined = f"{result.stdout}\n{result.stderr}".lower()
    assert "gpu" not in combined
    assert "service" not in combined


def test_cli_ask_simple_humanizes_is_a_relation_and_strips_modal_subject() -> None:
    result = run_cli(
        "ask",
        "All men are mortal. Socrates is a man. Can Socrates die?",
        "--mode",
        "simple",
    )

    assert result.returncode == 0
    assert "Yes — Socrates is mortal." in result.stdout
    assert "can socrates" not in result.stdout.lower()


def test_cli_ask_explain_and_debug_preserve_proof_trace() -> None:
    explain = run_cli(
        "ask",
        "All men are mortal. Socrates is a man. Can Socrates die?",
        "--mode",
        "explain",
    )
    debug = run_cli(
        "ask",
        "All men are mortal. Socrates is a man. Can Socrates die?",
        "--mode",
        "debug",
    )

    assert explain.returncode == 0
    assert "because" in explain.stdout
    assert "is_a" not in explain.stdout.lower()
    assert "socrates is a man" in explain.stdout.lower()
    assert "man is mortal" in explain.stdout.lower()
    assert "socrates is mortal" in explain.stdout.lower()
    assert "→" in explain.stdout

    assert debug.returncode == 0
    assert "answer: socrates is_a mortal" in debug.stdout.lower()
    assert "answer_human: Socrates is mortal" in debug.stdout
    assert "proof_trace_canonical:" in debug.stdout
    assert "proof_trace_human:" in debug.stdout
    assert "socrates is_a man" in debug.stdout.lower()
    assert "socrates is a man" in debug.stdout.lower()
