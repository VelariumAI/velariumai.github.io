"""Tests for canonical claim normalization."""

from vcse.compression.canonicalizer import canonicalize_claim, CanonicalClaim


def test_canonicalize_basic():
    claim = {"subject": "Socrates", "relation": "is_a", "object": "Man"}
    result = canonicalize_claim(claim)
    assert result.subject == "socrates"
    assert result.relation == "is_a"
    assert result.object == "man"


def test_canonicalize_lowercase():
    claim = {"subject": "PLATO", "relation": "IS_A", "object": "PHILOSOPHER"}
    result = canonicalize_claim(claim)
    assert result.subject == "plato"
    assert result.relation == "is_a"
    assert result.object == "philosopher"


def test_canonicalize_relation_normalization():
    claim = {"subject": "x", "relation": "ISA", "object": "y"}
    result = canonicalize_claim(claim)
    assert result.relation == "is_a"


def test_canonicalize_whitespace():
    claim = {"subject": "  Socrates  ", "relation": "  is_a  ", "object": "  man  "}
    result = canonicalize_claim(claim)
    assert result.subject == "socrates"
    assert result.relation == "is_a"
    assert result.object == "man"


def test_canonicalize_qualifiers_sorted():
    claim = {"subject": "x", "relation": "is_a", "object": "y", "qualifiers": {"z": "w", "a": "b"}}
    result = canonicalize_claim(claim)
    assert result.qualifiers == (("a", "b"), ("z", "w"))


def test_canonicalize_empty_qualifiers():
    claim = {"subject": "x", "relation": "is_a", "object": "y", "qualifiers": {}}
    result = canonicalize_claim(claim)
    assert result.qualifiers == ()


def test_canonicalize_missing_subject():
    from vcse.compression.errors import CanonicalizationError
    claim = {"relation": "is_a", "object": "Man"}
    try:
        canonicalize_claim(claim)
        assert False, "should raise"
    except CanonicalizationError as exc:
        assert exc.code == "MISSING_SUBJECT"


def test_canonicalize_missing_relation():
    from vcse.compression.errors import CanonicalizationError
    claim = {"subject": "Socrates", "object": "Man"}
    try:
        canonicalize_claim(claim)
        assert False, "should raise"
    except CanonicalizationError as exc:
        assert exc.code == "MISSING_RELATION"


def test_canonicalize_empty_object():
    from vcse.compression.errors import CanonicalizationError
    claim = {"subject": "Socrates", "relation": "is_a", "object": ""}
    try:
        canonicalize_claim(claim)
        assert False, "should raise"
    except CanonicalizationError as exc:
        assert exc.code == "MISSING_OBJECT"


def test_canonicalize_idempotent():
    claim = {"subject": "socrates", "relation": "is_a", "object": "man"}
    result1 = canonicalize_claim(claim)
    result2 = canonicalize_claim(result1.to_dict())
    assert result1.subject == result2.subject
    assert result1.relation == result2.relation
    assert result1.object == result2.object
    assert result1.qualifiers == result2.qualifiers


def test_canonicalize_to_dict():
    claim = {"subject": "Socrates", "relation": "is_a", "object": "Man", "qualifiers": {"scope": "ancient"}}
    result = canonicalize_claim(claim)
    d = result.to_dict()
    assert d["subject"] == "socrates"
    assert d["relation"] == "is_a"
    assert d["object"] == "man"
    assert d["qualifiers"] == {"scope": "ancient"}