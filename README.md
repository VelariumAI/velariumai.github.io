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
```
