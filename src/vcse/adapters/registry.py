"""Source adapter registry."""

from __future__ import annotations

from vcse.adapters.base import SourceAdapter
from vcse.adapters.csv_adapter import CSVAdapter
from vcse.adapters.json_adapter import JSONAdapter
from vcse.adapters.jsonl_adapter import JSONLAdapter

ADAPTERS: dict[str, SourceAdapter] = {
    "json": JSONAdapter(),
    "jsonl": JSONLAdapter(),
    "csv": CSVAdapter(),
}


def get_adapter(adapter_type: str) -> SourceAdapter:
    key = str(adapter_type).strip().lower()
    if key not in ADAPTERS:
        raise ValueError(f"UNKNOWN_ADAPTER: {adapter_type}")
    return ADAPTERS[key]
