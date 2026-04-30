"""Rule and template DSL."""

from vcse.dsl.compiler import DSLCompiler
from vcse.dsl.errors import DSLError
from vcse.dsl.loader import DSLLoader
from vcse.dsl.registry import CapabilityRegistry, GLOBAL_REGISTRY
from vcse.dsl.schema import (
    CapabilityBundle,
    DSLArtifact,
    DSLDocument,
    GenerationTemplateRule,
)
from vcse.dsl.validator import DSLValidationResult, DSLValidator

__all__ = [
    "DSLCompiler",
    "DSLError",
    "DSLLoader",
    "CapabilityRegistry",
    "GLOBAL_REGISTRY",
    "CapabilityBundle",
    "DSLArtifact",
    "DSLDocument",
    "GenerationTemplateRule",
    "DSLValidationResult",
    "DSLValidator",
]
