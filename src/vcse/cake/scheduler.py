"""CAKE scheduler stub — reserved for future scheduled acquisition runs."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScheduledRun:
    source_config_path: str
    interval_seconds: int
    enabled: bool = True
    last_run: str | None = None
    run_count: int = 0


class CakeScheduler:
    """Stub scheduler. Not yet implemented — placeholder for cron-based acquisition."""

    def __init__(self) -> None:
        self._runs: list[ScheduledRun] = []

    def schedule(self, run: ScheduledRun) -> None:
        self._runs.append(run)

    def list_scheduled(self) -> list[ScheduledRun]:
        return list(self._runs)