# Generation

VCSE generation is deterministic construction plus verification.

## Principles

- Generation is construction + verification.
- No free-form or probabilistic text generation.
- No LLM or neural dependencies.
- Artifacts are not final unless constraints pass.
- Missing required fields returns `NEEDS_CLARIFICATION`.

## Supported Artifact Types

- `plan`
- `policy`
- `structured_document`
- `config`
- `simple_code`

`simple_code` is template-limited. If execution checks are requested and code
execution is not enabled, VCSE returns `INCONCLUSIVE_ARTIFACT` with
`CODE_EXECUTION_NOT_ENABLED`.

## Pipeline

```text
spec -> validate -> template selection -> candidate generation
     -> evaluate constraints/verifier checks -> bounded repair -> rank -> result
```

## Statuses

- `VERIFIED_ARTIFACT`
- `NEEDS_CLARIFICATION`
- `INCONCLUSIVE_ARTIFACT`
- `FAILED_ARTIFACT`
- `CONTRADICTORY_ARTIFACT`

## CLI

```bash
vcse generate examples/generation/contractor_policy_spec.json
vcse generate examples/generation/incomplete_policy_spec.json
vcse generate examples/generation/contractor_policy_spec.json --debug
vcse generate examples/generation/contractor_policy_spec.json --index
vcse generate examples/generation/contractor_policy_spec.json --output /tmp/vcse_artifact.json
```

## Template Authoring

Generation templates can come from built-ins or DSL `generation_template`
artifacts. Templates render deterministic fields and constraints only.

They do not execute code, reason, or decide truth.

Generation templates may be delivered through capability packs and activated
with `--pack` / `--packs`. See [docs/PACKS.md](PACKS.md).
