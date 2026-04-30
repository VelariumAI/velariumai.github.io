"""Tool system with strict schema validation."""

from __future__ import annotations

import ast
from typing import Any, Callable

from vcse.agent.errors import UnknownToolError, ToolValidationError
from vcse.agent.task import Result, ResultStatus
from vcse.agent.validation import validate_tool_input, validate_tool_output


# Tool signature: (input_dict) -> output_dict
ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


class ToolRegistry:
    """
    Registry of validated tools with schema enforcement.

    All tools must be registered with input/output schemas.
    Execution validates input before calling and output after.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolHandler] = {}
        self._input_validators: dict[str, Callable[[dict[str, Any]], list[str]]] = {}
        self._output_validators: dict[str, Callable[[dict[str, Any]], list[str]]] = {}

    def register(
        self,
        name: str,
        handler: ToolHandler,
        input_validator: Callable[[dict[str, Any]], list[str]] | None = None,
        output_validator: Callable[[dict[str, Any]], list[str]] | None = None,
    ) -> None:
        self._tools[name] = handler
        self._input_validators[name] = input_validator or (lambda _: [])
        self._output_validators[name] = output_validator or (lambda _: [])

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool with full validation."""
        if tool_name not in self._tools:
            raise UnknownToolError("UNKNOWN_TOOL", f"tool not registered: {tool_name}")

        # Validate input — skip for custom tools (custom validators handle their own schema)
        if tool_name in self._input_validators and self._input_validators[tool_name] is not None:
            errors = self._input_validators[tool_name](tool_input)
        else:
            errors = validate_tool_input(tool_name, tool_input)
        if errors:
            raise ToolValidationError("INVALID_INPUT", "; ".join(errors))

        # Execute
        handler = self._tools[tool_name]
        try:
            output = handler(tool_input)
        except Exception as exc:
            raise ToolValidationError("TOOL_ERROR", f"tool execution failed: {exc}")

        # Validate output — skip for custom tools
        if tool_name in self._output_validators and self._output_validators[tool_name] is not None:
            output_errors = self._output_validators[tool_name](output)
        else:
            output_errors = validate_tool_output(tool_name, output)
        if output_errors:
            raise ToolValidationError("INVALID_OUTPUT", "; ".join(output_errors))

        return output


# Global registry
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_default_tools(_registry)
    return _registry


# ─── Tool Implementations ────────────────────────────────────────────────────


def _handle_vcse_query(inp: dict[str, Any]) -> dict[str, Any]:
    """Query VCSE knowledge base."""
    query = inp["query"].strip()

    # Use VCSE engine to answer the query
    from vcse.engine import build_search, state_from_case
    from vcse.memory.relations import RelationSchema
    from vcse.memory.world_state import TruthStatus, WorldStateMemory

    state = WorldStateMemory()
    state.add_relation_schema(RelationSchema(name="is_a", transitive=True))

    # Load facts from query context (via inputs if available)
    facts = inp.get("facts", [])
    for fact in facts:
        subject = str(fact.get("subject", ""))
        relation = str(fact.get("relation", "is_a"))
        obj = str(fact.get("object", ""))
        if subject and obj:
            state.add_claim(subject, relation, obj, TruthStatus.ASSERTED)

    # Set up goal
    goal_data = inp.get("goal", {})
    if goal_data:
        state.add_goal(
            str(goal_data.get("subject", "")),
            str(goal_data.get("relation", "")),
            str(goal_data.get("object", "")),
        )

    search = build_search(enable_ts3=False, search_backend="beam")
    result = search.run(state)

    if result and result.evaluation:
        status_str = result.evaluation.status.value
        answer = f"{status_str}: {result.evaluation.answer or status_str}"
        status = status_str
    elif result:
        answer = "FAILURE: reasoning did not complete"
        status = "FAILURE"
    else:
        answer = "FAILURE: no result returned"
        status = "FAILURE"

    return {"answer": answer, "status": status}


def _handle_math_solver(inp: dict[str, Any]) -> dict[str, Any]:
    """Solve a mathematical expression."""
    expression = inp["expression"].strip()

    # Restrict to safe subset: integers, +, -, *, /, (), numbers, spaces
    safe_chars = set("0123456789 +-*/().")
    if not all(c in safe_chars for c in expression):
        raise ValueError(f"unsafe expression: {expression}")

    try:
        tree = ast.parse(expression, mode="eval")
        result = eval(compile(tree, "<expr>", "eval"))
    except Exception as exc:
        raise ValueError(f"math evaluation failed: {exc}")

    return {"result": result}


