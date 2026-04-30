"""Adapters between VCSE internal states and API-facing text."""

from __future__ import annotations

from typing import Any


def render_status_text(
    status: str,
    answer: Any | None,
    reasons: list[str] | None = None,
    proof_trace: list[str] | None = None,
) -> str:
    reasons = reasons or []
    proof_trace = proof_trace or []

    if status == "VERIFIED":
        if answer is None:
            return "Yes — verified."
        if proof_trace:
            return f"Yes — {answer}"
        return f"Yes — {answer}"
    if status == "INCONCLUSIVE":
        return "Cannot determine with current information."
    if status == "NEEDS_CLARIFICATION":
        suffix = reasons[0] if reasons else "please provide additional details."
        return f"Additional information required: {suffix}"
    if status == "CONTRADICTORY":
        suffix = reasons[0] if reasons else "conflicting facts were found."
        return f"Contradiction detected: {suffix}"
    if status == "UNSATISFIABLE":
        return "Constraints cannot be satisfied."

    if status == "VERIFIED_ARTIFACT":
        return str(answer)
    if status == "INCONCLUSIVE_ARTIFACT":
        suffix = reasons[0] if reasons else "artifact could not be fully verified."
        return f"Artifact is inconclusive: {suffix}"
    if status == "FAILED_ARTIFACT":
        suffix = reasons[0] if reasons else "validation failed."
        return f"Artifact generation failed: {suffix}"
    if status == "CONTRADICTORY_ARTIFACT":
        suffix = reasons[0] if reasons else "artifact contradicts known facts."
        return f"Contradiction detected: {suffix}"

    return f"Status: {status}"
