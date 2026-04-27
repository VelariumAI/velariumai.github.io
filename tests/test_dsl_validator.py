from pathlib import Path

from vcse.dsl.loader import DSLLoader
from vcse.dsl.validator import DSLValidator


def _example_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "dsl" / name


def test_validator_valid_document_passes() -> None:
    doc = DSLLoader.load(_example_path("basic_logic.json"))
    result = DSLValidator.validate(doc)

    assert result.passed is True
    assert result.errors == []
    assert result.artifact_count >= 1
    assert result.enabled_count >= 1


def test_validator_duplicate_artifact_ids_fail() -> None:
    doc = DSLLoader.load(_example_path("invalid_duplicate_ids.json"))
    result = DSLValidator.validate(doc)

    assert result.passed is False
    assert any("Duplicate artifact id" in item for item in result.errors)


def test_validator_unknown_artifact_type_fails() -> None:
    doc = DSLLoader.load(_example_path("invalid_unknown_type.json"))
    result = DSLValidator.validate(doc)

    assert result.passed is False
    assert any("Unknown artifact type" in item for item in result.errors)


def test_validator_invalid_placeholder_fails(tmp_path: Path) -> None:
    path = tmp_path / "invalid_placeholder.json"
    path.write_text(
        """
{
  "name": "bad_placeholders",
  "version": "1.0.0",
  "description": "invalid placeholders",
  "artifacts": [
    {
      "id": "bad_pattern",
      "type": "parser_pattern",
      "version": "1.0.0",
      "description": "bad",
      "enabled": true,
      "priority": 10,
      "pattern": "all {subject-name} are {object}",
      "output": {
        "frame_type": "claim",
        "relation": "is_a",
        "subject": "{subject-name}",
        "object": "{object}"
      }
    }
  ]
}
""".strip()
    )

    doc = DSLLoader.load(path)
    result = DSLValidator.validate(doc)

    assert result.passed is False
    assert any("placeholder" in item.lower() for item in result.errors)


def test_validator_invalid_transition_action_fails(tmp_path: Path) -> None:
    path = tmp_path / "invalid_action.json"
    path.write_text(
        """
{
  "name": "bad_action",
  "version": "1.0.0",
  "description": "invalid action",
  "artifacts": [
    {
      "id": "bad_rule",
      "type": "proposer_rule",
      "version": "1.0.0",
      "description": "bad action",
      "enabled": true,
      "priority": 10,
      "when": [
        {"subject": "{a}", "relation": "is_a", "object": "{b}"},
        {"subject": "{b}", "relation": "is_a", "object": "{c}"}
      ],
      "then": {
        "action": "ExecutePython",
        "subject": "{a}",
        "relation": "is_a",
        "object": "{c}"
      }
    }
  ]
}
""".strip()
    )

    doc = DSLLoader.load(path)
    result = DSLValidator.validate(doc)

    assert result.passed is False
    assert any("Invalid transition action" in item for item in result.errors)
