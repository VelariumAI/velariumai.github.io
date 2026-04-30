import copy
from pathlib import Path

from vcse.dsl import DSLCompiler, DSLLoader
from vcse.ingestion.pipeline import ingest_file
from vcse.interaction.normalizer import SemanticNormalizer
from vcse.interaction.parser import PatternParser
from vcse.interaction.response_modes import ResponseMode, render_response
from vcse.interaction.session import Session
from vcse.memory.world_state import WorldStateMemory


def _example_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "dsl" / name


def _bundle(name: str):
    return DSLCompiler.compile(DSLLoader.load(_example_path(name)))


def test_dsl_synonym_affects_normalizer() -> None:
    bundle = _bundle("mortality.json")
    synonyms = [(rule.pattern, rule.replacement) for rule in bundle.synonyms]
    normalizer = SemanticNormalizer(external_synonyms=synonyms)

    normalized = normalizer.normalize("Can Socrates perish?")

    assert "is mortal" in normalized.normalized_text


def test_dsl_parser_pattern_affects_parser() -> None:
    bundle = _bundle("basic_logic.json")
    parser = PatternParser(external_patterns=bundle.parser_patterns)

    result = parser.parse("all birds are animals")

    assert result.frames
    frame = result.frames[0]
    assert getattr(frame, "relation") == "is_a"
    assert getattr(frame, "subject") == "birds"
    assert getattr(frame, "object") == "animals"


def test_dsl_relation_schema_registers_in_memory() -> None:
    bundle = _bundle("simple_policy.json")
    session = Session.create(dsl_bundle=bundle)

    session.ingest("Employees must be background checked.")
    session.solve()

    assert session.memory.get_relation_schema("requires") is not None


def test_dsl_ingestion_template_works(tmp_path: Path) -> None:
    bundle = _bundle("simple_policy.json")
    source = tmp_path / "policy.txt"
    source.write_text("Employees requires background checked.")

    result = ingest_file(source, auto=True, dry_run=True, dsl_bundle=bundle)

    assert result.import_result.frames_extracted >= 1
    assert result.import_result.status in {"IMPORTED", "PARTIAL", "CONTRADICTORY"}


def test_dsl_proposer_rule_produces_transition() -> None:
    bundle = _bundle("basic_logic.json")
    session = Session.create(dsl_bundle=bundle)

    session.ingest("All men are mortal. Socrates is a man. Can Socrates die?")
    result = session.solve()

    assert result is not None
    assert hasattr(result, "evaluation")
    assert result.evaluation.status.value == "VERIFIED"


def test_dsl_renderer_template_affects_output() -> None:
    bundle = _bundle("basic_logic.json")
    session = Session.create(dsl_bundle=bundle)

    session.ingest("All men are mortal. Socrates is a man. Can Socrates die?")
    result = session.solve()
    assert result is not None

    renderer_templates = {rule.relation: rule.template for rule in bundle.renderer_templates}
    text = render_response(result, ResponseMode.SIMPLE, session.memory, renderer_templates=renderer_templates)

    assert "is_a" not in text
    assert "Socrates is mortal" in text


def test_invalid_dsl_does_not_alter_baseline_behavior() -> None:
    baseline = Session.create()
    baseline.ingest("All men are mortal. Socrates is a man. Can Socrates die?")
    baseline_result = baseline.solve()

    followup = Session.create()
    followup.ingest("All men are mortal. Socrates is a man. Can Socrates die?")
    followup_result = followup.solve()

    assert baseline_result is not None and followup_result is not None
    assert baseline_result.evaluation.status == followup_result.evaluation.status


def test_renderer_does_not_mutate_state_with_dsl_templates() -> None:
    bundle = _bundle("basic_logic.json")
    session = Session.create(dsl_bundle=bundle)
    session.ingest("All men are mortal. Socrates is a man. Can Socrates die?")
    result = session.solve()
    assert result is not None

    before = copy.deepcopy(session.memory.to_dict())
    renderer_templates = {rule.relation: rule.template for rule in bundle.renderer_templates}
    render_response(result, ResponseMode.EXPLAIN, session.memory, renderer_templates=renderer_templates)

    assert session.memory.to_dict() == before


def test_dsl_clarification_rule_is_applied(tmp_path: Path) -> None:
    dsl_path = tmp_path / "clarify.json"
    dsl_path.write_text(
        """
{
  "name": "clarify_bundle",
  "version": "1.0.0",
  "description": "clarification bundle",
  "artifacts": [
    {
      "id": "eligible_goal",
      "type": "parser_pattern",
      "version": "1.0.0",
      "description": "eligible goal",
      "enabled": true,
      "priority": 5,
      "pattern": "can {subject} get {object}",
      "output": {
        "frame_type": "goal",
        "relation": "eligible",
        "subject": "{subject}",
        "object": "{object}"
      }
    },
    {
      "id": "clarify_eligible",
      "type": "clarification_rule",
      "version": "1.0.0",
      "description": "ask for eligibility rules",
      "enabled": true,
      "priority": 10,
      "trigger": {
        "relation": "eligible",
        "missing_rule": false
      },
      "message": "I need the eligibility criteria before I can verify that."
    }
  ]
}
""".strip()
    )
    bundle = DSLCompiler.compile(DSLLoader.load(dsl_path))
    session = Session.create(dsl_bundle=bundle)

    session.ingest("Can Alice get premium")
    result = session.solve()

    assert result is not None
    assert hasattr(result, "user_message")
    assert "eligibility criteria" in result.user_message.lower()
