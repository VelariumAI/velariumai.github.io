"""Constraint evaluation for generated artifacts."""

from __future__ import annotations

from typing import Any

from vcse.generation.artifact import GeneratedArtifact


def evaluate_constraints(
    artifact: GeneratedArtifact,
    constraints: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    satisfied: list[str] = []
    violations: list[str] = []

    for item in constraints:
        kind = str(item.get("kind", "")).strip().lower()
        target = str(item.get("target", "")).strip()
        if kind == "field_present":
            if _field_present(artifact.fields_used, target):
                satisfied.append(f"field_present:{target}")
            else:
                violations.append(f"missing required field: {target}")
        elif kind == "section_present":
            sections = artifact.content.get("sections") if isinstance(artifact.content, dict) else None
            if target == "sections" and isinstance(sections, list) and sections:
                satisfied.append(f"section_present:{target}")
            else:
                violations.append(f"missing required section: {target}")
        elif kind == "key_present":
            if isinstance(artifact.content, dict) and target in artifact.content:
                satisfied.append(f"key_present:{target}")
            else:
                violations.append(f"missing config key: {target}")
        else:
            violations.append(f"unsupported constraint: {kind}")

    return satisfied, violations


def _field_present(fields: dict[str, Any], key: str) -> bool:
    if key not in fields:
        return False
    value = fields[key]
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, list) and not value:
        return False
    return True
