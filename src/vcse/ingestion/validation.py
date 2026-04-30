"""Frame validation for ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcse.interaction.frames import ClaimFrame, ConstraintFrame, DefinitionFrame, GoalFrame
from vcse.memory.world_state import WorldStateMemory


@dataclass
class ValidationResult:
    valid_frames: list[object] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def validate_frames(frames: list[object], memory: WorldStateMemory) -> ValidationResult:
    result = ValidationResult()
    for index, frame in enumerate(frames, start=1):
        if isinstance(frame, ClaimFrame):
            if not frame.subject or not frame.relation or frame.object is None:
                result.errors.append(f"ClaimFrame {index} missing subject/relation/object")
                continue
            if memory.get_relation_schema(frame.relation) is None:
                result.warnings.append(f"Unknown relation schema: {frame.relation}")
            result.valid_frames.append(frame)
            continue
        if isinstance(frame, GoalFrame):
            if not frame.subject or not frame.relation or frame.object is None:
                result.errors.append(f"GoalFrame {index} missing subject/relation/object")
                continue
            if memory.get_relation_schema(frame.relation) is None:
                result.warnings.append(f"Unknown relation schema: {frame.relation}")
            result.valid_frames.append(frame)
            continue
        if isinstance(frame, ConstraintFrame):
            if not frame.target or not frame.operator:
                result.errors.append(f"ConstraintFrame {index} missing target/operator")
                continue
            result.valid_frames.append(frame)
            continue
        if isinstance(frame, DefinitionFrame):
            if not frame.term or not frame.definition:
                result.errors.append(f"DefinitionFrame {index} missing term/definition")
                continue
            result.valid_frames.append(frame)
            continue
        result.errors.append(f"Unsupported frame type at {index}: {type(frame).__name__}")
    return result
