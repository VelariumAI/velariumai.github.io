"""Deterministic ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vcse.ingestion.adapters import load_source_document
from vcse.ingestion.import_result import (
    CONTRADICTORY,
    IMPORTED,
    PARTIAL,
    REJECTED,
    UNSUPPORTED_FORMAT,
    VALIDATION_FAILED,
    ImportResult,
)
from vcse.ingestion.pack_export import export_capability_pack
from vcse.ingestion.source import SourceLoadError
from vcse.ingestion.templates import extract_frames, resolve_template
from vcse.ingestion.validation import validate_frames
from vcse.interaction.frames_applicator import FrameApplicator
from vcse.memory.world_state import WorldStateMemory
from vcse.verifier.stack import VerifierStack


class IngestionError(ValueError):
    def __init__(self, error_type: str, reason: str) -> None:
        super().__init__(f"{error_type}: {reason}")
        self.error_type = error_type
        self.reason = reason


@dataclass
class IngestionPipelineResult:
    import_result: ImportResult
    memory: WorldStateMemory
    source_id: str


def ingest_file(
    path: str | Path,
    memory: WorldStateMemory | None = None,
    template_name: str | None = None,
    auto: bool = False,
    dry_run: bool = False,
    output_memory_path: str | Path | None = None,
    export_pack_path: str | Path | None = None,
    dsl_bundle=None,
) -> IngestionPipelineResult:
    base_memory = memory or WorldStateMemory()
    try:
        source = load_source_document(path)
    except SourceLoadError as exc:
        status = UNSUPPORTED_FORMAT if exc.error_type == "UNSUPPORTED_FORMAT" else REJECTED
        return IngestionPipelineResult(
            import_result=ImportResult(
                status=status,
                source_id="unknown",
                errors=[f"{exc.error_type}: {exc.reason}"],
            ),
            memory=base_memory,
            source_id="unknown",
        )

    template = resolve_template(
        source,
        template_name=template_name,
        auto=auto,
        dsl_bundle=dsl_bundle,
    )
    if template is None:
        raise IngestionError(
            "MISSING_TEMPLATE",
            f"No template resolved (template={template_name!r}, auto={auto})",
        )

    frames, extraction_warnings = extract_frames(source, template)
    validation = validate_frames(frames, base_memory)
    if validation.errors:
        return IngestionPipelineResult(
            import_result=ImportResult(
                status=VALIDATION_FAILED,
                source_id=source.id,
                frames_extracted=len(frames),
                warnings=[*extraction_warnings, *validation.warnings],
                errors=validation.errors,
            ),
            memory=base_memory,
            source_id=source.id,
        )

    candidate_memory = base_memory.clone()
    if dsl_bundle is not None:
        from vcse.memory.relations import RelationSchema
        for schema in getattr(dsl_bundle, "relation_schemas", []):
            name = str(schema.get("name", "")).strip()
            if not name:
                continue
            if candidate_memory.get_relation_schema(name) is None:
                properties = set(schema.get("properties", []))
                candidate_memory.add_relation_schema(
                    RelationSchema(
                        name=name,
                        transitive="transitive" in properties,
                        symmetric="symmetric" in properties,
                        reflexive="reflexive" in properties,
                        functional="functional" in properties,
                    )
                )
    applicator = FrameApplicator()
    apply_result = applicator.apply(validation.valid_frames, candidate_memory)
    verifier = VerifierStack.default().evaluate(candidate_memory)
    contradictions = _collect_contradictions(candidate_memory)

    status = IMPORTED
    if contradictions:
        status = CONTRADICTORY if apply_result.created_elements > 0 else PARTIAL
    elif apply_result.errors:
        status = PARTIAL if apply_result.created_elements > 0 else REJECTED

    for created_id, frame in zip(apply_result.created_ids, validation.valid_frames):
        provenance = getattr(frame, "provenance", None)
        if provenance:
            candidate_memory.add_evidence(
                target_id=created_id,
                content=str(provenance),
                source="ingestion_provenance",
            )

    output_memory = base_memory if dry_run else candidate_memory
    if output_memory_path:
        output_memory.save_json(output_memory_path)
    if export_pack_path:
        export_capability_pack(
            export_pack_path,
            source_count=1,
            memory=output_memory,
            frames=validation.valid_frames,
        )

    return IngestionPipelineResult(
        import_result=ImportResult(
            status=status,
            source_id=source.id,
            frames_extracted=len(frames),
            transitions_applied=apply_result.transitions_applied,
            created_elements=apply_result.created_elements,
            warnings=[*extraction_warnings, *validation.warnings, *apply_result.warnings, *verifier.reasons],
            errors=apply_result.errors,
            contradictions_detected=contradictions,
        ),
        memory=output_memory,
        source_id=source.id,
    )


def _collect_contradictions(memory: WorldStateMemory) -> list[str]:
    seen: set[str] = set()
    reasons: list[str] = []
    for contradictions in memory.contradictions.values():
        for contradiction in contradictions:
            if contradiction.id in seen:
                continue
            seen.add(contradiction.id)
            reasons.append(contradiction.reason)
    return reasons
