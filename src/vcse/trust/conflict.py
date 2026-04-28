"""Conflict detection engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConflictResult:
    conflict_type: str
    conflict_score: float
    affected_claims: list[str]
    explanation: str
    severity: str


def detect_conflicts(claims: list[dict[str, Any]]) -> list[ConflictResult]:
    results: list[ConflictResult] = []
    results.extend(_detect_equality_conflicts(claims))
    results.extend(_detect_numeric_range_conflicts(claims))
    results.extend(_detect_direct_negation(claims))
    results.extend(_detect_functional_conflicts(claims))
    results.extend(_detect_temporal_conflicts(claims))
    return results


def _detect_equality_conflicts(claims: list[dict[str, Any]]) -> list[ConflictResult]:
    by_subject: dict[str, set[str]] = {}
    refs: dict[tuple[str, str], list[str]] = {}
    for claim in claims:
        if str(claim.get("relation", "")) != "equals":
            continue
        subject = str(claim.get("subject", ""))
        obj = str(claim.get("object", ""))
        by_subject.setdefault(subject, set()).add(obj)
        refs.setdefault((subject, obj), []).append(str(claim.get("claim_id", "")))
    results: list[ConflictResult] = []
    for subject, values in by_subject.items():
        if len(values) <= 1:
            continue
        affected: list[str] = []
        for obj in sorted(values):
            affected.extend(refs.get((subject, obj), []))
        results.append(
            ConflictResult(
                conflict_type="EQUALITY_CONFLICT",
                conflict_score=1.0,
                affected_claims=[item for item in affected if item],
                explanation=f"{subject} has multiple equals assignments: {sorted(values)}",
                severity="high",
            )
        )
    return results


def _parse_numeric(value: str) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _detect_numeric_range_conflicts(claims: list[dict[str, Any]]) -> list[ConflictResult]:
    bounds: dict[str, dict[str, float]] = {}
    refs: dict[str, list[str]] = {}
    for claim in claims:
        relation = str(claim.get("relation", ""))
        if relation not in {">", ">=", "<", "<=", "greater_than", "less_than", "less_or_equal", "greater_or_equal"}:
            continue
        subject = str(claim.get("subject", ""))
        value = _parse_numeric(str(claim.get("object", "")))
        if value is None:
            continue
        bucket = bounds.setdefault(subject, {})
        cid = str(claim.get("claim_id", ""))
        refs.setdefault(subject, []).append(cid)
        if relation in {">", "greater_than"}:
            bucket["min_strict"] = max(bucket.get("min_strict", float("-inf")), value)
        elif relation in {">=", "greater_or_equal"}:
            bucket["min_inclusive"] = max(bucket.get("min_inclusive", float("-inf")), value)
        elif relation in {"<", "less_than"}:
            bucket["max_strict"] = min(bucket.get("max_strict", float("inf")), value)
        else:
            bucket["max_inclusive"] = min(bucket.get("max_inclusive", float("inf")), value)

    results: list[ConflictResult] = []
    for subject, item in bounds.items():
        min_value = max(item.get("min_strict", float("-inf")), item.get("min_inclusive", float("-inf")))
        max_value = min(item.get("max_strict", float("inf")), item.get("max_inclusive", float("inf")))
        if min_value > max_value or (min_value == max_value and ("min_strict" in item or "max_strict" in item)):
            results.append(
                ConflictResult(
                    conflict_type="NUMERIC_RANGE_CONFLICT",
                    conflict_score=0.95,
                    affected_claims=[c for c in refs.get(subject, []) if c],
                    explanation=f"numeric bounds conflict for {subject}",
                    severity="high",
                )
            )
    return results


def _detect_direct_negation(claims: list[dict[str, Any]]) -> list[ConflictResult]:
    positive: set[tuple[str, str, str]] = set()
    negated_refs: dict[tuple[str, str, str], list[str]] = {}
    for claim in claims:
        subject = str(claim.get("subject", ""))
        relation = str(claim.get("relation", ""))
        obj = str(claim.get("object", ""))
        if relation == "not_is":
            negated_refs.setdefault((subject, "is", obj), []).append(str(claim.get("claim_id", "")))
        elif relation == "is":
            positive.add((subject, "is", obj))
    results: list[ConflictResult] = []
    for key, refs in negated_refs.items():
        if key in positive:
            results.append(
                ConflictResult(
                    conflict_type="DIRECT_NEGATION_CONFLICT",
                    conflict_score=0.9,
                    affected_claims=[item for item in refs if item],
                    explanation=f"direct negation conflict for {key[0]}",
                    severity="high",
                )
            )
    return results


def _detect_functional_conflicts(claims: list[dict[str, Any]]) -> list[ConflictResult]:
    functional_relations = {"has_ssn", "has_id", "current_status", "ceo", "president"}
    by_key: dict[tuple[str, str], set[str]] = {}
    refs: dict[tuple[str, str], list[str]] = {}
    for claim in claims:
        relation = str(claim.get("relation", ""))
        if relation not in functional_relations:
            continue
        key = (str(claim.get("subject", "")), relation)
        by_key.setdefault(key, set()).add(str(claim.get("object", "")))
        refs.setdefault(key, []).append(str(claim.get("claim_id", "")))
    results: list[ConflictResult] = []
    for key, values in by_key.items():
        if len(values) <= 1:
            continue
        results.append(
            ConflictResult(
                conflict_type="FUNCTIONAL_RELATION_CONFLICT",
                conflict_score=0.88,
                affected_claims=[item for item in refs.get(key, []) if item],
                explanation=f"functional relation conflict for {key[0]} {key[1]}",
                severity="medium",
            )
        )
    return results


def _detect_temporal_conflicts(claims: list[dict[str, Any]]) -> list[ConflictResult]:
    by_key: dict[tuple[str, str, str], dict[str, set[str]]] = {}
    refs: dict[tuple[str, str, str], list[str]] = {}
    for claim in claims:
        key = (str(claim.get("subject", "")), str(claim.get("relation", "")), str(claim.get("object", "")))
        qualifiers = claim.get("qualifiers", {}) or {}
        start = str(qualifiers.get("valid_from", ""))
        end = str(qualifiers.get("valid_to", ""))
        if not start and not end:
            continue
        by_key.setdefault(key, {}).setdefault(start, set()).add(end)
        refs.setdefault(key, []).append(str(claim.get("claim_id", "")))
    results: list[ConflictResult] = []
    for key, intervals in by_key.items():
        # Minimal deterministic check: same start with multiple different end dates.
        for start, ends in intervals.items():
            if len(ends) > 1:
                results.append(
                    ConflictResult(
                        conflict_type="TEMPORAL_CONFLICT",
                        conflict_score=0.8,
                        affected_claims=[item for item in refs.get(key, []) if item],
                        explanation=f"temporal qualifier conflict for {key[0]} {key[1]} {key[2]}",
                        severity="medium",
                    )
                )
                break
    return results
