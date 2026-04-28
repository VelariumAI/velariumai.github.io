"""Execution engine with step-by-step validation and ledger logging."""

from __future__ import annotations

import uuid
from typing import Any

from vcse.agent.errors import ExecutionError
from vcse.agent.planner import plan_task
from vcse.agent.state import ExecutionState, ExecutionStatus, StateManager
from vcse.agent.task import (
    ExecutionState as ExecState,
    Plan,
    Result,
    ResultStatus,
    Step,
    StepStatus,
    Task,
)
from vcse.agent.tools import get_registry
from vcse.agent.validation import validate_step


def _result_from_tool_output(tool_name: str, output: dict[str, Any]) -> Result:
    """Convert tool output to Result."""
    if tool_name in ("vcse_query", "assert_claim", "verify_claim"):
        status = ResultStatus.SUCCESS if output.get("verified", False) or "answer" in output else ResultStatus.FAILURE
        if output.get("status") == "INCONCLUSIVE":
            status = ResultStatus.INCONCLUSIVE
        return Result(status=status, data=output)

    if "error" in output:
        return Result(status=ResultStatus.FAILURE, data=output, error=output["error"])

    return Result(status=ResultStatus.SUCCESS, data=output)


def execute_step(
    step: Step,
    state: ExecutionState,
    tool_registry=None,
    ledger_logger=None,
) -> tuple[Step, ExecutionState]:
    """
    Execute a single step with full validation.

    Steps:
    1. Validate step schema
    2. Mark step RUNNING
    3. Execute tool (with input validation)
    4. Validate output
    5. Convert to Result
    6. Update state
    7. Mark step COMPLETED

    Returns (updated_step, updated_state).
    Raises ExecutionError on failure.
    """
    if tool_registry is None:
        tool_registry = get_registry()
    if ledger_logger is None:
        ledger_logger = default_ledger_logger

    # Validate step schema
    errors = validate_step(step)
    if errors:
        step = Step(
            id=step.id,
            type=step.type,
            tool_name=step.tool_name,
            inputs=step.inputs,
            expected_output=step.expected_output,
            status=StepStatus.FAILED,
            result={"error": "; ".join(errors)},
        )
        state = StateManager.update(state, step)
        raise ExecutionError("INVALID_STEP", "; ".join(errors))

    # Mark RUNNING
    step = Step(
        id=step.id,
        type=step.type,
        tool_name=step.tool_name,
        inputs=step.inputs,
        expected_output=step.expected_output,
        status=StepStatus.RUNNING,
    )

    # Log step started
    try:
        ledger_logger("STEP_STARTED", {
            "task_id": state.task_id,
            "step_id": step.id,
            "tool_name": step.tool_name,
        })
    except Exception:
        pass  # ledger failure should not halt execution

    # Execute via tool registry
    if step.type == "tool" and step.tool_name:
        try:
            tool_output = tool_registry.execute(step.tool_name, step.inputs)
            step = Step(
                id=step.id,
                type=step.type,
                tool_name=step.tool_name,
                inputs=step.inputs,
                expected_output=step.expected_output,
                status=StepStatus.COMPLETED,
                result=tool_output,
            )
            result_obj = _result_from_tool_output(step.tool_name, tool_output)
        except Exception as exc:
            step = Step(
                id=step.id,
                type=step.type,
                tool_name=step.tool_name,
                inputs=step.inputs,
                expected_output=step.expected_output,
                status=StepStatus.FAILED,
                result={"error": str(exc)},
            )
            state = StateManager.update(state, step)
            try:
                ledger_logger("STEP_FAILED", {
                    "task_id": state.task_id,
                    "step_id": step.id,
                    "error": str(exc),
                })
            except Exception:
                pass
            return step, state

    elif step.type == "query":
        # Handle query step — just store inputs as result
        step = Step(
            id=step.id,
            type=step.type,
            tool_name=step.tool_name,
            inputs=step.inputs,
            expected_output=step.expected_output,
            status=StepStatus.COMPLETED,
            result={"status": "COMPLETED", "inputs": step.inputs},
        )
        result_obj = Result(status=ResultStatus.SUCCESS, data=step.result)

    else:
        step = Step(
            id=step.id,
            type=step.type,
            tool_name=step.tool_name,
            inputs=step.inputs,
            expected_output=step.expected_output,
            status=StepStatus.COMPLETED,
            result={"status": "COMPLETED"},
        )
        result_obj = Result(status=ResultStatus.SUCCESS, data=step.result)

    # Update state with completed step
    state = StateManager.update(state, step, result_obj)

    # Log step completed
    try:
        ledger_logger("STEP_COMPLETED", {
            "task_id": state.task_id,
            "step_id": step.id,
            "result_status": result_obj.status.value,
        })
    except Exception:
        pass

    return step, state


