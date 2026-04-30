"""Runtime settings models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    search_backend: str = "beam"
    ts3_enabled: bool = False
    indexing_enabled: bool = False
    top_k_rules: int = 20
    top_k_packs: int = 5
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_debug: bool = False
    api_timeout_seconds: float = 30.0
    api_max_request_bytes: int = 1_000_000
    log_level: str = "INFO"
    profiling_enabled: bool = False
