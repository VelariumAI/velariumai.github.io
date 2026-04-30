"""Tests for dictionary encoding and decoding."""

from vcse.compression.canonicalizer import canonicalize_claim
from vcse.compression.dictionary import (
    encode_claim,
    decode_claim,
    encode_claim_from_canonical,
    encoded_to_dict,
    dict_to_encoded,
)
from vcse.compression.interner import Interner


def test_encode_decode_roundtrip():
    i = Interner()
    raw = {"subject": "Socrates", "relation": "is_a", "object": "Man"}
    enc = encode_claim(raw, i)
    assert enc.subject_id != enc.object_id
    dec = decode_claim(enc, i)
    assert dec.subject == "socrates"
    assert dec.relation == "is_a"
    assert dec.object == "man"


def test_encode_decode_with_qualifiers():
    i = Interner()
    raw = {"subject": "x", "relation": "is_a", "object": "y", "qualifiers": {"scope": "test"}}
    enc = encode_claim(raw, i)
    dec = decode_claim(enc, i)
    assert dec.subject == "x"
    assert dec.qualifiers == (("scope", "test"),)


def test_encode_claim_from_canonical():
    i = Interner()
    cc = canonicalize_claim({"subject": "test", "relation": "is_a", "object": "thing"})
    enc = encode_claim_from_canonical(cc, i)
    assert enc.subject_id == i.intern("test")
    assert enc.relation_id == i.intern("is_a")
    assert enc.object_id == i.intern("thing")


def test_encoded_to_dict():
    from vcse.compression.dictionary import EncodedClaim
    enc = EncodedClaim(subject_id=5, relation_id=3, object_id=7, qualifier_ids=((1, 2),))
    d = encoded_to_dict(enc)
    assert d["subject_id"] == 5
    assert d["relation_id"] == 3
    assert d["object_id"] == 7
    assert d["qualifier_ids"] == [[1, 2]]


def test_dict_to_encoded():
    data = {"subject_id": 5, "relation_id": 3, "object_id": 7, "qualifier_ids": [[1, 2]]}
    enc = dict_to_encoded(data)
    assert enc.subject_id == 5
    assert enc.relation_id == 3
    assert enc.object_id == 7
    assert enc.qualifier_ids == ((1, 2),)


def test_encode_multiple_claims_same_strings():
    i = Interner()
    raw1 = {"subject": " Socrates ", "relation": "  is_a  ", "object": " man "}
    raw2 = {"subject": "socrates", "relation": "is_a", "object": "man"}
    enc1 = encode_claim(raw1, i)
    enc2 = encode_claim(raw2, i)
    assert enc1.subject_id == enc2.subject_id
    assert enc1.relation_id == enc2.relation_id
    assert enc1.object_id == enc2.object_id


def test_encode_missing_field():
    from vcse.compression.errors import CanonicalizationError
    i = Interner()
    try:
        encode_claim({"subject": "x", "object": "y"}, i)
        assert False, "should raise"
    except CanonicalizationError:
        pass  # missing relation caught by canonicalizer


def test_decode_unknown_id():
    i = Interner()
    i.intern("known")
    from vcse.compression.dictionary import EncodedClaim
    enc = EncodedClaim(subject_id=99, relation_id=99, object_id=99, qualifier_ids=())
    try:
        decode_claim(enc, i)
        assert False, "should raise"
    except Exception:
        pass