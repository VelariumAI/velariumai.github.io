import json
import subprocess
import sys
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_raw_sources_and_validation_artifacts_exist() -> None:
    root = _root()
    assert (root / "examples" / "knowledge" / "raw" / "iso_countries.json").exists()
    assert (root / "examples" / "knowledge" / "general_world_source_validation.json").exists()
    assert (root / "examples" / "knowledge" / "general_world_expanded.json").exists()
    assert (root / "examples" / "cake" / "general_world_seed.json").exists()


def test_validation_report_has_required_source_and_hash() -> None:
    report = json.loads((_root() / "examples" / "knowledge" / "general_world_source_validation.json").read_text())
    entries = {row["source_id"]: row for row in report["sources"]}
    assert "iso_countries" in entries
    assert entries["iso_countries"]["status"] == "ok"
    assert entries["iso_countries"]["record_count"] > 0
    assert entries["iso_countries"]["sha256"]


def test_merged_dataset_required_fields_and_unique_countries() -> None:
    merged = json.loads((_root() / "examples" / "knowledge" / "general_world_expanded.json").read_text())
    assert len(merged) >= 100
    seen = set()
    for row in merged:
        country = row["country"]
        assert country not in seen
        seen.add(country)
        assert row["capital"]
        assert row["region"] or row["continent"]
        assert row["currency"] or row["currency_code"]
        assert row["languages"]
        assert row["country_code"]
        assert row["source_ids"]


def test_generator_is_deterministic() -> None:
    root = _root()
    seed_path = root / "examples" / "cake" / "general_world_seed.json"
    before = seed_path.read_text()
    subprocess.run([sys.executable, str(root / "scripts" / "generate_general_world_seed.py")], check=True)
    after = seed_path.read_text()
    assert before == after

