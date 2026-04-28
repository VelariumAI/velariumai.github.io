"""Tests for compression round-trip integrity."""

import json
from pathlib import Path

from vcse.compression.pack_optimizer import optimize_pack, save_compressed, load_compressed
from vcse.compression.decompressor import verify_integrity


def test_roundtrip_logic_basic():
    """Compress and decompress logic_basic pack, verify all claims restored."""
    pack = optimize_pack("examples/packs/logic_basic")
    save_compressed(pack, "tests/roundtrip_test")

    loaded = load_compressed("tests/roundtrip_test")

    assert len(loaded.original_claims) == len(pack.original_claims)
    for idx in range(len(pack.original_claims)):
        assert loaded.original_claims[idx] == pack.original_claims[idx]

    result = verify_integrity("tests/roundtrip_test")
    assert result.get("valid") == True


def test_roundtrip_trusted_basic():
    """Round-trip the trusted_basic pack."""
    pack = optimize_pack("examples/packs/trusted_basic")
    save_compressed(pack, "tests/roundtrip_trusted")

    loaded = load_compressed("tests/roundtrip_trusted")

    assert len(loaded.original_claims) == len(pack.original_claims)
    assert loaded.original_claims == pack.original_claims

    result = verify_integrity("tests/roundtrip_trusted")
    assert result.get("valid") == True


def test_roundtrip_all_claims_preserved():
    """Ensure every field of every claim survives round-trip."""
    pack = optimize_pack("examples/packs/logic_basic")
    save_compressed(pack, "tests/roundtrip_full")

    loaded = load_compressed("tests/roundtrip_full")

    for orig, restored in zip(pack.original_claims, loaded.original_claims):
        assert orig == restored


def test_compression_ratio_positive():
    """Verify compression produces metrics."""
    pack = optimize_pack("examples/packs/logic_basic")
    assert pack.metrics["original_claims"] == pack.metrics["compressed_claims"]
    assert pack.metrics["compression_ratio"] > 0


def test_verify_invalid_dir():
    """Verify integrity check handles invalid path."""
    result = verify_integrity("tests/nonexistent_dir_xyz")
    assert result.get("valid") == False
    assert result.get("status") == "MISSING_FILE"


def test_metadata_preserved():
    """Pack manifest is preserved through round-trip."""
    pack = optimize_pack("examples/packs/logic_basic")
    save_compressed(pack, "tests/roundtrip_meta")

    loaded = load_compressed("tests/roundtrip_meta")
    assert loaded.original_manifest["id"] == pack.original_manifest["id"]
    assert loaded.original_manifest["version"] == pack.original_manifest["version"]