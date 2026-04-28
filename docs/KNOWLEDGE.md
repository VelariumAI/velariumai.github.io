# Knowledge Automation

VCSE knowledge automation turns local structured and semi-structured sources into verified knowledge packs.

The flow is deterministic:

```text
source -> extraction -> normalization -> validation -> conflict resolution -> pack build
```

## Sources

Supported local source types:

- JSON
- JSONL
- CSV
- structured text

Each source has an id, type, trust level, update frequency, and optional schema hint. Network-backed sources are reserved for a later release.

## Extraction

Extraction uses templates, DSL-compatible patterns, and fixed pattern matching. It creates candidate claims with mandatory provenance. Bad rows are preserved as candidates when possible so validation can reject them explicitly.

Example:

```text
Paris is the capital of France
```

becomes:

```json
{"subject": "Paris", "relation": "is_a", "object": "capital_of_France"}
```

## Validation

Every candidate claim is checked for:

- subject, relation, and object
- known relation schema
- provenance source and evidence text

Invalid claims are rejected and counted in metrics.

## Conflict Handling

VCSE detects duplicate claims, contradictory equality claims, and temporal conflicts. Conflicts are stored in the pack; claims are not silently overwritten.

## Packs

`vcse knowledge build` writes a pack directory:

```text
pack/
  pack.json
  pack.yaml
  claims.jsonl
  constraints.jsonl
  templates.json
  provenance.jsonl
  conflicts.jsonl
  metrics.json
```

## CLI

```bash
vcse knowledge validate examples/ingestion/simple_claims.json
vcse knowledge build examples/ingestion/simple_claims.json --pack test_pack
vcse knowledge stats test_pack
vcse pack install ./test_pack
vcse pack list
```

Installing a pack is local and deterministic. Existing installed packs are not overwritten.

For pack manifests, dependency handling, install/list/info/audit, and runtime
activation, see [docs/PACKS.md](PACKS.md).
