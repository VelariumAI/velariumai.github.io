"""Tests for ReasonOps logging."""

import json
import tempfile
from pathlib import Path

import pytest
from vcse.reasonops.failure_record import FailureRecord, FailureType
from vcse.reasonops.logger import ReasonOpsLogger
from vcse.reasonops.reports import generate_report


def test_failure_record_create():
    record = FailureRecord.create(
        input_text="test input",
        normalized_text="test normalized",
        parse_status="FAILED",
        failure_type=FailureType.PARSE_FAILURE,
        actual_behavior="crash",
    )
    assert record.input_text == "test input"
    assert record.failure_type == FailureType.PARSE_FAILURE


def test_failure_record_to_dict():
    record = FailureRecord.create(
        input_text="test",
        normalized_text="test",
        parse_status="PARSED",
        failure_type=FailureType.MISSING_PATTERN,
    )
    d = record.to_dict()
    assert d["input_text"] == "test"
    assert d["failure_type"] == "MISSING_PATTERN"


def test_failure_record_from_dict():
    data = {
        "id": "test123",
        "timestamp": "2024-01-01T00:00:00",
        "input_text": "test",
        "normalized_text": "test",
        "parse_status": "PARSED",
        "failure_type": "MISSING_PATTERN",
        "expected_behavior": None,
        "actual_behavior": "",
        "missing_component": "",
        "suggested_fix": "",
        "severity": 1,
    }
    record = FailureRecord.from_dict(data)
    assert record.id == "test123"
    assert record.failure_type == FailureType.MISSING_PATTERN


def test_logger_write():
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        path = Path(f.name)

    logger = ReasonOpsLogger(path)
    record = FailureRecord.create(
        input_text="test",
        normalized_text="test",
        parse_status="FAILED",
        failure_type=FailureType.PARSE_FAILURE,
    )
    logger.log(record)
    logger.close()

    with open(path) as f:
        lines = f.readlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["input_text"] == "test"


def test_generate_report():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
        path = Path(f.name)
        record = FailureRecord.create(
            input_text="test input",
            normalized_text="test",
            parse_status="FAILED",
            failure_type=FailureType.MISSING_PATTERN,
            severity=3,
        )
        f.write(json.dumps(record.to_dict()) + "\n")

    report = generate_report(path)
    assert "ReasonOps Failure Report" in report
    assert "MISSING_PATTERN" in report
    path.unlink()
