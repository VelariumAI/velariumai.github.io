"""Deterministic knowledge extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from vcse.ingestion.adapters import load_source_document
from vcse.ingestion.source import SourceLoadError
from vcse.ingestion.templates import extract_frames, resolve_template
from vcse.interaction.frames import ClaimFrame
from vcse.knowledge.errors import KnowledgeError
from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgeProvenance
from vcse.knowledge.sources import Source


@dataclass
class ExtractionResult:
    claims: list[KnowledgeClaim] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class KnowledgeExtractor:
    def extract(self, source: Source) -> ExtractionResult:
        if source.type == "api":
            raise KnowledgeError("UNSUPPORTED_SOURCE", "network-backed sources are not enabled")
        try:
            document = load_source_document(Path(source.path))
        except SourceLoadError as exc:
            raise KnowledgeError(exc.error_type, exc.reason) from exc

        claims: list[KnowledgeClaim] = []
        warnings: list[str] = []
        if document.source_type == "text":
            claims.extend(_extract_special_text_claims(source, str(document.content or "")))

        template = resolve_template(document, template_name=source.schema_hint, auto=True)
        if template is not None:
            frames, extraction_warnings = extract_frames(document, template)
            warnings.extend(extraction_warnings)
            claims.extend(_claims_from_frames(source, frames))
            if document.source_type in {"json", "jsonl", "yaml"}:
                claims.extend(_claims_from_raw_structured(source, document.content))
        return ExtractionResult(claims=_dedupe_preserve_order(claims), warnings=warnings)


def _extract_special_text_claims(source: Source, text: str) -> list[KnowledgeClaim]:
    claims: list[KnowledgeClaim] = []
    statements = [item.strip() for item in re.split(r"[.\n]+", text) if item.strip()]
    for index, statement in enumerate(statements, start=1):
        match = re.match(r"^(.+?)\s+is\s+the\s+capital\s+of\s+(.+)$", statement, re.IGNORECASE)
        if not match:
            continue
        subject = match.group(1).strip()
        country = "_".join(token.capitalize() for token in match.group(2).strip().split())
        claims.append(
            KnowledgeClaim(
                subject=subject,
                relation="is_a",
                object=f"capital_of_{country}",
                provenance=KnowledgeProvenance(
                    source_id=source.id,
                    source_type=source.type,
                    location=f"statement:{index}",
                    evidence_text=statement,
                    trust_level=source.trust_level,
                ),
            )
        )
    return claims


def _claims_from_frames(source: Source, frames: list[object]) -> list[KnowledgeClaim]:
    claims: list[KnowledgeClaim] = []
    for frame in frames:
        if not isinstance(frame, ClaimFrame):
            continue
        provenance = getattr(frame, "provenance", None) or {}
        claims.append(
            KnowledgeClaim(
                subject=str(frame.subject),
                relation=str(frame.relation),
                object=str(frame.object),
                provenance=KnowledgeProvenance(
                    source_id=str(provenance.get("source_id", source.id)),
                    source_type=str(provenance.get("source_type", source.type)),
                    location=str(provenance.get("location", "unknown")),
                    evidence_text=str(provenance.get("evidence_text", frame.source_text)),
                    trust_level=source.trust_level,
                    confidence=float(provenance.get("confidence", getattr(frame, "confidence", 0.9))),
                ),
                qualifiers={str(k): str(v) for k, v in getattr(frame, "qualifiers", {}).items()}
                if isinstance(getattr(frame, "qualifiers", {}), dict)
                else {},
                confidence=float(getattr(frame, "confidence", 0.9)),
            )
        )
    return claims


def _claims_from_raw_structured(source: Source, content: object) -> list[KnowledgeClaim]:
    if isinstance(content, list):
        rows = [row for row in content if isinstance(row, dict)]
    elif isinstance(content, dict):
        rows = content.get("facts", []) if isinstance(content.get("facts"), list) else [content]
        rows = [row for row in rows if isinstance(row, dict)]
    else:
        return []

    claims: list[KnowledgeClaim] = []
    for index, row in enumerate(rows, start=1):
        subject = str(row.get("subject", "")).strip()
        relation = str(row.get("relation", "is_a")).strip()
        obj = str(row.get("object", "")).strip()
        if subject and relation and obj:
            continue
        claims.append(
            KnowledgeClaim(
                subject=subject,
                relation=relation,
                object=obj,
                provenance=KnowledgeProvenance(
                    source_id=source.id,
                    source_type=source.type,
                    location=f"record:{index}",
                    evidence_text=str(row),
                    trust_level=source.trust_level,
                ),
            )
        )
    return claims


def _dedupe_preserve_order(claims: list[KnowledgeClaim]) -> list[KnowledgeClaim]:
    seen: set[str] = set()
    output: list[KnowledgeClaim] = []
    for claim in claims:
        fingerprint = f"{claim.key}|{claim.provenance.location}|{claim.provenance.evidence_text}"
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        output.append(claim)
    return output
