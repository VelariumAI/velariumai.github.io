"""Domain specification loader and validator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vcse.domain.spec import (
    BenchmarkTemplateSpec,
    DomainSpec,
    InferenceRuleSpec,
    QueryPatternSpec,
    RelationSpec,
    ShardRuleSpec,
)
from vcse.semantic.relation_ontology import RELATION_MAP


class DomainSpecError(ValueError):
    """Raised for malformed or contradictory domain specs."""


def load_domain_specs(paths: list[Path]) -> dict[str, DomainSpec]:
    loaded: dict[str, DomainSpec] = {}
    for path in sorted((Path(p) for p in paths), key=lambda p: str(p)):
        spec = load_domain_spec(path)
        if spec.domain_id in loaded:
            raise DomainSpecError(f"Duplicate domain_id '{spec.domain_id}' from {path}")
        loaded[spec.domain_id] = spec
    return loaded


def load_domain_spec(path: Path) -> DomainSpec:
    source = Path(path)
    source_text = str(path)
    if source_text.startswith("http://") or source_text.startswith("https://") or source_text.startswith("http:/") or source_text.startswith("https:/"):
        raise DomainSpecError("Network loading is not allowed")
    if not source.exists():
        raise DomainSpecError(f"Domain spec not found: {source}")
    payload = _load_payload(source)
    spec = _to_domain_spec(payload, source)
    validate_domain_spec_against_ontology(spec)
    return spec


def validate_domain_spec_against_ontology(spec: DomainSpec) -> None:
    by_relation = {item.relation: item for item in spec.relations}
    for relation, definition in RELATION_MAP.items():
        if relation not in by_relation:
            continue
        item = by_relation[relation]
        if item.canonical != definition.canonical:
            raise DomainSpecError(
                f"Ontology contradiction for relation '{relation}': canonical='{item.canonical}' expected='{definition.canonical}'"
            )
        if item.inverse != definition.inverse:
            raise DomainSpecError(
                f"Ontology contradiction for relation '{relation}': inverse='{item.inverse}' expected='{definition.inverse}'"
            )


def _load_payload(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise DomainSpecError(f"Malformed JSON in {path}: {exc.msg}") from exc
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-not-found]
        except Exception as exc:
            raise DomainSpecError("PyYAML is required to load YAML domain specs") from exc
        try:
            data = yaml.safe_load(path.read_text())
        except Exception as exc:
            raise DomainSpecError(f"Malformed YAML in {path}: {exc}") from exc
    else:
        raise DomainSpecError(f"Unsupported spec format: {suffix or '<none>'}")
    if not isinstance(data, dict):
        raise DomainSpecError("Domain spec root must be an object")
    return data


def _require(root: dict[str, Any], key: str, typ: type, source: Path) -> Any:
    if key not in root:
        raise DomainSpecError(f"Missing required field '{key}' in {source}")
    value = root[key]
    if not isinstance(value, typ):
        raise DomainSpecError(f"Invalid field '{key}' in {source}: expected {typ.__name__}")
    return value


def _to_domain_spec(payload: dict[str, Any], source: Path) -> DomainSpec:
    relations_raw = _require(payload, "relations", list, source)
    query_patterns_raw = _require(payload, "query_patterns", list, source)
    shard_rules_raw = _require(payload, "shard_rules", list, source)
    inference_rules_raw = _require(payload, "inference_rules", list, source)
    benchmark_templates_raw = _require(payload, "benchmark_templates", list, source)

    relations = tuple(_to_relation_spec(item, idx, source) for idx, item in enumerate(relations_raw, start=1))
    query_patterns = tuple(_to_query_pattern_spec(item, idx, source) for idx, item in enumerate(query_patterns_raw, start=1))
    shard_rules = tuple(_to_shard_rule_spec(item, idx, source) for idx, item in enumerate(shard_rules_raw, start=1))
    inference_rules = tuple(_to_inference_rule_spec(item, idx, source) for idx, item in enumerate(inference_rules_raw, start=1))
    benchmark_templates = tuple(
        _to_benchmark_template_spec(item, idx, source) for idx, item in enumerate(benchmark_templates_raw, start=1)
    )

    relation_names = {item.relation for item in relations}
    for item in query_patterns:
        if item.relation not in relation_names:
            raise DomainSpecError(f"query_patterns references unknown relation '{item.relation}'")

    all_shard_relations = {rel for shard in shard_rules for rel in shard.relations}
    if "misc.unknown" not in {item.shard_id for item in shard_rules}:
        raise DomainSpecError("shard_rules must include misc.unknown fallback")
    for relation in relation_names:
        if relation not in all_shard_relations:
            raise DomainSpecError(f"No shard mapping for relation '{relation}'")

    return DomainSpec(
        domain_id=str(_require(payload, "domain_id", str, source)).strip(),
        name=str(_require(payload, "name", str, source)).strip(),
        version=str(_require(payload, "version", str, source)).strip(),
        relations=relations,
        query_patterns=query_patterns,
        shard_rules=shard_rules,
        inference_rules=inference_rules,
        benchmark_templates=benchmark_templates,
    )


def _to_relation_spec(item: Any, idx: int, source: Path) -> RelationSpec:
    if not isinstance(item, dict):
        raise DomainSpecError(f"relations[{idx}] must be an object")
    return RelationSpec(
        relation=str(_required_item(item, "relation", idx, "relations")).strip(),
        canonical=str(_required_item(item, "canonical", idx, "relations")).strip(),
        inverse=_optional_str(item.get("inverse")),
        domain=str(_required_item(item, "domain", idx, "relations")).strip(),
        range=str(_required_item(item, "range", idx, "relations")).strip(),
        functional=_required_bool(item, "functional", idx, "relations"),
        symmetric=_required_bool(item, "symmetric", idx, "relations"),
        transitive=_required_bool(item, "transitive", idx, "relations"),
        shard=str(_required_item(item, "shard", idx, "relations")).strip(),
    )


def _to_query_pattern_spec(item: Any, idx: int, source: Path) -> QueryPatternSpec:
    if not isinstance(item, dict):
        raise DomainSpecError(f"query_patterns[{idx}] must be an object")
    return QueryPatternSpec(
        pattern=str(_required_item(item, "pattern", idx, "query_patterns")).strip(),
        relation=str(_required_item(item, "relation", idx, "query_patterns")).strip(),
        query_type=str(_required_item(item, "query_type", idx, "query_patterns")).strip(),
        subject_slot=str(_required_item(item, "subject_slot", idx, "query_patterns")).strip(),
        object_slot=_optional_str(item.get("object_slot")),
    )


def _to_shard_rule_spec(item: Any, idx: int, source: Path) -> ShardRuleSpec:
    if not isinstance(item, dict):
        raise DomainSpecError(f"shard_rules[{idx}] must be an object")
    relations = item.get("relations")
    if not isinstance(relations, list):
        raise DomainSpecError(f"shard_rules[{idx}].relations must be a list")
    return ShardRuleSpec(
        shard_id=str(_required_item(item, "shard_id", idx, "shard_rules")).strip(),
        relations=tuple(str(v).strip() for v in relations),
    )


def _to_inference_rule_spec(item: Any, idx: int, source: Path) -> InferenceRuleSpec:
    if not isinstance(item, dict):
        raise DomainSpecError(f"inference_rules[{idx}] must be an object")
    required_relations = item.get("required_relations")
    if not isinstance(required_relations, list):
        raise DomainSpecError(f"inference_rules[{idx}].required_relations must be a list")
    max_hops = item.get("max_hops")
    if not isinstance(max_hops, int):
        raise DomainSpecError(f"inference_rules[{idx}].max_hops must be an int")
    return InferenceRuleSpec(
        rule_id=str(_required_item(item, "rule_id", idx, "inference_rules")).strip(),
        output_relation=str(_required_item(item, "output_relation", idx, "inference_rules")).strip(),
        required_relations=tuple(str(v).strip() for v in required_relations),
        max_hops=max_hops,
    )


def _to_benchmark_template_spec(item: Any, idx: int, source: Path) -> BenchmarkTemplateSpec:
    if not isinstance(item, dict):
        raise DomainSpecError(f"benchmark_templates[{idx}] must be an object")
    return BenchmarkTemplateSpec(
        relation=str(_required_item(item, "relation", idx, "benchmark_templates")).strip(),
        template=str(_required_item(item, "template", idx, "benchmark_templates")).strip(),
        expected_slot=str(_required_item(item, "expected_slot", idx, "benchmark_templates")).strip(),
    )


def _required_item(item: dict[str, Any], key: str, idx: int, section: str) -> Any:
    if key not in item:
        raise DomainSpecError(f"Missing required field '{section}[{idx}].{key}'")
    return item[key]


def _required_bool(item: dict[str, Any], key: str, idx: int, section: str) -> bool:
    value = _required_item(item, key, idx, section)
    if not isinstance(value, bool):
        raise DomainSpecError(f"{section}[{idx}].{key} must be a bool")
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip()
