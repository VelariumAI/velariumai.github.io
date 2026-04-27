# Capability Packs

VCSE can export ingestion results as capability packs.
Capability packs and DSL bundles are complementary:

- DSL defines deterministic rules/templates.
- Capability packs store extracted claims/constraints/provenance/benchmarks.
- Verifiers still decide what is usable at solve time.

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
