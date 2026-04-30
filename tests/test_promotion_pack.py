from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from shutil import copytree
from pathlib import Path


def run_cli(*args: str, pack_home: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    env["VCSE_PACK_HOME"] = str(pack_home)
    return subprocess.run(
        [sys.executable, "-m", "vcse.cli", *args],
        capture_output=True,
        env=env,
        text=True,
        cwd=cwd,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prepare_workspace(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = Path(__file__).resolve().parents[1]
    workspace = tmp_path / "workspace"
    source_pack = repo_root / "examples" / "packs" / "general_world"
    target_pack = workspace / "examples" / "packs" / "general_world"
    target_pack.parent.mkdir(parents=True, exist_ok=True)
    copytree(source_pack, target_pack)
    return workspace, target_pack


def _prepare_index(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "vcse_home"
    workspace, _ = _prepare_workspace(tmp_path)
    indexed = run_cli("pack", "index", "--dirs", str(workspace / "examples" / "packs"), pack_home=home, cwd=workspace)
    assert indexed.returncode == 0
    return home, workspace


def _benchmark_path() -> Path:
    return Path(__file__).resolve().parents[1] / "benchmarks" / "general_knowledge.jsonl"


def test_candidate_pack_generation_is_deterministic(tmp_path: Path) -> None:
    home, workspace = _prepare_index(tmp_path)
    first = "promoted_world_det_a"
    second = "promoted_world_det_b"
    a = run_cli(
        "infer",
        "promote",
        "--pack",
        "general_world",
        "--threshold",
        "2",
        "--benchmark",
        str(_benchmark_path()),
        "--as-pack",
        first,
        pack_home=home,
        cwd=workspace,
    )
    b = run_cli(
        "infer",
        "promote",
        "--pack",
        "general_world",
        "--threshold",
        "2",
        "--benchmark",
        str(_benchmark_path()),
        "--as-pack",
        second,
        pack_home=home,
        cwd=workspace,
    )
    assert a.returncode == 0
    assert b.returncode == 0
    root = workspace / "examples" / "packs"
    for file_name in ["claims.jsonl", "provenance.jsonl", "metrics.json", "trust_report.json"]:
        assert _sha256(root / first / file_name) == _sha256(root / second / file_name)


def test_candidate_pack_has_complete_provenance_and_lifecycle(tmp_path: Path) -> None:
    home, workspace = _prepare_index(tmp_path)
    pack_id = "promoted_world_integrity"
    result = run_cli(
        "infer",
        "promote",
        "--pack",
        "general_world",
        "--threshold",
        "2",
        "--benchmark",
        str(_benchmark_path()),
        "--as-pack",
        pack_id,
        pack_home=home,
        cwd=workspace,
    )
    assert result.returncode == 0
    pack_dir = workspace / "examples" / "packs" / pack_id
    manifest = json.loads((pack_dir / "pack.json").read_text())
    assert manifest["lifecycle_status"] == "candidate"
    assert manifest["version"] == "0.1.0"
    claims = [json.loads(line) for line in (pack_dir / "claims.jsonl").read_text().splitlines() if line.strip()]
    assert claims
    for claim in claims[:20]:
        prov = claim["provenance"]
        for key in ["source_type", "source_id", "location", "evidence_text", "confidence", "trust_level"]:
            assert key in prov
            assert str(prov[key]).strip() != ""


def test_candidate_pack_generation_does_not_mutate_existing_pack(tmp_path: Path) -> None:
    home, workspace = _prepare_index(tmp_path)
    claims_path = workspace / "examples" / "packs" / "general_world" / "claims.jsonl"
    before = _sha256(claims_path)
    result = run_cli(
        "infer",
        "promote",
        "--pack",
        "general_world",
        "--threshold",
        "2",
        "--benchmark",
        str(_benchmark_path()),
        "--as-pack",
        "promoted_world_no_mutate",
        pack_home=home,
        cwd=workspace,
    )
    assert result.returncode == 0
    after = _sha256(claims_path)
    assert before == after
