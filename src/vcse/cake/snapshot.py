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