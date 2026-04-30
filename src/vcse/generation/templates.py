"""Deterministic generation templates."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from vcse.dsl.schema import CapabilityBundle

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


@dataclass(frozen=True)
class GenerationTemplate:
    id: str
    artifact_type: str
    required_fields: list[str]
    optional_fields: list[str] = field(default_factory=list)
    body: dict[str, Any] = field(default_factory=dict)
    constraints: list[dict[str, Any]] = field(default_factory=list)
    renderer: str = "json"
    priority: int = 100


BUILTIN_GENERATION_TEMPLATES: list[GenerationTemplate] = [
    GenerationTemplate(
        id="contractor_access_policy",
        artifact_type="policy",
        required_fields=["role", "systems", "approver", "duration"],
        body={
            "title": "{role} Access Policy",
            "sections": [
                "Access to {systems} requires approval from {approver}.",
                "Access expires after {duration}.",
            ],
        },
        constraints=[
            {"kind": "field_present", "target": "role"},
            {"kind": "field_present", "target": "systems"},
            {"kind": "field_present", "target": "approver"},
            {"kind": "field_present", "target": "duration"},
            {"kind": "section_present", "target": "sections"},
        ],
        priority=10,
    ),
    GenerationTemplate(
        id="simple_plan_template",
        artifact_type="plan",
        required_fields=["title", "steps", "preconditions", "effects"],
        body={
            "title": "{title}",
            "steps": "{steps}",
            "preconditions": "{preconditions}",
            "effects": "{effects}",
        },
        constraints=[
            {"kind": "field_present", "target": "steps"},
            {"kind": "field_present", "target": "preconditions"},
            {"kind": "field_present", "target": "effects"},
        ],
        priority=20,
    ),
    GenerationTemplate(
        id="simple_config_template",
        artifact_type="config",
        required_fields=["name", "enabled", "threshold"],
        body={
            "name": "{name}",
            "enabled": "{enabled}",
            "threshold": "{threshold}",
        },
        constraints=[
            {"kind": "field_present", "target": "name"},
            {"kind": "field_present", "target": "enabled"},
            {"kind": "field_present", "target": "threshold"},
        ],
        priority=30,
    ),
    GenerationTemplate(
        id="simple_python_function_template",
        artifact_type="simple_code",
        required_fields=["function_name", "args", "body"],
        optional_fields=["tests"],
        body={
            "language": "python",
            "code": "def {function_name}({args}):\n    {body}",
            "tests": "{tests}",
        },
        constraints=[
            {"kind": "field_present", "target": "function_name"},
            {"kind": "field_present", "target": "args"},
            {"kind": "field_present", "target": "body"},
        ],
        priority=40,
    ),
]


def templates_from_bundle(bundle: CapabilityBundle | None) -> list[GenerationTemplate]:
    if bundle is None:
        return []
    templates: list[GenerationTemplate] = []
    for item in sorted(bundle.generation_templates, key=lambda x: (x.priority, x.id)):
        templates.append(
            GenerationTemplate(
                id=item.id,
                artifact_type=item.artifact_type,
                required_fields=list(item.required_fields),
                optional_fields=list(item.optional_fields),
                body=dict(item.body),
                constraints=[dict(c) for c in item.constraints],
                priority=item.priority,
            )
        )
    return templates


def render_template_body(body: Any, fields: dict[str, Any]) -> Any:
    if isinstance(body, dict):
        return {key: render_template_body(value, fields) for key, value in body.items()}
    if isinstance(body, list):
        return [render_template_body(item, fields) for item in body]
    if isinstance(body, str):
        return _render_string(body, fields)
    return body


def template_placeholders(template: GenerationTemplate) -> set[str]:
    values = [json.dumps(template.body), json.dumps(template.constraints)]
    found: set[str] = set()
    for value in values:
        for match in PLACEHOLDER_RE.findall(value):
            found.add(match)
    return found


def _render_string(value: str, fields: dict[str, Any]) -> str:
    rendered = value
    for key, field_value in fields.items():
        rendered = rendered.replace("{" + key + "}", _field_to_text(field_value))
    return rendered


def _field_to_text(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value)
