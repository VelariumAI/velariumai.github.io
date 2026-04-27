"""Provenance records for ingested frames."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Provenance:
    source_id: str
    source_type: str
    location: str
    evidence_text: str
    imported_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    confidence: float = 1.0
    qualifiers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "location": self.location,
            "evidence_text": self.evidence_text,
            "imported_at": self.imported_at,
            "confidence": self.confidence,
            "qualifiers": dict(self.qualifiers),
        }
