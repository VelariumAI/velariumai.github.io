# CAKE Design Spec — v2.7.0
**Controlled Acquisition of Knowledge Engine**

Date: 2026-04-27
Status: Approved
Project: VCSE (VRM) — Verified Reasoning Model
Version bump: 2.6.0 → 2.7.0

---

## 1. Goal

CAKE is an acquisition frontend for VCSE. It collects structured knowledge from approved sources, snapshots raw data immutably, extracts structured claims deterministically, and routes them into the existing ingestion → normalization → trust → ledger → pack pipeline without touching any downstream logic.

**Core principle:** CAKE collects broadly. Trust certifies narrowly.

---

## 2. Boundary of Responsibility

### CAKE owns
- Source config loading and validation
- Transport execution (file or controlled HTTP)
- Immutable snapshot storage
- Deterministic claim extraction (Wikidata JSON, DBpedia TTL)
- Acquisition run reporting (CakeRunReport)

### CAKE does NOT own (delegates to existing systems)
- Normalization → `KnowledgeNormalizer` (knowledge/normalizer.py)
- Validation → `KnowledgeValidator` (knowledge/validator.py)
- Conflict resolution → `ConflictResolver` (knowledge/resolver.py)
- Pack building → `KnowledgePackBuilder` + `KnowledgePipeline` (knowledge/pack_builder.py, pipeline.py)
- Trust evaluation + promotion → `TrustPromoter` (trust/promoter.py)
- Ledger recording → `LedgerStore` + `new_event` (ledger/store.py, events.py)

### Shared data models (reused, not duplicated)
- `KnowledgeClaim` — primary claim unit
- `KnowledgeProvenance` — provenance record
- `KnowledgePack` — pack container
- `LedgerEvent` — ledger entry
- `TrustReport` / `TrustDecision` — trust outcome

---

## 3. Architecture

```
CakeSourceConfig (JSON file)
        ↓
  [validate sources, enforce allowlist]
        ↓
CakeTransport (FileTransport | HttpStaticTransport)
        ↓
FetchedSource (raw bytes + metadata)
        ↓
CakeSnapshotStore → snapshot file (SHA-256, append-only, ~/.vcse/cake/snapshots/)
        ↓
WikidataExtractor | DBpediaExtractor
        ↓
List[KnowledgeClaim]  ← existing model, populated with full provenance
        ↓
KnowledgeNormalizer  ← existing
        ↓
KnowledgePipeline.build()  ← existing (validate, resolve, build pack)
        ↓
TrustPromoter.evaluate_claims() + .promote()  ← existing, read-only usage
        ↓
CakePackUpdater (append-only update of pack on disk)
        ↓
CakeRunReport (JSON)
```

---

## 4. New CAKE-Specific Models

Only four new data models are needed:

### CakeSource
```python
@dataclass(frozen=True)
class CakeSource:
    id: str
    source_type: str          # "local_file" | "http_static"
    format: str               # "wikidata_json" | "dbpedia_ttl" | "json" | "jsonl"
    path_or_url: str          # local path or single URL
    trust_level: str          # "unrated" | "community" | "institutional"
    enabled: bool = True
    description: str = ""
    metadata: dict = field(default_factory=dict)
```

### CakeSourceConfig
```python
@dataclass
class CakeSourceConfig:
    sources: list[CakeSource]
    version: str
    description: str
```

### FetchedSource
```python
@dataclass(frozen=True)
class FetchedSource:
    source_id: str
    raw_bytes: bytes
    content_hash: str         # SHA-256 hex
    fetched_at: str           # ISO timestamp
    transport_type: str       # "file" | "http"
    origin: str               # path or URL
```

### CakeRunReport
```python
@dataclass
class CakeRunReport:
    run_id: str
    source_id: str
    status: str               # CAKE_COMPLETE | CAKE_PARTIAL | CAKE_DRY_RUN | CAKE_FAILED
    claims_extracted: int
    claims_normalized: int
    claims_ingested: int
    trust_decisions: int
    snapshot_id: str
    errors: list[str]
    warnings: list[str]
    dry_run: bool
    timestamp: str
```

---

## 5. Transport System

```
CakeTransport (abstract interface)
    def fetch(self, source: CakeSource) -> FetchedSource
```

### FileTransport (default)
- Reads local file path
- No network
- Used in all tests and CI
- Fails with `CakeTransportError` if file missing

### HttpStaticTransport
- Fetches single URL using `urllib.request` (stdlib only)
- Requires `allow_http=True` flag (off by default)
- Domain allowlist enforced: only `wikidata.org`, `dbpedia.org`
- Rejects any domain not in allowlist with `CakeTransportError`
- No redirects to unapproved domains
- Result immediately handed to CakeSnapshotStore before extraction

