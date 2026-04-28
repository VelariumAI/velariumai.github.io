"""Strict query normalizer with explicit fixed patterns only."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedQuery:
    subject: str
    relation: str
    object: str | None = None


def normalize_query(text: str) -> NormalizedQuery | None:
    raw = text.strip()
    if not raw:
        return None

    # 1) What is the capital of X?
    prefix = "what is the capital of "
    if raw.lower().startswith(prefix) and raw.endswith("?"):
        subject = raw[len(prefix):-1].strip()
        if subject:
            return NormalizedQuery(subject=subject, relation="capital_of", object=None)
        return None

    # 2) What country is X in?
    prefix = "what country is "
    suffix = " in?"
    if raw.lower().startswith(prefix) and raw.lower().endswith(suffix):
        subject = raw[len(prefix):-len(suffix)].strip()
        if subject:
            return NormalizedQuery(subject=subject, relation="located_in_country", object=None)
        return None

    # 3) What continent is X part of?
    prefix = "what continent is "
    suffix = " part of?"
    if raw.lower().startswith(prefix) and raw.lower().endswith(suffix):
        subject = raw[len(prefix):-len(suffix)].strip()
        if subject:
            return NormalizedQuery(subject=subject, relation="part_of", object=None)
        return None

    # 4) Is X a city?
    prefix = "is "
    suffix = " a city?"
    if raw.lower().startswith(prefix) and raw.lower().endswith(suffix):
        subject = raw[len(prefix):-len(suffix)].strip()
        if subject:
            return NormalizedQuery(subject=subject, relation="instance_of", object="City")
        return None

    # 5) Is X a country?
    suffix = " a country?"
    if raw.lower().startswith(prefix) and raw.lower().endswith(suffix):
        subject = raw[len(prefix):-len(suffix)].strip()
        if subject:
            return NormalizedQuery(subject=subject, relation="instance_of", object="Country")
        return None

    return None
