# Improvement Methodology

VCSE is not trained on text. It improves through benchmark-driven iteration:

1. Run benchmark suites.
2. Classify each failure as parser, proposer, verifier, search, or rendering.
3. Add a deterministic rule, constraint check, or search heuristic.
4. Re-run the full test and benchmark matrix.
5. Keep changes only when they improve measured correctness.

Optional future work can include grid-search heuristic tuning, solver-generated
test cases, and rule mining from proof traces.
