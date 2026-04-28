"""Append-only ledger store."""

from __future__ import annotations

import json
from pathlib import Path

from vcse.ledger.errors import LedgerError
from vcse.ledger.events import LedgerEvent, new_event
from vcse.ledger.hashing import hash_event


class LedgerStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> list[LedgerEvent]:
        if not self.path.exists():
            return []
        text = self.path.read_text().strip()
        if not text:
            return []
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise LedgerError("INVALID_LEDGER", "ledger file must contain a JSON list")
        return [LedgerEvent.from_dict(item) for item in payload]

    def save(self, events: list[LedgerEvent]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([event.to_dict() for event in events], indent=2, sort_keys=True) + "\n")

    def append(self, event: LedgerEvent) -> LedgerEvent:
        events = self.load()
        expected_previous = events[-1].event_hash if events else "GENESIS"
        if event.previous_hash != expected_previous:
            # normalize incoming event into valid append step while preserving payload.
            event = new_event(
                event_type=event.event_type,
                payload=event.payload,
                claim_id=event.claim_id,
                pack_id=event.pack_id,
                previous_hash=expected_previous,
            )
        events.append(event)
        self.save(events)
        return event

    def verify(self) -> tuple[bool, list[str]]:
        events = self.load()
        errors: list[str] = []
        previous_hash = "GENESIS"
        for index, event in enumerate(events):
            if event.previous_hash != previous_hash:
                errors.append(f"event {index} previous_hash mismatch")
            expected = hash_event(
                previous_hash,
                {
                    "event_type": event.event_type,
                    "claim_id": event.claim_id,
                    "pack_id": event.pack_id,
                    "payload": event.payload,
                },
            )
            if event.event_hash != expected:
                errors.append(f"event {index} hash mismatch")
            previous_hash = event.event_hash
        return len(errors) == 0, errors

    def inspect(self, token: str) -> dict | None:
        for event in self.load():
            if event.event_id == token or event.claim_id == token:
                return event.to_dict()
        return None
