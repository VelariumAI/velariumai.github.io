import json
import os
import subprocess
import sys
from pathlib import Path

from vcse.knowledge.pipeline import KnowledgePipeline
from vcse.knowledge.sources import Source


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    home_root = cwd if cwd is not None else Path.cwd()
    env["VCSE_PACK_HOME"] = str(home_root / ".vcse_test_home")
    return subprocess.run(
        [sys.executable, "-m", "vcse.cli", *args],
        cwd=cwd,
        capture_output=True,
        env=env,
        text=True,
    )


def test_pipeline_rejects_invalid_and_detects_conflict(tmp_path: Path) -> None:
    source_path = tmp_path / "claims.jsonl"
    source_path.write_text(
        "\n".join(
            [
                json.dumps({"subject": "x", "relation": "equals", "object": "3"}),
                json.dumps({"subject": "x", "relation": "equals", "object": "4"}),
                json.dumps({"subject": "", "relation": "is_a", "object": "missing"}),
            ]
        )
        + "\n"
    )

    result = KnowledgePipeline().build(Source(id="conflicts", type="jsonl", path=str(source_path)), "conflict_pack")

    assert result.metrics.claims_extracted == 3
    assert result.metrics.invalid_claims_rejected == 1
    assert result.metrics.conflicts_detected == 1
    assert result.pack.conflicts
    assert len(result.pack.claims) == 2


def test_cli_knowledge_build_validate_stats_and_pack_install(tmp_path: Path) -> None:
    source_path = Path(__file__).resolve().parents[1] / "examples" / "ingestion" / "simple_claims.json"

    validate = run_cli("knowledge", "validate", str(source_path), cwd=tmp_path)
    assert validate.returncode == 0
    assert "status: VALID" in validate.stdout

    build = run_cli("knowledge", "build", str(source_path), "--pack", "test_pack", cwd=tmp_path)
    assert build.returncode == 0
    assert (tmp_path / "test_pack" / "pack.json").exists()

    stats = run_cli("knowledge", "stats", "test_pack", cwd=tmp_path)
    assert stats.returncode == 0
    assert "claims:" in stats.stdout

    install = run_cli("pack", "install", "./test_pack", cwd=tmp_path)
    assert install.returncode == 0
    assert "status: INSTALLED" in install.stdout

    reinstall = run_cli("pack", "install", "./test_pack", cwd=tmp_path)
    assert reinstall.returncode == 2
    assert "error_type: PACK_EXISTS" in reinstall.stderr

    listed = run_cli("pack", "list", cwd=tmp_path)
    assert listed.returncode == 0
    assert "test_pack" in listed.stdout
