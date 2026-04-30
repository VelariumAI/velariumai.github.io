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
VALID_GENERATION_ARTIFACT_TYPES = {
    "plan",
    "policy",
    "structured_document",
    "config",
    "simple_code",
}


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
            if artifact.type == "generation_template":
                _validate_placeholders(artifact.payload, errors, artifact.id)
                artifact_type = str(artifact.payload.get("artifact_type", "")).strip().lower()
                if artifact_type not in VALID_GENERATION_ARTIFACT_TYPES:
                    errors.append(
                        f"Invalid generation artifact_type in {artifact.id}: {artifact_type}"
                    )
                required_fields = artifact.payload.get("required_fields", [])
                optional_fields = artifact.payload.get("optional_fields", [])
                if not isinstance(required_fields, list) or not all(
                    isinstance(item, str) and item.strip() for item in required_fields
                ):
                    errors.append(f"Invalid required_fields in {artifact.id}")
                if not isinstance(optional_fields, list) or not all(
                    isinstance(item, str) and item.strip() for item in optional_fields
                ):
                    errors.append(f"Invalid optional_fields in {artifact.id}")
                body = artifact.payload.get("body", {})
                if not isinstance(body, dict):
                    errors.append(f"Invalid body in {artifact.id}")
                constraints = artifact.payload.get("constraints", [])
                if not isinstance(constraints, list):
                    errors.append(f"Invalid constraints in {artifact.id}")
                placeholders = _collect_placeholders(artifact.payload.get("body", {}))
                allowed = {
                    str(item).strip()
                    for item in [*required_fields, *optional_fields]
                    if str(item).strip()
                }
                invalid = sorted(item for item in placeholders if item not in allowed)
                if invalid:
                    errors.append(
                        f"Invalid generation placeholders in {artifact.id}: {invalid}"
                    )
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


def _collect_placeholders(payload: object) -> set[str]:
    found: set[str] = set()
    if isinstance(payload, dict):
        for value in payload.values():
            found.update(_collect_placeholders(value))
        return found
    if isinstance(payload, list):
        for value in payload:
            found.update(_collect_placeholders(value))
        return found
    if isinstance(payload, str):
        for match in PLACEHOLDER_RE.finditer(payload):
            found.add(match.group(1))
    return found
