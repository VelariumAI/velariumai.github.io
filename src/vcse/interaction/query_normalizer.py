"""Strict query normalizer with explicit fixed patterns only."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedQuery:
    subject: str
    relation: str
    object: str | None = None


def _strip_trailing_punctuation(text: str) -> str:
    return text.rstrip("?.!")


def normalize_query(text: str) -> NormalizedQuery | None:
    raw = text.strip()
    if not raw:
        return None
    raw_no_punct = _strip_trailing_punctuation(raw).strip()
    lower = raw_no_punct.lower()

    # 1) What is the capital of X?
    prefix = "what is the capital of "
    if lower.startswith(prefix):
        subject = raw_no_punct[len(prefix):].strip()
        if subject:
            return NormalizedQuery(subject=subject, relation="capital_of", object=None)
        return None

    # 2) What country is X in?
    prefix = "what country is "
    suffix = " in"
    if lower.startswith(prefix) and lower.endswith(suffix):
        subject = raw_no_punct[len(prefix):-len(suffix)].strip()
        if subject:
            return NormalizedQuery(subject=subject, relation="located_in_country", object=None)
        return None

    # 3) What continent is X part of?
    prefix = "what continent is "
    suffix = " part of"
    if lower.startswith(prefix) and lower.endswith(suffix):
        subject = raw_no_punct[len(prefix):-len(suffix)].strip()
        if subject:
            return NormalizedQuery(subject=subject, relation="part_of", object=None)
        return None

    # 4) What currency does X use?
    prefix = "what currency does "
    suffix = " use"
    if lower.startswith(prefix) and lower.endswith(suffix):
        subject = raw_no_punct[len(prefix):-len(suffix)].strip()
        if subject:
            return NormalizedQuery(subject=subject, relation="uses_currency", object=None)
        return None

    # 5) What is the currency of X?
    prefix = "what is the currency of "
    if lower.startswith(prefix):
        subject = raw_no_punct[len(prefix):].strip()
        if subject:
            return NormalizedQuery(subject=subject, relation="uses_currency", object=None)
        return None

    # 6) What language is spoken in X?
    prefix = "what language is spoken in "
    if lower.startswith(prefix):
        subject = raw_no_punct[len(prefix):].strip()
        if subject:
            return NormalizedQuery(subject=subject, relation="language_of", object=None)
        return None

    # 7) What languages are spoken in X?
    prefix = "what languages are spoken in "
    if lower.startswith(prefix):
        subject = raw_no_punct[len(prefix):].strip()
        if subject:
            return NormalizedQuery(subject=subject, relation="language_of", object=None)
        return None

    # 8) What is the country code of X?
    prefix = "what is the country code of "
    if lower.startswith(prefix):
        subject = raw_no_punct[len(prefix):].strip()
        if subject:
            return NormalizedQuery(subject=subject, relation="has_country_code", object=None)
        return None

    # 9) What region is X in?
    prefix = "what region is "
    suffix = " in"
    if lower.startswith(prefix) and lower.endswith(suffix):
        subject = raw_no_punct[len(prefix):-len(suffix)].strip()
        if subject:
            return NormalizedQuery(subject=subject, relation="located_in_region", object=None)
        return None

    # 10) What subregion is X in?
    prefix = "what subregion is "
    suffix = " in"
    if lower.startswith(prefix) and lower.endswith(suffix):
        subject = raw_no_punct[len(prefix):-len(suffix)].strip()
        if subject:
            return NormalizedQuery(subject=subject, relation="located_in_subregion", object=None)
        return None

    # 4) Is X a city?
    prefix = "is "
    suffix = " a city"
    if lower.startswith(prefix) and lower.endswith(suffix):
        subject = raw_no_punct[len(prefix):-len(suffix)].strip()
        if subject:
            return NormalizedQuery(subject=subject, relation="instance_of", object="City")
        return None

    # 5) Is X a country?
    suffix = " a country"
    if lower.startswith(prefix) and lower.endswith(suffix):
        subject = raw_no_punct[len(prefix):-len(suffix)].strip()
        if subject:
            return NormalizedQuery(subject=subject, relation="instance_of", object="Country")
        return None

    return None
