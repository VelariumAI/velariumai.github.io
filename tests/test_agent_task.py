"""Tests for agent task models."""

from vcse.agent.task import (
    ExecutionState,
    ExecutionStatus,
    Plan,
    Result,
    ResultStatus,
    Step,
    StepStatus,
    Task,
)


def test_task_to_dict_roundtrip():
    t = Task(id="t1", description="test", inputs={"a": 1}, goal={"b": 2})
    d = t.to_dict()
    t2 = Task.from_dict(d)
    assert t2.id == t.id
    assert t2.description == t.description
    assert t2.inputs == t.inputs
    assert t2.goal == t.goal


def test_task_from_dict_defaults():
    t = Task.from_dict({"id": "t1", "description": "desc", "inputs": {}, "goal": {"x": 1}})
    assert t.id == "t1"
    assert t.created_at != ""


def test_step_status_enum():
    for status in StepStatus:
        s = Step(id="s1", type="tool", tool_name="test", status=status)
        assert s.status == status


def test_plan_to_dict():
    p = Plan(
        task_id="t1",
        steps=(
            Step(id="s1", type="tool", tool_name="vcse_query", inputs={"query": "test"}),
            Step(id="s2", type="tool", tool_name="math_solver", inputs={"expression": "1+1"}),
        ),
    )
    d = p.to_dict()
    p2 = Plan.from_dict(d)
    assert len(p2.steps) == 2
    assert p2.task_id == "t1"


def test_execution_state_to_dict():
    state = ExecutionState(
        task_id="t1",
        current_step=2,
        completed_steps=["s1", "s2"],
        results={"s1": {"answer": "test"}},
        status=ExecutionStatus.RUNNING,
    )
    d = state.to_dict()
    state2 = ExecutionState.from_dict(d)
    assert state2.current_step == 2
    assert state2.task_id == "t1"


def test_result_status_enum():
    for status in ResultStatus:
        r = Result(status=status, data={})
        assert r.status == status


def test_result_with_error():
    r = Result(status=ResultStatus.FAILURE, data={}, error="something went wrong")
    assert r.error == "something went wrong"
    assert r.status == ResultStatus.FAILURE