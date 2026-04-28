"""Inference primitives."""

from vcse.inference.explanation import (
    ExplanationStep,
    InferenceExplanation,
    build_inverse_explanation,
    build_transitive_explanation,
)
from vcse.inference.inverse import InferredClaim, infer_inverse_claims
from vcse.inference.transitive import TransitiveInferredClaim, infer_transitive_claims

__all__ = [
    "ExplanationStep",
    "InferenceExplanation",
    "InferredClaim",
    "TransitiveInferredClaim",
    "build_inverse_explanation",
    "build_transitive_explanation",
    "infer_inverse_claims",
    "infer_transitive_claims",
]
