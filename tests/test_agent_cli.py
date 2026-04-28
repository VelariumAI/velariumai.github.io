"""Tests for agent CLI commands."""

import json
from pathlib import Path


def test_agent_plan_command(tmp_path):
    """vcse agent plan <task_file>"""
    import subprocess
    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps({
        "id": "plan_test",
        "description": "Calculate 5 + 3",
        "inputs": {"expression": "5 + 3"},
        "goal": {},
    }))
    result = subprocess.run(
        ["python", "-m", "vcse.cli", "agent", "plan", str(task_file)],
        capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "PLAN_CREATED" in result.stdout
    assert "step_count" in result.stdout


def test_agent_run_command(tmp_path):
    """vcse agent run <task_file>"""
    import subprocess
    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps({
        "id": "run_test",
        "description": "Calculate 9 - 4",
        "inputs": {"expression": "9 - 4"},
        "goal": {},
    }))
    result = subprocess.run(
        ["python", "-m", "vcse.cli", "agent", "run", str(task_file)],
        capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "status:" in result.stdout


def test_agent_plan_command_invalid_task(tmp_path):
    """vcse agent plan fails on invalid task"""
    import subprocess
    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps({
        "id": "",
        "description": "",
        "inputs": {},
        "goal": {},
    }))
    result = subprocess.run(
        ["python", "-m", "vcse.cli", "agent", "plan", str(task_file)],
        capture_output=True, text=True
    )
    assert result.returncode != 0


def test_agent_status_command():
    """vcse agent status <task_id>"""
    import subprocess
    result = subprocess.run(
        ["python", "-m", "vcse.cli", "agent", "status", "test_task_xyz"],
        capture_output=True, text=True
    )
    # Status always succeeds (in-memory state lookup)
    assert result.returncode == 0
    assert "UNKNOWN" in result.stdout


def test_agent_run_vcse_query_task(tmp_path):
    """vcse agent run with a VCSE query task"""
    import subprocess
    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps({
        "id": "query_test",
        "description": "Can Socrates die?",
        "inputs": {"facts": [{"subject": "socrates", "relation": "is_a", "object": "man"}, {"subject": "man", "relation": "is_a", "object": "mortal"}]},
        "goal": {"subject": "socrates", "relation": "is_a", "object": "mortal"},
    }))
    result = subprocess.run(
        ["python", "-m", "vcse.cli", "agent", "run", str(task_file)],
        capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_agent_plan_json_output(tmp_path):
    """vcse agent plan --json returns full plan"""
    import subprocess
    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps({
        "id": "json_test",
        "description": "Solve 2 + 2",
        "inputs": {"expression": "2 + 2"},
        "goal": {},
    }))
    result = subprocess.run(
        ["python", "-m", "vcse.cli", "agent", "plan", str(task_file), "--json"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    # With --json flag, last JSON block is the plan
    lines = result.stdout.strip().split("\n")
    json_part = lines[-1]
    payload = json.loads(json_part)
    assert "task_id" in payload
    assert "steps" in payload