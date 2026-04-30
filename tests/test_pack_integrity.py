from __future__ import annotations

import json
from pathlib import Path

from vcse.compression.pack_optimizer import optimize_pack, save_compressed
from vcse.compression.runtime_index import CompressedRuntimeIndex
from vcse.packs.integrity import (
    compute_pack_hash,
    diff_packs,
    sign_pack_manifest,
    update_pack_integrity_metadata,
    verify_pack_integrity,
    verify_pack_signature,
)
from vcse.knowledge.pack_builder import KnowledgePackBuilder
from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgePack, KnowledgeProvenance


def _write_simple_pack(path: Path, country: str = "France", capital: str = "Paris", pack_id: str | None = None) -> Path:
    claim = KnowledgeClaim(
        subject=country,
        relation="has_capital",
        object=capital,
        provenance=KnowledgeProvenance(
            source_id="unit",
            source_type="local_file",
            location="memory://test",
            evidence_text=f"{country} has capital {capital}",
        ),
        created_at="2026-01-01T00:00:00+00:00",
    )
    pack = KnowledgePack(
        id=pack_id or path.name,
        version="1.0.0",
        claims=[claim],
        provenance=[claim.provenance],
        created_at="2026-01-01T00:00:00+00:00",
    )
    KnowledgePackBuilder().write_pack(pack, path)
    return path


def test_pack_hash_determinism(tmp_path: Path) -> None:
    pack_path = _write_simple_pack(tmp_path / "p1")
    first = compute_pack_hash(pack_path).pack_hash
    second = compute_pack_hash(pack_path).pack_hash
    assert first == second


def test_merkle_integrity_detects_tamper(tmp_path: Path) -> None:
    pack_path = _write_simple_pack(tmp_path / "p2")
    update_pack_integrity_metadata(pack_path)
    ok = verify_pack_integrity(pack_path)
    assert ok["valid"] is True

    claims_path = pack_path / "claims.jsonl"
    rows = [json.loads(line) for line in claims_path.read_text().splitlines() if line.strip()]
    rows[0]["object"] = "Lyon"
    claims_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))

    bad = verify_pack_integrity(pack_path)
    assert bad["valid"] is False


def test_snapshot_hash_reproducibility(tmp_path: Path) -> None:
    pack_path = _write_simple_pack(tmp_path / "p3")
    first = update_pack_integrity_metadata(pack_path)
    second = update_pack_integrity_metadata(pack_path)
    assert first["source_snapshot"]["merkle_root"] == second["source_snapshot"]["merkle_root"]


def test_pack_diff(tmp_path: Path) -> None:
    a = _write_simple_pack(tmp_path / "a", country="France", capital="Paris")
    b = _write_simple_pack(tmp_path / "b", country="France", capital="Marseille")
    d = diff_packs(a, b)
    assert len(d["added"]) == 1
    assert len(d["removed"]) == 1
    assert d["unchanged"] == 0


def test_signature_verification(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VCSE_PACK_HOME", str(tmp_path / "home"))
    pack_path = _write_simple_pack(tmp_path / "signed")
    sign_pack_manifest(pack_path, write_artifacts=True)
    ok = verify_pack_signature(pack_path)
    assert ok["valid"] is True


def test_compressed_query_execution(tmp_path: Path) -> None:
    source = Path("examples/packs/logic_basic")
    compressed = tmp_path / "logic_basic_compressed"
    pack = optimize_pack(source)
    save_compressed(pack, compressed)

    runtime = CompressedRuntimeIndex(compressed)
    matches = runtime.lookup(subject="socrates", relation="is_a")
    assert any(row["object"] == "man" for row in matches)


def test_rebuild_same_pack_produces_identical_hash(tmp_path: Path) -> None:
    first = _write_simple_pack(tmp_path / "build1", pack_id="repro_pack")
    second = _write_simple_pack(tmp_path / "build2", pack_id="repro_pack")
    hash_a = compute_pack_hash(first).pack_hash
    hash_b = compute_pack_hash(second).pack_hash
    assert hash_a == hash_b
