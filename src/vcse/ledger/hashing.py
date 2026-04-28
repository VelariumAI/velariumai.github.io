"""Hashing helpers for ledger/integrity."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_event(previous_hash: str, payload: dict[str, Any]) -> str:
    return sha256_hex(canonical_json({"previous_hash": previous_hash, "payload": payload}))


def hash_bytes(data: bytes, algorithm: str = "sha256") -> str:
    if algorithm == "sha256":
        return hashlib.sha256(data).hexdigest()
    if algorithm == "blake3":
        try:
            import blake3  # type: ignore
        except Exception:
            return hashlib.sha256(data).hexdigest()
        return blake3.blake3(data).hexdigest()
    raise ValueError(f"unsupported hash algorithm: {algorithm}")
