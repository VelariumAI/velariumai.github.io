"""Deterministic pack integrity, hashing, diffing, and signatures."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from vcse.ledger.hashing import canonical_json, hash_bytes, sha256_hex
from vcse.ledger.merkle import build_merkle_root

VOLATILE_PACK_FIELDS = {
    "pack_hash",
    "hash_algorithm",
    "merkle_root",
    "source_snapshot",
}


@dataclass(frozen=True)
class PackHashResult:
    pack_hash: str
    algorithm: str


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def _canonical_jsonl(path: Path) -> str:
    rows: list[str] = []
    if not path.exists():
        return ""
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        rows.append(canonical_json(obj))
    rows.sort()
    return "\n".join(rows) + ("\n" if rows else "")


def _normalized_pack_metadata(path: Path) -> dict[str, Any]:
    meta = _read_json(path)
    return {k: v for k, v in meta.items() if k not in VOLATILE_PACK_FIELDS}


def compute_pack_hash(pack_path: str | Path) -> PackHashResult:
    root = Path(pack_path)
    claims = _canonical_jsonl(root / "claims.jsonl")
    provenance = _canonical_jsonl(root / "provenance.jsonl")
    metadata = canonical_json(_normalized_pack_metadata(root / "pack.json"))
    payload = canonical_json(
        {
            "claims_jsonl": claims,
            "provenance_jsonl": provenance,
            "pack_json": metadata,
        }
    )
    return PackHashResult(pack_hash=sha256_hex(payload), algorithm="sha256")


def _file_hash(path: Path) -> str:
    return f"sha256:{hash_bytes(path.read_bytes(), algorithm='sha256')}"


def _manifest_file_hash(path: Path, name: str) -> str:
    # Avoid self-referential cycles: merkle_root is stored in pack.json.
    if name == "pack.json":
        meta = _read_json(path)
        normalized = dict(meta)
        normalized.pop("merkle_root", None)
        payload = canonical_json(normalized).encode("utf-8")
        return f"sha256:{hash_bytes(payload, algorithm='sha256')}"
    return _file_hash(path)


def _hash_leaf_values(file_hashes: dict[str, str]) -> str:
    leaves = [value.split(":", 1)[1] for _, value in sorted(file_hashes.items())]
    return f"sha256:{build_merkle_root(leaves)}"


def build_manifest(pack_path: str | Path) -> dict[str, Any]:
    root = Path(pack_path)
    files = {
        "claims.jsonl": _manifest_file_hash(root / "claims.jsonl", "claims.jsonl"),
        "provenance.jsonl": _manifest_file_hash(root / "provenance.jsonl", "provenance.jsonl"),
        "pack.json": _manifest_file_hash(root / "pack.json", "pack.json"),
    }
    return {
        "files": files,
        "merkle_root": _hash_leaf_values(files),
        "algorithm": "sha256",
    }


def _build_source_snapshot(pack_path: str | Path) -> dict[str, Any]:
    root = Path(pack_path)
    claims_path = root / "claims.jsonl"
    by_source: dict[str, dict[str, Any]] = {}
    if claims_path.exists():
        for line in claims_path.read_text().splitlines():
            if not line.strip():
                continue
            claim = json.loads(line)
            prov = claim.get("provenance", {}) if isinstance(claim.get("provenance"), dict) else {}
            source_id = str(prov.get("source_id", claim.get("source_id", "unknown"))).strip() or "unknown"
            location = str(prov.get("location", "")).strip()
            bucket = by_source.setdefault(source_id, {"source_id": source_id, "locations": set(), "record_count": 0})
            bucket["record_count"] += 1
            if location:
                bucket["locations"].add(location)

    sources: list[dict[str, Any]] = []
    for source_id in sorted(by_source):
        bucket = by_source[source_id]
        locations = sorted(bucket["locations"])
        hash_input = canonical_json({"source_id": source_id, "locations": locations, "record_count": bucket["record_count"]})
        source_hash = f"sha256:{sha256_hex(hash_input)}"
        sources.append(
            {
                "source_id": source_id,
                "hash": source_hash,
                "record_count": int(bucket["record_count"]),
            }
        )
    source_leaves = [entry["hash"].split(":", 1)[1] for entry in sources]
    merkle_root = f"sha256:{build_merkle_root(source_leaves)}"
    return {
        "sources": sources,
        "merkle_root": merkle_root,
    }


def update_pack_integrity_metadata(pack_path: str | Path) -> dict[str, Any]:
    root = Path(pack_path)
    meta_path = root / "pack.json"
    meta = _read_json(meta_path)

    pack_hash = compute_pack_hash(root)
    meta["pack_hash"] = pack_hash.pack_hash
    meta["hash_algorithm"] = pack_hash.algorithm

    source_snapshot = _build_source_snapshot(root)
    meta["source_snapshot"] = source_snapshot

    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")

    manifest = build_manifest(root)
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    meta = _read_json(meta_path)
    meta["merkle_root"] = manifest["merkle_root"]
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")

    return {
        "pack_hash": pack_hash.pack_hash,
        "hash_algorithm": "sha256",
        "merkle_root": manifest["merkle_root"],
        "source_snapshot": source_snapshot,
        "manifest_path": str(root / "manifest.json"),
    }


def verify_pack_integrity(pack_path: str | Path) -> dict[str, Any]:
    root = Path(pack_path)
    meta = _read_json(root / "pack.json")
    manifest_path = root / "manifest.json"
    manifest_present = manifest_path.exists()
    manifest = _read_json(manifest_path) if manifest_present else build_manifest(root)
    expected_files = manifest.get("files", {})
    if not isinstance(expected_files, dict):
        return {"status": "INVALID", "reason": "manifest files invalid", "valid": False}

    observed_files: dict[str, str] = {}
    for name, expected_hash in sorted(expected_files.items()):
        p = root / str(name)
        if not p.exists():
            return {"status": "INVALID", "reason": f"missing file: {name}", "valid": False}
        observed_hash = _manifest_file_hash(p, str(name))
        observed_files[str(name)] = observed_hash
        if observed_hash != str(expected_hash):
            return {"status": "INVALID", "reason": f"file hash mismatch: {name}", "valid": False}

    observed_merkle = _hash_leaf_values(observed_files)
    if observed_merkle != str(manifest.get("merkle_root", "")):
        return {"status": "INVALID", "reason": "manifest merkle mismatch", "valid": False}
    metadata_merkle = str(meta.get("merkle_root", "")).strip()
    metadata_merkle_match = True
    if metadata_merkle:
        metadata_merkle_match = observed_merkle == metadata_merkle

    observed_pack_hash = compute_pack_hash(root)
    metadata_pack_hash = str(meta.get("pack_hash", "")).strip()
    metadata_pack_hash_match = True
    if metadata_pack_hash:
        metadata_pack_hash_match = observed_pack_hash.pack_hash == metadata_pack_hash

    return {
        "status": "VALID",
        "valid": True,
        "pack_hash": observed_pack_hash.pack_hash,
        "merkle_root": observed_merkle,
        "algorithm": "sha256",
        "manifest_present": manifest_present,
        "metadata_merkle_match": metadata_merkle_match,
        "metadata_pack_hash_match": metadata_pack_hash_match,
    }


def _load_claim_keys(pack_path: str | Path) -> set[tuple[str, str, str]]:
    root = Path(pack_path)
    keys: set[tuple[str, str, str]] = set()
    for line in (root / "claims.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        claim = json.loads(line)
        keys.add((str(claim.get("subject", "")), str(claim.get("relation", "")), str(claim.get("object", ""))))
    return keys


def resolve_pack_path(pack_spec: str | Path) -> Path:
    raw = Path(pack_spec)
    if raw.exists():
        return raw
    from vcse.packs.index import PackIndex

    metadata = PackIndex().get_pack_metadata(str(pack_spec))
    pack_path = Path(str(metadata.get("pack_path", "")))
    if not pack_path.exists():
        raise ValueError(f"pack not found: {pack_spec}")
    return pack_path


def diff_packs(pack_a: str | Path, pack_b: str | Path) -> dict[str, Any]:
    a = _load_claim_keys(pack_a)
    b = _load_claim_keys(pack_b)
    added = sorted({"subject": s, "relation": r, "object": o} for (s, r, o) in (b - a))
    removed = sorted({"subject": s, "relation": r, "object": o} for (s, r, o) in (a - b))
    unchanged = len(a & b)
    return {"added": added, "removed": removed, "unchanged": unchanged}


def _keys_dir() -> Path:
    from vcse.packs.index import _pack_home

    path = _pack_home() / "keys"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _private_key_path() -> Path:
    return _keys_dir() / "pack_signing_ed25519_private.pem"


def _public_key_path() -> Path:
    return _keys_dir() / "pack_signing_ed25519_public.pem"


def _load_or_create_signing_key() -> Ed25519PrivateKey:
    priv_path = _private_key_path()
    pub_path = _public_key_path()
    if priv_path.exists():
        key = serialization.load_pem_private_key(priv_path.read_bytes(), password=None)
        assert isinstance(key, Ed25519PrivateKey)
        return key
    key = Ed25519PrivateKey.generate()
    priv_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    pub_path.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return key


def sign_pack_manifest(
    pack_path: str | Path,
    *,
    write_artifacts: bool = False,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(pack_path)
    manifest = build_manifest(root)
    integrity = {
        "pack_hash": compute_pack_hash(root).pack_hash,
        "merkle_root": manifest["merkle_root"],
    }
    write_root = Path(output_dir) if output_dir else root
    key = _load_or_create_signing_key()
    payload = {
        "pack_hash": integrity["pack_hash"],
        "merkle_root": integrity["merkle_root"],
    }
    message = canonical_json(payload).encode("utf-8")
    signature = key.sign(message)
    out = {
        "pack_hash": integrity["pack_hash"],
        "merkle_root": integrity["merkle_root"],
        "signature": base64.b64encode(signature).decode("ascii"),
        "algorithm": "ed25519",
    }
    if write_artifacts:
        write_root.mkdir(parents=True, exist_ok=True)
        (write_root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        (write_root / "pack_signature.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    return out


def verify_pack_signature(pack_path: str | Path) -> dict[str, Any]:
    root = Path(pack_path)
    sig_path = root / "pack_signature.json"
    if not sig_path.exists():
        return {"status": "INVALID", "reason": "missing pack_signature.json", "valid": False}
    if not _public_key_path().exists():
        return {"status": "INVALID", "reason": "missing public key", "valid": False}
    sig = _read_json(sig_path)
    pub = serialization.load_pem_public_key(_public_key_path().read_bytes())
    assert isinstance(pub, Ed25519PublicKey)
    payload = {
        "pack_hash": str(sig.get("pack_hash", "")),
        "merkle_root": str(sig.get("merkle_root", "")),
    }
    message = canonical_json(payload).encode("utf-8")
    try:
        pub.verify(base64.b64decode(str(sig.get("signature", ""))), message)
    except (InvalidSignature, ValueError):
        return {"status": "INVALID", "reason": "signature mismatch", "valid": False}

    pack_meta = _read_json(root / "pack.json")
    if payload["pack_hash"] != str(pack_meta.get("pack_hash", "")) or payload["merkle_root"] != str(
        pack_meta.get("merkle_root", "")
    ):
        return {"status": "INVALID", "reason": "signature metadata mismatch", "valid": False}
    return {"status": "VALID", "valid": True, "algorithm": "ed25519"}
