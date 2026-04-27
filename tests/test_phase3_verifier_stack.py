from vcse.memory.constraints import Constraint
from vcse.memory.relations import RelationSchema
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.verifier.claim_verifier import ClaimVerifier
from vcse.verifier.constraint_verifier import ConstraintVerifier
from vcse.verifier.contradiction_detector import ContradictionDetector
from vcse.verifier.final_state import FinalStateEvaluator, FinalStatus
from vcse.verifier.goal_checker import GoalSatisfactionChecker
from vcse.verifier.stack import VerifierStack


def test_transitive_relation_supports_goal_claim() -> None:
    state = WorldStateMemory()
    state.add_relation_schema(RelationSchema("is_a", transitive=True))
    a = state.add_claim("A", "is_a", "B", TruthStatus.ASSERTED)
    b = state.add_claim("B", "is_a", "C", TruthStatus.ASSERTED)
    c = state.add_claim("A", "is_a", "C", TruthStatus.SUPPORTED, dependencies=[a, b])
    state.add_goal("A", "is_a", "C")

    result = ClaimVerifier().evaluate(state)
    final = FinalStateEvaluator().evaluate(state, verifier_score=result.score)

    assert result.passed
    assert result.status == "CLAIMS_VERIFIED"
    assert c in result.affected_elements
    assert "Transitive support verified for A is_a C" in result.reasons
    assert final.status == FinalStatus.VERIFIED


def test_equality_conflict_returns_contradictory() -> None:
    state = WorldStateMemory()
    state.add_claim("x", "equals", "3", TruthStatus.ASSERTED)
    state.add_claim("x", "equals", "4", TruthStatus.ASSERTED)

    stack_result = VerifierStack.default().evaluate(state)
    final = FinalStateEvaluator().evaluate(state, verifier_score=stack_result.score)

    assert not stack_result.passed
    assert stack_result.status == "VERIFIER_STACK_FAILED"
    assert final.status == FinalStatus.CONTRADICTORY
    assert any("x equals both 3 and 4" in reason for reason in final.reasons)


def test_bound_numeric_value_satisfies_constraint() -> None:
    state = WorldStateMemory()
    state.bind_symbol("x", 5)
    state.add_constraint(Constraint(kind="numeric", target="x", operator=">", value=0))
    state.add_goal("x", "satisfies", "constraints")

    stack_result = VerifierStack.default().evaluate(state)
    final = FinalStateEvaluator().evaluate(state, verifier_score=stack_result.score)

    assert stack_result.passed
    assert final.status == FinalStatus.VERIFIED
    assert final.answer == "x satisfies constraints"


def test_bound_numeric_value_violates_constraint() -> None:
    state = WorldStateMemory()
    state.bind_symbol("x", -1)
    state.add_constraint(Constraint(kind="numeric", target="x", operator=">", value=0))

    result = ConstraintVerifier().evaluate(state)

    assert not result.passed
    assert result.status == "CONSTRAINTS_VIOLATED"
    assert result.reasons == ["x=-1 violates x > 0"]


def test_conflicting_numeric_constraints_return_unsatisfiable() -> None:
    state = WorldStateMemory()
    state.add_constraint(Constraint(kind="numeric", target="x", operator=">", value=10))
    state.add_constraint(Constraint(kind="numeric", target="x", operator="<=", value=10))

    stack_result = VerifierStack.default().evaluate(state)
    final = FinalStateEvaluator().evaluate(state, verifier_score=stack_result.score)

    assert not stack_result.passed
    assert final.status == FinalStatus.UNSATISFIABLE
    assert any("x > 10 conflicts with x <= 10" in reason for reason in final.reasons)


def test_final_state_rejects_answer_when_contradiction_touches_proof_path() -> None:
    state = WorldStateMemory()
    a = state.add_claim("A", "is_a", "B", TruthStatus.ASSERTED)
    b = state.add_claim("B", "is_a", "C", TruthStatus.ASSERTED)
    c = state.add_claim("A", "is_a", "C", TruthStatus.SUPPORTED, dependencies=[a, b])
    state.add_goal("A", "is_a", "C")
    state.record_contradiction(b, "B is disputed")

    final = FinalStateEvaluator().evaluate(state)

    assert final.status == FinalStatus.CONTRADICTORY
    assert final.answer == "A is_a C"
    assert final.proof_trace == ["A is_a B", "B is_a C", "A is_a C"]
    assert "Contradiction touches proof path" in final.reasons


def test_final_state_returns_inconclusive_when_goal_is_unmet() -> None:
    state = WorldStateMemory()
    state.add_claim("A", "is_a", "B", TruthStatus.ASSERTED)
    state.add_goal("A", "is_a", "C")

    stack_result = VerifierStack.default().evaluate(state)
    final = FinalStateEvaluator().evaluate(state, verifier_score=stack_result.score)
    goal_result = GoalSatisfactionChecker().evaluate(state)

    assert goal_result.passed
    assert goal_result.status == "GOAL_UNMET"
    assert final.status == FinalStatus.INCONCLUSIVE