def _handle_file_read(inp: dict[str, Any]) -> dict[str, Any]:
    """Read a file (restricted to project-relative paths only)."""
    from pathlib import Path

    path_str = inp["path"]
    if ".." in path_str or path_str.startswith("/"):
        raise PermissionError("unsafe path: must be relative and below project root")

    root = Path.cwd()
    full_path = (root / path_str).resolve()

    # Must be within cwd
    try:
        full_path.relative_to(root)
    except ValueError:
        raise PermissionError(f"path outside project root: {path_str}")

    if not full_path.exists():
        raise FileNotFoundError(f"file not found: {path_str}")

    try:
        content = full_path.read_text()
    except Exception as exc:
        raise IOError(f"read failed: {exc}")

    return {"content": content}


def _handle_file_write(inp: dict[str, Any]) -> dict[str, Any]:
    """Write to a file (restricted to project-relative paths only)."""
    from pathlib import Path

    path_str = inp["path"]
    if ".." in path_str or path_str.startswith("/"):
        raise PermissionError("unsafe path: must be relative")

    root = Path.cwd()
    full_path = (root / path_str).resolve()

    try:
        full_path.relative_to(root)
    except ValueError:
        raise PermissionError(f"path outside project root: {path_str}")

    content = inp.get("content", "")
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
    except Exception as exc:
        raise IOError(f"write failed: {exc}")

    return {"written": True, "path": path_str}


def _handle_assert_claim(inp: dict[str, Any]) -> dict[str, Any]:
    """Assert a claim in the VCSE knowledge base."""
    claim = inp["claim"]
    subject = str(claim.get("subject", ""))
    relation = str(claim.get("relation", "is_a"))
    obj = str(claim.get("object", ""))

    if not subject or not obj:
        return {"verified": False, "error": "claim missing subject or object"}

    from vcse.engine import build_search
    from vcse.memory.relations import RelationSchema
    from vcse.memory.world_state import TruthStatus, WorldStateMemory

    state = WorldStateMemory()
    state.add_relation_schema(RelationSchema(name="is_a", transitive=True))
    state.add_claim(subject, relation, obj, TruthStatus.ASSERTED)
    state.add_goal(subject, relation, obj)

    search = build_search(enable_ts3=False, search_backend="beam")
    result = search.run(state)

    verified = bool(result and result.evaluation and result.evaluation.status.value == "VERIFIED")
    return {"verified": verified}


def _handle_verify_claim(inp: dict[str, Any]) -> dict[str, Any]:
    """Verify a claim using VCSE reasoning."""
    claim = inp["claim"]
    subject = str(claim.get("subject", ""))
    relation = str(claim.get("relation", "is_a"))
    obj = str(claim.get("object", ""))

    if not subject or not obj:
        return {"verified": False, "error": "claim missing subject or object"}

    from vcse.engine import build_search
    from vcse.memory.relations import RelationSchema
    from vcse.memory.world_state import TruthStatus, WorldStateMemory

    state = WorldStateMemory()
    state.add_relation_schema(RelationSchema(name="is_a", transitive=True))

    # Load all known facts from inputs (via related claims)
    for fact in inp.get("facts", []):
        s = str(fact.get("subject", ""))
        r = str(fact.get("relation", "is_a"))
        o = str(fact.get("object", ""))
        if s and o:
            state.add_claim(s, r, o, TruthStatus.ASSERTED)

    state.add_claim(subject, relation, obj, TruthStatus.UNKNOWN)
    state.add_goal(subject, relation, obj)

    search = build_search(enable_ts3=False, search_backend="beam")
    result = search.run(state)

    verified = bool(result and result.evaluation and result.evaluation.status.value == "VERIFIED")
    return {"verified": verified}


def _register_default_tools(reg: ToolRegistry) -> None:
    reg.register("vcse_query", _handle_vcse_query)
    reg.register("math_solver", _handle_math_solver)
    reg.register("file_read", _handle_file_read)
    reg.register("file_write", _handle_file_write)
    reg.register("assert_claim", _handle_assert_claim)
    reg.register("verify_claim", _handle_verify_claim)