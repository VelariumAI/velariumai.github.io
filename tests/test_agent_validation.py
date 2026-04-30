"""Tests for agent validation layer."""

from vcse.agent.task import Task, Step
from vcse.agent.validation import validate_task, validate_step, validate_tool_input, validate_tool_output


def test_validate_task_valid():
    t = Task(id="t1", description="test task", inputs={}, goal={"subject": "x", "relation": "is_a", "object": "y"})
    errors = validate_task(t)
    assert len(errors) == 0


def test_validate_task_missing_id():
    t = Task(id="", description="test task", inputs={}, goal={"subject": "x"})
    errors = validate_task(t)
    assert any("id" in e for e in errors)


def test_validate_task_missing_goal():
    t = Task(id="t1", description="test task", inputs={}, goal={})
    errors = validate_task(t)
    # Empty dict goal is valid (agent tasks may not need a structured goal)
    assert len(errors) == 0


def test_validate_step_valid():
    s = Step(id="s1", type="tool", tool_name="vcse_query", inputs={"query": "test"})
    errors = validate_step(s)
    assert len(errors) == 0


def test_validate_step_missing_tool_name():
    s = Step(id="s1", type="tool", tool_name=None, inputs={})
    errors = validate_step(s)
    assert len(errors) > 0


def test_validate_step_invalid_type():
    s = Step(id="s1", type="invalid_type_!", tool_name="vcse_query", inputs={})
    errors = validate_step(s)
    assert len(errors) > 0


def test_validate_tool_input_vcse_query_valid():
    errors = validate_tool_input("vcse_query", {"query": "Can Socrates die?"})
    assert len(errors) == 0


def test_validate_tool_input_vcse_query_missing():
    errors = validate_tool_input("vcse_query", {})
    assert len(errors) > 0


def test_validate_tool_input_math_solver_valid():
    errors = validate_tool_input("math_solver", {"expression": "2 + 2"})
    assert len(errors) == 0


def test_validate_tool_input_math_solver_missing():
    errors = validate_tool_input("math_solver", {})
    assert len(errors) > 0


def test_validate_tool_input_unknown_tool():
    errors = validate_tool_input("nonexistent_tool", {"foo": "bar"})
    assert len(errors) > 0


def test_validate_tool_output_vcse_query_valid():
    errors = validate_tool_output("vcse_query", {"answer": "VERIFIED", "status": "VERIFIED"})
    assert len(errors) == 0


def test_validate_tool_output_vcse_query_missing_fields():
    errors = validate_tool_output("vcse_query", {"answer": "VERIFIED"})
    assert len(errors) > 0


def test_validate_tool_output_math_solver_valid():
    errors = validate_tool_output("math_solver", {"result": 42})
    assert len(errors) == 0


def test_validate_tool_input_file_read_safe():
    errors = validate_tool_input("file_read", {"path": "src/vcse/main.py"})
    assert len(errors) == 0


def test_validate_tool_input_file_read_unsafe_absolute():
    errors = validate_tool_input("file_read", {"path": "/etc/passwd"})
    assert len(errors) > 0


def test_validate_tool_input_file_read_unsafe_parent():
    errors = validate_tool_input("file_read", {"path": "../../../etc/passwd"})
    assert len(errors) > 0