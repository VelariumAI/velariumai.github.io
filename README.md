# VCSE

VCSE is a verifier-centered symbolic reasoning engine prototype. It is not a
smaller LLM and it does not predict final answers directly. It constructs,
tests, and justifies state transitions inside a structured world model.

The architecture is deliberately post-LLM:

- The neural model proposes.
- The memory stores.
- The search explores.
- The verifier judges.
- The renderer explains.

Language models can be attached later as optional proposal modules, but they
are not the source of truth. VCSE is CPU-first and aimed at verifiable domains
such as logic, math, planning, code, and formal reasoning.

Phase 0 implements the minimal vertical slice: structured world-state memory,
typed transitive relations, explicit transitions, rule-based proposals,
verification, bounded beam search, final-state evaluation, rendering, and a CLI
logic demo.

Phase 1 hardens world-state memory with canonical qualifier-aware claim
identity, relation schema persistence, structured constraints, contradiction
indexing, versioned cloning, dependency paths, and JSON serialization that
preserves `TruthStatus` enums.

Phase 2 formalizes state transitions. Core paths now use `Transition` objects
with validation before application, cloned-state execution, structured
`VerificationResult` failures, and affected element tracking for `AddClaim`,
`AddConstraint`, `UpdateTruthStatus`, `BindSymbol`, `AddGoal`, `AddEvidence`,
and `RecordContradiction`.

Phase 3 completes the deterministic verifier stack with claim validation,
numeric constraint checking, equality and numeric contradiction detection, goal
satisfaction checks, and final-state classification into `VERIFIED`,
`INCONCLUSIVE`, `CONTRADICTORY`, or `UNSATISFIABLE`.

Phase 4 stabilizes bounded search with a shared `SearchNode`, `SearchConfig`,
structured `SearchResult`, verifier-integrated Beam Search, hard enforcement
of depth, beam width, and node expansion limits, early stop on `VERIFIED`, and
pruning for `CONTRADICTORY` / `UNSATISFIABLE` branches.

Phase 5 completes the symbolic proposer package with rule-based closure and
contradiction candidates, domain-specific arithmetic and symbolic-logic
proposal rules, and an optional solver-backed proposer that skips cleanly when
the external solver package is not installed.

Phase 6 hardens the renderer as a deterministic template system for final
evaluations and search results. Output now consistently includes status,
answer, proof trace, assumptions, contradictions, verifier reasons, and search
statistics.

Phase 7 completes the CPU-only CLI demo surface with `vcse demo logic`,
`vcse demo arithmetic`, `vcse demo contradiction`, `vcse run <file.json>`, and
`vcse benchmark <file.jsonl>`. JSON input is parsed into structured memory
before search and verification.

Current data flow:

```text
Input
  -> RuleBasedProposer
  -> WorldStateMemory
  -> State Transition Search
  -> VerifierStack
  -> FinalStateEvaluator
  -> ExplanationRenderer
```

Run:

```bash
python -m pytest
python -m vcse.cli demo logic
python -m vcse.cli demo arithmetic
python -m vcse.cli demo contradiction
```
