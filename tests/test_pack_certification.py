from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from shutil import copytree


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


def _benchmark_path() -> Path:
    return Path(__file__).resolve().parents[1] / "benchmarks" / "general_knowledge.jsonl"


def _prepare_candidate(tmp_path: Path, pack_id: str = "promoted_world") -> tuple[Path, Path]:
    home = tmp_path / "vcse_home"
    workspace, _ = _prepare_workspace(tmp_path)
    indexed = run_cli("pack", "index", "--dirs", str(workspace / "examples" / "packs"), pack_home=home, cwd=workspace)
    assert indexed.returncode == 0
    promote = run_cli(
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
    assert promote.returncode == 0
    return home, workspace


def test_pack_certification_valid_flow_and_no_mutation(tmp_path: Path) -> None:
    home, workspace = _prepare_candidate(tmp_path)
    source_claims = workspace / "examples" / "packs" / "promoted_world" / "claims.jsonl"
    before = _sha256(source_claims)
    cert = run_cli(
        "pack",
        "certify",
        "promoted_world",
        "--output",
        "promoted_world_certified",
        "--json",
        pack_home=home,
        cwd=workspace,
    )
    assert cert.returncode == 0
    payload = json.loads(cert.stdout)
    assert payload["status"] == "CERTIFICATION_PASSED"
    assert payload["certified_claim_count"] > 0
    output_dir = workspace / "examples" / "packs" / "promoted_world_certified"
    assert (output_dir / "claims.jsonl").exists()
    assert (output_dir / "provenance.jsonl").exists()
    manifest = json.loads((output_dir / "pack.json").read_text())
    assert manifest["lifecycle_status"] == "certified"
    assert manifest["version"] == "1.0.0"
    assert manifest["certified_from"] == "promoted_world"
    after = _sha256(source_claims)
    assert before == after


def test_pack_certification_failure_missing_provenance(tmp_path: Path) -> None:
    home, workspace = _prepare_candidate(tmp_path, pack_id="promoted_world_bad")
    source_dir = workspace / "examples" / "packs" / "promoted_world_bad"
    lines = source_dir.joinpath("claims.jsonl").read_text().splitlines()
    first = json.loads(lines[0])
    first.pop("provenance", None)
    lines[0] = json.dumps(first, sort_keys=True)
    source_dir.joinpath("claims.jsonl").write_text("\n".join(lines) + "\n")

    cert = run_cli(
        "pack",
        "certify",
        "promoted_world_bad",
        "--output",
        "promoted_world_bad_certified",
        "--json",
        pack_home=home,
        cwd=workspace,
    )
    assert cert.returncode == 2
    payload = json.loads(cert.stdout)
    assert payload["status"] == "CERTIFICATION_FAILED"
    assert payload["missing_provenance_count"] > 0
    assert not (workspace / "examples" / "packs" / "promoted_world_bad_certified").exists()


def test_pack_certification_deterministic_output(tmp_path: Path) -> None:
    home, workspace = _prepare_candidate(tmp_path, pack_id="promoted_world_seed")
    a = run_cli(
        "pack",
        "certify",
        "promoted_world_seed",
        "--output",
        "promoted_world_cert_a",
        pack_home=home,
        cwd=workspace,
    )
    b = run_cli(
        "pack",
        "certify",
        "promoted_world_seed",
        "--output",
        "promoted_world_cert_b",
        pack_home=home,
        cwd=workspace,
    )
    assert a.returncode == 0
    assert b.returncode == 0
    root = workspace / "examples" / "packs"
    assert _sha256(root / "promoted_world_cert_a" / "claims.jsonl") == _sha256(
        root / "promoted_world_cert_b" / "claims.jsonl"
    )
    assert _sha256(root / "promoted_world_cert_a" / "provenance.jsonl") == _sha256(
        root / "promoted_world_cert_b" / "provenance.jsonl"
    )
