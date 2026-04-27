"""DSL validator."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from vcse.dsl.schema import ARTIFACT_TYPES, DSLDocument

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
VALID_FRAME_TYPES = {"claim", "goal", "constraint", "definition"}
VALID_ACTIONS = {"AddClaim"}
VALID_RELATION_PROPERTIES = {"transitive", "symmetric", "reflexive", "functional"}


@dataclass
class DSLValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifact_count: int = 0
    enabled_count: int = 0


class DSLValidator:
    @staticmethod
    def validate(document: DSLDocument) -> DSLValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        if not document.name:
            errors.append("Document name is required")
        if not SEMVER_RE.match(document.version):
            errors.append("Document version must be SemVer")

        seen_ids: set[str] = set()
        enabled_count = 0
        for artifact in document.artifacts:
            if not artifact.id:
                errors.append("Artifact id is required")
            elif artifact.id in seen_ids:
                errors.append(f"Duplicate artifact id: {artifact.id}")
            else:
                seen_ids.add(artifact.id)
            if artifact.type not in ARTIFACT_TYPES:
                errors.append(f"Unknown artifact type: {artifact.type}")
            if not SEMVER_RE.match(artifact.version):
                errors.append(f"Artifact {artifact.id or '<missing>'} has invalid version")
            if artifact.enabled:
                enabled_count += 1

            if artifact.type in {"parser_pattern", "ingestion_template"}:
                _validate_placeholders(artifact.payload, errors, artifact.id)
            if artifact.type == "parser_pattern":
                output = artifact.payload.get("output", {})
                frame_type = str(output.get("frame_type", "")).lower()
                if frame_type and frame_type not in VALID_FRAME_TYPES:
                    errors.append(f"Invalid frame_type in {artifact.id}: {frame_type}")
            if artifact.type == "proposer_rule":
                action = str(artifact.payload.get("then", {}).get("action", ""))
                if action and action not in VALID_ACTIONS:
                    errors.append(f"Invalid transition action in {artifact.id}: {action}")
            if artifact.type == "relation_schema":
                properties = artifact.payload.get("properties", [])
                if isinstance(properties, list):
                    invalid = [item for item in properties if item not in VALID_RELATION_PROPERTIES]
                    if invalid:
                        errors.append(f"Invalid relation properties in {artifact.id}: {invalid}")

        return DSLValidationResult(
            passed=not errors,
            errors=errors,
            warnings=warnings,
            artifact_count=len(document.artifacts),
            enabled_count=enabled_count,
        )


def _validate_placeholders(payload: object, errors: list[str], artifact_id: str) -> None:
    if isinstance(payload, dict):
        for value in payload.values():
            _validate_placeholders(value, errors, artifact_id)
        return
    if isinstance(payload, list):
        for value in payload:
            _validate_placeholders(value, errors, artifact_id)
        return
    if isinstance(payload, str):
        opens = payload.count("{")
        closes = payload.count("}")
        if opens != closes:
            errors.append(f"Invalid placeholder braces in {artifact_id}: {payload}")
            return

        consumed = set()
        for match in PLACEHOLDER_RE.finditer(payload):
            key = match.group(1)
            consumed.update(range(match.start(), match.end()))
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", key):
                errors.append(f"Invalid placeholder in {artifact_id}: {key}")

        for index, char in enumerate(payload):
            if char in "{}" and index not in consumed:
                errors.append(f"Invalid placeholder format in {artifact_id}: {payload}")
                break
