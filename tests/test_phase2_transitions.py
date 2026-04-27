from vcse.memory.constraints import Constraint
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.proposer.rule_based import RuleBasedProposer
from vcse.transitions.actions import (
    ADD_CLAIM,
    ADD_CONSTRAINT,
    ADD_EVIDENCE,
    ADD_GOAL,
    BIND_SYMBOL,
    RECORD_CONTRADICTION,
    UPDATE_TRUTH_STATUS,
)
from vcse.transitions.state_transition import Transition


def test_transition_does_not_mutate_parent_state() -> None:
    parent = WorldStateMemory()
    transition = Transition(
        type=ADD_GOAL,
        args={"subject": "Socrates", "relation": "is_a", "object": "Mortal"},
        description="Set proof goal",
        expected_effect="Goal is stored",
        source="test",
    )

    child, result = transition.apply(parent)

    assert result.passed
    assert parent.goals == []
    assert child.goals[0].text == "Socrates is_a Mortal"
    assert child.parent_version == parent.version


def test_invalid_transition_fails_cleanly_with_structured_reasons() -> None:
    state = WorldStateMemory()
    transition = Transition(
        type=ADD_CLAIM,
        args={"subject": "Socrates", "relation": "is_a"},
        description="Malformed claim",
        expected_effect="Should fail",
        source="test",
    )

    new_state, result = transition.apply(state)

    assert not result.passed
    assert result.status == "INVALID_TRANSITION"
    assert result.reasons == ["Missing required AddClaim args: object"]
    assert result.affected_elements == []
    assert new_state.claims == {}


def test_add_claim_deduplicates_through_memory_and_tracks_affected_element() -> None:
    state = WorldStateMemory()
    existing = state.add_claim("Socrates", "is_a", "Man", TruthStatus.ASSERTED)
    transition = Transition(
        type=ADD_CLAIM,
        args={
            "subject": " Socrates ",
            "relation": "is_a",
            "object": "Man",
            "status": "SUPPORTED",
        },
        description="Duplicate claim",
        expected_effect="Claim is present",
        source="test",
    )

    new_state, result = transition.apply(state)

    assert result.passed
    assert result.affected_elements == [existing]
    assert len(new_state.claims) == 1
    assert len(state.claims) == 1


def test_add_constraint_stores_structured_constraint() -> None:
    state = WorldStateMemory()
    transition = Transition(
        type=ADD_CONSTRAINT,
        args={"kind": "numeric", "target": "x", "operator": ">", "value": 0},
        description="Require x positive",
        expected_effect="Constraint is stored",
        source="test",
    )

    new_state, result = transition.apply(state)

    assert result.passed
    assert new_state.constraints == [Constraint(kind="numeric", target="x", operator=">", value=0)]
    assert state.constraints == []
    assert result.affected_elements == ["constraint:1"]


def test_update_truth_status_preserves_enum_type() -> None:
    state = WorldStateMemory()
    claim_id = state.add_claim("A", "is_a", "B", TruthStatus.UNKNOWN)
    transition = Transition(
        type=UPDATE_TRUTH_STATUS,
        args={"claim_id": claim_id, "status": "SUPPORTED"},
        description="Support claim",
        expected_effect="Truth status is updated",
        source="test",
    )

    new_state, result = transition.apply(state)

    assert result.passed
    assert state.get_claim(claim_id).status is TruthStatus.UNKNOWN
    assert new_state.get_claim(claim_id).status is TruthStatus.SUPPORTED
    assert result.affected_elements == [claim_id]


def test_bind_symbol_add_evidence_and_record_contradiction_update_indexes() -> None:
    state = WorldStateMemory()
    claim_id = state.add_claim("x", "equals", "3", TruthStatus.ASSERTED)

    bound_state, bind_result = Transition(
        type=BIND_SYMBOL,
        args={"name": "x", "value": 3},
        description="Bind x",
        expected_effect="Symbol binding is stored",
        source="test",
    ).apply(state)
    evidence_state, evidence_result = Transition(
        type=ADD_EVIDENCE,
        args={"target_id": claim_id, "content": "Given x equals 3", "source": "fixture"},
        description="Attach evidence",
        expected_effect="Evidence is stored",
        source="test",
    ).apply(bound_state)
    contradicted_state, contradiction_result = Transition(
        type=RECORD_CONTRADICTION,
        args={
            "element_id": claim_id,
            "reason": "x cannot equal both 3 and 4",
            "related_element_ids": ["claim:missing"],
        },
        description="Record contradiction",
        expected_effect="Contradiction is indexed",
        source="test",
    ).apply(evidence_state)

    assert bind_result.passed
    assert evidence_result.passed
    assert contradiction_result.passed
    assert contradicted_state.symbol_bindings["x"] == 3
    assert contradicted_state.evidence[claim_id][0]["content"] == "Given x equals 3"
    assert contradicted_state.get_contradictions_for(claim_id)[0].reason == "x cannot equal both 3 and 4"
    assert contradicted_state.get_contradictions_for("claim:missing")[0].reason == "x cannot equal both 3 and 4"


def test_all_proposers_return_transition_objects_only() -> None:
    state = WorldStateMemory()
    state.add_relation_schema_from_name("is_a", transitive=True)
    state.add_claim("A", "is_a", "B", TruthStatus.ASSERTED)
    state.add_claim("B", "is_a", "C", TruthStatus.ASSERTED)

    proposals = RuleBasedProposer().propose(state)

    assert proposals
    assert all(isinstance(proposal, Transition) for proposal in proposals)
