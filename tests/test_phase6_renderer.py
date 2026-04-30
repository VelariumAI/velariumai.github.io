from pathlib import Path

from vcse.memory.relations import RelationSchema
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.proposer.rule_based import RuleBasedProposer
from vcse.renderer.explanation import ExplanationRenderer
from vcse.search.beam import BeamSearch
from vcse.verifier.final_state import FinalStateEvaluation, FinalStateEvaluator, FinalStatus
from vcse.verifier.stack import VerifierStack


def render_text(evaluation: FinalStateEvaluation, state: WorldStateMemory | None = None) -> str:
    return ExplanationRenderer().render(evaluation, state=state)


def test_renders_verified_result_with_proof_trace_and_template_sections() -> None:
    state = WorldStateMemory()
    state.add_relation_schema(RelationSchema("is_a", transitive=True))
    state.add_claim("Socrates", "is_a", "Man", TruthStatus.ASSERTED)
    state.add_claim("Man", "is_a", "Mortal", TruthStatus.ASSERTED)
    state.add_goal("Socrates", "is_a", "Mortal")
    result = BeamSearch(
        proposer=RuleBasedProposer(),
        verifier_stack=VerifierStack.default(),
        final_state_evaluator=FinalStateEvaluator(),
    ).run(state)

    text = ExplanationRenderer().render(result)

    assert "status: VERIFIED" in text
    assert "answer: Socrates is_a Mortal" in text
    assert "proof_trace:" in text
    assert "  - Socrates is_a Man" in text
    assert "  - Man is_a Mortal" in text
    assert "  - Socrates is_a Mortal" in text
    assert "assumptions_used:" in text
    assert "contradictions:" in text
    assert "verifier_reasons:" in text
    assert "search_stats:" in text
    assert "  nodes_expanded:" in text


def test_renders_contradictory_result_without_inventing_answer() -> None:
    state = WorldStateMemory()
    first = state.add_claim("x", "equals", "3", TruthStatus.ASSERTED)
    second = state.add_claim("x", "equals", "4", TruthStatus.ASSERTED)
    state.record_contradiction(first, "x equals both 3 and 4", related_element_ids=[second])
    evaluation = FinalStateEvaluator().evaluate(state)

    text = render_text(evaluation, state)

    assert "status: CONTRADICTORY" in text
    assert "answer: null" in text
    assert "contradictions:" in text
    assert "  - x equals both 3 and 4" in text


def test_renders_inconclusive_result_clearly() -> None:
    evaluation = FinalStateEvaluation(
        status=FinalStatus.INCONCLUSIVE,
        answer=None,
        reasons=["Goal not satisfied: A is_a C"],
    )

    text = render_text(evaluation)

    assert "status: INCONCLUSIVE" in text
    assert "answer: null" in text
    assert "verifier_reasons:" in text
    assert "  - Goal not satisfied: A is_a C" in text


def test_renders_unsatisfiable_result_clearly() -> None:
    evaluation = FinalStateEvaluation(
        status=FinalStatus.UNSATISFIABLE,
        answer=None,
        reasons=["x > 10 conflicts with x <= 10"],
    )

    text = render_text(evaluation)

    assert "status: UNSATISFIABLE" in text
    assert "answer: null" in text
    assert "  - x > 10 conflicts with x <= 10" in text


def test_renderer_does_not_mutate_state() -> None:
    state = WorldStateMemory()
    state.add_claim("hypothesis", "is_a", "Assumption", TruthStatus.ASSUMED)
    before = state.to_dict()

    ExplanationRenderer().render(
        FinalStateEvaluation(status=FinalStatus.INCONCLUSIVE, reasons=["No goal"]),
        state=state,
    )

    assert state.to_dict() == before


def test_source_scan_confirms_no_forbidden_renderer_terms() -> None:
    renderer_dir = Path(__file__).resolve().parents[1] / "src" / "vcse" / "renderer"
    forbidden = ("llm", "neural", "generative", "generate", "next-token", "transformer")

    for path in renderer_dir.glob("*.py"):
        text = path.read_text().lower()
        assert not any(term in text for term in forbidden), path
