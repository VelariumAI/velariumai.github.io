from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from vcse.interaction.query_normalizer import normalize_query
from vcse.packs.runtime_store import RuntimeStore, RuntimeStoreCompiler, runtime_store_path_for_pack
from vcse.packs.sharding import assign_shard
from vcse.query.executor import QueryExecutor
from vcse.query.planner import QueryPlanner


def run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-m", "vcse.cli", *args], capture_output=True, text=True, env=env, cwd=cwd)


def _write_pack(root: Path, pack_id: str = "sample_pack") -> Path:
    pack_dir = root / "examples" / "packs" / pack_id
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "pack.json").write_text(json.dumps({"id": pack_id, "pack_id": pack_id, "version": "1.0.0"}) + "\n")
    claims = [
        {"subject": "France", "relation": "has_capital", "object": "Paris"},
        {"subject": "France", "relation": "uses_currency", "object": "Euro"},
    ]
    (pack_dir / "claims.jsonl").write_text("\n".join(json.dumps(row, sort_keys=True) for row in claims) + "\n")
    (pack_dir / "provenance.jsonl").write_text(
        "\n".join(json.dumps({"source_id": f"s{i+1}", "evidence_text": "e"}, sort_keys=True) for i in range(len(claims))) + "\n"
    )
    return pack_dir


def test_shard_assignment_deterministic() -> None:
    claim = {"subject": "France", "relation": "has_capital", "object": "Paris"}
    assert assign_shard(claim) == "geography.capitals"
    assert assign_shard(claim) == "geography.capitals"


def test_planner_routes_supported_and_fallbacks_unsupported() -> None:
    planner = QueryPlanner()
    assert planner.plan(normalize_query("What is the capital of France?")) is not None
    assert planner.plan(normalize_query("Is France a country?")) is None


def test_executor_resolves_explicit_via_shard(tmp_path: Path) -> None:
    pack_dir = _write_pack(tmp_path)
    db = tmp_path / runtime_store_path_for_pack("sample_pack")
    RuntimeStoreCompiler().compile_pack(pack_dir, db)
    store = RuntimeStore(db)
    try:
        plan = QueryPlanner().plan(normalize_query("What is the currency of France?"))
        result = QueryExecutor().execute(plan, store)
    finally:
        store.close()
    assert result.answer_claim is not None
    assert result.answer_claim["object"] == "Euro"
    assert result.fallback_used is False
    assert result.rows_examined >= 1


def test_planned_ask_parity_and_fallback(tmp_path: Path) -> None:
    compile_result = run_cli("pack", "compile", "general_world", "--force", cwd=Path(__file__).resolve().parents[1])
    assert compile_result.returncode == 0
    normal = run_cli("ask", "What is the capital of France?", "--pack", "general_world", cwd=Path(__file__).resolve().parents[1])
    planned = run_cli(
        "ask",
        "What is the capital of France?",
        "--pack",
        "general_world",
        "--planned",
        cwd=Path(__file__).resolve().parents[1],
    )
    assert normal.returncode == 0
    assert planned.returncode == 0
    assert normal.stdout.strip() == planned.stdout.strip()

    unsupported = run_cli("ask", "Tell me about France", "--pack", "general_world", "--planned", cwd=Path(__file__).resolve().parents[1])
    baseline = run_cli("ask", "Tell me about France", "--pack", "general_world", cwd=Path(__file__).resolve().parents[1])
    assert unsupported.returncode == 0
    assert unsupported.stdout.strip() == baseline.stdout.strip()

