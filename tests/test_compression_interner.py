"""Tests for string interning."""

from vcse.compression.interner import Interner


def test_intern_basic():
    i = Interner()
    id1 = i.intern("hello")
    id2 = i.intern("world")
    assert id1 != id2
    assert i.resolve(id1) == "hello"
    assert i.resolve(id2) == "world"


def test_intern_deduplication():
    i = Interner()
    id1 = i.intern("hello")
    id2 = i.intern("hello")
    id3 = i.intern("hello")
    assert id1 == id2 == id3


def test_intern_multiple_strings():
    i = Interner()
    strings = ["alpha", "beta", "gamma", "alpha", "beta"]
    ids = [i.intern(s) for s in strings]
    assert ids[0] == ids[3]
    assert ids[1] == ids[4]
    assert ids[2] != ids[0]


def test_intern_resolve_roundtrip():
    i = Interner()
    for word in ["foo", "bar", "baz", "qux"]:
        i.intern(word)
    for word in ["foo", "bar", "baz", "qux"]:
        assert i.resolve(i.intern(word)) == word


def test_intern_resolve_unknown_id():
    i = Interner()
    i.intern("known")
    try:
        i.resolve(99)
        assert False, "should raise"
    except Exception:
        pass


def test_intern_contains():
    i = Interner()
    i.intern("present")
    assert i.contains("present")
    assert not i.contains("absent")


def test_intern_size():
    i = Interner()
    assert i.size == 0
    i.intern("a")
    i.intern("b")
    i.intern("a")
    assert i.size == 2


def test_intern_to_dict():
    i = Interner()
    i.intern("first")
    i.intern("second")
    d = i.to_dict()
    assert "string_to_id" in d
    assert "id_to_string" in d
    assert d["string_to_id"]["first"] == 0
    assert d["id_to_string"]["0"] == "first"


def test_intern_from_dict():
    data = {
        "string_to_id": {"x": 0, "y": 1, "z": 2},
        "id_to_string": {"0": "x", "1": "y", "2": "z"},
    }
    i = Interner.from_dict(data)
    assert i.resolve(0) == "x"
    assert i.resolve(1) == "y"
    assert i.resolve(2) == "z"
    assert i.intern("x") == 0
    assert i.intern("w") == 3


def test_intern_deterministic_order():
    """IDs assigned in insertion order; same string within one instance is stable."""
    i1 = Interner()
    i2 = Interner()
    words = ["zebra", "apple", "banana"]
    for w in words:
        i1.intern(w)
    for w in reversed(words):
        i2.intern(w)
    # ID 0 is "zebra" in i1 (first insertion)
    assert i1.resolve(0) == "zebra"
    # Within each interner, same string maps to same ID
    assert i1.intern("zebra") == i1.intern("zebra")
    assert i2.intern("zebra") == i2.intern("zebra")