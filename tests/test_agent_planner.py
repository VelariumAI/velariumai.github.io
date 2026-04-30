"""Tests for agent planner."""

from vcse.agent.planner import plan_task, _plan_task_from_template
from vcse.agent.task import Task


def test_plan_task_mortality():
    t = Task(
        id="mort_001",
        description="Can Socrates die?",
        inputs={"facts": [{"subject": "socrates", "relation": "is_a", "object": "man"}]},
        goal={"subject": "socrates", "relation": "is_a", "object": "mortal"},
    )
    plan = plan_task(t)
    assert len(plan.steps) >= 1
    assert plan.task_id == "mort_001"
    assert all(s.type == "tool" for s in plan.steps)


def test_plan_task_math():
    t = Task(
        id="math_001",
        description="Solve 2 + 2",
        inputs={"expression": "2 + 2"},
        goal={},
    )
    plan = plan_task(t)
    assert len(plan.steps) == 1
    assert plan.steps[0].tool_name == "math_solver"


def test_plan_task_verify():
    t = Task(
        id="verify_001",
        description="Verify something xyz unknown",
        inputs={"claim": {"subject": "socrates", "relation": "is_a", "object": "mortal"}},
        goal={},
    )
    plan = plan_task(t)
    assert len(plan.steps) == 1
    # "Verify" keyword maps to verify_claim tool
    assert plan.steps[0].tool_name == "verify_claim"


def test_plan_task_unknown_returns_inconclusive():
    t = Task(
        id="unknown_001",
        description="do something completely unrecognizable xyz123",
        inputs={},
        goal={},
    )
    plan = plan_task(t)
    # Should produce a step (even if inconclusive template)
    assert len(plan.steps) >= 1


def test_plan_task_invalid():
    from vcse.agent.errors import PlanningError
    t = Task(id="", description="", inputs={}, goal={})
    try:
        plan_task(t)
        assert False, "should raise"
    except PlanningError:
        pass


def test_plan_task_file_read():
    t = Task(
        id="read_001",
        description="Show contents of src/vcse/main.py",
        inputs={"path": "src/vcse/main.py"},
        goal={},
    )
    plan = plan_task(t)
    assert len(plan.steps) == 1
    assert plan.steps[0].tool_name == "file_read"


def test_plan_from_dict():
    t = Task(id="t1", description="Calculate 3 * 4", inputs={"expression": "3 * 4"}, goal={})
    plan = plan_task(t)
    plan_dict = plan.to_dict()
    from vcse.agent.task import Plan
    plan2 = Plan.from_dict(plan_dict)
    assert len(plan2.steps) == len(plan.steps)