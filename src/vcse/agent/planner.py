"""Deterministic task planner using rule-based templates."""

from __future__ import annotations

import uuid
from typing import Any

from vcse.agent.errors import PlanningError
from vcse.agent.task import Plan, Step, StepStatus, Task


def _step_id() -> str:
    return f"step_{uuid.uuid4().hex[:8]}"


def _plan_task_from_template(task: Task) -> Plan:
    """
    Map task description/goal to a predefined step sequence.

    Template rules (no dynamic reasoning):
    - "can X die" / "is X mortal" → vcse_query with verify_claim
    - "check if" / "verify that" → vcse_query + verify_claim
    - "solve" / "calculate" / "compute" → math_solver
    - "read file" / "show contents" → file_read
    - "write" / "save" → file_write
    - "assert" / "prove" → assert_claim
    - default → INCONCLUSIVE
    """
    desc = task.description.lower()
    goal_keys = list(task.goal.keys()) if task.goal else []
    inputs_keys = list(task.inputs.keys()) if task.inputs else []

    # Mortality/can-die type questions
    if any(kw in desc for kw in ["can die", "mortal", "is mortal", "die", "death"]):
        steps: list[Step] = []
        goal = task.goal

        # Step 1: Load facts into knowledge base
        if inputs_keys:
            steps.append(Step(
                id=_step_id(),
                type="tool",
                tool_name="vcse_query",
                inputs={"query": task.description, "facts": task.inputs.get("facts", []), "goal": task.goal},
                expected_output={"answer": "...", "status": "..."},
            ))
        else:
            # Use description as the query
            steps.append(Step(
                id=_step_id(),
                type="tool",
                tool_name="vcse_query",
                inputs={"query": task.description},
                expected_output={"answer": "...", "status": "..."},
            ))

        return Plan(task_id=task.id, steps=tuple(steps))

    # Arithmetic expressions
    if any(kw in desc for kw in ["solve", "calculate", "compute", "evaluate", "math"]):
        expression = task.inputs.get("expression", task.description)
        return Plan(
            task_id=task.id,
            steps=(
                Step(
                    id=_step_id(),
                    type="tool",
                    tool_name="math_solver",
                    inputs={"expression": str(expression)},
                    expected_output={"result": "..."},
                ),
            ),
        )

    # File read
    if any(kw in desc for kw in ["read file", "show contents", "display file", "cat "]):
        path = task.inputs.get("path", "")
        return Plan(
            task_id=task.id,
            steps=(
                Step(
                    id=_step_id(),
                    type="tool",
                    tool_name="file_read",
                    inputs={"path": path},
                    expected_output={"content": "..."},
                ),
            ),
        )

    # File write
    if any(kw in desc for kw in ["write to file", "save to", "write file"]):
        path = task.inputs.get("path", "")
        content = task.inputs.get("content", "")
        return Plan(
            task_id=task.id,
            steps=(
                Step(
                    id=_step_id(),
                    type="tool",
                    tool_name="file_write",
                    inputs={"path": path, "content": content},
                    expected_output={"written": True},
                ),
            ),
        )

    # Claim assertion
    if any(kw in desc for kw in ["assert", "prove", "confirm"]):
        claim = task.inputs.get("claim", task.goal)
        return Plan(
            task_id=task.id,
            steps=(
                Step(
                    id=_step_id(),
                    type="tool",
                    tool_name="assert_claim",
                    inputs={"claim": claim},
                    expected_output={"verified": True},
                ),
            ),
        )

    # Claim verification
    if any(kw in desc for kw in ["verify", "check if", "validate"]):
        claim = task.inputs.get("claim", task.goal)
        return Plan(
            task_id=task.id,
            steps=(
                Step(
                    id=_step_id(),
                    type="tool",
                    tool_name="verify_claim",
                    inputs={"claim": claim},
                    expected_output={"verified": True},
                ),
            ),
        )

    # Generic query
    if "query" in inputs_keys or "ask" in desc:
        return Plan(
            task_id=task.id,
            steps=(
                Step(
                    id=_step_id(),
                    type="tool",
                    tool_name="vcse_query",
                    inputs={"query": task.inputs.get("query", task.description)},
                    expected_output={"answer": "...", "status": "..."},
                ),
            ),
        )

    # Cannot plan
    return Plan(task_id=task.id, steps=())


def plan_task(task: Task | dict[str, Any]) -> Plan:
    """
    Create a Plan for a Task using deterministic template matching.

    Returns Plan with steps, or Plan with empty steps if task cannot be planned.
    Raises PlanningError on invalid task.
    """
    if isinstance(task, dict):
        t = Task.from_dict(task)
    else:
        t = task

    # Validate task
    from vcse.agent.validation import validate_task
    errors = validate_task(t)
    if errors:
        raise PlanningError("INVALID_TASK", "; ".join(errors))

    plan = _plan_task_from_template(t)

    # If no steps generated, mark as inconclusive
    if not plan.steps:
        # Return a single inconclusive step as placeholder
        return Plan(
            task_id=t.id,
            steps=(
                Step(
                    id=_step_id(),
                    type="query",
                    inputs={"task": t.description},
                    expected_output={"status": "INCONCLUSIVE", "reason": "no template matched"},
                ),
            ),
        )

    return plan