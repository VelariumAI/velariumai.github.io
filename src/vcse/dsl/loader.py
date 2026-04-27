"""DSL loader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vcse.dsl.errors import DSLError
from vcse.dsl.schema import DSLArtifact, DSLDocument


class DSLLoader:
    @staticmethod
    def load(path_like: str | Path) -> DSLDocument:
        path = Path(path_like)
        if str(path).startswith("http://") or str(path).startswith("https://"):
            raise DSLError("UNSUPPORTED_SOURCE", "Network loading is not allowed")
        if not path.exists():
            raise DSLError("FILE_ERROR", f"File not found: {path}")
        suffix = path.suffix.lower()
        if suffix == ".json":
            payload = _load_json(path)
        elif suffix in {".yaml", ".yml"}:
            payload = _load_yaml(path)
        else:
            raise DSLError("UNSUPPORTED_FORMAT", f"Unsupported DSL format: {suffix or '<none>'}")
        return _to_document(payload)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise DSLError("MALFORMED_DSL", exc.msg) from exc
    except OSError as exc:
        raise DSLError("FILE_ERROR", str(exc)) from exc
    if not isinstance(data, dict):
        raise DSLError("INVALID_DSL", "Root must be an object")
    return data


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-not-found]
    except Exception as exc:
        raise DSLError("UNSUPPORTED_FORMAT", "PyYAML is not available") from exc
    try:
        data = yaml.safe_load(path.read_text())
    except Exception as exc:
        raise DSLError("MALFORMED_DSL", str(exc)) from exc
    if not isinstance(data, dict):
        raise DSLError("INVALID_DSL", "Root must be an object")
    return data


def _to_document(payload: dict[str, Any]) -> DSLDocument:
    artifacts_raw = payload.get("artifacts", [])
    if not isinstance(artifacts_raw, list):
        raise DSLError("INVALID_DSL", "artifacts must be a list")
    artifacts: list[DSLArtifact] = []
    for index, item in enumerate(artifacts_raw, start=1):
        if not isinstance(item, dict):
            raise DSLError("INVALID_DSL", f"artifact {index} must be object")
        artifacts.append(
            DSLArtifact(
                id=str(item.get("id", "")),
                type=str(item.get("type", "")),
                version=str(item.get("version", "1.0.0")),
                description=str(item.get("description", "")),
                enabled=bool(item.get("enabled", True)),
                priority=int(item.get("priority", 100)),
                payload={k: v for k, v in item.items() if k not in {"id", "type", "version", "description", "enabled", "priority"}},
            )
        )
    return DSLDocument(
        name=str(payload.get("name", "")),
        version=str(payload.get("version", "")),
        description=str(payload.get("description", "")),
        artifacts=artifacts,
    )
