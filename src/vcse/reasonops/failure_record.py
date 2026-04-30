"""Failure record for ReasonOps logging."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class FailureType(Enum):
    """Categories of failures."""
    PARSE_FAILURE = "PARSE_FAILURE"
    AMBIGUOUS_INPUT = "AMBIGUOUS_INPUT"
    MISSING_SYNONYM = "MISSING_SYNONYM"
    MISSING_PATTERN = "MISSING_PATTERN"
    MISSING_DOMAIN_RULE = "MISSING_DOMAIN_RULE"
    MISSING_VERIFIER = "MISSING_VERIFIER"
    SEARCH_LIMIT_REACHED = "SEARCH_LIMIT_REACHED"
    CONTRADICTION = "CONTRADICTION"
    UNSUPPORTED_QUERY = "UNSUPPORTED_QUERY"
    RENDERING_FAILURE = "RENDERING_FAILURE"


@dataclass
class FailureRecord:
    """A record of a reasoning failure for later analysis."""
    id: str
    timestamp: str
    input_text: str
    normalized_text: str
    parse_status: str
    failure_type: FailureType
    expected_behavior: str | None = None
    actual_behavior: str = ""
    missing_component: str = ""
    suggested_fix: str = ""
    severity: int = 1  # 1-5, 5 being most severe

    @classmethod
    def create(
        cls,
        input_text: str,
        normalized_text: str,
        parse_status: str,
        failure_type: FailureType,
        actual_behavior: str = "",
        missing_component: str = "",
        suggested_fix: str = "",
        severity: int = 1,
        expected_behavior: str | None = None,
    ) -> "FailureRecord":
        """Create a new failure record."""
        import uuid
        return cls(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.utcnow().isoformat(),
            input_text=input_text,
            normalized_text=normalized_text,
            parse_status=parse_status,
            failure_type=failure_type,
            expected_behavior=expected_behavior,
            actual_behavior=actual_behavior,
            missing_component=missing_component,
            suggested_fix=suggested_fix,
            severity=severity,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "input_text": self.input_text,
            "normalized_text": self.normalized_text,
            "parse_status": self.parse_status,
            "failure_type": self.failure_type.value,
            "expected_behavior": self.expected_behavior,
            "actual_behavior": self.actual_behavior,
            "missing_component": self.missing_component,
            "suggested_fix": self.suggested_fix,
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FailureRecord":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            input_text=data["input_text"],
            normalized_text=data["normalized_text"],
            parse_status=data["parse_status"],
            failure_type=FailureType(data["failure_type"]),
            expected_behavior=data.get("expected_behavior"),
            actual_behavior=data.get("actual_behavior", ""),
            missing_component=data.get("missing_component", ""),
            suggested_fix=data.get("suggested_fix", ""),
            severity=data.get("severity", 1),
        )
