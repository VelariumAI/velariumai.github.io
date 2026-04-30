"""Failure classifier for categorizing errors."""

from __future__ import annotations

from vcse.interaction.frames import FrameParseResult, FrameStatus
from vcse.interaction.clarification import ClarificationRequest
from vcse.reasonops.failure_record import FailureType


class FailureClassifier:
    """Classify failures from parse/search/result objects."""

    def classify_from_parse(
        self, parse_result: FrameParseResult, input_text: str
    ) -> FailureType | None:
        """Classify failure from parse result."""
        if parse_result.status == FrameStatus.FAILED:
            return FailureType.PARSE_FAILURE

        if parse_result.status == FrameStatus.UNSUPPORTED:
            if parse_result.warnings:
                for warning in parse_result.warnings:
                    if "pattern" in warning.lower():
                        return FailureType.MISSING_PATTERN
                    if "synonym" in warning.lower():
                        return FailureType.MISSING_SYNONYM
            return FailureType.UNSUPPORTED_QUERY

        if parse_result.status == FrameStatus.AMBIGUOUS:
            return FailureType.AMBIGUOUS_INPUT

        return None

    def classify_from_clarification(
        self, request: ClarificationRequest
    ) -> FailureType:
        """Classify failure from clarification request."""
        code = request.machine_code
        if code == "AMBIGUOUS_INPUT":
            return FailureType.AMBIGUOUS_INPUT
        elif code == "INSUFFICIENT_FACTS":
            return FailureType.MISSING_DOMAIN_RULE
        elif code == "UNSUPPORTED_QUERY":
            return FailureType.UNSUPPORTED_QUERY
        else:
            return FailureType.MISSING_DOMAIN_RULE

    def classify_from_search(
        self, search_result: object, limit_reached: bool = False
    ) -> FailureType | None:
        """Classify failure from search result."""
        if limit_reached:
            return FailureType.SEARCH_LIMIT_REACHED
        return None
