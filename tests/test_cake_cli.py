"""Tests for CAKE CLI commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


def run_cli(args: list[str]) -> tuple[str, int]:
    """Run vcse CLI via main() and capture output."""
    from io import StringIO
    from contextlib import redirect_stdout, redirect_stderr
    from vcse.cli import main

    stdout_buf = StringIO()
    stderr_buf = StringIO()
    exit_code = 0
    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            main(args)
    except SystemExit as exc:
        exit_code = int(exc.code) if exc.code is not None else 0
    return stdout_buf.getvalue() + stderr_buf.getvalue(), exit_code


def test_cake_validate_valid_source():
    output, code = run_cli(["cake", "validate", "--source", "examples/cake/general_world_sources.json"])
    assert code == 0
    assert "VALID" in output


def test_cake_validate_malformed_source(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json")
    output, code = run_cli(["cake", "validate", "--source", str(bad)])
    assert code != 0


def test_cake_validate_disallowed_domain():
    output, code = run_cli(["cake", "validate", "--source", "examples/cake/disallowed_source.json"])
    assert code != 0
    assert "DISALLOWED_DOMAIN" in output or "ERROR" in output


def test_cake_run_dry_run(tmp_path):
    output, code = run_cli([
        "cake", "run",
        "--source", "examples/cake/general_world_sources.json",
        "--dry-run",
    ])
    assert code == 0
    data = json.loads(output)
    assert data["status"] == "CAKE_DRY_RUN"
    assert data["dry_run"] is True


def test_cake_run_with_limit(tmp_path):
    output, code = run_cli([
        "cake", "run",
        "--source", "examples/cake/general_world_sources.json",
        "--dry-run",
        "--limit", "1",
    ])
    assert code == 0
    data = json.loads(output)
    assert data["claims_extracted"] <= 2


def test_cake_run_live(tmp_path):
    output, code = run_cli([
        "cake", "run",
        "--source", "examples/cake/general_world_sources.json",
    ])
    assert code == 0
    data = json.loads(output)
    assert data["status"] in ("CAKE_COMPLETE", "CAKE_PARTIAL")
    assert data["claims_extracted"] > 0


def test_cake_run_missing_source(tmp_path):
    output, code = run_cli([
        "cake", "run",
        "--source", str(tmp_path / "nonexistent.json"),
    ])
    assert code != 0


def test_cake_report_cmd(tmp_path):
    """Write a report file, then read it back via vcse cake report."""
    report_data = {
        "run_id": "test-123",
        "status": "CAKE_COMPLETE",
        "source_ids": ["wikidata_capitals"],
        "snapshot_ids": ["wikidata_capitals/abc123"],
        "source_reports": [],
        "claims_extracted": 3,
        "claims_normalized": 3,
        "claims_ingested": 3,
        "trust_decisions": 3,
        "errors": [],
        "warnings": [],
        "dry_run": False,
        "timestamp": "2026-04-27T00:00:00+00:00",
    }
    report_file = tmp_path / "run_report.json"
    report_file.write_text(json.dumps(report_data))
    output, code = run_cli(["cake", "report", str(report_file)])
    assert code == 0
    assert "CAKE_COMPLETE" in output


def test_cake_run_without_allow_http_blocks_http_source(tmp_path):
    http_config = tmp_path / "http_sources.json"
    http_config.write_text(json.dumps({
        "version": "1.0.0",
        "description": "http source",
        "sources": [{
            "id": "wd_live",
            "source_type": "http_static",
            "format": "wikidata_json",
            "path_or_url": "https://www.wikidata.org/wiki/Special:EntityData/Q90.json",
        }]
    }))
    output, code = run_cli([
        "cake", "run",
        "--source", str(http_config),
        "--dry-run",
        # No --allow-http
    ])
    # Should fail because HTTP is disabled
    assert code != 0 or "HTTP_DISABLED" in output or "CAKE_FAILED" in output