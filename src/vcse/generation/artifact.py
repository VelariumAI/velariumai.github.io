"""Generated artifact models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ARTIFACT_STATUSES = {
    "VERIFIED_ARTIFACT",
    "INCONCLUSIVE_ARTIFACT",
    "FAILED_ARTIFACT",
    "NEEDS_CLARIFICATION",
    "CONTRADICTORY_ARTIFACT",
}


@dataclass
class GeneratedArtifact:
    id: str
    artifact_type: str
    content: Any
    template_id: str
    fields_used: dict[str, Any]
    constraints_satisfied: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    status: str = "INCONCLUSIVE_ARTIFACT"
    verifier_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "artifact_type": self.artifact_type,
            "content": self.content,
            "template_id": self.template_id,
            "fields_used": dict(self.fields_used),
            "constraints_satisfied": list(self.constraints_satisfied),
            "violations": list(self.violations),
            "provenance": dict(self.provenance),
            "status": self.status,
            "verifier_reasons": list(self.verifier_reasons),
        }
