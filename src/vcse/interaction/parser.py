"""Deterministic pattern parser for human input."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from vcse.interaction.errors import ParseError
from vcse.interaction.frames import (
    FrameParseResult,
    FrameStatus,
    ClaimFrame,
    GoalFrame,
    ConstraintFrame,
    DefinitionFrame,
    QuestionFrame,
)


# Comparison operators
COMPARISON_OPS = {">", "<", ">=", "<=", "=", "equals"}


@dataclass
class PatternParser:
    """Deterministic pattern parser for semantic frames."""

    def parse(self, text: str) -> FrameParseResult:
        """Parse text into frames."""
        result = FrameParseResult()

        # Handle empty input
        if not text or not text.strip():
            result.status = FrameStatus.FAILED
            result.errors.append("Empty input")
            return result

        # Split on statements (periods, semicolons, newlines)
        statements = self._split_statements(text)

        all_frames = []
        for stmt_text in statements:
            stmt_text = stmt_text.strip()
            if not stmt_text:
                continue

            stmt_result = self._parse_statement(stmt_text)
            if stmt_result.status == FrameStatus.FAILED:
                result.errors.extend(stmt_result.errors)
            elif stmt_result.status == FrameStatus.UNSUPPORTED:
                result.warnings.append(f"Unsupported: {stmt_text}")
            else:
                all_frames.extend(stmt_result.frames)

        if all_frames:
            result.frames = all_frames
            result.status = FrameStatus.PARSED
            result.confidence = 0.9
        elif not result.errors:
            result.status = FrameStatus.PARTIAL
            result.confidence = 0.3

        return result

    def _split_statements(self, text: str) -> list[str]:
        """Split text into individual statements."""
        # Split on periods, semicolons, and newlines
        # But preserve patterns like "Mr." or "Dr."
        statements = re.split(r"[.;\n]+", text)
        return [s.strip() for s in statements if s.strip()]

    def _parse_statement(self, text: str) -> FrameParseResult:
        """Parse a single statement into frames."""
        result = FrameParseResult()
        text = text.strip()

        # Try each pattern in order of specificity
        # Questions first
        question_result = self._try_question(text)
        if question_result.status != FrameStatus.UNSUPPORTED:
            return question_result

        # Claim patterns
        claim_result = self._try_claim(text)
        if claim_result.status != FrameStatus.UNSUPPORTED:
            return claim_result

        # Arithmetic patterns
        arith_result = self._try_arithmetic(text)
        if arith_result.status != FrameStatus.UNSUPPORTED:
            return arith_result

        # If nothing matched, return unsupported
        result.status = FrameStatus.UNSUPPORTED
        result.warnings.append(f"No pattern matched: {text}")
        return result

    def _try_question(self, text: str) -> FrameParseResult:
        """Try to parse as a question."""
        result = FrameParseResult()

        # Must end with "?" to be a question
        if not text.strip().endswith("?"):
            result.status = FrameStatus.UNSUPPORTED
            return result

        # "Is X a Y?" / "Is X Y?"
        m = re.match(r"^is\s+(.+?)\s+(?:a|an)?\s*(.+?)\??$", text, re.IGNORECASE)
        if m:
            subject, obj = m.group(1).strip(), m.group(2).strip()
            frame = GoalFrame(
                subject=self._canonicalize(subject),
                relation="is_a",
                object=obj,
                source_text=text,
            )
            result.frames.append(frame)
            result.status = FrameStatus.PARSED
            result.confidence = 0.9
            return result

        # "Can X die?" - normalized form "X is_a mortal"
        m = re.match(r"^(.+?)\s+is_a\s+(.+?)\??$", text, re.IGNORECASE)
        if m:
            subject, obj = m.group(1).strip(), m.group(2).strip()
            frame = GoalFrame(
                subject=self._canonicalize(subject),
                relation="is_a",
                object=obj,
                source_text=text,
            )
            result.frames.append(frame)
            result.status = FrameStatus.PARSED
            result.confidence = 0.9
            return result

        # "Can X die?" / "Can X fly?" / "Can X swim?" / etc
        m = re.match(r"^can\s+(.+?)\s+(die|fly|swim|walk|run|jump|breathe|eat|drink|see|hear|think)\s*\??$", text, re.IGNORECASE)
        if m:
            subject = m.group(1).strip()
            frame = GoalFrame(
                subject=self._canonicalize(subject),
                relation="is_a",
                object="mortal",
                source_text=text,
            )
            result.frames.append(frame)
            result.status = FrameStatus.PARSED
            result.confidence = 0.9
            return result

        # "What is X?" / "What's X?"
        m = re.match(r"^(?:what is|what's)\s+(.+?)\??$", text, re.IGNORECASE)
        if m:
            target = m.group(1).strip()
            frame = QuestionFrame(
                question_type="definition",
                target=target,
                source_text=text,
            )
            result.frames.append(frame)
            result.status = FrameStatus.PARSED
            result.confidence = 0.8
            return result

        # "Prove X is Y" / "Determine whether X is Y"
        m = re.match(r"^(?:prove|determine)\s+(?:whether\s+)?(.+?)\s+(?:is|are|equals)\s+(.+?)\??$", text, re.IGNORECASE)
        if m:
            subject, obj = m.group(1).strip(), m.group(2).strip()
            frame = GoalFrame(
                subject=self._canonicalize(subject),
                relation="is_a",
                object=obj,
                source_text=text,
            )
            result.frames.append(frame)
            result.status = FrameStatus.PARSED
            result.confidence = 0.9
            return result

        # No question pattern matched
        result.status = FrameStatus.UNSUPPORTED
        return result

    def _try_claim(self, text: str) -> FrameParseResult:
        """Try to parse as a claim."""
        result = FrameParseResult()

        # "X is_a Y" - explicit is_a relation
        m = re.match(r"^(.+?)\s+is_a\s+(.+?)\.?$", text, re.IGNORECASE)
        if m:
            subject, obj = m.group(1).strip(), m.group(2).strip()
            frame = ClaimFrame(
                subject=self._canonicalize(subject),
                relation="is_a",
                object=obj,
                source_text=text,
            )
            result.frames.append(frame)
            result.status = FrameStatus.PARSED
            result.confidence = 0.9
            return result

        # "X is a Y" / "X is an Y" / "X is Y"
        m = re.match(r"^(.+?)\s+is\s+(?:a|an)?\s*(.+?)\.?$", text, re.IGNORECASE)
        if m:
            subject, obj = m.group(1).strip(), m.group(2).strip()
            frame = ClaimFrame(
                subject=self._canonicalize(subject),
                relation="is_a",
                object=obj,
                source_text=text,
            )
            result.frames.append(frame)
            result.status = FrameStatus.PARSED
            result.confidence = 0.9
            return result

        # "All X are Y" / "Every X is Y"
        m = re.match(r"^(?:all|every)\s+(.+?)\s+(?:are|is)\s+(.+?)\.?$", text, re.IGNORECASE)
        if m:
            subject, obj = m.group(1).strip(), m.group(2).strip()
            frame = ClaimFrame(
                subject=self._canonicalize(subject),
                relation="is_a",
                object=obj,
                source_text=text,
            )
            result.frames.append(frame)
            result.status = FrameStatus.PARSED
            result.confidence = 0.9
            return result

        # "X equals Y" / "X is equal to Y" / "X is the same as Y"
        m = re.match(r"^(.+?)\s+(?:is\s+)?(?:equal to|same as|equals)\s+(.+?)\.?$", text, re.IGNORECASE)
        if m:
            subject, obj = m.group(1).strip(), m.group(2).strip()
            frame = ClaimFrame(
                subject=self._canonicalize(subject),
                relation="equals",
                object=obj,
                source_text=text,
            )
            result.frames.append(frame)
            result.status = FrameStatus.PARSED
            result.confidence = 0.9
            return result

        # "X is part of Y"
        m = re.match(r"^(.+?)\s+is\s+part\s+of\s+(.+?)\.?$", text, re.IGNORECASE)
        if m:
            subject, obj = m.group(1).strip(), m.group(2).strip()
            frame = ClaimFrame(
                subject=self._canonicalize(subject),
                relation="part_of",
                object=obj,
                source_text=text,
            )
            result.frames.append(frame)
            result.status = FrameStatus.PARSED
            result.confidence = 0.9
            return result

        # No claim pattern matched
        result.status = FrameStatus.UNSUPPORTED
        return result

    def _try_arithmetic(self, text: str) -> FrameParseResult:
        """Try to parse as arithmetic constraint."""
        result = FrameParseResult()

        # "x = 5" / "x equals 5"
        m = re.match(r"^(.+?)\s*(?:equals|=)\s*(.+?)\.?$", text, re.IGNORECASE)
        if m:
            target = m.group(1).strip()
            value = m.group(2).strip()
            # Check if value is numeric
            try:
                float(value)
                frame = ConstraintFrame(
                    target=target,
                    operator="=",
                    value=value,
                    source_text=text,
                )
                result.frames.append(frame)
                result.status = FrameStatus.PARSED
                result.confidence = 0.9
                return result
            except ValueError:
                pass

        # "x > 0" / "x is greater than 0"
        m = re.match(r"^(.+?)\s*(?:is\s+)?(?:greater than |>)\s*(.+?)\.?$", text, re.IGNORECASE)
        if m:
            target, value = m.group(1).strip(), m.group(2).strip()
            try:
                float(value)
                frame = ConstraintFrame(
                    target=target,
                    operator=">",
                    value=value,
                    source_text=text,
                )
                result.frames.append(frame)
                result.status = FrameStatus.PARSED
                result.confidence = 0.9
                return result
            except ValueError:
                pass

        # "x < 10" / "x is less than 10"
        m = re.match(r"^(.+?)\s*(?:is\s+)?(?:less than |<)\s*(.+?)\.?$", text, re.IGNORECASE)
        if m:
            target, value = m.group(1).strip(), m.group(2).strip()
            try:
                float(value)
                frame = ConstraintFrame(
                    target=target,
                    operator="<",
                    value=value,
                    source_text=text,
                )
                result.frames.append(frame)
                result.status = FrameStatus.PARSED
                result.confidence = 0.9
                return result
            except ValueError:
                pass

        # "x >= 5" / "x is at least 5"
        m = re.match(r"^(.+?)\s*(?:is\s+)?(?:at least|>=\s*)\s*(.+?)\.?$", text, re.IGNORECASE)
        if m:
            target, value = m.group(1).strip(), m.group(2).strip()
            try:
                float(value)
                frame = ConstraintFrame(
                    target=target,
                    operator=">=",
                    value=value,
                    source_text=text,
                )
                result.frames.append(frame)
                result.status = FrameStatus.PARSED
                result.confidence = 0.9
                return result
            except ValueError:
                pass

        # "x <= 10" / "x is at most 10"
        m = re.match(r"^(.+?)\s*(?:is\s+)?(?:at most|<=\s*)\s*(.+?)\.?$", text, re.IGNORECASE)
        if m:
            target, value = m.group(1).strip(), m.group(2).strip()
            try:
                float(value)
                frame = ConstraintFrame(
                    target=target,
                    operator="<=",
                    value=value,
                    source_text=text,
                )
                result.frames.append(frame)
                result.status = FrameStatus.PARSED
                result.confidence = 0.9
                return result
            except ValueError:
                pass

        # No arithmetic pattern matched
        result.status = FrameStatus.UNSUPPORTED
        return result

    def _canonicalize(self, text: str) -> str:
        """Canonicalize a term name."""
        # Remove leading/trailing whitespace, lowercase
        return text.strip().lower()
