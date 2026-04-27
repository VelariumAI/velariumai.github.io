from vcse.memory.relations import RelationSchema
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.proposer.rule_based import RuleBasedProposer
from vcse.search.beam import BeamSearch, SearchConfig
from vcse.search.result import SearchResult
from vcse.transitions.actions import ADD_CLAIM
from vcse.transitions.state_transition import Transition
from vcse.verifier.final_state import FinalStateEvaluator, FinalStatus
from vcse.verifier.stack import VerifierStack


class StaticProposer:
    def __init__(self, transitions: list[Transition]) -> None:
        self.transitions = transitions
        self.calls = 0

    def propose(self, memory: WorldStateMemory, goal=None) -> list[Transition]:
        self.calls += 1
        return list(self.transitions)


def make_search(proposer, config: SearchConfig | None = None) -> BeamSearch:
    return BeamSearch(
        proposer=proposer,
        verifier_stack=VerifierStack.default(),
        final_state_evaluator=FinalStateEvaluator(),
        config=config or SearchConfig(),
    )


def make_logic_state() -> WorldStateMemory:
    state = WorldStateMemory()
    state.add_relation_schema(RelationSchema("is_a", transitive=True))
    state.add_claim("A", "is_a", "B", TruthStatus.ASSERTED)
    state.add_claim("B", "is_a", "C", TruthStatus.ASSERTED)
    state.add_goal("A", "is_a", "C")
    return state


def test_search_finds_transitive_conclusion_and_returns_result_stats() -> None:
    result = make_search(RuleBasedProposer()).run(make_logic_state())

    assert isinstance(result, SearchResult)
    assert result.evaluation.status == FinalStatus.VERIFIED
    assert result.terminal_status == "VERIFIED"
    assert result.state.find_claim("A", "is_a", "C") is not None
    assert result.nodes_expanded == 1
    assert result.max_depth_reached == 1
    assert result.best_score == result.best_node.score


def test_search_stops_early_when_initial_state_is_verified() -> None:
    state = make_logic_state()
    state.add_claim("A", "is_a", "C", TruthStatus.ASSERTED)
    proposer = StaticProposer([])

    result = make_search(proposer).run(state)

    assert result.terminal_status == "VERIFIED"
    assert result.nodes_expanded == 0
    assert proposer.calls == 0


def test_search_prunes_contradictory_branch() -> None:
    state = WorldStateMemory()
    state.add_claim("x", "equals", "3", TruthStatus.ASSERTED)
    state.add_goal("x", "equals", "4")
    proposer = StaticProposer(
        [
            Transition(
                type=ADD_CLAIM,
                args={
                    "subject": "x",
                    "relation": "equals",
                    "object": "4",
                    "status": "ASSERTED",
                },
                description="Contradict x",
                expected_effect="Adds conflicting equality",
                source="test",
            )
        ]
    )

    result = make_search(proposer).run(state)

    assert result.nodes_expanded == 1
    assert result.terminal_status == "INCONCLUSIVE"
    assert result.best_node.depth == 0


def test_max_nodes_expanded_is_enforced() -> None:
    state = WorldStateMemory()
    state.add_goal("A", "is_a", "Z")
    transitions = [
        Transition(
            type=ADD_CLAIM,
            args={"subject": f"A{i}", "relation": "is_a", "object": f"B{i}"},
            description="Add distractor",
            expected_effect="Adds distractor claim",
            source="test",
        )
        for i in range(5)
    ]

    result = make_search(StaticProposer(transitions), SearchConfig(max_nodes_expanded=2)).run(state)

    assert result.nodes_expanded == 2
    assert result.nodes_expanded <= 2


def test_max_depth_is_enforced() -> None:
    state = WorldStateMemory()
    state.add_relation_schema(RelationSchema("is_a", transitive=True))
    state.add_claim("A", "is_a", "B", TruthStatus.ASSERTED)
    state.add_claim("B", "is_a", "C", TruthStatus.ASSERTED)
    state.add_claim("C", "is_a", "D", TruthStatus.ASSERTED)
    state.add_goal("A", "is_a", "D")

    result = make_search(RuleBasedProposer(), SearchConfig(max_depth=1, beam_width=4)).run(state)

    assert result.terminal_status == "INCONCLUSIVE"
    assert result.max_depth_reached == 1
    assert result.state.find_claim("A", "is_a", "D") is None


def test_returns_inconclusive_when_no_verified_path_exists() -> None:
    state = WorldStateMemory()
    state.add_claim("A", "related_to", "B", TruthStatus.ASSERTED)
    state.add_goal("A", "related_to", "C")

    result = make_search(RuleBasedProposer()).run(state)

    assert result.evaluation.status == FinalStatus.INCONCLUSIVE
    assert result.terminal_status == "INCONCLUSIVE"


def test_beam_width_limits_frontier() -> None:
    state = WorldStateMemory()
    state.add_goal("target", "is_a", "done")
    transitions = [
        Transition(
            type=ADD_CLAIM,
            args={"subject": f"A{i}", "relation": "is_a", "object": f"B{i}"},
            description="Add branch",
            expected_effect="Adds branch claim",
            source="test",
        )
        for i in range(4)
    ]

    result = make_search(
        StaticProposer(transitions),
        SearchConfig(max_depth=1, beam_width=2, max_nodes_expanded=10),
    ).run(state)

    assert result.max_frontier_size <= 2
