from __future__ import annotations

import json
from pathlib import Path

from vcse.packs.runtime_store import (
    RuntimeStoreCompiler,
    load_runtime_claims_if_valid,
    runtime_store_path_for_pack,
)


def _write_pack(root: Path, pack_id: str = "sample_pack") -> Path:
    pack_dir = root / "examples" / "packs" / pack_id
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "pack.json").write_text(
        json.dumps(
            {
                "id": pack_id,
                "pack_id": pack_id,
                "version": "1.0.0",
                "lifecycle_status": "candidate",
                "claim_count": 1,
                "provenance_count": 1,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    claim = {"subject": "France", "relation": "has_capital", "object": "Paris", "trust_tier": "T0_CANDIDATE"}
    (pack_dir / "claims.jsonl").write_text(json.dumps(claim, sort_keys=True) + "\n")
    prov = {"source_id": "s1", "evidence_text": "France has_capital Paris"}
    (pack_dir / "provenance.jsonl").write_text(json.dumps(prov, sort_keys=True) + "\n")
    return pack_dir


def test_incremental_initial_compile_creates_store(tmp_path: Path) -> None:
    pack_dir = _write_pack(tmp_path)
    output = tmp_path / runtime_store_path_for_pack("sample_pack")
    report = RuntimeStoreCompiler().compile_incremental(pack_dir, output)
    assert report.status == "REBUILT"
    assert output.exists()


def test_incremental_second_compile_no_changes(tmp_path: Path) -> None:
    pack_dir = _write_pack(tmp_path)
    output = tmp_path / runtime_store_path_for_pack("sample_pack")
    compiler = RuntimeStoreCompiler()
    first = compiler.compile_incremental(pack_dir, output)
    before_mtime = output.stat().st_mtime_ns
    second = compiler.compile_incremental(pack_dir, output)
    after_mtime = output.stat().st_mtime_ns
    assert first.status == "REBUILT"
    assert second.status == "NO_CHANGES"
    assert before_mtime == after_mtime


def test_incremental_claim_change_forces_rebuild(tmp_path: Path) -> None:
    pack_dir = _write_pack(tmp_path)
    output = tmp_path / runtime_store_path_for_pack("sample_pack")
    compiler = RuntimeStoreCompiler()
    compiler.compile_incremental(pack_dir, output)
    (pack_dir / "claims.jsonl").write_text(
        json.dumps({"subject": "France", "relation": "has_capital", "object": "Lyon"}, sort_keys=True) + "\n"
    )
    report = compiler.compile_incremental(pack_dir, output)
    assert report.status == "REBUILT"


def test_incremental_provenance_change_forces_rebuild(tmp_path: Path) -> None:
    pack_dir = _write_pack(tmp_path)
    output = tmp_path / runtime_store_path_for_pack("sample_pack")
    compiler = RuntimeStoreCompiler()
    compiler.compile_incremental(pack_dir, output)
    (pack_dir / "provenance.jsonl").write_text(
        json.dumps({"source_id": "s1", "evidence_text": "France has_capital Lyon"}, sort_keys=True) + "\n"
    )
    report = compiler.compile_incremental(pack_dir, output)
    assert report.status == "REBUILT"


def test_runtime_load_detects_stale_store(tmp_path: Path) -> None:
    pack_dir = _write_pack(tmp_path)
    output = tmp_path / runtime_store_path_for_pack("sample_pack")
    compiler = RuntimeStoreCompiler()
    compiler.compile_incremental(pack_dir, output)
    (pack_dir / "claims.jsonl").write_text(
        json.dumps({"subject": "France", "relation": "has_capital", "object": "Lyon"}, sort_keys=True) + "\n"
    )
    assert load_runtime_claims_if_valid(pack_dir, "sample_pack") is None


def test_incremental_metrics_present(tmp_path: Path) -> None:
    pack_dir = _write_pack(tmp_path)
    output = tmp_path / runtime_store_path_for_pack("sample_pack")
    report = RuntimeStoreCompiler().compile_incremental(pack_dir, output)
    assert report.compile_time_ms >= 0.0
    assert report.load_time_ms >= 0.0
    assert report.avg_query_latency_ms >= 0.0
    assert report.backend == "sqlite"
