"""JSONL source adapter."""

from __future__ import annotations

import json
from pathlib import Path

from vcse.adapters.base import SourceAdapter
from vcse.adapters.json_adapter import _normalize_records


class JSONLAdapter(SourceAdapter):
    def load(self, path: Path) -> list[dict]:
        rows: list[dict] = []
        for idx, line in enumerate(Path(path).read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"MALFORMED_JSONL: line {idx}: {exc.msg}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"INVALID_JSONL: line {idx} must be an object")
            rows.append(item)
        return rows

    def normalize(self, raw_records: list[dict]) -> list[dict]:
        return _normalize_records(raw_records)
