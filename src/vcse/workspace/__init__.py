"""Persistent multi-user workspace system."""

from vcse.workspace.models import Workspace, Session, PersistedTask, WorkspaceState
from vcse.workspace.manager import WorkspaceManager
from vcse.workspace.store import WorkspaceStore
from vcse.workspace.state_store import StateStore
from vcse.workspace.errors import (
    WorkspaceError,
    InvalidWorkspaceID,
    WorkspaceNotFound,
    WorkspaceExists,
    TaskNotFound,
    SessionNotFound,
    IsolationViolation,
    SerializationError,
    ImportError,
    ExportError,
    ValidationError,
)

__all__ = [
    "Workspace",
    "Session",
    "PersistedTask",
    "WorkspaceState",
    "WorkspaceManager",
    "WorkspaceStore",
    "StateStore",
    "WorkspaceError",
    "InvalidWorkspaceID",
    "WorkspaceNotFound",
    "WorkspaceExists",
    "TaskNotFound",
    "SessionNotFound",
    "IsolationViolation",
    "SerializationError",
    "ImportError",
    "ExportError",
    "ValidationError",
]