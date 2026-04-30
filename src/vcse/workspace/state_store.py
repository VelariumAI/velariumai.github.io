"""Task state persistence layer."""

from __future__ import annotations

from typing import Any

from vcse.workspace.errors import TaskNotFound
from vcse.workspace.store import WorkspaceStore
from vcse.workspace.models import PersistedTask


class StateStore:
    """Persist and retrieve agent task execution state."""

    def __init__(self, store: WorkspaceStore) -> None:
        self._store = store

    def save_task(
        self,
        workspace_id: str,
        task_id: str,
        plan: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        persisted = PersistedTask.create(
            workspace_id=workspace_id,
            task_id=task_id,
            plan=plan,
            state=state,
        )
        self._store.save_task(workspace_id, task_id, persisted.to_dict())

    def load_task(self, workspace_id: str, task_id: str) -> PersistedTask:
        data = self._store.load_task(workspace_id, task_id)
        return PersistedTask.from_dict(data)

    def task_exists(self, workspace_id: str, task_id: str) -> bool:
        return self._store.task_exists(workspace_id, task_id)

    def list_tasks(self, workspace_id: str) -> list[PersistedTask]:
        all_data = self._store.list_tasks(workspace_id)
        return [PersistedTask.from_dict(d) for d in all_data]

    def delete_task(self, workspace_id: str, task_id: str) -> None:
        self._store.delete_task(workspace_id, task_id)