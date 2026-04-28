"""Deterministic inference stability tracking."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InferenceObservation:
    claim_key: str
    inference_type: str
    occurrences: int


class InferenceStabilityTracker:
    def __init__(self) -> None:
        self._counts: dict[tuple[str, str], int] = {}

    def record(self, claim_key: str, inference_type: str) -> None:
        key = (claim_key, inference_type)
        self._counts[key] = self._counts.get(key, 0) + 1

    def get_counts(self) -> list[InferenceObservation]:
        observations = [
            InferenceObservation(claim_key=claim_key, inference_type=inference_type, occurrences=occurrences)
            for (claim_key, inference_type), occurrences in self._counts.items()
        ]
        return sorted(observations, key=lambda item: (item.claim_key, item.inference_type))

    def get_stable(self, threshold: int) -> list[InferenceObservation]:
        if threshold < 1:
            raise ValueError("threshold must be >= 1")
        return [item for item in self.get_counts() if item.occurrences >= threshold]
