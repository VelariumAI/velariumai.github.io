"""Base source adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class SourceAdapter(ABC):
    @abstractmethod
    def load(self, path: Path) -> list[dict]:
        """Parse source input into raw records."""

    @abstractmethod
    def normalize(self, raw_records: list[dict]) -> list[dict]:
        """Shape raw records into normalized records."""

    def run(self, path: Path) -> list[dict]:
        raw = self.load(path)
        return self.normalize(raw)
