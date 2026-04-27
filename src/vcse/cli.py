"""VCSE command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from vcse.memory.constraints import Constraint
from vcse.memory.relations import RelationSchema
from vcse.memory.serialization import JSONDict
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.proposer.domain_specific import DomainSpecificProposer
from vcse.proposer.rule_based import RuleBasedProposer
from vcse.renderer.explanation import ExplanationRenderer
from vcse.search.beam import BeamSearch
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


def build_logic_demo_state() -> WorldStateMemory:
    state = WorldStateMemory()
    state.add_relation_schema(RelationSchema(name="is_a", transitive=True))
    state.add_claim("Socrates", "is_a", "Man", TruthStatus.ASSERTED)
    state.add_claim("Man", "is_a", "Mortal", TruthStatus.ASSERTED)
    state.add_goal("Socrates", "is_a", "Mortal")
    return state


def build_arithmetic_demo_state() -> WorldStateMemory:
    state = WorldStateMemory()
    state.add_claim("x", "equals", "5", TruthStatus.ASSERTED)
    state.add_constraint(Constraint(kind="numeric", target="x", operator=">", value=0))
    state.add_goal("x", "satisfies", "constraints")
    return state


def build_contradiction_demo_state() -> WorldStateMemory:
    state = WorldStateMemory()
    state.add_claim("x", "equals", "3", TruthStatus.ASSERTED)
    state.add_claim("x", "equals", "4", TruthStatus.ASSERTED)
    return state


def build_search() -> BeamSearch:
    return BeamSearch(
        proposer=CompositeProposer([RuleBasedProposer(), DomainSpecificProposer()]),
        verifier_stack=VerifierStack.default(),
        final_state_evaluator=FinalStateEvaluator(),
    )


def run_logic_demo() -> str:
    search = build_search()
    node = search.run(build_logic_demo_state())
    return ExplanationRenderer().render(node)


def run_demo(name: str) -> str:
    builders = {
        "logic": build_logic_demo_state,
        "arithmetic": build_arithmetic_demo_state,
        "contradiction": build_contradiction_demo_state,
    }
    result = build_search().run(builders[name]())
    return ExplanationRenderer().render(result)


def load_case_file(path: Path) -> WorldStateMemory:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"MALFORMED_JSON: {exc.msg}") from exc
    except OSError as exc:
        raise ValueError(f"FILE_ERROR: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("INVALID_CASE: root must be an object")
    return state_from_case(data)


def state_from_case(data: JSONDict) -> WorldStateMemory:
    state = WorldStateMemory()
    state.add_relation_schema(RelationSchema(name="is_a", transitive=True))

    facts = data.get("facts", [])
    if not isinstance(facts, list):
        raise ValueError("INVALID_CASE: facts must be a list")
    for fact in facts:
        if not isinstance(fact, dict):
            raise ValueError("INVALID_CASE: each fact must be an object")
        state.add_claim(
            fact["subject"],
            fact["relation"],
            fact["object"],
            TruthStatus(str(fact.get("status", TruthStatus.ASSERTED.value))),
        )

    constraints = data.get("constraints", [])
    if not isinstance(constraints, list):
        raise ValueError("INVALID_CASE: constraints must be a list")
    for constraint in constraints:
        if not isinstance(constraint, dict):
            raise ValueError("INVALID_CASE: each constraint must be an object")
        state.add_constraint(
            Constraint(
                kind=str(constraint.get("kind", "numeric")),
                target=str(constraint["target"]),
                operator=str(constraint["operator"]),
                value=constraint["value"],
                description=str(constraint.get("description", "")),
            )
        )

    goal = data.get("goal")
    if goal is not None:
        if not isinstance(goal, dict):
            raise ValueError("INVALID_CASE: goal must be an object")
        state.add_goal(goal["subject"], goal["relation"], goal["object"])

    return state


def render_error(error_type: str, reason: str) -> str:
    return "\n".join(
        [
            "status: ERROR",
            f"error_type: {error_type}",
            "reasons:",
            f"  - {reason}",
        ]
    )


def run_case_file(path: Path) -> str:
    state = load_case_file(path)
    result = build_search().run(state)
    return ExplanationRenderer().render(result)


def run_benchmark_file(path: Path) -> str:
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        raise ValueError(f"FILE_ERROR: {exc}") from exc

    total = 0
    correct = 0
    verified = 0
    contradictory = 0
    inconclusive = 0
    unsatisfiable = 0

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"MALFORMED_JSON: line {line_number}: {exc.msg}") from exc
        if not isinstance(case, dict):
            raise ValueError(f"INVALID_CASE: line {line_number} root must be an object")

        result = build_search().run(state_from_case(case))
        status = result.evaluation.status.value
        expected = case.get("expected_status")
        total += 1
        correct += int(expected == status)
        verified += int(status == "VERIFIED")
        contradictory += int(status == "CONTRADICTORY")
        inconclusive += int(status == "INCONCLUSIVE")
        unsatisfiable += int(status == "UNSATISFIABLE")

    accuracy = correct / total if total else 0.0
    return "\n".join(
        [
            "status: BENCHMARK_COMPLETE",
            f"cases: {total}",
            f"accuracy: {accuracy}",
            f"verified: {verified}",
            f"contradictory: {contradictory}",
            f"inconclusive: {inconclusive}",
            f"unsatisfiable: {unsatisfiable}",
        ]
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="vcse")
    subparsers = parser.add_subparsers(dest="command")

    demo_parser = subparsers.add_parser("demo")
    demo_parser.add_argument("name", choices=["logic", "arithmetic", "contradiction"])

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("path")

    benchmark_parser = subparsers.add_parser("benchmark")
    benchmark_parser.add_argument("path")

    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            print(run_demo(args.name))
            return
        if args.command == "run":
            print(run_case_file(Path(args.path)))
            return
        if args.command == "benchmark":
            print(run_benchmark_file(Path(args.path)))
            return
    except ValueError as exc:
        error_type, _, reason = str(exc).partition(": ")
        print(render_error(error_type, reason or str(exc)), file=sys.stderr)
        raise SystemExit(2) from None

    parser.print_help()


if __name__ == "__main__":
    main()
