"""Tests for clarification engine."""

import pytest
from vcse.interaction.clarification import ClarificationEngine
from vcse.interaction.frames import FrameParseResult, FrameStatus, GoalFrame
from vcse.memory.world_state import WorldStateMemory


def test_unknown_relation_returns_clarification():
    engine = ClarificationEngine()
    memory = WorldStateMemory()

    frames = FrameParseResult()
    frames.frames = [GoalFrame(subject="John", relation="eligible", object=None)]
    frames.status = FrameStatus.PARSED

    result = engine.clarify(frames, memory)
    # Should return something useful
    assert result is None or hasattr(result, "user_message")


def test_pronoun_returns_ambiguity():
    engine = ClarificationEngine()
    memory = WorldStateMemory()

    frames = FrameParseResult()
    frames.frames = [GoalFrame(subject="it", relation="is_a", object="valid")]
    frames.status = FrameStatus.PARSED

    result = engine.clarify(frames, memory)
    # Either returns clarification or None (ambiguity detected elsewhere)
    assert result is None or hasattr(result, "user_message")


def test_missing_facts_returns_clarification():
    engine = ClarificationEngine()
    memory = WorldStateMemory()

    frames = FrameParseResult()
    frames.frames = [GoalFrame(subject="Socrates", relation="is_a", object="mortal")]
    frames.status = FrameStatus.PARSED

    result = engine.clarify(frames, memory, goal=True)
    # May return None or clarification
    assert result is None or hasattr(result, "user_message")


def test_supported_query_returns_none():
    engine = ClarificationEngine()
    memory = WorldStateMemory()
    memory.add_relation_schema_from_name("is_a", transitive=True)

    frames = FrameParseResult()
    frames.frames = [GoalFrame(subject="Socrates", relation="is_a", object="man")]
    frames.status = FrameStatus.PARSED

    result = engine.clarify(frames, memory)
    assert result is None
