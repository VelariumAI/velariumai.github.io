"""Deterministic tokenization helpers for symbolic retrieval."""

from __future__ import annotations

import re
from typing import Iterable

TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9_]+")


def normalize_text(text: str, normalized_hint: str | None = None) -> str:
    if normalized_hint:
        return normalized_hint.strip().lower()
    base = text or ""
    base = base.lower()
    base = re.sub(r"\s+", " ", base)
    return base.strip()


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    lowered = text.lower().strip()
    if not lowered:
        return []
    return [token for token in TOKEN_SPLIT_RE.split(lowered) if token]


def normalized_tokens(text: str, normalized_hint: str | None = None) -> list[str]:
    return tokenize(normalize_text(text, normalized_hint=normalized_hint))


def merge_tokens(*values: Iterable[str]) -> list[str]:
    merged: list[str] = []
    for value in values:
        merged.extend(value)
    return merged
