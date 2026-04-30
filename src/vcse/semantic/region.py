"""Deterministic semantic region model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticRegion:
    region_id: str
    relations: set[str]
    subjects: set[str]
    size: int
