"""Tests for CAKE source config loading and validation."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from vcse.cake.sources import (
    ALLOWED_DOMAINS,
    ALLOWED_FORMATS,
    ALLOWED_SOURCE_TYPES,
    CakeSource,
    CakeSourceConfig,
    load_source_config,
    validate_source,
)
from vcse.cake.errors import CakeConfigError


def _write_config(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "sources.json"
    p.write_text(json.dumps(data))
    return p


def test_load_valid_config(tmp_path):
    cfg = _write_config(tmp_path, {
        "version": "1.0.0",
        "description": "test",
        "sources": [
            {
                "id": "wikidata_capitals",
                "source_type": "local_file",
                "format": "wikidata_json",
                "path_or_url": "examples/cake/wikidata_sample.json",
                "trust_level": "community",
                "enabled": True,
                "description": "test source",
            }
        ],
    })
    config = load_source_config(cfg)
    assert isinstance(config, CakeSourceConfig)
    assert config.version == "1.0.0"
    assert len(config.sources) == 1
    assert config.sources[0].id == "wikidata_capitals"
    assert config.sources[0].format == "wikidata_json"


def test_disabled_sources_included_but_flagged(tmp_path):
    cfg = _write_config(tmp_path, {
        "version": "1.0.0",
        "description": "test",
        "sources": [
            {
                "id": "disabled_src",
                "source_type": "local_file",
                "format": "json",
                "path_or_url": "some/file.json",
                "enabled": False,
            }
        ],
    })
    config = load_source_config(cfg)
    assert config.sources[0].enabled is False


def test_invalid_source_type_raises(tmp_path):
    cfg = _write_config(tmp_path, {
        "version": "1.0.0",
        "description": "test",
        "sources": [
            {
                "id": "bad",
                "source_type": "ftp_server",
                "format": "json",
                "path_or_url": "ftp://example.com/data.json",
            }
        ],
    })
    with pytest.raises(CakeConfigError) as exc_info:
        load_source_config(cfg)
    assert "INVALID_SOURCE_TYPE" in exc_info.value.error_type


def test_invalid_format_raises(tmp_path):
    cfg = _write_config(tmp_path, {
        "version": "1.0.0",
        "description": "test",
        "sources": [
            {
                "id": "bad",
                "source_type": "local_file",
                "format": "html_page",
                "path_or_url": "file.html",
            }
        ],
    })
    with pytest.raises(CakeConfigError) as exc_info:
        load_source_config(cfg)
    assert "INVALID_FORMAT" in exc_info.value.error_type


def test_http_source_with_disallowed_domain_raises(tmp_path):
    cfg = _write_config(tmp_path, {
        "version": "1.0.0",
        "description": "test",
        "sources": [
            {
                "id": "evil",
                "source_type": "http_static",
                "format": "json",
                "path_or_url": "https://evil.com/data.json",
            }
        ],
    })
    with pytest.raises(CakeConfigError) as exc_info:
        load_source_config(cfg)
    assert "DISALLOWED_DOMAIN" in exc_info.value.error_type


def test_http_source_with_allowed_domain_ok(tmp_path):
    cfg = _write_config(tmp_path, {
        "version": "1.0.0",
        "description": "test",
        "sources": [
            {
                "id": "wd",
                "source_type": "http_static",
                "format": "wikidata_json",
                "path_or_url": "https://www.wikidata.org/wiki/Special:EntityData/Q90.json",
            }
        ],
    })
    config = load_source_config(cfg)
    assert config.sources[0].id == "wd"


def test_missing_required_field_raises(tmp_path):
    cfg = _write_config(tmp_path, {
        "version": "1.0.0",
        "description": "test",
        "sources": [
            {"id": "no_format", "source_type": "local_file", "path_or_url": "f.json"},
        ],
    })
    with pytest.raises(CakeConfigError) as exc_info:
        load_source_config(cfg)
    assert "MISSING_FIELD" in exc_info.value.error_type


def test_malformed_json_raises(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json")
    with pytest.raises(CakeConfigError) as exc_info:
        load_source_config(p)
    assert "MALFORMED_CONFIG" in exc_info.value.error_type


def test_missing_file_raises(tmp_path):
    with pytest.raises(CakeConfigError) as exc_info:
        load_source_config(tmp_path / "nonexistent.json")
    assert "FILE_NOT_FOUND" in exc_info.value.error_type


def test_allowed_constants():
    assert "local_file" in ALLOWED_SOURCE_TYPES
    assert "http_static" in ALLOWED_SOURCE_TYPES
    assert "wikidata_json" in ALLOWED_FORMATS
    assert "dbpedia_ttl" in ALLOWED_FORMATS
    assert "wikidata.org" in ALLOWED_DOMAINS
    assert "dbpedia.org" in ALLOWED_DOMAINS
