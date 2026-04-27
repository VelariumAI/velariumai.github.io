from pathlib import Path

from vcse.ingestion.import_result import CONTRADICTORY, IMPORTED, UNSUPPORTED_FORMAT
from vcse.ingestion.pipeline import ingest_file
from vcse.memory.world_state import WorldStateMemory


def test_dry_run_does_not_mutate_memory(tmp_path: Path) -> None:
    path = tmp_path / "policy.txt"
    path.write_text("All employees are workers.")
    memory = WorldStateMemory()
    before = memory.to_dict()

    result = ingest_file(path=path, auto=True, dry_run=True, memory=memory)

    assert result.import_result.status in {IMPORTED, CONTRADICTORY}
    assert memory.to_dict() == before


def test_accepted_import_creates_elements_and_provenance(tmp_path: Path) -> None:
    path = tmp_path / "policy.txt"
    path.write_text("All employees are workers.\nEmployees must be background checked.")
    result = ingest_file(path=path, auto=True, dry_run=False)

    assert result.import_result.status in {IMPORTED, CONTRADICTORY}
    assert result.import_result.created_elements >= 1
    assert any(result.memory.evidence.values())


def test_contradiction_import_returns_contradictory(tmp_path: Path) -> None:
    path = tmp_path / "contradiction.txt"
    path.write_text("x equals 3.\nx equals 4.")
    result = ingest_file(path=path, auto=True, dry_run=True)

    assert result.import_result.status == CONTRADICTORY
    assert result.import_result.contradictions_detected


def test_unknown_relation_warns(tmp_path: Path) -> None:
    path = tmp_path / "claims.json"
    path.write_text('{"subject":"a","relation":"unknown_rel","object":"b"}')
    result = ingest_file(path=path, auto=True, dry_run=True)

    assert any("Unknown relation schema" in warning for warning in result.import_result.warnings)


def test_unsupported_format_fails_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "sample.md"
    path.write_text("hello")
    result = ingest_file(path=path, auto=True, dry_run=True)

    assert result.import_result.status == UNSUPPORTED_FORMAT
