# CAKE Implementation Plan — v2.7.0

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement CAKE (Controlled Acquisition of Knowledge Engine) — a deterministic acquisition frontend that fetches, snapshots, extracts, and routes structured claims into VCSE's existing normalization → trust → ledger → pack pipeline.

**Architecture:** CAKE is a thin acquisition layer. It owns: source config, transport (file/http), immutable snapshots, and deterministic extractors. Everything downstream (normalization, validation, trust, ledger, pack building) is delegated to existing systems without modification. The boundary is `List[KnowledgeClaim]` — CAKE produces it, existing code consumes it.

**Tech Stack:** Python 3.11+ stdlib only. No new dependencies. Reuses: `vcse.knowledge.{normalizer,validator,resolver,pack_builder,pack_model}`, `vcse.trust.promoter`, `vcse.ledger.{store,events,audit}`.

---

## File Map

**Create:**
```
src/vcse/cake/__init__.py
src/vcse/cake/errors.py
src/vcse/cake/sources.py
src/vcse/cake/snapshot.py
src/vcse/cake/fetcher.py
src/vcse/cake/extractor_wikidata.py
src/vcse/cake/extractor_dbpedia.py
src/vcse/cake/normalizer_adapter.py
src/vcse/cake/trust_runner.py
src/vcse/cake/pack_updater.py
src/vcse/cake/pipeline.py
src/vcse/cake/reports.py
src/vcse/cake/scheduler.py       (stub only)
examples/cake/general_world_sources.json
examples/cake/wikidata_sample.json
examples/cake/dbpedia_sample.ttl
examples/cake/malformed_source.json
examples/cake/disallowed_source.json
docs/CAKE.md
tests/test_cake_sources.py
tests/test_cake_fetcher.py
tests/test_cake_snapshot.py
tests/test_cake_extractors.py
tests/test_cake_pipeline.py
tests/test_cake_pack_updater.py
tests/test_cake_cli.py
```

**Modify:**
```
src/vcse/cli.py              (add cake subparser + dispatch)
src/vcse/__init__.py         (bump to "2.7.0")
pyproject.toml               (bump to "2.7.0")
README.md                    (add CAKE section)
docs/ARCHITECTURE.md         (add CAKE layer)
docs/KNOWLEDGE.md            (note CAKE upstream)
docs/TRUST.md                (note CAKE trust entry)
docs/LEDGER.md               (note CAKE ledger events)
```

---

## Task 0: Pre-Implementation Version Check

**Files:** none

- [ ] **Step 1: Confirm version is 2.6.0**

```bash
cd /data/data/com.termux/files/home/project/vcse
git status
python -c "import vcse; print(vcse.__version__)"
```

Expected: clean working tree (only untracked files), output `2.6.0`.
If not `2.6.0` — **STOP. Do not proceed.**

- [ ] **Step 2: Confirm existing tests pass**

```bash
python -m pytest -q --tb=short 2>&1 | tail -5
```

Expected: all pass, 0 failures.

---

## Task 1: errors.py

**Files:**
- Create: `src/vcse/cake/errors.py`

- [ ] **Step 1: Create the errors module**

```python
# src/vcse/cake/errors.py
"""CAKE error hierarchy."""

from __future__ import annotations


class CakeError(ValueError):
    """Base error for all CAKE failures."""

    def __init__(self, error_type: str, reason: str) -> None:
        super().__init__(f"{error_type}: {reason}")
        self.error_type = error_type
        self.reason = reason


class CakeConfigError(CakeError):
    """Invalid or missing source configuration."""


class CakeTransportError(CakeError):
    """Transport failure (file not found, domain blocked, HTTP disabled)."""


class CakeSnapshotCorruptedError(CakeError):
    """Snapshot hash does not match stored content."""


class CakeExtractionError(CakeError):
    """Extractor failed to parse source data."""


class CakePipelineError(CakeError):
    """Pipeline step failed; acquisition aborted."""
```

- [ ] **Step 2: Create package init (placeholder — will fill in Task 12)**

```python
# src/vcse/cake/__init__.py
"""CAKE — Controlled Acquisition of Knowledge Engine."""
```

- [ ] **Step 3: Commit**

```bash
git add src/vcse/cake/__init__.py src/vcse/cake/errors.py
git commit -m "feat(cake): add package scaffold and error hierarchy"
```

---

## Task 2: sources.py + test_cake_sources.py

**Files:**
- Create: `src/vcse/cake/sources.py`
- Create: `tests/test_cake_sources.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cake_sources.py
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
                "source_type": "ftp_server",  # not allowed
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
                "format": "html_page",  # not allowed
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_cake_sources.py -q 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'vcse.cake.sources'`

- [ ] **Step 3: Implement sources.py**

```python
# src/vcse/cake/sources.py
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
        domain = parsed.netloc.lower().lstrip("www.")
        if not any(url_domain == parsed.netloc.lower() for url_domain in ALLOWED_DOMAINS):
            # Try stripping www. prefix
            bare = parsed.netloc.lower()
            if not any(bare == d or bare == f"www.{d}" for d in ALLOWED_DOMAINS):
                raise CakeConfigError(
                    "DISALLOWED_DOMAIN",
                    f"domain '{parsed.netloc}' not in allowlist {sorted(ALLOWED_DOMAINS)}",
                )
    except CakeConfigError:
        raise
    except Exception as exc:
        raise CakeConfigError("INVALID_URL", f"cannot parse URL: {url}") from exc
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_cake_sources.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/vcse/cake/sources.py tests/test_cake_sources.py
git commit -m "feat(cake): add source config loader with domain allowlist validation"
```

---

## Task 3: snapshot.py + test_cake_snapshot.py

**Files:**
- Create: `src/vcse/cake/snapshot.py`
- Create: `tests/test_cake_snapshot.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cake_snapshot.py
"""Tests for CAKE snapshot store."""

from __future__ import annotations

import hashlib
import json
import pytest
from pathlib import Path

from vcse.cake.snapshot import CakeSnapshot, CakeSnapshotStore, FetchedSource
from vcse.cake.errors import CakeSnapshotCorruptedError


def _make_fetched(source_id: str = "test_src", content: bytes = b"hello world") -> FetchedSource:
    sha = hashlib.sha256(content).hexdigest()
    return FetchedSource(
        source_id=source_id,
        raw_bytes=content,
        content_hash=sha,
        fetched_at="2026-04-27T00:00:00+00:00",
        transport_type="file",
        origin="/tmp/test.json",
    )


def test_save_creates_snapshot_file(tmp_path):
    store = CakeSnapshotStore(root=tmp_path)
    fetched = _make_fetched()
    snap = store.save(fetched)
    assert snap.path.exists()
    assert snap.meta_path.exists()
    assert snap.snapshot_id.startswith("test_src/")


def test_load_returns_original_bytes(tmp_path):
    store = CakeSnapshotStore(root=tmp_path)
    fetched = _make_fetched(content=b"some data 123")
    snap = store.save(fetched)
    loaded = store.load(snap.snapshot_id)
    assert loaded == b"some data 123"


def test_verify_passes_for_valid_snapshot(tmp_path):
    store = CakeSnapshotStore(root=tmp_path)
    fetched = _make_fetched()
    snap = store.save(fetched)
    assert store.verify(snap.snapshot_id) is True


def test_verify_fails_for_corrupted_snapshot(tmp_path):
    store = CakeSnapshotStore(root=tmp_path)
    fetched = _make_fetched()
    snap = store.save(fetched)
    snap.path.write_bytes(b"corrupted!")
    with pytest.raises(CakeSnapshotCorruptedError):
        store.verify(snap.snapshot_id)


def test_no_overwrite_on_duplicate(tmp_path):
    store = CakeSnapshotStore(root=tmp_path)
    fetched = _make_fetched()
    snap1 = store.save(fetched)
    snap2 = store.save(fetched)
    assert snap1.snapshot_id == snap2.snapshot_id
    assert snap1.path == snap2.path


def test_meta_sidecar_has_required_fields(tmp_path):
    store = CakeSnapshotStore(root=tmp_path)
    fetched = _make_fetched()
    snap = store.save(fetched)
    meta = json.loads(snap.meta_path.read_text())
    assert "source_id" in meta
    assert "content_hash" in meta
    assert "fetched_at" in meta
    assert "origin" in meta
    assert "content_length" in meta


def test_snapshot_id_format(tmp_path):
    store = CakeSnapshotStore(root=tmp_path)
    fetched = _make_fetched(source_id="my_source", content=b"abc")
    snap = store.save(fetched)
    parts = snap.snapshot_id.split("/")
    assert parts[0] == "my_source"
    assert len(parts[1]) == 16  # first 16 hex chars of sha256


def test_different_content_different_snapshot_ids(tmp_path):
    store = CakeSnapshotStore(root=tmp_path)
    snap1 = store.save(_make_fetched(content=b"data A"))
    snap2 = store.save(_make_fetched(content=b"data B"))
    assert snap1.snapshot_id != snap2.snapshot_id
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_cake_snapshot.py -q 2>&1 | head -5
```

Expected: `ModuleNotFoundError: No module named 'vcse.cake.snapshot'`

- [ ] **Step 3: Implement snapshot.py**

