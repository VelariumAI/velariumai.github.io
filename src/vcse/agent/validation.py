"""Validation layer for tasks, steps, and tool I/O."""

from __future__ import annotations

import re
from typing import Any

from vcse.agent.errors import ValidationError
from vcse.agent.task import Task, Step


def _fail(code: str, message: str) -> None:
    raise ValidationError(code, message)


def validate_task(task: Task | dict[str, Any]) -> list[str]:
    """
    Validate a task. Returns list of error strings (empty = valid).

    Rules:
    - id: non-empty string
    - description: non-empty string
    - inputs: dict
    - goal: dict (must have at least one key)
    """
    errors: list[str] = []
    if isinstance(task, dict):
        t = Task.from_dict(task)
    else:
        t = task

    if not t.id.strip():
        errors.append("[VALIDATION] task id is empty")
    if not t.description.strip():
        errors.append("[VALIDATION] task description is empty")
    if not isinstance(t.inputs, dict):
        errors.append("[VALIDATION] task inputs must be a dict")
    if not isinstance(t.goal, dict):
        errors.append("[VALIDATION] task goal must be a dict")
    return errors


def validate_step(step: Step | dict[str, Any]) -> list[str]:
    """
    Validate a step. Returns list of error strings (empty = valid).

    Rules:
    - id: non-empty string
    - type: non-empty string, alphanumeric + underscore only
    - tool_name: required for 'tool' type steps
    - inputs: dict
    """
    errors: list[str] = []
    if isinstance(step, dict):
        s = Step.from_dict(step)
    else:
        s = step

    if not s.id.strip():
        errors.append("[VALIDATION] step id is empty")
    if not s.type.strip():
        errors.append("[VALIDATION] step type is empty")
    if not re.match(r"^[a-zA-Z0-9_]+$", s.type):
        errors.append(f"[VALIDATION] step type contains invalid characters: {s.type}")
    if s.type not in ("tool", "query", "verify", "branch"):
        errors.append(f"[VALIDATION] unknown step type: {s.type}")
    if s.type == "tool" and not s.tool_name:
        errors.append("[VALIDATION] tool-type step missing tool_name")
    if not isinstance(s.inputs, dict):
        errors.append("[VALIDATION] step inputs must be a dict")
    return errors


def validate_tool_input(tool_name: str, tool_input: dict[str, Any]) -> list[str]:
    """
    Validate tool input against tool schema.

    Returns list of error strings (empty = valid).
    """
    errors: list[str] = []

    if tool_name == "vcse_query":
        if "query" not in tool_input:
            errors.append("[VALIDATION] vcse_query requires 'query' field")
        elif not isinstance(tool_input["query"], str) or not tool_input["query"].strip():
            errors.append("[VALIDATION] vcse_query.query must be non-empty string")

    elif tool_name == "math_solver":
        if "expression" not in tool_input:
            errors.append("[VALIDATION] math_solver requires 'expression' field")
        elif not isinstance(tool_input["expression"], str):
            errors.append("[VALIDATION] math_solver.expression must be string")

    elif tool_name == "file_read":
        if "path" not in tool_input:
            errors.append("[VALIDATION] file_read requires 'path' field")
        elif not isinstance(tool_input["path"], str):
            errors.append("[VALIDATION] file_read.path must be string")
        elif ".." in tool_input["path"] or tool_input["path"].startswith("/"):
            errors.append("[VALIDATION] file_read.path must be relative and safe")

    elif tool_name == "file_write":
        required = ["path", "content"]
        for field_name in required:
            if field_name not in tool_input:
                errors.append(f"[VALIDATION] file_write requires '{field_name}' field")
        if "path" in tool_input:
            if ".." in tool_input["path"] or tool_input["path"].startswith("/"):
                errors.append("[VALIDATION] file_write.path must be relative and safe")

    elif tool_name == "assert_claim":
        if "claim" not in tool_input:
            errors.append("[VALIDATION] assert_claim requires 'claim' field")
        claim = tool_input.get("claim", {})
        for key in ("subject", "relation", "object"):
            if key not in claim:
                errors.append(f"[VALIDATION] assert_claim.claim missing '{key}'")

    elif tool_name == "verify_claim":
        if "claim" not in tool_input:
            errors.append("[VALIDATION] verify_claim requires 'claim' field")

    else:
        errors.append(f"[VALIDATION] unknown tool: {tool_name}")

    return errors


def validate_tool_output(tool_name: str, tool_output: dict[str, Any]) -> list[str]:
    """
    Validate tool output against expected schema.

    Returns list of error strings (empty = valid).
    """
    errors: list[str] = []

    if tool_name == "vcse_query":
        if "answer" not in tool_output:
            errors.append("[VALIDATION] vcse_query output missing 'answer'")
        if "status" not in tool_output:
            errors.append("[VALIDATION] vcse_query output missing 'status'")

    elif tool_name == "math_solver":
        if "result" not in tool_output:
            errors.append("[VALIDATION] math_solver output missing 'result'")

    elif tool_name == "file_read":
        if "content" not in tool_output:
            errors.append("[VALIDATION] file_read output missing 'content'")

    elif tool_name == "file_write":
        if "written" not in tool_output:
            errors.append("[VALIDATION] file_write output missing 'written'")

    elif tool_name == "assert_claim":
        if "verified" not in tool_output:
            errors.append("[VALIDATION] assert_claim output missing 'verified'")

    elif tool_name == "verify_claim":
        if "verified" not in tool_output:
            errors.append("[VALIDATION] verify_claim output missing 'verified'")

    return errors