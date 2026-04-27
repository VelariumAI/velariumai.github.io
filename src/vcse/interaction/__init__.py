"""Interaction layer: human input normalization, parsing, and response."""

from vcse.interaction.errors import InteractionError, ParseError, ClarificationError
from vcse.interaction.frames import (
    ClaimFrame,
    ConstraintFrame,
    DefinitionFrame,
    FrameParseResult,
    GoalFrame,
    QuestionFrame,
    ClarificationFrame,
)
from vcse.interaction.normalizer import SemanticNormalizer, NormalizedInput
from vcse.interaction.parser import PatternParser
from vcse.interaction.frames_applicator import FrameApplicator, ApplicationResult
from vcse.interaction.clarification import ClarificationEngine, ClarificationRequest
from vcse.interaction.session import Session
from vcse.interaction.response_modes import ResponseMode, render_response

__all__ = [
    "InteractionError",
    "ParseError",
    "ClarificationError",
    "ClaimFrame",
    "ConstraintFrame",
    "DefinitionFrame",
    "FrameParseResult",
    "GoalFrame",
    "QuestionFrame",
    "ClarificationFrame",
    "SemanticNormalizer",
    "NormalizedInput",
    "PatternParser",
    "FrameApplicator",
    "ApplicationResult",
    "ClarificationEngine",
    "ClarificationRequest",
    "Session",
    "ResponseMode",
    "render_response",
]
