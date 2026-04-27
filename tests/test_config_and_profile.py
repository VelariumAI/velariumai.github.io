import json
import os
import subprocess
import sys
from pathlib import Path

from vcse.config import load_settings


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    runtime_env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    runtime_env["PYTHONPATH"] = src_path + os.pathsep + runtime_env.get("PYTHONPATH", "")
    if env:
        runtime_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "vcse.cli", *args],
        capture_output=True,
        env=runtime_env,
        text=True,
    )


def test_config_loader_reads_env_and_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VCSE_SEARCH_BACKEND", "mcts")
    monkeypatch.setenv("VCSE_TS3_ENABLED", "true")
    settings = load_settings()
    assert settings.search_backend == "mcts"
    assert settings.ts3_enabled is True

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"api_host": "0.0.0.0", "api_port": 9000}))
    loaded = load_settings(config_path)
    assert loaded.api_host == "0.0.0.0"
    assert loaded.api_port == 9000


def test_profile_command_emits_profile_summary() -> None:
    result = run_cli(
        "profile",
        "ask",
        "All men are mortal. Socrates is a man. Can Socrates die?",
        "--mode",
        "simple",
    )
    assert result.returncode == 0
    assert "profile:" in result.stdout
    assert "total_seconds:" in result.stdout


def test_direct_profile_flag_on_ask_emits_profile_summary() -> None:
    result = run_cli(
        "ask",
        "All men are mortal. Socrates is a man. Can Socrates die?",
        "--mode",
        "simple",
        "--profile",
    )
    assert result.returncode == 0
    assert "profile:" in result.stdout
    assert "total_seconds:" in result.stdout
