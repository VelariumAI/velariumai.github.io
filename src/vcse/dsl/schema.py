"""DSL schema models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


ARTIFACT_TYPES = {
    "parser_pattern",
    "synonym",
    "relation_schema",
    "ingestion_template",
    "generation_template",
    "proposer_rule",
    "verifier_rule_stub",
    "renderer_template",
    "clarification_rule",
}


@dataclass(frozen=True)
class DSLArtifact:
    id: str
    type: str
    version: str
    description: str
    enabled: bool = True
    priority: int = 100
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DSLDocument:
    name: str
    version: str
    description: str
    artifacts: list[DSLArtifact]


@dataclass(frozen=True)
class SynonymRule:
    id: str
    pattern: str
    replacement: str
    priority: int


@dataclass(frozen=True)
class ParserPatternRule:
    id: str
    pattern: str
    output: dict[str, str]
    priority: int


@dataclass(frozen=True)
class ProposerRule:
    id: str
    when: list[dict[str, str]]
    then: dict[str, str]
    priority: int


@dataclass(frozen=True)
class ClarificationRule:
    id: str
    trigger: dict[str, Any]
    message: str
    priority: int


@dataclass(frozen=True)
class RendererTemplateRule:
    id: str
    relation: str
    template: str
    priority: int


@dataclass(frozen=True)
class IngestionTemplateRule:
    id: str
    patterns: list[str]
    output: dict[str, str]
    priority: int


@dataclass(frozen=True)
class GenerationTemplateRule:
    id: str
    artifact_type: str
    required_fields: list[str]
    optional_fields: list[str]
    body: dict[str, Any]
    constraints: list[dict[str, Any]]
    priority: int


@dataclass(frozen=True)
class VerifierRuleStub:
    id: str
    description: str
    status: str
    priority: int


@dataclass(frozen=True)
class CapabilityBundle:
    name: str
    version: str
    synonyms: list[SynonymRule] = field(default_factory=list)
    parser_patterns: list[ParserPatternRule] = field(default_factory=list)
    relation_schemas: list[dict[str, Any]] = field(default_factory=list)
    ingestion_templates: list[IngestionTemplateRule] = field(default_factory=list)
    generation_templates: list[GenerationTemplateRule] = field(default_factory=list)
    proposer_rules: list[ProposerRule] = field(default_factory=list)
    clarification_rules: list[ClarificationRule] = field(default_factory=list)
    renderer_templates: list[RendererTemplateRule] = field(default_factory=list)
    verifier_stubs: list[VerifierRuleStub] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
