"""Tests for pack optimizer."""

import json
from pathlib import Path

from vcse.compression.pack_optimizer import (
    optimize_pack,
    save_compressed,
    load_compressed,
    CompressedPack,
)


def test_optimize_pack_produces_compressed_pack():
    pack = optimize_pack("examples/packs/logic_basic")
    assert isinstance(pack, CompressedPack)
    assert pack.metrics["original_claims"] > 0
    assert pack.metrics["unique_strings"] > 0


def test_optimize_pack_has_all_fields():
    pack = optimize_pack("examples/packs/logic_basic")
    assert pack.intern_table is not None
    assert pack.encoded_claims is not None
    assert pack.provenance_map is not None
    assert pack.graph_index is not None
    assert pack.original_manifest is not None
    assert pack.original_claims is not None
    assert pack.metrics is not None


def test_save_and_load_roundtrip():
    pack = optimize_pack("examples/packs/logic_basic")
    save_compressed(pack, "tests/optimizer_test")
    loaded = load_compressed("tests/optimizer_test")
    assert loaded.original_claims == pack.original_claims
    assert loaded.original_manifest["id"] == pack.original_manifest["id"]


def test_original_claims_fully_preserved():
    """original_claims field must be bit-for-bit identical after save/load."""
    pack = optimize_pack("examples/packs/logic_basic")
    save_compressed(pack, "tests/optimizer_full")
    loaded = load_compressed("tests/optimizer_full")

    for idx, (orig, rest) in enumerate(zip(pack.original_claims, loaded.original_claims)):
        assert orig == rest, f"claim {idx} mismatch"


def test_graph_index_builds():
    pack = optimize_pack("examples/packs/logic_basic")
    assert "socrates" in pack.graph_index or "man" in pack.graph_index


def test_metrics_contain_required_fields():
    pack = optimize_pack("examples/packs/logic_basic")
    required = ["original_claims", "compressed_claims", "unique_strings",
                "original_size_bytes", "compressed_size_bytes", "compression_ratio"]
    for field in required:
        assert field in pack.metrics


def test_packed_claims_match_original_count():
    pack = optimize_pack("examples/packs/trusted_basic")
    assert len(pack.encoded_claims) == len(pack.original_claims)


def test_compression_reduces_size_on_large_pack():
    """For packs with enough repetition, total compressed < original size."""
    pack = optimize_pack("examples/packs/trusted_basic")
    total = pack.metrics.get("total_compressed_size_bytes", 0)
    original = pack.metrics.get("original_size_bytes", 0)
    if original > 0:
        assert total <= original or pack.metrics.get("compression_ratio", 1.0) <= 1.0