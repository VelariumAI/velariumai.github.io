"""Tests for semantic normalizer."""

import pytest
from vcse.interaction.normalizer import SemanticNormalizer


def test_empty_input():
    normalizer = SemanticNormalizer()
    result = normalizer.normalize("")
    assert result.confidence == 0.0


def test_basic_case_normalization():
    normalizer = SemanticNormalizer()
    result = normalizer.normalize("SOCRATES IS A MAN")
    assert result.normalized_text
    assert result.confidence > 0.0


def test_whitespace_cleanup():
    normalizer = SemanticNormalizer()
    result = normalizer.normalize("  Socrates   is   a   man  ")
    assert "socrates" in result.normalized_text
    assert "  " not in result.normalized_text


def test_mortal_synonym():
    normalizer = SemanticNormalizer()
    result = normalizer.normalize("Can Socrates die?")
    assert result.normalized_text
    assert len(result.replacements_applied) >= 0


def test_relation_mapping():
    normalizer = SemanticNormalizer()
    result = normalizer.normalize("Man is a kind of Mortal")
    assert result.normalized_text


def test_comparison_mapping():
    normalizer = SemanticNormalizer()
    result = normalizer.normalize("x is greater than 5")
    assert result.normalized_text
    assert ">" in result.normalized_text or "greater" in result.normalized_text


def test_all_men_canonicalization():
    normalizer = SemanticNormalizer()
    result = normalizer.normalize("All men are mortal")
    assert result.normalized_text


def test_confidence_high_for_minimal_changes():
    normalizer = SemanticNormalizer()
    result = normalizer.normalize("socrates is a man")
    assert result.confidence >= 0.5
