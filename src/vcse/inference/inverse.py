"""Deterministic inverse-relation inference."""

from __future__ import annotations

from dataclasses import dataclass

from vcse.knowledge.pack_model import KnowledgeClaim
from vcse.semantic.relation_ontology import RELATION_MAP


@dataclass(frozen=True)
class InferredClaim:
    subject: str
    relation: str
    object: str
    derived_from: str
    rule: str
    trust_tier: str = "T1_INFERRED"

    @property
    def key(self) -> str:
        return "|".join([self.subject, self.relation, self.object])


def infer_inverse_claims(claims: list[KnowledgeClaim]) -> list[InferredClaim]:
    explicit_keys = {claim.key for claim in claims}
    inferred: list[InferredClaim] = []
    inferred_keys: set[str] = set()

    for claim in claims:
        relation_def = RELATION_MAP.get(claim.relation)
        if relation_def is None or relation_def.inverse is None:
            continue
        if relation_def.inverse == claim.relation:
            continue
        inverse_relation = relation_def.inverse
        inferred_claim = InferredClaim(
            subject=claim.object,
            relation=inverse_relation,
            object=claim.subject,
            derived_from=claim.key,
            rule="inverse_relation",
        )
        if inferred_claim.key in explicit_keys or inferred_claim.key in inferred_keys:
            continue
        inferred.append(inferred_claim)
        inferred_keys.add(inferred_claim.key)

    return inferred
