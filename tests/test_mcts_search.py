from vcse.engine import CompositeProposer
from vcse.memory.constraints import Constraint
from vcse.memory.relations import RelationSchema
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.proposer.domain_specific import DomainSpecificProposer
from vcse.proposer.rule_based import RuleBasedProposer
from vcse.search.backend import SearchBackend
from vcse.search.beam import BeamSearch, SearchConfig
from vcse.search.mcts import MCTSSearch
from vcse.search.result import SearchResult
from vcse.transitions.actions import ADD_CLAIM
from vcse.transitions.state_transition import Transition
from vcse.verifier.final_state import FinalStateEvaluator, FinalStatus
from vcse.verifier.stack import VerifierStack


class StaticProposer:
    def __init__(self, transitions: list[Transition]) -> None:
        self.transitions = transitions

    def propose(self, memory: WorldStateMemory, goal=None) -> list[Transition]:
        return list(self.transitions)


def make_logic_state() -> WorldStateMemory:
    state = WorldStateMemory()
    state.add_relation_schema(RelationSchema("is_a", transitive=True))
    state.add_claim("A", "is_a", "B", TruthStatus.ASSERTED)
    state.add_claim("B", "is_a", "C", TruthStatus.ASSERTED)
    state.add_goal("A", "is_a", "C")
    return state


def make_mcts(config: SearchConfig) -> MCTSSearch:
    proposer = CompositeProposer([RuleBasedProposer(), DomainSpecificProposer()])
    return MCTSSearch(
        proposer=proposer,
        verifier_stack=VerifierStack.default(),
        final_state_evaluator=FinalStateEvaluator(),
        config=config,
    )


def test_backends_implement_search_backend() -> None:
    assert issubclass(BeamSearch, SearchBackend)
    assert issubclass(MCTSSearch, SearchBackend)


def test_mcts_finds_socrates_style_transitive_proof() -> None:
    result = make_mcts(
        SearchConfig(search_backend="mcts", mcts_iterations=80, mcts_max_depth=4, mcts_rollout_depth=3)
    ).run(make_logic_state())

    assert isinstance(result, SearchResult)
    assert result.evaluation.status == FinalStatus.VERIFIED
    assert result.state.find_claim("A", "is_a", "C") is not None
    assert result.stats.backend == "mcts"


def test_mcts_respects_iteration_bound() -> None:
    result = make_mcts(
        SearchConfig(search_backend="mcts", mcts_iterations=5, mcts_max_depth=2, mcts_rollout_depth=1)
    ).run(make_logic_state())

    assert result.stats.iterations <= 5


def test_mcts_respects_max_depth() -> None:
    state = make_logic_state()
    result = make_mcts(
        SearchConfig(search_backend="mcts", mcts_iterations=10, mcts_max_depth=0, mcts_rollout_depth=0)
    ).run(state)

    assert result.max_depth_reached == 0


def test_mcts_does_not_mutate_parent_state() -> None:
    state = make_logic_state()
    before = state.to_dict()

    make_mcts(
        SearchConfig(search_backend="mcts", mcts_iterations=20, mcts_max_depth=4, mcts_rollout_depth=2)
    ).run(state)

    assert state.to_dict() == before


def test_ts3_mcts_detects_loop_and_keeps_progressing_arithmetic_path() -> None:
    no_op_transitions = [
        Transition(
            type=ADD_CLAIM,
            args={"subject": "A", "relation": "is_a", "object": "B", "status": "ASSERTED"},
            description="No-op claim",
            expected_effect="No-op",
            source="test",
        )
    ]
    loop_state = WorldStateMemory()
    loop_state.add_relation_schema(RelationSchema("is_a", transitive=True))
    loop_state.add_claim("A", "is_a", "B", TruthStatus.ASSERTED)
    loop_state.add_goal("A", "is_a", "C")
    loop_search = MCTSSearch(
        proposer=StaticProposer(no_op_transitions),
        verifier_stack=VerifierStack.default(),
        final_state_evaluator=FinalStateEvaluator(),
        config=SearchConfig(search_backend="mcts", enable_ts3=True, mcts_iterations=10),
    )
    loop_result = loop_search.run(loop_state)
    assert loop_result.ts3_analysis is not None
    assert loop_result.ts3_analysis.loop_detected is True

    arithmetic_state = WorldStateMemory()
    arithmetic_state.add_claim("x", "equals", "5", TruthStatus.ASSERTED)
    arithmetic_state.add_constraint(Constraint(kind="numeric", target="x", operator=">", value=0))
    arithmetic_state.add_goal("x", "satisfies", "constraints")
    arithmetic_search = make_mcts(
        SearchConfig(search_backend="mcts", enable_ts3=True, mcts_iterations=60, mcts_rollout_depth=3)
    )
    arithmetic_result = arithmetic_search.run(arithmetic_state)
    assert arithmetic_result.evaluation.status == FinalStatus.VERIFIED
    assert arithmetic_result.ts3_analysis is not None
