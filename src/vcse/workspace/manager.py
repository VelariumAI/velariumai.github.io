"""Workspace manager — create, load, list, delete workspaces."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from vcse.workspace.errors import (
    WorkspaceExists,
    WorkspaceNotFound,
    ValidationError,
    ExportError,
    ImportError,
)
from vcse.workspace.isolation import verify_workspace_id
from vcse.workspace.models import Workspace, Session, PersistedTask
from vcse.workspace.store import WorkspaceStore
from vcse.workspace.state_store import StateStore


class WorkspaceManager:
    """Manage workspaces with strict isolation."""

    def __init__(self, store: WorkspaceStore | None = None) -> None:
        self._store = store or WorkspaceStore()
        self._state_store = StateStore(self._store)

    # ─── Workspace CRUD ───────────────────────────────────────────────────

    def create_workspace(self, name: str, owner: str, workspace_id: str | None = None) -> Workspace:
        ws = Workspace.create(name=name, owner=owner, workspace_id=workspace_id)
        if self._store.workspace_exists(ws.id):
            raise WorkspaceExists(f"workspace already exists: {ws.name} ({ws.id})")
        self._store.create_workspace(ws.id, ws.to_dict())
        return ws

    def load_workspace(self, workspace_id: str) -> Workspace:
        data = self._store.load_workspace(workspace_id)
        return Workspace.from_dict(data)

    def list_workspaces(self) -> list[Workspace]:
        all_data = self._store.list_workspaces()
        return [Workspace.from_dict(d) for d in all_data]

    def delete_workspace(self, workspace_id: str) -> None:
        if not self._store.workspace_exists(workspace_id):
            raise WorkspaceNotFound(f"workspace not found: {workspace_id}")
        self._store.delete_workspace(workspace_id)

    # ─── Session management ──────────────────────────────────────────────

    def create_session(self, workspace_id: str) -> Session:
        if not self._store.workspace_exists(workspace_id):
            raise WorkspaceNotFound(f"workspace not found: {workspace_id}")
        session = Session.create(workspace_id=workspace_id)
        self._store.save_session(workspace_id, session.id, session.to_dict())
        return session

    def load_session(self, workspace_id: str, session_id: str) -> Session:
        data = self._store.load_session(workspace_id, session_id)
        return Session.from_dict(data)

    def list_sessions(self, workspace_id: str) -> list[Session]:
        all_data = self._store.list_sessions(workspace_id)
        return [Session.from_dict(d) for d in all_data]

    # ─── Task persistence ────────────────────────────────────────────────

    def save_task(
        self,
        workspace_id: str,
        task_id: str,
        plan: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        self._state_store.save_task(workspace_id, task_id, plan, state)

    def load_task(self, workspace_id: str, task_id: str) -> PersistedTask:
        return self._state_store.load_task(workspace_id, task_id)

    def list_tasks(self, workspace_id: str) -> list[PersistedTask]:
        return self._state_store.list_tasks(workspace_id)

    def task_exists(self, workspace_id: str, task_id: str) -> bool:
        return self._state_store.task_exists(workspace_id, task_id)

    # ─── Import / Export ─────────────────────────────────────────────────

    def export_workspace(self, workspace_id: str, output_path: str) -> None:
        ws = self.load_workspace(workspace_id)
        tasks = self._state_store.list_tasks(workspace_id)
        sessions = self._store.list_sessions(workspace_id)
        events = self._store.read_ledger_events(workspace_id)

        export_data = {
            "version": "2.6.0",
            "workspace": ws.to_dict(),
            "tasks": [t.to_dict() for t in tasks],
            "sessions": sessions,
            "ledger_events": events,
        }

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        import json
        tmp = output.with_suffix(".tmp")
        tmp.write_text(json.dumps(export_data, indent=2))
        tmp.rename(output)

    def import_workspace(self, input_path: str, force: bool = False) -> Workspace:
        import json
        path = Path(input_path)
        if not path.is_file():
            raise ImportError(f"import file not found: {input_path}")

        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ImportError(f"invalid import file: {exc}")

        ws_data = data.get("workspace", {})
        ws = Workspace.from_dict(ws_data)

        if self._store.workspace_exists(ws.id):
            if not force:
                raise ImportError(f"workspace already exists: {ws.id}. Use --force to overwrite.")
            self._store.delete_workspace(ws.id)

        self._store.create_workspace(ws.id, ws.to_dict())

        # restore tasks
        for task_data in data.get("tasks", []):
            pt = PersistedTask.from_dict(task_data)
            self._state_store.save_task(ws.id, pt.task_id, pt.plan, pt.state)

        # restore sessions
        for sess_data in data.get("sessions", []):
            sess = Session.from_dict(sess_data)
            self._store.save_session(ws.id, sess.id, sess.to_dict())

        # restore ledger events
        for event in data.get("ledger_events", []):
            self._store.append_ledger_event(ws.id, event)

        return ws