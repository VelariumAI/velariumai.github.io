import json
from pathlib import Path

from vcse.dsl import DSLCompiler, DSLLoader
from vcse.generation import GenerationPipeline, GenerationSpec, VerifiedGenerator, spec_from_dict
from vcse.memory.relations import RelationSchema
from vcse.memory.world_state import TruthStatus, WorldStateMemory


def _example_spec(name: str) -> dict:
    path = Path(__file__).resolve().parents[1] / "examples" / "generation" / name
    return json.loads(path.read_text())


def _dsl_bundle(name: str):
    path = Path(__file__).resolve().parents[1] / "examples" / "dsl" / name
    return DSLCompiler.compile(DSLLoader.load(path))


def test_generation_spec_valid_passes() -> None:
    spec = spec_from_dict(_example_spec("contractor_policy_spec.json"))
    missing = spec.validate()
    assert missing == []


def test_generation_spec_incomplete_needs_clarification() -> None:
    spec = spec_from_dict(_example_spec("incomplete_policy_spec.json"))
    missing = spec.validate()
    assert set(missing) == {"approver", "duration"}


def test_generation_spec_invalid_artifact_type_fails() -> None:
    payload = _example_spec("contractor_policy_spec.json")
    payload["artifact_type"] = "novel"
    spec = spec_from_dict(payload)
    try:
        spec.validate()
        assert False, "expected validation failure"
    except Exception as exc:
        assert "INVALID_ARTIFACT_TYPE" in str(exc)


def test_template_render_is_deterministic() -> None:
    spec = spec_from_dict(_example_spec("contractor_policy_spec.json"))
    memory = WorldStateMemory()
    pipeline = GenerationPipeline()

    r1 = pipeline.generate(spec, memory)
    r2 = pipeline.generate(spec, memory)

    assert r1.best_artifact is not None
    assert r2.best_artifact is not None
    assert r1.best_artifact.content == r2.best_artifact.content


def test_generate_policy_from_complete_spec_verified() -> None:
    spec = spec_from_dict(_example_spec("contractor_policy_spec.json"))
    memory = WorldStateMemory()
    result = VerifiedGenerator().generate(spec, memory)

    assert result.status == "VERIFIED_ARTIFACT"
    assert result.best_artifact is not None
    assert result.best_artifact.provenance


def test_does_not_generate_from_incomplete_spec() -> None:
    spec = spec_from_dict(_example_spec("incomplete_policy_spec.json"))
    result = VerifiedGenerator().generate(spec, WorldStateMemory())

    assert result.status == "NEEDS_CLARIFICATION"
    assert result.clarification_request is not None


def test_multiple_templates_have_deterministic_ordering() -> None:
    spec = spec_from_dict(_example_spec("contractor_policy_spec.json"))
    bundle = _dsl_bundle("generation_policy.json")
    result = VerifiedGenerator().generate(spec, WorldStateMemory(), bundle=bundle)

    template_ids = [item.template_id for item in result.candidates]
    assert template_ids == sorted(template_ids)


def test_artifact_contradiction_detected() -> None:
    payload = _example_spec("simple_config_spec.json")
    payload["artifact_type"] = "config"
    payload["required_fields"] = {
        "name": "demo",
        "enabled": True,
        "threshold": 1,
        "subject": "x",
        "relation": "equals",
        "object": "4",
    }
    payload["success_criteria"] = ["demo"]
    spec = spec_from_dict(payload)

    memory = WorldStateMemory()
    memory.add_relation_schema(RelationSchema(name="equals"))
    memory.add_claim("x", "equals", "3", TruthStatus.ASSERTED)

    result = VerifiedGenerator().generate(spec, memory)
    assert result.status == "CONTRADICTORY_ARTIFACT"


def test_simple_plan_validation_verified() -> None:
    spec = spec_from_dict(_example_spec("simple_plan_spec.json"))
    result = VerifiedGenerator().generate(spec, WorldStateMemory())
    assert result.status == "VERIFIED_ARTIFACT"


def test_simple_config_validation_verified() -> None:
    spec = spec_from_dict(_example_spec("simple_config_spec.json"))
    result = VerifiedGenerator().generate(spec, WorldStateMemory())
    assert result.status == "VERIFIED_ARTIFACT"


def test_simple_code_is_inconclusive_without_execution() -> None:
    spec = spec_from_dict(_example_spec("simple_code_spec.json"))
    result = VerifiedGenerator().generate(spec, WorldStateMemory())
    assert result.status == "INCONCLUSIVE_ARTIFACT"
    assert result.best_artifact is not None
    assert "CODE_EXECUTION_NOT_ENABLED" in result.best_artifact.verifier_reasons


def test_generation_pipeline_index_mode() -> None:
    spec = spec_from_dict(_example_spec("contractor_policy_spec.json"))
    result = GenerationPipeline().generate(spec, WorldStateMemory(), enable_index=True, top_k_rules=1)

    assert result.best_artifact is not None
    assert result.template_stats.get("selected_templates_count", 1) >= 1
