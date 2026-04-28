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
from vcse.knowledge import (
    KnowledgePipeline,
    Source,
)
from vcse.knowledge.errors import KnowledgeError
from vcse.memory.constraints import Constraint
from vcse.memory.relations import RelationSchema
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.packs import (
    PackActivator,
    PackAuditor,
    PackError,
    PackInstaller,
    PackRegistry,
    PackValidator,
)
from vcse.perf import profile_result, profile_run
from vcse.ledger import LedgerError, LedgerStore, build_integrity, export_ledger, verify_ledger, verify_pack_ledger
from vcse.renderer.explanation import ExplanationRenderer
from vcse.trust import TrustError, TrustPromoter, load_policy
from vcse.compression.metrics import compute_metrics as compression_compute_metrics
from vcse.compression import (
    optimize_pack,
    save_compressed,
    load_compressed,
    verify_integrity,
    format_metrics,
    CompressionError,
)


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
    preload_claims: list[dict[str, str]] | None = None,
    preload_constraints: list[Constraint] | None = None,
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
        _apply_preloaded_knowledge(session.memory, preload_claims or [], preload_constraints or [])

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


def _apply_preloaded_knowledge(
    memory: WorldStateMemory,
    claims: list[dict[str, str]],
    constraints: list[Constraint],
) -> None:
    for claim in claims:
        subject = str(claim.get("subject", "")).strip()
        relation = str(claim.get("relation", "")).strip()
        obj = str(claim.get("object", "")).strip()
        if not subject or not relation or not obj:
            continue
        if memory.get_relation_schema(relation) is None:
            memory.add_relation_schema(RelationSchema(name=relation, transitive=(relation == "is_a")))
        memory.add_claim(subject, relation, obj, TruthStatus.ASSERTED, source="pack")
    for constraint in constraints:
        memory.add_constraint(constraint)


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
    preload_claims: list[dict[str, str]] | None = None,
    preload_constraints: list[Constraint] | None = None,
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
        _apply_preloaded_knowledge(memory, preload_claims or [], preload_constraints or [])
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


def run_knowledge_validate(path: Path) -> str:
    result = KnowledgePipeline().validate_source(Source.from_path(path))
    lines = [
        f"status: {result.status}",
        f"claims_extracted: {result.metrics.claims_extracted}",
        f"valid_claims: {result.metrics.valid_claims}",
        f"invalid_claims_rejected: {result.metrics.invalid_claims_rejected}",
        f"conflicts_detected: {result.metrics.conflicts_detected}",
    ]
    if result.errors:
        lines.append("errors:")
        for error in result.errors:
            lines.append(f"  - {error}")
    if result.warnings:
        lines.append("warnings:")
        for warning in result.warnings:
            lines.append(f"  - {warning}")
    return "\n".join(lines)


def run_knowledge_build(path: Path, pack_name: str, domain: str = "general") -> str:
    result = KnowledgePipeline().build(
        Source.from_path(path),
        pack_id=pack_name,
        domain=domain,
        output_path=pack_name,
        write=True,
    )
    lines = [
        f"status: BUILT",
        f"pack: {pack_name}",
        f"output: {result.output_path}",
        f"claims: {len(result.pack.claims)}",
        f"invalid_claims_rejected: {result.metrics.invalid_claims_rejected}",
        f"conflicts_detected: {result.metrics.conflicts_detected}",
    ]
    if result.errors:
        lines.append("errors:")
        for error in result.errors:
            lines.append(f"  - {error}")
    return "\n".join(lines)


def run_knowledge_stats(path: Path) -> str:
    from vcse.knowledge.pack_builder import pack_stats
    stats = pack_stats(path)
    return "\n".join(
        [
            "status: PACK_STATS",
            f"pack: {stats['id']}",
            f"version: {stats['version']}",
            f"domain: {stats['domain']}",
            f"claims: {stats['claim_count']}",
            f"constraints: {stats['constraint_count']}",
            f"conflicts: {stats['conflict_count']}",
        ]
    )


def run_pack_list(json_output: bool = False) -> str:
    registry = PackRegistry()
    items = registry.list()
    if json_output:
        return json.dumps({"packs": items}, sort_keys=True)
    lines = ["packs:"]
    if not items:
        lines.append("  - none")
    else:
        for item in items:
            lines.append(
                f"  - {item.get('id')}@{item.get('version')} domain={item.get('domain')} path={item.get('install_path')}"
            )
    return "\n".join(lines)