**Rule:** Tests MUST NOT instantiate `HttpStaticTransport`. CI requires no internet.

---

## 6. Snapshot Store

Location: `~/.vcse/cake/snapshots/<source_id>/<sha256_prefix>_<timestamp>.snap`

Rules:
- Append-only: never overwrite an existing snapshot
- Metadata sidecar: `<snapshot_file>.meta.json` with source_id, origin, sha256, fetched_at, content_length
- `verify(snapshot_id)` recomputes SHA-256 and compares to stored hash
- `load(snapshot_id)` returns raw bytes
- On hash mismatch: raises `CakeSnapshotCorruptedError`

Snapshot ID: `<source_id>/<sha256[:16]>`

---

## 7. Extractors

Both extractors return `List[KnowledgeClaim]`. Errors raise `CakeExtractionError`. Malformed entries are skipped with a warning, not silently discarded without logging.

### WikidataExtractor
Input: Wikidata JSON (simplified entity format)
Property mappings (hardcoded, deterministic):
- `P36` → `capital_of`
- `P17` → `located_in_country`
- `P31` → `instance_of`

Provenance fields on each claim:
- `source_id` = CakeSource.id
- `source_type` = "wikidata_json"
- `location` = snapshot_id
- `evidence_text` = raw entity label + property
- `trust_level` = CakeSource.trust_level
- `snapshot_id` added to claim.qualifiers

Reject: missing entity ID, missing property value, non-string values.

### DBpediaExtractor
Input: DBpedia N-Triples / simple TTL
Parsing: stdlib `re` only — no external TTL parser.
Format: `<subject_uri> <predicate_uri> <object_uri_or_literal> .`

Extraction:
- Subject: last path segment of URI
- Predicate: last path segment of URI, underscored
- Object: last path segment or stripped literal

Reject: lines without 3 tokens, malformed URIs, comment lines (`#`).

---

## 8. Normalizer Adapter

`CakeNormalizerAdapter` is a thin wrapper — not a reimplementation:

```python
class CakeNormalizerAdapter:
    def __init__(self):
        self._normalizer = KnowledgeNormalizer()

    def normalize(self, claims: list[KnowledgeClaim]) -> list[KnowledgeClaim]:
        return [self._normalizer.normalize_claim(c) for c in claims]
```

---

## 9. Trust Integration

`CakeTrustRunner` calls existing `TrustPromoter` read-only:

```python
class CakeTrustRunner:
    def evaluate(self, claims: list[KnowledgeClaim], pack_path: Path) -> TrustReport:
        promoter = TrustPromoter()
        report = promoter.evaluate_claims([c.to_dict() for c in claims])
        # Record ledger events from report
        return report
```

CAKE does NOT modify `TrustPromoter`. If the promoter API is insufficient, a small adapter wraps it.

---

## 10. Pack Updater

`CakePackUpdater` appends new claims to an existing pack on disk:

- Reads existing `claims.jsonl`
- Deduplicates by `claim.key` (subject|relation|object)
- Appends new non-duplicate claims
- Rewrites `claims.jsonl` and `provenance.jsonl`
- Updates `metrics.json`
- Rebuilds `integrity.json` via existing `build_integrity()`
- No overwrite of existing claims

If pack does not exist, delegates to `KnowledgePipeline.build()` with `write=True`.

---

## 11. Pipeline Orchestrator

`run_cake_pipeline(source_config_path, *, limit, dry_run, allow_http, transport_type)` → `CakeRunReport`

Steps (each step must succeed or pipeline raises `CakePipelineError` and returns `CAKE_FAILED`):
1. Load + validate `CakeSourceConfig`
2. For each enabled source:
   a. Select transport (FileTransport or HttpStaticTransport)
   b. `fetch_source()` → `FetchedSource`
   c. `snapshot_store.save()` → snapshot_id
   d. Extract → `List[KnowledgeClaim]`
   e. Normalize (adapter)
   f. If `dry_run`: log, return `CAKE_DRY_RUN`
   g. `KnowledgePipeline.build()` or `CakePackUpdater.update()`
   h. `CakeTrustRunner.evaluate()`
   i. Append ledger events
3. Generate `CakeRunReport`

---

## 12. CLI Commands

All added to existing `src/vcse/cli.py` under `cake` subparser.

```
vcse cake validate --source <file>
vcse cake run --source <file> [--dry-run] [--limit N] [--allow-http] [--transport file|http] [--allow-partial]
vcse cake report <report_file>
```

Output: structured JSON to stdout. Errors to stderr.

---

## 13. Source Config Example (`examples/cake/general_world_sources.json`)

