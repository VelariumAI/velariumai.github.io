# VCSE Architecture

VCSE is an LLM-free verifier-centered symbolic reasoning engine. It does not
use next-token prediction. It reasons by structured state transitions, bounded
search, and deterministic verification.

```text
Input JSON / CLI demo
  -> deterministic parser
  -> WorldStateMemory
  -> symbolic proposers
  -> bounded transition search
  -> verifier stack
  -> final state evaluator
  -> deterministic renderer
```

## Components

- Parser: extracts facts, constraints, and goals into typed memory objects.
- Memory: stores claims, constraints, goals, symbol bindings, evidence, and
  contradiction indexes.
- Proposers: produce `Transition` objects only.
- Search: explores bounded transition paths and prunes failed branches.
- Verifiers: judge claims, constraints, contradictions, and goal satisfaction.
- Renderer: prints evaluated state with no inference or decision logic.

## Guardrails

- Search is always bounded by depth, beam width, and node expansion limits.
- Final answers come only from `FinalStateEvaluator`.
- Verified answers include proof traces.
- Contradictory and unsatisfiable states are rejected as final answers.
