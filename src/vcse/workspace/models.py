"""Workspace data models."""

from __future__ import annotations

import uuid
import time
from dataclasses import dataclass, field, asdict
from typing import Any

from vcse.workspace.errors import ValidationError


def _namespace_uuid(name: str) -> str:
    """Generate a deterministic UUIDv5 from a string name."""
    return str(uuid.uuid5(uuid.NAMESPACE_OID, name))


def _timestamp() -> str:
    return f"{time.time():.6f}"


@dataclass
class Workspace:
    id: str
    name: str
    owner: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, name: str, owner: str, workspace_id: str | None = None) -> Workspace:
        if not name or not name.strip():
            raise ValidationError("name cannot be empty")
        if not owner or not owner.strip():
            raise ValidationError("owner cannot be empty")
        ws_id = workspace_id or _namespace_uuid(f"workspace:{name}:{owner}")
        return cls(
            id=ws_id,
            name=name.strip(),
            owner=owner.strip(),
            created_at=_timestamp(),
            metadata={},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Workspace:
        for req in ("id", "name", "owner", "created_at"):
            if req not in data:
                raise ValidationError(f"missing required field: {req}")
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            owner=str(data["owner"]),
            created_at=str(data["created_at"]),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class Session:
    id: str
    workspace_id: str
    created_at: str
    last_active: str

    @classmethod
    def create(cls, workspace_id: str, session_id: str | None = None) -> Session:
        sess_id = session_id or _namespace_uuid(f"session:{workspace_id}:{_timestamp()}")
        now = _timestamp()
        return cls(
            id=sess_id,
            workspace_id=workspace_id,
            created_at=now,
            last_active=now,
        )

    def touch(self) -> None:
        self.last_active = _timestamp()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        for req in ("id", "workspace_id", "created_at", "last_active"):
            if req not in data:
                raise ValidationError(f"missing required field: {req}")
        return cls(
            id=str(data["id"]),
            workspace_id=str(data["workspace_id"]),
            created_at=str(data["created_at"]),
            last_active=str(data["last_active"]),
        )


@dataclass
class PersistedTask:
    task_id: str
    workspace_id: str
    plan: dict[str, Any]
    state: dict[str, Any]
    created_at: str
    updated_at: str

    @classmethod
    def create(
        cls,
        workspace_id: str,
        task_id: str,
        plan: dict[str, Any],
        state: dict[str, Any],
    ) -> PersistedTask:
        if not workspace_id:
            raise ValidationError("workspace_id cannot be empty")
        if not task_id:
            raise ValidationError("task_id cannot be empty")
        now = _timestamp()
        return cls(
            task_id=task_id,
            workspace_id=workspace_id,
            plan=dict(plan),
            state=dict(state),
            created_at=now,
            updated_at=now,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PersistedTask:
        for req in ("task_id", "workspace_id", "plan", "state", "created_at", "updated_at"):
            if req not in data:
                raise ValidationError(f"missing required field: {req}")
        return cls(
            task_id=str(data["task_id"]),
            workspace_id=str(data["workspace_id"]),
            plan=dict(data["plan"]),
            state=dict(data["state"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
        )


@dataclass
class WorkspaceState:
    workspace_id: str
    tasks: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, workspace_id: str) -> WorkspaceState:
        return cls(workspace_id=workspace_id, tasks=[], metadata={})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkspaceState:
        return cls(
            workspace_id=str(data.get("workspace_id", "")),
            tasks=list(data.get("tasks", [])),
            metadata=dict(data.get("metadata", {})),
        )