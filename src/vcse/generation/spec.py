"""Generation spec models and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vcse.generation.errors import GenerationError

SUPPORTED_ARTIFACT_TYPES = {
    "plan",
    "policy",
    "structured_document",
    "config",
    "simple_code",
}
SUPPORTED_MODES = {"strict", "explain", "debug"}


@dataclass(frozen=True)
class GenerationSpec:
    id: str
    artifact_type: str
    goal: str
    required_fields: dict[str, Any]
    constraints: list[dict[str, Any]] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    allowed_templates: list[str] = field(default_factory=list)
    source_text: str = ""
    mode: str = "strict"

    def validate(self) -> list[str]:
        missing: list[str] = []
        if self.artifact_type not in SUPPORTED_ARTIFACT_TYPES:
            raise GenerationError(
                "INVALID_ARTIFACT_TYPE",
                f"Unsupported artifact_type: {self.artifact_type}",
            )
        if self.mode not in SUPPORTED_MODES:
            raise GenerationError("INVALID_MODE", f"Unsupported mode: {self.mode}")
        if not self.goal.strip():
            raise GenerationError("INVALID_SPEC", "goal is required")
        if not isinstance(self.required_fields, dict):
            raise GenerationError("INVALID_SPEC", "required_fields must be an object")
        if not isinstance(self.constraints, list) or not all(
            isinstance(item, dict) for item in self.constraints
        ):
            raise GenerationError("INVALID_SPEC", "constraints must be a list of objects")
        if not self.success_criteria or not all(
            isinstance(item, str) and item.strip() for item in self.success_criteria
        ):
            raise GenerationError(
                "INVALID_SPEC",
                "success_criteria must be a non-empty list of strings",
            )
        for key, value in self.required_fields.items():
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(str(key))
        return missing



def spec_from_dict(payload: dict[str, Any]) -> GenerationSpec:
    if not isinstance(payload, dict):
        raise GenerationError("INVALID_SPEC", "spec root must be an object")
    return GenerationSpec(
        id=str(payload.get("id", "gen_spec")),
        artifact_type=str(payload.get("artifact_type", "")).strip(),
        goal=str(payload.get("goal", "")).strip(),
        required_fields=dict(payload.get("required_fields", {})),
        constraints=[dict(item) for item in payload.get("constraints", [])],
        success_criteria=[str(item) for item in payload.get("success_criteria", [])],
        allowed_templates=[str(item) for item in payload.get("allowed_templates", [])],
        source_text=str(payload.get("source_text", "")),
        mode=str(payload.get("mode", "strict")),
    )
