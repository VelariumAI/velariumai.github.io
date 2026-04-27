"""Reports for ReasonOps analysis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vcse.reasonops.failure_record import FailureRecord


def generate_report(failures_path: str | Path) -> str:
    """Generate a text report from failure log."""
    failures: list[FailureRecord] = []
    path = Path(failures_path)

    if path.exists():
        with open(path) as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        failures.append(FailureRecord.from_dict(data))
                    except json.JSONDecodeError:
                        continue

    if not failures:
        return "No failures recorded."

    # Count by type
    type_counts: dict[str, int] = {}
    severity_counts: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    missing_patterns: list[str] = []
    missing_relations: list[str] = []

    for failure in failures:
        ft = failure.failure_type.value
        type_counts[ft] = type_counts.get(ft, 0) + 1
        severity_counts[failure.severity] = severity_counts.get(failure.severity, 0) + 1

        if failure.failure_type.value == "MISSING_PATTERN":
            missing_patterns.append(failure.input_text)
        if failure.missing_component:
            missing_relations.append(failure.missing_component)

    # Build report
    lines = [
        "ReasonOps Failure Report",
        "=" * 40,
        f"Total failures: {len(failures)}",
        "",
        "By Failure Type:",
    ]

    for ft, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {ft}: {count}")

    lines.extend(["", "By Severity:"])
    for sev in [5, 4, 3, 2, 1]:
        count = severity_counts.get(sev, 0)
        if count > 0:
            lines.append(f"  {sev}/5: {count}")

    if missing_patterns:
        unique_patterns = list(set(missing_patterns))[:10]
        lines.extend(["", "Top Missing Patterns:"])
        for p in unique_patterns:
            lines.append(f"  - {p}")

    if missing_relations:
        unique_relations = list(set(missing_relations))[:10]
        lines.extend(["", "Top Missing Components:"])
        for r in unique_relations:
            lines.append(f"  - {r}")

    return "\n".join(lines)
