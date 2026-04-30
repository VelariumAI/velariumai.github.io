"""Agent errors."""

from __future__ import annotations


class AgentError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class ValidationError(AgentError):
    """Task/step/tool input fails schema validation."""
    pass


class UnknownToolError(AgentError):
    """Tool name not found in registry."""
    pass


class ToolValidationError(AgentError):
    """Tool output does not match schema."""
    pass


class PlanningError(AgentError):
    """Task cannot be planned."""
    pass


class ExecutionError(AgentError):
    """Step execution failed."""
    pass


class StateError(AgentError):
    """ExecutionState update failed."""
    pass


class LedgerError(AgentError):
    """Ledger logging failed."""
    pass