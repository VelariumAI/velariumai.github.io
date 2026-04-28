# Inference Stability and Promotion

VCSE v3.8.0 adds a deterministic runtime framework for measuring inferred-claim stability from benchmark executions.

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

## Benchmark Coverage Output

`vcse benchmark coverage --pack <pack> --json` now includes:

- `stable_inferred_count`
- `stability_threshold_used`
