from pathlib import Path

from vcse.memory.constraints import Constraint
from vcse.memory.relations import RelationSchema
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.proposer.domain_specific import DomainSpecificProposer
from vcse.proposer.rule_based import RuleBasedProposer
from vcse.proposer.solver_backed import SolverBackedProposer
from vcse.transitions.actions import (
    ADD_EVIDENCE,
    BIND_SYMBOL,
    RECORD_CONTRADICTION,
)
from vcse.transitions.state_transition import Transition


def logic_state() -> WorldStateMemory:
    state = WorldStateMemory()
    state.add_relation_schema(RelationSchema("is_a", transitive=True))
    state.add_claim("A", "is_a", "B", TruthStatus.ASSERTED)
    state.add_claim("B", "is_a", "C", TruthStatus.ASSERTED)
    return state


def test_rule_based_proposer_returns_transition_objects_only_and_does_not_mutate_memory() -> None:
    state = logic_state()
    before = state.to_dict()

    proposals = RuleBasedProposer().propose(state)

    assert proposals
    assert all(isinstance(proposal, Transition) for proposal in proposals)
    assert state.to_dict() == before


def test_rule_based_proposer_proposes_transitive_closure() -> None:
    proposals = RuleBasedProposer().propose(logic_state())

    assert any(
        proposal.type == "AddClaim"
        and proposal.args["subject"] == "A"
        and proposal.args["relation"] == "is_a"
        and proposal.args["object"] == "C"
        for proposal in proposals
    )


def test_rule_based_proposer_proposes_contradiction_transition_for_conflicting_equalities() -> None:
    state = WorldStateMemory()
    first = state.add_claim("x", "equals", "3", TruthStatus.ASSERTED)
    second = state.add_claim("x", "equals", "4", TruthStatus.ASSERTED)

    proposals = RuleBasedProposer().propose(state)

    contradiction = next(
        proposal for proposal in proposals if proposal.type == RECORD_CONTRADICTION
    )
    assert contradiction.args["element_id"] == first
    assert contradiction.args["related_element_ids"] == [second]
    assert contradiction.args["reason"] == "x equals both 3 and 4"


def test_domain_specific_proposer_proposes_constraint_related_transition() -> None:
    state = WorldStateMemory()
    state.add_claim("x", "equals", "5", TruthStatus.ASSERTED)
    state.add_constraint(Constraint(kind="numeric", target="x", operator=">", value=0))

    proposals = DomainSpecificProposer().propose(state)

    assert any(
        proposal.type == BIND_SYMBOL
        and proposal.args["name"] == "x"
        and proposal.args["value"] == 5
        for proposal in proposals
    )


def test_domain_specific_proposer_proposes_constraint_evidence_for_bound_value() -> None:
    state = WorldStateMemory()
    state.bind_symbol("x", 5)
    state.add_constraint(Constraint(kind="numeric", target="x", operator=">", value=0))

    proposals = DomainSpecificProposer().propose(state)

    assert any(
        proposal.type == ADD_EVIDENCE
        and proposal.args["target_id"] == "constraint:1"
        and "satisfies" in proposal.args["content"]
        for proposal in proposals
    )


def test_solver_backed_proposer_degrades_gracefully_without_crashing() -> None:
    state = WorldStateMemory()
    state.add_constraint(Constraint(kind="numeric", target="x", operator=">", value=10))
    state.add_constraint(Constraint(kind="numeric", target="x", operator="<=", value=10))
    proposer = SolverBackedProposer()

    proposals = proposer.propose(state)
    status = proposer.support_status()

    assert all(isinstance(proposal, Transition) for proposal in proposals)
    assert status.status in {"SOLVER_AVAILABLE", "SOLVER_UNAVAILABLE"}
    assert status.reasons


def test_no_forbidden_proposer_files_or_terms_exist() -> None:
    proposer_dir = Path(__file__).resolve().parents[1] / "src" / "vcse" / "proposer"

    assert not (proposer_dir / "neural_stub.py").exists()

    forbidden = ("llm", "neural", "transformer", "next-token", "autoregressive")
    for path in proposer_dir.glob("*.py"):
        text = path.read_text().lower()
        assert not any(term in text for term in forbidden), path
