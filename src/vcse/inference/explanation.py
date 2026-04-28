"""Deterministic explanation primitives for inferred claims."""

from __future__ import annotations

from dataclasses import dataclass

from vcse.inference.inverse import InferredClaim
from vcse.inference.transitive import TransitiveInferredClaim


@dataclass(frozen=True)
class ExplanationStep:
    subject: str
    relation: str
    object: str


@dataclass(frozen=True)
class InferenceExplanation:
    conclusion: tuple[str, str, str]
    steps: list[ExplanationStep]
    rule: str


def _parse_claim_key(claim_key: str) -> ExplanationStep:
    parts = claim_key.split("|")
    if len(parts) != 3:
        raise ValueError(f"invalid claim key: {claim_key}")
    return ExplanationStep(subject=parts[0], relation=parts[1], object=parts[2])


def build_inverse_explanation(inferred: InferredClaim) -> InferenceExplanation:
    return InferenceExplanation(
        conclusion=(inferred.subject, inferred.relation, inferred.object),
        steps=[_parse_claim_key(inferred.derived_from)],
        rule=inferred.rule,
    )


def build_transitive_explanation(inferred: TransitiveInferredClaim) -> InferenceExplanation:
    first, second = inferred.derived_from
    return InferenceExplanation(
        conclusion=(inferred.subject, inferred.relation, inferred.object),
        steps=[_parse_claim_key(first), _parse_claim_key(second)],
        rule=inferred.rule,
    )
