from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from vcse.packs.runtime_store import (
    RuntimeStore,
    RuntimeStoreCompiler,
    load_runtime_claims_if_valid,
    runtime_store_path_for_pack,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_pack(root: Path, pack_id: str = "sample_pack") -> Path:
    pack_dir = root / "examples" / "packs" / pack_id
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "pack.json").write_text(
        json.dumps(
            {
                "id": pack_id,
                "pack_id": pack_id,
                "version": "1.0.0",
                "lifecycle_status": "candidate",
                "claim_count": 2,
                "provenance_count": 2,
                "created_at": "2026-01-01T00:00:00+00:00",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    claims = [
        {
            "subject": "France",
            "relation": "has_capital",
            "object": "Paris",
            "trust_tier": "T0_CANDIDATE",
            "provenance": {
                "source_id": "s1",
                "source_type": "test",
                "location": "loc1",
                "evidence_text": "France has_capital Paris",
            },
        },
        {
            "subject": "Paris",
            "relation": "capital_of",
            "object": "France",
            "trust_tier": "T0_CANDIDATE",
            "provenance": {
                "source_id": "s2",
                "source_type": "test",
                "location": "loc2",
                "evidence_text": "Paris capital_of France",
            },
        },
    ]
    (pack_dir / "claims.jsonl").write_text("\n".join(json.dumps(row, sort_keys=True) for row in claims) + "\n")
    provenance = [
        {
            "source_id": "s1",
            "source_type": "test",
            "location": "loc1",
            "evidence_text": "France has_capital Paris",
            "inference_type": "",
        },
        {
            "source_id": "s2",
            "source_type": "test",
            "location": "loc2",
            "evidence_text": "Paris capital_of France",
            "inference_type": "inverse",
        },
    ]
    (pack_dir / "provenance.jsonl").write_text("\n".join(json.dumps(row, sort_keys=True) for row in provenance) + "\n")
    return pack_dir


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


def test_compile_creates_sqlite_store_and_inserts_claims_and_provenance(tmp_path: Path) -> None:
    pack_dir = _write_pack(tmp_path)
    store_path = runtime_store_path_for_pack("sample_pack")
    report = RuntimeStoreCompiler().compile_pack(pack_dir, tmp_path / store_path)
    assert report.status == "REBUILT"
    assert report.claim_count == 2
    assert report.provenance_count == 2
    assert report.backend == "sqlite"
    assert (tmp_path / store_path).exists()

    store = RuntimeStore(tmp_path / store_path)
    try:
        assert store.get_claim_by_key("France|has_capital|Paris") is not None
        assert len(store.get_provenance("France|has_capital|Paris")) == 1
        claims = store.get_claims_for_subject_relation("France", "has_capital")
        assert len(claims) == 1
        assert claims[0]["object"] == "Paris"
    finally:
        store.close()


def test_store_info_works(tmp_path: Path) -> None:
    pack_dir = _write_pack(tmp_path)
    compiled = run_cli("pack", "compile", str(pack_dir), "--force", "--json", cwd=tmp_path)
    assert compiled.returncode == 0
    info = run_cli("pack", "store-info", str(pack_dir), "--json", cwd=tmp_path)
    assert info.returncode == 0
    payload = json.loads(info.stdout)
    assert payload["pack_id"] == "sample_pack"
    assert payload["schema_version"] == 2
    assert payload["claim_count"] == 2
    assert payload["provenance_count"] == 2
    assert payload["store_size_bytes"] > 0
    assert payload["pack_hash"]
    assert payload["backend"] == "sqlite"
    assert payload["shard_count"] >= 1
    assert payload["entity_dictionary_count"] >= 1
    assert payload["relation_dictionary_count"] >= 1


def test_fallback_when_store_missing(tmp_path: Path) -> None:
    pack_dir = _write_pack(tmp_path)
    assert load_runtime_claims_if_valid(pack_dir, "sample_pack") is None


def test_stale_store_is_ignored(tmp_path: Path) -> None:
    pack_dir = _write_pack(tmp_path)
    store_path = tmp_path / runtime_store_path_for_pack("sample_pack")
    RuntimeStoreCompiler().compile_pack(pack_dir, store_path)
    claims_path = pack_dir / "claims.jsonl"
    lines = claims_path.read_text().splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]
    rows[0]["object"] = "Lyon"
    claims_path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n")
    assert load_runtime_claims_if_valid(pack_dir, "sample_pack") is None


def test_compile_does_not_mutate_pack_files(tmp_path: Path) -> None:
    pack_dir = _write_pack(tmp_path)
    before = {
        "pack": _sha(pack_dir / "pack.json"),
        "claims": _sha(pack_dir / "claims.jsonl"),
        "provenance": _sha(pack_dir / "provenance.jsonl"),
    }
    RuntimeStoreCompiler().compile_pack(pack_dir, tmp_path / runtime_store_path_for_pack("sample_pack"))
    after = {
        "pack": _sha(pack_dir / "pack.json"),
        "claims": _sha(pack_dir / "claims.jsonl"),
        "provenance": _sha(pack_dir / "provenance.jsonl"),
    }
    assert before == after


def test_gitignore_has_runtime_store_rules() -> None:
    text = Path(__file__).resolve().parents[1].joinpath(".gitignore").read_text()
    assert ".vcse/runtime_stores/" in text
    assert "*.sqlite" in text
