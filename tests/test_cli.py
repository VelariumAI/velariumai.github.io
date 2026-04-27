import os
import json
import subprocess
import sys
from pathlib import Path


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "vcse.cli", *args],
        capture_output=True,
        env=env,
        text=True,
    )


def test_cli_logic_demo_outputs_verified_trace() -> None:
    result = run_cli("demo", "logic")

    assert result.returncode == 0
    assert "status: VERIFIED" in result.stdout
    assert "answer: Socrates is_a Mortal" in result.stdout
    assert "proof_trace:" in result.stdout
    assert "- Socrates is_a Mortal" in result.stdout


def test_cli_arithmetic_demo_outputs_verified() -> None:
    result = run_cli("demo", "arithmetic")

    assert result.returncode == 0
    assert "status: VERIFIED" in result.stdout
    assert "answer: x satisfies constraints" in result.stdout


def test_cli_contradiction_demo_outputs_contradictory_without_answer() -> None:
    result = run_cli("demo", "contradiction")

    assert result.returncode == 0
    assert "status: CONTRADICTORY" in result.stdout
    assert "answer: null" in result.stdout
    assert "x equals both 3 and 4" in result.stdout


def test_cli_run_accepts_json_file(tmp_path: Path) -> None:
    case_file = tmp_path / "case.json"
    case_file.write_text(
        json.dumps(
            {
                "facts": [
                    {"subject": "Socrates", "relation": "is_a", "object": "Man"},
                    {"subject": "Man", "relation": "is_a", "object": "Mortal"},
                ],
                "constraints": [],
                "goal": {
                    "subject": "Socrates",
                    "relation": "is_a",
                    "object": "Mortal",
                },
            }
        )
    )

    result = run_cli("run", str(case_file))

    assert result.returncode == 0
    assert "status: VERIFIED" in result.stdout
    assert "answer: Socrates is_a Mortal" in result.stdout


def test_cli_run_malformed_json_fails_with_structured_error(tmp_path: Path) -> None:
    case_file = tmp_path / "bad.json"
    case_file.write_text("{not json")

    result = run_cli("run", str(case_file))

    assert result.returncode == 2
    assert "status: ERROR" in result.stderr
    assert "error_type: MALFORMED_JSON" in result.stderr
    assert "traceback" not in result.stderr.lower()


def test_cli_benchmark_accepts_jsonl_file(tmp_path: Path) -> None:
    benchmark_file = tmp_path / "cases.jsonl"
    benchmark_file.write_text(
        json.dumps(
            {
                "id": "logic_001",
                "facts": [
                    {"subject": "Socrates", "relation": "is_a", "object": "Man"},
                    {"subject": "Man", "relation": "is_a", "object": "Mortal"},
                ],
                "constraints": [],
                "goal": {
                    "subject": "Socrates",
                    "relation": "is_a",
                    "object": "Mortal",
                },
                "expected_status": "VERIFIED",
            }
        )
        + "\n"
    )

    result = run_cli("benchmark", str(benchmark_file))

    assert result.returncode == 0
    assert "status: BENCHMARK_COMPLETE" in result.stdout
    assert "cases: 1" in result.stdout
    assert "accuracy: 1.0" in result.stdout


def test_cli_does_not_require_gpu_or_external_service() -> None:
    result = run_cli("demo", "logic")

    assert result.returncode == 0
    combined = f"{result.stdout}\n{result.stderr}".lower()
    assert "gpu" not in combined
    assert "service" not in combined


def test_cli_ask_simple_humanizes_is_a_relation_and_strips_modal_subject() -> None:
    result = run_cli(
        "ask",
        "All men are mortal. Socrates is a man. Can Socrates die?",
        "--mode",
        "simple",
    )

    assert result.returncode == 0
    assert "Yes — Socrates is mortal." in result.stdout
    assert "can socrates" not in result.stdout.lower()


