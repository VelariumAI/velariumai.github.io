"""Tests for agent executor."""

from vcse.agent import run_task, execute_plan, execute_step, Task, Plan, ExecutionState
from vcse.agent.state import StateManager
from vcse.agent.task import Step, StepStatus


def test_execute_step_valid():
    step = Step(id="s1", type="tool", tool_name="math_solver", inputs={"expression": "3 + 5"})
    state = ExecutionState(task_id="t1")
    updated_step, new_state = execute_step(step, state)
    assert updated_step.status == StepStatus.COMPLETED
    assert new_state.current_step == 1


def test_execute_step_invalid_tool():
    step = Step(id="s1", type="tool", tool_name="nonexistent_xyz", inputs={})
    state = ExecutionState(task_id="t1")
    try:
        execute_step(step, state)
        assert False, "should raise"
    except Exception:
        pass


def test_execute_plan_success():
    plan = Plan(
        task_id="t1",
        steps=(
            Step(id="s1", type="tool", tool_name="math_solver", inputs={"expression": "10 - 4"}),
            Step(id="s2", type="tool", tool_name="math_solver", inputs={"expression": "6 + 1"}),
        ),
    )
    final_plan, final_state = execute_plan(plan)
    assert final_state.status.value in ("COMPLETED", "RUNNING")
    assert len(final_state.completed_steps) >= 1


def test_execute_plan_stops_on_failure():
    plan = Plan(
        task_id="t1",
        steps=(
            Step(id="s1", type="tool", tool_name="nonexistent_xyz", inputs={}),
            Step(id="s2", type="tool", tool_name="math_solver", inputs={"expression": "1+1"}),
        ),
    )
    final_plan, final_state = execute_plan(plan)
    assert final_state.status.value == "FAILED"


def test_run_task_full():
    task = Task(
        id="task_001",
        description="Calculate 7 * 6",
        inputs={"expression": "7 * 6"},
        goal={},
    )
    t, plan, state = run_task(task)
    assert state.task_id == "task_001"
    assert len(plan.steps) == 1


def test_run_task_vcse_query():
    task = Task(
        id="task_002",
        description="Can Socrates die?",
        inputs={"facts": [{"subject": "socrates", "relation": "is_a", "object": "man"}, {"subject": "man", "relation": "is_a", "object": "mortal"}]},
        goal={"subject": "socrates", "relation": "is_a", "object": "mortal"},
    )
    t, plan, state = run_task(task)
    assert state.task_id == "task_002"
    assert len(plan.steps) >= 1


def test_state_manager_update():
    state = ExecutionState(task_id="t1", current_step=0)
    step = Step(
        id="s1",
        type="tool",
        tool_name="math_solver",
        inputs={"expression": "1+1"},
        status=StepStatus.COMPLETED,
        result={"result": 2},
    )
    new_state = StateManager.update(state, step)
    assert new_state.current_step == 1
    assert "s1" in new_state.completed_steps
    assert "result" in new_state.results.get("s1", {})


def test_execute_plan_empty_steps():
    plan = Plan(task_id="t1", steps=())
    final_plan, final_state = execute_plan(plan)
    assert final_state.task_id == "t1"