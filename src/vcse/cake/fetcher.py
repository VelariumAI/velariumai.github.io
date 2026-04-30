"""CAKE transport system — FileTransport, HttpStaticTransport, fetch_source."""

from __future__ import annotations

import hashlib
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from vcse.cake.errors import CakeTransportError
from vcse.cake.snapshot import FetchedSource
from vcse.cake.sources import ALLOWED_DOMAINS, CakeSource

_ALLOWED_HTTP_DOMAINS = ALLOWED_DOMAINS


class CakeTransport:
    """Abstract transport interface."""

    def fetch(self, source: CakeSource) -> FetchedSource:
        raise NotImplementedError


class FileTransport(CakeTransport):
    """Reads a local file. Default transport; safe for CI and tests."""

    def fetch(self, source: CakeSource) -> FetchedSource:
        path = Path(source.path_or_url)
        if not path.exists():
            raise CakeTransportError("FILE_NOT_FOUND", f"local file not found: {path}")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise CakeTransportError("FILE_READ_ERROR", str(exc)) from exc
        return _make_fetched(source.id, raw, "file", str(path))


class HttpStaticTransport(CakeTransport):
    """Fetches a single URL. Requires allow_http=True and domain allowlist."""

    def __init__(self, allow_http: bool = False) -> None:
        self.allow_http = allow_http

    def fetch(self, source: CakeSource) -> FetchedSource:
        if not self.allow_http:
            raise CakeTransportError(
                "HTTP_DISABLED",
                "HTTP transport requires --allow-http flag; use FileTransport for local files",
            )
        url = source.path_or_url
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc not in _ALLOWED_HTTP_DOMAINS:
            raise CakeTransportError(
                "DISALLOWED_DOMAIN",
                f"domain '{netloc}' not in allowlist {sorted(_ALLOWED_HTTP_DOMAINS)}",
            )
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
                raw = resp.read()
        except Exception as exc:
            raise CakeTransportError("HTTP_FETCH_ERROR", f"fetching {url}: {exc}") from exc
        return _make_fetched(source.id, raw, "http", url)


def fetch_source(
    source: CakeSource,
    transport: CakeTransport,
    *,
    limit: int | None = None,
) -> FetchedSource:
    """Fetch source via transport. If limit is set, truncate to first N lines (line-oriented formats)."""
    fetched = transport.fetch(source)
    if limit is None:
        return fetched
    lines = fetched.raw_bytes.splitlines(keepends=True)[:limit]
    truncated = b"".join(lines)
    return _make_fetched(source.id, truncated, fetched.transport_type, fetched.origin)


def _make_fetched(source_id: str, raw: bytes, transport_type: str, origin: str) -> FetchedSource:
    return FetchedSource(
        source_id=source_id,
        raw_bytes=raw,
        content_hash=hashlib.sha256(raw).hexdigest(),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        transport_type=transport_type,
        origin=origin,
    )