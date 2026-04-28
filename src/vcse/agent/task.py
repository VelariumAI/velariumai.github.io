"""Agent task and step data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class StepStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ExecutionStatus(Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class ResultStatus(Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class Task:
    id: str
    description: str
    inputs: dict[str, Any]
    goal: dict[str, Any]
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "inputs": dict(self.inputs),
            "goal": dict(self.goal),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        return cls(
            id=str(data.get("id", "")),
            description=str(data.get("description", "")),
            inputs=dict(data.get("inputs", {})),
            goal=dict(data.get("goal", {})),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
        )


@dataclass(frozen=True)
class Step:
    id: str
    type: str
    tool_name: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    expected_output: dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "tool_name": self.tool_name,
            "inputs": dict(self.inputs),
            "expected_output": dict(self.expected_output),
            "status": self.status.value,
            "result": dict(self.result) if self.result is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Step":
        status = StepStatus(data.get("status", StepStatus.PENDING.value))
        return cls(
            id=str(data.get("id", "")),
            type=str(data.get("type", "")),
            tool_name=data.get("tool_name"),
            inputs=dict(data.get("inputs", {})),
            expected_output=dict(data.get("expected_output", {})),
            status=status,
            result=data.get("result"),
        )


@dataclass(frozen=True)
class Plan:
    task_id: str
    steps: tuple[Step, ...]
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Plan":
        steps = tuple(Step.from_dict(s) for s in data.get("steps", []))
        return cls(
            task_id=str(data.get("task_id", "")),
            steps=steps,
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
        )


@dataclass
class ExecutionState:
    task_id: str
    current_step: int = 0
    completed_steps: list[str] = field(default_factory=list)
    results: dict[str, Any] = field(default_factory=dict)
    status: ExecutionStatus = ExecutionStatus.RUNNING

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "current_step": self.current_step,
            "completed_steps": list(self.completed_steps),
            "results": dict(self.results),
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionState":
        return cls(
            task_id=str(data.get("task_id", "")),
            current_step=int(data.get("current_step", 0)),
            completed_steps=list(data.get("completed_steps", [])),
            results=dict(data.get("results", {})),
            status=ExecutionStatus(data.get("status", ExecutionStatus.RUNNING.value)),
        )


@dataclass(frozen=True)
class ToolCall:
    tool_name: str
    input: dict[str, Any]
    output: dict[str, Any]
    validated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "input": dict(self.input),
            "output": dict(self.output),
            "validated": self.validated,
        }


@dataclass(frozen=True)
class Result:
    status: ResultStatus
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "data": dict(self.data),
            "error": self.error,
        }