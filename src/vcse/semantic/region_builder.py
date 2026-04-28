"""Deterministic semantic region builder."""

from __future__ import annotations

import hashlib
from collections import defaultdict

from vcse.knowledge.pack_model import KnowledgeClaim
from vcse.semantic.region import SemanticRegion


def _subject_group_key(subject: str) -> str | None:
    # Optional secondary grouping for namespace-like subjects.
    for separator in (":", "/", "#"):
        if separator in subject:
            prefix = subject.split(separator, 1)[0].strip()
            if prefix:
                return prefix
    return None


def _secondary_group_key(claim: KnowledgeClaim) -> str | None:
    category = claim.qualifiers.get("category")
    if category:
        return f"category:{category.strip()}"

    subject_prefix = _subject_group_key(claim.subject)
    if subject_prefix:
        return f"subject_prefix:{subject_prefix}"
    return None


def _region_seed(relation: str, secondary: str | None) -> str:
    if secondary is None:
        return f"relation:{relation}"
    return f"relation:{relation}|secondary:{secondary}"


def _region_id(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def build_regions(claims: list[KnowledgeClaim]) -> list[SemanticRegion]:
    grouped: dict[tuple[str, str | None], list[KnowledgeClaim]] = defaultdict(list)
    for claim in claims:
        relation = claim.relation.strip()
        grouped[(relation, _secondary_group_key(claim))].append(claim)

    regions: list[SemanticRegion] = []
    for relation, secondary in sorted(grouped.keys(), key=lambda item: (item[0], item[1] or "")):
        bucket = grouped[(relation, secondary)]
        seed = _region_seed(relation, secondary)
        subjects = {claim.subject for claim in bucket}
        relations = {relation}
        regions.append(
            SemanticRegion(
                region_id=_region_id(seed),
                relations=relations,
                subjects=subjects,
                size=len(bucket),
            )
        )
    return regions
