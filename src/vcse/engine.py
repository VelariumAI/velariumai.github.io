"""Engine assembly helpers."""

from __future__ import annotations

from dataclasses import dataclass

from vcse.dsl.schema import CapabilityBundle
from vcse.index.retrieval import RetrievalConfig, SymbolicRetriever, filter_bundle_by_artifact_ids
from vcse.memory.constraints import Constraint
from vcse.memory.relations import RelationSchema
from vcse.memory.serialization import JSONDict
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.proposer.domain_specific import DomainSpecificProposer
from vcse.proposer.rule_based import RuleBasedProposer
from vcse.search.beam import BeamSearch, SearchConfig
from vcse.search.mcts import MCTSSearch
from vcse.transitions.state_transition import Transition
from vcse.verifier.final_state import FinalStateEvaluator
from vcse.verifier.stack import VerifierStack


@dataclass
class CompositeProposer:
    proposers: list[object]

    def propose(self, memory: WorldStateMemory, goal=None) -> list[Transition]:
        proposals: list[Transition] = []
        for proposer in self.proposers:
            proposals.extend(proposer.propose(memory, goal))
        return proposals


class CaseValidationError(ValueError):
    def __init__(self, error_type: str, reason: str) -> None:
        super().__init__(f"{error_type}: {reason}")
        self.error_type = error_type
        self.reason = reason


def filter_bundle_for_query(
    dsl_bundle: CapabilityBundle | None,
    query_text: str,
    relation_hints: set[str] | None = None,
    top_k_rules: int = 20,
    top_k_packs: int = 5,
) -> tuple[CapabilityBundle | None, dict[str, object] | None]:
    """Return a filtered capability bundle and retrieval stats for a query."""
    if dsl_bundle is None:
        return None, None

    retriever = SymbolicRetriever.from_bundles([dsl_bundle])
    retrieval = retriever.retrieve(
        query_text=query_text,
        relation_hints=relation_hints or set(),
        config=RetrievalConfig(top_k_rules=top_k_rules, top_k_packs=top_k_packs),
    )
    selected_ids = set(retrieval.selected_artifact_ids)
    filtered = filter_bundle_by_artifact_ids(dsl_bundle, selected_ids)
    stats = {
        "selected_packs": retrieval.selected_pack_ids,
        "selected_artifacts_count": len(retrieval.selected_artifact_ids),
        "top_scores": retrieval.top_scores,
        "filtered_out_count": retrieval.filtered_out_count,
        "candidate_count": retrieval.candidate_count,
        "index_stats": retriever.index.stats(),
    }
    return filtered, stats


def build_search(enable_ts3: bool = False, search_backend: str = "beam", dsl_bundle=None):
    proposer = CompositeProposer(
        [
            RuleBasedProposer(external_rules=getattr(dsl_bundle, "proposer_rules", None)),
            DomainSpecificProposer(),
        ]
    )
    verifier_stack = VerifierStack.default()
    final_evaluator = FinalStateEvaluator()
    config = SearchConfig(enable_ts3=enable_ts3, search_backend=search_backend)
    if search_backend == "beam":
        return BeamSearch(
            proposer=proposer,
            verifier_stack=verifier_stack,
            final_state_evaluator=final_evaluator,
            config=config,
        )
    if search_backend == "mcts":
        return MCTSSearch(
            proposer=proposer,
            verifier_stack=verifier_stack,
            final_state_evaluator=final_evaluator,
            config=config,
        )
    raise CaseValidationError(
        "INVALID_SEARCH_BACKEND",
        f"Unsupported search backend: {search_backend!r}. Allowed: beam, mcts",
    )


def state_from_case(data: JSONDict) -> WorldStateMemory:
    if not isinstance(data, dict):
        raise CaseValidationError("INVALID_CASE", "root must be an object")

    state = WorldStateMemory()
    state.add_relation_schema(RelationSchema(name="is_a", transitive=True))

    facts = data.get("facts", [])
    if not isinstance(facts, list):
        raise CaseValidationError("INVALID_CASE", "facts must be a list")
    for fact in facts:
        if not isinstance(fact, dict):
            raise CaseValidationError("INVALID_CASE", "each fact must be an object")
        try:
            relation = str(fact["relation"])
            if state.get_relation_schema(relation) is None:
                state.add_relation_schema(
                    RelationSchema(name=relation, transitive=(relation == "is_a"))
                )
            state.add_claim(
                fact["subject"],
                relation,
                fact["object"],
                TruthStatus(str(fact.get("status", TruthStatus.ASSERTED.value))),
            )
        except KeyError as exc:
            raise CaseValidationError("INVALID_CASE", f"fact missing key: {exc.args[0]}") from exc

    constraints = data.get("constraints", [])
    if not isinstance(constraints, list):
        raise CaseValidationError("INVALID_CASE", "constraints must be a list")
    for constraint in constraints:
        if not isinstance(constraint, dict):
            raise CaseValidationError("INVALID_CASE", "each constraint must be an object")
        try:
            state.add_constraint(
                Constraint(
                    kind=str(constraint.get("kind", "numeric")),
                    target=str(constraint["target"]),
                    operator=str(constraint["operator"]),
                    value=constraint["value"],
                    description=str(constraint.get("description", "")),
                )
            )
        except KeyError as exc:
            raise CaseValidationError(
                "INVALID_CASE", f"constraint missing key: {exc.args[0]}"
            ) from exc

    goal = data.get("goal")
    if goal is not None:
        if not isinstance(goal, dict):
            raise CaseValidationError("INVALID_CASE", "goal must be an object")
        try:
            state.add_goal(goal["subject"], goal["relation"], goal["object"])
        except KeyError as exc:
            raise CaseValidationError("INVALID_CASE", f"goal missing key: {exc.args[0]}") from exc

    return state
