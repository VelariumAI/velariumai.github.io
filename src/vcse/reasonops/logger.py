"""ReasonOps logger for writing failure records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TextIO

from vcse.reasonops.failure_record import FailureRecord


class ReasonOpsLogger:
    """Write failure records to JSONL log files."""

    def __init__(self, path: str | Path | None = None) -> None:
        """Initialize logger with optional file path."""
        self.path = Path(path) if path else None
        self._stream: TextIO | None = None

    def open(self) -> None:
        """Open the log file for appending."""
        if self.path:
            self._stream = open(self.path, "a", encoding="utf-8")

    def close(self) -> None:
        """Close the log file."""
        if self._stream:
            self._stream.close()
            self._stream = None

    def log(self, record: FailureRecord) -> None:
        """Write a failure record."""
        line = json.dumps(record.to_dict(), ensure_ascii=False)
        if self._stream:
            self._stream.write(line + "\n")
            self._stream.flush()
        elif self.path:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def __enter__(self) -> "ReasonOpsLogger":
        """Context manager entry."""
        self.open()
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit."""
        self.close()
