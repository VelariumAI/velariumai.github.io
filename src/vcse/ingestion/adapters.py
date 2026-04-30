"""Deterministic source adapters."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from vcse.ingestion.source import SourceDocument, SourceLoadError, build_source_id


class JSONAdapter:
    source_type = "json"

    def load(self, path: Path) -> SourceDocument:
        try:
            content = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise SourceLoadError("MALFORMED_JSON", exc.msg) from exc
        except OSError as exc:
            raise SourceLoadError("FILE_ERROR", str(exc)) from exc
        return SourceDocument(
            id=build_source_id(path, self.source_type),
            source_type=self.source_type,
            path_or_uri=str(path),
            content=content,
            metadata={"extension": path.suffix.lower()},
        )


class JSONLAdapter:
    source_type = "jsonl"

    def load(self, path: Path) -> SourceDocument:
        rows: list[dict[str, Any]] = []
        try:
            for line_number, line in enumerate(path.read_text().splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise SourceLoadError("MALFORMED_JSON", f"line {line_number}: {exc.msg}") from exc
                if not isinstance(row, dict):
                    raise SourceLoadError("INVALID_SOURCE", f"line {line_number} must be object")
                rows.append(row)
        except OSError as exc:
            raise SourceLoadError("FILE_ERROR", str(exc)) from exc
        return SourceDocument(
            id=build_source_id(path, self.source_type),
            source_type=self.source_type,
            path_or_uri=str(path),
            content=rows,
            metadata={"rows": len(rows), "extension": path.suffix.lower()},
        )


class CSVAdapter:
    source_type = "csv"

    def load(self, path: Path) -> SourceDocument:
        try:
            with path.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
        except OSError as exc:
            raise SourceLoadError("FILE_ERROR", str(exc)) from exc
        return SourceDocument(
            id=build_source_id(path, self.source_type),
            source_type=self.source_type,
            path_or_uri=str(path),
            content=rows,
            metadata={"rows": len(rows), "extension": path.suffix.lower()},
        )


class TextAdapter:
    source_type = "text"

    def load(self, path: Path) -> SourceDocument:
        try:
            text = path.read_text()
        except OSError as exc:
            raise SourceLoadError("FILE_ERROR", str(exc)) from exc
        return SourceDocument(
            id=build_source_id(path, self.source_type),
            source_type=self.source_type,
            path_or_uri=str(path),
            content=text,
            metadata={"length": len(text), "extension": path.suffix.lower()},
        )


class YAMLAdapter:
    source_type = "yaml"

    def load(self, path: Path) -> SourceDocument:
        try:
            import yaml  # type: ignore[import-not-found]
        except Exception as exc:
            raise SourceLoadError("UNSUPPORTED_FORMAT", "PyYAML is not available") from exc
        try:
            content = yaml.safe_load(path.read_text())
        except OSError as exc:
            raise SourceLoadError("FILE_ERROR", str(exc)) from exc
        except Exception as exc:
            raise SourceLoadError("MALFORMED_YAML", str(exc)) from exc
        return SourceDocument(
            id=build_source_id(path, self.source_type),
            source_type=self.source_type,
            path_or_uri=str(path),
            content=content,
            metadata={"extension": path.suffix.lower()},
        )


def load_source_document(path_like: str | Path) -> SourceDocument:
    path = Path(path_like)
    if str(path).startswith("http://") or str(path).startswith("https://"):
        raise SourceLoadError("UNSUPPORTED_SOURCE", "Network sources are not allowed")
    if not path.exists():
        raise SourceLoadError("FILE_ERROR", f"File not found: {path}")
    suffix = path.suffix.lower()
    adapters = {
        ".json": JSONAdapter(),
        ".jsonl": JSONLAdapter(),
        ".csv": CSVAdapter(),
        ".txt": TextAdapter(),
        ".yaml": YAMLAdapter(),
        ".yml": YAMLAdapter(),
    }
    adapter = adapters.get(suffix)
    if adapter is None:
        raise SourceLoadError("UNSUPPORTED_FORMAT", f"Unsupported file extension: {suffix or '<none>'}")
    return adapter.load(path)
