"""CAKE source configuration models and loader."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from vcse.cake.errors import CakeConfigError

ALLOWED_SOURCE_TYPES: frozenset[str] = frozenset({"local_file", "http_static"})
ALLOWED_FORMATS: frozenset[str] = frozenset({"wikidata_json", "dbpedia_ttl", "json", "jsonl"})
ALLOWED_DOMAINS: frozenset[str] = frozenset({"wikidata.org", "www.wikidata.org", "dbpedia.org", "www.dbpedia.org"})

_REQUIRED_FIELDS = ("id", "source_type", "format", "path_or_url")


@dataclass(frozen=True)
class CakeSource:
    id: str
    source_type: str
    format: str
    path_or_url: str
    trust_level: str = "unrated"
    enabled: bool = True
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CakeSourceConfig:
    sources: list[CakeSource]
    version: str
    description: str


def load_source_config(path: str | Path) -> CakeSourceConfig:
    """Load and validate a CAKE source config JSON file."""
    p = Path(path)
    if not p.exists():
        raise CakeConfigError("FILE_NOT_FOUND", f"source config not found: {p}")
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise CakeConfigError("MALFORMED_CONFIG", f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise CakeConfigError("MALFORMED_CONFIG", "config must be a JSON object")

    version = str(data.get("version", ""))
    description = str(data.get("description", ""))
    raw_sources = data.get("sources", [])
    if not isinstance(raw_sources, list):
        raise CakeConfigError("MALFORMED_CONFIG", "'sources' must be a list")

    sources: list[CakeSource] = []
    for raw in raw_sources:
        source = _parse_source(raw)
        validate_source(source)
        sources.append(source)

    return CakeSourceConfig(sources=sources, version=version, description=description)


def _parse_source(raw: Any) -> CakeSource:
    if not isinstance(raw, dict):
        raise CakeConfigError("MALFORMED_CONFIG", "each source must be a JSON object")
    for field_name in _REQUIRED_FIELDS:
        if field_name not in raw:
            raise CakeConfigError("MISSING_FIELD", f"source missing required field: '{field_name}'")
    return CakeSource(
        id=str(raw["id"]),
        source_type=str(raw["source_type"]),
        format=str(raw["format"]),
        path_or_url=str(raw["path_or_url"]),
        trust_level=str(raw.get("trust_level", "unrated")),
        enabled=bool(raw.get("enabled", True)),
        description=str(raw.get("description", "")),
        metadata=dict(raw.get("metadata", {})),
    )


def validate_source(source: CakeSource) -> None:
    """Validate a single CakeSource. Raises CakeConfigError on any violation."""
    if source.source_type not in ALLOWED_SOURCE_TYPES:
        raise CakeConfigError(
            "INVALID_SOURCE_TYPE",
            f"source_type '{source.source_type}' not allowed; must be one of {sorted(ALLOWED_SOURCE_TYPES)}",
        )
    if source.format not in ALLOWED_FORMATS:
        raise CakeConfigError(
            "INVALID_FORMAT",
            f"format '{source.format}' not allowed; must be one of {sorted(ALLOWED_FORMATS)}",
        )
    if source.source_type == "http_static":
        _validate_domain(source.path_or_url)


def _validate_domain(url: str) -> None:
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc not in ALLOWED_DOMAINS:
            raise CakeConfigError(
                "DISALLOWED_DOMAIN",
                f"domain '{netloc}' not in allowlist {sorted(ALLOWED_DOMAINS)}",
            )
    except CakeConfigError:
        raise
    except Exception as exc:
        raise CakeConfigError("INVALID_URL", f"cannot parse URL: {url}") from exc
