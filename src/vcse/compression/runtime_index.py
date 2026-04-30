"""Compression-aware runtime claim lookup without full decompression."""

from __future__ import annotations

import json
import mmap
from pathlib import Path
from typing import Any


class CompressedRuntimeIndex:
    def __init__(self, pack_path: str | Path) -> None:
        self.root = Path(pack_path)
        intern_table_path = self.root / "intern_table.json"
        encoded_path = self.root / "encoded_claims.jsonl"
        if not intern_table_path.exists() or not encoded_path.exists():
            raise ValueError(f"invalid compressed pack at {self.root}")

        intern_table = json.loads(intern_table_path.read_text())
        self._string_to_id = {
            str(key): int(value) for key, value in intern_table.get("string_to_id", {}).items()
        }
        self._id_to_string = {
            int(key): str(value) for key, value in intern_table.get("id_to_string", {}).items()
        }
        self._encoded_path = encoded_path

    def _resolve(self, idx: int) -> str:
        return self._id_to_string.get(int(idx), "")

    def iter_claims(self) -> list[dict[str, str]]:
        claims: list[dict[str, str]] = []
        with self._encoded_path.open("rb") as fh:
            with mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                for raw in iter(mm.readline, b""):
                    line = raw.strip()
                    if not line:
                        continue
                    row = json.loads(line.decode("utf-8"))
                    claims.append(
                        {
                            "subject": self._resolve(int(row["subject_id"])),
                            "relation": self._resolve(int(row["relation_id"])),
                            "object": self._resolve(int(row["object_id"])),
                        }
                    )
        return claims

    def lookup(
        self,
        *,
        subject: str | None = None,
        relation: str | None = None,
        object_: str | None = None,
    ) -> list[dict[str, str]]:
        subject_id = self._string_to_id.get(subject) if subject is not None else None
        relation_id = self._string_to_id.get(relation) if relation is not None else None
        object_id = self._string_to_id.get(object_) if object_ is not None else None
        if (subject is not None and subject_id is None) or (relation is not None and relation_id is None) or (
            object_ is not None and object_id is None
        ):
            return []

        matches: list[dict[str, str]] = []
        with self._encoded_path.open("rb") as fh:
            with mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                for raw in iter(mm.readline, b""):
                    line = raw.strip()
                    if not line:
                        continue
                    row = json.loads(line.decode("utf-8"))
                    if subject_id is not None and int(row["subject_id"]) != subject_id:
                        continue
                    if relation_id is not None and int(row["relation_id"]) != relation_id:
                        continue
                    if object_id is not None and int(row["object_id"]) != object_id:
                        continue
                    matches.append(
                        {
                            "subject": self._resolve(int(row["subject_id"])),
                            "relation": self._resolve(int(row["relation_id"])),
                            "object": self._resolve(int(row["object_id"])),
                        }
                    )
        return matches
