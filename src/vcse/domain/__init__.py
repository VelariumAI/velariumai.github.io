"""Domain packs and declarative domain specs."""

from vcse.domain.base import DomainPack, RelationSchema, ProposerRule, VerifierRule
from vcse.domain.logic import LogicDomainPack
from vcse.domain.arithmetic import ArithmeticDomainPack
from vcse.domain.eligibility import EligibilityDomainPack
from vcse.domain.loader import DomainSpecError, load_domain_spec, load_domain_specs, validate_domain_spec_against_ontology
from vcse.domain.spec import (
    BenchmarkTemplateSpec,
    DomainSpec,
    InferenceRuleSpec,
    QueryPatternSpec,
    RelationSpec,
    ShardRuleSpec,
)

__all__ = [
    "DomainPack",
    "RelationSchema",
    "ProposerRule",
    "VerifierRule",
    "LogicDomainPack",
    "ArithmeticDomainPack",
    "EligibilityDomainPack",
    "DomainSpecError",
    "load_domain_spec",
    "load_domain_specs",
    "validate_domain_spec_against_ontology",
    "DomainSpec",
    "RelationSpec",
    "QueryPatternSpec",
    "ShardRuleSpec",
    "InferenceRuleSpec",
    "BenchmarkTemplateSpec",
]
