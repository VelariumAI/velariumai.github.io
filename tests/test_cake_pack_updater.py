"""Tests for CakePackUpdater — append-only pack updates."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vcse.cake.pack_updater import CakePackUpdater
from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgeProvenance, KnowledgePack
from vcse.knowledge.pack_builder import KnowledgePackBuilder


def _prov(source_id: str = "src") -> KnowledgeProvenance:
    return KnowledgeProvenance(
        source_id=source_id,
        source_type="wikidata_json",
        location="snap/abc",
        evidence_text="test",
        trust_level="unrated",
    )


def _claim(subj: str, rel: str, obj: str) -> KnowledgeClaim:
    return KnowledgeClaim(subject=subj, relation=rel, object=obj, provenance=_prov())


def _build_pack(tmp_path: Path, claims: list[KnowledgeClaim]) -> Path:
    pack = KnowledgePack(
        id="test_pack",
        version="1.0.0",
        claims=claims,
        provenance=[c.provenance for c in claims],
    )
    builder = KnowledgePackBuilder()
    return builder.write_pack(pack, tmp_path / "test_pack")


def test_append_new_claims_to_existing_pack(tmp_path):
    existing = [_claim("Paris", "capital_of", "France")]
    pack_path = _build_pack(tmp_path, existing)

    new_claims = [_claim("Berlin", "capital_of", "Germany")]
    updater = CakePackUpdater()
    added = updater.update(pack_path, new_claims)

    assert added == 1
    # Verify on disk
    lines = (pack_path / "claims.jsonl").read_text().splitlines()
    subjects = [json.loads(l)["subject"] for l in lines if l.strip()]
    assert "Paris" in subjects
    assert "Berlin" in subjects


def test_duplicate_claims_not_added(tmp_path):
    existing = [_claim("Paris", "capital_of", "France")]
    pack_path = _build_pack(tmp_path, existing)

    duplicate = [_claim("Paris", "capital_of", "France")]
    updater = CakePackUpdater()
    added = updater.update(pack_path, duplicate)

    assert added == 0
    lines = (pack_path / "claims.jsonl").read_text().splitlines()
    paris_count = sum(1 for l in lines if l.strip() and json.loads(l)["subject"] == "Paris")
    assert paris_count == 1


def test_existing_claims_preserved(tmp_path):
    existing = [_claim("A", "rel", "B"), _claim("C", "rel", "D")]
    pack_path = _build_pack(tmp_path, existing)

    new_claims = [_claim("E", "rel", "F")]
    updater = CakePackUpdater()
    updater.update(pack_path, new_claims)

    lines = (pack_path / "claims.jsonl").read_text().splitlines()
    assert len([l for l in lines if l.strip()]) == 3


def test_pack_does_not_exist_creates_it(tmp_path):
    pack_path = tmp_path / "new_pack"
    new_claims = [_claim("Rome", "capital_of", "Italy")]
    updater = CakePackUpdater()
    added = updater.update(pack_path, new_claims)
    assert added == 1
    assert (pack_path / "claims.jsonl").exists()


def test_integrity_file_rebuilt_after_update(tmp_path):
    pack_path = _build_pack(tmp_path, [_claim("A", "r", "B")])
    updater = CakePackUpdater()
    updater.update(pack_path, [_claim("C", "r", "D")])
    assert (pack_path / "integrity.json").exists()
    integrity = json.loads((pack_path / "integrity.json").read_text())
    assert isinstance(integrity, dict)


def test_provenance_file_updated(tmp_path):
    pack_path = _build_pack(tmp_path, [_claim("A", "r", "B")])
    updater = CakePackUpdater()
    updater.update(pack_path, [_claim("C", "r", "D")])
    prov_lines = (pack_path / "provenance.jsonl").read_text().splitlines()
    assert len([l for l in prov_lines if l.strip()]) == 2