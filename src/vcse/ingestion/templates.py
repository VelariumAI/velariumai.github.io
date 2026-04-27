"""Deterministic ingestion templates and extractors."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from vcse.ingestion.provenance import Provenance
from vcse.ingestion.source import SourceDocument
from vcse.interaction.frames import ClaimFrame, ConstraintFrame, DefinitionFrame, GoalFrame


@dataclass(frozen=True)
class Template:
    name: str
    input_type: str
    patterns: list[str] = field(default_factory=list)
    output_frame_type: str = "ClaimFrame"
    relation: str = "is_a"
    field_mappings: dict[str, str] = field(default_factory=dict)
    qualifiers: list[str] = field(default_factory=list)
    confidence: float = 0.9
    columns: dict[str, str] = field(default_factory=dict)


BUILTIN_TEMPLATES: dict[str, Template] = {
    "text_policy": Template(
        name="text_policy",
        input_type="text",
        patterns=[
            "{subject} are {object}",
            "{subject} is {object}",
            "{subject} must be {requirement}",
            "{subject} requires {requirement}",
            "{subject} equals {value}",
        ],
    ),
    "csv_triples": Template(
        name="csv_triples",
        input_type="csv",
        columns={"subject": "subject", "relation": "relation", "object": "object"},
    ),
    "csv_entity_relation_value": Template(
        name="csv_entity_relation_value",
        input_type="csv",
        columns={"subject": "entity", "relation": "relation", "object": "value"},
    ),
    "json_claims": Template(name="json_claims", input_type="json"),
    "jsonl_claims": Template(name="jsonl_claims", input_type="jsonl"),
    "yaml_claims": Template(name="yaml_claims", input_type="yaml"),
}


def resolve_template(
    source: SourceDocument,
    template_name: str | None,
    auto: bool,
) -> Template | None:
    if template_name:
        return BUILTIN_TEMPLATES.get(template_name)
    if not auto:
        return None
    if source.source_type == "text":
        return BUILTIN_TEMPLATES["text_policy"]
    if source.source_type == "json":
        return BUILTIN_TEMPLATES["json_claims"]
    if source.source_type == "jsonl":
        return BUILTIN_TEMPLATES["jsonl_claims"]
    if source.source_type == "yaml":
        return BUILTIN_TEMPLATES["yaml_claims"]
    if source.source_type == "csv":
        rows = source.content if isinstance(source.content, list) else []
        if rows and isinstance(rows[0], dict):
            keys = {str(k).strip().lower() for k in rows[0].keys()}
            if {"subject", "relation", "object"}.issubset(keys):
                return BUILTIN_TEMPLATES["csv_triples"]
            if {"entity", "relation", "value"}.issubset(keys):
                return BUILTIN_TEMPLATES["csv_entity_relation_value"]
        return BUILTIN_TEMPLATES["csv_triples"]
    return None


def extract_frames(
    source: SourceDocument,
    template: Template,
) -> tuple[list[object], list[str]]:
    warnings: list[str] = []
    if template.input_type != source.source_type:
        warnings.append(
            f"Template {template.name} expects {template.input_type}, got {source.source_type}"
        )
    if source.source_type == "text":
        return _extract_text(source, template, warnings), warnings
    if source.source_type == "csv":
        return _extract_csv(source, template, warnings), warnings
    if source.source_type in {"json", "jsonl", "yaml"}:
        return _extract_structured(source, template, warnings), warnings
    warnings.append(f"No extractor for source type: {source.source_type}")
    return [], warnings


def _extract_text(source: SourceDocument, template: Template, warnings: list[str]) -> list[object]:
    text = str(source.content or "")
    statements = [item.strip() for item in re.split(r"[.\n]+", text) if item.strip()]
    frames: list[object] = []
    for index, statement in enumerate(statements, start=1):
        provenance = Provenance(
            source_id=source.id,
            source_type=source.source_type,
            location=f"statement:{index}",
            evidence_text=statement,
            confidence=template.confidence,
        )
        lower = statement.lower()
        match = re.match(r"^(?:all\s+)?(.+?)\s+(?:are|is)\s+(.+)$", lower)
        if match and "must be" not in lower and "requires" not in lower and "equals" not in lower:
            subject = _singular(match.group(1))
            obj = _normalize_requirement(match.group(2), pascal_case=False)
            frames.append(
                ClaimFrame(
                    subject=subject,
                    relation="is_a",
                    object=obj,
                    source_text=statement,
                    provenance=provenance.to_dict(),
                    confidence=template.confidence,
                    qualifiers=list(template.qualifiers),
                )
            )
            continue
        match = re.match(r"^(.+?)\s+must be\s+(.+)$", lower)
        if match:
            frames.append(
                ClaimFrame(
                    subject=_singular(match.group(1)),
                    relation="requires",
                    object=_normalize_requirement(match.group(2), pascal_case=True),
                    source_text=statement,
                    provenance=provenance.to_dict(),
                    confidence=template.confidence,
                    qualifiers=list(template.qualifiers),
                )
            )
            continue
        match = re.match(r"^(.+?)\s+requires\s+(.+)$", lower)
        if match:
            frames.append(
                ClaimFrame(
                    subject=_singular(match.group(1)),
                    relation="requires",
                    object=_normalize_requirement(match.group(2), pascal_case=True),
                    source_text=statement,
                    provenance=provenance.to_dict(),
                    confidence=template.confidence,
                    qualifiers=list(template.qualifiers),
                )
            )
            continue
        match = re.match(r"^(.+?)\s+equals\s+(.+)$", lower)
        if match:
            frames.append(
                ClaimFrame(
                    subject=match.group(1).strip(),
                    relation="equals",
                    object=match.group(2).strip(),
                    source_text=statement,
                    provenance=provenance.to_dict(),
                    confidence=template.confidence,
                    qualifiers=list(template.qualifiers),
                )
            )
            continue
        warnings.append(f"No template match for text statement: {statement}")
    return frames


def _extract_csv(source: SourceDocument, template: Template, warnings: list[str]) -> list[object]:
    rows = source.content if isinstance(source.content, list) else []
    frames: list[object] = []
    subject_column = template.columns.get("subject", "subject")
    relation_column = template.columns.get("relation", "relation")
    object_column = template.columns.get("object", "object")
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            warnings.append(f"CSV row {index} is not an object")
            continue
        row_lc = {str(k).strip().lower(): v for k, v in row.items()}
        subject = _read_case_insensitive(row_lc, subject_column)
        relation = _read_case_insensitive(row_lc, relation_column)
        obj = _read_case_insensitive(row_lc, object_column)
        if subject is None or relation is None or obj is None:
            warnings.append(f"CSV row {index} missing mapped fields")
            continue
        provenance = Provenance(
            source_id=source.id,
            source_type=source.source_type,
            location=f"row:{index}",
            evidence_text=str(row),
            confidence=template.confidence,
        )
        frames.append(
            ClaimFrame(
                subject=str(subject).strip().lower(),
                relation=str(relation).strip().lower(),
                object=str(obj).strip().lower(),
                source_text=str(row),
                provenance=provenance.to_dict(),
                confidence=template.confidence,
                qualifiers=list(template.qualifiers),
            )
        )
    return frames


def _extract_structured(source: SourceDocument, template: Template, warnings: list[str]) -> list[object]:
    frames: list[object] = []
    rows: list[dict[str, Any]]
    if isinstance(source.content, list):
        rows = [row for row in source.content if isinstance(row, dict)]
    elif isinstance(source.content, dict):
        rows = source.content.get("facts", []) if isinstance(source.content.get("facts"), list) else [source.content]
    else:
        warnings.append("Structured source has unsupported shape")
        return frames

    for index, row in enumerate(rows, start=1):
        provenance = Provenance(
            source_id=source.id,
            source_type=source.source_type,
            location=f"record:{index}",
            evidence_text=str(row),
            confidence=template.confidence,
        )
        relation = str(row.get("relation", "is_a")).strip().lower()
        subject = str(row.get("subject", "")).strip().lower()
        obj = row.get("object")
        if not subject:
            warnings.append(f"Record {index} missing subject")
            continue
        if relation in {">", "<", ">=", "<=", "=", "equals"} and "target" in row:
            frames.append(
                ConstraintFrame(
                    target=str(row["target"]).strip().lower(),
                    operator=str(row["operator"]).strip(),
                    value=row["value"],
                    source_text=str(row),
                    provenance=provenance.to_dict(),
                    confidence=template.confidence,
                )
            )
            continue
        frame_type = str(row.get("frame_type", "claim")).lower()
        if frame_type == "goal":
            frames.append(
                GoalFrame(
                    subject=subject,
                    relation=relation,
                    object=str(obj or "").strip().lower(),
                    source_text=str(row),
                    provenance=provenance.to_dict(),
                    confidence=template.confidence,
                )
            )
            continue
        if frame_type == "definition":
            frames.append(
                DefinitionFrame(
                    term=subject,
                    definition=str(obj or "").strip(),
                    source_text=str(row),
                    provenance=provenance.to_dict(),
                    confidence=template.confidence,
                )
            )
            continue
        frames.append(
            ClaimFrame(
                subject=subject,
                relation=relation,
                object=str(obj or "").strip().lower(),
                source_text=str(row),
                provenance=provenance.to_dict(),
                confidence=template.confidence,
            )
        )
    return frames


def _read_case_insensitive(row_lc: dict[str, Any], key: str) -> Any | None:
    return row_lc.get(key.strip().lower())


def _singular(value: str) -> str:
    clean = value.strip().lower()
    if clean.endswith("ies"):
        return clean[:-3] + "y"
    if clean.endswith("s") and len(clean) > 1:
        return clean[:-1]
    return clean


def _normalize_requirement(value: str, pascal_case: bool) -> str:
    clean = re.sub(r"[^a-zA-Z0-9\s]+", " ", value).strip().lower()
    if not pascal_case:
        return clean
    tokens = [token for token in clean.split() if token]
    return "".join(token.capitalize() for token in tokens)