def test_cli_ask_explain_and_debug_preserve_proof_trace() -> None:
    explain = run_cli(
        "ask",
        "All men are mortal. Socrates is a man. Can Socrates die?",
        "--mode",
        "explain",
    )
    debug = run_cli(
        "ask",
        "All men are mortal. Socrates is a man. Can Socrates die?",
        "--mode",
        "debug",
    )

    assert explain.returncode == 0
    assert "because" in explain.stdout
    assert "is_a" not in explain.stdout.lower()
    assert "socrates is a man" in explain.stdout.lower()
    assert "man is mortal" in explain.stdout.lower()
    assert "socrates is mortal" in explain.stdout.lower()
    assert "→" in explain.stdout

    assert debug.returncode == 0
    assert "answer: socrates is_a mortal" in debug.stdout.lower()
    assert "answer_human: Socrates is mortal" in debug.stdout
    assert "proof_trace_canonical:" in debug.stdout
    assert "proof_trace_human:" in debug.stdout
    assert "socrates is_a man" in debug.stdout.lower()
    assert "socrates is a man" in debug.stdout.lower()


def test_cli_ask_debug_with_ts3_emits_ts3_stats() -> None:
    debug = run_cli(
        "ask",
        "All men are mortal. Socrates is a man. Can Socrates die?",
        "--mode",
        "debug",
        "--ts3",
    )

    assert debug.returncode == 0
    assert "ts3:" in debug.stdout
    assert "loop_detected:" in debug.stdout
    assert "reachable_by_depth:" in debug.stdout
    assert "absorption_counts:" in debug.stdout
    assert "novelty_score:" in debug.stdout
    assert "contradiction_risk:" in debug.stdout


def test_cli_search_beam_and_mcts_modes_work() -> None:
    beam = run_cli(
        "ask",
        "All men are mortal. Socrates is a man. Can Socrates die?",
        "--search",
        "beam",
    )
    mcts = run_cli(
        "ask",
        "All men are mortal. Socrates is a man. Can Socrates die?",
        "--search",
        "mcts",
    )

    assert beam.returncode == 0
    assert mcts.returncode == 0
    assert "Yes —" in beam.stdout
    assert "Yes —" in mcts.stdout


def test_cli_invalid_search_backend_fails_structured() -> None:
    result = run_cli("ask", "Can Socrates die?", "--search", "invalid")

    assert result.returncode == 2
    assert "status: ERROR" in result.stderr
    assert "error_type: INVALID_SEARCH_BACKEND" in result.stderr
    assert "traceback" not in result.stderr.lower()


def test_cli_search_mcts_with_ts3_debug_works() -> None:
    result = run_cli(
        "ask",
        "All men are mortal. Socrates is a man. Can Socrates die?",
        "--search",
        "mcts",
        "--ts3",
        "--mode",
        "debug",
    )

    assert result.returncode == 0
    assert "search_stats:" in result.stdout
    assert "backend: mcts" in result.stdout
    assert "ts3:" in result.stdout