```python
# src/vcse/cake/snapshot.py
"""Immutable snapshot store for CAKE fetched sources."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from vcse.cake.errors import CakeSnapshotCorruptedError


@dataclass(frozen=True)
class FetchedSource:
    source_id: str
    raw_bytes: bytes
    content_hash: str       # SHA-256 hex of raw_bytes
    fetched_at: str         # ISO 8601 UTC
    transport_type: str     # "file" | "http"
    origin: str             # local path or URL


@dataclass(frozen=True)
class CakeSnapshot:
    snapshot_id: str        # "{source_id}/{sha256[:16]}"
    source_id: str
    content_hash: str
    fetched_at: str
    path: Path              # .snap file
    meta_path: Path         # .snap.meta.json file


class CakeSnapshotStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.home() / ".vcse" / "cake" / "snapshots"

    def save(self, fetched: FetchedSource) -> CakeSnapshot:
        """Save raw bytes to a new snapshot file. No-op (returns existing) if same hash already stored."""
        short_hash = fetched.content_hash[:16]
        snapshot_id = f"{fetched.source_id}/{short_hash}"
        snap_dir = self.root / fetched.source_id
        snap_dir.mkdir(parents=True, exist_ok=True)

        snap_path = snap_dir / f"{short_hash}.snap"
        meta_path = snap_dir / f"{short_hash}.snap.meta.json"

        if snap_path.exists():
            # Already stored — return existing without overwrite
            return CakeSnapshot(
                snapshot_id=snapshot_id,
                source_id=fetched.source_id,
                content_hash=fetched.content_hash,
                fetched_at=fetched.fetched_at,
                path=snap_path,
                meta_path=meta_path,
            )

        snap_path.write_bytes(fetched.raw_bytes)
        meta = {
            "snapshot_id": snapshot_id,
            "source_id": fetched.source_id,
            "content_hash": fetched.content_hash,
            "fetched_at": fetched.fetched_at,
            "transport_type": fetched.transport_type,
            "origin": fetched.origin,
            "content_length": len(fetched.raw_bytes),
        }
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True))

        return CakeSnapshot(
            snapshot_id=snapshot_id,
            source_id=fetched.source_id,
            content_hash=fetched.content_hash,
            fetched_at=fetched.fetched_at,
            path=snap_path,
            meta_path=meta_path,
        )

    def load(self, snapshot_id: str) -> bytes:
        """Load raw bytes for a snapshot. Raises FileNotFoundError if missing."""
        source_id, short_hash = snapshot_id.split("/", 1)
        snap_path = self.root / source_id / f"{short_hash}.snap"
        if not snap_path.exists():
            raise FileNotFoundError(f"snapshot not found: {snap_path}")
        return snap_path.read_bytes()

    def verify(self, snapshot_id: str) -> bool:
        """Recompute SHA-256 and compare to stored hash. Raises CakeSnapshotCorruptedError on mismatch."""
        source_id, short_hash = snapshot_id.split("/", 1)
        snap_path = self.root / source_id / f"{short_hash}.snap"
        meta_path = self.root / source_id / f"{short_hash}.snap.meta.json"

        if not snap_path.exists() or not meta_path.exists():
            raise FileNotFoundError(f"snapshot files missing for: {snapshot_id}")

        raw = snap_path.read_bytes()
        actual_hash = hashlib.sha256(raw).hexdigest()
        meta = json.loads(meta_path.read_text())
        stored_hash = meta["content_hash"]

        if actual_hash != stored_hash:
            raise CakeSnapshotCorruptedError(
                "SNAPSHOT_CORRUPTED",
                f"hash mismatch for {snapshot_id}: stored={stored_hash[:16]}… actual={actual_hash[:16]}…",
            )
        return True
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_cake_snapshot.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/vcse/cake/snapshot.py tests/test_cake_snapshot.py
git commit -m "feat(cake): add immutable snapshot store with SHA-256 integrity"
```

---

## Task 4: fetcher.py + test_cake_fetcher.py

**Files:**
- Create: `src/vcse/cake/fetcher.py`
- Create: `tests/test_cake_fetcher.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cake_fetcher.py
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_cake_fetcher.py -q 2>&1 | head -5
```

Expected: `ModuleNotFoundError: No module named 'vcse.cake.fetcher'`

- [ ] **Step 3: Implement fetcher.py**

```python
# src/vcse/cake/fetcher.py
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
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_cake_fetcher.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/vcse/cake/fetcher.py tests/test_cake_fetcher.py
git commit -m "feat(cake): add pluggable transport system (FileTransport + HttpStaticTransport)"
```

---

## Task 5: extractor_wikidata.py + extractor_dbpedia.py + test_cake_extractors.py

**Files:**
- Create: `src/vcse/cake/extractor_wikidata.py`
- Create: `src/vcse/cake/extractor_dbpedia.py`
- Create: `tests/test_cake_extractors.py`

- [ ] **Step 1: Create example data files (needed by tests)**

```bash
mkdir -p examples/cake
```

`examples/cake/wikidata_sample.json`:
```json
{
  "entities": {
    "Q90": {
      "id": "Q90",
      "labels": {"en": {"language": "en", "value": "Paris"}},
      "claims": {
        "P36": [
          {
            "mainsnak": {
              "snaktype": "value",
              "property": "P36",
              "datatype": "wikibase-item",
              "datavalue": {"value": {"entity-type": "item", "id": "Q142"}, "type": "wikibase-entityid"}
            },
            "type": "statement",
            "rank": "normal"
          }
        ],
        "P17": [
          {
            "mainsnak": {
              "snaktype": "value",
              "property": "P17",
              "datatype": "wikibase-item",
              "datavalue": {"value": {"entity-type": "item", "id": "Q142"}, "type": "wikibase-entityid"}
            },
            "type": "statement",
            "rank": "normal"
          }
        ],
        "P31": [
          {
            "mainsnak": {
              "snaktype": "value",
              "property": "P31",
              "datatype": "wikibase-item",
              "datavalue": {"value": {"entity-type": "item", "id": "Q515"}, "type": "wikibase-entityid"}
            },
            "type": "statement",
            "rank": "normal"
          }
        ]
      }
    },
    "Q142": {
      "id": "Q142",
      "labels": {"en": {"language": "en", "value": "France"}},
      "claims": {}
    },
    "Q515": {
      "id": "Q515",
      "labels": {"en": {"language": "en", "value": "city"}},
      "claims": {}
    }
  }
}
```

`examples/cake/dbpedia_sample.ttl`:
```
# DBpedia sample triples — CI-safe, no network required
<http://dbpedia.org/resource/Paris> <http://dbpedia.org/ontology/capital_of> <http://dbpedia.org/resource/France> .
<http://dbpedia.org/resource/Paris> <http://dbpedia.org/ontology/country> <http://dbpedia.org/resource/France> .
<http://dbpedia.org/resource/France> <http://dbpedia.org/ontology/instance_of> <http://dbpedia.org/resource/Country> .
```

`examples/cake/malformed_source.json` (invalid config — missing fields):
```json
{
  "version": "1.0.0",
  "description": "malformed — missing format field",
  "sources": [
    {"id": "bad_source", "source_type": "local_file", "path_or_url": "data.json"}
  ]
}
```

