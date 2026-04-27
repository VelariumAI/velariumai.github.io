"""VCSE command line interface."""

from __future__ import annotations

import argparse

from vcse.memory.relations import RelationSchema
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.proposer.rule_based import RuleBasedProposer
from vcse.renderer.explanation import ExplanationRenderer
from vcse.search.beam import BeamSearch
from vcse.verifier.final_state import FinalStateEvaluator
from vcse.verifier.stack import VerifierStack


def build_logic_demo_state() -> WorldStateMemory:
    state = WorldStateMemory()
    state.add_relation_schema(RelationSchema(name="is_a", transitive=True))
    state.add_claim("Socrates", "is_a", "Man", TruthStatus.ASSERTED)
    state.add_claim("Man", "is_a", "Mortal", TruthStatus.ASSERTED)
    state.add_goal("Socrates", "is_a", "Mortal")
    return state


def run_logic_demo() -> str:
    search = BeamSearch(
        proposer=RuleBasedProposer(),
        verifier_stack=VerifierStack.default(),
        final_state_evaluator=FinalStateEvaluator(),
    )
    node = search.run(build_logic_demo_state())
    return ExplanationRenderer().render(node)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="vcse")
    subparsers = parser.add_subparsers(dest="command")

    demo_parser = subparsers.add_parser("demo")
    demo_parser.add_argument("name", choices=["logic"])

    args = parser.parse_args(argv)
    if args.command == "demo" and args.name == "logic":
        print(run_logic_demo())
        return

    parser.print_help()


if __name__ == "__main__":
    main()
