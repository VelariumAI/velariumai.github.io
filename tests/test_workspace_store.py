"""Tests for workspace storage layer."""

import json
import tempfile
from pathlib import Path

from vcse.workspace.store import WorkspaceStore
from vcse.workspace.errors import (
    WorkspaceNotFound,
    TaskNotFound,
    SerializationError,
)


def test_create_and_load_workspace():
    with tempfile.TemporaryDirectory() as tmp:
        store = WorkspaceStore(root=tmp)
        ws_data = {"id": "ws-001", "name": "test", "owner": "alice", "created_at": "12345", "metadata": {}}
        store.create_workspace("ws-001", ws_data)
        loaded = store.load_workspace("ws-001")
        assert loaded["id"] == "ws-001"
        assert loaded["name"] == "test"


def test_workspace_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        store = WorkspaceStore(root=tmp)
        try:
            store.load_workspace("nonexistent")
            assert False, "should raise"
        except WorkspaceNotFound:
            pass


def test_workspace_exists():
    with tempfile.TemporaryDirectory() as tmp:
        store = WorkspaceStore(root=tmp)
        assert store.workspace_exists("ws-001") is False
        store.create_workspace("ws-001", {"id": "ws-001", "name": "test", "owner": "alice", "created_at": "12345", "metadata": {}})
        assert store.workspace_exists("ws-001") is True


def test_list_workspaces():
    with tempfile.TemporaryDirectory() as tmp:
        store = WorkspaceStore(root=tmp)
        store.create_workspace("ws-001", {"id": "ws-001", "name": "a", "owner": "x", "created_at": "1", "metadata": {}})
        store.create_workspace("ws-002", {"id": "ws-002", "name": "b", "owner": "y", "created_at": "2", "metadata": {}})
        workspaces = store.list_workspaces()
        assert len(workspaces) == 2


def test_delete_workspace():
    with tempfile.TemporaryDirectory() as tmp:
        store = WorkspaceStore(root=tmp)
        store.create_workspace("ws-001", {"id": "ws-001", "name": "test", "owner": "alice", "created_at": "12345", "metadata": {}})
        store.delete_workspace("ws-001")
        assert store.workspace_exists("ws-001") is False


def test_save_and_load_task():
    with tempfile.TemporaryDirectory() as tmp:
        store = WorkspaceStore(root=tmp)
        store.create_workspace("ws-001", {"id": "ws-001", "name": "test", "owner": "alice", "created_at": "12345", "metadata": {}})
        task_data = {"task_id": "t1", "workspace_id": "ws-001", "plan": {}, "state": {}, "created_at": "1", "updated_at": "2"}
        store.save_task("ws-001", "t1", task_data)
        loaded = store.load_task("ws-001", "t1")
        assert loaded["task_id"] == "t1"


def test_load_task_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        store = WorkspaceStore(root=tmp)
        store.create_workspace("ws-001", {"id": "ws-001", "name": "test", "owner": "alice", "created_at": "12345", "metadata": {}})
        try:
            store.load_task("ws-001", "nonexistent")
            assert False, "should raise"
        except TaskNotFound:
            pass


def test_list_tasks():
    with tempfile.TemporaryDirectory() as tmp:
        store = WorkspaceStore(root=tmp)
        store.create_workspace("ws-001", {"id": "ws-001", "name": "test", "owner": "alice", "created_at": "12345", "metadata": {}})
        store.save_task("ws-001", "t1", {"task_id": "t1", "workspace_id": "ws-001", "plan": {}, "state": {}, "created_at": "1", "updated_at": "2"})
        store.save_task("ws-001", "t2", {"task_id": "t2", "workspace_id": "ws-001", "plan": {}, "state": {}, "created_at": "1", "updated_at": "2"})
        tasks = store.list_tasks("ws-001")
        assert len(tasks) == 2


def test_append_and_read_ledger_events():
    with tempfile.TemporaryDirectory() as tmp:
        store = WorkspaceStore(root=tmp)
        store.create_workspace("ws-001", {"id": "ws-001", "name": "test", "owner": "alice", "created_at": "12345", "metadata": {}})
        store.append_ledger_event("ws-001", {"event": "TEST_EVENT", "workspace_id": "ws-001"})
        store.append_ledger_event("ws-001", {"event": "ANOTHER_EVENT", "workspace_id": "ws-001"})
        events = store.read_ledger_events("ws-001")
        assert len(events) == 2
        assert events[0]["event"] == "TEST_EVENT"