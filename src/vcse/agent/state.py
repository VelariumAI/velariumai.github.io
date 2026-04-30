"""Execution state management — deterministic updates."""

from __future__ import annotations

from vcse.agent.errors import StateError
from vcse.agent.task import (
    ExecutionState,
    ExecutionStatus,
    Result,
    Step,
    StepStatus,
)


class StateManager:
    """
    Deterministic execution state updates.

    All updates are pure functions — no mutation of previous state.
    Each update produces a new ExecutionState.
    """

    @staticmethod
    def update(
        state: ExecutionState,
        completed_step: Step,
        result: Result | None = None,
    ) -> ExecutionState:
        """
        Update state after a step completes or fails.

        Rules:
        - current_step advances by 1
        - completed_steps appends step id
        - results stores step output
        - status reflects overall execution

        Returns new ExecutionState (does not mutate).
        """
        if completed_step.status not in (StepStatus.COMPLETED, StepStatus.FAILED):
            return state

        new_completed = list(state.completed_steps)
        new_results = dict(state.results)

        new_completed.append(completed_step.id)

        if completed_step.id in new_results:
            # Merge rather than overwrite
            existing = new_results[completed_step.id]
            if isinstance(existing, dict) and isinstance(completed_step.result, dict):
                new_results[completed_step.id] = {**existing, **completed_step.result}
            else:
                new_results[completed_step.id] = completed_step.result
        else:
            new_results[completed_step.id] = completed_step.result or {}

        # Determine status
        if completed_step.status == StepStatus.FAILED:
            new_status = ExecutionStatus.FAILED
        elif len(new_completed) == len(state.results) + 1:
            # Advanced one step
            new_status = ExecutionStatus.RUNNING
        else:
            new_status = state.status

        return ExecutionState(
            task_id=state.task_id,
            current_step=state.current_step + 1,
            completed_steps=new_completed,
            results=new_results,
            status=new_status,
        )

    @staticmethod
    def advance(state: ExecutionState) -> ExecutionState:
        """Advance to next step without completing one (for blocked states)."""
        return ExecutionState(
            task_id=state.task_id,
            current_step=state.current_step,
            completed_steps=list(state.completed_steps),
            results=dict(state.results),
            status=ExecutionStatus.BLOCKED,
        )

    @staticmethod
    def restore(state_dict: dict[str, Any]) -> ExecutionState:
        """Reconstruct state from dict (for deserialization)."""
        return ExecutionState.from_dict(state_dict)