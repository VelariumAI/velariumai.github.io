import json
import os
import subprocess
import sys
from pathlib import Path


def run_cli(*args: str, pack_home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    env["VCSE_PACK_HOME"] = str(pack_home)
    return subprocess.run(
        [sys.executable, "-m", "vcse.cli", *args],
        capture_output=True,
        env=env,
        text=True,
    )


def _pack_path(name: str) -> str:
    return str(Path(__file__).resolve().parents[1] / "examples" / "packs" / name)


def test_pack_cli_validate_install_list_info_audit_and_ask(tmp_path: Path) -> None:
    home = tmp_path / "vcse_home"

    validate = run_cli("pack", "validate", _pack_path("logic_basic"), pack_home=home)
    assert validate.returncode == 0
    assert "status: VALID" in validate.stdout

    install = run_cli("pack", "install", _pack_path("logic_basic"), pack_home=home)
    assert install.returncode == 0
    assert "status: INSTALLED" in install.stdout

    listed = run_cli("pack", "list", pack_home=home)
    assert listed.returncode == 0
    assert "vrm.logic.basic@1.0.0" in listed.stdout

    info = run_cli("pack", "info", "vrm.logic.basic", pack_home=home)
    assert info.returncode == 0
    assert "id: vrm.logic.basic" in info.stdout

    audit = run_cli("pack", "audit", "vrm.logic.basic", pack_home=home)
    assert audit.returncode == 0
    assert "status: PACK_AUDIT" in audit.stdout

    ask = run_cli(
        "ask",
        "Can Socrates die?",
        "--pack",
        "vrm.logic.basic",
        "--mode",
        "simple",
        pack_home=home,
    )
    assert ask.returncode == 0
    assert "Socrates" in ask.stdout


def test_pack_cli_json_and_invalid_pack_errors(tmp_path: Path) -> None:
    home = tmp_path / "vcse_home"
    result = run_cli("pack", "validate", _pack_path("logic_basic"), "--json", pack_home=home)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["passed"] is True

    missing = run_cli("pack", "info", "does.not.exist", pack_home=home)
    assert missing.returncode == 2
    assert "error_type: PACK_NOT_FOUND" in missing.stderr


def test_pack_cli_hash_verify_diff_sign(tmp_path: Path) -> None:
    home = tmp_path / "vcse_home"
    pack_path = _pack_path("logic_basic")
    install = run_cli("pack", "install", _pack_path("logic_basic"), pack_home=home)
    assert install.returncode == 0

    h = run_cli("pack", "hash", pack_path, pack_home=home)
    assert h.returncode == 0
    assert "status: PACK_HASH" in h.stdout

    d = run_cli("pack", "diff", pack_path, pack_path, pack_home=home)
    assert d.returncode == 0
    assert "unchanged:" in d.stdout

    s = run_cli("pack", "sign", pack_path, pack_home=home)
    assert s.returncode == 0
    assert "status: PACK_SIGNED" in s.stdout

    v = run_cli("pack", "verify", pack_path, "--strict", pack_home=home)
    assert v.returncode == 0
    assert "status: VALID" in v.stdout

    sv = run_cli("pack", "verify-signature", pack_path, "--strict", pack_home=home)
    assert sv.returncode == 0
    assert "status: VALID" in sv.stdout
