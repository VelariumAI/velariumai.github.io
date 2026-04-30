"""Compression errors."""

from __future__ import annotations


class CompressionError(Exception):
    """Base exception for compression subsystem."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class CanonicalizationError(CompressionError):
    """Claim cannot be canonicalized."""
    pass


class InterningError(CompressionError):
    """String interning failed."""
    pass


class EncodingError(CompressionError):
    """Claim encoding/decoding failed."""
    pass


class ProvenanceError(CompressionError):
    """Provenance compression failed."""
    pass


class GraphError(CompressionError):
    """Graph compression failed."""
    pass


class PackOptimizationError(CompressionError):
    """Pack optimization failed."""
    pass


class DecompressionError(CompressionError):
    """Decompression failed."""
    pass


class IntegrityError(CompressionError):
    """Integrity check failed during round-trip."""
    pass