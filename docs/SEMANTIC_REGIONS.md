# Semantic Regions

Semantic Regions provide deterministic structural locality for claims.

A region is a grouping of claims by shared structure and is intended as a non-ML foundation for locality-aware retrieval and future directed reasoning.

## v3.1 Scope

- Deterministic grouping only
- No inference
- No expansion
- No probabilistic scoring
- No embeddings

## Relation Granularity (v3.1 Behavior)

- Regions are grouped strictly by relation string.
- Inverse relations are NOT merged.

Example:

`has_capital`:
- France -> Paris

`capital_of`:
- Paris -> France

These produce separate regions.

This is intentional. Semantic normalization (including inverse relation merging) is deferred to v3.2.
