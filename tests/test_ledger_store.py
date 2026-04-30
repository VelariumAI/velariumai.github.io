import json
from pathlib import Path

from vcse.ledger.events import new_event
from vcse.ledger.store import LedgerStore


def test_ledger_append_only_behavior_and_tamper_detection(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    store = LedgerStore(path)
    store.append(new_event(event_type="CLAIM_CREATED", claim_id="c1", payload={"value": 1}))
    store.append(new_event(event_type="TRUST_PROMOTED", claim_id="c1", payload={"tier": "T1_PROVENANCED"}))

    ok, errors = store.verify()
    assert ok is True
    assert errors == []

    data = json.loads(path.read_text())
    data[1]["payload"]["tier"] = "T5_CERTIFIED"
    path.write_text(json.dumps(data))
    ok2, errors2 = store.verify()
    assert ok2 is False
    assert errors2