def execute_plan(
    plan: Plan,
    initial_state: ExecutionState | None = None,
    tool_registry=None,
    ledger_logger=None,
) -> tuple[Plan, ExecutionState]:
    """
    Execute all steps in a plan in order.

    Stops on first failure. State is updated after each step.

    Returns (updated_plan, final_state).
    """
    if initial_state is None:
        initial_state = ExecutionState(task_id=plan.task_id)

    state = initial_state
    updated_steps: list[Step] = []

    for step in plan.steps:
        try:
            updated_step, state = execute_step(step, state, tool_registry, ledger_logger)
            updated_steps.append(updated_step)
            if updated_step.status == StepStatus.FAILED:
                break
        except ExecutionError:
            # Already handled in execute_step (step marked FAILED there)
            updated_steps.append(step)
            break
        except Exception as exc:
            failed_step = Step(
                id=step.id,
                type=step.type,
                tool_name=step.tool_name,
                inputs=step.inputs,
                expected_output=step.expected_output,
                status=StepStatus.FAILED,
                result={"error": str(exc)},
            )
            updated_steps.append(failed_step)
            state = StateManager.update(state, failed_step)
            break

    # Determine final state status
    if state.completed_steps:
        if any(s.status == StepStatus.FAILED for s in updated_steps):
            state = ExecutionState(
                task_id=state.task_id,
                current_step=state.current_step,
                completed_steps=state.completed_steps,
                results=state.results,
                status=ExecutionStatus.FAILED,
            )
        else:
            state = ExecutionState(
                task_id=state.task_id,
                current_step=state.current_step,
                completed_steps=state.completed_steps,
                results=state.results,
                status=ExecutionStatus.COMPLETED,
            )

    updated_plan = Plan(
        task_id=plan.task_id,
        steps=tuple(updated_steps),
        created_at=plan.created_at,
    )

    return updated_plan, state


def run_task(
    task: Task | dict[str, Any],
    tool_registry=None,
    ledger_logger=None,
) -> tuple[Task, Plan, ExecutionState]:
    """
    Full task execution: plan → execute → return all artifacts.

    Returns (task, final_plan, final_state).
    """
    if isinstance(task, dict):
        t = Task.from_dict(task)
    else:
        t = task

    # Log task created
    if ledger_logger:
        try:
            ledger_logger("TASK_CREATED", {
                "task_id": t.id,
                "description": t.description,
                "inputs": t.inputs,
                "goal": t.goal,
            })
        except Exception:
            pass

    # Create plan
    plan = plan_task(t)

    # Log plan created
    if ledger_logger:
        try:
            ledger_logger("PLAN_CREATED", {
                "task_id": t.id,
                "step_count": len(plan.steps),
            })
        except Exception:
            pass

    # Execute plan
    final_plan, final_state = execute_plan(
        plan,
        ExecutionState(task_id=t.id),
        tool_registry,
        ledger_logger,
    )

    # Log task completed
    if ledger_logger:
        try:
            ledger_logger("TASK_COMPLETED", {
                "task_id": t.id,
                "status": final_state.status.value,
                "completed_steps": len(final_state.completed_steps),
            })
        except Exception:
            pass

    return t, final_plan, final_state


def resume_task(
    task: Task,
    plan: Plan,
    initial_state: ExecutionState,
    tool_registry=None,
    ledger_logger=None,
) -> tuple[Task, Plan, ExecutionState]:
    """
    Resume a task from saved plan and state.

    Skips completed steps, executes only remaining steps.
    Returns (task, final_plan, final_state).
    """
    if tool_registry is None:
        tool_registry = get_registry()
    if ledger_logger is None:
        ledger_logger = default_ledger_logger

    # Filter to remaining steps
    completed_ids = set(initial_state.completed_steps)
    remaining_steps = [s for s in plan.steps if s.id not in completed_ids]
    if not remaining_steps:
        return task, plan, initial_state

    state = initial_state
    updated_steps: list[Step] = []

    for step in remaining_steps:
        try:
            updated_step, state = execute_step(step, state, tool_registry, ledger_logger)
            updated_steps.append(updated_step)
            if updated_step.status == StepStatus.FAILED:
                break
        except ExecutionError:
            updated_steps.append(step)
            break
        except Exception as exc:
            failed_step = Step(
                id=step.id,
                type=step.type,
                tool_name=step.tool_name,
                inputs=step.inputs,
                expected_output=step.expected_output,
                status=StepStatus.FAILED,
                result={"error": str(exc)},
            )
            updated_steps.append(failed_step)
            state = StateManager.update(state, failed_step)
            break

    # Build final plan: original completed steps + newly executed
    completed_original = [s for s in plan.steps if s.id in completed_ids]
    final_steps = tuple(completed_original) + tuple(updated_steps)

    if any(s.status == StepStatus.FAILED for s in updated_steps):
        final_status = ExecutionStatus.FAILED
    elif updated_steps:
        final_status = ExecutionStatus.COMPLETED
    else:
        final_status = initial_state.status

    final_state = ExecutionState(
        task_id=state.task_id,
        current_step=state.current_step,
        completed_steps=state.completed_steps,
        results=state.results,
        status=final_status,
    )

    final_plan = Plan(
        task_id=plan.task_id,
        steps=final_steps,
        created_at=plan.created_at,
    )

    return task, final_plan, final_state


def default_ledger_logger(event_type: str, payload: dict[str, Any]) -> None:
    """
    Default ledger logger — logs to stdout.

    In production this would write to the VCSE ledger system.
    Here we provide a no-op that can be replaced via injection.
    """
    pass