def run_pack_validate(path: Path, json_output: bool = False) -> str:
    validation = PackValidator().validate(path)
    payload = {
        "passed": validation.passed,
        "errors": validation.errors,
        "warnings": validation.warnings,
        "artifact_count": validation.artifact_count,
        "benchmark_count": validation.benchmark_count,
        "gauntlet_count": validation.gauntlet_count,
        "manifest": validation.manifest.to_dict() if validation.manifest else None,
    }
    if json_output:
        return json.dumps(payload, sort_keys=True)
    lines = [
        f"status: {'VALID' if validation.passed else 'INVALID'}",
        f"artifact_count: {validation.artifact_count}",
        f"benchmark_count: {validation.benchmark_count}",
        f"gauntlet_count: {validation.gauntlet_count}",
    ]
    if validation.errors:
        lines.append("errors:")
        for error in validation.errors:
            lines.append(f"  - {error}")
    if validation.warnings:
        lines.append("warnings:")
        for warning in validation.warnings:
            lines.append(f"  - {warning}")
    return "\n".join(lines)


def run_pack_install(path: Path, force: bool = False, json_output: bool = False) -> str:
    result = PackInstaller().install(path, force=force)
    payload = {
        "status": "INSTALLED",
        "pack_id": result.pack_id,
        "version": result.version,
        "install_path": str(result.install_path),
    }
    if json_output:
        return json.dumps(payload, sort_keys=True)
    lines = [
        "status: INSTALLED",
        f"pack: {result.pack_id}@{result.version}",
        f"path: {result.install_path}",
    ]
    if result.validation.warnings:
        lines.append("warnings:")
        for warning in result.validation.warnings:
            lines.append(f"  - {warning}")
    return "\n".join(lines)


def run_pack_uninstall(pack_id: str, version: str | None = None, json_output: bool = False) -> str:
    removed = PackInstaller().uninstall(pack_id, version)
    payload = {"status": "UNINSTALLED", "removed": removed}
    if json_output:
        return json.dumps(payload, sort_keys=True)
    return "\n".join(["status: UNINSTALLED", f"removed: {removed}"])


def run_pack_info(pack_id: str, version: str | None = None, json_output: bool = False) -> str:
    record = PackInstaller().get_pack(pack_id, version)
    if json_output:
        return json.dumps(record, sort_keys=True)
    return "\n".join(
        [
            "status: PACK_INFO",
            f"id: {record.get('id')}",
            f"name: {record.get('name')}",
            f"version: {record.get('version')}",
            f"domain: {record.get('domain')}",
            f"install_path: {record.get('install_path')}",
        ]
    )


def run_pack_audit(target: str, json_output: bool = False) -> str:
    report = PackAuditor().audit(target)
    payload = report.to_dict()
    if json_output:
        return json.dumps(payload, sort_keys=True)
    return "\n".join(
        [
            "status: PACK_AUDIT",
            f"claims_count: {report.claims_count}",
            f"constraints_count: {report.constraints_count}",
            f"templates_count: {report.templates_count}",
            f"dsl_artifacts_count: {report.dsl_artifacts_count}",
            f"provenance_coverage_percent: {report.provenance_coverage_percent}",
            f"contradiction_count: {report.contradiction_count}",
            f"benchmark_status: {report.benchmark_status}",
            f"gauntlet_status: {report.gauntlet_status}",
            f"dependency_status: {report.dependency_status}",
            f"hash_integrity_status: {report.hash_integrity_status}",
        ]
    )


def _load_claims_from_jsonl(path: Path) -> list[dict]:
    claims: list[dict] = []
    for idx, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        payload.setdefault("claim_id", f"claim:{idx}")
        payload.setdefault("source_id", payload.get("provenance", {}).get("source_id", "unknown"))
        claims.append(payload)
    return claims


def _claims_from_source_or_pack(target: Path) -> tuple[list[dict], Path]:
    if target.is_dir():
        claims_path = target / "claims.jsonl"
        if not claims_path.exists():
            raise TrustError("MISSING_CLAIMS", f"missing claims.jsonl in {target}")
        return _load_claims_from_jsonl(claims_path), target
    if target.suffix.lower() == ".jsonl":
        return _load_claims_from_jsonl(target), target.parent
    raise TrustError("UNSUPPORTED_INPUT", f"expected pack dir or .jsonl file: {target}")


