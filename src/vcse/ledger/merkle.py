"""Merkle pack integrity utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vcse.ledger.hashing import hash_bytes, sha256_hex


@dataclass(frozen=True)
class MerkleIntegrityReport:
    artifact_hashes: dict[str, str]
    merkle_root: str
    generated_at: str

    def to_dict(self) -> dict[str, str | dict[str, str]]:
        return {
            "artifact_hashes": dict(self.artifact_hashes),
            "merkle_root": self.merkle_root,
            "generated_at": self.generated_at,
        }


def build_merkle_root(hashes: list[str]) -> str:
    if not hashes:
        return sha256_hex("")
    level = list(hashes)
    while len(level) > 1:
        next_level: list[str] = []
        for idx in range(0, len(level), 2):
            left = level[idx]
            right = level[idx + 1] if idx + 1 < len(level) else left
            next_level.append(sha256_hex(left + right))
        level = next_level
    return level[0]


def pack_integrity_report(pack_path: str | Path, artifacts: list[str], algorithm: str = "sha256") -> MerkleIntegrityReport:
    from datetime import datetime, timezone

    root = Path(pack_path)
    artifact_hashes: dict[str, str] = {}
    hashes: list[str] = []
    for rel in artifacts:
        path = root / rel
        if not path.exists():
            raise FileNotFoundError(f"missing artifact for integrity: {rel}")
        digest = hash_bytes(path.read_bytes(), algorithm=algorithm)
        artifact_hashes[rel] = digest
        hashes.append(digest)
    hashes.sort()
    return MerkleIntegrityReport(
        artifact_hashes=artifact_hashes,
        merkle_root=build_merkle_root(hashes),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
