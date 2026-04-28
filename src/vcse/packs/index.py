"""Claim-level index for knowledge packs."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


def _pack_home() -> Path:
    base = os.getenv("VCSE_PACK_HOME")
    if base:
        return Path(base).expanduser()
    return Path.home() / ".vcse"


def _default_index_path() -> Path:
    return _pack_home() / "packs" / "index.json"


class PackIndexError(ValueError):
    def __init__(self, error_type: str, reason: str) -> None:
        super().__init__(f"{error_type}: {reason}")
        self.error_type = error_type
        self.reason = reason


def _parse_semver(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise PackIndexError("INVALID_SEMVER", f"invalid semantic version: {value}")
    return int(parts[0]), int(parts[1]), int(parts[2])


class PackIndex:
    def __init__(self, index_path: Path | None = None) -> None:
        self.index_path = Path(index_path) if index_path else _default_index_path()
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

    def load_index(self) -> dict[str, dict]:
        if not self.index_path.exists():
            return {}
        try:
            payload = json.loads(self.index_path.read_text())
        except json.JSONDecodeError as exc:
            raise PackIndexError("CORRUPTED_INDEX", f"malformed JSON in {self.index_path}") from exc
        if not isinstance(payload, dict):
            raise PackIndexError("CORRUPTED_INDEX", "index root must be an object")
        for key, value in payload.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                raise PackIndexError("CORRUPTED_INDEX", "index entries must be object values")
        return payload

    def _save_index(self, payload: dict[str, dict]) -> None:
        with NamedTemporaryFile("w", delete=False, dir=self.index_path.parent) as tmp:
            json.dump(payload, tmp, indent=2, sort_keys=True)
            tmp.write("\n")
            tmp_path = Path(tmp.name)
        tmp_path.replace(self.index_path)

    def _entry_from_pack_path(self, pack_path: Path) -> tuple[str, dict[str, Any]]:
        pack_json = pack_path / "pack.json"
        claims_jsonl = pack_path / "claims.jsonl"
        if not pack_json.exists() or not claims_jsonl.exists():
            raise PackIndexError("INVALID_PACK", f"missing pack.json or claims.jsonl in {pack_path}")

        meta = json.loads(pack_json.read_text())
        if not isinstance(meta, dict):
            raise PackIndexError("INVALID_PACK", f"pack metadata must be object: {pack_json}")

        pack_id = str(meta.get("id", "")).strip()
        version = str(meta.get("version", "")).strip()
        if not pack_id or not version:
            raise PackIndexError("INVALID_PACK", f"pack id/version missing in {pack_json}")

        claims: list[dict[str, Any]] = []
        for line in claims_jsonl.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                claims.append(row)

        claim_count = len(claims)
        certified_count = sum(1 for claim in claims if claim.get("trust_tier") == "T5_CERTIFIED")
        candidate_count = claim_count - certified_count

        source_ids = sorted(
            {
                str(source_id)
                for claim in claims
                for source_id in claim.get("source_ids", [])
                if str(source_id).strip()
            }
        )
        if not source_ids:
            fallback = meta.get("source_ids", [])
            if isinstance(fallback, list):
                source_ids = sorted({str(item) for item in fallback if str(item).strip()})

        lifecycle_status = str(meta.get("lifecycle_status", "candidate")).strip() or "candidate"
        metrics_path = pack_path / "metrics.json"
        metrics_payload: dict[str, Any] = {}
        if metrics_path.exists():
            try:
                loaded = json.loads(metrics_path.read_text())
                if isinstance(loaded, dict):
                    metrics_payload = loaded
            except Exception:
                metrics_payload = {}

        uncompressed_size = int(
            metrics_payload.get("original_size_bytes", 0) or meta.get("uncompressed_size", 0) or 0
        )
        compressed_size = int(
            metrics_payload.get("total_compressed_size_bytes", 0) or meta.get("compressed_size", 0) or 0
        )
        ratio = (
            float(metrics_payload.get("compression_ratio"))
            if metrics_payload.get("compression_ratio") is not None
            else float(meta.get("compression_ratio", 0.0) or 0.0)
        )
        key = f"{pack_id}@{version}"
        last_updated = datetime.now(timezone.utc).isoformat()
        entry = {
            "pack_id": pack_id,
            "version": version,
            "domain": str(meta.get("domain", "general")),
            "lifecycle_status": lifecycle_status,
            "claim_count": claim_count,
            "certified_count": certified_count,
            "candidate_count": candidate_count,
            "source_ids": source_ids,
            "last_updated": last_updated,
            "pack_path": str(pack_path),
            "stale": False,
            "pack_hash": str(meta.get("pack_hash", "")),
            "merkle_root": str(meta.get("merkle_root", "")),
            "compression_ratio": ratio,
            "compressed_size": compressed_size,
            "uncompressed_size": uncompressed_size,
        }
        return key, entry

    def build_index(self, scan_dirs: list[Path]) -> None:
        index = self.load_index()
        for scan_dir in scan_dirs:
            root = Path(scan_dir)
            if not root.exists() or not root.is_dir():
                continue
            for child in sorted(path for path in root.iterdir() if path.is_dir()):
                if not (child / "pack.json").exists() or not (child / "claims.jsonl").exists():
                    continue
                key, entry = self._entry_from_pack_path(child)
                index[key] = entry

        for key, entry in index.items():
            pack_path = Path(str(entry.get("pack_path", "")))
            entry["stale"] = not pack_path.exists()
        self._save_index(index)

    def update_entry(self, pack_path: Path) -> None:
        index = self.load_index()
        key, entry = self._entry_from_pack_path(Path(pack_path))
        index[key] = entry
        self._save_index(index)

    def list_packs(self, include_stale: bool = False) -> list[dict]:
        entries = list(self.load_index().values())
        if not include_stale:
            entries = [entry for entry in entries if not bool(entry.get("stale"))]
        return sorted(entries, key=lambda item: (str(item.get("pack_id", "")), str(item.get("version", ""))))

    def get_pack_metadata(self, pack_id_version: str) -> dict:
        index = self.load_index()
        if "@" in pack_id_version:
            item = index.get(pack_id_version)
            if item is None:
                raise PackIndexError("PACK_NOT_FOUND", f"pack not found: {pack_id_version}")
            return item

        candidates = [value for value in index.values() if value.get("pack_id") == pack_id_version]
        if not candidates:
            raise PackIndexError("PACK_NOT_FOUND", f"pack not found: {pack_id_version}")
        non_stale = [item for item in candidates if not bool(item.get("stale"))]
        if non_stale:
            candidates = non_stale
        return sorted(candidates, key=lambda item: _parse_semver(str(item.get("version", "0.0.0"))), reverse=True)[0]
