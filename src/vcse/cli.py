"""VCSE command line interface."""

from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

from vcse.benchmark import BenchmarkCaseError, format_benchmark_text, run_benchmark
from vcse.config import load_settings
from vcse.dsl import DSLCompiler, DSLLoader, DSLValidator, GLOBAL_REGISTRY
from vcse.dsl.errors import DSLError
from vcse.gauntlet import (
    GauntletEvaluator,
    GauntletRunConfig,
    GauntletRunner,
    GauntletError,
    compute_metrics,
    load_gauntlet_cases,
    render_gauntlet_json,
    render_gauntlet_summary,
)
from vcse.generation import GenerationError, VerifiedGenerator, spec_from_dict
from vcse.index import SymbolicRetriever
from vcse.engine import CaseValidationError, build_search, state_from_case
from vcse.ingestion.pipeline import IngestionError, ingest_file
from vcse.memory.constraints import Constraint
from vcse.memory.relations import RelationSchema
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.perf import profile_result, profile_run
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
    dsl_bundle=None,
    enable_index: bool = False,
    top_k_rules: int = 20,
    top_k_packs: int = 5,
    profile: bool = False,
) -> str:
    """Handle vcse ask command."""
    from vcse.interaction.session import Session
    from vcse.interaction.response_modes import ResponseMode, render_response

    def _run() -> str:
        session = Session.create(
            dsl_bundle=dsl_bundle,
            enable_indexing=enable_index,
            top_k_rules=top_k_rules,
            top_k_packs=top_k_packs,
        )
        session.mode = mode

        session.ingest(text)
        result = session.solve(enable_ts3=enable_ts3, search_backend=search_backend)

        if result is None:
            return "No result."

        if hasattr(result, "user_message"):
            return result.user_message

        response_mode = ResponseMode(mode) if mode in ["simple", "explain", "debug", "strict"] else ResponseMode.EXPLAIN
        return render_response(
            result,
            response_mode,
            session.memory,
            renderer_templates=_renderer_templates_from_bundle(
                session.history[-1].runtime_bundle if session.history else dsl_bundle
            ),
        )

    if not profile:
        return _run()

    with profile_run() as (trace, holder):
        output = _run()
    total_seconds = holder[0] if holder else 0.0
    result = profile_result(trace, total_seconds)
    lines = [output, "profile:", f"  total_seconds: {result.total_seconds:.6f}"]
    if result.stage_durations:
        lines.append("  stages:")
        for name, duration in result.stage_durations.items():
            lines.append(f"    {name}: {duration:.6f}")
    if result.counters:
        lines.append("  counters:")
        for name, count in result.counters.items():
            lines.append(f"    {name}: {count}")
    return "\n".join(lines)