```json
{
  "version": "1.0.0",
  "description": "General world knowledge — CI-safe local files only",
  "sources": [
    {
      "id": "wikidata_capitals",
      "source_type": "local_file",
      "format": "wikidata_json",
      "path_or_url": "examples/cake/wikidata_sample.json",
      "trust_level": "community",
      "enabled": true,
      "description": "Sample Wikidata capital claims"
    },
    {
      "id": "dbpedia_countries",
      "source_type": "local_file",
      "format": "dbpedia_ttl",
      "path_or_url": "examples/cake/dbpedia_sample.ttl",
      "trust_level": "community",
      "enabled": true,
      "description": "Sample DBpedia country triples"
    }
  ]
}
```

`wikidata_sample.json` must contain entity with Paris → capital_of → France.
`dbpedia_sample.ttl` must contain matching N-Triple.
Both are static local files. No network required.

---

## 14. Tests

All tests use `FileTransport` only. `HttpStaticTransport` tested with local mock (monkeypatch `urllib.request.urlopen`).

| Test file | Coverage |
|---|---|
| `test_cake_sources.py` | valid/invalid config, domain allowlist, disabled sources |
| `test_cake_fetcher.py` | file fetch success/failure, missing file, limit |
| `test_cake_snapshot.py` | save/load/verify, no overwrite, hash mismatch |
| `test_cake_extractors.py` | wikidata valid/malformed, dbpedia valid/malformed, empty input |
| `test_cake_pipeline.py` | end-to-end dry_run, end-to-end live, CAKE_FAILED on bad source |
| `test_cake_pack_updater.py` | append new claims, deduplicate, integrity rebuild |
| `test_cake_cli.py` | validate cmd, run --dry-run, run --limit, report, bad source rejects |

---

## 15. Forbidden Patterns

Not permitted anywhere in `src/vcse/cake/`:
- `openai`, `anthropic`, `llama`, `transformers`
- `torch`, `tensorflow`, `numpy` (ML use)
- `langchain`, `llamaindex`
- `beautifulsoup`, `bs4`, `scrapy`, `selenium`, `playwright`
- `eval()`, `exec()` (except existing sandboxed use in agent/tools.py)
- Arbitrary HTTP beyond allowlisted domains

---

## 16. Files to Create

```
src/vcse/cake/
  __init__.py
  sources.py          CakeSource, CakeSourceConfig, load_source_config()
  fetcher.py          fetch_source(), FileTransport, HttpStaticTransport, CakeTransport
  snapshot.py         CakeSnapshotStore, FetchedSource, CakeSnapshot
  extractor_wikidata.py  WikidataExtractor
  extractor_dbpedia.py   DBpediaExtractor
  normalizer_adapter.py  CakeNormalizerAdapter
  trust_runner.py     CakeTrustRunner
  pack_updater.py     CakePackUpdater
  pipeline.py         run_cake_pipeline(), CakeRunReport, CakePipelineError
  reports.py          report rendering (JSON + summary text)
  errors.py           CakeError, CakeTransportError, CakeSnapshotCorruptedError,
                      CakeExtractionError, CakePipelineError, CakeConfigError

tests/
  test_cake_sources.py
  test_cake_fetcher.py
  test_cake_snapshot.py
  test_cake_extractors.py
  test_cake_pipeline.py
  test_cake_pack_updater.py
  test_cake_cli.py

examples/cake/
  general_world_sources.json
  wikidata_sample.json
  dbpedia_sample.ttl
  malformed_source.json
  disallowed_source.json

docs/
  CAKE.md
```

## 17. Files to Modify

```
src/vcse/cli.py              add `cake` subparser + subcommands
src/vcse/__init__.py         bump __version__ to "2.7.0"
pyproject.toml               bump version to "2.7.0"
```

No other files modified.

---

## 18. Verification Steps

```
python -m pytest -q
vcse cake validate --source examples/cake/general_world_sources.json
vcse cake run --source examples/cake/general_world_sources.json --dry-run
vcse cake run --source examples/cake/general_world_sources.json --limit 100
vcse cake report <output_path>
vcse gauntlet benchmarks/gauntlet/ --search mcts --ts3 --index
```

All must pass. `false_verified_count = 0` required.

---

## 19. Acceptance Criteria

- All 7 test files pass
- Pipeline runs end-to-end with `general_world_sources.json`
- Paris → capital_of → France claim flows through correctly
- No claim enters system without provenance
- No duplicate logic from existing downstream systems
- No regression in any existing feature
- Gauntlet: `false_verified_count = 0`
- Version: `2.7.0` consistent across `pyproject.toml` and `__init__.py`
- Git tag `v2.7.0` created

---

*Spec self-review passed: no TBDs, no contradictions, no ambiguity, appropriately scoped for one implementation plan.*
