# Capability Packs

VCSE can export ingestion results as capability packs.

## Output Layout

```text
pack_dir/
  pack.yaml
  claims.jsonl
  constraints.jsonl
  templates.yaml
  provenance.jsonl
  benchmarks.jsonl
```

`pack.yaml` includes summary metadata:

- name
- version
- description
- created_at
- source_count
- claim_count
- constraint_count

## Guarantees

- Exported claims keep provenance linkage.
- Contradictions/warnings are preserved through ingestion status.
- Generated benchmark rows are deterministic.
