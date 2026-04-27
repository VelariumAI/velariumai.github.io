from vcse.memory.relations import RelationSchema
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.proposer.rule_based import RuleBasedProposer
from vcse.renderer.explanation import ExplanationRenderer
from vcse.search.beam import BeamSearch
from vcse.transitions.state_transition import Transition
from vcse.verifier.final_state import FinalStateEvaluator, FinalStatus
from vcse.verifier.stack import VerifierStack


def make_logic_state() -> WorldStateMemory:
    state = WorldStateMemory()
    state.add_relation_schema(RelationSchema(name="is_a", transitive=True))
    state.add_claim("Socrates", "is_a", "Man", TruthStatus.ASSERTED)
    state.add_claim("Man", "is_a", "Mortal", TruthStatus.ASSERTED)
    state.add_goal("Socrates", "is_a", "Mortal")
    return state


def test_duplicate_claims_resolve_to_one_id() -> None:
    state = WorldStateMemory()
    first = state.add_claim("Socrates", "is_a", "Man")
    second = state.add_claim(" Socrates ", "is_a", " Man ")

    assert first == second
    assert len(state.claims) == 1


def test_transition_applies_to_clone_and_preserves_parent() -> None:
    state = WorldStateMemory()
    transition = Transition(
        type="AddClaim",
        args={"subject": "Socrates", "relation": "is_a", "object": "Mortal"},
        description="Infer Socrates is_a Mortal",
        expected_effect="Adds supported claim",
    )

    new_state, result = transition.apply(state)

    assert result.passed
    assert state.find_claim("Socrates", "is_a", "Mortal") is None
    assert new_state.find_claim("Socrates", "is_a", "Mortal") is not None


def test_rule_based_proposer_generates_transitive_transition() -> None:
    state = make_logic_state()
    proposer = RuleBasedProposer()

    proposals = proposer.propose(state, state.goals[0])

    assert all(isinstance(item, Transition) for item in proposals)
    assert any(
        item.args.get("subject") == "Socrates"
        and item.args.get("relation") == "is_a"
        and item.args.get("object") == "Mortal"
        for item in proposals
    )
    assert state.find_claim("Socrates", "is_a", "Mortal") is None


def test_beam_search_verifies_socrates_goal_with_proof_trace() -> None:
    state = make_logic_state()
    search = BeamSearch(
        proposer=RuleBasedProposer(),
        verifier_stack=VerifierStack.default(),
        final_state_evaluator=FinalStateEvaluator(),
        max_depth=3,
        beam_width=2,
    )

    node = search.run(state)
    evaluation = FinalStateEvaluator().evaluate(node.state)

    assert evaluation.status == FinalStatus.VERIFIED
    assert evaluation.answer == "Socrates is_a Mortal"
    assert evaluation.proof_trace == [
        "Socrates is_a Man",
        "Man is_a Mortal",
        "Socrates is_a Mortal",
    ]


def test_renderer_includes_status_answer_and_proof_trace() -> None:
    state = make_logic_state()
    search = BeamSearch(
        proposer=RuleBasedProposer(),
        verifier_stack=VerifierStack.default(),
        final_state_evaluator=FinalStateEvaluator(),
    )

    node = search.run(state)
    text = ExplanationRenderer().render(FinalStateEvaluator().evaluate(node.state))

    assert "status: VERIFIED" in text
    assert "answer: Socrates is_a Mortal" in text
    assert "- Socrates is_a Man" in text
    assert "- Man is_a Mortal" in text
    assert "- Socrates is_a Mortal" in text
