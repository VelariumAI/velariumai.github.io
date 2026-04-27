from pathlib import Path

from vcse.ingestion.adapters import load_source_document
from vcse.ingestion.source import SourceLoadError


def test_json_adapter_loads(tmp_path: Path) -> None:
    path = tmp_path / "sample.json"
    path.write_text('{"subject":"a","relation":"is_a","object":"b"}')
    doc = load_source_document(path)
    assert doc.source_type == "json"
    assert isinstance(doc.content, dict)


def test_jsonl_adapter_loads(tmp_path: Path) -> None:
    path = tmp_path / "sample.jsonl"
    path.write_text('{"subject":"a","relation":"is_a","object":"b"}\n')
    doc = load_source_document(path)
    assert doc.source_type == "jsonl"
    assert isinstance(doc.content, list)
    assert len(doc.content) == 1


def test_csv_adapter_loads(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    path.write_text("subject,relation,object\na,is_a,b\n")
    doc = load_source_document(path)
    assert doc.source_type == "csv"
    assert isinstance(doc.content, list)
    assert doc.content[0]["subject"] == "a"


def test_text_adapter_loads(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("All employees are workers.")
    doc = load_source_document(path)
    assert doc.source_type == "text"
    assert "employees" in doc.content


def test_yaml_adapter_graceful_when_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "sample.yaml"
    path.write_text("subject: a\nrelation: is_a\nobject: b\n")
    try:
        doc = load_source_document(path)
    except SourceLoadError as exc:
        assert exc.error_type in {"UNSUPPORTED_FORMAT", "MALFORMED_YAML"}
    else:
        assert doc.source_type == "yaml"
