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
vcse run examples/file.json
vcse benchmark benchmarks/simple_logic_cases.jsonl
vcse benchmark benchmarks/mixed_cases.jsonl --json
vcse benchmark benchmarks/mixed_cases.jsonl --search mcts --ts3
vcse ask "All men are mortal. Socrates is a man. Can Socrates die?" --search mcts
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
- Solver-backed proposals are optional and skipped when the external solver
  package is unavailable.

## Roadmap To 1.0.0

VCSE 1.0.0 is released. Future work tracked in docs/ROADMAP.md.

## Development

```bash
python -m pytest
```
