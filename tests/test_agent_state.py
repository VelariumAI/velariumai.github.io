"""Tests for agent state management."""

from vcse.agent.state import StateManager
from vcse.agent.task import ExecutionState, ExecutionStatus, Step, StepStatus


def test_state_manager_update_completed():
    state = ExecutionState(task_id="t1", current_step=0)
    step = Step(
        id="s1", type="tool", tool_name="math_solver",
        inputs={"expression": "1+1"},
        status=StepStatus.COMPLETED,
        result={"result": 2},
    )
    new_state = StateManager.update(state, step)
    assert new_state.current_step == 1
    assert len(new_state.completed_steps) == 1
    assert new_state.status == ExecutionStatus.RUNNING


def test_state_manager_update_failed():
    state = ExecutionState(task_id="t1", current_step=0)
    step = Step(
        id="s1", type="tool", tool_name="bad_tool",
        inputs={},
        status=StepStatus.FAILED,
        result={"error": "unknown tool"},
    )
    new_state = StateManager.update(state, step)
    assert new_state.status == ExecutionStatus.FAILED


def test_state_manager_advance():
    state = ExecutionState(task_id="t1", current_step=1)
    new_state = StateManager.advance(state)
    assert new_state.status == ExecutionStatus.BLOCKED


def test_state_manager_restore():
    data = {
        "task_id": "t1",
        "current_step": 2,
        "completed_steps": ["s1", "s2"],
        "results": {"s1": {"result": 1}},
        "status": "RUNNING",
    }
    state = StateManager.restore(data)
    assert state.current_step == 2
    assert len(state.completed_steps) == 2


def test_state_immutability():
    state = ExecutionState(task_id="t1", current_step=0)
    step = Step(id="s1", type="tool", tool_name="math_solver", inputs={"expression": "1+1"}, status=StepStatus.COMPLETED, result={"result": 2})
    new_state = StateManager.update(state, step)
    # Original state should not be mutated
    assert state.current_step == 0
    assert new_state.current_step == 1