def test_cli_ingest_auto_and_dry_run(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("All employees are workers.\nEmployees must be background checked.")
    result = run_cli("ingest", str(path), "--auto", "--dry-run")

    assert result.returncode == 0
    assert "status:" in result.stdout
    assert "frames_extracted:" in result.stdout
    assert "dry_run: true" in result.stdout


def test_cli_ingest_unsupported_file_fails_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "sample.md"
    path.write_text("hello")
    result = run_cli("ingest", str(path), "--auto")

    assert result.returncode == 0
    assert "status: UNSUPPORTED_FORMAT" in result.stdout
    assert "traceback" not in result.stdout.lower()


def test_cli_ingest_malformed_json_fails_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json")
    result = run_cli("ingest", str(path), "--auto")

    assert result.returncode == 0
    assert "status: REJECTED" in result.stdout
    assert "MALFORMED_JSON" in result.stdout


def test_cli_ingest_output_memory_and_export_pack(tmp_path: Path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("All employees are workers.")
    memory_out = tmp_path / "memory.json"
    pack_dir = tmp_path / "pack"

    result = run_cli(
        "ingest",
        str(source),
        "--auto",
        "--output-memory",
        str(memory_out),
        "--export-pack",
        str(pack_dir),
    )

    assert result.returncode == 0
    assert memory_out.exists()
    assert (pack_dir / "pack.yaml").exists()
    assert (pack_dir / "claims.jsonl").exists()


def test_cli_dsl_validate_compile_and_list_work() -> None:
    base = Path(__file__).resolve().parents[1] / "examples" / "dsl"
    dsl_path = str(base / "basic_logic.json")

    validate = run_cli("dsl", "validate", dsl_path)
    compile_result = run_cli("dsl", "compile", dsl_path)
    listed = run_cli("dsl", "list")

    assert validate.returncode == 0
    assert "status: VALID" in validate.stdout

    assert compile_result.returncode == 0
    assert "status: COMPILED" in compile_result.stdout
    assert "parser_patterns:" in compile_result.stdout

    assert listed.returncode == 0
    assert "bundles:" in listed.stdout


def test_cli_ask_with_dsl_works() -> None:
    dsl_path = Path(__file__).resolve().parents[1] / "examples" / "dsl" / "basic_logic.json"
    result = run_cli(
        "ask",
        "All men are mortal. Socrates is a man. Can Socrates die?",
        "--dsl",
        str(dsl_path),
        "--mode",
        "simple",
    )

    assert result.returncode == 0
    assert "Yes — Socrates is mortal." in result.stdout


def test_cli_ingest_with_dsl_works(tmp_path: Path) -> None:
    dsl_path = Path(__file__).resolve().parents[1] / "examples" / "dsl" / "simple_policy.json"
    source = tmp_path / "policy.txt"
    source.write_text("Employees requires background checked.")

    result = run_cli(
        "ingest",
        str(source),
        "--dsl",
        str(dsl_path),
        "--auto",
        "--dry-run",
    )

    assert result.returncode == 0
    assert "status:" in result.stdout
    assert "frames_extracted:" in result.stdout


def test_cli_invalid_dsl_fails_cleanly() -> None:
    dsl_path = Path(__file__).resolve().parents[1] / "examples" / "dsl" / "invalid_unknown_type.json"

    result = run_cli(
        "ask",
        "Can Socrates die?",
        "--dsl",
        str(dsl_path),
    )

    assert result.returncode == 2
    assert "status: ERROR" in result.stderr
    assert "error_type: INVALID_DSL" in result.stderr
    assert "traceback" not in result.stderr.lower()


def test_cli_index_build_and_stats_work() -> None:
    dsl_path = Path(__file__).resolve().parents[1] / "examples" / "dsl" / "basic_logic.json"

    built = run_cli("index", "build", "--dsl", str(dsl_path))
    stats = run_cli("index", "stats", "--dsl", str(dsl_path))

    assert built.returncode == 0
    assert "status: INDEX_BUILT" in built.stdout
    assert "artifact_count:" in built.stdout

    assert stats.returncode == 0
    assert "status: INDEX_STATS" in stats.stdout
    assert "token_count:" in stats.stdout


def test_cli_ask_index_debug_emits_selection_stats() -> None:
    dsl_path = Path(__file__).resolve().parents[1] / "examples" / "dsl" / "basic_logic.json"
    result = run_cli(
        "ask",
        "All men are mortal. Socrates is a man. Can Socrates die?",
        "--mode",
        "debug",
        "--dsl",
        str(dsl_path),
        "--index",
        "--top-k",
        "2",
        "--top-k-packs",
        "1",
    )

    assert result.returncode == 0
    assert "index:" in result.stdout
    assert "selected_packs:" in result.stdout
    assert "selected_artifacts_count:" in result.stdout
    assert "top_scores:" in result.stdout
    assert "filtered_out_count:" in result.stdout


def test_cli_benchmark_index_flag_works() -> None:
    dsl_path = Path(__file__).resolve().parents[1] / "examples" / "dsl" / "basic_logic.json"
    benchmark_path = Path(__file__).resolve().parents[1] / "benchmarks" / "mixed_cases.jsonl"
    result = run_cli(
        "benchmark",
        str(benchmark_path),
        "--search",
        "beam",
        "--dsl",
        str(dsl_path),
        "--index",
    )

    assert result.returncode == 0
    assert "status: BENCHMARK_COMPLETE" in result.stdout


def test_cli_invalid_index_config_fails_structured() -> None:
    result = run_cli(
        "ask",
        "Can Socrates die?",
        "--index",
        "--top-k",
        "0",
    )

    assert result.returncode == 2
    assert "status: ERROR" in result.stderr
    assert "error_type: INVALID_INDEX_CONFIG" in result.stderr
