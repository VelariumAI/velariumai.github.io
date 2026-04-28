"""Append-only pack updater for CAKE — no overwrites, preserves existing claims."""

from __future__ import annotations

import json
from pathlib import Path

from vcse.knowledge.dedup import deduplicate_claims
from vcse.knowledge.pack_builder import KnowledgePackBuilder
from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgePack, KnowledgeProvenance
from vcse.ledger.audit import build_integrity
from vcse.packs.index import PackIndex
from vcse.packs.lifecycle import PackLifecycleManager


def _read_claims(pack_path: Path) -> list[KnowledgeClaim]:
    claims_path = pack_path / "claims.jsonl"
    if not claims_path.exists():
        return []
    return [
        KnowledgeClaim.from_dict(json.loads(line))
        for line in claims_path.read_text().splitlines()
        if line.strip()
    ]


def _read_provenance(pack_path: Path) -> list[KnowledgeProvenance]:
    prov_path = pack_path / "provenance.jsonl"
    if not prov_path.exists():
        return []
    return [
        KnowledgeProvenance.from_dict(json.loads(line))
        for line in prov_path.read_text().splitlines()
        if line.strip()
    ]


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


class CakePackUpdater:
    """Appends new unique claims to an existing pack on disk. Never overwrites."""

    def update(self, pack_path: Path, new_claims: list[KnowledgeClaim]) -> int:
        """
        Append new_claims to pack at pack_path. Returns count of claims actually added.
        If pack does not exist, creates it via KnowledgePackBuilder.
        """
        pack_path = Path(pack_path)

        if not pack_path.exists() or not (pack_path / "claims.jsonl").exists():
            added = self._create_new_pack(pack_path, new_claims)
            PackIndex().update_entry(pack_path)
            return added

        PackLifecycleManager().assert_writable(pack_path)

        existing = _read_claims(pack_path)
        dedup = deduplicate_claims(existing, new_claims)
        to_add = dedup.unique_claims
        if not to_add:
            duplicate_provenance = [
                provenance
                for key in sorted(dedup.merged_provenance_map)
                for provenance in dedup.merged_provenance_map[key][1:]
            ]
            if duplicate_provenance:
                all_prov = _read_provenance(pack_path) + duplicate_provenance
                _write_jsonl(pack_path / "provenance.jsonl", [p.to_dict() for p in all_prov])
            return 0

        all_claims = existing + to_add
        _write_jsonl(pack_path / "claims.jsonl", [c.to_dict() for c in all_claims])

        duplicate_provenance = [
            provenance
            for key in sorted(dedup.merged_provenance_map)
            for provenance in dedup.merged_provenance_map[key][1:]
        ]
        all_prov = _read_provenance(pack_path) + [c.provenance for c in to_add] + duplicate_provenance
        _write_jsonl(pack_path / "provenance.jsonl", [p.to_dict() for p in all_prov])

        metrics_path = pack_path / "metrics.json"
        metrics = {}
        if metrics_path.exists():
            metrics = json.loads(metrics_path.read_text())
        metrics["claim_count"] = len(all_claims)
        metrics_path.write_text(json.dumps(metrics, indent=2))

        integrity = build_integrity(pack_path)
        (pack_path / "integrity.json").write_text(json.dumps(integrity, indent=2))
        PackIndex().update_entry(pack_path)

        return len(to_add)

    def _create_new_pack(self, pack_path: Path, claims: list[KnowledgeClaim]) -> int:
        pack = KnowledgePack(
            id=pack_path.name,
            version="1.0.0",
            claims=claims,
            provenance=[c.provenance for c in claims],
        )
        KnowledgePackBuilder().write_pack(pack, pack_path)
        metadata_path = pack_path / "pack.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["lifecycle_status"] = "candidate"
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
        return len(claims)
