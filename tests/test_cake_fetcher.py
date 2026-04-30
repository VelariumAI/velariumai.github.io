"""Tests for CAKE transport system and fetcher."""

from __future__ import annotations

import hashlib
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from vcse.cake.fetcher import FileTransport, HttpStaticTransport, fetch_source
from vcse.cake.snapshot import FetchedSource
from vcse.cake.sources import CakeSource
from vcse.cake.errors import CakeTransportError


def _local_source(path: str, source_type: str = "local_file", fmt: str = "json") -> CakeSource:
    return CakeSource(
        id="test_src",
        source_type=source_type,
        format=fmt,
        path_or_url=path,
    )


def test_file_transport_reads_existing_file(tmp_path):
    data = b'{"key": "value"}'
    f = tmp_path / "data.json"
    f.write_bytes(data)
    src = _local_source(str(f))
    transport = FileTransport()
    fetched = transport.fetch(src)
    assert isinstance(fetched, FetchedSource)
    assert fetched.raw_bytes == data
    assert fetched.content_hash == hashlib.sha256(data).hexdigest()
    assert fetched.transport_type == "file"
    assert fetched.source_id == "test_src"


def test_file_transport_raises_on_missing_file(tmp_path):
    src = _local_source(str(tmp_path / "nonexistent.json"))
    transport = FileTransport()
    with pytest.raises(CakeTransportError) as exc_info:
        transport.fetch(src)
    assert "FILE_NOT_FOUND" in exc_info.value.error_type


def test_http_transport_disabled_by_default():
    src = _local_source("https://www.wikidata.org/Q90.json", source_type="http_static", fmt="wikidata_json")
    transport = HttpStaticTransport(allow_http=False)
    with pytest.raises(CakeTransportError) as exc_info:
        transport.fetch(src)
    assert "HTTP_DISABLED" in exc_info.value.error_type


def test_http_transport_blocks_disallowed_domain():
    src = CakeSource(
        id="evil",
        source_type="http_static",
        format="json",
        path_or_url="https://evil.com/data.json",
    )
    transport = HttpStaticTransport(allow_http=True)
    with pytest.raises(CakeTransportError) as exc_info:
        transport.fetch(src)
    assert "DISALLOWED_DOMAIN" in exc_info.value.error_type


def test_http_transport_fetches_allowed_domain(tmp_path):
    """Mock urllib to avoid real network access."""
    fake_content = b'{"entities": {}}'
    src = CakeSource(
        id="wd_test",
        source_type="http_static",
        format="wikidata_json",
        path_or_url="https://www.wikidata.org/wiki/Special:EntityData/Q90.json",
    )
    mock_response = MagicMock()
    mock_response.read.return_value = fake_content
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("vcse.cake.fetcher.urllib.request.urlopen", return_value=mock_response):
        transport = HttpStaticTransport(allow_http=True)
        fetched = transport.fetch(src)

    assert fetched.raw_bytes == fake_content
    assert fetched.transport_type == "http"
    assert fetched.source_id == "wd_test"


def test_fetch_source_with_limit(tmp_path):
    """fetch_source respects limit by truncating lines."""
    lines = [json.dumps({"n": i}) for i in range(200)]
    f = tmp_path / "data.jsonl"
    f.write_bytes("\n".join(lines).encode())
    src = CakeSource(id="s", source_type="local_file", format="jsonl", path_or_url=str(f))
    transport = FileTransport()
    fetched = fetch_source(src, transport, limit=50)
    content = fetched.raw_bytes.decode()
    loaded_lines = [l for l in content.splitlines() if l.strip()]
    assert len(loaded_lines) == 50


def test_fetch_source_no_limit_returns_all(tmp_path):
    lines = [json.dumps({"n": i}) for i in range(10)]
    f = tmp_path / "data.jsonl"
    f.write_bytes("\n".join(lines).encode())
    src = CakeSource(id="s", source_type="local_file", format="jsonl", path_or_url=str(f))
    transport = FileTransport()
    fetched = fetch_source(src, transport, limit=None)
    content = fetched.raw_bytes.decode()
    loaded_lines = [l for l in content.splitlines() if l.strip()]
    assert len(loaded_lines) == 10