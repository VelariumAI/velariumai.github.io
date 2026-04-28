"""Deterministic pack coverage benchmark."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CoverageBenchmarkError(ValueError):
    def __init__(self, error_type: str, reason: str) -> None:
        super().__init__(f"{error_type}: {reason}")
        self.error_type = error_type
        self.reason = reason


def run_coverage_benchmark(pack_path: Path, benchmark_path: Path) -> dict[str, Any]:
    claims = _load_claims(pack_path)
    cases = _load_cases(benchmark_path)
    claim_map = {
        (str(claim.get("subject", "")), str(claim.get("relation", "")), str(claim.get("object", ""))): claim
        for claim in claims
        if isinstance(claim, dict)
    }
    results: list[dict[str, str]] = []
    verified = 0
    candidate = 0
    unknown = 0
    incorrect = 0

    for case in cases:
        key = (case["subject"], case["relation"], case["object"])
        hit = claim_map.get(key)
        if hit is None:
            observed = "unknown"
            unknown += 1
        elif str(hit.get("trust_tier", "")) == "T5_CERTIFIED":
            observed = "verified"
            verified += 1
        else:
            observed = "candidate"
            candidate += 1

        expected = case["expected"]
        ok = observed == expected
        if not ok:
            incorrect += 1
        results.append(
            {
                "id": case["id"],
                "expected": expected,
                "observed": observed,
                "status": "PASS" if ok else "FAIL",
            }
        )

    total = len(cases)
    answered = verified + candidate
    return {
        "status": "COVERAGE_COMPLETE" if incorrect == 0 else "COVERAGE_MISMATCH",
        "pack_path": str(pack_path),
        "benchmark_path": str(benchmark_path),
        "total": total,
        "answered": answered,
        "verified": verified,
        "candidate": candidate,
        "unknown": unknown,
        "incorrect": incorrect,
        "coverage_rate": _rate(answered, total),
        "verified_rate": _rate(verified, total),
        "candidate_rate": _rate(candidate, total),
        "unknown_rate": _rate(unknown, total),
        "results": results,
    }


def format_coverage_text(summary: dict[str, Any]) -> str:
    lines = [
        f"status: {summary['status']}",
        f"total: {summary['total']}",
        f"answered: {summary['answered']}",
        f"verified: {summary['verified']}",
        f"candidate: {summary['candidate']}",
        f"unknown: {summary['unknown']}",
        f"incorrect: {summary['incorrect']}",
        f"coverage_rate: {summary['coverage_rate']}",
        f"verified_rate: {summary['verified_rate']}",
        f"candidate_rate: {summary['candidate_rate']}",
        f"unknown_rate: {summary['unknown_rate']}",
    ]
    return "\n".join(lines)


def _load_claims(pack_path: Path) -> list[dict[str, Any]]:
    claims_path = pack_path / "claims.jsonl"
    if not claims_path.exists():
        raise CoverageBenchmarkError("MISSING_CLAIMS", f"missing claims.jsonl in {pack_path}")
    claims: list[dict[str, Any]] = []
    for idx, line in enumerate(claims_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CoverageBenchmarkError("MALFORMED_CLAIMS", f"claims.jsonl line {idx}: {exc.msg}") from exc
        if not isinstance(row, dict):
            raise CoverageBenchmarkError("MALFORMED_CLAIMS", f"claims.jsonl line {idx} must be an object")
        claims.append(row)
    return claims


def _load_cases(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise CoverageBenchmarkError("FILE_NOT_FOUND", f"benchmark file not found: {path}")
    cases: list[dict[str, str]] = []
    for idx, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CoverageBenchmarkError("MALFORMED_JSON", f"line {idx}: {exc.msg}") from exc
        if not isinstance(row, dict):
            raise CoverageBenchmarkError("INVALID_CASE", f"line {idx} root must be object")
        case = {
            "id": str(row.get("id", f"case_{idx}")),
            "subject": str(row.get("subject", "")).strip(),
            "relation": str(row.get("relation", "")).strip(),
            "object": str(row.get("object", "")).strip(),
            "expected": str(row.get("expected", "")).strip().lower(),
        }
        if not case["subject"] or not case["relation"] or not case["object"]:
            raise CoverageBenchmarkError("INVALID_CASE", f"line {idx} requires subject/relation/object")
        if case["expected"] not in {"verified", "candidate", "unknown"}:
            raise CoverageBenchmarkError("INVALID_EXPECTED", f"line {idx} expected must be verified/candidate/unknown")
        cases.append(case)
    return cases


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0
