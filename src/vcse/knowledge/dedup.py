"""Cross-run exact-key claim deduplication."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgeProvenance


@dataclass(frozen=True)
class DedupResult:
    unique_claims: list[KnowledgeClaim] = field(default_factory=list)
    duplicates_detected: list[KnowledgeClaim] = field(default_factory=list)
    merged_provenance_map: dict[str, list[KnowledgeProvenance]] = field(default_factory=dict)


def deduplicate_claims(
    existing_claims: list[KnowledgeClaim],
    new_claims: list[KnowledgeClaim],
) -> DedupResult:
    if not new_claims:
        return DedupResult(unique_claims=[], duplicates_detected=[], merged_provenance_map={})

    existing_by_key = {claim.key: claim for claim in existing_claims}
    dup_by_key: dict[str, list[KnowledgeClaim]] = {}
    unique_claims: list[KnowledgeClaim] = []
    duplicates_detected: list[KnowledgeClaim] = []

    for claim in new_claims:
        if claim.key in existing_by_key:
            duplicates_detected.append(claim)
            dup_by_key.setdefault(claim.key, []).append(claim)
            continue
        unique_claims.append(claim)

    merged_provenance_map: dict[str, list[KnowledgeProvenance]] = {}
    for key in sorted(dup_by_key):
        merged_provenance_map[key] = [existing_by_key[key].provenance] + [
            claim.provenance for claim in dup_by_key[key]
        ]

    return DedupResult(
        unique_claims=unique_claims,
        duplicates_detected=duplicates_detected,
        merged_provenance_map=merged_provenance_map,
    )
