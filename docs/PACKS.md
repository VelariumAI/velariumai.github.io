# Capability Packs

VCSE capability packs are installable, versioned VRM modules.

A pack can include DSL artifacts, claims, constraints, templates, benchmarks,
and gauntlet cases. Packs extend runtime behavior but do not bypass verification.

## Principles

- Validation is required before installation.
- Packs do not execute arbitrary code.
- Dependencies are explicit and local-only in v2.2.0.
- Activation is deterministic.
- Provenance is mandatory.
- Runtime without packs behaves as before.

## Manifest

Each pack includes `pack.json` or `pack.yaml` with required fields:

- `id`, `name`, `version`, `description`, `domain`
- `authors`, `license`, `created_at`
- `vcse_min_version` (and optional `vcse_max_version`)
- `dependencies`
- `artifacts`
- `benchmarks`, `gauntlet_cases`
- `provenance`
- `integrity`

## Local Install and Registry

Installed packs are stored under:

- default: `~/.vcse/packs/`
- override: `VCSE_PACK_HOME`

Registry file:

- `~/.vcse/registry.json`

## CLI

```bash
vcse pack validate examples/packs/logic_basic
vcse pack install examples/packs/logic_basic
vcse pack list
vcse pack info vrm.logic.basic
vcse pack audit vrm.logic.basic
vcse pack uninstall vrm.logic.basic --version 1.0.0
```

JSON output is supported with `--json` on validate/install/list/info/audit/uninstall.

## Candidate Certification

Candidate packs can be certified explicitly through the CLI:

```bash
vcse pack certify <candidate_pack_id> --output <certified_pack_id>
```

Behavior:

- source pack must exist and have `lifecycle_status: candidate`
- certification is validation-gated (duplicates, provenance completeness, trust/metrics artifacts)
- source pack is never mutated
- certified output is always a new pack directory
- output lifecycle is `certified` with `version: 1.0.0`

## Runtime Activation

Use packs per command:

```bash
vcse ask "Can Socrates die?" --pack vrm.logic.basic
vcse ask "Can Socrates perish?" --packs vrm.logic.basic,vrm.mortality.basic
vcse generate examples/generation/contractor_policy_spec.json --pack vrm.policy.basic
vcse benchmark benchmarks/mixed_cases.jsonl --pack vrm.logic.basic
vcse gauntlet benchmarks/gauntlet/ --pack vrm.logic.basic
```

`--pack` may be repeated. `--packs` accepts comma-separated pack specs.
Specs may include versions (`pack_id@version`).

## Dependency Model

Supported dependency requirements:

- exact: `1.0.0`, `=1.0.0`, `==1.0.0`
- min: `>=1.0.0`
- range: `>=1.0.0,<2.0.0`

No remote fetching is performed in v2.2.0.

## Auditing

`vcse pack audit` reports:

- claims/constraints/templates/DSL counts
- provenance coverage
- contradiction count
- benchmark/gauntlet status
- dependency status
- hash integrity status

Audit is read-only and does not install or mutate packs.

## Trust Metadata

Trusted packs may include:

- `trust_report.json`
- `ledger_snapshot.json`
- `integrity.json`
- `conflicts.jsonl`
- `staleness.jsonl`

Missing trust files are warnings for compatibility with older packs.
