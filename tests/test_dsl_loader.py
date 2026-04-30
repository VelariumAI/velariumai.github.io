from pathlib import Path

from vcse.dsl.errors import DSLError
from vcse.dsl.loader import DSLLoader


def test_dsl_loader_loads_json() -> None:
    doc = DSLLoader.load(Path(__file__).resolve().parents[1] / "examples" / "dsl" / "basic_logic.json")
    assert doc.name == "logic_basic"
    assert doc.artifacts


def test_dsl_loader_yaml_graceful_when_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "sample.yaml"
    path.write_text("name: x\nversion: 1.0.0\ndescription: y\nartifacts: []\n")
    try:
        doc = DSLLoader.load(path)
    except DSLError as exc:
        assert exc.error_type in {"UNSUPPORTED_FORMAT", "MALFORMED_DSL"}
    else:
        assert doc.name == "x"


def test_dsl_loader_malformed_file_fails_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json")
    try:
        DSLLoader.load(path)
    except DSLError as exc:
        assert exc.error_type == "MALFORMED_DSL"
    else:
        raise AssertionError("expected DSLError")
