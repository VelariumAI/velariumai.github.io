# CAKE — Controlled Acquisition of Knowledge Engine

CAKE is the deterministic data acquisition layer for VCSE. It collects structured knowledge from approved sources, snapshots raw data immutably, extracts claims deterministically, and routes them into the trust → ledger → pack pipeline.

## Core Principle

**CAKE collects broadly. Trust certifies narrowly.**

CAKE ingests candidate claims at T0_CANDIDATE tier. Only the trust pipeline can promote them to higher tiers.

## Pipeline

```
CakeSourceConfig (JSON)
  → CakeTransport (FileTransport | HttpStaticTransport)
  → FetchedSource + CakeSnapshot (SHA-256, append-only)
  → WikidataExtractor | DBpediaExtractor
  → List[KnowledgeClaim]
  → KnowledgeNormalizer
  → KnowledgePipeline (validate → resolve → build pack)
  → TrustPromoter (evaluate + promote)
  → Append-only pack update
  → CakeRunReport (JSON)
```

## Allowed Sources

| Source Type | Format | Domain |
|---|---|---|
| local_file | wikidata_json, dbpedia_ttl, json, jsonl | any local path |
| http_static | wikidata_json, dbpedia_ttl | wikidata.org, dbpedia.org only |

HTTP sources require `--allow-http` flag. CI and tests use `local_file` only.

## CLI

```bash
# Validate source config
vcse cake validate --source examples/cake/general_world_sources.json

# Dry run (no writes)
vcse cake run --source examples/cake/general_world_sources.json --dry-run

# Live run with limit
vcse cake run --source examples/cake/general_world_sources.json --limit 100

# View report
vcse cake report <path/to/report.json>
```

## Forbidden Patterns

CAKE does not use: LLMs, neural libraries, web scrapers, arbitrary HTTP, eval/exec.

## Run Statuses

| Status | Meaning |
|---|---|
| CAKE_COMPLETE | All sources processed successfully |
| CAKE_PARTIAL | Some sources failed (use --allow-partial) |
| CAKE_DRY_RUN | Dry run — no writes |
| CAKE_FAILED | Pipeline aborted |