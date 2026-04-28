"""Inference primitives."""

from vcse.inference.inverse import InferredClaim, infer_inverse_claims
from vcse.inference.transitive import TransitiveInferredClaim, infer_transitive_claims

__all__ = [
    "InferredClaim",
    "TransitiveInferredClaim",
    "infer_inverse_claims",
    "infer_transitive_claims",
]
