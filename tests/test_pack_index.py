from __future__ import annotations

import json
from pathlib import Path

import pytest

from vcse.packs.index import PackIndex, PackIndexError


def _write_pack(path: Path, pack_id: str, version: str, trust_tiers: list[str]) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "pack.json").write_text(
        json.dumps(
            {
                "id": pack_id,
                "version": version,
                "domain": "general",
                "lifecycle_status": "candidate",
            }
        )
        + "\n"
    )
    claims = []
    for i, tier in enumerate(trust_tiers):
        claims.append(
            {
                "subject": f"s{i}",
                "relation": "rel",
                "object": f"o{i}",
                "trust_tier": tier,
                "source_ids": [f"src{i}"],
            }
        )
    (path / "claims.jsonl").write_text("".join(json.dumps(item) + "\n" for item in claims))
    (path / "provenance.jsonl").write_text("")
    return path


def test_build_and_query_index(tmp_path: Path) -> None:
    index_path = tmp_path / "index.json"
    scan_dir = tmp_path / "packs"
    _write_pack(scan_dir / "capitals_v1", "capitals", "1.0.0", ["T5_CERTIFIED", "T0_CANDIDATE"])
    _write_pack(scan_dir / "capitals_v2", "capitals", "1.1.0", ["T5_CERTIFIED"])

    index = PackIndex(index_path=index_path)
    index.build_index([scan_dir])
    rows = index.list_packs()

    assert len(rows) == 2
    assert rows[0]["pack_id"] == "capitals"
    latest = index.get_pack_metadata("capitals")
    assert latest["version"] == "1.1.0"
    exact = index.get_pack_metadata("capitals@1.0.0")
    assert exact["claim_count"] == 2
    assert exact["certified_count"] == 1
    assert exact["candidate_count"] == 1
    assert exact["region_count"] >= 1
    assert exact["avg_region_size"] > 0


def test_build_index_marks_stale_entries(tmp_path: Path) -> None:
    index_path = tmp_path / "index.json"
    scan_dir = tmp_path / "packs"
    pack_path = _write_pack(scan_dir / "capitals_v1", "capitals", "1.0.0", ["T0_CANDIDATE"])
    index = PackIndex(index_path=index_path)
    index.build_index([scan_dir])

    for child in scan_dir.iterdir():
        if child.is_dir():
            for file in child.iterdir():
                file.unlink()
            child.rmdir()

    index.build_index([scan_dir])
    stale_rows = index.list_packs(include_stale=True)
    assert stale_rows[0]["stale"] is True
    assert stale_rows[0]["pack_path"] == str(pack_path)


def test_load_index_raises_for_corrupt_file(tmp_path: Path) -> None:
    index_path = tmp_path / "index.json"
    index_path.write_text("{not valid json")
    with pytest.raises(PackIndexError, match="CORRUPTED_INDEX"):
        PackIndex(index_path=index_path).load_index()
