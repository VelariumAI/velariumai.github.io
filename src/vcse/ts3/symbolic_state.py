"""Symbolic state model for TS3."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolicState:
    signature: str
    depth: int
    status: str
    score: float
    outgoing_transition_count: int
