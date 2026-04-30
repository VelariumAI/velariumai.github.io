"""Tests for workspace models."""

from vcse.workspace.models import Workspace, Session, PersistedTask, WorkspaceState
from vcse.workspace.errors import ValidationError


def test_workspace_create_valid():
    ws = Workspace.create(name="test-workspace", owner="alice")
    assert ws.name == "test-workspace"
    assert ws.owner == "alice"
    assert ws.id  # UUID5 format, not "workspace:" prefix
    assert ws.created_at
    assert ws.metadata == {}


def test_workspace_create_with_id():
    ws = Workspace.create(name="test", owner="bob", workspace_id="custom-id-123")
    assert ws.id == "custom-id-123"


def test_workspace_create_empty_name():
    try:
        Workspace.create(name="   ", owner="alice")
        assert False, "should raise"
    except ValidationError:
        pass


def test_workspace_create_empty_owner():
    try:
        Workspace.create(name="test", owner="")
        assert False, "should raise"
    except ValidationError:
        pass


def test_workspace_to_dict_from_dict():
    ws = Workspace.create(name="test", owner="alice")
    d = ws.to_dict()
    ws2 = Workspace.from_dict(d)
    assert ws2.id == ws.id
    assert ws2.name == ws.name
    assert ws2.owner == ws.owner


def test_workspace_from_dict_missing_field():
    try:
        Workspace.from_dict({"id": "x", "name": "test"})
        assert False, "should raise"
    except ValidationError:
        pass


def test_session_create():
    ws = Workspace.create(name="test", owner="alice")
    sess = Session.create(workspace_id=ws.id)
    assert sess.workspace_id == ws.id
    assert sess.id  # UUID5 format
    assert sess.created_at == sess.last_active


def test_session_touch():
    ws = Workspace.create(name="test", owner="alice")
    sess = Session.create(workspace_id=ws.id)
    old = sess.last_active
    sess.touch()
    assert sess.last_active >= old


def test_persisted_task_create():
    ws = Workspace.create(name="test", owner="alice")
    task = PersistedTask.create(
        workspace_id=ws.id,
        task_id="task-001",
        plan={"task_id": "task-001", "steps": []},
        state={"task_id": "task-001", "current_step": 0},
    )
    assert task.workspace_id == ws.id
    assert task.task_id == "task-001"


def test_persisted_task_create_empty_workspace_id():
    try:
        PersistedTask.create(workspace_id="", task_id="t", plan={}, state={})
        assert False, "should raise"
    except ValidationError:
        pass


def test_persisted_task_to_dict_from_dict():
    ws = Workspace.create(name="test", owner="alice")
    task = PersistedTask.create(
        workspace_id=ws.id,
        task_id="task-001",
        plan={"task_id": "task-001", "steps": []},
        state={"task_id": "task-001", "current_step": 0},
    )
    d = task.to_dict()
    task2 = PersistedTask.from_dict(d)
    assert task2.task_id == task.task_id
    assert task2.workspace_id == task.workspace_id


def test_workspace_state_create():
    ws = Workspace.create(name="test", owner="alice")
    state = WorkspaceState.create(workspace_id=ws.id)
    assert state.workspace_id == ws.id
    assert state.tasks == []
    assert state.metadata == {}