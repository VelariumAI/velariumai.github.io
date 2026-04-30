"""Tests for WikidataExtractor and DBpediaExtractor."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from vcse.cake.extractor_wikidata import WikidataExtractor, PROPERTY_MAP
from vcse.cake.extractor_dbpedia import DBpediaExtractor
from vcse.cake.snapshot import FetchedSource
from vcse.cake.errors import CakeExtractionError
from vcse.knowledge.pack_model import KnowledgeClaim


WIKIDATA_SAMPLE_PATH = Path("examples/cake/wikidata_sample.json")
DBPEDIA_SAMPLE_PATH = Path("examples/cake/dbpedia_sample.ttl")


def _fetched(source_id: str, content: bytes) -> FetchedSource:
    return FetchedSource(
        source_id=source_id,
        raw_bytes=content,
        content_hash=hashlib.sha256(content).hexdigest(),
        fetched_at="2026-04-27T00:00:00+00:00",
        transport_type="file",
        origin="test",
    )


def _wikidata_fetched() -> FetchedSource:
    return _fetched("wikidata_src", WIKIDATA_SAMPLE_PATH.read_bytes())


def _dbpedia_fetched() -> FetchedSource:
    return _fetched("dbpedia_src", DBPEDIA_SAMPLE_PATH.read_bytes())


# ─── WikidataExtractor ────────────────────────────────────────────

def test_wikidata_extracts_paris_capital_of_france():
    extractor = WikidataExtractor()
    claims = extractor.extract(_wikidata_fetched(), snapshot_id="wikidata_src/abc123")
    keys = [(c.subject, c.relation, c.object) for c in claims]
    assert ("Paris", "capital_of", "France") in keys


def test_wikidata_extracts_located_in_country():
    extractor = WikidataExtractor()
    claims = extractor.extract(_wikidata_fetched(), snapshot_id="wikidata_src/abc123")
    keys = [(c.subject, c.relation, c.object) for c in claims]
    assert ("Paris", "located_in_country", "France") in keys


def test_wikidata_extracts_instance_of():
    extractor = WikidataExtractor()
    claims = extractor.extract(_wikidata_fetched(), snapshot_id="wikidata_src/abc123")
    keys = [(c.subject, c.relation, c.object) for c in claims]
    assert ("Paris", "instance_of", "city") in keys


def test_wikidata_claims_have_provenance():
    extractor = WikidataExtractor()
    claims = extractor.extract(_wikidata_fetched(), snapshot_id="wikidata_src/abc123")
    for claim in claims:
        assert claim.provenance.source_id == "wikidata_src"
        assert claim.provenance.source_type == "wikidata_json"
        assert "abc123" in claim.provenance.location


def test_wikidata_claims_have_snapshot_id_in_qualifiers():
    extractor = WikidataExtractor()
    claims = extractor.extract(_wikidata_fetched(), snapshot_id="wikidata_src/abc123")
    for claim in claims:
        assert "snapshot_id" in claim.qualifiers


def test_wikidata_rejects_malformed_json():
    fetched = _fetched("bad_src", b"{not valid json")
    extractor = WikidataExtractor()
    with pytest.raises(CakeExtractionError) as exc_info:
        extractor.extract(fetched, snapshot_id="bad_src/xxx")
    assert "MALFORMED_JSON" in exc_info.value.error_type


def test_wikidata_empty_entities_returns_empty_list():
    fetched = _fetched("empty_src", json.dumps({"entities": {}}).encode())
    extractor = WikidataExtractor()
    claims = extractor.extract(fetched, snapshot_id="empty_src/yyy")
    assert claims == []


def test_wikidata_limit_respected():
    # Build wikidata JSON with 10 entities each having 1 P36 claim
    entities = {}
    for i in range(10):
        qid = f"Q{i}"
        obj_qid = f"Q{100 + i}"
        entities[qid] = {
            "id": qid,
            "labels": {"en": {"value": f"Entity{i}"}},
            "claims": {
                "P36": [{
                    "mainsnak": {
                        "datavalue": {"value": {"entity-type": "item", "id": obj_qid}}
                    }
                }]
            }
        }
        entities[obj_qid] = {
            "id": obj_qid,
            "labels": {"en": {"value": f"Object{i}"}},
            "claims": {}
        }
    fetched = _fetched("limit_src", json.dumps({"entities": entities}).encode())
    extractor = WikidataExtractor()
    claims = extractor.extract(fetched, snapshot_id="limit_src/zzz", limit=3)
    assert len(claims) <= 3


def test_property_map_has_required_mappings():
    assert "P36" in PROPERTY_MAP
    assert PROPERTY_MAP["P36"] == "capital_of"
    assert "P17" in PROPERTY_MAP
    assert PROPERTY_MAP["P17"] == "located_in_country"
    assert "P31" in PROPERTY_MAP
    assert PROPERTY_MAP["P31"] == "instance_of"


# ─── DBpediaExtractor ─────────────────────────────────────────────

def test_dbpedia_extracts_paris_capital_of_france():
    extractor = DBpediaExtractor()
    claims = extractor.extract(_dbpedia_fetched(), snapshot_id="dbpedia_src/abc")
    keys = [(c.subject, c.relation, c.object) for c in claims]
    assert ("Paris", "capital_of", "France") in keys


def test_dbpedia_extracts_country_relation():
    extractor = DBpediaExtractor()
    claims = extractor.extract(_dbpedia_fetched(), snapshot_id="dbpedia_src/abc")
    keys = [(c.subject, c.relation, c.object) for c in claims]
    assert ("Paris", "country", "France") in keys


def test_dbpedia_skips_comment_lines():
    content = b"# This is a comment\n<http://dbpedia.org/resource/A> <http://b.org/rel> <http://c.org/B> .\n"
    extractor = DBpediaExtractor()
    claims = extractor.extract(_fetched("db", content), snapshot_id="db/abc")
    assert len(claims) == 1
    assert claims[0].subject == "A"


def test_dbpedia_rejects_malformed_triple(caplog):
    content = b"this is not a valid triple\n<http://a.org/A> <http://b.org/rel> <http://c.org/B> .\n"
    extractor = DBpediaExtractor()
    # Malformed lines skipped with warning; valid ones extracted
    claims = extractor.extract(_fetched("db", content), snapshot_id="db/abc")
    assert len(claims) == 1


def test_dbpedia_empty_file_returns_empty():
    extractor = DBpediaExtractor()
    claims = extractor.extract(_fetched("empty", b""), snapshot_id="empty/abc")
    assert claims == []


def test_dbpedia_claims_have_provenance():
    extractor = DBpediaExtractor()
    claims = extractor.extract(_dbpedia_fetched(), snapshot_id="dbpedia_src/abc")
    for claim in claims:
        assert claim.provenance.source_id == "dbpedia_src"
        assert claim.provenance.source_type == "dbpedia_ttl"


def test_dbpedia_limit_respected():
    lines = [
        f"<http://a.org/{i}> <http://b.org/rel> <http://c.org/{i}> ."
        for i in range(20)
    ]
    content = "\n".join(lines).encode()
    extractor = DBpediaExtractor()
    claims = extractor.extract(_fetched("db", content), snapshot_id="db/abc", limit=5)
    assert len(claims) <= 5