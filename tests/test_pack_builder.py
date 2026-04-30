import json
from pathlib import Path

from vcse.knowledge.pack_builder import KnowledgePackBuilder
from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgePack, KnowledgeProvenance
from vcse.knowledge.pack_version import diff_packs, next_patch_version


def _claim(subject: str, relation: str, obj: str) -> KnowledgeClaim:
    return KnowledgeClaim(
        subject=subject,
        relation=relation,
        object=obj,
        provenance=KnowledgeProvenance(
            source_id="source",
            source_type="json",
            location="record:1",
            evidence_text=f"{subject} {relation} {obj}",
        ),
    )


def test_pack_builder_writes_integrity_files(tmp_path: Path) -> None:
    pack = KnowledgePack(
        id="test_pack",
        version="1.0.0",
        domain="general",
        claims=[_claim("employee", "is_a", "worker")],
    )

    output = KnowledgePackBuilder().write_pack(pack, tmp_path / "test_pack")

    assert (output / "pack.json").exists()
    assert (output / "claims.jsonl").exists()
    assert (output / "provenance.jsonl").exists()
    metadata = json.loads((output / "pack.json").read_text())
    assert metadata["id"] == "test_pack"
    assert metadata["claim_count"] == 1


def test_pack_version_diff_detects_claim_changes() -> None:
    old = KnowledgePack(id="pack", version="1.0.0", claims=[_claim("a", "is_a", "b")])
    new = KnowledgePack(
        id="pack",
        version="1.0.1",
        claims=[_claim("a", "is_a", "b"), _claim("a", "part_of", "c")],
    )

    diff = diff_packs(old, new)

    assert diff.added_claims == ["a|part_of|c"]
    assert next_patch_version("1.0.0") == "1.0.1"
