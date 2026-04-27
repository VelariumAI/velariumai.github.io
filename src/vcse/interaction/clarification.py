"""Clarification engine: generate helpful questions instead of guessing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vcse.interaction.frames import FrameParseResult, FrameStatus, ClarificationFrame
from vcse.memory.world_state import WorldStateMemory


@dataclass
class ClarificationRequest:
    """Request for user clarification."""
    reason: str
    user_message: str
    missing_fields: list[str] = field(default_factory=list)
    candidate_options: list[str] = field(default_factory=list)
    machine_code: str = ""


class ClarificationEngine:
    """Generate deterministic clarification requests instead of guessing."""

    def clarify(
        self,
        parse_result: FrameParseResult,
        memory: WorldStateMemory,
        goal: Any = None,
    ) -> ClarificationRequest | None:
        """Generate clarification request if needed, else None."""
        # Check for unknown relation
        if self._has_unknown_relation(parse_result, memory):
            return ClarificationRequest(
                reason="unknown_relation",
                user_message="I need the eligibility criteria before I can verify that.",
                missing_fields=["eligibility_rule"],
                machine_code="NEEDS_CLARIFICATION",
            )

        # Check for ambiguous target
        if self._is_ambiguous(parse_result):
            return ClarificationRequest(
                reason="ambiguous_target",
                user_message="What does 'it' refer to?",
                missing_fields=["target"],
                machine_code="AMBIGUOUS_INPUT",
            )

        # Check for missing facts
        if self._needs_more_facts(parse_result, memory, goal):
            return ClarificationRequest(
                reason="missing_facts",
                user_message="I do not have enough facts to prove that. "
                           "Provide facts such as 'Socrates is a man' "
                           "or a rule like 'All men are mortal.'",
                missing_fields=["relevant_facts"],
                machine_code="INSUFFICIENT_FACTS",
            )

        # Check for unsupported syntax
        if parse_result.status == FrameStatus.UNSUPPORTED:
            return ClarificationRequest(
                reason="unsupported_syntax",
                user_message="I need a specific claim, rule, constraint, or goal.",
                missing_fields=["supported_pattern"],
                machine_code="UNSUPPORTED_QUERY",
            )

        return None

    def _has_unknown_relation(
        self, parse_result: FrameParseResult, memory: WorldStateMemory
    ) -> bool:
        """Check if parsed frames contain an unknown relation."""
        for frame in parse_result.frames:
            if hasattr(frame, "relation"):
                relation = frame.relation
                if relation not in {"is_a", "equals", "part_of", ">", "<", ">=", "<=", "="}:
                    # Check if memory knows this relation
                    if memory.get_relation_schema(relation) is None:
                        return True
        return False

    def _is_ambiguous(self, parse_result: FrameParseResult) -> bool:
        """Check if input is ambiguous."""
        text = ""
        for frame in parse_result.frames:
            if hasattr(frame, "source_text"):
                text += frame.source_text

        # Check for pronouns without antecedents
        ambiguous_pronouns = {"it", "he", "she", "they", "this", "that"}
        tokens = text.lower().split()
        for token in tokens:
            if token.strip("?.,!") in ambiguous_pronouns:
                return True
        return False

    def _needs_more_facts(
        self,
        parse_result: FrameParseResult,
        memory: WorldStateMemory,
        goal: Any,
    ) -> bool:
        """Check if more facts are needed to proceed."""
        # If there's a goal but no claims to support it
        if goal is not None:
            has_claims = any(
                hasattr(f, "relation") and f.relation == "is_a"
                for f in parse_result.frames
            )
            if not has_claims and not memory.claims:
                return True
        return False
