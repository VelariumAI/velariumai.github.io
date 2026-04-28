"""Workspace errors."""

from __future__ import annotations


class WorkspaceError(Exception):
    """Base workspace error."""
    code: str = "WORKSPACE_ERROR"


class InvalidWorkspaceID(WorkspaceError):
    code = "INVALID_WORKSPACE_ID"


class WorkspaceNotFound(WorkspaceError):
    code = "WORKSPACE_NOT_FOUND"


class WorkspaceExists(WorkspaceError):
    code = "WORKSPACE_EXISTS"


class TaskNotFound(WorkspaceError):
    code = "TASK_NOT_FOUND"


class SessionNotFound(WorkspaceError):
    code = "SESSION_NOT_FOUND"


class IsolationViolation(WorkspaceError):
    code = "ISOLATION_VIOLATION"


class SerializationError(WorkspaceError):
    code = "SERIALIZATION_ERROR"


class ImportError(WorkspaceError):
    code = "IMPORT_ERROR"


class ExportError(WorkspaceError):
    code = "EXPORT_ERROR"


class ValidationError(WorkspaceError):
    code = "VALIDATION_ERROR"