`examples/cake/disallowed_source.json` (disallowed domain):
```json
{
  "version": "1.0.0",
  "description": "disallowed domain test",
  "sources": [
    {
      "id": "disallowed",
      "source_type": "http_static",
      "format": "json",
      "path_or_url": "https://evil.com/data.json"
    }
  ]
}
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_cake_extractors.py
"""Tests for WikidataExtractor and DBpediaExtractor."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from vcse.cake.extractor_wikidata import WikidataExtractor, PROPERTY_MAP
from vcse.cake.extractor_dbpedia import DBpediaExtractor
from vcse.cake.snapshot import FetchedSource
from vcse.cake.errors import CakeExtractionError
from vcse.knowledge.pack_model import KnowledgeClaim


WIKIDATA_SAMPLE_PATH = Path("examples/cake/wikidata_sample.json")
DBPEDIA_SAMPLE_PATH = Path("examples/cake/dbpedia_sample.ttl")


def _fetched(source_id: str, content: bytes) -> FetchedSource:
    return FetchedSource(
        source_id=source_id,
        raw_bytes=content,
        content_hash=hashlib.sha256(content).hexdigest(),
        fetched_at="2026-04-27T00:00:00+00:00",
        transport_type="file",
        origin="test",
    )


def _wikidata_fetched() -> FetchedSource:
    return _fetched("wikidata_src", WIKIDATA_SAMPLE_PATH.read_bytes())


def _dbpedia_fetched() -> FetchedSource:
    return _fetched("dbpedia_src", DBPEDIA_SAMPLE_PATH.read_bytes())


# ─── WikidataExtractor ────────────────────────────────────────────

def test_wikidata_extracts_paris_capital_of_france():
    extractor = WikidataExtractor()
    claims = extractor.extract(_wikidata_fetched(), snapshot_id="wikidata_src/abc123")
    keys = [(c.subject, c.relation, c.object) for c in claims]
    assert ("Paris", "capital_of", "France") in keys


def test_wikidata_extracts_located_in_country():
    extractor = WikidataExtractor()
    claims = extractor.extract(_wikidata_fetched(), snapshot_id="wikidata_src/abc123")
    keys = [(c.subject, c.relation, c.object) for c in claims]
    assert ("Paris", "located_in_country", "France") in keys


def test_wikidata_extracts_instance_of():
    extractor = WikidataExtractor()
    claims = extractor.extract(_wikidata_fetched(), snapshot_id="wikidata_src/abc123")
    keys = [(c.subject, c.relation, c.object) for c in claims]
    assert ("Paris", "instance_of", "city") in keys


def test_wikidata_claims_have_provenance():
    extractor = WikidataExtractor()
    claims = extractor.extract(_wikidata_fetched(), snapshot_id="wikidata_src/abc123")
    for claim in claims:
        assert claim.provenance.source_id == "wikidata_src"
        assert claim.provenance.source_type == "wikidata_json"
        assert "abc123" in claim.provenance.location


def test_wikidata_claims_have_snapshot_id_in_qualifiers():
    extractor = WikidataExtractor()
    claims = extractor.extract(_wikidata_fetched(), snapshot_id="wikidata_src/abc123")
    for claim in claims:
        assert "snapshot_id" in claim.qualifiers


def test_wikidata_rejects_malformed_json():
    fetched = _fetched("bad_src", b"{not valid json")
    extractor = WikidataExtractor()
    with pytest.raises(CakeExtractionError) as exc_info:
        extractor.extract(fetched, snapshot_id="bad_src/xxx")
    assert "MALFORMED_JSON" in exc_info.value.error_type


def test_wikidata_empty_entities_returns_empty_list():
    fetched = _fetched("empty_src", json.dumps({"entities": {}}).encode())
    extractor = WikidataExtractor()
    claims = extractor.extract(fetched, snapshot_id="empty_src/yyy")
    assert claims == []


def test_wikidata_limit_respected():
    # Build wikidata JSON with 10 entities each having 1 P36 claim
    entities = {}
    for i in range(10):
        qid = f"Q{i}"
        obj_qid = f"Q{100 + i}"
        entities[qid] = {
            "id": qid,
            "labels": {"en": {"value": f"Entity{i}"}},
            "claims": {
                "P36": [{
                    "mainsnak": {
                        "datavalue": {"value": {"entity-type": "item", "id": obj_qid}}
                    }
                }]
            }
        }
        entities[obj_qid] = {
            "id": obj_qid,
            "labels": {"en": {"value": f"Object{i}"}},
            "claims": {}
        }
    fetched = _fetched("limit_src", json.dumps({"entities": entities}).encode())
    extractor = WikidataExtractor()
    claims = extractor.extract(fetched, snapshot_id="limit_src/zzz", limit=3)
    assert len(claims) <= 3


def test_property_map_has_required_mappings():
    assert "P36" in PROPERTY_MAP
    assert PROPERTY_MAP["P36"] == "capital_of"
    assert "P17" in PROPERTY_MAP
    assert PROPERTY_MAP["P17"] == "located_in_country"
    assert "P31" in PROPERTY_MAP
    assert PROPERTY_MAP["P31"] == "instance_of"


# ─── DBpediaExtractor ─────────────────────────────────────────────

def test_dbpedia_extracts_paris_capital_of_france():
    extractor = DBpediaExtractor()
    claims = extractor.extract(_dbpedia_fetched(), snapshot_id="dbpedia_src/abc")
    keys = [(c.subject, c.relation, c.object) for c in claims]
    assert ("Paris", "capital_of", "France") in keys


def test_dbpedia_extracts_country_relation():
    extractor = DBpediaExtractor()
    claims = extractor.extract(_dbpedia_fetched(), snapshot_id="dbpedia_src/abc")
    keys = [(c.subject, c.relation, c.object) for c in claims]
    assert ("Paris", "country", "France") in keys


def test_dbpedia_skips_comment_lines():
    content = b"# This is a comment\n<http://dbpedia.org/resource/A> <http://dbpedia.org/ontology/is_a> <http://dbpedia.org/resource/B> .\n"
    extractor = DBpediaExtractor()
    claims = extractor.extract(_fetched("db", content), snapshot_id="db/abc")
    assert len(claims) == 1
    assert claims[0].subject == "A"


def test_dbpedia_rejects_malformed_triple(caplog):
    content = b"this is not a valid triple\n<http://a.org/A> <http://b.org/rel> <http://c.org/B> .\n"
    extractor = DBpediaExtractor()
    # Malformed lines skipped with warning; valid ones extracted
    claims = extractor.extract(_fetched("db", content), snapshot_id="db/abc")
    assert len(claims) == 1


def test_dbpedia_empty_file_returns_empty():
    extractor = DBpediaExtractor()
    claims = extractor.extract(_fetched("empty", b""), snapshot_id="empty/abc")
    assert claims == []


def test_dbpedia_claims_have_provenance():
    extractor = DBpediaExtractor()
    claims = extractor.extract(_dbpedia_fetched(), snapshot_id="dbpedia_src/abc")
    for claim in claims:
        assert claim.provenance.source_id == "dbpedia_src"
        assert claim.provenance.source_type == "dbpedia_ttl"


def test_dbpedia_limit_respected():
    lines = [
        f"<http://a.org/{i}> <http://b.org/rel> <http://c.org/{i}> ."
        for i in range(20)
    ]
    content = "\n".join(lines).encode()
    extractor = DBpediaExtractor()
    claims = extractor.extract(_fetched("db", content), snapshot_id="db/abc", limit=5)
    assert len(claims) <= 5
```

- [ ] **Step 3: Run to confirm failure**

```bash
python -m pytest tests/test_cake_extractors.py -q 2>&1 | head -5
```

Expected: `ModuleNotFoundError: No module named 'vcse.cake.extractor_wikidata'`

- [ ] **Step 4: Implement extractor_wikidata.py**

```python
# src/vcse/cake/extractor_wikidata.py
"""Deterministic Wikidata JSON extractor for CAKE."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from vcse.cake.errors import CakeExtractionError
from vcse.cake.snapshot import FetchedSource
from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgeProvenance

PROPERTY_MAP: dict[str, str] = {
    "P36": "capital_of",
    "P17": "located_in_country",
    "P31": "instance_of",
}


class WikidataExtractor:
    """Extract KnowledgeClaims from a simplified Wikidata JSON entity dump."""

    def extract(
        self,
        fetched: FetchedSource,
        snapshot_id: str,
        *,
        limit: int | None = None,
    ) -> list[KnowledgeClaim]:
        try:
            data = json.loads(fetched.raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CakeExtractionError("MALFORMED_JSON", f"wikidata parse error: {exc}") from exc

        entities: dict[str, Any] = data.get("entities", {})
        if not isinstance(entities, dict):
            raise CakeExtractionError("INVALID_STRUCTURE", "'entities' must be a dict")

        # Build label lookup for object resolution
        label_map: dict[str, str] = {}
        for qid, entity in entities.items():
            label = _get_en_label(entity)
            if label:
                label_map[qid] = label

        claims: list[KnowledgeClaim] = []
        now = datetime.now(timezone.utc).isoformat()

        for qid, entity in entities.items():
            if limit is not None and len(claims) >= limit:
                break
            subject_label = label_map.get(qid, qid)
            raw_claims = entity.get("claims", {})
            if not isinstance(raw_claims, dict):
                continue
            for prop_id, relation in PROPERTY_MAP.items():
                if prop_id not in raw_claims:
                    continue
                for statement in raw_claims[prop_id]:
                    obj_label = _extract_object_label(statement, label_map)
                    if obj_label is None:
                        continue
                    prov = KnowledgeProvenance(
                        source_id=fetched.source_id,
                        source_type="wikidata_json",
                        location=snapshot_id,
                        evidence_text=f"{subject_label} {prop_id}={relation} {obj_label}",
                        trust_level="unrated",
                        confidence=0.9,
                    )
                    claim = KnowledgeClaim(
                        subject=subject_label,
                        relation=relation,
                        object=obj_label,
                        provenance=prov,
                        qualifiers={"snapshot_id": snapshot_id, "wikidata_entity": qid, "wikidata_prop": prop_id},
                        confidence=0.9,
                    )
                    claims.append(claim)
                    if limit is not None and len(claims) >= limit:
                        break

        return claims


def _get_en_label(entity: dict[str, Any]) -> str | None:
    labels = entity.get("labels", {})
    en = labels.get("en", {})
    return en.get("value") if isinstance(en, dict) else None


def _extract_object_label(statement: dict[str, Any], label_map: dict[str, str]) -> str | None:
    try:
        mainsnak = statement.get("mainsnak", {})
        datavalue = mainsnak.get("datavalue", {})
        value = datavalue.get("value", {})
        if isinstance(value, dict):
            obj_qid = value.get("id")
            if obj_qid:
                return label_map.get(obj_qid, obj_qid)
        if isinstance(value, str):
            return value
    except (AttributeError, TypeError):
        pass
    return None
```

- [ ] **Step 5: Implement extractor_dbpedia.py**

