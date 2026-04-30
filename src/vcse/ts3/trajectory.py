"""Trajectory model for TS3."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcse.ts3.symbolic_state import SymbolicState


@dataclass
class Trajectory:
    symbolic_states: list[SymbolicState] = field(default_factory=list)
    transitions: list[str] = field(default_factory=list)
    terminal_status: str | None = None
    loop_detected: bool = False
