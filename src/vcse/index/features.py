"""Feature extraction for symbolic index entries."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from vcse.dsl.schema import CapabilityBundle
from vcse.index.tokenizer import normalized_tokens


@dataclass(frozen=True)
class ArtifactFeatures:
    artifact_id: str
    artifact_type: str
    source_bundle: str
    priority: int
    token_freq: dict[str, int]
    relations: tuple[str, ...] = field(default_factory=tuple)
    domain_tags: tuple[str, ...] = field(default_factory=tuple)
    frame_types: tuple[str, ...] = field(default_factory=tuple)


def _to_tokens(values: list[str]) -> dict[str, int]:
    counter = Counter()
    for value in values:
        counter.update(normalized_tokens(value))
    return dict(counter)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def extract_bundle_features(bundle: CapabilityBundle) -> list[ArtifactFeatures]:
    features: list[ArtifactFeatures] = []

    for item in bundle.synonyms:
        tokens = _to_tokens([item.pattern, item.replacement, "synonym"])
        features.append(
            ArtifactFeatures(
                artifact_id=item.id,
                artifact_type="synonym",
                source_bundle=bundle.name,
                priority=item.priority,
                token_freq=tokens,
            )
        )

    for item in bundle.parser_patterns:
        output = item.output
        relation = _stringify(output.get("relation", "")).lower().strip()
        frame_type = _stringify(output.get("frame_type", "claim")).lower().strip()
        tokens = _to_tokens(
            [
                item.pattern,
                _stringify(output.get("subject", "")),
                _stringify(output.get("object", "")),
                relation,
                frame_type,
                "parser_pattern",
            ]
        )
        features.append(
            ArtifactFeatures(
                artifact_id=item.id,
                artifact_type="parser_pattern",
                source_bundle=bundle.name,
                priority=item.priority,
                token_freq=tokens,
                relations=(relation,) if relation else tuple(),
                frame_types=(frame_type,) if frame_type else tuple(),
            )
        )

    for schema in bundle.relation_schemas:
        relation = _stringify(schema.get("name", "")).lower().strip()
        tags = tuple(_stringify(tag).lower().strip() for tag in schema.get("properties", []))
        tokens = _to_tokens([relation, "relation_schema", *tags])
        features.append(
            ArtifactFeatures(
                artifact_id=_stringify(schema.get("id", relation or "relation_schema")),
                artifact_type="relation_schema",
                source_bundle=bundle.name,
                priority=int(schema.get("priority", 100)),
                token_freq=tokens,
                relations=(relation,) if relation else tuple(),
                domain_tags=tuple(tag for tag in tags if tag),
            )
        )

    for item in bundle.ingestion_templates:
        output = item.output
        relation = _stringify(output.get("relation", "")).lower().strip()
        frame_type = _stringify(output.get("frame_type", "claim")).lower().strip()
        tokens = _to_tokens(
            [
                *item.patterns,
                relation,
                frame_type,
                _stringify(output.get("subject", "")),
                _stringify(output.get("object", "")),
                "ingestion_template",
            ]
        )
        features.append(
            ArtifactFeatures(
                artifact_id=item.id,
                artifact_type="ingestion_template",
                source_bundle=bundle.name,
                priority=item.priority,
                token_freq=tokens,
                relations=(relation,) if relation else tuple(),
                frame_types=(frame_type,) if frame_type else tuple(),
            )
        )

    for item in bundle.generation_templates:
        tokens = _to_tokens(
            [
                item.artifact_type,
                "generation_template",
                " ".join(item.required_fields),
                " ".join(item.optional_fields),
                _stringify(item.body),
                _stringify(item.constraints),
            ]
        )
        features.append(
            ArtifactFeatures(
                artifact_id=item.id,
                artifact_type="generation_template",
                source_bundle=bundle.name,
                priority=item.priority,
                token_freq=tokens,
                frame_types=(item.artifact_type,),
            )
        )

    for item in bundle.proposer_rules:
        rule_texts = []
        relations: list[str] = []
        for clause in item.when:
            rule_texts.append(" ".join(f"{k} {v}" for k, v in sorted(clause.items())))
            relation = _stringify(clause.get("relation", "")).lower().strip()
            if relation:
                relations.append(relation)
        then_relation = _stringify(item.then.get("relation", "")).lower().strip()
        if then_relation:
            relations.append(then_relation)
        rule_texts.append(" ".join(f"{k} {v}" for k, v in sorted(item.then.items())))
        tokens = _to_tokens([*rule_texts, "proposer_rule"]) 
        features.append(
            ArtifactFeatures(
                artifact_id=item.id,
                artifact_type="proposer_rule",
                source_bundle=bundle.name,
                priority=item.priority,
                token_freq=tokens,
                relations=tuple(sorted(set(relations))),
            )
        )

    for item in bundle.clarification_rules:
        trigger_tokens = " ".join(f"{k} {_stringify(v)}" for k, v in sorted(item.trigger.items()))
        relation = _stringify(item.trigger.get("relation", "")).lower().strip()
        tokens = _to_tokens([trigger_tokens, item.message, "clarification_rule"]) 
        features.append(
            ArtifactFeatures(
                artifact_id=item.id,
                artifact_type="clarification_rule",
                source_bundle=bundle.name,
                priority=item.priority,
                token_freq=tokens,
                relations=(relation,) if relation else tuple(),
            )
        )

    for item in bundle.renderer_templates:
        relation = _stringify(item.relation).lower().strip()
        tokens = _to_tokens([relation, item.template, "renderer_template"]) 
        features.append(
            ArtifactFeatures(
                artifact_id=item.id,
                artifact_type="renderer_template",
                source_bundle=bundle.name,
                priority=item.priority,
                token_freq=tokens,
                relations=(relation,) if relation else tuple(),
            )
        )

    for item in bundle.verifier_stubs:
        tokens = _to_tokens([item.description, item.status, "verifier_rule_stub"]) 
        features.append(
            ArtifactFeatures(
                artifact_id=item.id,
                artifact_type="verifier_rule_stub",
                source_bundle=bundle.name,
                priority=item.priority,
                token_freq=tokens,
            )
        )

    return features
