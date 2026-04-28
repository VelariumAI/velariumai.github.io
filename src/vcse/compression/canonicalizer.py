"""Canonical claim normalization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from vcse.compression.errors import CanonicalizationError


# Relation normalization map: variants → canonical form
_RELATION_CANONICAL = {
    "is_a": "is_a",
    "is_an": "is_a",
    "isa": "is_a",
    "type_of": "is_a",
    "subclass_of": "is_a",
    "subtypeof": "is_a",
    "part_of": "part_of",
    "part": "part_of",
    "has_part": "part_of",
    "contains": "contains",
    "stored_in": "stored_in",
    "located_in": "located_in",
    "related_to": "related_to",
    "depends_on": "depends_on",
    "causes": "causes",
    "enables": "enables",
    "precedes": "precedes",
    "follows": "precedes",
}


def _canonicalize_relation(relation: str) -> str:
    rel = relation.strip().lower()
    return _RELATION_CANONICAL.get(rel, rel)


def _normalize_whitespace(text: str) -> str:
    """Collapse multiple spaces to single space, strip leading/trailing."""
    return " ".join(text.split())


@dataclass(frozen=True)
class CanonicalClaim:
    """Normalized claim with deterministic field ordering."""
    subject: str
    relation: str
    object: str
    qualifiers: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        result = {
            "subject": self.subject,
            "relation": self.relation,
            "object": self.object,
        }
        if self.qualifiers:
            result["qualifiers"] = dict(self.qualifiers)
        return result


def canonicalize_claim(claim: dict[str, Any]) -> CanonicalClaim:
    """
    Convert a raw claim dict into a CanonicalClaim.

    Normalization rules:
    - subject/object: lowercase, strip whitespace
    - relation: lowercase, map to canonical form
    - qualifiers: sorted by key, each key/value normalized

    Raises CanonicalizationError on malformed input.
    """
    subject = claim.get("subject")
    relation = claim.get("relation")
    obj = claim.get("object")

    if subject is None or str(subject).strip() == "":
        raise CanonicalizationError("MISSING_SUBJECT", "claim missing subject field")
    if relation is None or str(relation).strip() == "":
        raise CanonicalizationError("MISSING_RELATION", "claim missing relation field")
    if obj is None or str(obj).strip() == "":
        raise CanonicalizationError("MISSING_OBJECT", "claim missing object field")

    subject_str = _normalize_whitespace(str(subject).strip().lower())
    relation_str = _canonicalize_relation(str(relation).strip())
    obj_str = _normalize_whitespace(str(obj).strip().lower())

    if not subject_str:
        raise CanonicalizationError("EMPTY_SUBJECT", "subject normalized to empty string")
    if not relation_str:
        raise CanonicalizationError("EMPTY_RELATION", "relation normalized to empty string")
    if not obj_str:
        raise CanonicalizationError("EMPTY_OBJECT", "object normalized to empty string")

    qualifiers_raw = claim.get("qualifiers", {})
    if not isinstance(qualifiers_raw, dict):
        qualifiers_raw = {}

    qualifier_items = []
    for k, v in qualifiers_raw.items():
        k_str = _normalize_whitespace(str(k).strip().lower())
        v_str = _normalize_whitespace(str(v).strip())
        if k_str:
            qualifier_items.append((k_str, v_str))

    qualifier_items.sort(key=lambda x: x[0])
    qualifiers = tuple(qualifier_items)

    return CanonicalClaim(
        subject=subject_str,
        relation=relation_str,
        object=obj_str,
        qualifiers=qualifiers,
    )