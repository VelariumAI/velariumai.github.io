"""Provenance compression via deduplication and referencing."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProvenanceRef:
    """Compressed reference to a provenance entry."""
    source_id: str
    source_type: str
    location: str
    evidence_text: str
    trust_level: str
    confidence: float


def _provenance_fingerprint(entry: dict[str, Any]) -> str:
    """Build a deterministic fingerprint for a provenance entry."""
    parts = [
        str(entry.get("source_id", "")),
        str(entry.get("source_type", "")),
        str(entry.get("location", "")),
        str(entry.get("evidence_text", "")),
        str(entry.get("trust_level", "unrated")),
        str(entry.get("confidence", 0.9)),
    ]
    return "|".join(parts)


@dataclass
class ProvenanceCompressor:
    """
    Deduplicates provenance entries, mapping many claims to the same ref.

    Original data is fully preserved; deduplication is virtual — same
    provenance entries get the same integer ID instead of being duplicated.
    """
    def __init__(self) -> None:
        self._fp2id: dict[str, int] = {}
        self._entries: list[dict[str, Any]] = []

    def add(self, provenance_entry: dict[str, Any]) -> int:
        """
        Add a provenance entry, returning the canonical ID.

        If an identical entry was already added, returns the existing ID.
        """
        fp = _provenance_fingerprint(provenance_entry)
        if fp in self._fp2id:
            return self._fp2id[fp]
        next_id = len(self._entries)
        self._fp2id[fp] = next_id
        self._entries.append(dict(provenance_entry))
        return next_id

    def get(self, ref_id: int) -> dict[str, Any]:
        """Get the original provenance entry by ref ID."""
        return dict(self._entries[ref_id])

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {"entries": list(self._entries)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProvenanceCompressor":
        """Deserialize."""
        inst = cls()
        for entry in data.get("entries", []):
            fp = _provenance_fingerprint(entry)
            inst._fp2id[fp] = len(inst._entries)
            inst._entries.append(dict(entry))
        return inst

    @property
    def size(self) -> int:
        return len(self._entries)

    def fingerprint_to_id(self, entry: dict[str, Any]) -> int:
        """Map an entry to its ref ID, creating one if needed."""
        return self.add(entry)