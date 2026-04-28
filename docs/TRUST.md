# Trust Pipeline

> **CAKE entry point:** Claims acquired by CAKE enter the trust pipeline at T0_CANDIDATE tier. `CakeTrustRunner` calls `TrustPromoter.evaluate_claims()` and `TrustPromoter.promote()` — no trust logic is duplicated inside CAKE.

VCSE trust processing separates candidate knowledge from certified support.

Core workflow:

```text
ingest broadly -> attach provenance -> cluster claims -> validate cross-source support
-> detect conflicts -> detect staleness -> evaluate promotion policy -> certify selectively
```

## Trust Tiers

- `T0_CANDIDATE`
- `T1_PROVENANCED`
- `T2_SOURCE_TRUSTED`
- `T3_CROSS_SUPPORTED`
- `T4_VERIFIER_CONSISTENT`
- `T5_CERTIFIED`
- `T6_DEPRECATED`
- `T7_CONFLICTED`

Flags:

- `STALE`
- `CONFLICTED`
- `DEPRECATED`
- `SUPERSEDED`

No silent tier skipping. No silent overwrite.

## Source Authority

Source authority affects promotion eligibility, not truth.

Built-ins include:

- official government
- standards body
- academic reference
- wikidata
- wikipedia
- local file
- unknown

## Conflict and Staleness

Conflicts are detected and quarantined, not erased.
Stale claims are flagged, not deleted.

## CLI

```bash
vcse trust evaluate examples/trust/cross_supported_claims.jsonl
vcse trust evaluate examples/trust/conflicting_claims.jsonl
vcse trust promote examples/packs/trusted_basic
vcse trust stats examples/packs/trusted_basic
vcse trust conflicts examples/packs/trusted_basic
vcse trust stale examples/packs/trusted_basic
```

Use `--json` for structured output and `--policy <file>` to load explicit promotion policy.