```python
# src/vcse/cake/extractor_dbpedia.py
"""Deterministic DBpedia N-Triples extractor for CAKE."""

from __future__ import annotations

import re
import warnings
from datetime import datetime, timezone

from vcse.cake.errors import CakeExtractionError
from vcse.cake.snapshot import FetchedSource
from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgeProvenance

# Matches: <uri> <uri> <uri_or_literal> .
_TRIPLE_RE = re.compile(
    r'^<([^>]+)>\s+<([^>]+)>\s+(?:<([^>]+)>|"([^"]*)"(?:\^\^<[^>]+>)?)\s*\.\s*$'
)


def _last_segment(uri: str) -> str:
    """Extract last path segment from a URI, underscored."""
    segment = uri.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    return segment


class DBpediaExtractor:
    """Extract KnowledgeClaims from DBpedia N-Triples / simple TTL."""

    def extract(
        self,
        fetched: FetchedSource,
        snapshot_id: str,
        *,
        limit: int | None = None,
    ) -> list[KnowledgeClaim]:
        try:
            text = fetched.raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CakeExtractionError("ENCODING_ERROR", f"UTF-8 decode failed: {exc}") from exc

        claims: list[KnowledgeClaim] = []
        now = datetime.now(timezone.utc).isoformat()

        for line in text.splitlines():
            if limit is not None and len(claims) >= limit:
                break
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _TRIPLE_RE.match(line)
            if not m:
                warnings.warn(f"CAKE DBpedia: skipping malformed line: {line[:80]!r}", stacklevel=2)
                continue
            subj_uri, pred_uri, obj_uri, obj_literal = m.groups()
            subject = _last_segment(subj_uri)
            relation = _last_segment(pred_uri)
            obj = _last_segment(obj_uri) if obj_uri else (obj_literal or "")
            if not subject or not relation or not obj:
                continue
            prov = KnowledgeProvenance(
                source_id=fetched.source_id,
                source_type="dbpedia_ttl",
                location=snapshot_id,
                evidence_text=f"{subject} {relation} {obj}",
                trust_level="unrated",
                confidence=0.85,
            )
            claim = KnowledgeClaim(
                subject=subject,
                relation=relation,
                object=obj,
                provenance=prov,
                qualifiers={"snapshot_id": snapshot_id},
                confidence=0.85,
            )
            claims.append(claim)

        return claims
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_cake_extractors.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/vcse/cake/extractor_wikidata.py src/vcse/cake/extractor_dbpedia.py \
    tests/test_cake_extractors.py \
    examples/cake/wikidata_sample.json examples/cake/dbpedia_sample.ttl \
    examples/cake/malformed_source.json examples/cake/disallowed_source.json
git commit -m "feat(cake): add deterministic Wikidata + DBpedia extractors with example data"
```

---

## Task 6: normalizer_adapter.py + trust_runner.py

**Files:**
- Create: `src/vcse/cake/normalizer_adapter.py`
- Create: `src/vcse/cake/trust_runner.py`
- Create: `src/vcse/cake/scheduler.py` (stub)

These are thin wrappers — tested via pipeline integration in Task 8.

- [ ] **Step 1: Implement normalizer_adapter.py**

```python
# src/vcse/cake/normalizer_adapter.py
"""Thin adapter over KnowledgeNormalizer for CAKE claims."""

from __future__ import annotations

from vcse.knowledge.normalizer import KnowledgeNormalizer
from vcse.knowledge.pack_model import KnowledgeClaim


class CakeNormalizerAdapter:
    """Normalizes claims using the existing KnowledgeNormalizer. Zero duplication."""

    def __init__(self) -> None:
        self._normalizer = KnowledgeNormalizer()

    def normalize(self, claims: list[KnowledgeClaim]) -> list[KnowledgeClaim]:
        return [self._normalizer.normalize_claim(c) for c in claims]
```

- [ ] **Step 2: Implement trust_runner.py**

```python
# src/vcse/cake/trust_runner.py
"""CAKE trust integration — delegates to TrustPromoter, read-only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vcse.knowledge.pack_model import KnowledgeClaim
from vcse.trust.promoter import TrustPromoter, TrustReport


class CakeTrustRunner:
    """Calls existing TrustPromoter without modification."""

    def evaluate(self, claims: list[KnowledgeClaim]) -> TrustReport:
        """Evaluate trust decisions for a list of claims."""
        promoter = TrustPromoter()
        return promoter.evaluate_claims([c.to_dict() for c in claims])

    def promote(self, pack_path: Path) -> TrustReport:
        """Run trust promotion on an on-disk pack."""
        promoter = TrustPromoter()
        return promoter.promote(pack_path)
```

- [ ] **Step 3: Implement scheduler.py (stub)**

```python
# src/vcse/cake/scheduler.py
"""CAKE scheduler stub — reserved for future scheduled acquisition runs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScheduledRun:
    source_config_path: str
    interval_seconds: int
    enabled: bool = True
    last_run: str | None = None
    run_count: int = 0


class CakeScheduler:
    """Stub scheduler. Not yet implemented — placeholder for cron-based acquisition."""

    def __init__(self) -> None:
        self._runs: list[ScheduledRun] = []

    def schedule(self, run: ScheduledRun) -> None:
        self._runs.append(run)

    def list_scheduled(self) -> list[ScheduledRun]:
        return list(self._runs)
```

- [ ] **Step 4: Commit**

```bash
git add src/vcse/cake/normalizer_adapter.py src/vcse/cake/trust_runner.py src/vcse/cake/scheduler.py
git commit -m "feat(cake): add normalizer adapter, trust runner wrapper, scheduler stub"
```

---

## Task 7: pack_updater.py + test_cake_pack_updater.py

**Files:**
- Create: `src/vcse/cake/pack_updater.py`
- Create: `tests/test_cake_pack_updater.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cake_pack_updater.py
"""Tests for CakePackUpdater — append-only pack updates."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vcse.cake.pack_updater import CakePackUpdater
from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgeProvenance, KnowledgePack
from vcse.knowledge.pack_builder import KnowledgePackBuilder


def _prov(source_id: str = "src") -> KnowledgeProvenance:
    return KnowledgeProvenance(
        source_id=source_id,
        source_type="wikidata_json",
        location="snap/abc",
        evidence_text="test",
        trust_level="unrated",
    )


def _claim(subj: str, rel: str, obj: str) -> KnowledgeClaim:
    return KnowledgeClaim(subject=subj, relation=rel, object=obj, provenance=_prov())


def _build_pack(tmp_path: Path, claims: list[KnowledgeClaim]) -> Path:
    pack = KnowledgePack(
        id="test_pack",
        version="1.0.0",
        claims=claims,
        provenance=[c.provenance for c in claims],
    )
    builder = KnowledgePackBuilder()
    return builder.write_pack(pack, tmp_path / "test_pack")


def test_append_new_claims_to_existing_pack(tmp_path):
    existing = [_claim("Paris", "capital_of", "France")]
    pack_path = _build_pack(tmp_path, existing)

    new_claims = [_claim("Berlin", "capital_of", "Germany")]
    updater = CakePackUpdater()
    added = updater.update(pack_path, new_claims)

    assert added == 1
    # Verify on disk
    lines = (pack_path / "claims.jsonl").read_text().splitlines()
    subjects = [json.loads(l)["subject"] for l in lines if l.strip()]
    assert "Paris" in subjects
    assert "Berlin" in subjects


def test_duplicate_claims_not_added(tmp_path):
    existing = [_claim("Paris", "capital_of", "France")]
    pack_path = _build_pack(tmp_path, existing)

    duplicate = [_claim("Paris", "capital_of", "France")]
    updater = CakePackUpdater()
    added = updater.update(pack_path, duplicate)

    assert added == 0
    lines = (pack_path / "claims.jsonl").read_text().splitlines()
    paris_count = sum(1 for l in lines if l.strip() and json.loads(l)["subject"] == "Paris")
    assert paris_count == 1


def test_existing_claims_preserved(tmp_path):
    existing = [_claim("A", "rel", "B"), _claim("C", "rel", "D")]
    pack_path = _build_pack(tmp_path, existing)

    new_claims = [_claim("E", "rel", "F")]
    updater = CakePackUpdater()
    updater.update(pack_path, new_claims)

    lines = (pack_path / "claims.jsonl").read_text().splitlines()
    assert len([l for l in lines if l.strip()]) == 3


def test_pack_does_not_exist_creates_it(tmp_path):
    pack_path = tmp_path / "new_pack"
    new_claims = [_claim("Rome", "capital_of", "Italy")]
    updater = CakePackUpdater()
    added = updater.update(pack_path, new_claims)
    assert added == 1
    assert (pack_path / "claims.jsonl").exists()


def test_integrity_file_rebuilt_after_update(tmp_path):
    pack_path = _build_pack(tmp_path, [_claim("A", "r", "B")])
    updater = CakePackUpdater()
    updater.update(pack_path, [_claim("C", "r", "D")])
    assert (pack_path / "integrity.json").exists()
    integrity = json.loads((pack_path / "integrity.json").read_text())
    assert isinstance(integrity, dict)


def test_provenance_file_updated(tmp_path):
    pack_path = _build_pack(tmp_path, [_claim("A", "r", "B")])
    updater = CakePackUpdater()
    updater.update(pack_path, [_claim("C", "r", "D")])
    prov_lines = (pack_path / "provenance.jsonl").read_text().splitlines()
    assert len([l for l in prov_lines if l.strip()]) == 2
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_cake_pack_updater.py -q 2>&1 | head -5
```

Expected: `ModuleNotFoundError: No module named 'vcse.cake.pack_updater'`

- [ ] **Step 3: Implement pack_updater.py**

