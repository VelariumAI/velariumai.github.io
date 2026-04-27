from pathlib import Path

from vcse.dsl.compiler import DSLCompiler
from vcse.dsl.loader import DSLLoader


def _example_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "dsl" / name


def test_compiler_ignores_disabled_artifacts(tmp_path: Path) -> None:
    path = tmp_path / "disabled.json"
    path.write_text(
        """
{
  "name": "disabled_case",
  "version": "1.0.0",
  "description": "disabled artifact case",
  "artifacts": [
    {
      "id": "on_syn",
      "type": "synonym",
      "version": "1.0.0",
      "description": "enabled synonym",
      "enabled": true,
      "priority": 10,
      "patterns": ["perish"],
      "replacement": "is mortal"
    },
    {
      "id": "off_syn",
      "type": "synonym",
      "version": "1.0.0",
      "description": "disabled synonym",
      "enabled": false,
      "priority": 1,
      "patterns": ["die"],
      "replacement": "is mortal"
    }
  ]
}
""".strip()
    )

    bundle = DSLCompiler.compile(DSLLoader.load(path))

    assert len(bundle.synonyms) == 1
    assert bundle.synonyms[0].id == "on_syn"


def test_compiler_priority_ordering_works(tmp_path: Path) -> None:
    path = tmp_path / "priority.json"
    path.write_text(
        """
{
  "name": "priority_case",
  "version": "1.0.0",
  "description": "priority ordering",
  "artifacts": [
    {
      "id": "z_late",
      "type": "synonym",
      "version": "1.0.0",
      "description": "late",
      "enabled": true,
      "priority": 50,
      "patterns": ["die"],
      "replacement": "is mortal"
    },
    {
      "id": "a_early",
      "type": "synonym",
      "version": "1.0.0",
      "description": "early",
      "enabled": true,
      "priority": 10,
      "patterns": ["perish"],
      "replacement": "is mortal"
    }
  ]
}
""".strip()
    )

    bundle = DSLCompiler.compile(DSLLoader.load(path))

    assert bundle.synonyms[0].id == "a_early"
    assert bundle.synonyms[1].id == "z_late"


def test_compiler_is_deterministic() -> None:
    doc = DSLLoader.load(_example_path("basic_logic.json"))

    bundle_1 = DSLCompiler.compile(doc)
    bundle_2 = DSLCompiler.compile(doc)

    assert bundle_1 == bundle_2


def test_compiler_bundle_contains_expected_artifacts() -> None:
    doc = DSLLoader.load(_example_path("basic_logic.json"))
    bundle = DSLCompiler.compile(doc)

    assert bundle.name == "logic_basic"
    assert bundle.version == "1.0.0"
    assert bundle.parser_patterns
    assert bundle.proposer_rules
    assert bundle.relation_schemas
    assert bundle.renderer_templates


def test_compiler_generation_template_compiles() -> None:
    doc = DSLLoader.load(_example_path("generation_policy.json"))
    bundle = DSLCompiler.compile(doc)

    assert len(bundle.generation_templates) == 1
    assert bundle.generation_templates[0].artifact_type == "policy"
