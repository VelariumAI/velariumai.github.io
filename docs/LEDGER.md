# Immutable Ledger

> **CAKE ledger events:** CAKE acquisition runs may emit the following event types: `CAKE_FETCH`, `CAKE_SNAPSHOT`, `CAKE_INGEST`. These are recorded via the standard `LedgerStore.append()` API.

VCSE ledger is append-only and tamper-evident.

This is not a blockchain system:

- no network consensus
- no mining
- no proof-of-work
- no tokens

It uses local cryptographic integrity only.

## Event Model

Each event stores:

- `event_id`
- `timestamp`
- `event_type`
- `claim_id` (optional)
- `pack_id` (optional)
- `previous_hash`
- `event_hash`
- `payload`

`event_hash` uses SHA-256 over canonical JSON of `previous_hash + payload`.

## Integrity

- Ledger verification recomputes the full hash chain.
- Any modification is detected.
- Pack integrity uses artifact hashes plus a Merkle root.

## CLI

```bash
vcse ledger verify examples/packs/trusted_basic
vcse ledger inspect examples/packs/trusted_basic claim:1
vcse ledger export examples/packs/trusted_basic --output /tmp/ledger.json
```

Use `--strict` on `ledger verify` to fail command execution when integrity is invalid.
