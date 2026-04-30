# VCSE

VCSE is an LLM-free verifier-centered symbolic reasoning engine. It does not use
next-token prediction. It reasons by structured state transitions, bounded
search, and deterministic verification.

VCSE is not a chatbot and not a wrapper around a text model. The parser extracts
structure, memory stores state, proposers emit candidate transitions, search
explores bounded paths, verifiers judge, and the renderer explains evaluated
state.

## Doctrine

- Parser extracts structure.
- Memory stores state.
- Proposer generates transitions.
- Search explores.
- Verifier judges.
- Renderer explains.

No component predicts final text. No final answer is accepted without
verifier-backed state support and, for verified answers, a proof trace.

## Architecture

```text
Input
  -> Parser / CLI JSON loader
  -> WorldStateMemory
  -> Symbolic proposers
  -> Bounded state-transition search
  -> VerifierStack
  -> FinalStateEvaluator
  -> Deterministic renderer
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Semantic Regions (v3.2)

- Deterministic grouping by relation (default behavior unchanged)
- Optional canonical grouping for inverse-relation pairs (for example, `has_capital`/`capital_of`)
- Canonical mode is opt-in via `vcse region list --canonical`


## Install

```bash
python -m pip install -e .
```

## CLI

```bash
vcse demo logic
vcse demo arithmetic
vcse demo contradiction
vcse demo logic --search mcts
vcse ingest examples/ingestion/simple_policy.txt --auto --dry-run
vcse run examples/file.json
vcse benchmark benchmarks/simple_logic_cases.jsonl
vcse benchmark benchmarks/mixed_cases.jsonl --json
vcse benchmark benchmarks/mixed_cases.jsonl --search mcts --ts3
vcse ask "All men are mortal. Socrates is a man. Can Socrates die?" --search mcts
vcse dsl validate examples/dsl/basic_logic.json
vcse ask "Can Socrates perish?" --dsl examples/dsl/mortality.json
vcse index build --dsl examples/dsl/basic_logic.json
vcse ask "Can Socrates perish?" --dsl examples/dsl/mortality.json --index
vcse generate examples/generation/contractor_policy_spec.json
vcse gauntlet benchmarks/gauntlet/
vcse serve
vcse pack validate examples/packs/logic_basic
vcse pack install examples/packs/logic_basic
vcse ask "Can Socrates die?" --pack vrm.logic.basic
vcse trust evaluate examples/trust/cross_supported_claims.jsonl
vcse trust promote examples/packs/trusted_basic
vcse ledger verify examples/packs/trusted_basic
vcse compiler validate-mapping --mapping examples/compiler/geography_mapping.json --domain domains/geography.yaml
vcse compile knowledge --source examples/knowledge/general_world_expanded.json --mapping examples/compiler/geography_mapping.json --domain domains/geography.yaml --pack-id compiled_geography --output-root examples/packs --benchmark-output benchmarks/compiled_geography_knowledge.jsonl --json
vcse adapter run --type json --source examples/knowledge/general_world_expanded.json --output /tmp/general_world_normalized.jsonl
vcse compile knowledge --adapter json --source examples/knowledge/general_world_expanded.json --mapping examples/compiler/geography_mapping.json --domain domains/geography.yaml --pack-id compiled_geography_v49 --output-root examples/packs --json
vcse pipeline run examples/pipelines/geography_compile.yaml --run-id test_geography_pipeline --json
vcse pipeline inspect test_geography_pipeline --json

## CAKE — Knowledge Acquisition

VCSE 2.7.0 adds CAKE (Controlled Acquisition of Knowledge Engine), a deterministic pipeline for collecting structured knowledge from approved sources.

```bash
vcse cake validate --source examples/cake/general_world_sources.json
vcse cake run --source examples/cake/general_world_sources.json --dry-run
vcse cake run --source examples/cake/general_world_sources.json --limit 100
```

