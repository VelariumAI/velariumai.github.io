"""Tests for workspace isolation."""

import tempfile

from vcse.workspace.isolation import verify_workspace_id, validate_workspace_path
from vcse.workspace.errors import IsolationViolation


def test_verify_workspace_id_valid():
    verify_workspace_id("ws-001", expected="ws-001")  # no raise


def test_verify_workspace_id_mismatch():
    try:
        verify_workspace_id("ws-001", expected="ws-002")
        assert False, "should raise"
    except IsolationViolation:
        pass


def test_verify_workspace_id_empty():
    try:
        verify_workspace_id("", expected=None)
        assert False, "should raise"
    except IsolationViolation:
        pass


def test_validate_workspace_path_valid():
    with tempfile.TemporaryDirectory() as tmp:
        validate_workspace_path(tmp + "/ws/file.txt", tmp)  # no raise


def test_validate_workspace_path_escape():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            validate_workspace_path("/etc/passwd", tmp)
            assert False, "should raise"
        except IsolationViolation:
            pass


def test_validate_workspace_path_parent_traversal():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            validate_workspace_path(tmp + "/../../etc/passwd", tmp)
            assert False, "should raise"
        except IsolationViolation:
            pass