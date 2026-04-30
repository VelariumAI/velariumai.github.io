"""Workspace storage layer with atomic writes."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from vcse.workspace.errors import (
    SerializationError,
    WorkspaceNotFound,
    TaskNotFound,
    IsolationViolation,
)
from vcse.workspace.isolation import validate_workspace_path


_WORKSPACE_ROOT = Path.home() / ".vcse" / "workspaces"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SerializationError(f"failed to read {path}: {exc}")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Atomic write: write to temp file then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.rename(path)


def _delete_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.is_file():
        path.unlink()


class WorkspaceStore:
    """
    Local file-based storage for workspaces.

    Structure:
      ~/.vcse/workspaces/<workspace_id>/
        workspace.json
        metadata.json
        sessions/
          <session_id>.json
        tasks/
          <task_id>.json
        ledger/
          events.jsonl
    """

    def __init__(self, root: Path | str | None = None) -> None:
        self._root = Path(root) if root else _WORKSPACE_ROOT

    def _ws_path(self, workspace_id: str) -> Path:
        p = self._root / workspace_id
        validate_workspace_path(str(p), str(self._root))
        return p

    def _task_path(self, workspace_id: str, task_id: str) -> Path:
        return self._ws_path(workspace_id) / "tasks" / f"{task_id}.json"

    def create_workspace(self, workspace_id: str, data: dict[str, Any]) -> None:
        ws_dir = self._ws_path(workspace_id)
        ws_dir.mkdir(parents=True, exist_ok=True)
        (ws_dir / "tasks").mkdir(exist_ok=True)
        (ws_dir / "sessions").mkdir(exist_ok=True)
        (ws_dir / "ledger").mkdir(exist_ok=True)
        _write_json(ws_dir / "workspace.json", data)

    def load_workspace(self, workspace_id: str) -> dict[str, Any]:
        path = self._ws_path(workspace_id) / "workspace.json"
        if not path.is_file():
            raise WorkspaceNotFound(f"workspace not found: {workspace_id}")
        return _read_json(path)

    def workspace_exists(self, workspace_id: str) -> bool:
        return (self._ws_path(workspace_id) / "workspace.json").is_file()

    def delete_workspace(self, workspace_id: str) -> None:
        ws_dir = self._ws_path(workspace_id)
        if not ws_dir.is_dir():
            raise WorkspaceNotFound(f"workspace not found: {workspace_id}")
        _delete_path(ws_dir)

    def list_workspaces(self) -> list[dict[str, Any]]:
        if not self._root.is_dir():
            return []
        results = []
        for entry in self._root.iterdir():
            wp = entry / "workspace.json"
            if entry.is_dir() and wp.is_file():
                try:
                    results.append(_read_json(wp))
                except Exception:
                    continue
        return results

    def save_task(self, workspace_id: str, task_id: str, data: dict[str, Any]) -> None:
        validate_workspace_path(str(self._ws_path(workspace_id)), str(self._root))
        path = self._task_path(workspace_id, task_id)
        _write_json(path, data)

    def load_task(self, workspace_id: str, task_id: str) -> dict[str, Any]:
        validate_workspace_path(str(self._ws_path(workspace_id)), str(self._root))
        path = self._task_path(workspace_id, task_id)
        if not path.is_file():
            raise TaskNotFound(f"task not found: {task_id}")
        return _read_json(path)

    def task_exists(self, workspace_id: str, task_id: str) -> bool:
        return self._task_path(workspace_id, task_id).is_file()

    def delete_task(self, workspace_id: str, task_id: str) -> None:
        validate_workspace_path(str(self._ws_path(workspace_id)), str(self._root))
        path = self._task_path(workspace_id, task_id)
        if path.is_file():
            path.unlink()

    def list_tasks(self, workspace_id: str) -> list[dict[str, Any]]:
        validate_workspace_path(str(self._ws_path(workspace_id)), str(self._root))
        tasks_dir = self._ws_path(workspace_id) / "tasks"
        if not tasks_dir.is_dir():
            return []
        results = []
        for fp in tasks_dir.iterdir():
            if fp.suffix == ".json":
                try:
                    results.append(_read_json(fp))
                except Exception:
                    continue
        return results

    def save_session(self, workspace_id: str, session_id: str, data: dict[str, Any]) -> None:
        validate_workspace_path(str(self._ws_path(workspace_id)), str(self._root))
        path = self._ws_path(workspace_id) / "sessions" / f"{session_id}.json"
        _write_json(path, data)

    def load_session(self, workspace_id: str, session_id: str) -> dict[str, Any]:
        validate_workspace_path(str(self._ws_path(workspace_id)), str(self._root))
        path = self._ws_path(workspace_id) / "sessions" / f"{session_id}.json"
        if not path.is_file():
            from vcse.workspace.errors import SessionNotFound
            raise SessionNotFound(f"session not found: {session_id}")
        return _read_json(path)

    def list_sessions(self, workspace_id: str) -> list[dict[str, Any]]:
        validate_workspace_path(str(self._ws_path(workspace_id)), str(self._root))
        sessions_dir = self._ws_path(workspace_id) / "sessions"
        if not sessions_dir.is_dir():
            return []
        results = []
        for fp in sessions_dir.iterdir():
            if fp.suffix == ".json":
                try:
                    results.append(_read_json(fp))
                except Exception:
                    continue
        return results

    def append_ledger_event(self, workspace_id: str, event: dict[str, Any]) -> None:
        validate_workspace_path(str(self._ws_path(workspace_id)), str(self._root))
        ledger_path = self._ws_path(workspace_id) / "ledger" / "events.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ledger_path, "a") as f:
            f.write(json.dumps(event) + "\n")

    def read_ledger_events(self, workspace_id: str) -> list[dict[str, Any]]:
        validate_workspace_path(str(self._ws_path(workspace_id)), str(self._root))
        ledger_path = self._ws_path(workspace_id) / "ledger" / "events.jsonl"
        if not ledger_path.is_file():
            return []
        events = []
        with open(ledger_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return events