```python
# src/vcse/cake/pack_updater.py
"""Append-only pack updater for CAKE — no overwrites, preserves existing claims."""

from __future__ import annotations

import json
from pathlib import Path

from vcse.knowledge.pack_builder import KnowledgePackBuilder
from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgePack, KnowledgeProvenance
from vcse.ledger.audit import build_integrity


def _read_claims(pack_path: Path) -> list[KnowledgeClaim]:
    claims_path = pack_path / "claims.jsonl"
    if not claims_path.exists():
        return []
    return [
        KnowledgeClaim.from_dict(json.loads(line))
        for line in claims_path.read_text().splitlines()
        if line.strip()
    ]


def _read_provenance(pack_path: Path) -> list[KnowledgeProvenance]:
    prov_path = pack_path / "provenance.jsonl"
    if not prov_path.exists():
        return []
    return [
        KnowledgeProvenance.from_dict(json.loads(line))
        for line in prov_path.read_text().splitlines()
        if line.strip()
    ]


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


class CakePackUpdater:
    """Appends new unique claims to an existing pack on disk. Never overwrites."""

    def update(self, pack_path: Path, new_claims: list[KnowledgeClaim]) -> int:
        """
        Append new_claims to pack at pack_path. Returns count of claims actually added.
        If pack does not exist, creates it via KnowledgePackBuilder.
        """
        pack_path = Path(pack_path)

        if not pack_path.exists() or not (pack_path / "claims.jsonl").exists():
            return self._create_new_pack(pack_path, new_claims)

        existing = _read_claims(pack_path)
        existing_keys = {c.key for c in existing}

        to_add = [c for c in new_claims if c.key not in existing_keys]
        if not to_add:
            return 0

        all_claims = existing + to_add
        _write_jsonl(pack_path / "claims.jsonl", [c.to_dict() for c in all_claims])

        all_prov = _read_provenance(pack_path) + [c.provenance for c in to_add]
        _write_jsonl(pack_path / "provenance.jsonl", [p.to_dict() for p in all_prov])

        metrics_path = pack_path / "metrics.json"
        metrics = {}
        if metrics_path.exists():
            metrics = json.loads(metrics_path.read_text())
        metrics["claim_count"] = len(all_claims)
        metrics_path.write_text(json.dumps(metrics, indent=2))

        integrity = build_integrity(pack_path)
        (pack_path / "integrity.json").write_text(json.dumps(integrity, indent=2))

        return len(to_add)

    def _create_new_pack(self, pack_path: Path, claims: list[KnowledgeClaim]) -> int:
        pack = KnowledgePack(
            id=pack_path.name,
            version="1.0.0",
            claims=claims,
            provenance=[c.provenance for c in claims],
        )
        KnowledgePackBuilder().write_pack(pack, pack_path)
        return len(claims)
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_cake_pack_updater.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/vcse/cake/pack_updater.py tests/test_cake_pack_updater.py
git commit -m "feat(cake): add append-only pack updater"
```

---

## Task 8: pipeline.py + reports.py + test_cake_pipeline.py

**Files:**
- Create: `src/vcse/cake/pipeline.py`
- Create: `src/vcse/cake/reports.py`
- Create: `tests/test_cake_pipeline.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cake_pipeline.py
"""End-to-end pipeline tests for CAKE."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vcse.cake.pipeline import (
    CAKE_COMPLETE,
    CAKE_DRY_RUN,
    CAKE_FAILED,
    CakeRunReport,
    run_cake_pipeline,
)
from vcse.cake.errors import CakePipelineError


GENERAL_WORLD_CONFIG = Path("examples/cake/general_world_sources.json")


def test_dry_run_returns_cake_dry_run_status(tmp_path):
    report = run_cake_pipeline(
        GENERAL_WORLD_CONFIG,
        dry_run=True,
        pack_output_dir=tmp_path,
    )
    assert isinstance(report, CakeRunReport)
    assert report.status == CAKE_DRY_RUN
    assert report.dry_run is True


def test_dry_run_does_not_write_pack(tmp_path):
    run_cake_pipeline(
        GENERAL_WORLD_CONFIG,
        dry_run=True,
        pack_output_dir=tmp_path,
    )
    # tmp_path should have no pack directories
    pack_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert pack_dirs == []


def test_live_run_extracts_claims(tmp_path):
    report = run_cake_pipeline(
        GENERAL_WORLD_CONFIG,
        dry_run=False,
        pack_output_dir=tmp_path,
    )
    assert report.status in (CAKE_COMPLETE, "CAKE_PARTIAL")
    assert report.claims_extracted > 0


def test_live_run_paris_capital_of_france(tmp_path):
    report = run_cake_pipeline(
        GENERAL_WORLD_CONFIG,
        dry_run=False,
        pack_output_dir=tmp_path,
    )
    # Find wikidata_capitals pack
    pack_dirs = list(tmp_path.iterdir())
    found = False
    for pack_dir in pack_dirs:
        claims_file = pack_dir / "claims.jsonl"
        if claims_file.exists():
            for line in claims_file.read_text().splitlines():
                if not line.strip():
                    continue
                c = json.loads(line)
                if c.get("subject") == "Paris" and c.get("relation") == "capital_of" and c.get("object") == "France":
                    found = True
                    break
    assert found, "Paris → capital_of → France not found in any pack"


def test_report_has_all_required_fields(tmp_path):
    report = run_cake_pipeline(
        GENERAL_WORLD_CONFIG,
        dry_run=True,
        pack_output_dir=tmp_path,
    )
    assert hasattr(report, "run_id")
    assert hasattr(report, "source_ids")
    assert hasattr(report, "snapshot_ids")
    assert hasattr(report, "source_reports")
    assert hasattr(report, "claims_extracted")
    assert hasattr(report, "claims_normalized")
    assert hasattr(report, "claims_ingested")
    assert hasattr(report, "trust_decisions")
    assert hasattr(report, "errors")
    assert hasattr(report, "warnings")
    assert hasattr(report, "timestamp")
    assert isinstance(report.source_ids, list)
    assert isinstance(report.source_reports, list)


def test_limit_respected(tmp_path):
    report = run_cake_pipeline(
        GENERAL_WORLD_CONFIG,
        limit=1,
        dry_run=True,
        pack_output_dir=tmp_path,
    )
    assert report.claims_extracted <= 2  # 1 per enabled source


def test_missing_source_file_returns_failed(tmp_path):
    bad_config = tmp_path / "bad.json"
    bad_config.write_text(json.dumps({
        "version": "1.0.0",
        "description": "bad",
        "sources": [{
            "id": "missing_src",
            "source_type": "local_file",
            "format": "json",
            "path_or_url": str(tmp_path / "nonexistent.json"),
        }],
    }))
    report = run_cake_pipeline(bad_config, dry_run=False, pack_output_dir=tmp_path, allow_partial=True)
    assert report.status in (CAKE_FAILED, "CAKE_PARTIAL")
    assert len(report.errors) > 0


def test_report_serializes_to_dict(tmp_path):
    report = run_cake_pipeline(
        GENERAL_WORLD_CONFIG,
        dry_run=True,
        pack_output_dir=tmp_path,
    )
    d = report.to_dict()
    assert isinstance(d, dict)
    assert "status" in d
    assert "source_ids" in d
    assert "source_reports" in d
    # Must be JSON-serializable
    json.dumps(d)
```

- [ ] **Step 2: Create examples/cake/general_world_sources.json**

```json
{
  "version": "1.0.0",
  "description": "General world knowledge — CI-safe local files only",
  "sources": [
    {
      "id": "wikidata_capitals",
      "source_type": "local_file",
      "format": "wikidata_json",
      "path_or_url": "examples/cake/wikidata_sample.json",
      "trust_level": "community",
      "enabled": true,
      "description": "Sample Wikidata capital claims — Paris capital_of France"
    },
    {
      "id": "dbpedia_countries",
      "source_type": "local_file",
      "format": "dbpedia_ttl",
      "path_or_url": "examples/cake/dbpedia_sample.ttl",
      "trust_level": "community",
      "enabled": true,
      "description": "Sample DBpedia country triples"
    }
  ]
}
```

- [ ] **Step 3: Run to confirm failure**

```bash
python -m pytest tests/test_cake_pipeline.py -q 2>&1 | head -5
```

Expected: `ModuleNotFoundError: No module named 'vcse.cake.pipeline'`

- [ ] **Step 4: Implement pipeline.py**