def _renderer_templates_from_bundle(dsl_bundle) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if dsl_bundle is None:
        return mapping
    for rule in getattr(dsl_bundle, "renderer_templates", []):
        relation = str(getattr(rule, "relation", "")).strip()
        template = str(getattr(rule, "template", "")).strip()
        if relation and template:
            mapping[relation] = template
    return mapping


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
    dsl_bundle=None,
) -> str:
    result = ingest_file(
        path=path,
        template_name=template_name,
        auto=auto,
        dry_run=dry_run,
        output_memory_path=output_memory,
        export_pack_path=export_pack,
        dsl_bundle=dsl_bundle,
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


def run_generate(
    spec_path: Path,
    mode: str = "strict",
    enable_index: bool = False,
    top_k_rules: int = 20,
    dsl_bundle=None,
    output_path: Path | None = None,
    profile: bool = False,
) -> str:
    def _run() -> str:
        try:
            payload = json.loads(spec_path.read_text())
        except json.JSONDecodeError as exc:
            raise GenerationError("MALFORMED_SPEC", exc.msg) from exc
        except OSError as exc:
            raise GenerationError("FILE_ERROR", str(exc)) from exc
        if not isinstance(payload, dict):
            raise GenerationError("INVALID_SPEC", "spec root must be an object")
        if mode:
            payload["mode"] = mode

        spec = spec_from_dict(payload)
        memory = WorldStateMemory()
        for fact in payload.get("memory_claims", []):
            if not isinstance(fact, dict):
                continue
            subject = str(fact.get("subject", "")).strip()
            relation = str(fact.get("relation", "")).strip()
            obj = str(fact.get("object", "")).strip()
            if subject and relation and obj:
                if memory.get_relation_schema(relation) is None:
                    memory.add_relation_schema(RelationSchema(name=relation, transitive=(relation == "is_a")))
                memory.add_claim(subject, relation, obj, TruthStatus.ASSERTED)

        result = VerifiedGenerator().generate(
            spec=spec,
            memory=memory,
            bundle=dsl_bundle,
            enable_index=enable_index,
            top_k_rules=top_k_rules,
        )

        output = {
            "status": result.status,
            "clarification_request": result.clarification_request,
            "evaluation_reasons": result.evaluation_reasons,
            "search_stats": result.search_stats,
            "template_stats": result.template_stats,
            "best_artifact": result.best_artifact.to_dict() if result.best_artifact else None,
            "candidates": [item.to_dict() for item in result.candidates] if spec.mode == "debug" else None,
        }

        if output_path is not None:
            output_path.write_text(json.dumps(output, indent=2, sort_keys=True))

        lines = [f"status: {result.status}"]
        if result.clarification_request:
            lines.append(f"clarification_request: {result.clarification_request}")
        if result.best_artifact is not None:
            lines.append(f"artifact_type: {result.best_artifact.artifact_type}")
            lines.append(f"template_id: {result.best_artifact.template_id}")
            lines.append(f"artifact_status: {result.best_artifact.status}")
            lines.append("artifact_content:")
            lines.append(json.dumps(result.best_artifact.content, sort_keys=True))
            lines.append("provenance:")
            lines.append(json.dumps(result.best_artifact.provenance, sort_keys=True))
        if spec.mode == "debug":
            lines.append("template_stats:")
            lines.append(json.dumps(result.template_stats, sort_keys=True))
        if output_path is not None:
            lines.append(f"output: {output_path}")
        return "\n".join(lines)

    if not profile:
        return _run()

    with profile_run() as (trace, holder):
        output = _run()
    total_seconds = holder[0] if holder else 0.0
    result = profile_result(trace, total_seconds)
    lines = [output, "profile:", f"  total_seconds: {result.total_seconds:.6f}"]
    if result.stage_durations:
        lines.append("  stages:")
        for name, duration in result.stage_durations.items():
            lines.append(f"    {name}: {duration:.6f}")
    if result.counters:
        lines.append("  counters:")
        for name, count in result.counters.items():
            lines.append(f"    {name}: {count}")
    return "\n".join(lines)


def run_gauntlet(
    target_path: Path,
    search_backend: str = "beam",
    enable_ts3: bool = False,
    enable_index: bool = False,
    top_k_rules: int = 20,
    top_k_packs: int = 5,
    dsl_bundle=None,
    json_output: bool = False,
    debug: bool = False,
) -> tuple[str, int]:
    cases = load_gauntlet_cases(target_path)
    results = GauntletRunner().run(
        cases,
        GauntletRunConfig(
            search_backend=search_backend,
            enable_ts3=enable_ts3,
            enable_index=enable_index,
            top_k_rules=top_k_rules,
            top_k_packs=top_k_packs,
            dsl_bundle=dsl_bundle,
            debug=debug,
        ),
    )
    evaluator = GauntletEvaluator()
    evaluations = [evaluator.evaluate(case, result) for case, result in zip(cases, results)]
    metrics = compute_metrics(cases, results, evaluations)

    if json_output:
        text = render_gauntlet_json(metrics, cases, results, evaluations, debug=debug)
    else:
        text = render_gauntlet_summary(metrics, cases, results, evaluations)

    exit_code = 0
    if metrics.critical_failures > 0 or metrics.false_verified_count > 0:
        exit_code = 2
    elif metrics.failed > 0:
        exit_code = 1
    return text, exit_code


def run_serve(host: str, port: int, settings=None) -> None:
    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover - dependency error path
        raise ValueError("MISSING_DEPENDENCY: uvicorn is required for vcse serve") from exc
    from vcse.api.server import create_app

    print(f"Starting VCSE API server {host}:{port} (version {__import__('vcse').__version__})")
    log_level = getattr(settings, "log_level", "INFO").lower() if settings is not None else "info"
    uvicorn.run(create_app(settings=settings), host=host, port=port, log_level=log_level)


def run_profile(argv: list[str], settings) -> tuple[str, int]:
    """Execute a VCSE command and append profiling output."""
    buffer = io.StringIO()
    exit_code = 0
    with profile_run() as (trace, holder):
        with redirect_stdout(buffer):
            try:
                main(argv)
            except SystemExit as exc:
                exit_code = exc.code if isinstance(exc.code, int) else 1
    total_seconds = holder[0] if holder else 0.0
    profile = profile_result(trace, total_seconds)
    lines = [buffer.getvalue().rstrip()]
    lines.append("profile:")
    lines.append(f"  total_seconds: {profile.total_seconds:.6f}")
    if profile.stage_durations:
        lines.append("  stages:")
        for name, duration in profile.stage_durations.items():
            lines.append(f"    {name}: {duration:.6f}")
    if profile.counters:
        lines.append("  counters:")
        for name, count in profile.counters.items():
            lines.append(f"    {name}: {count}")
    return "\n".join(line for line in lines if line), exit_code


def load_dsl_bundle(path: str | Path):
    document = DSLLoader.load(path)
    validation = DSLValidator.validate(document)
    if not validation.passed:
        raise DSLError("INVALID_DSL", "; ".join(validation.errors))
    return DSLCompiler.compile(document)


def validate_index_args(top_k_rules: int, top_k_packs: int) -> None:
    if top_k_rules < 1:
        raise ValueError("INVALID_INDEX_CONFIG: --top-k must be >= 1")
    if top_k_packs < 1:
        raise ValueError("INVALID_INDEX_CONFIG: --top-k-packs must be >= 1")


def _bundles_for_index(dsl_path: str | None):
    bundles = []
    if dsl_path:
        bundles.append(load_dsl_bundle(dsl_path))
    for name in GLOBAL_REGISTRY.list_bundles():
        bundle = GLOBAL_REGISTRY.bundles.get(name)
        if bundle is not None:
            bundles.append(bundle)
    return bundles


def run_index_build(dsl_path: str | None = None) -> str:
    bundles = _bundles_for_index(dsl_path)
    retriever = SymbolicRetriever.from_bundles(bundles)
    stats = retriever.index.stats()
    lines = [
        "status: INDEX_BUILT",
        f"bundles: {len(bundles)}",
        f"artifact_count: {stats['artifact_count']}",
        f"token_count: {stats['token_count']}",
        f"pack_count: {stats['pack_count']}",
        f"average_doc_length: {stats['average_doc_length']}",
    ]
    return "\n".join(lines)


def run_index_stats(dsl_path: str | None = None) -> str:
    bundles = _bundles_for_index(dsl_path)
    retriever = SymbolicRetriever.from_bundles(bundles)
    stats = retriever.index.stats()
    lines = [
        "status: INDEX_STATS",
        f"bundles: {len(bundles)}",
        f"artifact_count: {stats['artifact_count']}",
        f"token_count: {stats['token_count']}",
        f"pack_count: {stats['pack_count']}",
        f"average_doc_length: {stats['average_doc_length']}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="vcse")
    parser.add_argument("--config")
    subparsers = parser.add_subparsers(dest="command")

    demo_parser = subparsers.add_parser("demo")
    demo_parser.add_argument("name", choices=["logic", "arithmetic", "contradiction"])
    demo_parser.add_argument("--ts3", action="store_true")
    demo_parser.add_argument("--search")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("path")

    benchmark_parser = subparsers.add_parser("benchmark")
    benchmark_parser.add_argument("path")
    benchmark_parser.add_argument("--json", action="store_true", dest="json_output")
    benchmark_parser.add_argument("--allow-fail", action="store_true")
    benchmark_parser.add_argument("--ts3", action="store_true")
    benchmark_parser.add_argument("--search")
    benchmark_parser.add_argument("--dsl")
    benchmark_parser.add_argument("--index", action="store_true")
    benchmark_parser.add_argument("--top-k", type=int, dest="top_k_rules")
    benchmark_parser.add_argument("--top-k-packs", type=int, dest="top_k_packs")

    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("path")
    ingest_parser.add_argument("--template", dest="template_name")
    ingest_parser.add_argument("--auto", action="store_true")
    ingest_parser.add_argument("--dry-run", action="store_true")
    ingest_parser.add_argument("--output-memory", type=Path)
    ingest_parser.add_argument("--export-pack", type=Path)
    ingest_parser.add_argument("--dsl")

    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("spec")
    generate_parser.add_argument("--debug", action="store_true")
    generate_parser.add_argument("--index", action="store_true")
    generate_parser.add_argument("--dsl")
    generate_parser.add_argument("--top-k", type=int, dest="top_k_rules")
    generate_parser.add_argument("--output", type=Path)
    generate_parser.add_argument("--profile", action="store_true")

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host")
    serve_parser.add_argument("--port", type=int)
    serve_parser.add_argument("--profile", action="store_true")

    gauntlet_parser = subparsers.add_parser("gauntlet")
    gauntlet_parser.add_argument("path")
    gauntlet_parser.add_argument("--json", action="store_true", dest="json_output")
    gauntlet_parser.add_argument("--debug", action="store_true")
    gauntlet_parser.add_argument("--search")
    gauntlet_parser.add_argument("--ts3", action="store_true")
    gauntlet_parser.add_argument("--index", action="store_true")
    gauntlet_parser.add_argument("--top-k", type=int, dest="top_k_rules")
    gauntlet_parser.add_argument("--top-k-packs", type=int, dest="top_k_packs")
    gauntlet_parser.add_argument("--dsl")
    gauntlet_parser.add_argument("--profile", action="store_true")

    # New interaction commands
    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("text", nargs="*", default=[])
    ask_parser.add_argument("--mode", default="explain")
    ask_parser.add_argument("--ts3", action="store_true")
    ask_parser.add_argument("--search")
    ask_parser.add_argument("--dsl")
    ask_parser.add_argument("--index", action="store_true")
    ask_parser.add_argument("--top-k", type=int, dest="top_k_rules")
    ask_parser.add_argument("--top-k-packs", type=int, dest="top_k_packs")
    ask_parser.add_argument("--profile", action="store_true")

    normalize_parser = subparsers.add_parser("normalize")
    normalize_parser.add_argument("text", nargs="*", default=[])

    parse_parser = subparsers.add_parser("parse")
    parse_parser.add_argument("text", nargs="*", default=[])

    session_parser = subparsers.add_parser("session")

    profile_parser = subparsers.add_parser("profile")
    profile_parser.add_argument("argv", nargs=argparse.REMAINDER)

    reasonops_subparsers = subparsers.add_parser("reasonops").add_subparsers(
        dest="reasonops_command"
    )
    reasonops_report_parser = reasonops_subparsers.add_parser("report")
    reasonops_report_parser.add_argument("path", type=Path)

    dsl_parser = subparsers.add_parser("dsl")
    dsl_subparsers = dsl_parser.add_subparsers(dest="dsl_command")
    dsl_validate_parser = dsl_subparsers.add_parser("validate")
    dsl_validate_parser.add_argument("path")
    dsl_compile_parser = dsl_subparsers.add_parser("compile")
    dsl_compile_parser.add_argument("path")
    dsl_load_parser = dsl_subparsers.add_parser("load")
    dsl_load_parser.add_argument("path")
    dsl_subparsers.add_parser("list")

    index_parser = subparsers.add_parser("index")
    index_subparsers = index_parser.add_subparsers(dest="index_command")
    index_build_parser = index_subparsers.add_parser("build")
    index_build_parser.add_argument("--dsl")
    index_stats_parser = index_subparsers.add_parser("stats")
    index_stats_parser.add_argument("--dsl")

    try:
        args = parser.parse_args(argv)
        settings = load_settings(args.config)
        if args.command == "demo":
            print(run_demo(args.name, enable_ts3=args.ts3, search_backend=args.search or settings.search_backend))
            return
        if args.command == "run":
            print(run_case_file(Path(args.path)))
            return
        if args.command == "benchmark":
            top_k_rules = args.top_k_rules if args.top_k_rules is not None else settings.top_k_rules
            top_k_packs = args.top_k_packs if args.top_k_packs is not None else settings.top_k_packs
            validate_index_args(top_k_rules, top_k_packs)
            dsl_bundle = load_dsl_bundle(args.dsl) if args.dsl else None
            summary = run_benchmark(
                Path(args.path),
                enable_ts3=args.ts3,
                search_backend=args.search or settings.search_backend,
                dsl_bundle=dsl_bundle,
                enable_index=args.index,
                top_k_rules=top_k_rules,
                top_k_packs=top_k_packs,
            )
            if args.json_output:
                print(json.dumps(summary, sort_keys=True))
            else:
                print(format_benchmark_text(summary))
            if summary["status"] != "BENCHMARK_COMPLETE" and not args.allow_fail:
                raise SystemExit(1)
            return
        if args.command == "ingest":
            dsl_bundle = load_dsl_bundle(args.dsl) if args.dsl else None
            print(
                run_ingest(
                    Path(args.path),
                    template_name=args.template_name,
                    auto=args.auto,
                    dry_run=args.dry_run,
                    output_memory=args.output_memory,
                    export_pack=args.export_pack,
                    dsl_bundle=dsl_bundle,
                )
            )
            return
        if args.command == "generate":
            top_k_rules = args.top_k_rules if args.top_k_rules is not None else settings.top_k_rules
            validate_index_args(top_k_rules, 1)
            dsl_bundle = load_dsl_bundle(args.dsl) if args.dsl else None
            mode = "debug" if args.debug else "strict"
            print(
                run_generate(
                    Path(args.spec),
                    mode=mode,
                    enable_index=args.index,
                    top_k_rules=top_k_rules,
                    dsl_bundle=dsl_bundle,
                    output_path=args.output,
                    profile=args.profile,
                )
            )
            return
        if args.command == "serve":
            host = args.host or settings.api_host
            port = args.port if args.port is not None else settings.api_port
            run_serve(host, port, settings=settings)
            return
        if args.command == "gauntlet":
            top_k_rules = args.top_k_rules if args.top_k_rules is not None else settings.top_k_rules
            top_k_packs = args.top_k_packs if args.top_k_packs is not None else settings.top_k_packs
            validate_index_args(top_k_rules, top_k_packs)
            dsl_bundle = load_dsl_bundle(args.dsl) if args.dsl else None
            text, exit_code = run_gauntlet(
                Path(args.path),
                search_backend=args.search or settings.search_backend,
                enable_ts3=args.ts3,
                enable_index=args.index,
                top_k_rules=top_k_rules,
                top_k_packs=top_k_packs,
                dsl_bundle=dsl_bundle,
                json_output=args.json_output,
                debug=args.debug,
            )
            print(text)
            if exit_code != 0:
                raise SystemExit(exit_code)
            return
        if args.command == "ask":
            top_k_rules = args.top_k_rules if args.top_k_rules is not None else settings.top_k_rules
            top_k_packs = args.top_k_packs if args.top_k_packs is not None else settings.top_k_packs
            validate_index_args(top_k_rules, top_k_packs)
            dsl_bundle = load_dsl_bundle(args.dsl) if args.dsl else None
            text = " ".join(args.text) if args.text else ""
            print(
                run_ask(
                    text,
                    args.mode,
                    enable_ts3=args.ts3,
                    search_backend=args.search or settings.search_backend,
                    dsl_bundle=dsl_bundle,
                    enable_index=args.index,
                    top_k_rules=top_k_rules,
                    top_k_packs=top_k_packs,
                    profile=args.profile,
                )
            )
            return
        if args.command == "index":
            if args.index_command == "build":
                print(run_index_build(args.dsl))
                return
            if args.index_command == "stats":
                print(run_index_stats(args.dsl))
                return
        if args.command == "dsl":
            if args.dsl_command == "validate":
                document = DSLLoader.load(args.path)
                validation = DSLValidator.validate(document)
                if validation.passed:
                    print("status: VALID")
                    print(f"artifact_count: {validation.artifact_count}")
                    print(f"enabled_count: {validation.enabled_count}")
                else:
                    print("status: INVALID")
                    print("errors:")
                    for error in validation.errors:
                        print(f"  - {error}")
                    raise SystemExit(2)
                return
            if args.dsl_command == "compile":
                bundle = load_dsl_bundle(args.path)
                print("status: COMPILED")
                print(f"name: {bundle.name}")
                print(f"version: {bundle.version}")
                print(f"synonyms: {len(bundle.synonyms)}")
                print(f"parser_patterns: {len(bundle.parser_patterns)}")
                print(f"relation_schemas: {len(bundle.relation_schemas)}")
                print(f"ingestion_templates: {len(bundle.ingestion_templates)}")
                print(f"generation_templates: {len(bundle.generation_templates)}")
                print(f"proposer_rules: {len(bundle.proposer_rules)}")
                print(f"renderer_templates: {len(bundle.renderer_templates)}")
                print(f"clarification_rules: {len(bundle.clarification_rules)}")
                return
            if args.dsl_command == "load":
                bundle = load_dsl_bundle(args.path)
                GLOBAL_REGISTRY.register_bundle(bundle)
                print("status: LOADED")
                print(f"name: {bundle.name}")
                return
            if args.dsl_command == "list":
                print("bundles:")
                names = GLOBAL_REGISTRY.list_bundles()
                if names:
                    for name in names:
                        print(f"  - {name}")
                else:
                    print("  - none")
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
        if args.command == "profile":
            if not args.argv:
                raise SystemExit("profile requires a nested command")
            profile_argv = list(args.argv)
            if args.config:
                profile_argv = ["--config", args.config, *profile_argv]
            profile_text, exit_code = run_profile(profile_argv, settings)
            print(profile_text)
            if exit_code != 0:
                raise SystemExit(exit_code)
            return
        if args.command == "reasonops":
            if args.reasonops_command == "report":
                print(run_reasonops_report(args.path))
            else:
                reasonops_subparsers.print_help()
            return
    except (
        ValueError,
        BenchmarkCaseError,
        CaseValidationError,
        IngestionError,
        DSLError,
        GenerationError,
        GauntletError,
    ) as exc:
        error_type = getattr(exc, "error_type", None)
        reason = getattr(exc, "reason", None)
        if error_type is None:
            error_type, _, reason = str(exc).partition(": ")
        print(render_error(error_type, reason or str(exc)), file=sys.stderr)
        raise SystemExit(2) from None

    parser.print_help()


if __name__ == "__main__":
    main()
