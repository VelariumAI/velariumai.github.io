"""Semantic normalization: convert messy human text into canonical forms."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


# Relation phrase -> canonical relation mapping
RELATION_MAP: dict[str, str] = {
    "is a": "is_a",
    "is an": "is_a",
    "is": "is_a",
    "is the same as": "equals",
    "is equal to": "equals",
    "same as": "equals",
    "equals": "equals",
    "is part of": "part_of",
    "part of": "part_of",
    "part_of": "part_of",
    "is_a": "is_a",
}

# Comparison phrase -> operator mapping
COMPARISON_MAP: dict[str, str] = {
    "greater than": ">",
    "less than": "<",
    "greater than or equal to": ">=",
    "less than or equal to": "<=",
    "at least": ">=",
    "at most": "<=",
    "more than": ">",
    "under": "<",
    "exceeds": ">",
    ">": ">",
    "<": "<",
    ">=": ">=",
    "<=": "<=",
    "equals": "=",
    "=" : "=",
}

# Synonym -> canonical surface form mapping
SYNONYM_MAP: dict[str, str] = {
    "die": "is mortal",
    "dies": "is mortal",
    "dead": "dead",
    "mortal": "mortal",
    "man": "man",
    "men": "man",
    "human": "human",
    "humans": "human",
    "person": "person",
    "people": "person",
    "alive": "alive",
    "living": "living",
    "death": "mortal",
}

# Phrase canonicalization patterns
PHRASE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bis (\w+) a kind of\b", re.IGNORECASE), r"\1 is_a"),
]


@dataclass
class NormalizedInput:
    """Result of semantic normalization."""

    original_text: str
    normalized_text: str
    tokens: list[str]
    replacements_applied: list[tuple[str, str]]
    confidence: float
    warnings: list[str] = field(default_factory=list)
    is_question: bool = False


class SemanticNormalizer:
    """Deterministic text normalization for VCSE interaction layer."""

    def normalize(self, text: str) -> NormalizedInput:
        """Normalize input text into canonical form."""
        original = text
        replacements: list[tuple[str, str]] = []

        # Step 1: Unicode normalization
        text = unicodedata.normalize("NFKC", text)

        # Step 2: Case normalization
        text = text.lower()

        # Step 3: Whitespace cleanup
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

        # Step 4: Punctuation cleanup - remove leading/trailing punctuation
        text = re.sub(r"^[^\w\s]+", "", text)
        text = re.sub(r"[^\w\s]+$", "", text)

        # Step 5: Handle comparison operators
        text = self._apply_comparison_canonicalization(text, replacements)

        # Step 6: Apply phrase canonicalization patterns
        for pattern, replacement in PHRASE_PATTERNS:
            new_text = pattern.sub(replacement, text)
            if new_text != text:
                replacements.append((pattern.pattern, replacement))
                text = new_text

        # Step 7: Relation phrase replacement
        text = self._apply_relation_canonicalization(text, replacements)

        # Step 8: Synonym replacement
        text = self._apply_synonym_canonicalization(text, replacements)

        # Step 9: Final cleanup
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

        # Tokenize
        tokens = text.split()

        # Calculate confidence
        confidence = self._compute_confidence(original, text, replacements)

        # Detect question
        is_question = "?" in original or "can " in text or "does " in text or "is " in text or "what " in text or "how " in text or "prove " in text or "determine " in text

        return NormalizedInput(
            original_text=original,
            normalized_text=text,
            tokens=tokens,
            replacements_applied=replacements,
            confidence=confidence,
            warnings=self._compute_warnings(original, text),
            is_question=is_question,
        )

    def _apply_comparison_canonicalization(
        self, text: str, replacements: list[tuple[str, str]]
    ) -> str:
        """Replace comparison phrases with operators."""
        for phrase, op in COMPARISON_MAP.items():
            if phrase in text:
                pattern = re.compile(
                    re.escape(phrase), re.IGNORECASE
                )
                new_text = pattern.sub(op, text)
                if new_text != text:
                    replacements.append((phrase, op))
                    return new_text
        return text

    def _apply_relation_canonicalization(
        self, text: str, replacements: list[tuple[str, str]]
    ) -> str:
        """Replace relation phrases with canonical relations."""
        sorted_relations = sorted(RELATION_MAP.keys(), key=len, reverse=True)
        for phrase in sorted_relations:
            canonical = RELATION_MAP[phrase]
            pattern = re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)
            new_text, count = pattern.subn(canonical, text)
            if count:
                replacements.append((phrase, canonical))
                text = new_text
        return text

    def _apply_synonym_canonicalization(
        self, text: str, replacements: list[tuple[str, str]]
    ) -> str:
        """Replace synonyms with canonical forms."""
        for phrase, canonical in SYNONYM_MAP.items():
            pattern = re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)
            new_text, count = pattern.subn(canonical, text)
            if count:
                replacements.append((phrase, canonical))
                text = new_text
        return text

    def _compute_confidence(
        self, original: str, normalized: str, replacements: list[tuple[str, str]]
    ) -> float:
        """Compute confidence score for normalization."""
        if not original.strip():
            return 0.0

        if len(replacements) == 0:
            if original.lower().strip() == normalized:
                return 1.0
            return 0.9

        confidence = 1.0 - (len(replacements) * 0.1)
        return max(0.5, min(1.0, confidence))

    def _compute_warnings(self, original: str, normalized: str) -> list[str]:
        """Compute warnings about normalization."""
        warnings: list[str] = []

        if len(normalized) < 3 and len(original) >= 3:
            warnings.append("Input normalized to very short form")

        if len(re.findall(r"[^\w\s]", original)) > 3:
            warnings.append("Heavy punctuation removed")

        return warnings
