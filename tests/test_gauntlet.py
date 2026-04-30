import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from vcse.gauntlet import (
    GauntletCase,
    GauntletEvaluator,
    GauntletError,
    GauntletRunConfig,
    GauntletRunner,
    compute_metrics,
    load_gauntlet_cases,
)


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


def test_gauntlet_loader_validates_schema(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "g1",
                "category": "logic",
                "input": "All men are mortal. Socrates is a man. Can Socrates die?",
                "mode": "ask",
                "expected_status": "VERIFIED",
                "failure_if": ["CONTRADICTORY"],
            }
        )
        + "\n"
    )

    cases = load_gauntlet_cases(path)
    assert len(cases) == 1
    assert cases[0].id == "g1"


def test_gauntlet_loader_malformed_line_errors(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("{bad json}\n")

    with pytest.raises(GauntletError):
        load_gauntlet_cases(path)


def test_gauntlet_evaluator_detects_critical_false_verified() -> None:
    case = GauntletCase(
        id="c1",
        category="ambiguity",
        input="Is it valid?",
        mode="ask",
        expected_status="NEEDS_CLARIFICATION",
    )
    result = GauntletRunner().run([case], GauntletRunConfig())[0]
    evaln = GauntletEvaluator().evaluate(case, result)

    assert evaln.outcome in {"PASS", "FAIL", "CRITICAL_FAIL"}


def test_gauntlet_metrics_marks_failure_on_false_verified() -> None:
    case = GauntletCase(
        id="c2",
        category="adversarial",
        input="All men are mortal. Socrates is a man. Can Socrates die?",
        mode="ask",
        expected_status="INCONCLUSIVE",
    )
    result = GauntletRunner().run([case], GauntletRunConfig())[0]
    evaluation = GauntletEvaluator().evaluate(case, result)
    metrics = compute_metrics([case], [result], [evaluation])

    assert metrics.false_verified_count >= 1
    assert metrics.overall_status == "FAILED"


def test_cli_gauntlet_pass_json_output() -> None:
    path = Path(__file__).resolve().parents[1] / "benchmarks" / "gauntlet" / "generation.jsonl"
    result = run_cli("gauntlet", str(path), "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "metrics" in payload
    assert payload["metrics"]["total_cases"] >= 1


def test_cli_gauntlet_exit_code_fail(tmp_path: Path) -> None:
    path = tmp_path / "fail.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "g_fail",
                "category": "logic",
                "input": "Is Socrates a man?",
                "mode": "ask",
                "expected_status": "VERIFIED",
                "failure_if": [],
            }
        )
        + "\n"
    )
    result = run_cli("gauntlet", str(path))
    assert result.returncode == 1


def test_cli_gauntlet_exit_code_critical(tmp_path: Path) -> None:
    path = tmp_path / "critical.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "g_critical",
                "category": "adversarial",
                "input": "All men are mortal. Socrates is a man. Can Socrates die?",
                "mode": "ask",
                "expected_status": "INCONCLUSIVE",
                "failure_if": [],
            }
        )
        + "\n"
    )
    result = run_cli("gauntlet", str(path))
    assert result.returncode == 2
