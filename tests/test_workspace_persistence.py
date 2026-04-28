"""Tests for workspace task persistence and resume."""

import tempfile

from vcse.workspace.manager import WorkspaceManager
from vcse.workspace.store import WorkspaceStore


def test_task_persistence_after_save():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = WorkspaceManager(store=WorkspaceStore(root=tmp))
        ws = mgr.create_workspace(name="test", owner="alice")
        mgr.save_task(ws.id, "task-001", {"task_id": "task-001", "steps": [{"id": "s1"}]}, {"task_id": "task-001", "current_step": 1})
        loaded = mgr.load_task(ws.id, "task-001")
        assert loaded.task_id == "task-001"
        assert loaded.plan["task_id"] == "task-001"
        assert loaded.state["current_step"] == 1


def test_task_exists():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = WorkspaceManager(store=WorkspaceStore(root=tmp))
        ws = mgr.create_workspace(name="test", owner="alice")
        assert mgr.task_exists(ws.id, "task-001") is False
        mgr.save_task(ws.id, "task-001", {"task_id": "task-001", "steps": []}, {"task_id": "task_id", "current_step": 0})
        assert mgr.task_exists(ws.id, "task-001") is True


def test_resume_task():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = WorkspaceManager(store=WorkspaceStore(root=tmp))
        ws = mgr.create_workspace(name="test", owner="alice")
        plan = {"task_id": "task-001", "steps": [{"id": "s1", "status": "COMPLETED"}, {"id": "s2", "status": "PENDING"}]}
        state = {"task_id": "task-001", "current_step": 1, "completed_steps": ["s1"], "status": "RUNNING"}
        mgr.save_task(ws.id, "task-001", plan, state)
        loaded = mgr.load_task(ws.id, "task-001")
        assert loaded.state["current_step"] == 1
        assert "s1" in loaded.state["completed_steps"]


def test_session_create_and_list():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = WorkspaceManager(store=WorkspaceStore(root=tmp))
        ws = mgr.create_workspace(name="test", owner="alice")
        sess = mgr.create_session(ws.id)
        assert sess.workspace_id == ws.id

        sessions = mgr.list_sessions(ws.id)
        assert len(sessions) == 1
        assert sessions[0].id == sess.id