"""Tests for provenance compression."""

from vcse.compression.provenance import ProvenanceCompressor, _provenance_fingerprint


def test_provenance_fingerprint_deterministic():
    entry = {"source_id": "s1", "source_type": "text", "location": "loc1", "evidence_text": "ev1", "trust_level": "trusted", "confidence": 0.9}
    fp1 = _provenance_fingerprint(entry)
    fp2 = _provenance_fingerprint(entry)
    assert fp1 == fp2


def test_provenance_fingerprint_different_entries():
    e1 = {"source_id": "s1", "source_type": "text", "location": "l1", "evidence_text": "e1", "trust_level": "trusted", "confidence": 0.9}
    e2 = {"source_id": "s2", "source_type": "text", "location": "l1", "evidence_text": "e1", "trust_level": "trusted", "confidence": 0.9}
    assert _provenance_fingerprint(e1) != _provenance_fingerprint(e2)


def test_provenance_add_deduplication():
    pc = ProvenanceCompressor()
    entry = {"source_id": "s1", "source_type": "text", "location": "loc1", "evidence_text": "ev1", "trust_level": "trusted", "confidence": 0.9}
    id1 = pc.add(entry)
    id2 = pc.add(entry)
    assert id1 == id2


def test_provenance_add_different_entries():
    pc = ProvenanceCompressor()
    e1 = {"source_id": "s1", "source_type": "text", "location": "l1", "evidence_text": "e1", "trust_level": "trusted", "confidence": 0.9}
    e2 = {"source_id": "s2", "source_type": "text", "location": "l1", "evidence_text": "e1", "trust_level": "trusted", "confidence": 0.9}
    id1 = pc.add(e1)
    id2 = pc.add(e2)
    assert id1 != id2


def test_provenance_get():
    pc = ProvenanceCompressor()
    entry = {"source_id": "s1", "source_type": "text", "location": "loc1", "evidence_text": "ev1", "trust_level": "trusted", "confidence": 0.9}
    ref_id = pc.add(entry)
    retrieved = pc.get(ref_id)
    assert retrieved["source_id"] == "s1"


def test_provenance_to_dict():
    pc = ProvenanceCompressor()
    pc.add({"source_id": "s1", "source_type": "text", "location": "l1", "evidence_text": "e1", "trust_level": "trusted", "confidence": 0.9})
    pc.add({"source_id": "s2", "source_type": "text", "location": "l2", "evidence_text": "e2", "trust_level": "trusted", "confidence": 0.9})
    d = pc.to_dict()
    assert len(d["entries"]) == 2


def test_provenance_from_dict():
    data = {"entries": [
        {"source_id": "s1", "source_type": "text", "location": "l1", "evidence_text": "e1", "trust_level": "trusted", "confidence": 0.9},
        {"source_id": "s2", "source_type": "text", "location": "l2", "evidence_text": "e2", "trust_level": "trusted", "confidence": 0.9},
    ]}
    pc = ProvenanceCompressor.from_dict(data)
    assert pc.size == 2
    assert pc.get(0)["source_id"] == "s1"


def test_provenance_size():
    pc = ProvenanceCompressor()
    assert pc.size == 0
    pc.add({"source_id": "s1", "source_type": "text", "location": "l1", "evidence_text": "e1", "trust_level": "trusted", "confidence": 0.9})
    pc.add({"source_id": "s1", "source_type": "text", "location": "l1", "evidence_text": "e1", "trust_level": "trusted", "confidence": 0.9})
    pc.add({"source_id": "s2", "source_type": "text", "location": "l2", "evidence_text": "e2", "trust_level": "trusted", "confidence": 0.9})
    assert pc.size == 2


def test_provenance_no_data_loss():
    original = {"source_id": "s1", "source_type": "text", "location": "loc1", "evidence_text": "ev1", "trust_level": "trusted", "confidence": 0.9}
    pc = ProvenanceCompressor()
    ref_id = pc.add(original)
    retrieved = pc.get(ref_id)
    assert retrieved == original