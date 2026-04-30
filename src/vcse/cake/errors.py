"""CAKE error hierarchy."""

from __future__ import annotations


class CakeError(ValueError):
    """Base error for all CAKE failures."""

    def __init__(self, error_type: str, reason: str) -> None:
        super().__init__(f"{error_type}: {reason}")
        self.error_type = error_type
        self.reason = reason


class CakeConfigError(CakeError):
    """Invalid or missing source configuration."""


class CakeTransportError(CakeError):
    """Transport failure (file not found, domain blocked, HTTP disabled)."""


class CakeSnapshotCorruptedError(CakeError):
    """Snapshot hash does not match stored content."""


class CakeExtractionError(CakeError):
    """Extractor failed to parse source data."""


class CakePipelineError(CakeError):
    """Pipeline step failed; acquisition aborted."""
