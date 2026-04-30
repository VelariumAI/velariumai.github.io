"""Deterministic bounded transitive inference."""

from __future__ import annotations

from dataclasses import dataclass

from vcse.knowledge.pack_model import KnowledgeClaim


@dataclass(frozen=True)
class TransitiveInferredClaim:
    subject: str
    relation: str
    object: str
    derived_from: tuple[str, str]
    rule: str
    trust_tier: str = "T1_INFERRED"

    @property
    def key(self) -> str:
        return "|".join([self.subject, self.relation, self.object])


def infer_transitive_claims(claims: list[KnowledgeClaim]) -> list[TransitiveInferredClaim]:
    """Infer location/containment claims with a fixed max depth of exactly two hops.

    Approved chains only:
    - located_in_country + part_of -> located_in_region
    - located_in_country + located_in_region -> located_in_region
    """

    explicit_keys = {claim.key for claim in claims}
    inferred_keys: set[str] = set()
    inferred: list[TransitiveInferredClaim] = []

    by_subject_relation: dict[tuple[str, str], list[KnowledgeClaim]] = {}
    for claim in claims:
        by_subject_relation.setdefault((claim.subject.lower(), claim.relation.lower()), []).append(claim)

    for first in claims:
        if first.relation != "located_in_country":
            continue
        second_candidates: list[KnowledgeClaim] = []
        second_candidates.extend(by_subject_relation.get((first.object.lower(), "part_of"), []))
        second_candidates.extend(by_subject_relation.get((first.object.lower(), "located_in_region"), []))
        for second in second_candidates:
            inferred_claim = TransitiveInferredClaim(
                subject=first.subject,
                relation="located_in_region",
                object=second.object,
                derived_from=(first.key, second.key),
                rule="transitive_location_containment",
            )
            if inferred_claim.key in explicit_keys or inferred_claim.key in inferred_keys:
                continue
            inferred.append(inferred_claim)
            inferred_keys.add(inferred_claim.key)

    return inferred
