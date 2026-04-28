"""Workspace isolation guards."""

from __future__ import annotations

from vcse.workspace.errors import IsolationViolation


def verify_workspace_id(workspace_id: str, expected: str | None) -> None:
    """Verify the workspace_id matches the expected workspace."""
    if not workspace_id:
        raise IsolationViolation("workspace_id is required")
    if expected and workspace_id != expected:
        raise IsolationViolation(
            f"workspace mismatch: got '{workspace_id}', expected '{expected}'"
        )


def validate_workspace_path(path: str, root: str) -> None:
    """Ensure a path is within the workspace root (no path traversal)."""
    import os.path
    real_path = os.path.realpath(path)
    real_root = os.path.realpath(root)
    if not real_path.startswith(real_root + os.sep) and real_path != real_root:
        raise IsolationViolation(f"path escape attempt: {path}")