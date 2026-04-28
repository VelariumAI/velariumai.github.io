"""Ledger event definitions for workspace operations."""

from __future__ import annotations

import time
from typing import Any


def _timestamp() -> str:
    return f"{time.time():.6f}"


def workspace_created(workspace_id: str, name: str, owner: str, **metadata: Any) -> dict[str, Any]:
    return {
        "event": "WORKSPACE_CREATED",
        "workspace_id": workspace_id,
        "timestamp": _timestamp(),
        "payload": {"name": name, "owner": owner, "metadata": metadata},
    }


def workspace_deleted(workspace_id: str, **metadata: Any) -> dict[str, Any]:
    return {
        "event": "WORKSPACE_DELETED",
        "workspace_id": workspace_id,
        "timestamp": _timestamp(),
        "payload": metadata,
    }


def task_persisted(
    workspace_id: str,
    task_id: str,
    step_index: int,
    **metadata: Any,
) -> dict[str, Any]:
    return {
        "event": "TASK_PERSISTED",
        "workspace_id": workspace_id,
        "timestamp": _timestamp(),
        "payload": {
            "task_id": task_id,
            "step_index": step_index,
            **metadata,
        },
    }


def task_resumed(
    workspace_id: str,
    task_id: str,
    step_index: int,
    **metadata: Any,
) -> dict[str, Any]:
    return {
        "event": "TASK_RESUMED",
        "workspace_id": workspace_id,
        "timestamp": _timestamp(),
        "payload": {
            "task_id": task_id,
            "step_index": step_index,
            **metadata,
        },
    }


def workspace_exported(workspace_id: str, path: str, **metadata: Any) -> dict[str, Any]:
    return {
        "event": "WORKSPACE_EXPORTED",
        "workspace_id": workspace_id,
        "timestamp": _timestamp(),
        "payload": {"path": path, **metadata},
    }


def workspace_imported(workspace_id: str, path: str, **metadata: Any) -> dict[str, Any]:
    return {
        "event": "WORKSPACE_IMPORTED",
        "workspace_id": workspace_id,
        "timestamp": _timestamp(),
        "payload": {"path": path, **metadata},
    }


def session_created(workspace_id: str, session_id: str, **metadata: Any) -> dict[str, Any]:
    return {
        "event": "SESSION_CREATED",
        "workspace_id": workspace_id,
        "timestamp": _timestamp(),
        "payload": {"session_id": session_id, **metadata},
    }


def task_completed(workspace_id: str, task_id: str, **metadata: Any) -> dict[str, Any]:
    return {
        "event": "TASK_COMPLETED",
        "workspace_id": workspace_id,
        "timestamp": _timestamp(),
        "payload": {"task_id": task_id, **metadata},
    }