def run_trust_evaluate(target: Path, policy_path: str | None = None, json_output: bool = False) -> str:
    claims, _ = _claims_from_source_or_pack(target)
    report = TrustPromoter(policy=load_policy(policy_path)).evaluate_claims(claims)
    payload = report.to_dict()
    if json_output:
        return json.dumps(payload, sort_keys=True)
    return "\n".join(
        [
            "status: TRUST_EVALUATED",
            f"claims: {len(payload['decisions'])}",
            f"conflicts: {len(payload['conflicts'])}",
            f"stale_flags: {sum(1 for item in payload['staleness'] if item.get('stale'))}",
        ]
    )


def run_trust_promote(
    pack_path: Path,
    policy_path: str | None = None,
    strict: bool = False,
    output_path: Path | None = None,
    json_output: bool = False,
) -> str:
    report = TrustPromoter(policy=load_policy(policy_path)).promote(pack_path)
    payload = report.to_dict()
    integrity_payload = build_integrity(pack_path)
    (pack_path / "integrity.json").write_text(json.dumps(integrity_payload, indent=2, sort_keys=True) + "\n")
    if output_path is not None:
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    blockers = sum(len(item["blocking_issues"]) for item in payload["decisions"])
    if strict and blockers > 0:
        raise TrustError("TRUST_PROMOTION_BLOCKED", "strict mode blocked promotion due to unresolved issues")
    if json_output:
        return json.dumps(
            {
                "status": "TRUST_PROMOTED",
                "decisions": payload["decisions"],
                "conflicts": payload["conflicts"],
                "staleness": payload["staleness"],
                "integrity": integrity_payload,
            },
            sort_keys=True,
        )
    lines = [
        "status: TRUST_PROMOTED",
        f"decisions: {len(payload['decisions'])}",
        f"conflicts: {len(payload['conflicts'])}",
        f"stale_flags: {sum(1 for item in payload['staleness'] if item.get('stale'))}",
        f"blocking_issues: {blockers}",
    ]
    if output_path is not None:
        lines.append(f"output: {output_path}")
    return "\n".join(lines)


def run_trust_stats(pack_path: Path, json_output: bool = False) -> str:
    trust_path = pack_path / "trust_report.json"
    if not trust_path.exists():
        raise TrustError("MISSING_TRUST_REPORT", f"missing trust_report.json in {pack_path}")
    payload = json.loads(trust_path.read_text())
    decisions = list(payload.get("decisions", []))
    conflicts = list(payload.get("conflicts", []))
    stale = [item for item in payload.get("staleness", []) if item.get("stale")]
    certified = [item for item in decisions if item.get("recommended_tier") in {"T4_VERIFIER_CONSISTENT", "T5_CERTIFIED"}]
    stats = {
        "total_claims": len(decisions),
        "certified_like_claims": len(certified),
        "conflicts": len(conflicts),
        "stale_claims": len(stale),
    }
    if json_output:
        return json.dumps(stats, sort_keys=True)
    return "\n".join(
        [
            "status: TRUST_STATS",
            f"total_claims: {stats['total_claims']}",
            f"certified_like_claims: {stats['certified_like_claims']}",
            f"conflicts: {stats['conflicts']}",
            f"stale_claims: {stats['stale_claims']}",
        ]
    )


def run_trust_conflicts(pack_path: Path, json_output: bool = False) -> str:
    conflicts_path = pack_path / "conflicts.jsonl"
    if not conflicts_path.exists():
        raise TrustError("MISSING_CONFLICTS", f"missing conflicts.jsonl in {pack_path}")
    rows = [json.loads(line) for line in conflicts_path.read_text().splitlines() if line.strip()]
    if json_output:
        return json.dumps({"conflicts": rows}, sort_keys=True)
    lines = ["status: TRUST_CONFLICTS", f"count: {len(rows)}"]
    if rows:
        lines.append("items:")
        for row in rows:
            lines.append(f"  - {row.get('conflict_type')}: {row.get('explanation')}")
    return "\n".join(lines)


