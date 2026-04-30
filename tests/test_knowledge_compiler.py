import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from vcse.compiler import CompilerError, KnowledgeCompiler


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _mapping(relation_override: str | None = None) -> dict:
    relation = relation_override or "has_capital"
    return {
        "domain_id": "geography",
        "source_id": "test_source",
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
    }


def _source() -> list[dict]:
    return [
        {
            "id": "a",
            "country": "France",
            "capital": "Paris",
            "languages": ["French", "French"],
            "region": "Europe",
        },
        {
            "country": "Spain",
            "capital": "Madrid",
            "languages": ["Spanish"],
            "region": "Europe",
        },
        {
            "country": "Nullland",
            "capital": "",
            "languages": [],
            "region": None,
        },
    ]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-m", "vcse.cli", *args], capture_output=True, env=env, text=True)


def test_valid_mapping_compiles_candidate_pack(tmp_path: Path) -> None:
    compiler = KnowledgeCompiler()
    source = tmp_path / "source.json"
    mapping = tmp_path / "mapping.json"
    _write_json(source, _source())
    _write_json(mapping, _mapping())

    report = compiler.compile(
        source_path=source,
        mapping_path=mapping,
        domain_spec_path=Path("domains/geography.yaml"),
        output_pack_id="compiled",
        output_root=tmp_path,
    )

    assert report.status == "COMPILE_PASSED"
    pack = json.loads((tmp_path / "compiled" / "pack.json").read_text())
    assert pack["lifecycle_status"] == "candidate"


def test_malformed_mapping_fails_clearly(tmp_path: Path) -> None:
    compiler = KnowledgeCompiler()
    source = tmp_path / "source.json"
    mapping = tmp_path / "mapping.json"
    _write_json(source, _source())
    mapping.write_text("{bad")

    with pytest.raises(CompilerError, match="malformed mapping JSON"):
        compiler.compile(
            source_path=source,
            mapping_path=mapping,
            domain_spec_path=Path("domains/geography.yaml"),
            output_pack_id="compiled",
            output_root=tmp_path,
        )


def test_unknown_relation_fails(tmp_path: Path) -> None:
    compiler = KnowledgeCompiler()
    source = tmp_path / "source.json"
    mapping = tmp_path / "mapping.json"
    _write_json(source, _source())
    _write_json(mapping, _mapping(relation_override="not_a_relation"))

    with pytest.raises(CompilerError, match="unknown relation"):
        compiler.compile(
            source_path=source,
            mapping_path=mapping,
            domain_spec_path=Path("domains/geography.yaml"),
            output_pack_id="compiled",
            output_root=tmp_path,
        )


def test_list_values_generate_multiple_claims(tmp_path: Path) -> None:
    compiler = KnowledgeCompiler()
    source = tmp_path / "source.json"
    mapping = tmp_path / "mapping.json"
    _write_json(source, _source())
    _write_json(mapping, _mapping())

    compiler.compile(source, mapping, Path("domains/geography.yaml"), "compiled", tmp_path)
    claims = _read_jsonl(tmp_path / "compiled" / "claims.jsonl")

    french_language_claims = [c for c in claims if c["subject"] == "France" and c["relation"] == "language_of"]
    assert len(french_language_claims) == 1
    assert french_language_claims[0]["object"] == "French"


def test_null_empty_values_skipped(tmp_path: Path) -> None:
    compiler = KnowledgeCompiler()
    source = tmp_path / "source.json"
    mapping = tmp_path / "mapping.json"
    _write_json(source, _source())
    _write_json(mapping, _mapping())

    compiler.compile(source, mapping, Path("domains/geography.yaml"), "compiled", tmp_path)
    claims = _read_jsonl(tmp_path / "compiled" / "claims.jsonl")
    assert all(c["subject"] != "Nullland" for c in claims)


