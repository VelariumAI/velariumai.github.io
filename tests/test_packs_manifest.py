import json
from pathlib import Path

from vcse.packs.loader import load_manifest
from vcse.packs.manifest import PackManifest


def test_manifest_unknown_fields_are_warned() -> None:
    manifest = PackManifest.from_dict(
        {
            "id": "vrm.logic.basic",
            "name": "Logic",
            "version": "1.0.0",
            "description": "desc",
            "domain": "logic",
            "authors": ["x"],
            "license": "MIT",
            "created_at": "2026-01-01T00:00:00Z",
            "vcse_min_version": "2.2.0",
            "dependencies": [],
            "artifacts": {"dsl": ["dsl/basic_logic.json"]},
            "benchmarks": [],
            "gauntlet_cases": [],
            "provenance": [],
            "integrity": {"hash_algorithm": "sha256", "manifest_hash": "", "artifact_hashes": {}},
            "extra_field": "ignored",
        }
    )

    assert manifest.id == "vrm.logic.basic"
    assert any("unknown manifest field" in warning for warning in manifest.warnings)


def test_load_manifest_from_example_pack() -> None:
    path = Path(__file__).resolve().parents[1] / "examples" / "packs" / "logic_basic"
    manifest, root = load_manifest(path)

    assert manifest.id == "vrm.logic.basic"
    assert root == path
    assert "dsl" in manifest.artifacts
