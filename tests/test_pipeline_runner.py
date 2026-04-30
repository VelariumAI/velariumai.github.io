from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from vcse.pipeline.runner import PackPipelineRunner, PipelineError


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_yaml(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-m", "vcse.cli", *args], capture_output=True, text=True, env=env)


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mk_config(base_name: str, *, mapping_path: str, source_path: str, pack_id: str, output_root: str, benchmark_path: str) -> Path:
    config_path = REPO_ROOT / ".vcse" / "test_pipeline_configs" / f"{base_name}.yaml"
    _write_yaml(
        config_path,
        "\n".join(
            [
                f"pipeline_id: {base_name}",
                "domain: domains/geography.yaml",
                "adapter:",
                "  type: json",
                f"  source: {source_path}",
                "compiler:",
                f"  mapping: {mapping_path}",
                f"  pack_id: {pack_id}",
                f"  output_root: {output_root}",
                f"  benchmark_output: {benchmark_path}",
                "validation:",
                "  validate_pack: true",
                "  review_pack: true",
                "runtime_store:",
                "  compile: false",
                "",
            ]
        ),
    )
    return config_path


def _make_source(name: str) -> Path:
    path = REPO_ROOT / ".vcse" / "test_pipeline_sources" / f"{name}.json"
    _write_json(
        path,
        [
            {"id": "r1", "country": "France", "capital": "Paris", "languages": ["French"], "region": "Europe"},
            {"id": "r2", "country": "Spain", "capital": "Madrid", "languages": ["Spanish"], "region": "Europe"},
        ],
    )
    return path


def _make_mapping(name: str, *, relation: str = "has_capital") -> Path:
    path = REPO_ROOT / ".vcse" / "test_pipeline_mappings" / f"{name}.json"
    _write_json(
        path,
        {
            "domain_id": "geography",
            "source_id": "test_pipeline_source",
            "entity_field": "country",
            "fields": {
                "capital": "capital",
                "languages": "languages",
                "region": "region",
            },
            "relation_map": {
                "capital": relation,
                "languages": "language_of",
                "region": "located_in_region",
            },
        },
    )
    return path


def test_valid_pipeline_runs_end_to_end() -> None:
    suffix = uuid.uuid4().hex[:8]
    source = _make_source(f"ok_{suffix}")
    mapping = _make_mapping(f"ok_{suffix}")
    pack_id = f"compiled_pipeline_test_{suffix}"
    output_root = "examples/packs"
    benchmark_path = f"benchmarks/compiled_pipeline_test_{suffix}.jsonl"
    config = _mk_config(f"pipeline_ok_{suffix}", mapping_path=str(mapping.relative_to(REPO_ROOT)), source_path=str(source.relative_to(REPO_ROOT)), pack_id=pack_id, output_root=output_root, benchmark_path=benchmark_path)

    report = PackPipelineRunner(run_id=f"run_ok_{suffix}").run(config)

    assert report.status == "PIPELINE_PASSED"
    assert report.pack_id == pack_id


def test_malformed_config_fails_clearly() -> None:
    cfg = REPO_ROOT / ".vcse" / "test_pipeline_configs" / "malformed.yaml"
    _write_yaml(cfg, "pipeline_id: bad\nadapter: [1,2]\n")
    with pytest.raises(PipelineError, match="missing required fields"):
        PackPipelineRunner(run_id="run_bad_config").run(cfg)


def test_missing_adapter_source_fails() -> None:
    suffix = uuid.uuid4().hex[:8]
    mapping = _make_mapping(f"missing_src_{suffix}")
    cfg = _mk_config(
        f"pipeline_missing_source_{suffix}",
        mapping_path=str(mapping.relative_to(REPO_ROOT)),
        source_path=".vcse/test_pipeline_sources/does_not_exist.json",
        pack_id=f"compiled_missing_source_{suffix}",
        output_root="examples/packs",
        benchmark_path=f"benchmarks/compiled_missing_source_{suffix}.jsonl",
    )
    with pytest.raises(PipelineError, match="adapter source not found"):
        PackPipelineRunner(run_id=f"run_missing_source_{suffix}").run(cfg)


def test_compiler_failure_propagates() -> None:
    suffix = uuid.uuid4().hex[:8]
    source = _make_source(f"bad_map_{suffix}")
    mapping = _make_mapping(f"bad_map_{suffix}", relation="not_a_relation")
    cfg = _mk_config(
        f"pipeline_bad_compiler_{suffix}",
        mapping_path=str(mapping.relative_to(REPO_ROOT)),
        source_path=str(source.relative_to(REPO_ROOT)),
        pack_id=f"compiled_bad_compiler_{suffix}",
        output_root="examples/packs",
        benchmark_path=f"benchmarks/compiled_bad_compiler_{suffix}.jsonl",
    )

    report = PackPipelineRunner(run_id=f"run_bad_compiler_{suffix}").run(cfg)
    assert report.status == "PIPELINE_FAILED"
    assert any("compiler failed" in item for item in report.reasons)


def test_validation_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    suffix = uuid.uuid4().hex[:8]
    source = _make_source(f"bad_validate_{suffix}")
    mapping = _make_mapping(f"bad_validate_{suffix}")
    cfg = _mk_config(
        f"pipeline_bad_validation_{suffix}",
        mapping_path=str(mapping.relative_to(REPO_ROOT)),
        source_path=str(source.relative_to(REPO_ROOT)),
        pack_id=f"compiled_bad_validation_{suffix}",
        output_root="examples/packs",
        benchmark_path=f"benchmarks/compiled_bad_validation_{suffix}.jsonl",
    )

    def _fake_validate(self, pack_path: Path) -> dict[str, object]:
        return {"status": "INVALID", "passed": False, "errors": ["forced validation failure"]}

    monkeypatch.setattr("vcse.pipeline.runner.PackPipelineRunner._validate_pack", _fake_validate)
    report = PackPipelineRunner(run_id=f"run_bad_validation_{suffix}").run(cfg)
    assert report.status == "PIPELINE_FAILED"
    assert "validation failed" in report.reasons


def test_pipeline_output_directory_contains_all_reports() -> None:
    suffix = uuid.uuid4().hex[:8]
    source = _make_source(f"reports_{suffix}")
    mapping = _make_mapping(f"reports_{suffix}")
    pack_id = f"compiled_reports_{suffix}"
    cfg = _mk_config(
        f"pipeline_reports_{suffix}",
        mapping_path=str(mapping.relative_to(REPO_ROOT)),
        source_path=str(source.relative_to(REPO_ROOT)),
        pack_id=pack_id,
        output_root="examples/packs",
        benchmark_path=f"benchmarks/compiled_reports_{suffix}.jsonl",
    )
    run_id = f"run_reports_{suffix}"
    report = PackPipelineRunner(run_id=run_id).run(cfg)
    out = Path(report.output_dir)
    assert (out / "normalized.jsonl").exists()
    assert (out / "compile_report.json").exists()
    assert (out / "validation_report.json").exists()
    assert (out / "review_report.json").exists()
    assert (out / "benchmark_report.json").exists()
    assert (out / "pipeline_report.json").exists()


def test_pipeline_run_deterministic_with_fixed_run_id() -> None:
    suffix = uuid.uuid4().hex[:8]
    source = _make_source(f"det_{suffix}")
    mapping = _make_mapping(f"det_{suffix}")
    pack_id = f"compiled_det_{suffix}"
    benchmark_rel = f"benchmarks/compiled_det_{suffix}.jsonl"
    cfg = _mk_config(
        f"pipeline_det_{suffix}",
        mapping_path=str(mapping.relative_to(REPO_ROOT)),
        source_path=str(source.relative_to(REPO_ROOT)),
        pack_id=pack_id,
        output_root="examples/packs",
        benchmark_path=benchmark_rel,
    )
    run_id = f"run_det_{suffix}"

    runner = PackPipelineRunner(run_id=run_id)
    first = runner.run(cfg).to_dict()

    shutil.rmtree(REPO_ROOT / ".vcse" / "pipeline_runs" / run_id)
    shutil.rmtree(REPO_ROOT / "examples" / "packs" / pack_id)
    bench = REPO_ROOT / benchmark_rel
    if bench.exists():
        bench.unlink()

    second = runner.run(cfg).to_dict()
    assert first == second


def test_pipeline_does_not_mutate_existing_packs() -> None:
    suffix = uuid.uuid4().hex[:8]
    before = _hash_file(REPO_ROOT / "examples" / "packs" / "general_world" / "claims.jsonl")
    source = _make_source(f"nomut_{suffix}")
    mapping = _make_mapping(f"nomut_{suffix}")
    cfg = _mk_config(
        f"pipeline_nomut_{suffix}",
        mapping_path=str(mapping.relative_to(REPO_ROOT)),
        source_path=str(source.relative_to(REPO_ROOT)),
        pack_id=f"compiled_nomut_{suffix}",
        output_root="examples/packs",
        benchmark_path=f"benchmarks/compiled_nomut_{suffix}.jsonl",
    )
    report = PackPipelineRunner(run_id=f"run_nomut_{suffix}").run(cfg)
    assert report.status == "PIPELINE_PASSED"
    after = _hash_file(REPO_ROOT / "examples" / "packs" / "general_world" / "claims.jsonl")
    assert before == after


def test_cli_pipeline_run_works() -> None:
    suffix = uuid.uuid4().hex[:8]
    source = _make_source(f"cli_{suffix}")
    mapping = _make_mapping(f"cli_{suffix}")
    pack_id = f"compiled_cli_{suffix}"
    cfg = _mk_config(
        f"pipeline_cli_{suffix}",
        mapping_path=str(mapping.relative_to(REPO_ROOT)),
        source_path=str(source.relative_to(REPO_ROOT)),
        pack_id=pack_id,
        output_root="examples/packs",
        benchmark_path=f"benchmarks/compiled_cli_{suffix}.jsonl",
    )
    run_id = f"run_cli_{suffix}"
    result = _run_cli("pipeline", "run", str(cfg), "--run-id", run_id, "--json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "PIPELINE_PASSED"


def test_cli_pipeline_inspect_works() -> None:
    suffix = uuid.uuid4().hex[:8]
    source = _make_source(f"inspect_{suffix}")
    mapping = _make_mapping(f"inspect_{suffix}")
    pack_id = f"compiled_inspect_{suffix}"
    cfg = _mk_config(
        f"pipeline_inspect_{suffix}",
        mapping_path=str(mapping.relative_to(REPO_ROOT)),
        source_path=str(source.relative_to(REPO_ROOT)),
        pack_id=pack_id,
        output_root="examples/packs",
        benchmark_path=f"benchmarks/compiled_inspect_{suffix}.jsonl",
    )
    run_id = f"run_inspect_{suffix}"
    run_result = _run_cli("pipeline", "run", str(cfg), "--run-id", run_id, "--json")
    assert run_result.returncode == 0

    inspect_result = _run_cli("pipeline", "inspect", run_id, "--json")
    assert inspect_result.returncode == 0
    payload = json.loads(inspect_result.stdout)
    assert payload["run_id"] == run_id
    assert payload["status"] == "PIPELINE_PASSED"
