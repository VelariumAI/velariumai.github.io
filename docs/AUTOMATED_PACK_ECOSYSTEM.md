# Automated Pack Ecosystem (v5.0.0)

VCSE now supports deterministic end-to-end pack pipelines:

`source -> adapter -> compiler -> candidate pack -> validate -> review`

## Run

```bash
vcse pipeline run examples/pipelines/geography_compile.yaml
vcse pipeline run examples/pipelines/geography_compile.yaml --run-id test_geography_pipeline --json
```

## Inspect

```bash
vcse pipeline inspect test_geography_pipeline
vcse pipeline inspect test_geography_pipeline --json
```

## Output Artifacts

Each run writes:

- `.vcse/pipeline_runs/<run_id>/normalized.jsonl`
- `.vcse/pipeline_runs/<run_id>/compile_report.json`
- `.vcse/pipeline_runs/<run_id>/validation_report.json`
- `.vcse/pipeline_runs/<run_id>/review_report.json`
- `.vcse/pipeline_runs/<run_id>/benchmark_report.json`
- `.vcse/pipeline_runs/<run_id>/pipeline_report.json`

Candidate packs are generated under `examples/packs/<pack_id>/`.

## Safety Rules

- Deterministic execution only
- No auto-certification
- No auto-merge
- No network ingestion
- No NLP/embeddings
- Clear fail-fast stage errors
- Existing canonical packs must not be mutated
