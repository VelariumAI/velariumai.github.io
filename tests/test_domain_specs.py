from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from vcse.domain.loader import DomainSpecError, load_domain_spec
from vcse.packs.sharding import assign_shard
from vcse.query.planner import QueryPlanner


ROOT = Path(__file__).resolve().parents[1]
GEO_SPEC = ROOT / "domains" / "geography.yaml"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(ROOT / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-m", "vcse.cli", *args], capture_output=True, text=True, env=env)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_geography_spec_loads_successfully() -> None:
    spec = load_domain_spec(GEO_SPEC)
    assert spec.domain_id == "geography"
    assert len(spec.relations) == 10


def test_malformed_spec_fails_clearly(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("domain_id: bad\nname: Bad\nversion: 1.0.0\n")
    with pytest.raises(DomainSpecError, match="Missing required field 'relations'"):
        load_domain_spec(bad)


def test_relation_count_matches_expected() -> None:
    spec = load_domain_spec(GEO_SPEC)
    assert len(spec.relations) == 10


def test_shard_mappings_match_current_hardcoded_behavior() -> None:
    assert assign_shard({"relation": "has_capital"}) == "geography.capitals"
    assert assign_shard({"relation": "capital_of"}) == "geography.capitals"
    assert assign_shard({"relation": "located_in_country"}) == "geography.location"
    assert assign_shard({"relation": "located_in_region"}) == "geography.location"
    assert assign_shard({"relation": "located_in_subregion"}) == "geography.location"
    assert assign_shard({"relation": "part_of"}) == "geography.location"
    assert assign_shard({"relation": "uses_currency"}) == "geography.currency"
    assert assign_shard({"relation": "language_of"}) == "geography.language"
    assert assign_shard({"relation": "has_country_code"}) == "geography.codes"
    assert assign_shard({"relation": "shares_border_with"}) == "geography.borders"
    assert assign_shard({"relation": "unknown_relation"}) == "misc.unknown"


def test_query_patterns_present_for_supported_queries() -> None:
    spec = load_domain_spec(GEO_SPEC)
    patterns = {item.pattern for item in spec.query_patterns}
    assert "What is the capital of {subject}?" in patterns
    assert "What is {subject} the capital of?" in patterns
    assert "What currency does {subject} use?" in patterns
    assert "What language is spoken in {subject}?" in patterns
    assert "What is the country code of {subject}?" in patterns
    assert "What region is {subject} in?" in patterns
    assert "What continent is {subject} in?" in patterns


def test_inference_rules_present_but_no_new_behavior() -> None:
    spec = load_domain_spec(GEO_SPEC)
    rule_ids = {item.rule_id for item in spec.inference_rules}
    assert "inverse_relation" in rule_ids
    assert "transitive_location_containment" in rule_ids

    planner = QueryPlanner()
    capital_plan = planner.plan_for_claim("Paris", "capital_of")
    assert capital_plan is not None
    assert capital_plan.target_relation == "has_capital"

    unsupported_plan = planner.plan_for_claim("France", "shares_border_with")
    assert unsupported_plan is None


def test_spec_validation_catches_ontology_contradiction(tmp_path: Path) -> None:
    payload = {
        "domain_id": "geography",
        "name": "Geography",
        "version": "1.0.0",
        "relations": [
            {
                "relation": "has_capital",
                "canonical": "capital_of",
                "inverse": "capital_of",
                "domain": "Country",
                "range": "City",
                "functional": True,
                "symmetric": False,
                "transitive": False,
                "shard": "geography.capitals",
            }
        ],
        "query_patterns": [
            {
                "pattern": "What is the capital of {subject}?",
                "relation": "has_capital",
                "query_type": "wh",
                "subject_slot": "subject",
                "object_slot": "object",
            }
        ],
        "shard_rules": [
            {"shard_id": "geography.capitals", "relations": ["has_capital"]},
            {"shard_id": "misc.unknown", "relations": []},
        ],
        "inference_rules": [
            {
                "rule_id": "inverse_relation",
                "output_relation": "has_capital",
                "required_relations": ["has_capital"],
                "max_hops": 1,
            }
        ],
        "benchmark_templates": [
            {
                "relation": "has_capital",
                "template": "What is the capital of {subject}?",
                "expected_slot": "object",
            }
        ],
    }
    bad = tmp_path / "contradiction.json"
    bad.write_text(json.dumps(payload))
    with pytest.raises(DomainSpecError, match="Ontology contradiction"):
        load_domain_spec(bad)


def test_cli_domain_list_inspect_validate_works() -> None:
    listing = run_cli("domain", "list")
    assert listing.returncode == 0
    assert "domain_id: geography" in listing.stdout

    inspect_out = run_cli("domain", "inspect", "geography")
    assert inspect_out.returncode == 0
    assert "relation_count: 10" in inspect_out.stdout

    validate_out = run_cli("domain", "validate", "domains/geography.yaml")
    assert validate_out.returncode == 0
    assert "status: VALID" in validate_out.stdout


def test_no_network_access() -> None:
    with pytest.raises(DomainSpecError, match="Network loading is not allowed"):
        load_domain_spec(Path("https://example.com/geography.yaml"))


def test_no_pack_mutation() -> None:
    pack_dir = ROOT / "examples" / "packs" / "general_world"
    before = {
        "pack": _sha(pack_dir / "pack.json"),
        "claims": _sha(pack_dir / "claims.jsonl"),
        "provenance": _sha(pack_dir / "provenance.jsonl"),
    }

    run_cli("domain", "list")
    run_cli("domain", "inspect", "geography")
    run_cli("domain", "validate", "domains/geography.yaml")

    after = {
        "pack": _sha(pack_dir / "pack.json"),
        "claims": _sha(pack_dir / "claims.jsonl"),
        "provenance": _sha(pack_dir / "provenance.jsonl"),
    }
    assert before == after
