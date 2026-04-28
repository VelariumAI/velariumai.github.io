"""Safety tests: ensure no LLM/neural dependencies in core implementation."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


FORBIDDEN_IMPORTS = {
    "openai",
    "anthropic",
    "llama",
    "transformer",
    "transformers",
    "neural",
    "llm",
    "large_language_model",
    "autoregressive",
    "next_token",
    "embedding_model",
    "torch",
    "tensorflow",
    "sentence_transformers",
    "langchain",
    "llamaindex",
}

FORBIDDEN_TERMS = {
    "openai.",
    "anthropic.",
    "llama.",
    "transformer",
    "autoregressive",
    "next_token_prediction",
    "embedding_model",
}


def test_no_forbidden_imports():
    """Verify no forbidden packages in source."""
    src_path = Path(__file__).parent.parent.parent / "src"
    errors = []

    for py_file in src_path.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        try:
            content = py_file.read_text()
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.name.split(".")[0].lower()
                        if name in FORBIDDEN_IMPORTS:
                            errors.append(f"{py_file}: forbidden import '{name}'")
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        name = node.module.split(".")[0].lower()
                        if name in FORBIDDEN_IMPORTS:
                            errors.append(f"{py_file}: forbidden from '{node.module}'")
        except SyntaxError:
            continue

    error_text = "\n".join(errors)
    assert not errors, f"Forbidden imports found:\n{error_text}"


def test_no_forbidden_terms_in_files():
    """Verify no forbidden terms in proposer/parser/renderer files."""
    src_path = Path(__file__).parent.parent.parent / "src"
    files_to_check = [
        "proposer",
        "parser",
        "renderer",
        "interaction",
    ]
    errors = []

    for dir_name in files_to_check:
        dir_path = src_path / dir_name
        if not dir_path.exists():
            continue
        for py_file in dir_path.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            content = py_file.read_text().lower()
            for term in FORBIDDEN_TERMS:
                if term.lower() in content:
                    errors.append(f"{py_file}: forbidden term '{term}'")

    joined_errors = "\n".join(errors)
    assert not errors, f"Forbidden terms found:\n{joined_errors}"


def test_pyproject_no_forbidden_deps():
    """Verify pyproject.toml has no forbidden dependencies."""
    project_path = Path(__file__).parent.parent / "pyproject.toml"
    content = project_path.read_text().lower()

    for forbidden in FORBIDDEN_IMPORTS:
        assert forbidden not in content, f"pyproject.toml contains forbidden dep: {forbidden}"
