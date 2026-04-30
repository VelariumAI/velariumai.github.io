from vcse.memory.relations import RelationSchema
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.search.beam import BeamSearch, SearchConfig
from vcse.transitions.actions import ADD_CLAIM
from vcse.transitions.state_transition import Transition
from vcse.ts3.absorption import AbsorptionAnalyzer
from vcse.ts3.loop_detector import LOOP_DETECTED, LoopDetector
from vcse.ts3.reachability import ReachabilityAnalyzer
from vcse.ts3.signature import StateSignature
from vcse.ts3.symbolic_state import SymbolicState
from vcse.ts3.trajectory import Trajectory
from vcse.verifier.final_state import FinalStateEvaluator
from vcse.verifier.stack import VerifierStack


def make_logic_state() -> WorldStateMemory:
    state = WorldStateMemory()
    state.add_relation_schema(RelationSchema("is_a", transitive=True))
    state.add_claim("A", "is_a", "B", TruthStatus.ASSERTED)
    state.add_claim("B", "is_a", "C", TruthStatus.ASSERTED)
    state.add_goal("A", "is_a", "C")
    return state


def test_state_signature_identical_for_equivalent_states() -> None:
    left = make_logic_state()
    right = WorldStateMemory()
    right.add_relation_schema(RelationSchema("is_a", transitive=True))
    right.add_claim("B", "is_a", "C", TruthStatus.ASSERTED)
    right.add_claim("A", "is_a", "B", TruthStatus.ASSERTED)
    right.add_goal("A", "is_a", "C")

    assert StateSignature.from_memory(left) == StateSignature.from_memory(right)


def test_state_signature_differs_when_claims_differ() -> None:
    left = make_logic_state()
    right = make_logic_state()
    right.add_claim("C", "is_a", "D", TruthStatus.ASSERTED)

    assert StateSignature.from_memory(left) != StateSignature.from_memory(right)


def test_loop_detector_detects_repeated_signature() -> None:
    trajectory = Trajectory(
        symbolic_states=[
            SymbolicState("sig:a", 0, "INCONCLUSIVE", 0.1, 1),
            SymbolicState("sig:b", 1, "INCONCLUSIVE", 0.2, 1),
            SymbolicState("sig:a", 2, "INCONCLUSIVE", 0.2, 0),
        ]
    )

    assert LoopDetector().detect(trajectory) == LOOP_DETECTED


def test_reachability_counts_states_by_depth() -> None:
    reachability = ReachabilityAnalyzer()
    reachability.observe(0, "a")
    reachability.observe(1, "b")
    reachability.observe(1, "c")
    reachability.observe(1, "b")

    assert reachability.report() == {0: 1, 1: 2}


def test_absorption_counts_terminal_and_dead_end_paths() -> None:
    analyzer = AbsorptionAnalyzer()
    analyzer.record("VERIFIED")
    analyzer.record("CONTRADICTORY")
    analyzer.record("UNSATISFIABLE")
    analyzer.record("INCONCLUSIVE")
    report = analyzer.report()

    assert report["verified_paths"] == 1
    assert report["contradictory_paths"] == 1
    assert report["unsatisfiable_paths"] == 1
    assert report["dead_end_paths"] == 1
    assert report["absorption_rate"] == 0.75


class StaticProposer:
    def __init__(self, transitions: list[Transition]) -> None:
        self.transitions = transitions

    def propose(self, memory: WorldStateMemory, goal=None) -> list[Transition]:
        return list(self.transitions)


def test_beam_search_ts3_prunes_repeated_signatures_on_path() -> None:
    state = WorldStateMemory()
    state.add_relation_schema(RelationSchema("is_a", transitive=True))
    state.add_claim("A", "is_a", "B", TruthStatus.ASSERTED)
    state.add_goal("A", "is_a", "C")
    transitions = [
        Transition(
            type=ADD_CLAIM,
            args={"subject": "A", "relation": "is_a", "object": "B", "status": "ASSERTED"},
            description="No-op transition 1",
            expected_effect="No-op",
            source="test",
        ),
        Transition(
            type=ADD_CLAIM,
            args={"subject": "A", "relation": "is_a", "object": "B", "status": "ASSERTED"},
            description="No-op transition 2",
            expected_effect="No-op",
            source="test",
        ),
    ]
    search = BeamSearch(
        proposer=StaticProposer(transitions),
        verifier_stack=VerifierStack.default(),
        final_state_evaluator=FinalStateEvaluator(),
        config=SearchConfig(max_depth=2, beam_width=4, max_nodes_expanded=10, enable_ts3=True),
    )

    result = search.run(state)

    assert result.terminal_status == "INCONCLUSIVE"
    assert result.best_node.depth == 0
    assert result.ts3_analysis is not None
    assert result.ts3_analysis.loop_detected is True
    assert result.ts3_analysis.reachable_by_depth.get(0, 0) >= 1