def run_trust_stale(pack_path: Path, json_output: bool = False) -> str:
    stale_path = pack_path / "staleness.jsonl"
    if not stale_path.exists():
        raise TrustError("MISSING_STALENESS", f"missing staleness.jsonl in {pack_path}")
    rows = [json.loads(line) for line in stale_path.read_text().splitlines() if line.strip()]
    stale_rows = [item for item in rows if item.get("stale")]
    if json_output:
        return json.dumps({"staleness": rows, "stale_count": len(stale_rows)}, sort_keys=True)
    return "\n".join(
        [
            "status: TRUST_STALE",
            f"total: {len(rows)}",
            f"stale: {len(stale_rows)}",
        ]
    )


def run_ledger_verify(target: Path, json_output: bool = False) -> str:
    if target.is_dir():
        payload = verify_pack_ledger(target)
    else:
        payload = verify_ledger(target)
    if json_output:
        return json.dumps(payload, sort_keys=True)
    lines = [
        f"status: {'LEDGER_OK' if payload.get('ok') else 'LEDGER_INVALID'}",
        f"errors: {len(payload.get('errors', []))}",
    ]
    if payload.get("errors"):
        lines.append("details:")
        for item in payload["errors"]:
            lines.append(f"  - {item}")
    return "\n".join(lines)


def run_ledger_inspect(target: Path, token: str, json_output: bool = False) -> str:
    path = target if target.is_file() else (target / "ledger_snapshot.json")
    record = LedgerStore(path).inspect(token)
    if record is None:
        raise TrustError("NOT_FOUND", f"no matching event/claim found for {token}")
    if json_output:
        return json.dumps(record, sort_keys=True)
    return "\n".join(
        [
            "status: LEDGER_RECORD",
            f"event_id: {record.get('event_id')}",
            f"event_type: {record.get('event_type')}",
            f"claim_id: {record.get('claim_id')}",
            f"pack_id: {record.get('pack_id')}",
        ]
    )


def run_ledger_export(target: Path, output: Path, json_output: bool = False) -> str:
    source = target if target.is_file() else (target / "ledger_snapshot.json")
    exported = export_ledger(source, output)
    payload = {"status": "LEDGER_EXPORTED", "output": str(exported)}
    if json_output:
        return json.dumps(payload, sort_keys=True)
    return "\n".join(["status: LEDGER_EXPORTED", f"output: {exported}"])


def _merge_runtime_bundle(primary, secondary):
    if primary is None:
        return secondary
    if secondary is None:
        return primary
    from vcse.dsl.schema import CapabilityBundle

    merged = CapabilityBundle(name="runtime_merged", version="1.0.0")
    for bundle in (primary, secondary):
        merged.synonyms.extend(bundle.synonyms)
        merged.parser_patterns.extend(bundle.parser_patterns)
        merged.relation_schemas.extend(bundle.relation_schemas)
        merged.ingestion_templates.extend(bundle.ingestion_templates)
        merged.generation_templates.extend(bundle.generation_templates)
        merged.proposer_rules.extend(bundle.proposer_rules)
        merged.clarification_rules.extend(bundle.clarification_rules)
        merged.renderer_templates.extend(bundle.renderer_templates)
        merged.verifier_stubs.extend(bundle.verifier_stubs)
        merged.warnings.extend(bundle.warnings)
    return merged


def resolve_pack_activation(pack_values: list[str] | None, packs_csv: str | None):
    specs: list[str] = []
    for value in pack_values or []:
        clean = value.strip()
        if clean:
            specs.append(clean)
    if packs_csv:
        specs.extend(item.strip() for item in packs_csv.split(",") if item.strip())
    if not specs:
        return None
    return PackActivator().activate(specs)


