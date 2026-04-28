import json
import os
import subprocess
import sys
from pathlib import Path

from vcse.benchmark_inference_classification import InferenceType
from vcse.benchmark_coverage import run_coverage_benchmark
from vcse.cli import run_ask


def run_cli(*args: str, pack_home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    env["VCSE_PACK_HOME"] = str(pack_home)
    return subprocess.run(
        [sys.executable, "-m", "vcse.cli", *args],
        capture_output=True,
        env=env,
        text=True,
    )


def test_benchmark_coverage_text_and_json(tmp_path: Path) -> None:
    home = tmp_path / "vcse_home"
    repo_root = Path(__file__).resolve().parents[1]

    indexed = run_cli("pack", "index", "--dirs", str(repo_root / "examples" / "packs"), pack_home=home)
    assert indexed.returncode == 0

    text = run_cli("benchmark", "coverage", "--pack", "general_world", pack_home=home)
    assert text.returncode == 0
    assert "status: COVERAGE_COMPLETE" in text.stdout
    assert "coverage_rate:" in text.stdout
    assert "candidate_rate:" in text.stdout

    raw = run_cli("benchmark", "coverage", "--pack", "general_world", "--json", pack_home=home)
    assert raw.returncode == 0
    payload = json.loads(raw.stdout)
    assert payload["status"] == "COVERAGE_COMPLETE"
    assert payload["total"] >= 1500
    assert payload["incorrect"] == 0
    assert "explicit_answer_count" in payload
    assert "inverse_inferred_count" in payload
    assert "transitive_inferred_count" in payload
    assert "unknown_count" in payload
    assert "unsupported_query_count" in payload
    assert "total_queries" in payload
    assert "false_verified_count" in payload
    assert "compression_ratio" in payload
    assert "compressed_size" in payload
    assert "uncompressed_size" in payload
    assert "load_time_ms" in payload
    assert "query_latency_ms" in payload
    assert payload["inverse_inferred_count"] > 0
    assert payload["transitive_inferred_count"] > 0


def test_benchmark_coverage_missing_pack_reports_pack_not_found(tmp_path: Path) -> None:
    home = tmp_path / "vcse_home"
    result = run_cli("benchmark", "coverage", "--pack", "does.not.exist", pack_home=home)
    assert result.returncode == 2
    assert "error_type: PACK_NOT_FOUND" in result.stderr


def test_general_knowledge_benchmark_ids_are_unique() -> None:
    benchmark_path = Path(__file__).resolve().parents[1] / "benchmarks" / "general_knowledge.jsonl"
    ids: list[str] = []
    for line in benchmark_path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        ids.append(row["id"])
    assert len(ids) >= 500
    assert len(ids) == len(set(ids))


def test_coverage_classification_counts_and_totals(tmp_path: Path) -> None:
    pack_path = tmp_path / "pack"
    pack_path.mkdir(parents=True)
    claims = [
        {
            "subject": "France",
            "relation": "has_capital",
            "object": "Paris",
            "provenance": {
                "source_id": "s",
                "source_type": "test",
                "location": "unit",
                "evidence_text": "e",
            },
            "trust_tier": "T3_CANDIDATE",
        },
        {
            "subject": "Paris",
            "relation": "located_in_country",
            "object": "France",
            "provenance": {
                "source_id": "s",
                "source_type": "test",
                "location": "unit",
                "evidence_text": "e",
            },
            "trust_tier": "T3_CANDIDATE",
        },
        {
            "subject": "France",
            "relation": "part_of",
            "object": "Europe",
            "provenance": {
                "source_id": "s",
                "source_type": "test",
                "location": "unit",
                "evidence_text": "e",
            },
            "trust_tier": "T3_CANDIDATE",
        },
    ]
    (pack_path / "claims.jsonl").write_text("\n".join(json.dumps(row) for row in claims) + "\n")

    benchmark_path = tmp_path / "bench.jsonl"
    cases = [
        {"id": "explicit", "subject": "France", "relation": "has_capital", "object": "Paris", "expected": "candidate"},
        {"id": "inverse", "subject": "Paris", "relation": "capital_of", "object": "France", "expected": "candidate"},
        {"id": "transitive", "subject": "Paris", "relation": "located_in_region", "object": "Europe", "expected": "candidate"},
    ]
    benchmark_path.write_text("\n".join(json.dumps(row) for row in cases) + "\n")

    summary = run_coverage_benchmark(pack_path=pack_path, benchmark_path=benchmark_path)
    assert summary["explicit_answer_count"] == 1
    assert summary["inverse_inferred_count"] == 1
    assert summary["transitive_inferred_count"] == 1
    assert summary["unknown_count"] == 0
    assert summary["unsupported_query_count"] == 0
    assert summary["total_queries"] == 3
    assert (
        summary["explicit_answer_count"]
        + summary["inverse_inferred_count"]
        + summary["transitive_inferred_count"]
        + summary["unknown_count"]
        + summary["unsupported_query_count"]
    ) == summary["total_queries"]


def test_coverage_classification_deterministic(tmp_path: Path) -> None:
    pack_path = tmp_path / "pack"
    pack_path.mkdir(parents=True)
    claim = {
        "subject": "France",
        "relation": "has_capital",
        "object": "Paris",
        "provenance": {
            "source_id": "s",
            "source_type": "test",
            "location": "unit",
            "evidence_text": "e",
        },
        "trust_tier": "T3_CANDIDATE",
    }
    (pack_path / "claims.jsonl").write_text(json.dumps(claim) + "\n")
    benchmark_path = tmp_path / "bench.jsonl"
    benchmark_case = {
        "id": "inverse",
        "subject": "Paris",
        "relation": "capital_of",
        "object": "France",
        "expected": "candidate",
    }
    benchmark_path.write_text(json.dumps(benchmark_case) + "\n")

    first = run_coverage_benchmark(pack_path=pack_path, benchmark_path=benchmark_path)
    second = run_coverage_benchmark(pack_path=pack_path, benchmark_path=benchmark_path)
    assert first["explicit_answer_count"] == second["explicit_answer_count"]
    assert first["inverse_inferred_count"] == second["inverse_inferred_count"]
    assert first["transitive_inferred_count"] == second["transitive_inferred_count"]
    assert first["unknown_count"] == second["unknown_count"]
    assert first["unsupported_query_count"] == second["unsupported_query_count"]


def test_coverage_rate_unchanged_for_general_world(tmp_path: Path) -> None:
    home = tmp_path / "vcse_home"
    repo_root = Path(__file__).resolve().parents[1]
    indexed = run_cli("pack", "index", "--dirs", str(repo_root / "examples" / "packs"), pack_home=home)
    assert indexed.returncode == 0

    raw = run_cli("benchmark", "coverage", "--pack", "general_world", "--json", pack_home=home)
    assert raw.returncode == 0
    payload = json.loads(raw.stdout)
    assert payload["coverage_rate"] == 1.0


def test_run_ask_resolution_type_classification() -> None:
    claims = [
        {"subject": "France", "relation": "has_capital", "object": "Paris"},
        {"subject": "Paris", "relation": "located_in_country", "object": "France"},
        {"subject": "France", "relation": "part_of", "object": "Europe"},
    ]
    explicit = run_ask(
        "What is the capital of France?",
        preload_claims=claims,
        return_resolution_type=True,
    )
    inverse = run_ask(
        "What is Paris the capital of?",
        preload_claims=claims,
        return_resolution_type=True,
    )
    transitive = run_ask(
        "What continent is Paris in?",
        preload_claims=claims,
        return_resolution_type=True,
    )
    assert isinstance(explicit, tuple)
    assert isinstance(inverse, tuple)
    assert isinstance(transitive, tuple)
    assert explicit[1] == InferenceType.UNKNOWN
    assert inverse[1] == InferenceType.INVERSE
    assert transitive[1] == InferenceType.TRANSITIVE
