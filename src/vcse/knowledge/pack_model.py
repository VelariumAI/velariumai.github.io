"""Knowledge pack data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class KnowledgeProvenance:
    source_id: str
    source_type: str
    location: str
    evidence_text: str
    trust_level: str = "unrated"
    confidence: float = 0.9

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "location": self.location,
            "evidence_text": self.evidence_text,
            "trust_level": self.trust_level,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "KnowledgeProvenance":
        return cls(
            source_id=str(payload.get("source_id", "")),
            source_type=str(payload.get("source_type", "")),
            location=str(payload.get("location", "")),
            evidence_text=str(payload.get("evidence_text", "")),
            trust_level=str(payload.get("trust_level", "unrated")),
            confidence=float(payload.get("confidence", 0.9)),
        )


@dataclass(frozen=True)
class KnowledgeClaim:
    subject: str
    relation: str
    object: str
    provenance: KnowledgeProvenance
    qualifiers: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.9

    @property
    def key(self) -> str:
        return "|".join([self.subject, self.relation, self.object])

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "relation": self.relation,
            "object": self.object,
            "qualifiers": dict(sorted(self.qualifiers.items())),
            "confidence": self.confidence,
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "KnowledgeClaim":
        return cls(
            subject=str(payload["subject"]),
            relation=str(payload["relation"]),
            object=str(payload["object"]),
            qualifiers={str(k): str(v) for k, v in payload.get("qualifiers", {}).items()},
            confidence=float(payload.get("confidence", 0.9)),
            provenance=KnowledgeProvenance.from_dict(payload.get("provenance", {})),
        )


@dataclass(frozen=True)
class KnowledgeConflict:
    kind: str
    claim_keys: list[str]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "claim_keys": list(self.claim_keys),
            "reason": self.reason,
        }


@dataclass
class KnowledgePack:
    id: str
    version: str
    domain: str = "general"
    claims: list[KnowledgeClaim] = field(default_factory=list)
    templates: list[dict[str, Any]] = field(default_factory=list)
    constraints: list[dict[str, Any]] = field(default_factory=list)
    provenance: list[KnowledgeProvenance] = field(default_factory=list)
    conflicts: list[KnowledgeConflict] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def metadata(self) -> dict[str, Any]:
        provenance = self.provenance or [claim.provenance for claim in self.claims]
        return {
            "id": self.id,
            "version": self.version,
            "domain": self.domain,
            "created_at": self.created_at,
            "claim_count": len(self.claims),
            "template_count": len(self.templates),
            "constraint_count": len(self.constraints),
            "provenance_count": len(provenance),
            "conflict_count": len(self.conflicts),
            "metrics": dict(self.metrics),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.metadata(),
            "claims": [claim.to_dict() for claim in self.claims],
            "templates": list(self.templates),
            "constraints": list(self.constraints),
            "provenance": [item.to_dict() for item in (self.provenance or [c.provenance for c in self.claims])],
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
        }
