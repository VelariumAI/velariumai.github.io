# VCSE Architecture

VCSE is an LLM-free verifier-centered symbolic reasoning engine. It does not
use next-token prediction. It reasons by structured state transitions, bounded
search, and deterministic verification.

```text
Input JSON / CLI demo
  -> optional ingestion adapters/templates/provenance
  -> optional DSL bundle (synonyms/patterns/rules/templates)
  -> optional symbolic index + capability retrieval (token/BM25)
  -> deterministic parser
  -> WorldStateMemory
  -> symbolic proposers
  -> search backend (Beam default, optional MCTS)
  -> verifier stack
  -> final state evaluator
  -> deterministic renderer
```

## Components

- Parser: extracts facts, constraints, and goals into typed memory objects.
- DSL: optional deterministic capability bundle for parser patterns, synonym
  rules, relation schemas, ingestion templates, proposer rules, clarification
  rules, renderer templates, and verifier stubs.
- Ingestion: adapter + template pipeline imports candidate knowledge with
  provenance and validation.
- Memory: stores claims, constraints, goals, symbol bindings, evidence, and
  contradiction indexes.
- Proposers: produce `Transition` objects only.
- Search:
  - BeamSearch (default): deterministic bounded frontier search.
  - MCTSSearch (optional): UCB1-guided bounded exploration.
  - Both backends are verifier-centered and return `SearchResult`.
- TS3: optional transient symbolic state-space analysis for loop, reachability,
  absorption, novelty, and contradiction-risk diagnostics.
- Symbolic Indexing: optional deterministic retrieval layer that selects
  relevant artifacts/packs using symbolic tokens and BM25-style scoring.
- Verifiers: judge claims, constraints, contradictions, and goal satisfaction.
- Renderer: prints evaluated state with no inference or decision logic.

## Guardrails

- Search is always bounded by depth, beam width, and node expansion limits.
- MCTS exploration is bounded by iteration count, max depth, and rollout depth.
- Final answers come only from `FinalStateEvaluator`.
- Verified answers include proof traces.
- Contradictory and unsatisfiable states are rejected as final answers.
- TS3 may diagnose and deprioritize, but may not override final-state truth.
- Ingested knowledge is never implicitly true; verifiers determine usable state.
- DSL artifacts format behavior only; verifier remains the final authority.
- Retrieval is optimization only; it may prioritize/deprioritize candidates but
  must not change truth conditions.
