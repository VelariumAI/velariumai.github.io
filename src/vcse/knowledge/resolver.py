"""Duplicate and conflict resolution for knowledge claims."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgeConflict


@dataclass
class ResolutionResult:
    claims: list[KnowledgeClaim] = field(default_factory=list)
    duplicates: list[KnowledgeClaim] = field(default_factory=list)
    conflicts: list[KnowledgeConflict] = field(default_factory=list)


class ConflictResolver:
    def resolve(self, claims: list[KnowledgeClaim]) -> ResolutionResult:
        seen: dict[str, KnowledgeClaim] = {}
        output: list[KnowledgeClaim] = []
        duplicates: list[KnowledgeClaim] = []
        for claim in claims:
            if claim.key in seen:
                duplicates.append(claim)
                continue
            seen[claim.key] = claim
            output.append(claim)

        conflicts = _detect_conflicts(output)
        return ResolutionResult(claims=output, duplicates=duplicates, conflicts=conflicts)


def _detect_conflicts(claims: list[KnowledgeClaim]) -> list[KnowledgeConflict]:
    conflicts: list[KnowledgeConflict] = []
    equals_by_subject: dict[str, KnowledgeClaim] = {}
    temporal_by_slot: dict[tuple[str, str, str], KnowledgeClaim] = {}

    for claim in claims:
        if claim.relation == "equals":
            previous = equals_by_subject.get(claim.subject)
            if previous is not None and previous.object != claim.object:
                conflicts.append(
                    KnowledgeConflict(
                        kind="contradictory_claims",
                        claim_keys=[previous.key, claim.key],
                        reason=f"{claim.subject} equals both {previous.object} and {claim.object}",
                    )
                )
            else:
                equals_by_subject[claim.subject] = claim

        temporal_key = None
        for qualifier_key in ("valid_at", "effective_date"):
            if qualifier_key in claim.qualifiers:
                temporal_key = (claim.subject, claim.relation, claim.qualifiers[qualifier_key])
                break
        if temporal_key is not None:
            previous = temporal_by_slot.get(temporal_key)
            if previous is not None and previous.object != claim.object:
                conflicts.append(
                    KnowledgeConflict(
                        kind="temporal_conflict",
                        claim_keys=[previous.key, claim.key],
                        reason=f"{claim.subject} has conflicting {claim.relation} values at {temporal_key[2]}",
                    )
                )
            else:
                temporal_by_slot[temporal_key] = claim

    return conflicts
