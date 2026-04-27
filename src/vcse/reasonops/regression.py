"""Regression checking for ReasonOps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vcse.reasonops.failure_record import FailureRecord


class RegressionChecker:
    """Check for regressions in benchmark performance."""

    def __init__(self, baseline_path: str | Path | None = None) -> None:
        """Initialize with optional baseline."""
        self.baseline: dict[str, Any] = {}
        if baseline_path:
            self.load_baseline(Path(baseline_path))

    def load_baseline(self, path: Path) -> None:
        """Load baseline metrics from JSON file."""
        if path.exists():
            with open(path) as f:
                self.baseline = json.load(f)

    def check(
        self,
        current: dict[str, Any],
        failures: list[FailureRecord],
    ) -> list[str]:
        """Check for regressions. Returns list of regressions found."""
        regressions = []

        # Check benchmark accuracy
        if self.baseline:
            baseline_acc = self.baseline.get("accuracy", 1.0)
            current_acc = current.get("accuracy", 1.0)
            if current_acc < baseline_acc - 0.05:  # 5% tolerance
                regressions.append(
                    f"Accuracy regressed: {baseline_acc:.2f} -> {current_acc:.2f}"
                )

        # Check failure types
        severity_counts: dict[str, int] = {}
        for failure in failures:
            ft = failure.failure_type.value
            severity_counts[ft] = severity_counts.get(ft, 0) + 1

        baseline_failures = self.baseline.get("failure_types", {})
        for ft, count in severity_counts.items():
            baseline_count = baseline_failures.get(ft, 0)
            if count > baseline_count + 2:  # Allow small variance
                regressions.append(
                    f"Failure type increased: {ft} {baseline_count} -> {count}"
                )

        return regressions
