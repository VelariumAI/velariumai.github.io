"""Knowledge validation."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcse.knowledge.pack_model import KnowledgeClaim


KNOWN_RELATIONS = {"is_a", "equals", "part_of", "requires"}


@dataclass
class ValidationResult:
    valid_claims: list[KnowledgeClaim] = field(default_factory=list)
    rejected_claims: list[KnowledgeClaim] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class KnowledgeValidator:
    def __init__(self, relation_schemas: set[str] | None = None) -> None:
        self.relation_schemas = set(relation_schemas or KNOWN_RELATIONS)

    def validate(self, claims: list[KnowledgeClaim]) -> ValidationResult:
        result = ValidationResult()
        for claim in claims:
            errors = self._errors_for(claim)
            if errors:
                result.rejected_claims.append(claim)
                result.errors.extend(errors)
                continue
            result.valid_claims.append(claim)
        return result

    def _errors_for(self, claim: KnowledgeClaim) -> list[str]:
        errors: list[str] = []
        if not claim.subject.strip():
            errors.append("claim missing subject")
        if not claim.relation.strip():
            errors.append("claim missing relation")
        if not claim.object.strip():
            errors.append("claim missing object")
        if claim.relation and claim.relation not in self.relation_schemas:
            errors.append(f"unknown relation: {claim.relation}")
        if not claim.provenance.source_id:
            errors.append("claim missing provenance source_id")
        if not claim.provenance.evidence_text:
            errors.append("claim missing provenance evidence_text")
        return errors
