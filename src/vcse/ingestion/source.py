"""Source document models for ingestion."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SourceLoadError(ValueError):
    def __init__(self, error_type: str, reason: str) -> None:
        super().__init__(f"{error_type}: {reason}")
        self.error_type = error_type
        self.reason = reason


@dataclass
class SourceDocument:
    id: str
    source_type: str
    path_or_uri: str
    content: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    loaded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def build_source_id(path: Path, source_type: str) -> str:
    token = f"{path.resolve()}::{source_type}"
    return f"src:{hashlib.sha1(token.encode('utf-8')).hexdigest()[:12]}"