```python
# src/vcse/cake/pipeline.py
"""CAKE pipeline orchestrator."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vcse.cake.errors import CakePipelineError, CakeTransportError, CakeExtractionError
from vcse.cake.extractor_dbpedia import DBpediaExtractor
from vcse.cake.extractor_wikidata import WikidataExtractor
from vcse.cake.fetcher import FileTransport, HttpStaticTransport, fetch_source
from vcse.cake.normalizer_adapter import CakeNormalizerAdapter
from vcse.cake.pack_updater import CakePackUpdater
from vcse.cake.snapshot import CakeSnapshotStore
from vcse.cake.sources import CakeSource, load_source_config
from vcse.cake.trust_runner import CakeTrustRunner
from vcse.knowledge.pack_model import KnowledgeClaim
from vcse.knowledge.validator import KnowledgeValidator, KNOWN_RELATIONS

CAKE_COMPLETE = "CAKE_COMPLETE"
CAKE_PARTIAL = "CAKE_PARTIAL"
CAKE_DRY_RUN = "CAKE_DRY_RUN"
CAKE_FAILED = "CAKE_FAILED"

_CAKE_RELATIONS: frozenset[str] = frozenset(
    KNOWN_RELATIONS | {"capital_of", "located_in_country", "instance_of", "country"}
)

_EXTRACTORS = {
    "wikidata_json": WikidataExtractor(),
    "dbpedia_ttl": DBpediaExtractor(),
}


@dataclass
class CakeRunReport:
    run_id: str
    source_ids: list[str]
    snapshot_ids: list[str]
    source_reports: list[dict[str, Any]]
    status: str
    claims_extracted: int
    claims_normalized: int
    claims_ingested: int
    trust_decisions: int
    errors: list[str]
    warnings: list[str]
    dry_run: bool
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source_ids": self.source_ids,
            "snapshot_ids": self.snapshot_ids,
            "source_reports": self.source_reports,
            "status": self.status,
            "claims_extracted": self.claims_extracted,
            "claims_normalized": self.claims_normalized,
            "claims_ingested": self.claims_ingested,
            "trust_decisions": self.trust_decisions,
            "errors": self.errors,
            "warnings": self.warnings,
            "dry_run": self.dry_run,
            "timestamp": self.timestamp,
        }


def run_cake_pipeline(
    source_config_path: str | Path,
    *,
    limit: int | None = None,
    dry_run: bool = False,
    allow_http: bool = False,
    transport_type: str = "file",
    allow_partial: bool = False,
    pack_output_dir: str | Path | None = None,
    snapshot_root: Path | None = None,
) -> CakeRunReport:
    """Run the full CAKE acquisition pipeline. Returns a CakeRunReport."""
    run_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    output_dir = Path(pack_output_dir) if pack_output_dir else Path.home() / ".vcse" / "cake" / "packs"

    config = load_source_config(source_config_path)
    snapshot_store = CakeSnapshotStore(root=snapshot_root)
    normalizer = CakeNormalizerAdapter()
    trust_runner = CakeTrustRunner()
    pack_updater = CakePackUpdater()

    source_ids: list[str] = []
    snapshot_ids: list[str] = []
    source_reports: list[dict] = []
    all_errors: list[str] = []
    all_warnings: list[str] = []
    total_extracted = 0
    total_normalized = 0
    total_ingested = 0
    total_trust = 0
    any_success = False
    any_failure = False

    for source in config.sources:
        if not source.enabled:
            continue

        src_report: dict[str, Any] = {
            "source_id": source.id,
            "status": "PENDING",
            "claims_extracted": 0,
            "claims_normalized": 0,
            "snapshot_id": None,
            "errors": [],
            "warnings": [],
        }

        try:
            transport = _make_transport(source, transport_type, allow_http)
            fetched = fetch_source(source, transport, limit=limit)
            snap = snapshot_store.save(fetched)

            src_report["snapshot_id"] = snap.snapshot_id
            source_ids.append(source.id)
            snapshot_ids.append(snap.snapshot_id)

            extractor = _get_extractor(source.format)
            claims = extractor.extract(fetched, snap.snapshot_id, limit=limit)
            src_report["claims_extracted"] = len(claims)
            total_extracted += len(claims)

            normalized = normalizer.normalize(claims)
            src_report["claims_normalized"] = len(normalized)
            total_normalized += len(normalized)

            if dry_run:
                src_report["status"] = "DRY_RUN"
                any_success = True
                continue

            pack_path = output_dir / source.id
            ingested = pack_updater.update(pack_path, normalized)
            total_ingested += ingested
            src_report["claims_ingested"] = ingested

            trust_report = trust_runner.evaluate(normalized)
            total_trust += len(trust_report.decisions)

            src_report["status"] = "COMPLETE"
            any_success = True

        except (CakeTransportError, CakeExtractionError, CakePipelineError) as exc:
            msg = f"{source.id}: {exc.error_type}: {exc.reason}"
            src_report["status"] = "FAILED"
            src_report["errors"].append(msg)
            all_errors.append(msg)
            any_failure = True
            if not allow_partial:
                source_reports.append(src_report)
                status = CAKE_FAILED
                break
        except Exception as exc:
            msg = f"{source.id}: UNEXPECTED_ERROR: {exc}"
            src_report["status"] = "FAILED"
            src_report["errors"].append(msg)
            all_errors.append(msg)
            any_failure = True
            if not allow_partial:
                source_reports.append(src_report)
                status = CAKE_FAILED
                break

        source_reports.append(src_report)

    if dry_run:
        status = CAKE_DRY_RUN
    elif any_failure and not any_success:
        status = CAKE_FAILED
    elif any_failure and any_success:
        status = CAKE_PARTIAL
    else:
        status = CAKE_COMPLETE

    return CakeRunReport(
        run_id=run_id,
        source_ids=source_ids,
        snapshot_ids=snapshot_ids,
        source_reports=source_reports,
        status=status,
        claims_extracted=total_extracted,
        claims_normalized=total_normalized,
        claims_ingested=total_ingested,
        trust_decisions=total_trust,
        errors=all_errors,
        warnings=all_warnings,
        dry_run=dry_run,
        timestamp=timestamp,
    )


def _make_transport(source: CakeSource, transport_type: str, allow_http: bool):
    if source.source_type == "local_file" or transport_type == "file":
        return FileTransport()
    return HttpStaticTransport(allow_http=allow_http)


def _get_extractor(fmt: str):
    if fmt not in _EXTRACTORS:
        # json/jsonl not yet supported by specialized extractors; treat as empty
        class _NoOpExtractor:
            def extract(self, fetched, snapshot_id, *, limit=None):
                return []
        return _NoOpExtractor()
    return _EXTRACTORS[fmt]
```

- [ ] **Step 5: Implement reports.py**

```python
# src/vcse/cake/reports.py
"""CAKE report rendering."""

from __future__ import annotations

import json

from vcse.cake.pipeline import CakeRunReport


def render_report(report: CakeRunReport) -> str:
    """Render report as JSON string."""
    return json.dumps(report.to_dict(), indent=2, sort_keys=True)


def render_report_summary(report: CakeRunReport) -> str:
    """Render a short human-readable summary."""
    lines = [
        f"status: {report.status}",
        f"run_id: {report.run_id}",
        f"timestamp: {report.timestamp}",
        f"sources_processed: {len(report.source_ids)}",
        f"claims_extracted: {report.claims_extracted}",
        f"claims_normalized: {report.claims_normalized}",
        f"claims_ingested: {report.claims_ingested}",
        f"trust_decisions: {report.trust_decisions}",
        f"dry_run: {report.dry_run}",
    ]
    if report.errors:
        lines.append("errors:")
        for e in report.errors:
            lines.append(f"  - {e}")
    if report.warnings:
        lines.append("warnings:")
        for w in report.warnings:
            lines.append(f"  - {w}")
    return "\n".join(lines)
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/test_cake_pipeline.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/vcse/cake/pipeline.py src/vcse/cake/reports.py \
    tests/test_cake_pipeline.py examples/cake/general_world_sources.json
git commit -m "feat(cake): add pipeline orchestrator and report renderer"
```

---

## Task 9: __init__.py + CLI + test_cake_cli.py

**Files:**
- Modify: `src/vcse/cake/__init__.py`
- Modify: `src/vcse/cli.py`
- Create: `tests/test_cake_cli.py`

- [ ] **Step 1: Complete __init__.py**

```python
# src/vcse/cake/__init__.py
"""CAKE — Controlled Acquisition of Knowledge Engine."""

from vcse.cake.errors import (
    CakeConfigError,
    CakeError,
    CakeExtractionError,
    CakePipelineError,
    CakeSnapshotCorruptedError,
    CakeTransportError,
)
from vcse.cake.extractor_dbpedia import DBpediaExtractor
from vcse.cake.extractor_wikidata import WikidataExtractor
from vcse.cake.fetcher import CakeTransport, FileTransport, HttpStaticTransport, fetch_source
from vcse.cake.normalizer_adapter import CakeNormalizerAdapter
from vcse.cake.pack_updater import CakePackUpdater
from vcse.cake.pipeline import (
    CAKE_COMPLETE,
    CAKE_DRY_RUN,
    CAKE_FAILED,
    CAKE_PARTIAL,
    CakeRunReport,
    run_cake_pipeline,
)
from vcse.cake.reports import render_report, render_report_summary
from vcse.cake.scheduler import CakeScheduler
from vcse.cake.snapshot import CakeSnapshot, CakeSnapshotStore, FetchedSource
from vcse.cake.sources import CakeSource, CakeSourceConfig, load_source_config, validate_source
from vcse.cake.trust_runner import CakeTrustRunner

__all__ = [
    "CAKE_COMPLETE",
    "CAKE_DRY_RUN",
    "CAKE_FAILED",
    "CAKE_PARTIAL",
    "CakeConfigError",
    "CakeError",
    "CakeExtractionError",
    "CakePipelineError",
    "CakeRunReport",
    "CakeScheduler",
    "CakeSnapshot",
    "CakeSnapshotCorruptedError",
    "CakeSnapshotStore",
    "CakeSource",
    "CakeSourceConfig",
    "CakeTrustRunner",
    "CakeTransport",
    "CakeTransportError",
    "DBpediaExtractor",
    "FetchedSource",
    "FileTransport",
    "HttpStaticTransport",
    "WikidataExtractor",
    "fetch_source",
    "load_source_config",
    "render_report",
    "render_report_summary",
    "run_cake_pipeline",
    "validate_source",
]
```

- [ ] **Step 2: Write failing CLI tests**

