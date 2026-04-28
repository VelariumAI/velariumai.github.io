"""End-to-end pipeline tests for CAKE."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vcse.cake.pipeline import (
    CAKE_COMPLETE,
    CAKE_DRY_RUN,
    CAKE_FAILED,
    CakeRunReport,
    run_cake_pipeline,
)
from vcse.cake.errors import CakePipelineError


GENERAL_WORLD_CONFIG = Path("examples/cake/general_world_sources.json")


def test_dry_run_returns_cake_dry_run_status(tmp_path):
    report = run_cake_pipeline(
        GENERAL_WORLD_CONFIG,
        dry_run=True,
        pack_output_dir=tmp_path,
    )
    assert isinstance(report, CakeRunReport)
    assert report.status == CAKE_DRY_RUN
    assert report.dry_run is True


def test_dry_run_does_not_write_pack(tmp_path):
    run_cake_pipeline(
        GENERAL_WORLD_CONFIG,
        dry_run=True,
        pack_output_dir=tmp_path,
        snapshot_root=tmp_path / "snapshots",
    )
    # tmp_path should have no pack directories
    pack_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert pack_dirs == []


def test_live_run_extracts_claims(tmp_path):
    report = run_cake_pipeline(
        GENERAL_WORLD_CONFIG,
        dry_run=False,
        pack_output_dir=tmp_path,
        snapshot_root=tmp_path / "snapshots",
    )
    assert report.status in (CAKE_COMPLETE, "CAKE_PARTIAL")
    assert report.claims_extracted > 0


def test_live_run_paris_capital_of_france(tmp_path):
    report = run_cake_pipeline(
        GENERAL_WORLD_CONFIG,
        dry_run=False,
        pack_output_dir=tmp_path,
        snapshot_root=tmp_path / "snapshots",
    )
    # Find wikidata_capitals pack
    pack_dirs = list(tmp_path.iterdir())
    found = False
    for pack_dir in pack_dirs:
        claims_file = pack_dir / "claims.jsonl"
        if claims_file.exists():
            for line in claims_file.read_text().splitlines():
                if not line.strip():
                    continue
                c = json.loads(line)
                if c.get("subject") == "Paris" and c.get("relation") == "capital_of" and c.get("object") == "France":
                    found = True
                    break
    assert found, "Paris → capital_of → France not found in any pack"


def test_report_has_all_required_fields(tmp_path):
    report = run_cake_pipeline(
        GENERAL_WORLD_CONFIG,
        dry_run=True,
        pack_output_dir=tmp_path,
    )
    assert hasattr(report, "run_id")
    assert hasattr(report, "source_ids")
    assert hasattr(report, "snapshot_ids")
    assert hasattr(report, "source_reports")
    assert hasattr(report, "claims_extracted")
    assert hasattr(report, "claims_normalized")
    assert hasattr(report, "claims_ingested")
    assert hasattr(report, "duplicates_detected")
    assert hasattr(report, "claims_merged")
    assert hasattr(report, "new_claims")
    assert hasattr(report, "skipped_sources")
    assert hasattr(report, "trust_decisions")
    assert hasattr(report, "errors")
    assert hasattr(report, "warnings")
    assert hasattr(report, "timestamp")
    assert isinstance(report.source_ids, list)
    assert isinstance(report.source_reports, list)


def test_limit_respected(tmp_path):
    report = run_cake_pipeline(
        GENERAL_WORLD_CONFIG,
        limit=1,
        dry_run=True,
        pack_output_dir=tmp_path,
    )
    assert report.claims_extracted <= 2  # 1 per enabled source


def test_missing_source_file_returns_failed(tmp_path):
    bad_config = tmp_path / "bad.json"
    bad_config.write_text(json.dumps({
        "version": "1.0.0",
        "description": "bad",
        "sources": [{
            "id": "missing_src",
            "source_type": "local_file",
            "format": "json",
            "path_or_url": str(tmp_path / "nonexistent.json"),
        }],
    }))
    report = run_cake_pipeline(bad_config, dry_run=False, pack_output_dir=tmp_path, allow_partial=True)
    assert report.status in (CAKE_FAILED, "CAKE_PARTIAL")
    assert len(report.errors) > 0


def test_report_serializes_to_dict(tmp_path):
    report = run_cake_pipeline(
        GENERAL_WORLD_CONFIG,
        dry_run=True,
        pack_output_dir=tmp_path,
    )
    d = report.to_dict()
    assert isinstance(d, dict)
    assert "status" in d
    assert "source_ids" in d
    assert "source_reports" in d
    assert "duplicates_detected" in d
    assert "claims_merged" in d
    assert "new_claims" in d
    assert "skipped_sources" in d
    # Must be JSON-serializable
    json.dumps(d)


def test_second_run_marks_unchanged_source(tmp_path):
    first = run_cake_pipeline(
        GENERAL_WORLD_CONFIG,
        dry_run=False,
        incremental_mode=True,
        pack_output_dir=tmp_path,
        snapshot_root=tmp_path / "snapshots",
    )
    second = run_cake_pipeline(
        GENERAL_WORLD_CONFIG,
        dry_run=False,
        incremental_mode=True,
        pack_output_dir=tmp_path,
        snapshot_root=tmp_path / "snapshots",
    )
    assert first.status in (CAKE_COMPLETE, "CAKE_PARTIAL")
    assert second.skipped_sources >= 1
    assert any(item.get("status") == "UNCHANGED" for item in second.source_reports)
