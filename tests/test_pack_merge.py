from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "vcse.cli", *args],
        capture_output=True,
        env=env,
        text=True,
        cwd=cwd,
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_pack(
    root: Path,
    pack_id: str,
    lifecycle_status: str,
    version: str,
    claims: list[dict],
    provenance_rows: list[dict],
) -> Path:
    pack_dir = root / "examples" / "packs" / pack_id
    pack_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": pack_id,
        "pack_id": pack_id,
        "version": version,
        "lifecycle_status": lifecycle_status,
        "claim_count": len(claims),
        "provenance_count": len(provenance_rows),
        "domain": "general",
    }
    (pack_dir / "pack.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    (pack_dir / "claims.jsonl").write_text("\n".join(json.dumps(row, sort_keys=True) for row in claims) + "\n")
    (pack_dir / "provenance.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in provenance_rows) + "\n"
    )
    return pack_dir


def _claim(subject: str, relation: str, obj: str, source_id: str) -> dict:
    provenance = {
        "source_type": "test",
        "source_id": source_id,
        "location": f"{source_id}/loc",
        "evidence_text": f"{subject} {relation} {obj}",
        "confidence": 1.0,
        "trust_level": "candidate",
    }
    return {
        "subject": subject,
        "relation": relation,
        "object": obj,
        "provenance": provenance,
    }


def _read_claim_keys(path: Path) -> list[str]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [f"{item['subject']}|{item['relation']}|{item['object']}" for item in rows]


def _prepare_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    target_claims = [
        _claim("A", "r", "B", "target"),
        _claim("C", "r", "D", "target"),
    ]
    source_claims = [
        _claim("A", "r", "B", "source"),  # duplicate by claim key
        _claim("E", "r", "F", "source"),
        _claim("G", "r", "H", "source"),
    ]
    _write_pack(
        workspace,
        "general_world",
        "candidate",
        "2.0.0",
        target_claims,
        [item["provenance"] for item in target_claims],
    )
    _write_pack(
        workspace,
        "promoted_world_certified",
        "certified",
        "1.0.0",
        source_claims,
        [item["provenance"] for item in source_claims],
    )
    return workspace


def test_valid_merge_from_certified_to_target(tmp_path: Path) -> None:
    workspace = _prepare_workspace(tmp_path)
    result = run_cli("pack", "merge", "promoted_world_certified", "--into", "general_world", "--json", cwd=workspace)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "MERGE_PASSED"
    assert payload["merged_claim_count"] == 2
    assert payload["final_claim_count"] == 4


def test_duplicate_claims_are_skipped(tmp_path: Path) -> None:
    workspace = _prepare_workspace(tmp_path)
    result = run_cli("pack", "merge", "promoted_world_certified", "--into", "general_world", "--json", cwd=workspace)
    payload = json.loads(result.stdout)
    assert payload["skipped_duplicate_count"] == 1
    keys = _read_claim_keys(workspace / "examples" / "packs" / "general_world" / "claims.jsonl")
    assert len(keys) == len(set(keys))


def test_provenance_is_preserved_and_appended(tmp_path: Path) -> None:
    workspace = _prepare_workspace(tmp_path)
    target_before = [
        json.loads(line)
        for line in (workspace / "examples" / "packs" / "general_world" / "provenance.jsonl").read_text().splitlines()
        if line.strip()
    ]
    run_cli("pack", "merge", "promoted_world_certified", "--into", "general_world", cwd=workspace)
    target_after = [
        json.loads(line)
        for line in (workspace / "examples" / "packs" / "general_world" / "provenance.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert target_after[: len(target_before)] == target_before
    assert len(target_after) == 4


def test_snapshot_created_and_rollback_possible(tmp_path: Path) -> None:
    workspace = _prepare_workspace(tmp_path)
    target_pack = workspace / "examples" / "packs" / "general_world"
    before_claims = _sha(target_pack / "claims.jsonl")
    result = run_cli("pack", "merge", "promoted_world_certified", "--into", "general_world", "--json", cwd=workspace)
    payload = json.loads(result.stdout)
    snapshot_path = Path(payload["snapshot_path"])
    if not snapshot_path.is_absolute():
        snapshot_path = workspace / snapshot_path
    assert snapshot_path.exists()
    assert _sha(snapshot_path / "claims.jsonl") == before_claims


def test_version_increment_is_minor_bump(tmp_path: Path) -> None:
    workspace = _prepare_workspace(tmp_path)
    run_cli("pack", "merge", "promoted_world_certified", "--into", "general_world", cwd=workspace)
    meta = json.loads((workspace / "examples" / "packs" / "general_world" / "pack.json").read_text())
    assert meta["version"] == "2.1.0"
    assert meta["merged_from"] == "promoted_world_certified"


def test_non_certified_source_fails(tmp_path: Path) -> None:
    workspace = _prepare_workspace(tmp_path)
    source_meta = workspace / "examples" / "packs" / "promoted_world_certified" / "pack.json"
    payload = json.loads(source_meta.read_text())
    payload["lifecycle_status"] = "candidate"
    source_meta.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    result = run_cli("pack", "merge", "promoted_world_certified", "--into", "general_world", "--json", cwd=workspace)
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["status"] == "MERGE_FAILED"


def test_merge_is_deterministic(tmp_path: Path) -> None:
    workspace_a = _prepare_workspace(tmp_path / "a")
    workspace_b = _prepare_workspace(tmp_path / "b")
    run_cli("pack", "merge", "promoted_world_certified", "--into", "general_world", cwd=workspace_a)
    run_cli("pack", "merge", "promoted_world_certified", "--into", "general_world", cwd=workspace_b)
    assert _sha(workspace_a / "examples" / "packs" / "general_world" / "claims.jsonl") == _sha(
        workspace_b / "examples" / "packs" / "general_world" / "claims.jsonl"
    )
    assert _sha(workspace_a / "examples" / "packs" / "general_world" / "provenance.jsonl") == _sha(
        workspace_b / "examples" / "packs" / "general_world" / "provenance.jsonl"
    )
