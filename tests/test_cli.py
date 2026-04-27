import os
import subprocess
import sys
from pathlib import Path


def test_cli_logic_demo_outputs_verified_trace() -> None:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, "-m", "vcse.cli", "demo", "logic"],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    assert "status: VERIFIED" in result.stdout
    assert "answer: Socrates is_a Mortal" in result.stdout
    assert "proof_trace:" in result.stdout
    assert "- Socrates is_a Mortal" in result.stdout
