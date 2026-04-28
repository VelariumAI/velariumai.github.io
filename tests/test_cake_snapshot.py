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