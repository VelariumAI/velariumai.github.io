"""Session management for multi-turn reasoning."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from vcse.interaction.clarification import ClarificationRequest
from vcse.interaction.frames import FrameParseResult, FrameStatus
from vcse.interaction.normalizer import NormalizedInput
from vcse.memory.world_state import WorldStateMemory
from vcse.search.result import SearchResult


@dataclass
class TurnRecord:
    """A single turn in the conversation."""
    timestamp: str
    user_input: str
    normalized: NormalizedInput | None = None
    frames: FrameParseResult | None = None
    transitions_applied: list[str] = field(default_factory=list)
    result_status: str | None = None
    search_result: SearchResult | None = None


@dataclass
class Session:
    """In-memory session for multi-turn reasoning."""
    id: str
    memory: WorldStateMemory
    history: list[TurnRecord] = field(default_factory=list)
    current_goal: Any = None
    mode: str = "explain"
    dsl_bundle: Any = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @classmethod
    def create(cls, dsl_bundle: Any = None) -> "Session":
        """Create a new session."""
        return cls(
            id=str(uuid.uuid4())[:8],
            memory=WorldStateMemory(),
            dsl_bundle=dsl_bundle,
        )

    def ingest(self, text: str) -> FrameParseResult:
        """Ingest user input, normalize and parse."""
        from vcse.interaction.normalizer import SemanticNormalizer
        from vcse.interaction.parser import PatternParser
        from vcse.interaction.frames import GoalFrame, ClaimFrame
        import re

        external_synonyms = []
        external_patterns = []
        if self.dsl_bundle is not None:
            external_synonyms = [
                (rule.pattern, rule.replacement)
                for rule in getattr(self.dsl_bundle, "synonyms", [])
            ]
            external_patterns = list(getattr(self.dsl_bundle, "parser_patterns", []))

        normalizer = SemanticNormalizer(external_synonyms=external_synonyms)
        parser = PatternParser(external_patterns=external_patterns)

        normalized = normalizer.normalize(text)
        frames = parser.parse(normalized.normalized_text)

        # Handle direct "can X die" pattern before normalization.
        can_match = re.match(r"^\s*can\s+(.+?)\s+die\s*\??\s*$", text, re.IGNORECASE)
        if can_match:
            subject = can_match.group(1).strip().rstrip("?")
            frames = FrameParseResult()
            frames.status = FrameStatus.PARSED
            frames.confidence = 0.9
            frames.frames = [GoalFrame(
                subject=subject,
                relation="is_a",
                object="mortal",
                source_text=text,
            )]
        elif normalized.is_question and frames.frames:
            has_goal = any(isinstance(frame, GoalFrame) for frame in frames.frames)
            if has_goal:
                pass
            else:
                # If question and parser returned only claims, convert the last is_a claim to a goal.
                for index in range(len(frames.frames) - 1, -1, -1):
                    frame = frames.frames[index]
                    if isinstance(frame, ClaimFrame) and frame.relation == "is_a":
                        frames.frames[index] = GoalFrame(
                            subject=frame.subject,
                            relation=frame.relation,
                            object=frame.object,
                            source_text=frame.source_text,
                        )
                        break

        # Record the turn
        turn = TurnRecord(
            timestamp=datetime.utcnow().isoformat(),
            user_input=text,
            normalized=normalized,
            frames=frames,
        )
        self.history.append(turn)

        return frames

    def solve(
        self,
        enable_ts3: bool = False,
        search_backend: str = "beam",
    ) -> SearchResult | ClarificationRequest | None:
        """Run search on current memory state."""
        from vcse.engine import build_search
        from vcse.interaction.frames_applicator import FrameApplicator
        from vcse.interaction.clarification import ClarificationEngine
        from vcse.memory.relations import RelationSchema

        if self.dsl_bundle is not None:
            for schema in getattr(self.dsl_bundle, "relation_schemas", []):
                name = str(schema.get("name", "")).strip()
                if not name:
                    continue
                properties = set(schema.get("properties", []))
                existing = self.memory.get_relation_schema(name)
                if existing is None:
                    self.memory.add_relation_schema(
                        RelationSchema(
                            name=name,
                            transitive="transitive" in properties,
                            symmetric="symmetric" in properties,
                            reflexive="reflexive" in properties,
                            functional="functional" in properties,
                        )
                    )

        # Apply frames from history
        applicator = FrameApplicator()
        for turn in self.history:
            if turn.frames and turn.frames.frames:
                result = applicator.apply(turn.frames.frames, self.memory)
                turn.transitions_applied = result.transitions_applied

        # Check for clarification need
        clarification = ClarificationEngine(
            external_rules=getattr(self.dsl_bundle, "clarification_rules", None)
        ).clarify(
            self.history[-1].frames if self.history else None,
            self.memory,
            self.current_goal,
        )
        if clarification:
            return clarification

        # Run search if there's a goal
        if self.memory.goals:
            search = build_search(
                enable_ts3=enable_ts3,
                search_backend=search_backend,
                dsl_bundle=self.dsl_bundle,
            )
            result = search.run(self.memory)
            if self.history:
                self.history[-1].search_result = result
                self.history[-1].result_status = result.evaluation.status.value
            return result

        return None

    def explain(self) -> str:
        """Return explanation of last result."""
        if not self.history:
            return "No reasoning history yet."

        last = self.history[-1]
        if last.search_result:
            from vcse.renderer.explanation import ExplanationRenderer
            return ExplanationRenderer().render(last.search_result, last.search_result.state)
        elif last.result_status:
            return f"status: {last.result_status}"
        return "No result to explain."

    def reset(self) -> None:
        """Reset session memory and history."""
        self.memory = WorldStateMemory()
        self.history = []
        self.current_goal = None

    def fork(self) -> "Session":
        """Create an in-memory copy of this session."""
        new_session = Session(
            id=str(uuid.uuid4())[:8],
            memory=self.memory,  # Shallow copy - same memory reference
            history=list(self.history),  # Copy history
            mode=self.mode,
        )
        return new_session

    def summary(self) -> str:
        """Return a summary of the session."""
        lines = [
            f"Session {self.id}",
            f"Created: {self.created_at}",
            f"Turns: {len(self.history)}",
            f"Mode: {self.mode}",
            f"Memory: {len(self.memory.claims)} claims, {len(self.memory.constraints)} constraints",
        ]
        if self.memory.goals:
            lines.append(f"Goals: {len(self.memory.goals)}")
        return "\n".join(lines)