def test_duplicate_claims_deduped(tmp_path: Path) -> None:
    compiler = KnowledgeCompiler()
    source = tmp_path / "source.json"
    mapping = tmp_path / "mapping.json"
    rows = _source()
    rows.append({"country": "France", "capital": "Paris", "languages": ["French"], "region": "Europe"})
    _write_json(source, rows)
    _write_json(mapping, _mapping())

    report = compiler.compile(source, mapping, Path("domains/geography.yaml"), "compiled", tmp_path)
    claims = _read_jsonl(tmp_path / "compiled" / "claims.jsonl")
    keys = {c["claim_key"] for c in claims}
    assert len(claims) == len(keys)
    assert report.duplicate_count > 0


def test_every_claim_has_provenance(tmp_path: Path) -> None:
    compiler = KnowledgeCompiler()
    source = tmp_path / "source.json"
    mapping = tmp_path / "mapping.json"
    _write_json(source, _source())
    _write_json(mapping, _mapping())

    compiler.compile(source, mapping, Path("domains/geography.yaml"), "compiled", tmp_path)
    claims = _read_jsonl(tmp_path / "compiled" / "claims.jsonl")
    provenance = _read_jsonl(tmp_path / "compiled" / "provenance.jsonl")
    assert len(claims) == len(provenance)
    assert all(isinstance(c.get("provenance"), dict) for c in claims)


def test_benchmark_generation_works(tmp_path: Path) -> None:
    compiler = KnowledgeCompiler()
    source = tmp_path / "source.json"
    mapping = tmp_path / "mapping.json"
    benchmarks = tmp_path / "benchmarks.jsonl"
    _write_json(source, _source())
    _write_json(mapping, _mapping())

    report = compiler.compile(source, mapping, Path("domains/geography.yaml"), "compiled", tmp_path, benchmark_output=benchmarks)
    rows = _read_jsonl(benchmarks)
    assert report.benchmark_count == len(rows)
    assert all("source_claim_key" in row for row in rows)


def test_output_deterministic_across_two_runs(tmp_path: Path) -> None:
    compiler = KnowledgeCompiler()
    source = tmp_path / "source.json"
    mapping = tmp_path / "mapping.json"
    _write_json(source, _source())
    _write_json(mapping, _mapping())

    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"
    compiler.compile(source, mapping, Path("domains/geography.yaml"), "compiled", out_a)
    compiler.compile(source, mapping, Path("domains/geography.yaml"), "compiled", out_b)

    for name in ["claims.jsonl", "provenance.jsonl", "metrics.json", "trust_report.json", "pack.json"]:
        assert (out_a / "compiled" / name).read_text() == (out_b / "compiled" / name).read_text()


def test_existing_packs_are_not_mutated(tmp_path: Path) -> None:
    claims_path = Path("examples/packs/general_world/claims.jsonl")
    before = claims_path.read_bytes()

    compiler = KnowledgeCompiler()
    source = tmp_path / "source.json"
    mapping = tmp_path / "mapping.json"
    _write_json(source, _source())
    _write_json(mapping, _mapping())
    compiler.compile(source, mapping, Path("domains/geography.yaml"), "compiled", tmp_path)

    after = claims_path.read_bytes()
    assert before == after


def test_cli_compile_works(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    mapping = tmp_path / "mapping.json"
    benchmarks = tmp_path / "benchmarks.jsonl"
    _write_json(source, _source())
    _write_json(mapping, _mapping())

    result = run_cli(
        "compile",
        "knowledge",
        "--source",
        str(source),
        "--mapping",
        str(mapping),
        "--domain",
        "domains/geography.yaml",
        "--pack-id",
        "compiled",
        "--output-root",
        str(tmp_path),
        "--benchmark-output",
        str(benchmarks),
        "--json",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "COMPILE_PASSED"


def test_cli_validate_mapping_works(tmp_path: Path) -> None:
    mapping = tmp_path / "mapping.json"
    _write_json(mapping, _mapping())

    result = run_cli(
        "compiler",
        "validate-mapping",
        "--mapping",
        str(mapping),
        "--domain",
        "domains/geography.yaml",
        "--json",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "COMPILE_PASSED"
