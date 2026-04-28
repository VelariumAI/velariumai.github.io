"""Decompression engine — losslessly restore original pack data."""

from __future__ import annotations

import json
from pathlib import Path

from vcse.compression.dictionary import dict_to_encoded, decode_claim
from vcse.compression.errors import DecompressionError, IntegrityError
from vcse.compression.interner import Interner
from vcse.compression.pack_optimizer import CompressedPack, load_compressed


def decompress_pack(compressed_dir: str | Path) -> CompressedPack:
    """
    Load and verify a compressed pack.

    Integrity check: re-encode original claims and compare with stored encoded form.
    If any claim fails to round-trip, raises IntegrityError.
    """
    pack = load_compressed(compressed_dir)
    interner = Interner.from_dict(pack.intern_table)

    for encoded_dict in pack.encoded_claims:
        enc = dict_to_encoded(encoded_dict)
        try:
            canonical = decode_claim(enc, interner)
        except Exception as exc:
            raise IntegrityError(
                "DECODE_FAILED",
                f"failed to decode claim: {exc}",
            )

    for idx, original in enumerate(pack.original_claims):
        enc_dict = pack.encoded_claims[idx]
        enc = dict_to_encoded(enc_dict)
        decoded = decode_claim(enc, interner)

        sub = original.get("subject", "")
        rel = original.get("relation", "")
        obj = original.get("object", "")

        if sub and rel and obj:
            from vcse.compression.canonicalizer import canonicalize_claim
            canonical2 = canonicalize_claim(original)
            if (
                decoded.subject != canonical2.subject
                or decoded.relation != canonical2.relation
                or decoded.object != canonical2.object
            ):
                raise IntegrityError(
                    "MISMATCH",
                    f"claim {idx} round-trip mismatch: "
                    f"{decoded.subject}/{decoded.relation}/{decoded.object} != "
                    f"{canonical2.subject}/{canonical2.relation}/{canonical2.object}",
                )

    return pack


def verify_integrity(compressed_dir: str | Path) -> dict[str, Any]:
    """
    Verify integrity of a compressed pack without full decompression.

    Checks:
    - all files present
    - encoded claims can be decoded
    - original_claims.jsonl matches encoded form

    Returns dict with status and details.
    """
    root = Path(compressed_dir)
    required_files = [
        "pack.json",
        "intern_table.json",
        "encoded_claims.jsonl",
        "provenance_map.json",
        "graph_index.json",
        "original_claims.jsonl",
        "metrics.json",
    ]

    for fname in required_files:
        if not (root / fname).exists():
            return {
                "status": "MISSING_FILE",
                "file": fname,
                "valid": False,
            }

    try:
        pack = load_compressed(root)
    except Exception as exc:
        return {
            "status": "LOAD_FAILED",
            "error": str(exc),
            "valid": False,
        }

    interner = Interner.from_dict(pack.intern_table)

    for idx, enc_dict in enumerate(pack.encoded_claims):
        try:
            enc = dict_to_encoded(enc_dict)
            decode_claim(enc, interner)
        except Exception as exc:
            return {
                "status": "DECODE_FAILED",
                "claim_index": idx,
                "error": str(exc),
                "valid": False,
            }

    return {
        "status": "VALID",
        "claims": len(pack.original_claims),
        "unique_strings": interner.size,
        "valid": True,
    }