"""Tests for session management."""

import pytest
from vcse.interaction.session import Session


def test_session_create():
    session = Session.create()
    assert session.id is not None
    assert len(session.memory.claims) == 0
    assert len(session.history) == 0


def test_session_ingest():
    session = Session.create()
    frames = session.ingest("Socrates is a man")
    assert len(session.history) == 1
    assert frames is not None


def test_session_reset():
    session = Session.create()
    session.ingest("Socrates is a man")
    session.reset()
    assert len(session.history) == 0
    assert len(session.memory.claims) == 0


def test_session_fork():
    session = Session.create()
    session.ingest("Socrates is a man")
    forked = session.fork()
    assert forked.id != session.id
    assert len(forked.history) == len(session.history)


def test_session_summary():
    session = Session.create()
    summary = session.summary()
    assert "Session" in summary
    assert "Turns" in summary


def test_session_explain_no_result():
    session = Session.create()
    explain = session.explain()
    assert "No reasoning history" in explain
