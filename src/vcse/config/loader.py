"""Settings loader from env/config file."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from vcse.config.settings import Settings


def load_settings(config_path: str | Path | None = None) -> Settings:
    base = _from_env()
    if config_path is None:
        return base
    payload = _read_config_file(Path(config_path))
    merged = _merge(base, payload)
    return merged


def _from_env() -> Settings:
    return Settings(
        search_backend=os.getenv("VCSE_SEARCH_BACKEND", "beam"),
        ts3_enabled=_to_bool(os.getenv("VCSE_TS3_ENABLED"), False),
        indexing_enabled=_to_bool(os.getenv("VCSE_INDEXING_ENABLED"), False),
        top_k_rules=_to_int(os.getenv("VCSE_TOP_K_RULES"), 20),
        top_k_packs=_to_int(os.getenv("VCSE_TOP_K_PACKS"), 5),
        api_host=os.getenv("VCSE_API_HOST", "127.0.0.1"),
        api_port=_to_int(os.getenv("VCSE_API_PORT"), 8000),
        api_debug=_to_bool(os.getenv("VCSE_API_DEBUG"), False),
        api_timeout_seconds=_to_float(os.getenv("VCSE_API_TIMEOUT_SECONDS"), 30.0),
        api_max_request_bytes=_to_int(os.getenv("VCSE_API_MAX_REQUEST_BYTES"), 1_000_000),
        log_level=os.getenv("VCSE_LOG_LEVEL", "INFO").upper(),
        profiling_enabled=_to_bool(os.getenv("VCSE_PROFILING_ENABLED"), False),
    )


def _read_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"CONFIG_ERROR: file not found: {path}")
    suffix = path.suffix.lower()
    try:
        text = path.read_text()
    except OSError as exc:
        raise ValueError(f"CONFIG_ERROR: {exc}") from exc

    if suffix == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"CONFIG_ERROR: malformed JSON ({exc.msg})") from exc
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-not-found]
        except Exception as exc:
            raise ValueError("CONFIG_ERROR: PyYAML not available") from exc
        try:
            payload = yaml.safe_load(text)
        except Exception as exc:
            raise ValueError(f"CONFIG_ERROR: malformed YAML ({exc})") from exc
    else:
        raise ValueError(f"CONFIG_ERROR: unsupported config format: {suffix or '<none>'}")

    if not isinstance(payload, dict):
        raise ValueError("CONFIG_ERROR: config root must be object")
    return payload


def _merge(settings: Settings, payload: dict[str, Any]) -> Settings:
    data = settings.__dict__.copy()
    for key in data:
        if key in payload:
            data[key] = payload[key]
    return Settings(**data)


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    lowered = value.strip().lower()
    return lowered in {"1", "true", "yes", "on"}


def _to_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _to_float(value: str | None, default: float) -> float:
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError:
        return default
