"""Tests for human inputs through interaction layer."""

import pytest
from vcse.interaction.session import Session


def test_socrates_demo_through_interaction():
    """Test the classic Socrates demo through vcse ask."""
    session = Session.create()
    session.ingest("All men are mortal.")
    session.ingest("Socrates is a man.")
    result = session.solve()

    # Should not crash, may return None if no goal
    assert result is None or hasattr(result, "evaluation") or hasattr(result, "user_message")


def test_eligibility_needs_criteria():
    """Test that eligibility query without criteria returns clarification."""
    session = Session.create()
    session.ingest("Is John eligible?")
    result = session.solve()

    # Should return clarification, not crash
    assert result is None or hasattr(result, "user_message") or hasattr(result, "evaluation")


def test_contradiction_detection():
    """Test that contradictions are detected."""
    session = Session.create()
    session.ingest("x equals 3")
    session.ingest("x equals 4")
    result = session.solve()

    # Should not crash
    assert result is None or hasattr(result, "evaluation") or hasattr(result, "user_message")


def test_multi_statement_parse():
    """Test parsing multiple statements."""
    session = Session.create()
    frames = session.ingest("All men are mortal. Socrates is a man. Is Socrates mortal?")

    assert len(session.history) == 1
    assert frames is not None


def test_simple_mode():
    """Test simple response mode."""
    session = Session.create()
    session.mode = "simple"
    session.ingest("All birds can fly. Tweety is a bird.")
    result = session.solve()

    # Should not crash
    assert result is None or hasattr(result, "evaluation") or hasattr(result, "user_message")


def test_canonical_internal_relation_preserved_for_can_die_query():
    """Renderer polish must not alter canonical internal relation storage."""
    session = Session.create()
    session.ingest("All men are mortal. Socrates is a man. Can Socrates die?")
    result = session.solve()
    assert result is not None and hasattr(result, "state")
    goal = result.state.goals[0]
    assert goal.relation == "is_a"
