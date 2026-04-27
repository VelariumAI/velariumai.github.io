"""VCSE command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from vcse.benchmark import BenchmarkCaseError, format_benchmark_text, run_benchmark
from vcse.engine import CaseValidationError, build_search, state_from_case
from vcse.ingestion.pipeline import IngestionError, ingest_file
from vcse.memory.constraints import Constraint
from vcse.memory.relations import RelationSchema
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.renderer.explanation import ExplanationRenderer


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


def run_logic_demo(enable_ts3: bool = False, search_backend: str = "beam") -> str:
    search = build_search(enable_ts3=enable_ts3, search_backend=search_backend)
    node = search.run(build_logic_demo_state())
    return ExplanationRenderer().render(node)


def run_demo(name: str, enable_ts3: bool = False, search_backend: str = "beam") -> str:
    builders = {
        "logic": build_logic_demo_state,
        "arithmetic": build_arithmetic_demo_state,
        "contradiction": build_contradiction_demo_state,
    }
    result = build_search(enable_ts3=enable_ts3, search_backend=search_backend).run(builders[name]())
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


def run_ask(
    text: str,
    mode: str = "explain",
    enable_ts3: bool = False,
    search_backend: str = "beam",
) -> str:
    """Handle vcse ask command."""
    from vcse.interaction.session import Session
    from vcse.interaction.response_modes import ResponseMode, render_response

    session = Session.create()
    session.mode = mode

    # Ingest user input
    frames = session.ingest(text)

    # Solve
    result = session.solve(enable_ts3=enable_ts3, search_backend=search_backend)

    # Handle different result types
    if result is None:
        return "No result."

    # Check if it's a clarification request
    if hasattr(result, "user_message"):
        return result.user_message

    # Render the result
    response_mode = ResponseMode(mode) if mode in ["simple", "explain", "debug", "strict"] else ResponseMode.EXPLAIN
    return render_response(result, response_mode, session.memory)


def run_normalize(text: str) -> str:
    """Handle vcse normalize command."""
    from vcse.interaction.normalizer import SemanticNormalizer

    normalizer = SemanticNormalizer()
    normalized = normalizer.normalize(text)

    lines = [
        f"original: {normalized.original_text}",
        f"normalized: {normalized.normalized_text}",
        f"confidence: {normalized.confidence}",
        f"tokens: {normalized.tokens}",
        "replacements:",
    ]

    if normalized.replacements_applied:
        for old, new in normalized.replacements_applied:
            lines.append(f"  - {old!r} → {new!r}")
    else:
        lines.append("  - none")

    if normalized.warnings:
        lines.append("warnings:")
        for warning in normalized.warnings:
            lines.append(f"  - {warning}")

    return "\n".join(lines)


def run_parse(text: str) -> str:
    """Handle vcse parse command."""
    from vcse.interaction.parser import PatternParser
    from vcse.interaction.normalizer import SemanticNormalizer

    normalizer = SemanticNormalizer()
    normalized = normalizer.normalize(text)
    parser = PatternParser()
    result = parser.parse(normalized.normalized_text)

    lines = [
        f"status: {result.status.value}",
        f"confidence: {result.confidence}",
        "frames:",
    ]

    for i, frame in enumerate(result.frames):
        lines.append(f"  [{i}] {type(frame).__name__}")
        for key in ["subject", "relation", "object", "target", "operator", "value"]:
            val = getattr(frame, key, None)
            if val is not None:
                lines.append(f"      {key}: {val!r}")

    if result.errors:
        lines.append("errors:")
        for error in result.errors:
            lines.append(f"  - {error}")

    if result.warnings:
        lines.append("warnings:")
        for warning in result.warnings:
            lines.append(f"  - {warning}")

    return "\n".join(lines)


def run_session() -> None:
    """Handle vcse session command - interactive REPL."""
    from vcse.interaction.session import Session
    from vcse.interaction.response_modes import ResponseMode, render_response

    session = Session.create()
    print("VCSE Interactive Session (type /help for commands)")
    print("-" * 40)

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue

        # Handle commands
        if user_input.startswith("/"):
            cmd = user_input.split()[0].lower()
            if cmd == "/exit":
                print("Goodbye.")
                break
            elif cmd == "/reset":
                session.reset()
                print("Session reset.")
                continue
            elif cmd == "/summary":
                print(session.summary())
                continue
            elif cmd == "/why":
                print(session.explain())
                continue
            elif cmd == "/debug":
                session.mode = "debug"
                print("Mode: debug")
                continue
            elif cmd == "/simple":
                session.mode = "simple"
                print("Mode: simple")
                continue
            elif cmd == "/explain":
                session.mode = "explain"
                print("Mode: explain")
                continue
            elif cmd == "/help":
                print("Commands:")
                print("  /reset   - Clear session memory")
                print("  /summary - Show session summary")
                print("  /why     - Explain last result")
                print("  /debug   - Set debug mode")
                print("  /simple  - Set simple mode")
                print("  /explain - Set explain mode")
                print("  /exit    - Exit session")
                continue
            else:
                print(f"Unknown command: {cmd}")
                continue

        # Process normal input
        frames = session.ingest(user_input)
        result = session.solve()

        if result is None:
            print("Noted.")
        elif hasattr(result, "user_message"):
            print(result.user_message)
        else:
            mode = ResponseMode(session.mode)
            print(render_response(result, mode, session.memory))


def run_reasonops_report(path: Path) -> str:
    """Handle vcse reasonops report command."""
    from vcse.reasonops.reports import generate_report
    return generate_report(path)


def run_ingest(
    path: Path,
    template_name: str | None = None,
    auto: bool = False,
    dry_run: bool = False,
    output_memory: Path | None = None,
    export_pack: Path | None = None,
) -> str:
    result = ingest_file(
        path=path,
        template_name=template_name,
        auto=auto,
        dry_run=dry_run,
        output_memory_path=output_memory,
        export_pack_path=export_pack,
    )
    imported = result.import_result
    lines = [
        f"status: {imported.status}",
        f"source_id: {imported.source_id}",
        f"frames_extracted: {imported.frames_extracted}",
        f"created_elements: {imported.created_elements}",
        "transitions_applied:",
    ]
    if imported.transitions_applied:
        for item in imported.transitions_applied:
            lines.append(f"  - {item}")
    else:
        lines.append("  - none")
    lines.append("contradictions_detected:")
    if imported.contradictions_detected:
        for item in imported.contradictions_detected:
            lines.append(f"  - {item}")
    else:
        lines.append("  - none")
    if imported.warnings:
        lines.append("warnings:")
        for warning in imported.warnings:
            lines.append(f"  - {warning}")
    if imported.errors:
        lines.append("errors:")
        for error in imported.errors:
            lines.append(f"  - {error}")
    if dry_run:
        lines.append("dry_run: true")
    if output_memory:
        lines.append(f"output_memory: {output_memory}")
    if export_pack:
        lines.append(f"export_pack: {export_pack}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="vcse")
    subparsers = parser.add_subparsers(dest="command")

    demo_parser = subparsers.add_parser("demo")
    demo_parser.add_argument("name", choices=["logic", "arithmetic", "contradiction"])
    demo_parser.add_argument("--ts3", action="store_true")
    demo_parser.add_argument("--search", default="beam")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("path")

    benchmark_parser = subparsers.add_parser("benchmark")
    benchmark_parser.add_argument("path")
    benchmark_parser.add_argument("--json", action="store_true", dest="json_output")
    benchmark_parser.add_argument("--allow-fail", action="store_true")
    benchmark_parser.add_argument("--ts3", action="store_true")
    benchmark_parser.add_argument("--search", default="beam")

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("path")
    ingest_parser.add_argument("--template", dest="template_name")
    ingest_parser.add_argument("--auto", action="store_true")
    ingest_parser.add_argument("--dry-run", action="store_true")
    ingest_parser.add_argument("--output-memory", type=Path)
    ingest_parser.add_argument("--export-pack", type=Path)

    # New interaction commands
    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("text", nargs="*", default=[])
    ask_parser.add_argument("--mode", default="explain")
    ask_parser.add_argument("--ts3", action="store_true")
    ask_parser.add_argument("--search", default="beam")

    normalize_parser = subparsers.add_parser("normalize")
    normalize_parser.add_argument("text", nargs="...", default="")

    parse_parser = subparsers.add_parser("parse")
    parse_parser.add_argument("text", nargs="...", default="")

    session_parser = subparsers.add_parser("session")

    reasonops_subparsers = subparsers.add_parser("reasonops").add_subparsers(
        dest="reasonops_command"
    )
    reasonops_report_parser = reasonops_subparsers.add_parser("report")
    reasonops_report_parser.add_argument("path", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            print(run_demo(args.name, enable_ts3=args.ts3, search_backend=args.search))
            return
        if args.command == "run":
            print(run_case_file(Path(args.path)))
            return
        if args.command == "benchmark":
            summary = run_benchmark(
                Path(args.path),
                enable_ts3=args.ts3,
                search_backend=args.search,
            )
            if args.json_output:
                print(json.dumps(summary, sort_keys=True))
            else:
                print(format_benchmark_text(summary))
            if summary["status"] != "BENCHMARK_COMPLETE" and not args.allow_fail:
                raise SystemExit(1)
            return
        if args.command == "ingest":
            print(
                run_ingest(
                    Path(args.path),
                    template_name=args.template_name,
                    auto=args.auto,
                    dry_run=args.dry_run,
                    output_memory=args.output_memory,
                    export_pack=args.export_pack,
                )
            )
            return
        if args.command == "ask":
            text = " ".join(args.text) if args.text else ""
            print(
                run_ask(
                    text,
                    args.mode,
                    enable_ts3=args.ts3,
                    search_backend=args.search,
                )
            )
            return
        if args.command == "normalize":
            text = " ".join(args.text) if args.text else ""
            print(run_normalize(text))
            return
        if args.command == "parse":
            text = " ".join(args.text) if args.text else ""
            print(run_parse(text))
            return
        if args.command == "session":
            run_session()
            return
        if args.command == "reasonops":
            if args.reasonops_command == "report":
                print(run_reasonops_report(args.path))
            else:
                reasonops_subparsers.print_help()
            return
    except (ValueError, BenchmarkCaseError, CaseValidationError, IngestionError) as exc:
        error_type = getattr(exc, "error_type", None)
        reason = getattr(exc, "reason", None)
        if error_type is None:
            error_type, _, reason = str(exc).partition(": ")
        print(render_error(error_type, reason or str(exc)), file=sys.stderr)
        raise SystemExit(2) from None

    parser.print_help()


if __name__ == "__main__":
    main()
