# Inference Stability and Promotion

VCSE v4.1.0 adds a deterministic runtime framework for measuring inferred-claim stability from benchmark executions and producing candidate promotion packs.

## Scope

- Tracks only inferred claims observed in benchmark resolution paths.
- Supports inverse and transitive inferred claims.
- Does not change reasoning behavior.
- Does not mutate packs automatically.

## Stability Definition

- A claim is considered stable when `occurrences >= threshold`.
- Default threshold is `2`.

## Commands

### Stability Metrics

```bash
vcse infer stability --pack general_world
```

Outputs:

- total inferred claims
- stable inferred claims
- inverse/transitive breakdown

### Promotion Candidate Listing

```bash
vcse infer promote --pack general_world --threshold 2
```

Outputs a deterministic candidate list only:

- `subject relation object (source inference)`

No files are written to packs by this command.

### Controlled Promotion Write Path

```bash
vcse infer promote --pack general_world --threshold 2 --write
```

Writes `promoted_claims.jsonl` (or `--output <path>`) with full provenance fields:

- `subject`, `relation`, `object`
- `source_claims`
- `inference_type`
- `promoted_at` (ISO timestamp)

Candidate pack generation:

```bash
vcse infer promote --pack general_world --threshold 2 --as-pack <pack_id>
```

Creates:

- `examples/packs/<pack_id>/pack.json`
- `examples/packs/<pack_id>/claims.jsonl`
- `examples/packs/<pack_id>/provenance.jsonl`
- `examples/packs/<pack_id>/metrics.json`
- `examples/packs/<pack_id>/trust_report.json`

Pack rules:

- `lifecycle_status = candidate`
- `version = 0.1.0`
- deterministic claim ordering
- full provenance retained for each promoted claim

Promotion is always explicit and does not modify existing packs.

### Candidate Pack Review and Validation

```bash
vcse pack review <pack_id>
vcse pack validate <pack_id>
```

`pack review` provides:

- claim count
- inference type breakdown
- sample claims

`pack validate` enforces:

- no duplicate claims
- full per-claim provenance
- structural correctness of generated artifacts

## Benchmark Coverage Output

`vcse benchmark coverage --pack <pack> --json` now includes:

- `stable_inferred_count`
- `stability_threshold_used`
