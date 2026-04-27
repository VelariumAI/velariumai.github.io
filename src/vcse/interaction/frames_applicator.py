"""Frame applicator: convert semantic frames to WorldStateMemory transitions."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcse.memory.constraints import Constraint
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.interaction.frames import (
    ClaimFrame,
    GoalFrame,
    ConstraintFrame,
    DefinitionFrame,
    QuestionFrame,
    ClarificationFrame,
)


@dataclass
class ApplicationResult:
    """Result of applying frames to memory."""
    memory: WorldStateMemory
    transitions_applied: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    created_elements: int = 0


class FrameApplicator:
    """Convert semantic frames into WorldStateMemory transitions."""

    def apply(
        self, frames: list[object], memory: WorldStateMemory
    ) -> ApplicationResult:
        """Apply parsed frames to world state memory."""
        result = ApplicationResult(memory=memory)

        for frame in frames:
            if isinstance(frame, ClaimFrame):
                self._apply_claim(frame, result)
            elif isinstance(frame, GoalFrame):
                self._apply_goal(frame, result)
            elif isinstance(frame, ConstraintFrame):
                self._apply_constraint(frame, result)
            elif isinstance(frame, DefinitionFrame):
                self._apply_definition(frame, result)
            elif isinstance(frame, QuestionFrame):
                result.warnings.append(f"QuestionFrame not directly applied: {frame.target}")
            elif isinstance(frame, ClarificationFrame):
                result.warnings.append("ClarificationFrame should be handled separately")
            else:
                result.errors.append(f"Unknown frame type: {type(frame)}")

        return result

    def _apply_claim(self, frame: ClaimFrame, result: ApplicationResult) -> None:
        """Apply a ClaimFrame as a new claim in memory."""
        try:
            memory = result.memory
            # Ensure relation schema exists
            if memory.get_relation_schema(frame.relation) is None:
                memory.add_relation_schema(self._create_schema(frame.relation))
            # Add the claim
            memory.add_claim(
                frame.subject,
                frame.relation,
                frame.object or "",
                TruthStatus.ASSERTED,
            )
            result.transitions_applied.append(f"claim:{frame.subject}/{frame.relation}/{frame.object}")
            result.created_elements += 1
        except Exception as exc:
            result.errors.append(f"Failed to apply claim: {exc}")

    def _apply_goal(self, frame: GoalFrame, result: ApplicationResult) -> None:
        """Apply a GoalFrame as a goal in memory."""
        try:
            memory = result.memory
            # Ensure relation schema exists with transitive for is_a
            if memory.get_relation_schema(frame.relation) is None:
                from vcse.memory.relations import RelationSchema
                # Use transitive=True for is_a for proper inheritance reasoning
                transitive = (frame.relation == "is_a")
                memory.add_relation_schema(
                    RelationSchema(name=frame.relation, transitive=transitive)
                )
            memory.add_goal(
                frame.subject,
                frame.relation,
                frame.object or "",
            )
            result.transitions_applied.append(f"goal:{frame.subject}/{frame.relation}/{frame.object}")
            result.created_elements += 1
        except Exception as exc:
            result.errors.append(f"Failed to apply goal: {exc}")

    def _apply_constraint(self, frame: ConstraintFrame, result: ApplicationResult) -> None:
        """Apply a ConstraintFrame as a constraint in memory."""
        try:
            memory = result.memory
            memory.add_constraint(
                Constraint(
                    kind="numeric",
                    target=frame.target,
                    operator=frame.operator,
                    value=frame.value,
                )
            )
            result.transitions_applied.append(f"constraint:{frame.target}/{frame.operator}/{frame.value}")
            result.created_elements += 1
        except Exception as exc:
            result.errors.append(f"Failed to apply constraint: {exc}")

    def _apply_definition(self, frame: DefinitionFrame, result: ApplicationResult) -> None:
        """Apply a DefinitionFrame."""
        # For now, definitions are tracked as warnings
        result.warnings.append(f"Definition not directly applicable: {frame.term}")

    def _create_schema(self, relation: str) -> "RelationSchema":
        """Create a relation schema for unknown relations."""
        from vcse.memory.relations import RelationSchema
        return RelationSchema(name=relation, transitive=False)
