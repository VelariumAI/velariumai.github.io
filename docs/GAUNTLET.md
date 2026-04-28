# Gauntlet

VCSE Gauntlet is an adversarial benchmark suite for trust validation.

## Purpose

Gauntlet stress-tests reasoning, ingestion, and generation under normal and
worst-case conditions, with explicit penalties for false certainty.

Core rule: any incorrect `VERIFIED` (or `VERIFIED_ARTIFACT`) is critical.

## Categories

Gauntlet cases are organized under `benchmarks/gauntlet/`:

- `logic.jsonl`
- `arithmetic.jsonl`
- `contradiction.jsonl`
- `ambiguity.jsonl`
- `adversarial.jsonl`
- `ingestion.jsonl`
- `generation.jsonl`
- `search.jsonl`
- `scale.jsonl`
- `mixed.jsonl`

## Case Schema

Each JSONL line is one case:

- `id`
- `category`
- `input`
- `mode` (`ask` | `generate` | `ingest`)
- `expected_status`
- optional `expected_answer`
- optional `failure_if`
- optional `constraints`
- optional `notes`

Blank lines are rejected. Malformed lines fail the run.

## Scoring Rules

Per-case outcomes:

- `PASS`
- `FAIL`
- `CRITICAL_FAIL`

Critical conditions include false `VERIFIED` output when non-verified status was
expected.

## Metrics

Gauntlet reports:

- total/passed/failed/critical
- accuracy and verified accuracy
- inconclusive rate
- contradiction detection rate
- false verified count
- runtime/search/proof statistics

If `false_verified_count > 0`, overall status is `FAILED`.

## CLI

```bash
vcse gauntlet benchmarks/gauntlet/
vcse gauntlet benchmarks/gauntlet/ --json
vcse gauntlet benchmarks/gauntlet/ --search mcts --ts3 --index
vcse gauntlet benchmarks/gauntlet/ --pack vrm.logic.basic
```

Gauntlet runs can include activated packs to validate pack-extended runtime
behavior without changing verifier authority.

Exit codes:

- `0` pass
- `1` any non-critical failure
- `2` critical failure

## Adding Cases

1. Add one JSON object per line to a category file.
2. Include explicit `expected_status`.
3. Add `expected_answer` only when deterministic and stable.
4. Avoid hidden assumptions.
5. Re-run gauntlet and check `false_verified_count`.

## Interpretation

- `INCONCLUSIVE` is acceptable when evidence is insufficient.
- False certainty is not acceptable.
- Gauntlet should be reproducible with no randomness.
