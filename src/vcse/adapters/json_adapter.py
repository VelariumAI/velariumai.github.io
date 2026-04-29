"""JSON source adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vcse.adapters.base import SourceAdapter


class JSONAdapter(SourceAdapter):
    def load(self, path: Path) -> list[dict]:
        try:
            payload = json.loads(Path(path).read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(f"MALFORMED_JSON: {exc.msg}") from exc
        if not isinstance(payload, list):
            raise ValueError("INVALID_JSON: root must be a list of objects")
        rows: list[dict] = []
        for idx, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"INVALID_JSON: row {idx} must be an object")
            rows.append(item)
        return rows

    def normalize(self, raw_records: list[dict]) -> list[dict]:
        return _normalize_records(raw_records)


def _normalize_records(raw_records: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for idx, record in enumerate(raw_records, start=1):
        row = {str(key): _normalize_value(value) for key, value in record.items()}
        current_id = row.get("id")
        if current_id is None or str(current_id).strip() == "":
            row["id"] = f"row_{idx}"
        else:
            row["id"] = str(current_id).strip()
        normalized.append(row)
    return normalized


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        trimmed = value.strip()
        return None if trimmed == "" else trimmed
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _normalize_value(v) for k, v in value.items()}
    return value
