"""Pack optimization — compress a knowledge pack into a compressed form."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vcse.compression.canonicalizer import CanonicalClaim, canonicalize_claim
from vcse.compression.dictionary import (
    EncodedClaim,
    dict_to_encoded,
    encode_claim_from_canonical,
    encoded_to_dict,
)
from vcse.compression.errors import PackOptimizationError
from vcse.compression.graph import GraphIndex
from vcse.compression.interner import Interner
from vcse.compression.provenance import ProvenanceCompressor


@dataclass
class CompressedPack:
    """Complete compressed pack representation."""
    intern_table: dict[str, Any]
    encoded_claims: list[dict[str, Any]]
    provenance_map: dict[str, Any]
    graph_index: dict[str, Any]
    original_manifest: dict[str, Any]
    original_claims: list[dict[str, Any]]
    provenance_entries: list[dict[str, Any]]
    metrics: dict[str, Any]


def _load_pack_claims(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Load all claims from the pack's claims artifacts."""
    claims: list[dict[str, Any]] = []
    for rel_path in manifest.get("artifacts", {}).get("claims", []):
        path = root / rel_path
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    try:
                        claims.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return claims


def _load_pack_provenance(root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Load all provenance entries from the pack."""
    entries: list[dict[str, Any]] = []
    paths = list(manifest.get("artifacts", {}).get("provenance", [])) or manifest.get("provenance", [])
    for rel_path in paths:
        path = root / rel_path
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return entries


def optimize_pack(pack_path: str | Path) -> CompressedPack:
    """
    Compress a knowledge pack.

    Steps:
    1. Load original claims (preserved fully for round-trip)
    2. Canonicalize all claims
    3. Build interner with all unique strings
    4. Encode claims via interner
    5. Build provenance deduplication map
    6. Build graph index
    7. Capture compression metrics

    Returns a CompressedPack containing all original data plus compressed form.
    The original claims are fully preserved inside CompressedPack.original_claims.
    """
    root = Path(pack_path)
    manifest_path = root / "pack.json"
    if not manifest_path.exists():
        raise PackOptimizationError("MISSING_MANIFEST", f"pack manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text())
    original_claims = _load_pack_claims(root, manifest)
    provenance_entries = _load_pack_provenance(root, manifest)

    interner = Interner()
    canonical_claims: list[CanonicalClaim] = []
    for raw in original_claims:
        try:
            canonical = canonicalize_claim(raw)
            canonical_claims.append(canonical)
        except Exception:
            continue

    for cc in canonical_claims:
        interner.intern(cc.subject)
        interner.intern(cc.relation)
        interner.intern(cc.object)
        for k, v in cc.qualifiers:
            interner.intern(k)
            interner.intern(v)

    encoded_claims: list[dict[str, Any]] = []
    provenance_compressor = ProvenanceCompressor()
    graph_index = GraphIndex()

    provenance_ref_map: list[int] = []

    for idx, raw in enumerate(original_claims):
        try:
            canonical = canonical_claims[idx]
        except IndexError:
            continue
        enc = encode_claim_from_canonical(canonical, interner)
        encoded_claims.append(encoded_to_dict(enc))

        prov = raw.get("provenance", {})
        if prov:
            ref_id = provenance_compressor.fingerprint_to_id(prov)
            provenance_ref_map.append(ref_id)
        graph_index.add_claim(canonical.subject, canonical.relation, canonical.object)

    original_size = sum(len(json.dumps(c)) for c in original_claims)
    compressed_size = sum(len(json.dumps(e)) for e in encoded_claims)
    intern_size = len(json.dumps(interner.to_dict()))

    metrics = {
        "original_claims": len(original_claims),
        "compressed_claims": len(encoded_claims),
        "unique_strings": interner.size,
        "original_size_bytes": original_size,
        "compressed_size_bytes": compressed_size,
        "intern_table_size_bytes": intern_size,
        "total_compressed_size_bytes": compressed_size + intern_size,
        "provenance_unique": provenance_compressor.size,
        "provenance_total": len(provenance_ref_map),
        "graph_nodes": len(graph_index.nodes()),
        "graph_edges": graph_index.edge_count(),
        "compression_ratio": (
            round(compressed_size / original_size, 4)
            if original_size > 0 else 1.0
        ),
    }

    return CompressedPack(
        intern_table=interner.to_dict(),
        encoded_claims=encoded_claims,
        provenance_map=provenance_compressor.to_dict(),
        graph_index=graph_index.to_dict(),
        original_manifest=dict(manifest),
        original_claims=list(original_claims),
        provenance_entries=list(provenance_entries),
        metrics=metrics,
    )


def save_compressed(pack: CompressedPack, output_dir: str | Path) -> None:
    """Save a compressed pack to disk as structured files."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    (out / "pack.json").write_text(json.dumps(pack.original_manifest, indent=2))
    (out / "intern_table.json").write_text(json.dumps(pack.intern_table, indent=2))
    (out / "encoded_claims.jsonl").write_text(
        "\n".join(json.dumps(e) for e in pack.encoded_claims)
    )
    (out / "provenance_map.json").write_text(json.dumps(pack.provenance_map, indent=2))
    (out / "graph_index.json").write_text(json.dumps(pack.graph_index, indent=2))
    (out / "original_claims.jsonl").write_text(
        "\n".join(json.dumps(c) for c in pack.original_claims)
    )
    (out / "metrics.json").write_text(json.dumps(pack.metrics, indent=2))


def load_compressed(compressed_dir: str | Path) -> CompressedPack:
    """Load a compressed pack from disk."""
    root = Path(compressed_dir)

    with open(root / "pack.json") as f:
        manifest = json.load(f)
    with open(root / "intern_table.json") as f:
        intern_table = json.load(f)
    with open(root / "encoded_claims.jsonl") as f:
        encoded_claims = [json.loads(line) for line in f if line.strip()]
    with open(root / "provenance_map.json") as f:
        provenance_map = json.load(f)
    with open(root / "graph_index.json") as f:
        graph_index = json.load(f)
    with open(root / "original_claims.jsonl") as f:
        original_claims = [json.loads(line) for line in f if line.strip()]
    with open(root / "metrics.json") as f:
        metrics = json.load(f)

    provenance_entries = []
    pdata = provenance_map
    if pdata:
        provenance_entries = pdata.get("entries", [])

    return CompressedPack(
        intern_table=intern_table,
        encoded_claims=encoded_claims,
        provenance_map=provenance_map,
        graph_index=graph_index,
        original_manifest=manifest,
        original_claims=original_claims,
        provenance_entries=provenance_entries,
        metrics=metrics,
    )