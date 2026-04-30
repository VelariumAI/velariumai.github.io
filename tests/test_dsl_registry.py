from pathlib import Path

from vcse.dsl import CapabilityRegistry, DSLCompiler, DSLLoader


def _example_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "dsl" / name


def test_registry_register_list_unregister() -> None:
    registry = CapabilityRegistry()
    bundle = DSLCompiler.compile(DSLLoader.load(_example_path("basic_logic.json")))

    registry.register_bundle(bundle)
    assert registry.list_bundles() == ["logic_basic"]

    registry.unregister_bundle("logic_basic")
    assert registry.list_bundles() == []


def test_registry_duplicate_bundle_name_handled_cleanly() -> None:
    registry = CapabilityRegistry()

    first = DSLCompiler.compile(DSLLoader.load(_example_path("basic_logic.json")))
    second = DSLCompiler.compile(DSLLoader.load(_example_path("mortality.json")))

    # Force same registry key to validate deterministic overwrite behavior.
    second = second.__class__(
        name=first.name,
        version=second.version,
        synonyms=second.synonyms,
        parser_patterns=second.parser_patterns,
        relation_schemas=second.relation_schemas,
        ingestion_templates=second.ingestion_templates,
        generation_templates=second.generation_templates,
        proposer_rules=second.proposer_rules,
        clarification_rules=second.clarification_rules,
        renderer_templates=second.renderer_templates,
        verifier_stubs=second.verifier_stubs,
        warnings=second.warnings,
    )

    registry.register_bundle(first)
    registry.register_bundle(second)

    assert registry.list_bundles() == ["logic_basic"]
    assert registry.bundles["logic_basic"].version == second.version


def test_registry_getters_are_deterministic() -> None:
    registry = CapabilityRegistry()
    logic = DSLCompiler.compile(DSLLoader.load(_example_path("basic_logic.json")))
    mortality = DSLCompiler.compile(DSLLoader.load(_example_path("mortality.json")))

    registry.register_bundle(mortality)
    registry.register_bundle(logic)

    synonyms_1 = [item.id for item in registry.get_synonyms()]
    synonyms_2 = [item.id for item in registry.get_synonyms()]

    assert synonyms_1 == synonyms_2
