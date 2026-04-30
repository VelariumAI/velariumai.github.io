"""Ledger event models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from vcse.ledger.hashing import hash_event


@dataclass(frozen=True)
class LedgerEvent:
    event_id: str
    timestamp: str
    event_type: str
    claim_id: str | None
    pack_id: str | None
    previous_hash: str
    event_hash: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "claim_id": self.claim_id,
            "pack_id": self.pack_id,
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LedgerEvent":
        return cls(
            event_id=str(payload.get("event_id", "")),
            timestamp=str(payload.get("timestamp", "")),
            event_type=str(payload.get("event_type", "")),
            claim_id=(str(payload["claim_id"]) if payload.get("claim_id") is not None else None),
            pack_id=(str(payload["pack_id"]) if payload.get("pack_id") is not None else None),
            previous_hash=str(payload.get("previous_hash", "")),
            event_hash=str(payload.get("event_hash", "")),
            payload=dict(payload.get("payload", {})),
        )


def new_event(
    *,
    event_type: str,
    payload: dict[str, Any],
    claim_id: str | None = None,
    pack_id: str | None = None,
    previous_hash: str = "GENESIS",
) -> LedgerEvent:
    event_payload = {
        "event_type": event_type,
        "claim_id": claim_id,
        "pack_id": pack_id,
        "payload": payload,
    }
    event_hash = hash_event(previous_hash, event_payload)
    return LedgerEvent(
        event_id=str(uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type=event_type,
        claim_id=claim_id,
        pack_id=pack_id,
        previous_hash=previous_hash,
        event_hash=event_hash,
        payload=dict(payload),
    )
