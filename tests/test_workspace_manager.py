"""Tests for workspace manager."""

import tempfile
from pathlib import Path

from vcse.workspace.manager import WorkspaceManager
from vcse.workspace.store import WorkspaceStore
from vcse.workspace.errors import (
    WorkspaceExists,
    WorkspaceNotFound,
    TaskNotFound,
)


def test_create_and_load_workspace():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = WorkspaceManager(store=WorkspaceStore(root=tmp))
        ws = mgr.create_workspace(name="test-ws", owner="alice")
        assert ws.name == "test-ws"
        assert ws.owner == "alice"

        loaded = mgr.load_workspace(ws.id)
        assert loaded.id == ws.id
        assert loaded.name == "test-ws"


def test_create_duplicate_raises():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = WorkspaceManager(store=WorkspaceStore(root=tmp))
        ws = mgr.create_workspace(name="test", owner="alice")
        try:
            mgr.create_workspace(name="test", owner="alice")
            assert False, "should raise"
        except WorkspaceExists:
            pass


def test_list_workspaces():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = WorkspaceManager(store=WorkspaceStore(root=tmp))
        ws1 = mgr.create_workspace(name="a", owner="x")
        ws2 = mgr.create_workspace(name="b", owner="y")
        workspaces = mgr.list_workspaces()
        assert len(workspaces) == 2


def test_delete_workspace():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = WorkspaceManager(store=WorkspaceStore(root=tmp))
        ws = mgr.create_workspace(name="test", owner="alice")
        mgr.delete_workspace(ws.id)
        assert mgr.list_workspaces() == []


def test_delete_nonexistent_raises():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = WorkspaceManager(store=WorkspaceStore(root=tmp))
        try:
            mgr.delete_workspace("nonexistent")
            assert False, "should raise"
        except WorkspaceNotFound:
            pass


def test_save_and_load_task():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = WorkspaceManager(store=WorkspaceStore(root=tmp))
        ws = mgr.create_workspace(name="test", owner="alice")
        mgr.save_task(ws.id, "task-001", {"task_id": "task-001", "steps": []}, {"task_id": "task-001", "current_step": 0})
        task = mgr.load_task(ws.id, "task-001")
        assert task.task_id == "task-001"
        assert task.workspace_id == ws.id


def test_load_task_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = WorkspaceManager(store=WorkspaceStore(root=tmp))
        ws = mgr.create_workspace(name="test", owner="alice")
        try:
            mgr.load_task(ws.id, "nonexistent")
            assert False, "should raise"
        except TaskNotFound:
            pass


def test_list_tasks():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = WorkspaceManager(store=WorkspaceStore(root=tmp))
        ws = mgr.create_workspace(name="test", owner="alice")
        mgr.save_task(ws.id, "t1", {"task_id": "t1", "steps": []}, {"task_id": "t1", "current_step": 0})
        mgr.save_task(ws.id, "t2", {"task_id": "t2", "steps": []}, {"task_id": "t2", "current_step": 0})
        tasks = mgr.list_tasks(ws.id)
        assert len(tasks) == 2


def test_export_and_import_workspace():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = WorkspaceManager(store=WorkspaceStore(root=tmp))
        ws = mgr.create_workspace(name="test", owner="alice")
        mgr.save_task(ws.id, "t1", {"task_id": "t1", "steps": ["step1"]}, {"task_id": "t1", "current_step": 1})

        export_path = Path(tmp) / "export.json"
        mgr.export_workspace(ws.id, str(export_path))

        ws2 = mgr.import_workspace(str(export_path), force=True)
        assert ws2.id == ws.id

        tasks = mgr.list_tasks(ws.id)
        assert len(tasks) == 1
        assert tasks[0].task_id == "t1"


def test_import_overwrite_with_force():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = WorkspaceManager(store=WorkspaceStore(root=tmp))
        ws1 = mgr.create_workspace(name="test", owner="alice")
        export_path = Path(tmp) / "export.json"
        mgr.export_workspace(ws1.id, str(export_path))

        try:
            mgr.import_workspace(str(export_path))
            assert False, "should raise"
        except Exception:
            pass

        ws2 = mgr.import_workspace(str(export_path), force=True)
        assert ws2.id == ws1.id