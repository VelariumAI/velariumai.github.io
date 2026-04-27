# DSL

VCSE 1.5.0 adds a deterministic Rule/Template DSL for capability authoring without
editing Python core code.

## Purpose

- Move domain growth into auditable data files.
- Keep behavior deterministic and verifier-centered.
- Enable parser/normalizer/renderer/proposer/ingestion extension per command.

## Safety Rules

- No arbitrary code execution.
- No `eval`/`exec`.
- No network loading.
- No LLM parsing.
- Invalid DSL fails closed with structured errors.

## Supported Formats

- `.json` required.
- `.yaml` / `.yml` supported only when PyYAML is available.

## Document Shape

```json
{
  "name": "logic_basic",
  "version": "1.0.0",
  "description": "Basic logic domain rules",
  "artifacts": []
}
```

Every artifact includes:

- `id`
- `type`
- `version`
- `description`
- `enabled`
- `priority`

## Artifact Types

- `synonym`
- `parser_pattern`
- `relation_schema`
- `ingestion_template`
- `generation_template`
- `proposer_rule`
- `verifier_rule_stub`
- `renderer_template`
- `clarification_rule`

## CLI

```bash
vcse dsl validate examples/dsl/basic_logic.json
vcse dsl compile examples/dsl/basic_logic.json
vcse dsl load examples/dsl/basic_logic.json
vcse dsl list
```

Per-command DSL use:

```bash
vcse ask "All men are mortal. Socrates is a man. Can Socrates die?" --dsl examples/dsl/basic_logic.json
vcse ask "Can Socrates perish?" --dsl examples/dsl/mortality.json
vcse ingest examples/ingestion/simple_policy.txt --dsl examples/dsl/simple_policy.json --auto --dry-run
vcse benchmark benchmarks/mixed_cases.jsonl --dsl examples/dsl/basic_logic.json
vcse generate examples/generation/contractor_policy_spec.json --dsl examples/dsl/generation_policy.json
```

## Compilation Output

`vcse dsl compile` produces a deterministic capability bundle containing:

- synonyms
- parser patterns
- relation schemas
- ingestion templates
- generation templates
- proposer rules
- clarification rules
- renderer templates
- verifier stubs (registration only)

## Limitations

- Verifier logic is not implemented through DSL in v1.5.0.
- Registry persistence is in-memory only in v1.5.0.
- DSL changes behavior only when explicitly loaded.
