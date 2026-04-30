"""CSV source adapter."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from vcse.adapters.base import SourceAdapter
from vcse.adapters.json_adapter import _normalize_value


class CSVAdapter(SourceAdapter):
    def load(self, path: Path) -> list[dict]:
        with Path(path).open(newline="") as handle:
            reader = csv.DictReader(handle)
            rows = [dict(row) for row in reader]
        return rows

    def normalize(self, raw_records: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        for idx, record in enumerate(raw_records, start=1):
            row: dict[str, Any] = {str(key): _normalize_value(value) for key, value in record.items()}
            row["id"] = f"row_{idx}"
            normalized.append(row)
        return normalized