def resolve_runtime_inputs(
    *,
    dsl_path: str | None,
    pack_values: list[str] | None,
    packs_csv: str | None,
):
    dsl_bundle = load_dsl_bundle(dsl_path) if dsl_path else None
    activation = resolve_pack_activation(pack_values, packs_csv)
    if activation is None:
        return dsl_bundle, [], []
    merged_bundle = _merge_runtime_bundle(dsl_bundle, activation.dsl_bundle)
    return merged_bundle, list(activation.knowledge_claims), list(activation.constraints)


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
    benchmark_parser.add_argument("--pack", action="append", dest="pack_values")
    benchmark_parser.add_argument("--packs")
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
    ingest_parser.add_argument("--pack", action="append", dest="pack_values")
    ingest_parser.add_argument("--packs")

    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("spec")
    generate_parser.add_argument("--debug", action="store_true")
    generate_parser.add_argument("--index", action="store_true")
    generate_parser.add_argument("--dsl")
    generate_parser.add_argument("--pack", action="append", dest="pack_values")
    generate_parser.add_argument("--packs")
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
    gauntlet_parser.add_argument("--pack", action="append", dest="pack_values")
    gauntlet_parser.add_argument("--packs")
    gauntlet_parser.add_argument("--profile", action="store_true")

    # New interaction commands
    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("text", nargs="*", default=[])
    ask_parser.add_argument("--mode", default="explain")
    ask_parser.add_argument("--ts3", action="store_true")
    ask_parser.add_argument("--search")
    ask_parser.add_argument("--dsl")
    ask_parser.add_argument("--pack", action="append", dest="pack_values")
    ask_parser.add_argument("--packs")
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

    knowledge_parser = subparsers.add_parser("knowledge")
    knowledge_subparsers = knowledge_parser.add_subparsers(dest="knowledge_command")
    knowledge_validate_parser = knowledge_subparsers.add_parser("validate")
    knowledge_validate_parser.add_argument("source")
    knowledge_build_parser = knowledge_subparsers.add_parser("build")
    knowledge_build_parser.add_argument("source")
    knowledge_build_parser.add_argument("--pack", required=True)
    knowledge_build_parser.add_argument("--domain", default="general")
    knowledge_stats_parser = knowledge_subparsers.add_parser("stats")
    knowledge_stats_parser.add_argument("pack")

    pack_parser = subparsers.add_parser("pack")
    pack_subparsers = pack_parser.add_subparsers(dest="pack_command")
    pack_validate_parser = pack_subparsers.add_parser("validate")
    pack_validate_parser.add_argument("pack_path")
    pack_validate_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_install_parser = pack_subparsers.add_parser("install")
    pack_install_parser.add_argument("pack_path")
    pack_install_parser.add_argument("--force", action="store_true")
    pack_install_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_uninstall_parser = pack_subparsers.add_parser("uninstall")
    pack_uninstall_parser.add_argument("pack_id")
    pack_uninstall_parser.add_argument("--version")
    pack_uninstall_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_list_parser = pack_subparsers.add_parser("list")
    pack_list_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_info_parser = pack_subparsers.add_parser("info")
    pack_info_parser.add_argument("pack_id")
    pack_info_parser.add_argument("--version")
    pack_info_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_audit_parser = pack_subparsers.add_parser("audit")
    pack_audit_parser.add_argument("target")
    pack_audit_parser.add_argument("--json", action="store_true", dest="json_output")

    trust_parser = subparsers.add_parser("trust")
    trust_subparsers = trust_parser.add_subparsers(dest="trust_command")
    trust_eval_parser = trust_subparsers.add_parser("evaluate")
    trust_eval_parser.add_argument("target")
    trust_eval_parser.add_argument("--json", action="store_true", dest="json_output")
    trust_eval_parser.add_argument("--policy")
    trust_promote_parser = trust_subparsers.add_parser("promote")
    trust_promote_parser.add_argument("target")
    trust_promote_parser.add_argument("--json", action="store_true", dest="json_output")
    trust_promote_parser.add_argument("--policy")
    trust_promote_parser.add_argument("--strict", action="store_true")
    trust_promote_parser.add_argument("--output", type=Path)
    trust_stats_parser = trust_subparsers.add_parser("stats")
    trust_stats_parser.add_argument("target")
    trust_stats_parser.add_argument("--json", action="store_true", dest="json_output")
    trust_conflicts_parser = trust_subparsers.add_parser("conflicts")
    trust_conflicts_parser.add_argument("target")
    trust_conflicts_parser.add_argument("--json", action="store_true", dest="json_output")
    trust_stale_parser = trust_subparsers.add_parser("stale")
    trust_stale_parser.add_argument("target")
    trust_stale_parser.add_argument("--json", action="store_true", dest="json_output")

    ledger_parser = subparsers.add_parser("ledger")
    ledger_subparsers = ledger_parser.add_subparsers(dest="ledger_command")
    ledger_verify_parser = ledger_subparsers.add_parser("verify")
    ledger_verify_parser.add_argument("target")
    ledger_verify_parser.add_argument("--json", action="store_true", dest="json_output")
    ledger_verify_parser.add_argument("--strict", action="store_true")
    ledger_inspect_parser = ledger_subparsers.add_parser("inspect")
    ledger_inspect_parser.add_argument("token")
    ledger_inspect_parser.add_argument("--target", default=".")
    ledger_inspect_parser.add_argument("--json", action="store_true", dest="json_output")
    ledger_export_parser = ledger_subparsers.add_parser("export")
    ledger_export_parser.add_argument("target")
    ledger_export_parser.add_argument("--output", required=True, type=Path)
    ledger_export_parser.add_argument("--json", action="store_true", dest="json_output")

    compress_parser = subparsers.add_parser("compress")
    compress_subparsers = compress_parser.add_subparsers(dest="compress_command")
    compress_pack_parser = compress_subparsers.add_parser("pack")
    compress_pack_parser.add_argument("target")
    compress_pack_parser.add_argument("--output", required=True, type=Path)
    compress_pack_parser.add_argument("--json", action="store_true", dest="json_output")
    compress_stats_parser = compress_subparsers.add_parser("stats")
    compress_stats_parser.add_argument("target")
    compress_stats_parser.add_argument("--json", action="store_true", dest="json_output")
    decompress_parser = subparsers.add_parser("decompress")
    decompress_subparsers = decompress_parser.add_subparsers(dest="decompress_command")
    decompress_pack_parser = decompress_subparsers.add_parser("pack")
    decompress_pack_parser.add_argument("target")
    decompress_pack_parser.add_argument("--output", required=True, type=Path)
    decompress_pack_parser.add_argument("--json", action="store_true", dest="json_output")
    decompress_verify_parser = decompress_subparsers.add_parser("verify")
    decompress_verify_parser.add_argument("target")
    decompress_verify_parser.add_argument("--json", action="store_true", dest="json_output")

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
            dsl_bundle, _, _ = resolve_runtime_inputs(
                dsl_path=args.dsl,
                pack_values=args.pack_values,
                packs_csv=args.packs,
            )
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
            dsl_bundle, _, _ = resolve_runtime_inputs(
                dsl_path=args.dsl,
                pack_values=args.pack_values,
                packs_csv=args.packs,
            )
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
            dsl_bundle, preload_claims, preload_constraints = resolve_runtime_inputs(
                dsl_path=args.dsl,
                pack_values=args.pack_values,
                packs_csv=args.packs,
            )
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
                    preload_claims=preload_claims,
                    preload_constraints=preload_constraints,
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
            dsl_bundle, _, _ = resolve_runtime_inputs(
                dsl_path=args.dsl,
                pack_values=args.pack_values,
                packs_csv=args.packs,
            )
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
            dsl_bundle, preload_claims, preload_constraints = resolve_runtime_inputs(
                dsl_path=args.dsl,
                pack_values=args.pack_values,
                packs_csv=args.packs,
            )
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
                    preload_claims=preload_claims,
                    preload_constraints=preload_constraints,
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
        if args.command == "knowledge":
            if args.knowledge_command == "validate":
                print(run_knowledge_validate(Path(args.source)))
                return
            if args.knowledge_command == "build":
                print(run_knowledge_build(Path(args.source), args.pack, domain=args.domain))
                return
            if args.knowledge_command == "stats":
                print(run_knowledge_stats(Path(args.pack)))
                return
        if args.command == "pack":
            if args.pack_command == "validate":
                text = run_pack_validate(Path(args.pack_path), json_output=args.json_output)
                print(text)
                if "status: INVALID" in text and not args.json_output:
                    raise SystemExit(2)
                if args.json_output:
                    payload = json.loads(text)
                    if not payload.get("passed", False):
                        raise SystemExit(2)
                return
            if args.pack_command == "install":
                print(run_pack_install(Path(args.pack_path), force=args.force, json_output=args.json_output))
                return
            if args.pack_command == "uninstall":
                print(
                    run_pack_uninstall(
                        args.pack_id,
                        version=args.version,
                        json_output=args.json_output,
                    )
                )
                return
            if args.pack_command == "list":
                print(run_pack_list(json_output=args.json_output))
                return
            if args.pack_command == "info":
                print(run_pack_info(args.pack_id, version=args.version, json_output=args.json_output))
                return
            if args.pack_command == "audit":
                print(run_pack_audit(args.target, json_output=args.json_output))
                return
        if args.command == "trust":
            if args.trust_command == "evaluate":
                print(run_trust_evaluate(Path(args.target), policy_path=args.policy, json_output=args.json_output))
                return
            if args.trust_command == "promote":
                print(
                    run_trust_promote(
                        Path(args.target),
                        policy_path=args.policy,
                        strict=args.strict,
                        output_path=args.output,
                        json_output=args.json_output,
                    )
                )
                return
            if args.trust_command == "stats":
                print(run_trust_stats(Path(args.target), json_output=args.json_output))
                return
            if args.trust_command == "conflicts":
                print(run_trust_conflicts(Path(args.target), json_output=args.json_output))
                return
            if args.trust_command == "stale":
                print(run_trust_stale(Path(args.target), json_output=args.json_output))
                return
        if args.command == "ledger":
            if args.ledger_command == "verify":
                text = run_ledger_verify(Path(args.target), json_output=args.json_output)
                print(text)
                if args.strict and args.json_output:
                    payload = json.loads(text)
                    if not payload.get("ok", False):
                        raise SystemExit(2)
                if args.strict and not args.json_output and "status: LEDGER_INVALID" in text:
                    raise SystemExit(2)
                return
            if args.ledger_command == "inspect":
                print(run_ledger_inspect(Path(args.target), args.token, json_output=args.json_output))
                return
            if args.ledger_command == "export":
                print(run_ledger_export(Path(args.target), args.output, json_output=args.json_output))
                return
        if args.command == "compress":
            if args.compress_command == "pack":
                try:
                    pack = optimize_pack(Path(args.target))
                    save_compressed(pack, args.output)
                    msg = f"status: COMPRESSED\noutput: {args.output}\n"
                    msg += f"original_claims: {pack.metrics.get('original_claims', 0)}\n"
                    msg += f"compressed_claims: {pack.metrics.get('compressed_claims', 0)}\n"
                    msg += f"unique_strings: {pack.metrics.get('unique_strings', 0)}\n"
                    msg += f"original_size: {pack.metrics.get('original_size_bytes', 0)} bytes\n"
                    msg += f"compressed_size: {pack.metrics.get('compressed_size_bytes', 0)} bytes\n"
                    msg += f"compression_ratio: {pack.metrics.get('compression_ratio', 0)}\n"
                    print(msg if not args.json_output else json.dumps({"status": "COMPRESSED", "output": str(args.output), "metrics": pack.metrics}))
                except CompressionError as exc:
                    print(f"status: ERROR\nerror_type: {exc.code}\nmessage: {exc.message}")
                    raise SystemExit(2)
                return
            if args.compress_command == "stats":
                try:
                    metrics = compression_compute_metrics(Path(args.target))
                    if not metrics:
                        print("status: NO_METRICS\nmessage: not a compressed pack")
                        return
                    print(format_metrics(metrics) if not args.json_output else json.dumps({"status": "STATS", "metrics": metrics}))
                except Exception as exc:
                    print(f"status: ERROR\nmessage: {exc}")
                    raise SystemExit(2)
                return
        if args.command == "decompress":
            if args.decompress_command == "pack":
                try:
                    loaded = load_compressed(Path(args.target))
                    save_compressed(loaded, args.output)
                    print(f"status: DECOMPRESSED\noutput: {args.output}\nclaims: {len(loaded.original_claims)}")
                except CompressionError as exc:
                    print(f"status: ERROR\nerror_type: {exc.code}\nmessage: {exc.message}")
                    raise SystemExit(2)
                return
            if args.decompress_command == "verify":
                try:
                    result = verify_integrity(Path(args.target))
                    status_str = "status: VALID" if result.get("valid") else f"status: {result.get('status', 'INVALID')}"
                    result_str = format_metrics(result) if not args.json_output else json.dumps(result)
                    print(f"{status_str}\n{result_str}")
                    if not result.get("valid"):
                        raise SystemExit(2)
                except CompressionError as exc:
                    print(f"status: ERROR\nerror_type: {exc.code}\nmessage: {exc.message}")
                    raise SystemExit(2)
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
        KnowledgeError,
        PackError,
        TrustError,
        LedgerError,
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
