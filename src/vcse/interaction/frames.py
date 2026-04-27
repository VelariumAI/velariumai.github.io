"""Semantic frames: typed structured representations of extracted meaning."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FrameStatus(Enum):
    """Status of frame parsing."""
    PARSED = "PARSED"
    PARTIAL = "PARTIAL"
    AMBIGUOUS = "AMBIGUOUS"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"


@dataclass
class ClaimFrame:
    """A factual claim about the world."""
    subject: str
    relation: str
    object: str | None = None
    qualifiers: list[str] = field(default_factory=list)
    source_text: str = ""
    provenance: dict[str, object] | None = None
    confidence: float = 1.0


@dataclass
class GoalFrame:
    """A goal or question to be verified."""
    subject: str
    relation: str
    object: str | None = None
    constraints: list[str] = field(default_factory=list)
    success_criteria: str = ""
    source_text: str = ""
    provenance: dict[str, object] | None = None
    confidence: float = 1.0
    qualifiers: list[str] = field(default_factory=list)


@dataclass
class ConstraintFrame:
    """A constraint on a variable or entity."""
    target: str
    operator: str
    value: str | int | float
    source_text: str = ""
    provenance: dict[str, object] | None = None
    confidence: float = 1.0
    qualifiers: list[str] = field(default_factory=list)


@dataclass
class DefinitionFrame:
    """A definition of a term."""
    term: str
    definition: str
    source_text: str = ""
    provenance: dict[str, object] | None = None
    confidence: float = 1.0
    qualifiers: list[str] = field(default_factory=list)


@dataclass
class QuestionFrame:
    """A question to be answered."""
    question_type: str  # e.g., "is_a", "equals", "eligible"
    target: str
    source_text: str = ""


@dataclass
class ClarificationFrame:
    """A request for user clarification."""
    reason: str
    missing_fields: list[str] = field(default_factory=list)
    candidate_options: list[str] = field(default_factory=list)


@dataclass
class FrameParseResult:
    """Result of parsing text into frames."""
    frames: list[Any] = field(default_factory=list)
    status: FrameStatus = FrameStatus.FAILED
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def add_claim(self, subject: str, relation: str, obj: str | None = None) -> ClaimFrame:
        frame = ClaimFrame(subject=subject, relation=relation, object=obj, source_text="")
        self.frames.append(frame)
        return frame

    def add_goal(self, subject: str, relation: str, obj: str | None = None) -> GoalFrame:
        frame = GoalFrame(subject=subject, relation=relation, object=obj, source_text="")
        self.frames.append(frame)
        return frame

    def add_constraint(self, target: str, operator: str, value: str | int | float) -> ConstraintFrame:
        frame = ConstraintFrame(target=target, operator=operator, value=value, source_text="")
        self.frames.append(frame)
        return frame
