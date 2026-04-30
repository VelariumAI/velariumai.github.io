from pathlib import Path

from vcse.benchmark import run_benchmark
from vcse.dsl import DSLCompiler, DSLLoader
from vcse.engine import filter_bundle_for_query
from vcse.index import SymbolicRetriever
from vcse.index.features import extract_bundle_features
from vcse.index.retrieval import RetrievalConfig
from vcse.interaction.session import Session


def _example_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "dsl" / name


def _bundle(name: str):
    return DSLCompiler.compile(DSLLoader.load(_example_path(name)))


def test_index_build_populates_inverted_index_and_features() -> None:
    bundle = _bundle("basic_logic.json")
    features = extract_bundle_features(bundle)
    retriever = SymbolicRetriever.from_bundles([bundle])

    assert features
    assert retriever.index.artifact_count >= 5
    assert retriever.index.token_count > 0
    assert "is_a" in retriever.index.inverted_index


def test_retrieval_returns_relevant_rules_and_respects_top_k() -> None:
    bundle = _bundle("mortality.json")
    retriever = SymbolicRetriever.from_bundles([bundle])

    retrieval = retriever.retrieve("Can Socrates perish?", config=None)
    assert retrieval.selected_artifact_ids
    assert "syn_die" in retrieval.selected_artifact_ids

    limited = retriever.retrieve(
        "Can Socrates perish?",
        config=RetrievalConfig(top_k_rules=1, top_k_packs=1),
    )
    assert len(limited.selected_artifact_ids) <= 1


def test_pack_selection_prefers_relevant_pack() -> None:
    logic = _bundle("basic_logic.json")
    mortality = _bundle("mortality.json")
    retriever = SymbolicRetriever.from_bundles([logic, mortality])

    retrieval = retriever.retrieve("Can Socrates perish?")

    assert retrieval.selected_pack_ids
    assert retrieval.selected_pack_ids[0] == "mortality"


def test_indexing_on_preserves_correctness_and_reduces_candidates() -> None:
    bundle = _bundle("basic_logic.json")

    baseline = Session.create(dsl_bundle=bundle)
    baseline.ingest("All men are mortal. Socrates is a man. Can Socrates die?")
    baseline_result = baseline.solve()

    indexed = Session.create(dsl_bundle=bundle, enable_indexing=True, top_k_rules=2, top_k_packs=1)
    indexed.ingest("All men are mortal. Socrates is a man. Can Socrates die?")
    indexed_result = indexed.solve()

    assert baseline_result is not None and indexed_result is not None
    assert baseline_result.evaluation.status == indexed_result.evaluation.status
    assert indexed_result.retrieval_stats is not None
    assert indexed_result.retrieval_stats["selected_artifacts_count"] <= 2
    assert indexed_result.retrieval_stats["filtered_out_count"] >= 0


def test_filter_bundle_falls_back_when_no_candidates() -> None:
    bundle = _bundle("basic_logic.json")
    filtered, stats = filter_bundle_for_query(bundle, "qwerty zyx")

    assert filtered is bundle
    assert stats is not None
    assert stats["selected_artifacts_count"] == 0


def test_benchmark_index_mode_matches_non_index_mode() -> None:
    bundle = _bundle("basic_logic.json")
    path = Path(__file__).resolve().parents[1] / "benchmarks" / "mixed_cases.jsonl"

    off = run_benchmark(path, search_backend="beam", dsl_bundle=bundle)
    on = run_benchmark(path, search_backend="beam", dsl_bundle=bundle, enable_index=True)

    assert off["cases_passed"] == on["cases_passed"]
