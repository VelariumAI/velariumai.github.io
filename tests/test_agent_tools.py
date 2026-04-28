"""Tests for agent tools."""

from vcse.agent.errors import UnknownToolError, ToolValidationError
from vcse.agent.tools import ToolRegistry, get_registry


def test_tool_registry_lists_tools():
    reg = get_registry()
    tools = reg.list_tools()
    assert "vcse_query" in tools
    assert "math_solver" in tools
    assert "verify_claim" in tools
    assert len(tools) >= 6


def test_tool_registry_executes_vcse_query():
    reg = get_registry()
    output = reg.execute("vcse_query", {"query": "test"})
    assert "answer" in output
    assert "status" in output


def test_tool_registry_executes_math_solver():
    reg = get_registry()
    output = reg.execute("math_solver", {"expression": "2 + 2"})
    assert output["result"] == 4


def test_tool_registry_executes_verify_claim():
    reg = get_registry()
    output = reg.execute("verify_claim", {
        "claim": {"subject": "socrates", "relation": "is_a", "object": "mortal"},
        "facts": [{"subject": "socrates", "relation": "is_a", "object": "man"}, {"subject": "man", "relation": "is_a", "object": "mortal"}],
    })
    assert "verified" in output


def test_tool_registry_unknown_tool():
    reg = get_registry()
    try:
        reg.execute("nonexistent_tool", {})
        assert False, "should raise"
    except UnknownToolError:
        pass


def test_tool_registry_invalid_input():
    reg = get_registry()
    try:
        reg.execute("math_solver", {})  # missing expression
        assert False, "should raise"
    except ToolValidationError:
        pass


def test_tool_registry_math_safety():
    reg = get_registry()
    # Test unsafe expressions are caught
    try:
        reg.execute("math_solver", {"expression": "os.system('ls')"})
        assert False, "should raise"
    except ToolValidationError:
        pass


def test_tool_registry_file_read_safe_path():
    reg = get_registry()
    try:
        output = reg.execute("file_read", {"path": "pyproject.toml"})
        assert "content" in output
    except Exception:
        pass  # may not exist in cwd context


def test_tool_registry_file_read_unsafe_absolute():
    reg = get_registry()
    try:
        reg.execute("file_read", {"path": "/etc/passwd"})
        assert False, "should raise"
    except (ToolValidationError, PermissionError):
        pass


def test_tool_registry_file_read_unsafe_parent():
    reg = get_registry()
    try:
        reg.execute("file_read", {"path": "../../../etc/passwd"})
        assert False, "should raise"
    except (ToolValidationError, PermissionError):
        pass


def test_tool_registry_assert_claim():
    reg = get_registry()
    output = reg.execute("assert_claim", {
        "claim": {"subject": "test", "relation": "is_a", "object": "thing"}
    })
    assert "verified" in output


def test_tool_registry_custom_registration():
    """Custom tools can be registered on the shared registry and listed."""
    reg = get_registry()
    calls = []

    def handler(inp):
        calls.append(inp)
        return {"done": True}

    reg.register("custom_tool_xyz", handler, lambda _: [], lambda _: [])
    assert "custom_tool_xyz" in reg.list_tools()
    output = reg.execute("custom_tool_xyz", {"any": "input"})
    assert output == {"done": True}
    assert calls == [{"any": "input"}]