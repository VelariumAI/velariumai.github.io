"""Knowledge compiler models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompilerMapping:
    domain_id: str
    source_id: str
    entity_field: str
    fields: dict[str, str]
    relation_map: dict[str, str]


@dataclass(frozen=True)
class CompileReport:
    status: str
    domain_id: str
    source_id: str
    pack_id: str
    input_record_count: int
    claim_count: int
    duplicate_count: int
    provenance_count: int
    benchmark_count: int
    output_path: str
    reasons: list[str]


COMPILE_PASSED = "COMPILE_PASSED"
COMPILE_FAILED = "COMPILE_FAILED"
