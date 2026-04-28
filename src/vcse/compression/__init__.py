"""Knowledge Structure Compression (KSC) — lossless pack compression."""

from vcse.compression.canonicalizer import CanonicalClaim, canonicalize_claim
from vcse.compression.decompressor import decompress_pack, verify_integrity
from vcse.compression.dictionary import (
    EncodedClaim,
    decode_claim,
    dict_to_encoded,
    encode_claim,
    encode_claim_from_canonical,
    encoded_to_dict,
)
from vcse.compression.errors import (
    CompressionError,
    CanonicalizationError,
    DecompressionError,
    EncodingError,
    GraphError,
    IntegrityError,
    InterningError,
    PackOptimizationError,
    ProvenanceError,
)
from vcse.compression.graph import GraphIndex
from vcse.compression.interner import Interner
from vcse.compression.metrics import compute_metrics, format_metrics
from vcse.compression.pack_optimizer import (
    CompressedPack,
    load_compressed,
    optimize_pack,
    save_compressed,
)
from vcse.compression.provenance import ProvenanceCompressor, ProvenanceRef
from vcse.compression.runtime_index import CompressedRuntimeIndex

__all__ = [
    # canonicalizer
    "CanonicalClaim",
    "canonicalize_claim",
    # dictionary
    "EncodedClaim",
    "encode_claim",
    "decode_claim",
    "encode_claim_from_canonical",
    "encoded_to_dict",
    "dict_to_encoded",
    # interner
    "Interner",
    # provenance
    "ProvenanceCompressor",
    "ProvenanceRef",
    "CompressedRuntimeIndex",
    # graph
    "GraphIndex",
    # pack optimizer
    "CompressedPack",
    "optimize_pack",
    "save_compressed",
    "load_compressed",
    # decompressor
    "decompress_pack",
    "verify_integrity",
    # metrics
    "compute_metrics",
    "format_metrics",
    # errors
    "CompressionError",
    "CanonicalizationError",
    "DecompressionError",
    "EncodingError",
    "GraphError",
    "IntegrityError",
    "InterningError",
    "PackOptimizationError",
    "ProvenanceError",
]
