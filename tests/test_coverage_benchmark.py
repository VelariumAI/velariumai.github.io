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


def test_benchmark_coverage_text_and_json(tmp_path: Path) -> None:
    home = tmp_path / "vcse_home"
    repo_root = Path(__file__).resolve().parents[1]

    indexed = run_cli("pack", "index", "--dirs", str(repo_root / "examples" / "packs"), pack_home=home)
    assert indexed.returncode == 0

    text = run_cli("benchmark", "coverage", "--pack", "general_world", pack_home=home)
    assert text.returncode == 0
    assert "status: COVERAGE_COMPLETE" in text.stdout
    assert "coverage_rate:" in text.stdout
    assert "candidate_rate:" in text.stdout

    raw = run_cli("benchmark", "coverage", "--pack", "general_world", "--json", pack_home=home)
    assert raw.returncode == 0
    payload = json.loads(raw.stdout)
    assert payload["status"] == "COVERAGE_COMPLETE"
    assert payload["total"] >= 500
    assert payload["incorrect"] == 0
    assert "compression_ratio" in payload
    assert "compressed_size" in payload
    assert "uncompressed_size" in payload
    assert "load_time_ms" in payload
    assert "query_latency_ms" in payload


def test_benchmark_coverage_missing_pack_reports_pack_not_found(tmp_path: Path) -> None:
    home = tmp_path / "vcse_home"
    result = run_cli("benchmark", "coverage", "--pack", "does.not.exist", pack_home=home)
    assert result.returncode == 2
    assert "error_type: PACK_NOT_FOUND" in result.stderr


def test_general_knowledge_benchmark_ids_are_unique() -> None:
    benchmark_path = Path(__file__).resolve().parents[1] / "benchmarks" / "general_knowledge.jsonl"
    ids: list[str] = []
    for line in benchmark_path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        ids.append(row["id"])
    assert len(ids) >= 500
    assert len(ids) == len(set(ids))
