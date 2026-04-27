"""Ingestion pipeline and knowledge import."""

from vcse.ingestion.import_result import (
    CONTRADICTORY,
    IMPORTED,
    PARTIAL,
    REJECTED,
    UNSUPPORTED_FORMAT,
    VALIDATION_FAILED,
    ImportResult,
)
from vcse.ingestion.pipeline import IngestionError, IngestionPipelineResult, ingest_file
from vcse.ingestion.provenance import Provenance
from vcse.ingestion.source import SourceDocument, SourceLoadError
from vcse.ingestion.templates import BUILTIN_TEMPLATES, Template

__all__ = [
    "CONTRADICTORY",
    "IMPORTED",
    "PARTIAL",
    "REJECTED",
    "UNSUPPORTED_FORMAT",
    "VALIDATION_FAILED",
    "ImportResult",
    "IngestionError",
    "IngestionPipelineResult",
    "ingest_file",
    "Provenance",
    "SourceDocument",
    "SourceLoadError",
    "BUILTIN_TEMPLATES",
    "Template",
]
