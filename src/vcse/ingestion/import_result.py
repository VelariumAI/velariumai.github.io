"""Import result models."""

from __future__ import annotations

from dataclasses import dataclass, field


IMPORTED = "IMPORTED"
PARTIAL = "PARTIAL"
REJECTED = "REJECTED"
CONTRADICTORY = "CONTRADICTORY"
UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
VALIDATION_FAILED = "VALIDATION_FAILED"


@dataclass
class ImportResult:
    status: str
    source_id: str
    frames_extracted: int = 0
    transitions_applied: list[str] = field(default_factory=list)
    created_elements: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    contradictions_detected: list[str] = field(default_factory=list)