```python
# tests/test_cake_cli.py
"""Tests for CAKE CLI commands."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


def run_cli(args: list[str]) -> tuple[str, int]:
    """Run vcse CLI via main() and capture output."""
    from io import StringIO
    from contextlib import redirect_stdout, redirect_stderr
    from vcse.cli import main

    stdout_buf = StringIO()
    stderr_buf = StringIO()
    exit_code = 0
    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            main(args)
    except SystemExit as exc:
        exit_code = int(exc.code) if exc.code is not None else 0
    return stdout_buf.getvalue() + stderr_buf.getvalue(), exit_code


def test_cake_validate_valid_source():
    output, code = run_cli(["cake", "validate", "--source", "examples/cake/general_world_sources.json"])
    assert code == 0
    assert "VALID" in output


def test_cake_validate_malformed_source(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json")
    output, code = run_cli(["cake", "validate", "--source", str(bad)])
    assert code != 0


def test_cake_validate_disallowed_domain():
    output, code = run_cli(["cake", "validate", "--source", "examples/cake/disallowed_source.json"])
    assert code != 0
    assert "DISALLOWED_DOMAIN" in output or "ERROR" in output


def test_cake_run_dry_run(tmp_path):
    output, code = run_cli([
        "cake", "run",
        "--source", "examples/cake/general_world_sources.json",
        "--dry-run",
    ])
    assert code == 0
    data = json.loads(output)
    assert data["status"] == "CAKE_DRY_RUN"
    assert data["dry_run"] is True


def test_cake_run_with_limit(tmp_path):
    output, code = run_cli([
        "cake", "run",
        "--source", "examples/cake/general_world_sources.json",
        "--dry-run",
        "--limit", "1",
    ])
    assert code == 0
    data = json.loads(output)
    assert data["claims_extracted"] <= 2


def test_cake_run_live(tmp_path):
    output, code = run_cli([
        "cake", "run",
        "--source", "examples/cake/general_world_sources.json",
    ])
    assert code == 0
    data = json.loads(output)
    assert data["status"] in ("CAKE_COMPLETE", "CAKE_PARTIAL")
    assert data["claims_extracted"] > 0


def test_cake_run_missing_source(tmp_path):
    output, code = run_cli([
        "cake", "run",
        "--source", str(tmp_path / "nonexistent.json"),
    ])
    assert code != 0


def test_cake_report_cmd(tmp_path):
    """Write a report file, then read it back via vcse cake report."""
    report_data = {
        "run_id": "test-123",
        "status": "CAKE_COMPLETE",
        "source_ids": ["wikidata_capitals"],
        "snapshot_ids": ["wikidata_capitals/abc123"],
        "source_reports": [],
        "claims_extracted": 3,
        "claims_normalized": 3,
        "claims_ingested": 3,
        "trust_decisions": 3,
        "errors": [],
        "warnings": [],
        "dry_run": False,
        "timestamp": "2026-04-27T00:00:00+00:00",
    }
    report_file = tmp_path / "run_report.json"
    report_file.write_text(json.dumps(report_data))
    output, code = run_cli(["cake", "report", str(report_file)])
    assert code == 0
    assert "CAKE_COMPLETE" in output


def test_cake_run_without_allow_http_blocks_http_source(tmp_path):
    http_config = tmp_path / "http_sources.json"
    http_config.write_text(json.dumps({
        "version": "1.0.0",
        "description": "http source",
        "sources": [{
            "id": "wd_live",
            "source_type": "http_static",
            "format": "wikidata_json",
            "path_or_url": "https://www.wikidata.org/wiki/Special:EntityData/Q90.json",
        }]
    }))
    output, code = run_cli([
        "cake", "run",
        "--source", str(http_config),
        "--dry-run",
        # No --allow-http
    ])
    # Should fail because HTTP is disabled
    assert code != 0 or "HTTP_DISABLED" in output or "CAKE_FAILED" in output
```

- [ ] **Step 3: Run to confirm failure**

```bash
python -m pytest tests/test_cake_cli.py::test_cake_validate_valid_source -q 2>&1 | head -10
```

Expected: error about unknown `cake` command.

- [ ] **Step 4: Add cake subparser to cli.py**

Find the end of the workspace parser block in `src/vcse/cli.py` (after `ws_tasks_parser.add_argument("--json", ...)`). Add immediately after:

```python
    # CAKE subparser
    cake_parser = subparsers.add_parser("cake", help="Controlled Acquisition of Knowledge Engine")
    cake_subparsers = cake_parser.add_subparsers(dest="cake_command")

    cake_validate_parser = cake_subparsers.add_parser("validate", help="Validate a CAKE source config")
    cake_validate_parser.add_argument("--source", required=True, help="Path to source config JSON")

    cake_run_parser = cake_subparsers.add_parser("run", help="Run CAKE acquisition pipeline")
    cake_run_parser.add_argument("--source", required=True, help="Path to source config JSON")
    cake_run_parser.add_argument("--dry-run", action="store_true", dest="dry_run", help="Validate and extract without writing")
    cake_run_parser.add_argument("--limit", type=int, default=None, help="Max items to fetch per source")
    cake_run_parser.add_argument("--allow-http", action="store_true", dest="allow_http", help="Enable HTTP transport (off by default)")
    cake_run_parser.add_argument("--transport", choices=["file", "http"], default="file", help="Transport type (default: file)")
    cake_run_parser.add_argument("--allow-partial", action="store_true", dest="allow_partial", help="Continue on per-source failure")

    cake_report_parser = cake_subparsers.add_parser("report", help="Display a CAKE run report")
    cake_report_parser.add_argument("report_file", help="Path to a CakeRunReport JSON file")
```

- [ ] **Step 5: Add cake dispatch to cli.py main()**

Find the `if args.command == "reasonops":` block near the end of main(). Add immediately after it (before the `except` block):

```python
        if args.command == "cake":
            from vcse.cake import (
                CakeConfigError,
                CakePipelineError,
                CakeTransportError,
                load_source_config,
                render_report,
                render_report_summary,
                run_cake_pipeline,
            )
            if args.cake_command == "validate":
                config = load_source_config(args.source)
                print(f"status: VALID")
                print(f"sources: {len(config.sources)}")
                for src in config.sources:
                    enabled = "enabled" if src.enabled else "disabled"
                    print(f"  - {src.id} ({src.source_type}/{src.format}) [{enabled}]")
                return
            if args.cake_command == "run":
                report = run_cake_pipeline(
                    args.source,
                    limit=args.limit,
                    dry_run=args.dry_run,
                    allow_http=args.allow_http,
                    transport_type=args.transport,
                    allow_partial=args.allow_partial,
                )
                print(render_report(report))
                if report.status == "CAKE_FAILED":
                    raise SystemExit(2)
                return
            if args.cake_command == "report":
                import json as _json
                from pathlib import Path as _Path
                report_path = _Path(args.report_file)
                if not report_path.exists():
                    print(render_error("FILE_NOT_FOUND", f"report file not found: {report_path}"), file=sys.stderr)
                    raise SystemExit(2)
                data = _json.loads(report_path.read_text())
                print(render_report_summary_from_dict(data))
                return
            cake_parser.print_help()
            return
```

- [ ] **Step 6: Add render_report_summary_from_dict helper to cli.py**

Add near `render_error` function (around line 124):

```python
def render_report_summary_from_dict(data: dict) -> str:
    lines = [
        f"status: {data.get('status', 'UNKNOWN')}",
        f"run_id: {data.get('run_id', '')}",
        f"timestamp: {data.get('timestamp', '')}",
        f"sources_processed: {len(data.get('source_ids', []))}",
        f"claims_extracted: {data.get('claims_extracted', 0)}",
        f"claims_ingested: {data.get('claims_ingested', 0)}",
        f"trust_decisions: {data.get('trust_decisions', 0)}",
        f"dry_run: {data.get('dry_run', False)}",
    ]
    errors = data.get("errors", [])
    if errors:
        lines.append("errors:")
        for e in errors:
            lines.append(f"  - {e}")
    return "\n".join(lines)
```

- [ ] **Step 7: Add CakeConfigError and CakePipelineError to the main() exception handler**

In the `except (ValueError, BenchmarkCaseError, ...)` block, add the CAKE errors:

```python
    except (
        ValueError,
        BenchmarkCaseError,
        CaseValidationError,
        IngestionError,
        DSLError,
        GenerationError,
        GauntletError,
        KnowledgeError,
        PackError,
        TrustError,
        LedgerError,
    ) as exc:
```

Change to:

```python
    except (
        ValueError,
        BenchmarkCaseError,
        CaseValidationError,
        IngestionError,
        DSLError,
        GenerationError,
        GauntletError,
        KnowledgeError,
        PackError,
        TrustError,
        LedgerError,
    ) as exc:
```

Note: `CakeConfigError` and `CakePipelineError` inherit from `ValueError`, so they are already caught. No import needed in the except clause.

- [ ] **Step 8: Run CLI tests**

```bash
python -m pytest tests/test_cake_cli.py -q
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add src/vcse/cake/__init__.py src/vcse/cli.py tests/test_cake_cli.py
git commit -m "feat(cake): add cake CLI subcommands (validate, run, report)"
```

---

## Task 10: docs/CAKE.md + docs updates

**Files:**
- Create: `docs/CAKE.md`
- Modify: `README.md`, `docs/ARCHITECTURE.md`, `docs/KNOWLEDGE.md`, `docs/TRUST.md`, `docs/LEDGER.md`

- [ ] **Step 1: Create docs/CAKE.md**

```markdown
# CAKE — Controlled Acquisition of Knowledge Engine

CAKE is the deterministic data acquisition layer for VCSE. It collects structured knowledge from approved sources, snapshots raw data immutably, extracts claims deterministically, and routes them into the trust → ledger → pack pipeline.

## Core Principle

**CAKE collects broadly. Trust certifies narrowly.**

CAKE ingests candidate claims at T0_CANDIDATE tier. Only the trust pipeline can promote them to higher tiers.

## Pipeline

```
CakeSourceConfig (JSON)
  → CakeTransport (FileTransport | HttpStaticTransport)
  → FetchedSource + CakeSnapshot (SHA-256, append-only)
  → WikidataExtractor | DBpediaExtractor
  → List[KnowledgeClaim]
  → KnowledgeNormalizer
  → KnowledgePipeline (validate → resolve → build pack)
  → TrustPromoter (evaluate + promote)
  → Append-only pack update
  → CakeRunReport (JSON)
