import os
import subprocess
import sys
from pathlib import Path


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-m", "vcse.cli", *args], capture_output=True, text=True, env=env)


def test_trust_evaluate_cli_works() -> None:
    path = Path(__file__).resolve().parents[1] / "examples" / "trust" / "cross_supported_claims.jsonl"
    result = run_cli("trust", "evaluate", str(path))
    assert result.returncode == 0
    assert "status: TRUST_EVALUATED" in result.stdout


def test_trust_promote_and_ledger_verify_cli_work(tmp_path: Path) -> None:
    src = Path(__file__).resolve().parents[1] / "examples" / "packs" / "trusted_basic"
    target = tmp_path / "trusted_basic"
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        out = target / item.relative_to(src)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(item.read_bytes())

    promote = run_cli("trust", "promote", str(target))
    assert promote.returncode == 0
    assert "status: TRUST_PROMOTED" in promote.stdout

    verify = run_cli("ledger", "verify", str(target))
    assert verify.returncode == 0
    assert "status: LEDGER_OK" in verify.stdout
