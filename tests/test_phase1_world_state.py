from pathlib import Path

from vcse.memory.constraints import Constraint
from vcse.memory.relations import RelationSchema
from vcse.memory.world_state import TruthStatus, WorldStateMemory


def test_canonical_claim_identity_includes_normalized_qualifiers() -> None:
    state = WorldStateMemory()

    first = state.add_claim(
        " Socrates ",
        " is_a ",
        " Man ",
        status=TruthStatus.ASSERTED,
        qualifiers={"source": "dialogue", "confidence": "1"},
    )
    second = state.add_claim(
        "Socrates",
        "is_a",
        "Man",
        status=TruthStatus.SUPPORTED,
        qualifiers={"confidence": "1", "source": "dialogue"},
    )
    third = state.add_claim(
        "Socrates",
        "is_a",
        "Man",
        qualifiers={"source": "different"},
    )

    assert first == second
    assert third != first
    assert len(state.claims) == 2
    assert state.get_claim(first).status == TruthStatus.ASSERTED


def test_clone_can_diverge_without_mutating_parent() -> None:
    parent = WorldStateMemory()
    parent.add_claim("A", "is_a", "B", TruthStatus.ASSERTED)

    child = parent.clone()
    child.add_claim("B", "is_a", "C", TruthStatus.ASSERTED)

    assert child.parent_version == parent.version
    assert child.version == parent.version + 1
    assert parent.find_claim("B", "is_a", "C") is None
    assert child.find_claim("B", "is_a", "C") is not None


def test_serialization_round_trip_preserves_enums_schemas_constraints_and_goals(tmp_path: Path) -> None:
    state = WorldStateMemory()
    state.add_relation_schema(
        RelationSchema(
            name="sibling_of",
            symmetric=True,
            transitive=False,
            reflexive=False,
            functional=False,
            inverse="sibling_of",
        )
    )
    claim_id = state.add_claim("Ada", "sibling_of", "Byron", TruthStatus.ASSERTED)
    state.add_constraint(Constraint(kind="numeric", target="x", operator=">", value=0))
    state.add_goal("Ada", "sibling_of", "Byron")
    state.record_contradiction(claim_id, "example contradiction", related_element_ids=["goal:1"])

    loaded = WorldStateMemory.from_dict(state.to_dict())

    assert loaded.get_claim(claim_id).status is TruthStatus.ASSERTED
    assert loaded.get_relation_schema("sibling_of") == state.get_relation_schema("sibling_of")
    assert loaded.constraints[0] == Constraint(kind="numeric", target="x", operator=">", value=0)
    assert loaded.goals[0].text == "Ada sibling_of Byron"
    assert loaded.get_contradictions_for(claim_id)[0].reason == "example contradiction"

    path = tmp_path / "state.json"
    state.save_json(path)
    loaded_from_file = WorldStateMemory.load_json(path)

    assert loaded_from_file.get_claim(claim_id).status is TruthStatus.ASSERTED
    assert loaded_from_file.constraints[0].operator == ">"


def test_contradiction_index_detects_items_on_dependency_path() -> None:
    state = WorldStateMemory()
    a = state.add_claim("A", "is_a", "B", TruthStatus.ASSERTED)
    b = state.add_claim("B", "is_a", "C", TruthStatus.ASSERTED)
    c = state.add_claim("A", "is_a", "C", TruthStatus.SUPPORTED, dependencies=[a, b])

    state.record_contradiction(b, "B is disputed")

    path = state.dependency_path_for_claim(c)
    assert path == [a, b, c]
    assert state.has_contradiction_on_path(path)
    assert state.get_contradictions_for(b)[0].reason == "B is disputed"
