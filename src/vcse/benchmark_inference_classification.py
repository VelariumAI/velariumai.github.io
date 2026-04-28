"""Deterministic inference source classification."""

from __future__ import annotations

from enum import Enum

from vcse.inference.inverse import infer_inverse_claims
from vcse.inference.transitive import infer_transitive_claims
from vcse.knowledge.pack_model import KnowledgeClaim


class InferenceType(str, Enum):
    EXPLICIT = "explicit"
    INVERSE = "inverse"
    TRANSITIVE = "transitive"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


def classify_resolution_for_claim(
    claims: list[KnowledgeClaim],
    subject: str,
    relation: str,
    object_: str,
) -> InferenceType:
    target = (subject.lower(), relation.lower(), object_.lower())
    for claim in claims:
        if (claim.subject.lower(), claim.relation.lower(), claim.object.lower()) == target:
            return InferenceType.EXPLICIT

    for claim in infer_inverse_claims(claims):
        if (claim.subject.lower(), claim.relation.lower(), claim.object.lower()) == target:
            return InferenceType.INVERSE

    for claim in infer_transitive_claims(claims):
        if (claim.subject.lower(), claim.relation.lower(), claim.object.lower()) == target:
            return InferenceType.TRANSITIVE

    return InferenceType.UNKNOWN
