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
