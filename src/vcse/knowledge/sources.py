"""Knowledge source definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Source:
    id: str
    type: str
    path: str
    trust_level: str = "unrated"
    update_frequency: str = "manual"
    schema_hint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_path(cls, path: str | Path, *, source_id: str | None = None) -> "Source":
        resolved = Path(path)
        suffix = resolved.suffix.lower()
        source_type = {
            ".json": "json",
            ".jsonl": "jsonl",
            ".csv": "csv",
            ".txt": "text",
            ".yaml": "yaml",
            ".yml": "yaml",
        }.get(suffix, "unknown")
        return cls(
            id=source_id or resolved.stem,
            type=source_type,
            path=str(resolved),
            schema_hint=None,
        )
