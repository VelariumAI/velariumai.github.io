# Ingestion

VCSE ingestion imports candidate knowledge from local structured or
semi-structured files using deterministic adapters and templates.

## Principles

- Ingested does not mean true.
- Provenance is mandatory for extracted frames.
- Verifier validates imported state.
- Contradictions are surfaced explicitly.
- Dry-run is safe and does not mutate memory.
- No network fetching, no external services, no LLM parsing.

## Pipeline

```text
source file
  -> adapter
  -> template matcher
  -> semantic frames (with provenance)
  -> validation
  -> apply to cloned memory
  -> verifier stack
  -> import status
```

## CLI

```bash
vcse ingest examples/ingestion/simple_policy.txt --auto --dry-run
vcse ingest examples/ingestion/simple_policy.txt --auto --output-memory /tmp/vcse_memory.json
vcse ingest examples/ingestion/simple_policy.txt --auto --export-pack /tmp/vcse_pack
vcse ingest examples/ingestion/simple_policy.txt --dsl examples/dsl/simple_policy.json --auto --dry-run
```

Supported extensions:

- `.json`
- `.jsonl`
- `.csv`
- `.txt`
- `.yaml` / `.yml` (when PyYAML is available)

DSL ingestion templates can be loaded per command with `--dsl` to extend
deterministic extraction patterns.