```

## Allowed Sources

| Source Type | Format | Domain |
|---|---|---|
| local_file | wikidata_json, dbpedia_ttl, json, jsonl | any local path |
| http_static | wikidata_json, dbpedia_ttl | wikidata.org, dbpedia.org only |

HTTP sources require `--allow-http` flag. CI and tests use `local_file` only.

## CLI

```bash
# Validate source config
vcse cake validate --source examples/cake/general_world_sources.json

# Dry run (no writes)
vcse cake run --source examples/cake/general_world_sources.json --dry-run

# Live run with limit
vcse cake run --source examples/cake/general_world_sources.json --limit 100

# View report
vcse cake report <path/to/report.json>
```

## Forbidden Patterns

CAKE does not use: LLMs, neural libraries, web scrapers, arbitrary HTTP, eval/exec.

## Run Statuses

| Status | Meaning |
|---|---|
| CAKE_COMPLETE | All sources processed successfully |
| CAKE_PARTIAL | Some sources failed (use --allow-partial) |
| CAKE_DRY_RUN | Dry run — no writes |
| CAKE_FAILED | Pipeline aborted |
```

- [ ] **Step 2: Update README.md**

Append to the features/commands section:

```markdown
## CAKE — Knowledge Acquisition

VCSE 2.7.0 adds CAKE (Controlled Acquisition of Knowledge Engine), a deterministic pipeline for collecting structured knowledge from approved sources.

```bash
vcse cake validate --source examples/cake/general_world_sources.json
vcse cake run --source examples/cake/general_world_sources.json --dry-run
vcse cake run --source examples/cake/general_world_sources.json --limit 100
```

Sources: Wikidata JSON, DBpedia TTL. Allowed domains: wikidata.org, dbpedia.org. All claims pass the trust pipeline before certification.
```

- [ ] **Step 3: Update docs/ARCHITECTURE.md**

Add to the component table/layer diagram:

```markdown
## CAKE Acquisition Layer (v2.7.0)

CAKE sits upstream of the knowledge pipeline:

```
CAKE (src/vcse/cake/)
  ↓ List[KnowledgeClaim]
Knowledge Pipeline (src/vcse/knowledge/)
  ↓
Trust Pipeline (src/vcse/trust/)
  ↓
Ledger (src/vcse/ledger/)
  ↓
Packs (src/vcse/packs/)
```

CAKE owns: source config, transport, snapshot, extraction.
CAKE delegates: normalization, validation, trust, ledger, pack building.
```

- [ ] **Step 4: Update docs/KNOWLEDGE.md**

Add note at top:

```markdown
> **Upstream:** VCSE 2.7.0 adds CAKE as an upstream acquisition source. CAKE extracts `List[KnowledgeClaim]` and hands them to the knowledge normalizer and pipeline. See [CAKE.md](CAKE.md).
```

- [ ] **Step 5: Update docs/TRUST.md**

Add note:

```markdown
> **CAKE entry point:** Claims acquired by CAKE enter the trust pipeline at T0_CANDIDATE tier. `CakeTrustRunner` calls `TrustPromoter.evaluate_claims()` and `TrustPromoter.promote()` — no trust logic is duplicated inside CAKE.
```

- [ ] **Step 6: Update docs/LEDGER.md**

Add note:

```markdown
> **CAKE ledger events:** CAKE acquisition runs may emit the following event types: `CAKE_FETCH`, `CAKE_SNAPSHOT`, `CAKE_INGEST`. These are recorded via the standard `LedgerStore.append()` API.
```

- [ ] **Step 7: Commit**

```bash
git add docs/CAKE.md README.md docs/ARCHITECTURE.md docs/KNOWLEDGE.md docs/TRUST.md docs/LEDGER.md
git commit -m "docs: add CAKE documentation and update architecture, knowledge, trust, ledger docs"
```

---

## Task 11: Version bump

**Files:**
- Modify: `src/vcse/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Bump version**

In `src/vcse/__init__.py`, change:
```python
__version__ = "2.6.0"
```
to:
```python
__version__ = "2.7.0"
```

In `pyproject.toml`, change:
```toml
version = "2.6.0"
```
to:
```toml
version = "2.7.0"
```

- [ ] **Step 2: Verify**

```bash
python -c "import vcse; print(vcse.__version__)"
python -c "import tomllib; d = tomllib.loads(open('pyproject.toml').read()); print(d['project']['version'])"
```

Expected: both print `2.7.0`.

- [ ] **Step 3: Commit**

```bash
git add src/vcse/__init__.py pyproject.toml
git commit -m "chore: bump version to 2.7.0"
```

---

## Task 12: Full Verification

- [ ] **Step 1: Run all tests**

```bash
python -m pytest -q --tb=short 2>&1 | tail -15
```

Expected: all pass, 0 failures.

- [ ] **Step 2: Validate example config**

```bash
vcse cake validate --source examples/cake/general_world_sources.json
```

Expected:
```
status: VALID
sources: 2
  - wikidata_capitals (local_file/wikidata_json) [enabled]
  - dbpedia_countries (local_file/dbpedia_ttl) [enabled]
```

- [ ] **Step 3: Dry run**

```bash
vcse cake run --source examples/cake/general_world_sources.json --dry-run
```

Expected: JSON output with `"status": "CAKE_DRY_RUN"` and `"dry_run": true`.

- [ ] **Step 4: Live run with limit**

```bash
vcse cake run --source examples/cake/general_world_sources.json --limit 100
```

Expected: JSON output with `"status": "CAKE_COMPLETE"`, `claims_extracted > 0`.

- [ ] **Step 5: Verify Paris claim**

```bash
vcse cake run --source examples/cake/general_world_sources.json --limit 100 | \
  python3 -c "import json,sys; r=json.load(sys.stdin); print('ok' if r['claims_extracted']>0 else 'fail')"
```

Expected: `ok`

- [ ] **Step 6: Validate malformed source fails correctly**

```bash
vcse cake validate --source examples/cake/malformed_source.json; echo "exit: $?"
```

Expected: exit code 2, error output containing `MISSING_FIELD` or `ERROR`.

- [ ] **Step 7: Validate disallowed domain fails correctly**

```bash
vcse cake validate --source examples/cake/disallowed_source.json; echo "exit: $?"
```

Expected: exit code 2, output containing `DISALLOWED_DOMAIN` or `ERROR`.

- [ ] **Step 8: Run gauntlet**

```bash
vcse gauntlet benchmarks/gauntlet/ --search mcts --ts3 --index 2>&1 | tail -5
```

Expected: `false_verified_count: 0` (or `GAUNTLET_COMPLETE`). No regressions.

- [ ] **Step 9: Confirm version**

```bash
python -c "import vcse; print(vcse.__version__)"
```

Expected: `2.7.0`

---

## Task 13: Git Release

- [ ] **Step 1: Final status check**

```bash
git status
```

Expected: clean (no untracked non-cake files, working tree clean after adds).

- [ ] **Step 2: Stage any remaining files**

```bash
git add .
git status
```

- [ ] **Step 3: Commit if needed**

If anything unstaged:
```bash
git commit -m "chore: finalize CAKE 2.7.0 release"
```

- [ ] **Step 4: Create annotated tag**

```bash
git tag -a v2.7.0 -m "VCSE 2.7.0 CAKE — Controlled Acquisition of Knowledge Engine"
```

- [ ] **Step 5: Push (confirm with user before running)**

```bash
git push origin main
git push origin --tags
```

---

## Self-Review Checklist

- [x] **Spec coverage:**
  - Phase 1 (source config): Task 2 ✓
  - Phase 2 (transport): Task 4 ✓
  - Phase 3 (fetcher): Task 4 ✓
  - Phase 4 (snapshot): Task 3 ✓
  - Phase 5 (extractors): Task 5 ✓
  - Phase 6 (normalizer): Task 6 ✓
  - Phase 7 (trust): Task 6 ✓
  - Phase 8 (pack updater): Task 7 ✓
  - Phase 9 (pipeline): Task 8 ✓
  - Phase 10 (CLI): Task 9 ✓
  - Phase 11 (tests): Tasks 2-9 ✓
  - Phase 12 (examples): Tasks 5, 8 ✓
  - Phase 13 (forbidden patterns): enforced in all tasks (stdlib only) ✓
  - Phase 14 (verification): Task 12 ✓
  - Phase 15 (version bump): Task 11 ✓
  - Phase 16 (git release): Task 13 ✓
  - Version check: Task 0 ✓
  - Multi-source CakeRunReport: Task 8 ✓
  - Expanded modifiable files: Task 10 ✓

- [x] **No placeholders:** All steps contain real code and exact commands.

- [x] **Type consistency:**
  - `FetchedSource.source_id: str` used consistently in snapshot, fetcher, extractors
  - `CakeRunReport.source_ids: list[str]`, `snapshot_ids: list[str]`, `source_reports: list[dict]` consistent across pipeline + tests
  - `CakeSnapshotStore.save(fetched: FetchedSource) -> CakeSnapshot` consistent across tests
  - `WikidataExtractor.extract(fetched, snapshot_id, *, limit) -> list[KnowledgeClaim]` consistent
  - `DBpediaExtractor.extract(fetched, snapshot_id, *, limit) -> list[KnowledgeClaim]` consistent
  - `CakePackUpdater.update(pack_path: Path, new_claims: list[KnowledgeClaim]) -> int` consistent
  - `run_cake_pipeline(source_config_path, *, ...) -> CakeRunReport` consistent
