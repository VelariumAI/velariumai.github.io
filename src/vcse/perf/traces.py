"""Tracing helpers for runtime profiling."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter


@dataclass
class PerfTrace:
    durations: dict[str, float] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)

    @contextmanager
    def stage(self, name: str):
        started = perf_counter()
        try:
            yield
        finally:
            elapsed = perf_counter() - started
            self.durations[name] = self.durations.get(name, 0.0) + elapsed

    def incr(self, name: str, amount: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + amount


_CURRENT_TRACE: ContextVar[PerfTrace | None] = ContextVar("vcse_perf_trace", default=None)


@contextmanager
def activate_trace(trace: PerfTrace):
    token = _CURRENT_TRACE.set(trace)
    try:
        yield trace
    finally:
        _CURRENT_TRACE.reset(token)


@contextmanager
def stage(name: str):
    trace = _CURRENT_TRACE.get()
    if trace is None:
        yield
        return
    with trace.stage(name):
        yield


def increment(name: str, amount: int = 1) -> None:
    trace = _CURRENT_TRACE.get()
    if trace is None:
        return
    trace.incr(name, amount)


def current_trace() -> PerfTrace | None:
    return _CURRENT_TRACE.get()
