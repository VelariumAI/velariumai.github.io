from vcse.ledger.events import new_event
from vcse.ledger.hashing import hash_event


def test_ledger_event_hashing_deterministic() -> None:
    payload = {"k": "v"}
    h1 = hash_event("GENESIS", {"event_type": "CLAIM_CREATED", "claim_id": "c1", "pack_id": None, "payload": payload})
    h2 = hash_event("GENESIS", {"event_type": "CLAIM_CREATED", "claim_id": "c1", "pack_id": None, "payload": payload})
    assert h1 == h2
    e = new_event(event_type="CLAIM_CREATED", claim_id="c1", payload=payload)
    assert e.event_hash
