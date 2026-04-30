"""Gauntlet case evaluator."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from vcse.gauntlet.case import GauntletCase
from vcse.gauntlet.runner import GauntletCaseResult


@dataclass(frozen=True)
class CaseEvaluation:
    outcome: str
    reasons: list[str] = field(default_factory=list)


class GauntletEvaluator:
    def evaluate(self, case: GauntletCase, result: GauntletCaseResult) -> CaseEvaluation:
        reasons: list[str] = []
        critical = False

        if result.status != case.expected_status:
            reasons.append(
                f"status mismatch: expected {case.expected_status}, got {result.status}"
            )

        if result.status in set(case.failure_if):
            reasons.append(f"status {result.status} is in failure_if")

        if case.expected_answer is not None:
            if not _answer_matches(case.expected_answer, result.answer):
                reasons.append("answer mismatch")

        if case.expected_status not in {"VERIFIED", "VERIFIED_ARTIFACT"} and result.status in {
            "VERIFIED",
            "VERIFIED_ARTIFACT",
        }:
            reasons.append("false verified output")
            critical = True

        if case.mode == "generate" and result.status == "VERIFIED_ARTIFACT":
            artifact = result.artifact or {}
            if not artifact.get("provenance"):
                reasons.append("missing artifact provenance")
            if not artifact.get("constraints_satisfied"):
                reasons.append("artifact has no satisfied constraints")
            if artifact.get("violations"):
                reasons.append("artifact has constraint violations")

        if critical:
            return CaseEvaluation("CRITICAL_FAIL", reasons)
        if reasons:
            return CaseEvaluation("FAIL", reasons)
        return CaseEvaluation("PASS", ["ok"])


def _answer_matches(expected: Any, actual: Any) -> bool:
    if expected is None:
        return actual is None
    if isinstance(expected, dict):
        if isinstance(actual, dict):
            exp_norm = {str(k): _normalize(v) for k, v in expected.items()}
            act_norm = {str(k): _normalize(v) for k, v in actual.items()}
            return all(act_norm.get(k) == v for k, v in exp_norm.items())
        actual_text = _normalize(actual)
        return all(_normalize(v) in actual_text for v in expected.values())
    return _normalize(expected) == _normalize(actual)


def _normalize(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s_]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text