Sources: Wikidata JSON, DBpedia TTL. Allowed domains: wikidata.org, dbpedia.org. All claims pass the trust pipeline before certification.
```

Example JSON input:

```json
{
  "facts": [
    {"subject": "Socrates", "relation": "is_a", "object": "Man"},
    {"subject": "Man", "relation": "is_a", "object": "Mortal"}
  ],
  "constraints": [],
  "goal": {"subject": "Socrates", "relation": "is_a", "object": "Mortal"}
}
```

## Benchmarks

Benchmark files are JSONL. Each case may include `expected_status` and
`expected_answer`.

```bash
vcse benchmark benchmarks/simple_logic_cases.jsonl
vcse benchmark benchmarks/arithmetic_cases.jsonl
vcse benchmark benchmarks/contradiction_cases.jsonl
vcse benchmark benchmarks/mixed_cases.jsonl
vcse benchmark benchmarks/mixed_cases.jsonl --json
```

## Ingestion

VCSE can import candidate knowledge from local JSON/JSONL/CSV/TXT (and YAML when
available) through deterministic adapters and template extraction.

Ingestion is not blind trust: imported facts are validated, applied on cloned
memory, and checked by verifiers before acceptance.

```bash
vcse ingest examples/ingestion/simple_policy.txt --auto --dry-run
vcse ingest examples/ingestion/simple_policy.txt --auto --output-memory /tmp/vcse_memory.json
vcse ingest examples/ingestion/simple_policy.txt --auto --export-pack /tmp/vcse_pack
```

See [docs/INGESTION.md](docs/INGESTION.md) and
[docs/CAPABILITY_PACKS.md](docs/CAPABILITY_PACKS.md).

Automated pipeline docs: [docs/AUTOMATED_PACK_ECOSYSTEM.md](docs/AUTOMATED_PACK_ECOSYSTEM.md).

## DSL

VCSE includes a deterministic Rule/Template DSL for loading capabilities without
changing Python core modules. DSL bundles are explicit and command-scoped.

```bash
vcse dsl validate examples/dsl/basic_logic.json
vcse dsl compile examples/dsl/basic_logic.json
vcse ask "All men are mortal. Socrates is a man. Can Socrates die?" --dsl examples/dsl/basic_logic.json
vcse ingest examples/ingestion/simple_policy.txt --dsl examples/dsl/simple_policy.json --auto --dry-run
```

See [docs/DSL.md](docs/DSL.md).

## Verified Generation

VCSE 1.7.0 adds deterministic, verifier-centered generation from explicit specs
and templates. Generation is construction plus verification.

- No free-form creative generation
- No LLM/neural dependencies
- Missing required fields return `NEEDS_CLARIFICATION`
- Artifacts include provenance and verification status

```bash
vcse generate examples/generation/contractor_policy_spec.json
vcse generate examples/generation/incomplete_policy_spec.json
vcse generate examples/generation/contractor_policy_spec.json --debug
vcse generate examples/generation/contractor_policy_spec.json --index
```

See [docs/GENERATION.md](docs/GENERATION.md).

## Gauntlet

VCSE 1.8.0 adds the Gauntlet adversarial benchmark suite for trust and
robustness evaluation across ask/generate/ingest flows.

Critical policy:

- Incorrect `VERIFIED` is a critical failure.
- `INCONCLUSIVE` is acceptable.
- No silent case skipping.

```bash
vcse gauntlet benchmarks/gauntlet/
vcse gauntlet benchmarks/gauntlet/ --json
vcse gauntlet benchmarks/gauntlet/ --search mcts --ts3 --index
```

See [docs/GAUNTLET.md](docs/GAUNTLET.md).

## API Usage

VCSE 1.9.0 provides an OpenAI-compatible API adapter while preserving verifier
semantics.

```bash
vcse serve
curl http://localhost:8000/health
curl http://localhost:8000/v1/models
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"vcse-vrm-1.9","messages":[{"role":"user","content":"All men are mortal. Socrates is a man. Can Socrates die?"}]}'
```

See [docs/API.md](docs/API.md).

## Capability Packs

VCSE 2.2.0 adds installable capability packs for modular VRM extension.

- Validate before install
- Local registry and local dependency resolution
- Deterministic activation per command
- No arbitrary code execution

```bash
vcse pack validate examples/packs/logic_basic
vcse pack install examples/packs/logic_basic
vcse pack list
vcse ask "Can Socrates perish?" --packs vrm.logic.basic,vrm.mortality.basic --index
```

See [docs/PACKS.md](docs/PACKS.md).

## Trust and Ledger

VCSE 2.3.0 adds trust tiering and immutable ledger support for auditable
knowledge certification.

- Ingest broadly, certify selectively
- Conflicted/stale knowledge is quarantined, not deleted
- Ledger is append-only and tamper-evident
- SHA-256 hash chain + Merkle pack integrity snapshots
- This is not a blockchain network

```bash
vcse trust evaluate examples/trust/cross_supported_claims.jsonl
vcse trust promote examples/packs/trusted_basic
vcse trust stats examples/packs/trusted_basic
vcse ledger verify examples/packs/trusted_basic --strict
```

See [docs/TRUST.md](docs/TRUST.md) and [docs/LEDGER.md](docs/LEDGER.md).

## Symbolic Indexing

VCSE 1.6.0 adds an optional deterministic symbolic index for capability
retrieval. It uses tokenized symbolic features with BM25-style scoring over DSL
artifacts and capability packs.

- No embeddings
- No neural dependencies
- CPU-only deterministic ranking
- Retrieval suggests candidates; verifier remains final authority

Indexing is opt-in and default behavior is unchanged.

```bash
vcse index build --dsl examples/dsl/basic_logic.json
vcse index stats --dsl examples/dsl/basic_logic.json
vcse ask "Can Socrates perish?" --dsl examples/dsl/mortality.json --index
vcse benchmark benchmarks/mixed_cases.jsonl --search mcts --ts3 --index
```

Metrics include status accuracy, answer accuracy, status rates, runtime, nodes
expanded, search depth, and proof trace length.

## Versioning

VCSE 1.1.0 adds the interaction layer. VCSE 1.0.0 was the first stable release. See [docs/VERSIONING.md](docs/VERSIONING.md).

## Improvement Methodology

VCSE is improved through benchmark-driven iteration, rule expansion, verifier
expansion, heuristic tuning, and failure analysis. It is not trained on text.

See [docs/TRAINING.md](docs/TRAINING.md).

## Strict Policy

Core implementation is CPU-only and must not add text-model dependencies. See
[docs/NO_LLM_POLICY.md](docs/NO_LLM_POLICY.md).

## Limitations

- Current parser is a structured JSON loader, not a broad natural-language
  parser.
- Current reasoning domains are small: transitive relations, equality conflicts,
  and simple numeric constraints.
- Search uses Beam Search; richer strategies are future work.
- Search backend is configurable:
  - BeamSearch (default deterministic bounded search)
  - MCTSSearch (optional exploration backend with verifier-centered scoring)
- TS3 is an optional state-space analysis layer for loop/stagnation/absorption diagnostics.
- DSL is optional and deterministic; built-ins remain active when no bundle is loaded.
- Symbolic indexing is optional and deterministic; when disabled, VCSE uses full
  bundle behavior exactly as before.
- Solver-backed proposals are optional and skipped when the external solver
  package is unavailable.

## Roadmap To 1.0.0

VCSE 1.0.0 is released. Future work tracked in docs/ROADMAP.md.

## Development

```bash
python -m pytest
```

## Production Use

```bash
python -m pip install -e .
vcse serve
vcse serve --host 0.0.0.0 --port 8000
```

```bash
docker build -t vcse .
docker run -p 8000:8000 vcse
```

See [docs/CONFIG.md](docs/CONFIG.md) and [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for runtime settings and deployment notes.

## Knowledge Automation

VCSE can build deterministic knowledge packs from local JSON, JSONL, CSV, and structured text sources.

```bash
vcse knowledge validate examples/ingestion/simple_claims.json
vcse knowledge build examples/ingestion/simple_claims.json --pack test_pack
vcse pack install ./test_pack
vcse pack list
```

See [docs/KNOWLEDGE.md](docs/KNOWLEDGE.md) for the source, validation, conflict, and pack format.

## Inverse Inference

VCSE v3.3.0 adds deterministic inverse-relation inference as a read-only query fallback.

- Uses ontology inverse definitions only (example: `has_capital -> capital_of`)
- Checks explicit claims first, then inferred inverses
- Does not write inferred claims into packs

Inspect inferred inverse claims:

```bash
vcse infer inverse --pack general_world
```

## Transitive Location Inference

VCSE v3.4.0 adds bounded two-hop transitive inference for location/containment.

- Approved chains only:
  - `located_in_country + part_of -> located_in_region`
  - `located_in_country + located_in_region -> located_in_region`
- Max inference depth is fixed at 2
- Explicit claims still win over inferred claims
- Inferred claims are runtime-only and non-persistent

Inspect inferred transitive claims:

```bash
vcse infer transitive --pack general_world
```

## Inference Explanations

VCSE v3.5.0 adds deterministic explanation rendering for inferred answers.

- Explanations are derived only from explicit claim provenance used by inference
- No new inference rules are added
- Reasoning behavior and correctness remain unchanged
- Explanations are runtime-only and non-persistent
- Explicit claim answers remain unchanged

Example:

```bash
vcse ask "What continent is Paris in?" --pack general_world
```

Output:

```text
Paris is in the Europe region because:
- Paris is in France.
- France is part of Europe.
```

Disable explanation output for inferred answers:

```bash
vcse ask "What continent is Paris in?" --pack general_world --no-explain

# Opt-in planned shard-aware execution (v4.6 pilot)
vcse ask "What is the capital of France?" --pack general_world --planned
vcse benchmark coverage --pack general_world --planned --json
```
