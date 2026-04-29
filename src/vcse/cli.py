"""VCSE command line interface."""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from vcse.benchmark import BenchmarkCaseError, format_benchmark_text, run_benchmark
from vcse.benchmark_coverage import CoverageBenchmarkError, format_coverage_text, run_coverage_benchmark
from vcse.benchmark_inference_classification import InferenceType, classify_resolution_for_claim
from vcse.config import load_settings
from vcse.domain.loader import DomainSpecError, load_domain_spec
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
from vcse.inference.explanation import (
    InferenceExplanation,
    build_inverse_explanation,
    build_transitive_explanation,
)
from vcse.inference.inverse import infer_inverse_claims
from vcse.inference.transitive import infer_transitive_claims
from vcse.inference.stability import InferenceObservation, InferenceStabilityTracker
from vcse.inference.promotion import build_pack_from_promoted_claims, promote_stable_claims
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
    CertificationReport,
    MergeReport,
    certify_candidate_pack,
    merge_certified_pack,
    PackError,
    PackInstaller,
    PackIndex,
    PackIndexError,
    PackLifecycleManager,
    PackRegistry,
    PackValidator,
    RuntimeStore,
    RuntimeStoreCompiler,
    RuntimeStoreReport,
)
from vcse.packs.integrity import (
    compute_pack_hash,
    diff_packs,
    resolve_pack_path,
    sign_pack_manifest,
    verify_pack_integrity,
    verify_pack_signature,
)
from vcse.packs.runtime_store import load_runtime_claims_if_valid, runtime_store_path_for_pack
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
from vcse.agent import (
    AgentError,
    ExecutionError,
    Plan,
    Task,
    run_task,
    resume_task,
    plan_task,
    ExecutionState,
)
from vcse.knowledge.pack_model import KnowledgeClaim
from vcse.semantic.runtime_regions import RuntimeRegionIndex


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


def render_report_summary_from_dict(data: dict) -> str:
    lines = [
        f"status: {data.get('status', 'UNKNOWN')}",
        f"run_id: {data.get('run_id', '')}",
        f"timestamp: {data.get('timestamp', '')}",
        f"sources_processed: {len(data.get('source_ids', []))}",
        f"claims_extracted: {data.get('claims_extracted', 0)}",
        f"claims_ingested: {data.get('claims_ingested', 0)}",
        f"trust_decisions: {data.get('trust_decisions', 0)}",
        f"dry_run: {data.get('dry_run', False)}",
    ]
    errors = data.get("errors", [])
    if errors:
        lines.append("errors:")
        for e in errors:
            lines.append(f"  - {e}")
    return "\n".join(lines)


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
    allow_query_normalization: bool = True,
    explain_inferred: bool = True,
    return_resolution_type: bool = False,
    planned: bool = False,
    planned_debug: bool = False,
    planned_store_path: Path | None = None,
) -> str | tuple[str, InferenceType]:
    """Handle vcse ask command."""
    from vcse.interaction.session import Session, TurnRecord
    from vcse.interaction.response_modes import QueryType, ResponseMode, render_response
    from vcse.interaction.frames import FrameParseResult, FrameStatus, ClaimFrame, GoalFrame
    from vcse.interaction.query_normalizer import normalize_query
    from vcse.packs.runtime_store import RuntimeStore
    from vcse.query.executor import QueryExecutor
    from vcse.query.planner import QueryPlanner

    query_type = _classify_query_type(text)

    def _render_result(
        session: Session,
        result,
        inferred_explanation: InferenceExplanation | None = None,
    ) -> str:
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
            query_type=query_type,
            inferred_explanation=inferred_explanation if explain_inferred else None,
        )

    def _run_existing() -> tuple[str, InferenceType]:
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
        rendered = _render_result(session, result)
        if result is None or hasattr(result, "user_message"):
            return rendered, InferenceType.UNSUPPORTED
        evaluation = getattr(result, "evaluation", None)
        if evaluation is None or getattr(evaluation, "status", None) is None:
            return rendered, InferenceType.UNKNOWN
        if str(getattr(evaluation.status, "value", evaluation.status)) != "VERIFIED":
            return rendered, InferenceType.UNKNOWN
        return rendered, InferenceType.UNKNOWN

    def _run_normalized() -> tuple[str, InferenceType] | None:
        # Run only for direct user text input; skip when structured DSL bundle is provided.
        if not allow_query_normalization:
            return None
        normalized = normalize_query(text)
        if normalized is None:
            return None

        goal = _goal_from_normalized_query(
            normalized.subject,
            normalized.relation,
            normalized.object,
            preload_claims or [],
        )
        if goal is None:
            return None
        subject, relation, obj = goal

        session = Session.create(
            dsl_bundle=dsl_bundle,
            enable_indexing=enable_index,
            top_k_rules=top_k_rules,
            top_k_packs=top_k_packs,
        )
        session.mode = mode
        _apply_preloaded_knowledge(session.memory, preload_claims or [], preload_constraints or [])
        session.history.append(
            TurnRecord(
                timestamp="",
                user_input=text,
                frames=FrameParseResult(
                    frames=[
                        ClaimFrame(subject=subject, relation=relation, object=obj, source_text=text),
                        GoalFrame(subject=subject, relation=relation, object=obj, source_text=text),
                    ],
                    status=FrameStatus.PARSED,
                    confidence=1.0,
                ),
            )
        )
        result = session.solve(enable_ts3=enable_ts3, search_backend=search_backend)
        if result is None:
            return None
        status_value = getattr(getattr(result, "evaluation", None), "status", None)
        if status_value is not None and str(getattr(status_value, "value", status_value)) != "VERIFIED":
            return obj, InferenceType.UNKNOWN
        return _render_result(session, result), InferenceType.UNKNOWN

    def _run_boolean_capital_check() -> tuple[str, InferenceType] | None:
        clean = text.strip()
        low = clean.lower()
        prefix = "is "
        marker = " the capital of "
        if not (low.startswith(prefix) and low.endswith("?") and marker in low):
            return None
        body = clean[:-1]
        marker_index = low.find(marker)
        subject = body[len(prefix):marker_index].strip()
        obj = body[marker_index + len(marker):].strip()
        if not subject or not obj:
            return None
        goal_result = _goal_from_boolean_capital_query(subject, obj, preload_claims or [])
        if goal_result is None:
            return None
        goal, inferred_explanation = goal_result
        if inferred_explanation is not None and explain_inferred:
            return _render_inferred_boolean(goal, inferred_explanation), InferenceType.INVERSE
        g_subject, g_relation, g_object = goal
        session = Session.create(
            dsl_bundle=dsl_bundle,
            enable_indexing=enable_index,
            top_k_rules=top_k_rules,
            top_k_packs=top_k_packs,
        )
        session.mode = mode
        _apply_preloaded_knowledge(session.memory, preload_claims or [], preload_constraints or [])
        session.history.append(
            TurnRecord(
                timestamp="",
                user_input=text,
                frames=FrameParseResult(
                    frames=[
                        ClaimFrame(subject=g_subject, relation=g_relation, object=g_object, source_text=text),
                        GoalFrame(subject=g_subject, relation=g_relation, object=g_object, source_text=text),
                    ],
                    status=FrameStatus.PARSED,
                    confidence=1.0,
                ),
            )
        )
        result = session.solve(enable_ts3=enable_ts3, search_backend=search_backend)
        if result is None:
            return None
        rendered = _render_result(session, result)
        status_value = getattr(getattr(result, "evaluation", None), "status", None)
        if status_value is not None and str(getattr(status_value, "value", status_value)) == "VERIFIED":
            return rendered, InferenceType.EXPLICIT
        return rendered, InferenceType.UNKNOWN

    def _run_inverse_capital_fact_lookup() -> tuple[str, InferenceExplanation | None, InferenceType] | None:
        clean = text.strip()
        low = clean.lower()
        prefix = "what is "
        suffix = " the capital of?"
        if not (low.startswith(prefix) and low.endswith(suffix)):
            return None
        city = clean[len(prefix):len(clean) - len(suffix)].strip()
        if not city:
            return None
        explicit_claims = _knowledge_claims_from_dict_claims(preload_claims or [])
        explicit_values = sorted(
            {
                claim.object
                for claim in explicit_claims
                if claim.subject.lower() == city.lower() and claim.relation.lower() == "capital_of"
            }
        )
        if len(explicit_values) == 1:
            return explicit_values[0], None, InferenceType.EXPLICIT
        inferred_values = sorted(
            [
                claim
                for claim in infer_inverse_claims(explicit_claims)
                if claim.subject.lower() == city.lower() and claim.relation.lower() == "capital_of"
            ],
            key=lambda claim: claim.key,
        )
        if len(inferred_values) == 1:
            inferred = inferred_values[0]
            return inferred.object, build_inverse_explanation(inferred), InferenceType.INVERSE
        return None

    def _run_continent_lookup() -> tuple[str, InferenceExplanation | None, InferenceType] | None:
        clean = text.strip()
        low = clean.lower()
        prefix = "what continent is "
        suffix = " in?"
        if not (low.startswith(prefix) and low.endswith(suffix)):
            return None
        subject = clean[len(prefix):len(clean) - len(suffix)].strip()
        if not subject:
            return None
        explicit_claims = _knowledge_claims_from_dict_claims(preload_claims or [])
        explicit_values = sorted(
            {
                claim.object
                for claim in explicit_claims
                if claim.subject.lower() == subject.lower() and claim.relation.lower() in {"part_of", "located_in_region"}
            }
        )
        if len(explicit_values) == 1:
            return explicit_values[0], None, InferenceType.EXPLICIT
        inferred_values = sorted(
            [
                claim
                for claim in infer_transitive_claims(explicit_claims)
                if claim.subject.lower() == subject.lower() and claim.relation.lower() == "located_in_region"
            ],
            key=lambda claim: claim.key,
        )
        if len(inferred_values) == 1:
            inferred = inferred_values[0]
            return inferred.object, build_transitive_explanation(inferred), InferenceType.TRANSITIVE
        return None

    def _run() -> tuple[str, InferenceType]:
        if planned and planned_store_path is not None and allow_query_normalization:
            normalized = normalize_query(text)
            plan = QueryPlanner().plan(normalized)
            if plan is not None:
                store = RuntimeStore(planned_store_path)
                try:
                    planned_result = QueryExecutor().execute(plan, store)
                finally:
                    store.close()
                if planned_result.answer_claim is not None and not planned_result.fallback_used:
                    answer = _render_planned_answer(plan.target_relation, planned_result.answer_claim)
                    if planned_debug:
                        answer += (
                            "\nplanned_metrics:"
                            f"\n  rows_examined: {planned_result.rows_examined}"
                            f"\n  touched_shards: {list(planned_result.touched_shards)}"
                            f"\n  touched_indexes: {list(planned_result.touched_indexes)}"
                            f"\n  fallback_used: {planned_result.fallback_used}"
                        )
                    return answer, InferenceType.EXPLICIT
        continent = _run_continent_lookup()
        if continent is not None:
            answer, inferred_explanation, resolution_type = continent
            if inferred_explanation is None or not explain_inferred:
                return answer, resolution_type
            return _render_inferred_answer(answer, inferred_explanation), resolution_type
        inverse_capital = _run_inverse_capital_fact_lookup()
        if inverse_capital is not None:
            answer, inferred_explanation, resolution_type = inverse_capital
            if inferred_explanation is None or not explain_inferred:
                return answer, resolution_type
            return _render_inferred_answer(answer, inferred_explanation), resolution_type
        boolean_capital = _run_boolean_capital_check()
        if boolean_capital is not None:
            return boolean_capital
        normalized_output = _run_normalized()
        if normalized_output is not None:
            return normalized_output
        return _run_existing()

    if not profile:
        output, resolution_type = _run()
        if return_resolution_type:
            return output, resolution_type
        return output

    with profile_run() as (trace, holder):
        output, resolution_type = _run()
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
    profiled_output = "\n".join(lines)
    if return_resolution_type:
        return profiled_output, resolution_type
    return profiled_output


def _render_inferred_answer(
    answer_object: str,
    inferred_explanation: InferenceExplanation,
) -> str:
    from vcse.interaction.response_modes import QueryType, ResponseMode, render_response
    from vcse.verifier.final_state import FinalStateEvaluation, FinalStatus

    conclusion_subject, conclusion_relation, _ = inferred_explanation.conclusion
    evaluation = FinalStateEvaluation(
        status=FinalStatus.VERIFIED,
        answer=f"{conclusion_subject} {conclusion_relation} {answer_object}",
    )
    return render_response(
        evaluation,
        ResponseMode.EXPLAIN,
        query_type=QueryType.FACT,
        inferred_explanation=inferred_explanation,
    )


def _render_inferred_boolean(
    goal: tuple[str, str, str],
    inferred_explanation: InferenceExplanation,
) -> str:
    from vcse.interaction.response_modes import QueryType, ResponseMode, render_response
    from vcse.verifier.final_state import FinalStateEvaluation, FinalStatus

    evaluation = FinalStateEvaluation(
        status=FinalStatus.VERIFIED,
        answer=" ".join(goal),
    )
    return render_response(
        evaluation,
        ResponseMode.EXPLAIN,
        query_type=QueryType.BOOLEAN,
        inferred_explanation=inferred_explanation,
    )


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


def _render_planned_answer(relation: str, claim: dict[str, str]) -> str:
    subject = str(claim.get("subject", ""))
    object_ = str(claim.get("object", ""))
    if relation in {"has_capital", "capital_of"}:
        return f"{object_} is the capital of {subject}."
    if relation == "uses_currency":
        return f"{subject} uses the {object_}."
    if relation == "language_of":
        return f"{object_} is a language of {subject}."
    if relation == "has_country_code":
        return f"{subject} has country code {object_}."
    if relation in {"part_of", "located_in_region"}:
        return object_
    return object_


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
    indexed_items = PackIndex().list_packs(include_stale=False)
    if indexed_items:
        if json_output:
            return json.dumps(indexed_items, sort_keys=True)
        return "\n".join(
            [
                "status: PACK_INDEX_LIST",
                "packs:",
                *[
                    (
                        f"  - {item.get('pack_id')}@{item.get('version')} "
                        f"domain={item.get('domain')} lifecycle={item.get('lifecycle_status')} "
                        f"claims={item.get('claim_count')} path={item.get('pack_path')}"
                    )
                    for item in indexed_items
                ],
            ]
        )

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


def run_pack_certify(pack_id: str, output_pack_id: str, json_output: bool = False) -> str:
    report: CertificationReport = certify_candidate_pack(pack_id, output_pack_id)
    payload = {
        "source_pack_id": report.source_pack_id,
        "output_pack_id": report.output_pack_id,
        "status": report.status,
        "claim_count": report.claim_count,
        "duplicate_count": report.duplicate_count,
        "missing_provenance_count": report.missing_provenance_count,
        "certified_claim_count": report.certified_claim_count,
        "reasons": report.reasons,
        "output_pack_path": str(Path("examples") / "packs" / output_pack_id),
    }
    if json_output:
        return json.dumps(payload, sort_keys=True)
    lines = [
        f"status: {report.status}",
        f"source_pack_id: {report.source_pack_id}",
        f"output_pack_id: {report.output_pack_id}",
        f"claim_count: {report.claim_count}",
        f"duplicate_count: {report.duplicate_count}",
        f"missing_provenance_count: {report.missing_provenance_count}",
        f"certified_claim_count: {report.certified_claim_count}",
        f"output_pack_path: {Path('examples') / 'packs' / output_pack_id}",
    ]
    if report.reasons:
        lines.append("reasons:")
        for reason in report.reasons:
            lines.append(f"  - {reason}")
    return "\n".join(lines)


def run_pack_merge(
    source_pack_id: str,
    target_pack_id: str,
    output_pack_id: str | None = None,
    json_output: bool = False,
) -> str:
    report, snapshot_path, output_pack_path = merge_certified_pack(
        source_pack_id,
        target_pack_id,
        output_pack_id=output_pack_id,
    )
    payload = {
        "source_pack_id": report.source_pack_id,
        "target_pack_id": report.target_pack_id,
        "output_pack_id": output_pack_id or target_pack_id,
        "status": report.status,
        "merged_claim_count": report.merged_claim_count,
        "skipped_duplicate_count": report.skipped_duplicate_count,
        "final_claim_count": report.final_claim_count,
        "snapshot_path": str(snapshot_path) if str(snapshot_path) else "",
        "output_pack_path": str(output_pack_path),
        "reasons": report.reasons,
    }
    if json_output:
        return json.dumps(payload, sort_keys=True)
    lines = [
        f"status: {report.status}",
        f"source_pack_id: {report.source_pack_id}",
        f"target_pack_id: {report.target_pack_id}",
        f"output_pack_id: {output_pack_id or target_pack_id}",
        f"merged_claim_count: {report.merged_claim_count}",
        f"skipped_duplicate_count: {report.skipped_duplicate_count}",
        f"final_claim_count: {report.final_claim_count}",
        f"snapshot_path: {snapshot_path}",
        f"output_pack_path: {output_pack_path}",
    ]
    if report.reasons:
        lines.append("reasons:")
        for reason in report.reasons:
            lines.append(f"  - {reason}")
    return "\n".join(lines)


def run_pack_compile(pack_id: str, output: Path | None = None, force: bool = False, json_output: bool = False) -> str:
    return run_pack_compile_with_mode(
        pack_id=pack_id,
        output=output,
        force=force,
        incremental=False,
        stats=True,
        json_output=json_output,
    )


def run_pack_compile_with_mode(
    pack_id: str,
    output: Path | None = None,
    force: bool = False,
    incremental: bool = False,
    stats: bool = False,
    json_output: bool = False,
) -> str:
    pack_path = _resolve_pack_reference(pack_id)
    pack_meta = json.loads((pack_path / "pack.json").read_text())
    resolved_pack_id = str(pack_meta.get("id") or pack_meta.get("pack_id") or pack_path.name)
    default_output = runtime_store_path_for_pack(resolved_pack_id)
    output_path = output or default_output
    if output_path.exists() and not force and not incremental:
        raise PackError("STORE_EXISTS", f"runtime store already exists: {output_path}")
    compiler = RuntimeStoreCompiler()
    if incremental:
        report = compiler.compile_incremental(pack_path=pack_path, output_path=output_path)
    else:
        report = compiler.compile_pack(pack_path=pack_path, output_path=output_path)
    payload = {
        "pack_id": report.pack_id,
        "pack_path": report.pack_path,
        "output_path": report.output_path,
        "claim_count": report.claim_count,
        "provenance_count": report.provenance_count,
        "store_size_bytes": report.store_size_bytes,
        "compile_time_ms": report.compile_time_ms,
        "status": report.status,
        "reasons": report.reasons,
        "stage_timings_ms": report.stage_timings_ms,
    }
    if stats:
        payload.update(
            {
                "compile_time_ms": report.compile_time_ms,
                "load_time_ms": report.load_time_ms,
                "avg_query_latency_ms": report.avg_query_latency_ms,
                "backend": report.backend,
            }
        )
    if json_output:
        return json.dumps(payload, sort_keys=True)
    lines = [
        f"status: {report.status}",
        f"pack_id: {report.pack_id}",
        f"pack_path: {report.pack_path}",
        f"output_path: {report.output_path}",
        f"claim_count: {report.claim_count}",
        f"provenance_count: {report.provenance_count}",
        f"store_size_bytes: {report.store_size_bytes}",
    ]
    if stats:
        lines.extend(
            [
                f"compile_time_ms: {report.compile_time_ms}",
                f"load_time_ms: {report.load_time_ms}",
                f"avg_query_latency_ms: {report.avg_query_latency_ms}",
                f"backend: {report.backend}",
            ]
        )
    if report.reasons:
        lines.append("reasons:")
        for reason in report.reasons:
            lines.append(f"  - {reason}")
    return "\n".join(lines)


def run_pack_store_info(pack_id: str, json_output: bool = False) -> str:
    pack_path = _resolve_pack_reference(pack_id)
    pack_meta = json.loads((pack_path / "pack.json").read_text())
    resolved_pack_id = str(pack_meta.get("id") or pack_meta.get("pack_id") or pack_path.name)
    db_path = runtime_store_path_for_pack(resolved_pack_id)
    if not db_path.exists():
        raise PackError("STORE_NOT_FOUND", f"runtime store not found: {db_path}")
    sqlite_open_started = time.perf_counter()
    store = RuntimeStore(db_path)
    sqlite_open_ms = round((time.perf_counter() - sqlite_open_started) * 1000, 3)
    try:
        stats = store.stats()
        profile = store.profile_store_info()
    finally:
        store.close()
    payload = {
        "pack_id": stats["pack_id"] or resolved_pack_id,
        "pack_path": str(pack_path),
        "schema_version": stats["schema_version"],
        "claim_count": stats["claim_count"],
        "provenance_count": stats["provenance_count"],
        "store_size_bytes": stats["store_size_bytes"],
        "compile_time_ms": stats.get("compile_time_ms", 0.0),
        "load_time_ms": stats.get("load_time_ms", 0.0),
        "avg_query_latency_ms": stats.get("avg_query_latency_ms", 0.0),
        "backend": stats.get("backend", "sqlite"),
        "shard_count": stats.get("shard_count", 0),
        "entity_dictionary_count": stats.get("entity_dictionary_count", 0),
        "relation_dictionary_count": stats.get("relation_dictionary_count", 0),
        "pack_hash": stats["pack_hash"],
        "output_path": str(db_path),
        "store_info_timings_ms": {
            "sqlite_open_ms": sqlite_open_ms,
            "metadata_load_ms": profile.get("metadata_load_ms", 0.0),
            "sample_query_ms": profile.get("sample_query_ms", 0.0),
            "stats_query_ms": profile.get("stats_query_ms", 0.0),
        },
    }
    if json_output:
        return json.dumps(payload, sort_keys=True)
    return "\n".join(
        [
            "status: STORE_INFO",
            f"pack_id: {payload['pack_id']}",
            f"pack_path: {payload['pack_path']}",
            f"schema_version: {payload['schema_version']}",
            f"claim_count: {payload['claim_count']}",
            f"provenance_count: {payload['provenance_count']}",
            f"store_size_bytes: {payload['store_size_bytes']}",
            f"compile_time_ms: {payload['compile_time_ms']}",
            f"load_time_ms: {payload['load_time_ms']}",
            f"avg_query_latency_ms: {payload['avg_query_latency_ms']}",
            f"backend: {payload['backend']}",
            f"shard_count: {payload['shard_count']}",
            f"entity_dictionary_count: {payload['entity_dictionary_count']}",
            f"relation_dictionary_count: {payload['relation_dictionary_count']}",
            f"pack_hash: {payload['pack_hash']}",
            f"output_path: {payload['output_path']}",
        ]
    )


def _resolve_pack_reference(ref: str) -> Path:
    candidate = Path(ref)
    if candidate.exists():
        return candidate
    try:
        return resolve_pack_path(ref)
    except (PackError, PackIndexError):
        pass
    fallback = Path("examples") / "packs" / ref
    if fallback.exists():
        return fallback
    raise PackError("PACK_NOT_FOUND", f"pack not found: {ref}")


def run_pack_review(pack_ref: str, json_output: bool = False) -> str:
    pack_path = _resolve_pack_reference(pack_ref)
    claims_path = pack_path / "claims.jsonl"
    if not claims_path.exists():
        raise PackError("PACK_NOT_FOUND", f"missing claims.jsonl in {pack_path}")
    claims = [json.loads(line) for line in claims_path.read_text().splitlines() if line.strip()]
    inference_breakdown: dict[str, int] = {}
    for claim in claims:
        inference_type = str(claim.get("qualifiers", {}).get("inference_type", "unknown"))
        inference_breakdown[inference_type] = inference_breakdown.get(inference_type, 0) + 1
    sample = sorted(
        [
            {
                "subject": str(item.get("subject", "")),
                "relation": str(item.get("relation", "")),
                "object": str(item.get("object", "")),
            }
            for item in claims
        ],
        key=lambda row: (row["subject"], row["relation"], row["object"]),
    )[:5]
    payload = {
        "status": "PACK_REVIEW",
        "pack": pack_ref,
        "pack_path": str(pack_path),
        "claim_count": len(claims),
        "inference_type_breakdown": dict(sorted(inference_breakdown.items())),
        "sample_claims": sample,
    }
    if json_output:
        return json.dumps(payload, sort_keys=True)
    lines = [
        "status: PACK_REVIEW",
        f"pack: {pack_ref}",
        f"pack_path: {pack_path}",
        f"claim_count: {len(claims)}",
        "inference_type_breakdown:",
    ]
    for key, count in sorted(inference_breakdown.items()):
        lines.append(f"  - {key}: {count}")
    lines.append("sample_claims:")
    for row in sample:
        lines.append(f"  - {row['subject']} {row['relation']} {row['object']}")
    if not sample:
        lines.append("  - none")
    return "\n".join(lines)


def run_pack_validate_review(pack_ref: str, json_output: bool = False) -> str:
    direct_path = Path(pack_ref)
    if direct_path.exists():
        return run_pack_validate(direct_path, json_output=json_output)

    pack_path = _resolve_pack_reference(pack_ref)
    claims_path = pack_path / "claims.jsonl"
    provenance_path = pack_path / "provenance.jsonl"
    if not claims_path.exists():
        raise PackError("PACK_NOT_FOUND", f"missing claims.jsonl in {pack_path}")
    if not provenance_path.exists():
        raise PackError("PACK_NOT_FOUND", f"missing provenance.jsonl in {pack_path}")

    claims = [json.loads(line) for line in claims_path.read_text().splitlines() if line.strip()]
    provenance_rows = [json.loads(line) for line in provenance_path.read_text().splitlines() if line.strip()]
    errors: list[str] = []
    seen_keys: set[str] = set()
    for idx, claim in enumerate(claims):
        key = "|".join([str(claim.get("subject", "")), str(claim.get("relation", "")), str(claim.get("object", ""))])
        if key in seen_keys:
            errors.append(f"duplicate claim at line {idx + 1}: {key}")
        seen_keys.add(key)
        if not isinstance(claim.get("provenance"), dict):
            errors.append(f"missing provenance object at line {idx + 1}")
            continue
        prov = claim["provenance"]
        required = ["source_type", "source_id", "location", "evidence_text", "confidence", "trust_level"]
        missing = [field for field in required if not str(prov.get(field, "")).strip()]
        if missing:
            errors.append(f"incomplete provenance at line {idx + 1}: missing {','.join(missing)}")
    if len(provenance_rows) != len(claims):
        errors.append("provenance.jsonl length must match claims.jsonl length")

    payload = {
        "status": "VALID" if not errors else "INVALID",
        "pack": pack_ref,
        "pack_path": str(pack_path),
        "passed": not errors,
        "errors": errors,
        "claim_count": len(claims),
        "provenance_count": len(provenance_rows),
    }
    if json_output:
        return json.dumps(payload, sort_keys=True)
    lines = [
        f"status: {'VALID' if not errors else 'INVALID'}",
        f"pack: {pack_ref}",
        f"pack_path: {pack_path}",
        f"claim_count: {len(claims)}",
        f"provenance_count: {len(provenance_rows)}",
    ]
    if errors:
        lines.append("errors:")
        for error in errors:
            lines.append(f"  - {error}")
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
    index = PackIndex()
    query = f"{pack_id}@{version}" if version else pack_id
    try:
        metadata = index.get_pack_metadata(query)
        if json_output:
            return json.dumps(metadata, sort_keys=True)
        return "\n".join(
            [
                "status: PACK_INFO",
                f"id: {metadata.get('pack_id')}",
                f"version: {metadata.get('version')}",
                f"domain: {metadata.get('domain')}",
                f"lifecycle_status: {metadata.get('lifecycle_status')}",
                f"claim_count: {metadata.get('claim_count')}",
                f"certified_count: {metadata.get('certified_count')}",
                f"candidate_count: {metadata.get('candidate_count')}",
                f"source_ids: {','.join(metadata.get('source_ids', []))}",
                f"pack_hash: {metadata.get('pack_hash', '')}",
                f"merkle_root: {metadata.get('merkle_root', '')}",
                f"compression_ratio: {metadata.get('compression_ratio', 0)}",
                f"compressed_size: {metadata.get('compressed_size', 0)}",
                f"uncompressed_size: {metadata.get('uncompressed_size', 0)}",
                f"region_count: {metadata.get('region_count', 0)}",
                f"avg_region_size: {metadata.get('avg_region_size', 0)}",
                f"pack_path: {metadata.get('pack_path')}",
                f"last_updated: {metadata.get('last_updated')}",
            ]
        )
    except PackIndexError as exc:
        if exc.error_type != "PACK_NOT_FOUND":
            raise

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


def _resolve_indexed_pack_path(pack_id: str) -> Path:
    metadata = PackIndex().get_pack_metadata(pack_id)
    pack_path = Path(str(metadata.get("pack_path", "")))
    if not pack_path.exists():
        raise PackError("PACK_NOT_FOUND", f"pack not found: {pack_id}")
    return pack_path


def run_benchmark_coverage(pack_id: str, benchmark_path: Path, json_output: bool = False, planned: bool = False) -> str:
    pack_path = _resolve_indexed_pack_path(pack_id)
    summary = run_coverage_benchmark(pack_path=pack_path, benchmark_path=benchmark_path, planned=planned)
    if json_output:
        return json.dumps(summary, sort_keys=True)
    return format_coverage_text(summary)


def _load_pack_claim_models(pack_spec: str) -> tuple[list[KnowledgeClaim], Path]:
    pack_path = resolve_pack_path(pack_spec)
    claims_path = pack_path / "claims.jsonl"
    if not claims_path.exists():
        raise PackError("PACK_NOT_FOUND", f"missing claims.jsonl in {pack_path}")
    claims: list[KnowledgeClaim] = []
    for line in claims_path.read_text().splitlines():
        if not line.strip():
            continue
        claims.append(KnowledgeClaim.from_dict(json.loads(line)))
    return claims, pack_path


def run_region_list(pack_spec: str, json_output: bool = False, canonicalize: bool = False) -> str:
    claims, _ = _load_pack_claim_models(pack_spec)
    regions = sorted(RuntimeRegionIndex(claims, canonicalize=canonicalize).regions, key=lambda item: item.region_id)
    if json_output:
        payload = [
            {
                "region_id": region.region_id,
                "relations": sorted(region.relations),
                "size": region.size,
                "sample_subjects": sorted(region.subjects)[:5],
            }
            for region in regions
        ]
        return json.dumps(payload, sort_keys=True)
    lines = ["status: REGION_LIST", "regions:"]
    if not regions:
        lines.append("  - none")
    else:
        for region in regions:
            lines.append(f"  - region_id: {region.region_id}")
            lines.append(f"    relations: {','.join(sorted(region.relations))}")
            lines.append(f"    size: {region.size}")
            lines.append(f"    sample_subjects: {','.join(sorted(region.subjects)[:5])}")
    return "\n".join(lines)


def run_region_info(region_id: str, pack_spec: str, json_output: bool = False) -> str:
    claims, _ = _load_pack_claim_models(pack_spec)
    match = next((item for item in RuntimeRegionIndex(claims).regions if item.region_id == region_id), None)
    if match is None:
        raise PackError("REGION_NOT_FOUND", f"region not found: {region_id}")
    payload = {
        "region_id": match.region_id,
        "relations": sorted(match.relations),
        "size": match.size,
        "sample_subjects": sorted(match.subjects)[:10],
    }
    if json_output:
        return json.dumps(payload, sort_keys=True)
    return "\n".join(
        [
            "status: REGION_INFO",
            f"region_id: {payload['region_id']}",
            f"relations: {','.join(payload['relations'])}",
            f"size: {payload['size']}",
            f"sample_subjects: {','.join(payload['sample_subjects'])}",
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


def run_pack_index(scan_dirs: list[Path], json_output: bool = False) -> str:
    index = PackIndex()
    before = index.load_index()
    index.build_index(scan_dirs)
    after = index.load_index()
    stale_count = sum(1 for item in after.values() if bool(item.get("stale")))
    payload = {"status": "INDEXED", "packs_found": len(after), "stale": stale_count}
    if json_output:
        return json.dumps(payload, sort_keys=True)
    return "\n".join(
        [
            "status: INDEXED",
            f"packs_found: {len(after)}",
            f"stale: {stale_count}",
            f"updated_entries: {max(0, len(after) - len(before))}",
        ]
    )


def run_pack_list_index(include_stale: bool = False, json_output: bool = False) -> str:
    items = PackIndex().list_packs(include_stale=include_stale)
    if json_output:
        return json.dumps(items, sort_keys=True)
    lines = ["status: PACK_INDEX_LIST", "packs:"]
    if not items:
        lines.append("  - none")
    else:
        for item in items:
            lines.append(
                (
                    f"  - {item.get('pack_id')}@{item.get('version')} "
                    f"lifecycle={item.get('lifecycle_status')} claims={item.get('claim_count')} "
                    f"stale={item.get('stale')} path={item.get('pack_path')}"
                )
            )
    return "\n".join(lines)


def run_pack_freeze(pack_path: Path, json_output: bool = False) -> str:
    manager = PackLifecycleManager()
    manager.freeze_pack(pack_path)
    PackIndex().update_entry(pack_path)
    payload = {"status": "FROZEN", "path": str(pack_path)}
    if json_output:
        return json.dumps(payload, sort_keys=True)
    return "\n".join(["status: FROZEN", f"path: {pack_path}"])


def run_pack_archive(pack_path: Path, json_output: bool = False) -> str:
    manager = PackLifecycleManager()
    manager.archive_pack(pack_path)
    PackIndex().update_entry(pack_path)
    payload = {"status": "ARCHIVED", "path": str(pack_path)}
    if json_output:
        return json.dumps(payload, sort_keys=True)
    return "\n".join(["status: ARCHIVED", f"path: {pack_path}"])


def run_pack_create(name: str, base_dir: Path, json_output: bool = False) -> str:
    pack_dir = Path(base_dir) / name
    if pack_dir.exists():
        raise PackError("PACK_EXISTS", f"pack already exists: {pack_dir}")
    pack_dir.mkdir(parents=True, exist_ok=False)
    metadata = {
        "id": name,
        "version": "1.0.0",
        "domain": "general",
        "claim_count": 0,
        "lifecycle_status": "candidate",
    }
    (pack_dir / "pack.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    (pack_dir / "claims.jsonl").write_text("")
    (pack_dir / "provenance.jsonl").write_text("")
    PackIndex().update_entry(pack_dir)
    payload = {"status": "CREATED", "path": str(pack_dir)}
    if json_output:
        return json.dumps(payload, sort_keys=True)
    return "\n".join(["status: CREATED", f"path: {pack_dir}"])


def run_pack_hash(pack_spec: str, json_output: bool = False) -> str:
    path = resolve_pack_path(pack_spec)
    result = compute_pack_hash(path)
    payload = {
        "status": "PACK_HASH",
        "pack": pack_spec,
        "path": str(path),
        "pack_hash": result.pack_hash,
        "algorithm": result.algorithm,
    }
    if json_output:
        return json.dumps(payload, sort_keys=True)
    return "\n".join(
        [
            "status: PACK_HASH",
            f"pack: {pack_spec}",
            f"path: {path}",
            f"pack_hash: {result.pack_hash}",
            f"algorithm: {result.algorithm}",
        ]
    )


def run_pack_verify(
    pack_spec: str,
    json_output: bool = False,
    write_artifacts: bool = False,
    output_dir: Path | None = None,
) -> str:
    path = resolve_pack_path(pack_spec)
    if write_artifacts:
        import shutil
        from vcse.packs.integrity import build_manifest

        manifest = build_manifest(path)
        (path / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path / "manifest.json", output_dir / "manifest.json")
    result = verify_pack_integrity(path)
    payload = {"pack": pack_spec, "path": str(path), **result}
    if json_output:
        return json.dumps(payload, sort_keys=True)
    lines = [
        f"status: {result.get('status', 'INVALID')}",
        f"pack: {pack_spec}",
        f"path: {path}",
    ]
    if result.get("reason"):
        lines.append(f"reason: {result['reason']}")
    if result.get("pack_hash"):
        lines.append(f"pack_hash: {result['pack_hash']}")
    if result.get("merkle_root"):
        lines.append(f"merkle_root: {result['merkle_root']}")
    return "\n".join(lines)


def run_pack_diff(pack_a_spec: str, pack_b_spec: str, json_output: bool = False) -> str:
    pack_a = resolve_pack_path(pack_a_spec)
    pack_b = resolve_pack_path(pack_b_spec)
    result = diff_packs(pack_a, pack_b)
    payload = {
        "status": "PACK_DIFF",
        "pack_a": pack_a_spec,
        "pack_b": pack_b_spec,
        **result,
    }
    if json_output:
        return json.dumps(payload, sort_keys=True)
    return "\n".join(
        [
            "status: PACK_DIFF",
            f"pack_a: {pack_a_spec}",
            f"pack_b: {pack_b_spec}",
            f"added: {len(result['added'])}",
            f"removed: {len(result['removed'])}",
            f"unchanged: {result['unchanged']}",
        ]
    )


def run_pack_sign(
    pack_spec: str,
    json_output: bool = False,
    write_artifacts: bool = False,
    output_dir: Path | None = None,
) -> str:
    path = resolve_pack_path(pack_spec)
    result = sign_pack_manifest(path, write_artifacts=write_artifacts, output_dir=output_dir)
    payload = {"status": "PACK_SIGNED", "pack": pack_spec, "path": str(path), **result}
    if json_output:
        return json.dumps(payload, sort_keys=True)
    return "\n".join(
        [
            "status: PACK_SIGNED",
            f"pack: {pack_spec}",
            f"path: {path}",
            f"pack_hash: {result.get('pack_hash', '')}",
            f"merkle_root: {result.get('merkle_root', '')}",
            f"algorithm: {result.get('algorithm', '')}",
        ]
    )


def run_pack_verify_signature(pack_spec: str, json_output: bool = False) -> str:
    path = resolve_pack_path(pack_spec)
    result = verify_pack_signature(path)
    payload = {"pack": pack_spec, "path": str(path), **result}
    if json_output:
        return json.dumps(payload, sort_keys=True)
    lines = [
        f"status: {result.get('status', 'INVALID')}",
        f"pack: {pack_spec}",
        f"path: {path}",
    ]
    if result.get("reason"):
        lines.append(f"reason: {result['reason']}")
    if result.get("algorithm"):
        lines.append(f"algorithm: {result['algorithm']}")
    return "\n".join(lines)


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


def _goal_from_normalized_query(
    subject: str,
    relation: str,
    obj: str | None,
    preload_claims: list[dict[str, str]],
) -> tuple[str, str, str] | None:
    subject_clean = subject.strip()
    if not subject_clean:
        return None

    explicit_index: dict[tuple[str, str], set[str]] = {}
    for claim in preload_claims:
        s = str(claim.get("subject", "")).strip()
        r = str(claim.get("relation", "")).strip()
        o = str(claim.get("object", "")).strip()
        if not s or not r or not o:
            continue
        explicit_index.setdefault((s.lower(), r.lower()), set()).add(o)

    inferred_index: dict[tuple[str, str], set[str]] = {}
    explicit_knowledge_claims = _knowledge_claims_from_dict_claims(preload_claims)
    for inferred_claim in infer_inverse_claims(explicit_knowledge_claims):
        inferred_index.setdefault((inferred_claim.subject.lower(), inferred_claim.relation.lower()), set()).add(
            inferred_claim.object
        )
    for inferred_claim in infer_transitive_claims(explicit_knowledge_claims):
        inferred_index.setdefault((inferred_claim.subject.lower(), inferred_claim.relation.lower()), set()).add(
            inferred_claim.object
        )

    def _values(subject_key: str, relation_key: str) -> list[str]:
        explicit = sorted(explicit_index.get((subject_key, relation_key), set()))
        if explicit:
            return explicit
        return sorted(inferred_index.get((subject_key, relation_key), set()))

    if relation == "capital_of":
        values = _values(subject_clean.lower(), "has_capital")
        if len(values) == 1:
            return subject_clean, "has_capital", values[0]
        inferred_values = sorted(inferred_index.get((subject_clean.lower(), "capital_of"), set()))
        if len(inferred_values) == 1:
            country = inferred_values[0]
            return country, "has_capital", subject_clean
        return None

    if relation == "located_in_country":
        values = _values(subject_clean.lower(), "located_in_country")
        if len(values) == 1:
            return subject_clean, "located_in_country", values[0]
        values = _values(subject_clean.lower(), "capital_of")
        if len(values) == 1:
            return subject_clean, "capital_of", values[0]
        return None

    if relation == "part_of":
        values = _values(subject_clean.lower(), "part_of")
        if len(values) == 1:
            return subject_clean, "part_of", values[0]
        values = _values(subject_clean.lower(), "located_in_continent")
        if len(values) == 1:
            return subject_clean, "located_in_continent", values[0]
        return None

    if relation == "uses_currency":
        values = _values(subject_clean.lower(), "uses_currency")
        if len(values) == 1:
            return subject_clean, "uses_currency", values[0]
        return None

    if relation == "language_of":
        values: set[str] = set()
        for claim in preload_claims:
            s = str(claim.get("subject", "")).strip()
            r = str(claim.get("relation", "")).strip()
            o = str(claim.get("object", "")).strip()
            if r.lower() == "language_of" and o.lower() == subject_clean.lower() and s:
                values.add(s)
        if len(values) == 1:
            lang = sorted(values)[0]
            return lang, "language_of", subject_clean
        return None

    if relation == "has_country_code":
        values = _values(subject_clean.lower(), "has_country_code")
        if len(values) == 1:
            return subject_clean, "has_country_code", values[0]
        return None

    if relation == "located_in_region":
        values = _values(subject_clean.lower(), "located_in_region")
        if len(values) == 1:
            return subject_clean, "located_in_region", values[0]
        return None

    if relation == "located_in_subregion":
        values = _values(subject_clean.lower(), "located_in_subregion")
        if len(values) == 1:
            return subject_clean, "located_in_subregion", values[0]
        return None

    if relation == "instance_of" and obj is not None:
        values = {item.lower(): item for item in _values(subject_clean.lower(), "instance_of")}
        if obj == "City":
            if "city" in values:
                return subject_clean, "instance_of", values["city"]
            if "capital city" in values:
                return subject_clean, "instance_of", values["capital city"]
            return None
        if obj == "Country":
            if "country" in values:
                return subject_clean, "instance_of", values["country"]
            return None

    return None


def _goal_from_boolean_capital_query(
    subject: str,
    obj: str,
    preload_claims: list[dict[str, str]],
) -> tuple[tuple[str, str, str], InferenceExplanation | None] | None:
    subject_clean = subject.strip()
    obj_clean = obj.strip()
    if not subject_clean or not obj_clean:
        return None
    explicit_knowledge_claims = _knowledge_claims_from_dict_claims(preload_claims)
    inferred_claims = infer_inverse_claims(explicit_knowledge_claims)
    for claim in preload_claims:
        s = str(claim.get("subject", "")).strip()
        r = str(claim.get("relation", "")).strip()
        o = str(claim.get("object", "")).strip()
        if s.lower() == subject_clean.lower() and r.lower() == "capital_of" and o.lower() == obj_clean.lower():
            return (s, r, o), None
        if s.lower() == obj_clean.lower() and r.lower() == "has_capital" and o.lower() == subject_clean.lower():
            return (s, r, o), None
    for claim in inferred_claims:
        if (
            claim.subject.lower() == subject_clean.lower()
            and claim.relation.lower() == "capital_of"
            and claim.object.lower() == obj_clean.lower()
        ):
            return (
                (claim.subject, claim.relation, claim.object),
                build_inverse_explanation(claim),
            )
        if (
            claim.subject.lower() == obj_clean.lower()
            and claim.relation.lower() == "has_capital"
            and claim.object.lower() == subject_clean.lower()
        ):
            return (
                (claim.subject, claim.relation, claim.object),
                build_inverse_explanation(claim),
            )
    return None


def _knowledge_claims_from_dict_claims(claims: list[dict[str, str]]) -> list[KnowledgeClaim]:
    from vcse.knowledge.pack_model import KnowledgeProvenance

    converted: list[KnowledgeClaim] = []
    for claim in claims:
        subject = str(claim.get("subject", "")).strip()
        relation = str(claim.get("relation", "")).strip()
        obj = str(claim.get("object", "")).strip()
        if not subject or not relation or not obj:
            continue
        converted.append(
            KnowledgeClaim(
                subject=subject,
                relation=relation,
                object=obj,
                provenance=KnowledgeProvenance(
                    source_id="runtime",
                    source_type="runtime",
                    location="runtime",
                    evidence_text="runtime claim",
                ),
            )
        )
    return converted


def run_infer_inverse(pack_spec: str, json_output: bool = False) -> str:
    dsl_bundle, preload_claims, _ = resolve_runtime_inputs(dsl_path=None, pack_values=[pack_spec], packs_csv=None)
    _ = dsl_bundle  # for symmetry with runtime loading; inference uses claims only
    inferred = infer_inverse_claims(_knowledge_claims_from_dict_claims(preload_claims))
    if json_output:
        payload = {
            "status": "INFERENCE_COMPLETE",
            "pack": pack_spec,
            "inferred_count": len(inferred),
            "sample": [
                {
                    "subject": claim.subject,
                    "relation": claim.relation,
                    "object": claim.object,
                    "derived_from": claim.derived_from,
                    "rule": claim.rule,
                    "trust_tier": claim.trust_tier,
                }
                for claim in inferred[:10]
            ],
        }
        return json.dumps(payload, sort_keys=True)
    lines = [
        "status: INFERENCE_COMPLETE",
        f"pack: {pack_spec}",
        f"inferred_count: {len(inferred)}",
        "sample:",
    ]
    if inferred:
        for claim in inferred[:10]:
            lines.append(
                f"  - {claim.subject} {claim.relation} {claim.object} "
                f"(derived_from={claim.derived_from}, rule={claim.rule}, trust_tier={claim.trust_tier})"
            )
    else:
        lines.append("  - none")
    return "\n".join(lines)


def run_infer_transitive(pack_spec: str, json_output: bool = False) -> str:
    dsl_bundle, preload_claims, _ = resolve_runtime_inputs(dsl_path=None, pack_values=[pack_spec], packs_csv=None)
    _ = dsl_bundle
    inferred = infer_transitive_claims(_knowledge_claims_from_dict_claims(preload_claims))
    if json_output:
        payload = {
            "status": "INFERENCE_COMPLETE",
            "pack": pack_spec,
            "inferred_count": len(inferred),
            "sample": [
                {
                    "subject": claim.subject,
                    "relation": claim.relation,
                    "object": claim.object,
                    "derived_from": list(claim.derived_from),
                    "rule": claim.rule,
                    "trust_tier": claim.trust_tier,
                }
                for claim in inferred[:10]
            ],
        }
        return json.dumps(payload, sort_keys=True)
    lines = [
        "status: INFERENCE_COMPLETE",
        f"pack: {pack_spec}",
        f"inferred_count: {len(inferred)}",
        "sample:",
    ]
    if inferred:
        for claim in inferred[:10]:
            lines.append(
                f"  - {claim.subject} {claim.relation} {claim.object} "
                f"(derived_from={claim.derived_from[0]},{claim.derived_from[1]}, "
                f"rule={claim.rule}, trust_tier={claim.trust_tier})"
            )
    else:
        lines.append("  - none")
    return "\n".join(lines)


def _default_coverage_benchmark_path() -> Path:
    return Path("benchmarks") / "general_knowledge.jsonl"


def _collect_inference_observations(
    *,
    pack_spec: str,
    benchmark_path: Path | None = None,
) -> list[InferenceObservation]:
    _, preload_claims, _ = resolve_runtime_inputs(dsl_path=None, pack_values=[pack_spec], packs_csv=None)
    claim_models = _knowledge_claims_from_dict_claims(preload_claims)
    tracker = InferenceStabilityTracker()
    path = benchmark_path or _default_coverage_benchmark_path()
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        subject = str(row.get("subject", "")).strip()
        relation = str(row.get("relation", "")).strip()
        obj = str(row.get("object", "")).strip()
        if not subject or not relation or not obj:
            continue
        resolution_type = classify_resolution_for_claim(
            claim_models,
            subject=subject,
            relation=relation,
            object_=obj,
        )
        if resolution_type in {InferenceType.INVERSE, InferenceType.TRANSITIVE}:
            tracker.record("|".join([subject, relation, obj]), resolution_type.value)
    return tracker.get_counts()


def run_infer_stability(
    pack_spec: str,
    threshold: int = 2,
    benchmark_path: Path | None = None,
    json_output: bool = False,
) -> str:
    if threshold < 1:
        raise ValueError("INVALID_THRESHOLD: --threshold must be >= 1")
    observations = _collect_inference_observations(pack_spec=pack_spec, benchmark_path=benchmark_path)
    stable = [item for item in observations if item.occurrences >= threshold]
    inverse_total = sum(1 for item in observations if item.inference_type == InferenceType.INVERSE.value)
    transitive_total = sum(1 for item in observations if item.inference_type == InferenceType.TRANSITIVE.value)
    inverse_stable = sum(1 for item in stable if item.inference_type == InferenceType.INVERSE.value)
    transitive_stable = sum(1 for item in stable if item.inference_type == InferenceType.TRANSITIVE.value)
    if json_output:
        payload = {
            "status": "INFERENCE_STABILITY_COMPLETE",
            "pack": pack_spec,
            "benchmark_path": str(benchmark_path or _default_coverage_benchmark_path()),
            "threshold": threshold,
            "total_inferred_claims": len(observations),
            "stable_inferred_claims": len(stable),
            "inverse_inferred_count": inverse_total,
            "transitive_inferred_count": transitive_total,
            "stable_inverse_count": inverse_stable,
            "stable_transitive_count": transitive_stable,
        }
        return json.dumps(payload, sort_keys=True)
    lines = [
        "status: INFERENCE_STABILITY_COMPLETE",
        f"pack: {pack_spec}",
        f"benchmark_path: {benchmark_path or _default_coverage_benchmark_path()}",
        f"stability_threshold: {threshold}",
        f"total_inferred_claims: {len(observations)}",
        f"stable_inferred_claims: {len(stable)}",
        "breakdown:",
        f"  inverse: {inverse_total}",
        f"  transitive: {transitive_total}",
        f"  stable_inverse: {inverse_stable}",
        f"  stable_transitive: {transitive_stable}",
    ]
    return "\n".join(lines)


def run_infer_promote(
    pack_spec: str,
    threshold: int = 2,
    benchmark_path: Path | None = None,
    json_output: bool = False,
    write_output: bool = False,
    output_path: Path | None = None,
    as_pack: str | None = None,
) -> str:
    if threshold < 1:
        raise ValueError("INVALID_THRESHOLD: --threshold must be >= 1")
    if output_path is not None and not write_output:
        raise ValueError("INVALID_PROMOTION_FLAGS: --output requires --write")
    observations = _collect_inference_observations(pack_spec=pack_spec, benchmark_path=benchmark_path)
    _, preload_claims, _ = resolve_runtime_inputs(dsl_path=None, pack_values=[pack_spec], packs_csv=None)
    claim_models = _knowledge_claims_from_dict_claims(preload_claims)
    inverse_map = {claim.key: (claim.derived_from,) for claim in infer_inverse_claims(claim_models)}
    transitive_map = {claim.key: tuple(claim.derived_from) for claim in infer_transitive_claims(claim_models)}

    enriched: list[SimpleNamespace] = []
    for item in observations:
        if item.occurrences < threshold:
            continue
        if item.inference_type == InferenceType.INVERSE.value:
            sources = inverse_map.get(item.claim_key, ())
        elif item.inference_type == InferenceType.TRANSITIVE.value:
            sources = transitive_map.get(item.claim_key, ())
        else:
            sources = ()
        enriched.append(
            SimpleNamespace(
                claim_key=item.claim_key,
                inference_type=item.inference_type,
                occurrences=item.occurrences,
                source_claims=tuple(sources),
            )
        )
    stable_sorted = sorted(enriched, key=lambda item: (item.claim_key, item.inference_type))
    promoted = promote_stable_claims(stable_sorted, threshold=threshold)

    written_paths: list[str] = []
    should_write = write_output or (as_pack is not None)
    if should_write:
        target = output_path or Path("promoted_claims.jsonl")
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps(
                {
                    "subject": claim.subject,
                    "relation": claim.relation,
                    "object": claim.object,
                    "source_claims": list(claim.source_claims),
                    "inference_type": claim.inference_type,
                    "promoted_at": claim.promoted_at,
                },
                sort_keys=True,
            )
            for claim in promoted
        ]
        target.write_text("\n".join(lines) + ("\n" if lines else ""))
        written_paths.append(str(target))
        if as_pack:
            build_result = build_pack_from_promoted_claims(
                promoted_claims=promoted,
                pack_id=as_pack,
                source_pack=pack_spec,
                threshold=threshold,
            )
            written_paths.append(str(build_result.pack_dir))

    if json_output:
        payload = {
            "status": "INFERENCE_PROMOTION_CANDIDATES",
            "pack": pack_spec,
            "benchmark_path": str(benchmark_path or _default_coverage_benchmark_path()),
            "threshold": threshold,
            "stable_inferred_count": len(promoted),
            "write": should_write,
            "written_paths": written_paths,
            "candidates": [
                {
                    "subject": item.subject,
                    "relation": item.relation,
                    "object": item.object,
                    "source_claims": list(item.source_claims),
                    "source_inference": item.inference_type,
                    "target_tier": "T0_CANDIDATE",
                    "promoted_at": item.promoted_at,
                }
                for item in promoted
            ],
        }
        return json.dumps(payload, sort_keys=True)
    lines = [
        f"Stable inferred claims (threshold={threshold}):",
    ]
    if not promoted:
        lines.append("- none")
        return "\n".join(lines)
    for item in promoted:
        lines.append(f"- {item.subject} {item.relation} {item.object} ({item.inference_type})")
    if should_write:
        lines.append(f"written: {', '.join(written_paths)}")
    return "\n".join(lines)


def _classify_query_type(text: str):
    from vcse.interaction.response_modes import QueryType

    clean = text.strip().lower()
    if clean.startswith(("what ", "who ", "where ", "when ", "which ", "how ")):
        return QueryType.FACT
    if clean.startswith(("is ", "are ", "can ", "could ", "would ", "should ", "does ", "do ", "did ")):
        return QueryType.BOOLEAN
    return QueryType.BOOLEAN


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
    try:
        return PackActivator().activate(specs)
    except PackError as exc:
        if exc.error_type != "MISSING_DEPENDENCY":
            raise
        fallback_claims: list[dict[str, str]] = []
        for spec in specs:
            metadata = PackIndex().get_pack_metadata(spec)
            pack_path = Path(str(metadata.get("pack_path", "")))
            claims_path = pack_path / "claims.jsonl"
            if not claims_path.exists() or not pack_path.exists():
                raise PackError("PACK_NOT_FOUND", f"pack not found: {spec}")
            runtime_claims = load_runtime_claims_if_valid(pack_path, str(metadata.get("pack_id", spec)))
            if runtime_claims is not None:
                fallback_claims.extend(runtime_claims)
                continue
            for line in claims_path.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                fallback_claims.append(
                    {
                        "subject": str(row.get("subject", "")),
                        "relation": str(row.get("relation", "")),
                        "object": str(row.get("object", "")),
                    }
                )
        from vcse.dsl.schema import CapabilityBundle
        from vcse.packs.activator import ActivationResult
        return ActivationResult(
            selected_packs=specs,
            ordered_dependencies=specs,
            dsl_bundle=CapabilityBundle(name="runtime_packs_fallback", version="1.0.0"),
            knowledge_claims=fallback_claims,
            constraints=[],
        )


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


def _resolve_planned_store_path(pack_values: list[str] | None, packs_csv: str | None) -> Path | None:
    specs: list[str] = []
    for value in pack_values or []:
        clean = value.strip()
        if clean:
            specs.append(clean)
    if packs_csv:
        specs.extend(item.strip() for item in packs_csv.split(",") if item.strip())
    if len(specs) != 1:
        return None
    metadata = PackIndex().get_pack_metadata(specs[0])
    pack_id = str(metadata.get("pack_id", specs[0]))
    path = runtime_store_path_for_pack(pack_id)
    if not path.exists():
        return None
    return path


def _domain_spec_summary(spec, source: Path) -> dict[str, object]:
    return {
        "domain_id": spec.domain_id,
        "name": spec.name,
        "version": spec.version,
        "source": str(source),
        "relation_count": len(spec.relations),
        "query_pattern_count": len(spec.query_patterns),
        "shard_rule_count": len(spec.shard_rules),
        "inference_rule_count": len(spec.inference_rules),
        "benchmark_template_count": len(spec.benchmark_templates),
    }


def run_domain_list(json_output: bool = False) -> str:
    candidates = sorted(Path("domains").glob("*.y*ml"))
    rows: list[dict[str, object]] = []
    for source in sorted(candidates, key=lambda p: str(p)):
        spec = load_domain_spec(source)
        rows.append(_domain_spec_summary(spec, source))
    if json_output:
        return json.dumps({"domains": rows}, sort_keys=True)
    lines = [f"domain_count: {len(rows)}"]
    for row in rows:
        lines.append(f"- domain_id: {row['domain_id']}")
        lines.append(f"  relation_count: {row['relation_count']}")
        lines.append(f"  query_pattern_count: {row['query_pattern_count']}")
        lines.append(f"  shard_rule_count: {row['shard_rule_count']}")
        lines.append(f"  inference_rule_count: {row['inference_rule_count']}")
        lines.append(f"  benchmark_template_count: {row['benchmark_template_count']}")
    return "\n".join(lines)


def run_domain_inspect(domain_id: str, json_output: bool = False) -> str:
    target = Path("domains") / f"{domain_id}.yaml"
    spec = load_domain_spec(target)
    payload = _domain_spec_summary(spec, target)
    if json_output:
        return json.dumps(payload, sort_keys=True)
    lines = [
        f"domain_id: {payload['domain_id']}",
        f"name: {payload['name']}",
        f"version: {payload['version']}",
        f"source: {payload['source']}",
        f"relation_count: {payload['relation_count']}",
        f"query_pattern_count: {payload['query_pattern_count']}",
        f"shard_rule_count: {payload['shard_rule_count']}",
        f"inference_rule_count: {payload['inference_rule_count']}",
        f"benchmark_template_count: {payload['benchmark_template_count']}",
    ]
    return "\n".join(lines)


def run_domain_validate(path: Path, json_output: bool = False) -> str:
    spec = load_domain_spec(path)
    payload = _domain_spec_summary(spec, path)
    payload["status"] = "VALID"
    if json_output:
        return json.dumps(payload, sort_keys=True)
    lines = [
        "status: VALID",
        f"domain_id: {payload['domain_id']}",
        f"relation_count: {payload['relation_count']}",
        f"query_pattern_count: {payload['query_pattern_count']}",
        f"shard_rule_count: {payload['shard_rule_count']}",
        f"inference_rule_count: {payload['inference_rule_count']}",
        f"benchmark_template_count: {payload['benchmark_template_count']}",
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
    benchmark_parser.add_argument("path", nargs="?")
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
    benchmark_parser.add_argument("--benchmark")
    benchmark_parser.add_argument("--planned", action="store_true")

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
    ask_parser.add_argument("--no-explain", action="store_true")
    ask_parser.add_argument("--planned", action="store_true")
    ask_parser.add_argument("--planned-debug", action="store_true")

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
    pack_validate_parser.add_argument("pack_ref")
    pack_validate_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_certify_parser = pack_subparsers.add_parser("certify")
    pack_certify_parser.add_argument("pack_id")
    pack_certify_parser.add_argument("--output", required=True, dest="output_pack_id")
    pack_certify_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_merge_parser = pack_subparsers.add_parser("merge")
    pack_merge_parser.add_argument("source_pack_id")
    pack_merge_parser.add_argument("--into", required=True, dest="target_pack_id")
    pack_merge_parser.add_argument("--output", dest="output_pack_id")
    pack_merge_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_compile_parser = pack_subparsers.add_parser("compile")
    pack_compile_parser.add_argument("pack_id")
    pack_compile_parser.add_argument("--output", type=Path)
    pack_compile_parser.add_argument("--force", action="store_true")
    pack_compile_parser.add_argument("--incremental", action="store_true")
    pack_compile_parser.add_argument("--stats", action="store_true")
    pack_compile_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_store_info_parser = pack_subparsers.add_parser("store-info")
    pack_store_info_parser.add_argument("pack_id")
    pack_store_info_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_review_parser = pack_subparsers.add_parser("review")
    pack_review_parser.add_argument("pack_ref")
    pack_review_parser.add_argument("--json", action="store_true", dest="json_output")
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
    pack_list_parser.add_argument("--stale", action="store_true")
    pack_info_parser = pack_subparsers.add_parser("info")
    pack_info_parser.add_argument("pack_id")
    pack_info_parser.add_argument("--version")
    pack_info_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_audit_parser = pack_subparsers.add_parser("audit")
    pack_audit_parser.add_argument("target")
    pack_audit_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_index_parser = pack_subparsers.add_parser("index")
    pack_index_parser.add_argument("--dirs", nargs="+", type=Path)
    pack_index_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_freeze_parser = pack_subparsers.add_parser("freeze")
    pack_freeze_parser.add_argument("pack_id_version")
    pack_freeze_parser.add_argument("--path", required=True, type=Path)
    pack_freeze_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_archive_parser = pack_subparsers.add_parser("archive")
    pack_archive_parser.add_argument("pack_id_version")
    pack_archive_parser.add_argument("--path", required=True, type=Path)
    pack_archive_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_create_parser = pack_subparsers.add_parser("create")
    pack_create_parser.add_argument("name")
    pack_create_parser.add_argument("--path", required=True, type=Path)
    pack_create_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_hash_parser = pack_subparsers.add_parser("hash")
    pack_hash_parser.add_argument("pack")
    pack_hash_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_verify_parser = pack_subparsers.add_parser("verify")
    pack_verify_parser.add_argument("pack")
    pack_verify_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_verify_parser.add_argument("--strict", action="store_true")
    pack_verify_parser.add_argument("--write-artifacts", action="store_true")
    pack_verify_parser.add_argument("--output-dir", type=Path)
    pack_diff_parser = pack_subparsers.add_parser("diff")
    pack_diff_parser.add_argument("pack_a")
    pack_diff_parser.add_argument("pack_b")
    pack_diff_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_sign_parser = pack_subparsers.add_parser("sign")
    pack_sign_parser.add_argument("pack")
    pack_sign_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_sign_parser.add_argument("--write-artifacts", action="store_true")
    pack_sign_parser.add_argument("--output-dir", type=Path)
    pack_verify_sig_parser = pack_subparsers.add_parser("verify-signature")
    pack_verify_sig_parser.add_argument("pack")
    pack_verify_sig_parser.add_argument("--json", action="store_true", dest="json_output")
    pack_verify_sig_parser.add_argument("--strict", action="store_true")

    region_parser = subparsers.add_parser("region")
    region_subparsers = region_parser.add_subparsers(dest="region_command")
    region_list_parser = region_subparsers.add_parser(
        "list",
        help="List semantic regions (exact relation by default; use --canonical to merge inverses).",
    )
    region_list_parser.add_argument("--pack", required=True, dest="pack_spec")
    region_list_parser.add_argument("--json", action="store_true", dest="json_output")
    region_list_parser.add_argument("--canonical", action="store_true", dest="canonicalize")
    region_info_parser = region_subparsers.add_parser(
        "info",
        help="Inspect one semantic region by region id.",
    )
    region_info_parser.add_argument("region_id")
    region_info_parser.add_argument("--pack", required=True, dest="pack_spec")
    region_info_parser.add_argument("--json", action="store_true", dest="json_output")

    domain_parser = subparsers.add_parser("domain")
    domain_subparsers = domain_parser.add_subparsers(dest="domain_command")
    domain_list_parser = domain_subparsers.add_parser("list")
    domain_list_parser.add_argument("--json", action="store_true", dest="json_output")
    domain_inspect_parser = domain_subparsers.add_parser("inspect")
    domain_inspect_parser.add_argument("domain_id")
    domain_inspect_parser.add_argument("--json", action="store_true", dest="json_output")
    domain_validate_parser = domain_subparsers.add_parser("validate")
    domain_validate_parser.add_argument("path", type=Path)
    domain_validate_parser.add_argument("--json", action="store_true", dest="json_output")

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

    infer_parser = subparsers.add_parser("infer")
    infer_subparsers = infer_parser.add_subparsers(dest="infer_command")
    infer_inverse_parser = infer_subparsers.add_parser("inverse")
    infer_inverse_parser.add_argument("--pack", required=True)
    infer_inverse_parser.add_argument("--json", action="store_true", dest="json_output")
    infer_transitive_parser = infer_subparsers.add_parser("transitive")
    infer_transitive_parser.add_argument("--pack", required=True)
    infer_transitive_parser.add_argument("--json", action="store_true", dest="json_output")
    infer_stability_parser = infer_subparsers.add_parser("stability")
    infer_stability_parser.add_argument("--pack", required=True)
    infer_stability_parser.add_argument("--threshold", type=int, default=2)
    infer_stability_parser.add_argument("--benchmark", type=Path)
    infer_stability_parser.add_argument("--json", action="store_true", dest="json_output")
    infer_promote_parser = infer_subparsers.add_parser("promote")
    infer_promote_parser.add_argument("--pack", required=True)
    infer_promote_parser.add_argument("--threshold", type=int, default=2)
    infer_promote_parser.add_argument("--benchmark", type=Path)
    infer_promote_parser.add_argument("--write", action="store_true", dest="write_output")
    infer_promote_parser.add_argument("--output", type=Path)
    infer_promote_parser.add_argument("--as-pack")
    infer_promote_parser.add_argument("--json", action="store_true", dest="json_output")

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

    agent_parser = subparsers.add_parser("agent")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command")
    agent_run_parser = agent_subparsers.add_parser("run")
    agent_run_parser.add_argument("task_file", type=Path)
    agent_run_parser.add_argument("--json", action="store_true", dest="json_output")
    agent_run_parser.add_argument("--debug", action="store_true")
    agent_run_parser.add_argument("--workspace", dest="workspace_id")
    agent_plan_parser = agent_subparsers.add_parser("plan")
    agent_plan_parser.add_argument("task_file", type=Path)
    agent_plan_parser.add_argument("--json", action="store_true", dest="json_output")
    agent_resume_parser = agent_subparsers.add_parser("resume")
    agent_resume_parser.add_argument("task_id")
    agent_resume_parser.add_argument("--json", action="store_true", dest="json_output")
    agent_resume_parser.add_argument("--workspace", dest="workspace_id", required=True)
    agent_status_parser = agent_subparsers.add_parser("status")
    agent_status_parser.add_argument("task_id")
    agent_status_parser.add_argument("--workspace", dest="workspace_id")
    agent_status_parser.add_argument("--json", action="store_true", dest="json_output")

    workspace_parser = subparsers.add_parser("workspace")
    workspace_subparsers = workspace_parser.add_subparsers(dest="workspace_command")
    ws_create_parser = workspace_subparsers.add_parser("create")
    ws_create_parser.add_argument("name")
    ws_create_parser.add_argument("--owner", required=True)
    ws_create_parser.add_argument("--id")
    ws_create_parser.add_argument("--json", action="store_true", dest="json_output")
    ws_list_parser = workspace_subparsers.add_parser("list")
    ws_list_parser.add_argument("--json", action="store_true", dest="json_output")
    ws_delete_parser = workspace_subparsers.add_parser("delete")
    ws_delete_parser.add_argument("id")
    ws_delete_parser.add_argument("--json", action="store_true", dest="json_output")
    ws_export_parser = workspace_subparsers.add_parser("export")
    ws_export_parser.add_argument("id")
    ws_export_parser.add_argument("--output", required=True, type=Path)
    ws_export_parser.add_argument("--json", action="store_true", dest="json_output")
    ws_import_parser = workspace_subparsers.add_parser("import")
    ws_import_parser.add_argument("file", type=Path)
    ws_import_parser.add_argument("--force", action="store_true")
    ws_import_parser.add_argument("--json", action="store_true", dest="json_output")
    ws_tasks_parser = workspace_subparsers.add_parser("tasks")
    ws_tasks_parser.add_argument("id")
    ws_tasks_parser.add_argument("--json", action="store_true", dest="json_output")

    # CAKE subparser
    cake_parser = subparsers.add_parser("cake", help="Controlled Acquisition of Knowledge Engine")
    cake_subparsers = cake_parser.add_subparsers(dest="cake_command")

    cake_validate_parser = cake_subparsers.add_parser("validate", help="Validate a CAKE source config")
    cake_validate_parser.add_argument("--source", required=True, help="Path to source config JSON")

    cake_run_parser = cake_subparsers.add_parser("run", help="Run CAKE acquisition pipeline")
    cake_run_parser.add_argument("--source", required=True, help="Path to source config JSON")
    cake_run_parser.add_argument("--dry-run", action="store_true", dest="dry_run", help="Validate and extract without writing")
    cake_run_parser.add_argument("--limit", type=int, default=None, help="Max items to fetch per source")
    cake_run_parser.add_argument("--allow-http", action="store_true", dest="allow_http", help="Enable HTTP transport (off by default)")
    cake_run_parser.add_argument("--transport", choices=["file", "http"], default="file", help="Transport type (default: file)")
    cake_run_parser.add_argument("--allow-partial", action="store_true", dest="allow_partial", help="Continue on per-source failure")
    cake_run_parser.add_argument("--incremental", action="store_true", dest="incremental", help="Skip unchanged sources by snapshot hash")

    cake_report_parser = cake_subparsers.add_parser("report", help="Display a CAKE run report")
    cake_report_parser.add_argument("report_file", help="Path to a CakeRunReport JSON file")

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
            if args.path == "coverage":
                pack_values = [item.strip() for item in (args.pack_values or []) if item and item.strip()]
                if len(pack_values) != 1:
                    raise ValueError("INVALID_BENCHMARK_COVERAGE: benchmark coverage requires exactly one --pack <pack_id>")
                benchmark_file = Path(args.benchmark) if args.benchmark else (Path("benchmarks") / "general_knowledge.jsonl")
                output = run_benchmark_coverage(
                    pack_values[0],
                    benchmark_file,
                    json_output=args.json_output,
                    planned=args.planned,
                )
                print(output)
                return
            if not args.path:
                raise ValueError("MISSING_ARGUMENT: benchmark path is required")
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
                    allow_query_normalization=(args.dsl is None),
                    explain_inferred=(not args.no_explain),
                    planned=args.planned,
                    planned_debug=args.planned_debug,
                    planned_store_path=(
                        _resolve_planned_store_path(args.pack_values, args.packs) if args.planned else None
                    ),
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
                text = run_pack_validate_review(args.pack_ref, json_output=args.json_output)
                print(text)
                if "status: INVALID" in text and not args.json_output:
                    raise SystemExit(2)
                if args.json_output:
                    payload = json.loads(text)
                    if not payload.get("passed", False):
                        raise SystemExit(2)
                return
            if args.pack_command == "certify":
                text = run_pack_certify(args.pack_id, args.output_pack_id, json_output=args.json_output)
                print(text)
                if args.json_output:
                    payload = json.loads(text)
                    if payload.get("status") != "CERTIFICATION_PASSED":
                        raise SystemExit(2)
                elif "status: CERTIFICATION_PASSED" not in text:
                    raise SystemExit(2)
                return
            if args.pack_command == "review":
                print(run_pack_review(args.pack_ref, json_output=args.json_output))
                return
            if args.pack_command == "merge":
                text = run_pack_merge(
                    args.source_pack_id,
                    args.target_pack_id,
                    output_pack_id=args.output_pack_id,
                    json_output=args.json_output,
                )
                print(text)
                if args.json_output:
                    payload = json.loads(text)
                    if payload.get("status") != "MERGE_PASSED":
                        raise SystemExit(2)
                elif "status: MERGE_PASSED" not in text:
                    raise SystemExit(2)
                return
            if args.pack_command == "compile":
                text = run_pack_compile_with_mode(
                    args.pack_id,
                    output=args.output,
                    force=args.force,
                    incremental=args.incremental,
                    stats=args.stats,
                    json_output=args.json_output,
                )
                print(text)
                if args.json_output:
                    payload = json.loads(text)
                    if payload.get("status") not in {"REBUILT", "NO_CHANGES"}:
                        raise SystemExit(2)
                elif "status: REBUILT" not in text and "status: NO_CHANGES" not in text:
                    raise SystemExit(2)
                return
            if args.pack_command == "store-info":
                print(run_pack_store_info(args.pack_id, json_output=args.json_output))
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
                if args.stale:
                    print(run_pack_list_index(include_stale=True, json_output=args.json_output))
                else:
                    print(run_pack_list(json_output=args.json_output))
                return
            if args.pack_command == "info":
                print(run_pack_info(args.pack_id, version=args.version, json_output=args.json_output))
                return
            if args.pack_command == "audit":
                print(run_pack_audit(args.target, json_output=args.json_output))
                return
            if args.pack_command == "index":
                scan_dirs = args.dirs or [Path.home() / ".vcse" / "cake" / "packs", Path.cwd()]
                print(run_pack_index(scan_dirs, json_output=args.json_output))
                return
            if args.pack_command == "freeze":
                print(run_pack_freeze(args.path, json_output=args.json_output))
                return
            if args.pack_command == "archive":
                print(run_pack_archive(args.path, json_output=args.json_output))
                return
            if args.pack_command == "create":
                print(run_pack_create(args.name, args.path, json_output=args.json_output))
                return
            if args.pack_command == "hash":
                print(run_pack_hash(args.pack, json_output=args.json_output))
                return
            if args.pack_command == "verify":
                text = run_pack_verify(
                    args.pack,
                    json_output=args.json_output,
                    write_artifacts=args.write_artifacts,
                    output_dir=args.output_dir,
                )
                print(text)
                if args.strict:
                    if args.json_output:
                        payload = json.loads(text)
                        if not payload.get("valid", False):
                            raise SystemExit(2)
                    elif "status: VALID" not in text:
                        raise SystemExit(2)
                return
            if args.pack_command == "diff":
                print(run_pack_diff(args.pack_a, args.pack_b, json_output=args.json_output))
                return
            if args.pack_command == "sign":
                print(
                    run_pack_sign(
                        args.pack,
                        json_output=args.json_output,
                        write_artifacts=args.write_artifacts,
                        output_dir=args.output_dir,
                    )
                )
                return
            if args.pack_command == "verify-signature":
                text = run_pack_verify_signature(args.pack, json_output=args.json_output)
                print(text)
                if args.strict:
                    if args.json_output:
                        payload = json.loads(text)
                        if not payload.get("valid", False):
                            raise SystemExit(2)
                    elif "status: VALID" not in text:
                        raise SystemExit(2)
                return
        if args.command == "region":
            if args.region_command == "list":
                print(
                    run_region_list(
                        args.pack_spec,
                        json_output=args.json_output,
                        canonicalize=args.canonicalize,
                    )
                )
                return
            if args.region_command == "info":
                print(run_region_info(args.region_id, args.pack_spec, json_output=args.json_output))
                return
        if args.command == "domain":
            if args.domain_command == "list":
                print(run_domain_list(json_output=args.json_output))
                return
            if args.domain_command == "inspect":
                print(run_domain_inspect(args.domain_id, json_output=args.json_output))
                return
            if args.domain_command == "validate":
                print(run_domain_validate(args.path, json_output=args.json_output))
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
        if args.command == "infer":
            if args.infer_command == "inverse":
                print(run_infer_inverse(args.pack, json_output=args.json_output))
                return
            if args.infer_command == "transitive":
                print(run_infer_transitive(args.pack, json_output=args.json_output))
                return
            if args.infer_command == "stability":
                print(
                    run_infer_stability(
                        args.pack,
                        threshold=args.threshold,
                        benchmark_path=args.benchmark,
                        json_output=args.json_output,
                    )
                )
                return
            if args.infer_command == "promote":
                print(
                    run_infer_promote(
                        args.pack,
                        threshold=args.threshold,
                        benchmark_path=args.benchmark,
                        json_output=args.json_output,
                        write_output=args.write_output,
                        output_path=args.output,
                        as_pack=args.as_pack,
                    )
                )
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
        if args.command == "agent":
            import json as _json
            from vcse.workspace import WorkspaceManager, WorkspaceNotFound, TaskNotFound

            mgr = WorkspaceManager()

            if args.agent_command == "run":
                try:
                    task_data = _json.loads(Path(args.task_file).read_text())
                    task_obj = Task.from_dict(task_data)
                    # Persist to workspace if workspace_id provided
                    ws_id = getattr(args, "workspace_id", None)
                    if ws_id:
                        mgr.load_workspace(ws_id)  # validate exists
                        mgr.save_task(ws_id, task_obj.id, plan_task(task_obj).to_dict(), {
                            "task_id": task_obj.id,
                            "current_step": 0,
                            "completed_steps": [],
                            "results": {},
                            "status": "RUNNING",
                        })
                        # ledger event
                        mgr._store.append_ledger_event(ws_id, {
                            "event": "TASK_PERSISTED",
                            "workspace_id": ws_id,
                            "timestamp": f"{__import__('time').time():.6f}",
                            "payload": {"task_id": task_obj.id, "step_index": 0},
                        })
                    _, plan, state = run_task(task_obj)
                    if ws_id:
                        # Update final state
                        mgr.save_task(ws_id, task_obj.id, plan.to_dict(), state.to_dict())
                        mgr._store.append_ledger_event(ws_id, {
                            "event": "TASK_COMPLETED",
                            "workspace_id": ws_id,
                            "timestamp": f"{__import__('time').time():.6f}",
                            "payload": {"task_id": task_obj.id, "status": state.status.value},
                        })
                    print(f"status: {state.status.value}")
                    print(f"task_id: {state.task_id}")
                    print(f"completed_steps: {len(state.completed_steps)}")
                    print(f"results: {_json.dumps(state.results, sort_keys=True)}")
                    if args.json_output:
                        print(_json.dumps({
                            "status": state.status.value,
                            "task_id": state.task_id,
                            "completed_steps": len(state.completed_steps),
                            "results": state.results,
                            "plan_steps": len(plan.steps),
                        }))
                except (AgentError, WorkspaceNotFound) as exc:
                    print(f"status: ERROR\nerror_type: {exc.code if hasattr(exc, 'code') else 'AGENT_ERROR'}\nmessage: {exc.message if hasattr(exc, 'message') else str(exc)}")
                    raise SystemExit(2)
                except Exception as exc:
                    print(f"status: ERROR\nmessage: {exc}")
                    raise SystemExit(2)
                return
            if args.agent_command == "plan":
                try:
                    task_data = _json.loads(Path(args.task_file).read_text())
                    task_obj = Task.from_dict(task_data)
                    plan = plan_task(task_obj)
                    print(f"status: PLAN_CREATED")
                    print(f"task_id: {plan.task_id}")
                    print(f"step_count: {len(plan.steps)}")
                    for i, step in enumerate(plan.steps):
                        print(f"  step_{i}: type={step.type} tool={step.tool_name}")
                    if args.json_output:
                        print(_json.dumps(plan.to_dict(), sort_keys=True))
                except AgentError as exc:
                    print(f"status: ERROR\nerror_type: {exc.code}\nmessage: {exc.message}")
                    raise SystemExit(2)
                except Exception as exc:
                    print(f"status: ERROR\nmessage: {exc}")
                    raise SystemExit(2)
                return
            if args.agent_command == "resume":
                try:
                    ws_id = args.workspace_id
                    task_data = mgr.load_task(ws_id, args.task_id)
                    plan_dict = task_data.plan
                    state_dict = task_data.state

                    from vcse.agent.task import Plan as AgentPlan, ExecutionState as AgentExecState, Task as AgentTask
                    plan = AgentPlan.from_dict(plan_dict)
                    state = AgentExecState.from_dict(state_dict)
                    task = AgentTask(id=task_data.task_id, description="resumed", inputs={}, goal={})

                    # Use resume_task to execute only remaining steps
                    _, final_plan, final_state = resume_task(task, plan, state)
                    # Update persisted state
                    mgr.save_task(ws_id, task_data.task_id, final_plan.to_dict(), final_state.to_dict())
                    mgr._store.append_ledger_event(ws_id, {
                        "event": "TASK_RESUMED",
                        "workspace_id": ws_id,
                        "timestamp": f"{__import__('time').time():.6f}",
                        "payload": {"task_id": task_data.task_id, "step_index": final_state.current_step},
                    })
                    print(f"status: {final_state.status.value}")
                    print(f"task_id: {final_state.task_id}")
                    print(f"completed_steps: {len(final_state.completed_steps)}")
                    print(f"results: {_json.dumps(final_state.results, sort_keys=True)}")
                    if args.json_output:
                        print(_json.dumps({
                            "status": final_state.status.value,
                            "task_id": final_state.task_id,
                            "completed_steps": len(final_state.completed_steps),
                            "results": final_state.results,
                        }))
                except (WorkspaceNotFound, TaskNotFound, AgentError) as exc:
                    print(f"status: ERROR\nerror_type: {exc.code if hasattr(exc, 'code') else 'AGENT_ERROR'}\nmessage: {exc.message if hasattr(exc, 'message') else str(exc)}")
                    raise SystemExit(2)
                except Exception as exc:
                    print(f"status: ERROR\nmessage: {exc}")
                    raise SystemExit(2)
                return
            if args.agent_command == "status":
                ws_id = getattr(args, "workspace_id", None)
                if ws_id:
                    try:
                        mgr.load_workspace(ws_id)
                        task = mgr.load_task(ws_id, args.task_id)
                        state = ExecutionState.from_dict(task.state)
                        print(f"status: {state.status.value}")
                        print(f"task_id: {state.task_id}")
                        print(f"current_step: {state.current_step}")
                        print(f"completed_steps: {len(state.completed_steps)}")
                        if args.json_output:
                            print(_json.dumps(task.state, sort_keys=True))
                    except (WorkspaceNotFound, TaskNotFound):
                        print(f"status: UNKNOWN")
                        print(f"task_id: {args.task_id}")
                        print(f"message: task not found in workspace")
                else:
                    print(f"status: UNKNOWN")
                    print(f"task_id: {args.task_id}")
                    print(f"message: --workspace required for persisted status lookup")
                return
        if args.command == "workspace":
            import json as _json
            from vcse.workspace import (
                WorkspaceManager,
                WorkspaceNotFound,
                WorkspaceExists,
                ImportError,
            )
            mgr = WorkspaceManager()

            if args.workspace_command == "create":
                try:
                    ws = mgr.create_workspace(name=args.name, owner=args.owner, workspace_id=args.id)
                    print(f"status: WORKSPACE_CREATED")
                    print(f"workspace_id: {ws.id}")
                    print(f"name: {ws.name}")
                    print(f"owner: {ws.owner}")
                    if args.json_output:
                        print(_json.dumps(ws.to_dict(), sort_keys=True))
                except WorkspaceExists as exc:
                    print(f"status: ERROR\nerror_type: WORKSPACE_EXISTS\nmessage: {exc}")
                    raise SystemExit(2)
                except Exception as exc:
                    print(f"status: ERROR\nmessage: {exc}")
                    raise SystemExit(2)
                return
            if args.workspace_command == "list":
                try:
                    workspaces = mgr.list_workspaces()
                    if args.json_output:
                        print(_json.dumps([w.to_dict() for w in workspaces], sort_keys=True))
                    else:
                        print("workspaces:")
                        for ws in workspaces:
                            print(f"  - {ws.id} ({ws.name}, owner={ws.owner})")
                except Exception as exc:
                    print(f"status: ERROR\nmessage: {exc}")
                    raise SystemExit(2)
                return
            if args.workspace_command == "delete":
                try:
                    mgr.delete_workspace(args.id)
                    print(f"status: WORKSPACE_DELETED")
                    print(f"workspace_id: {args.id}")
                except WorkspaceNotFound:
                    print(f"status: ERROR\nerror_type: WORKSPACE_NOT_FOUND\nmessage: workspace not found: {args.id}")
                    raise SystemExit(2)
                except Exception as exc:
                    print(f"status: ERROR\nmessage: {exc}")
                    raise SystemExit(2)
                return
            if args.workspace_command == "export":
                try:
                    mgr.export_workspace(args.id, str(args.output))
                    print(f"status: WORKSPACE_EXPORTED")
                    print(f"workspace_id: {args.id}")
                    print(f"output: {args.output}")
                    if args.json_output:
                        print(_json.dumps({"status": "EXPORTED", "workspace_id": args.id, "output": str(args.output)}, sort_keys=True))
                except WorkspaceNotFound:
                    print(f"status: ERROR\nerror_type: WORKSPACE_NOT_FOUND\nmessage: workspace not found: {args.id}")
                    raise SystemExit(2)
                except Exception as exc:
                    print(f"status: ERROR\nmessage: {exc}")
                    raise SystemExit(2)
                return
            if args.workspace_command == "import":
                try:
                    ws = mgr.import_workspace(str(args.file), force=args.force)
                    print(f"status: WORKSPACE_IMPORTED")
                    print(f"workspace_id: {ws.id}")
                    print(f"name: {ws.name}")
                    if args.json_output:
                        print(_json.dumps(ws.to_dict(), sort_keys=True))
                except ImportError as exc:
                    print(f"status: ERROR\nerror_type: IMPORT_ERROR\nmessage: {exc}")
                    raise SystemExit(2)
                except Exception as exc:
                    print(f"status: ERROR\nmessage: {exc}")
                    raise SystemExit(2)
                return
            if args.workspace_command == "tasks":
                try:
                    tasks = mgr.list_tasks(args.id)
                    if args.json_output:
                        print(_json.dumps([t.to_dict() for t in tasks], sort_keys=True))
                    else:
                        print(f"workspace_id: {args.id}")
                        print(f"task_count: {len(tasks)}")
                        for t in tasks:
                            print(f"  - {t.task_id} (updated: {t.updated_at})")
                except WorkspaceNotFound:
                    print(f"status: ERROR\nerror_type: WORKSPACE_NOT_FOUND\nmessage: workspace not found: {args.id}")
                    raise SystemExit(2)
                except Exception as exc:
                    print(f"status: ERROR\nmessage: {exc}")
                    raise SystemExit(2)
                return
                return
        if args.command == "cake":
            from vcse.cake import (
                CakeConfigError,
                CakePipelineError,
                CakeTransportError,
                load_source_config,
                render_report,
                render_report_summary,
                run_cake_pipeline,
            )
            if args.cake_command == "validate":
                config = load_source_config(args.source)
                print(f"status: VALID")
                print(f"sources: {len(config.sources)}")
                for src in config.sources:
                    enabled = "enabled" if src.enabled else "disabled"
                    print(f"  - {src.id} ({src.source_type}/{src.format}) [{enabled}]")
                return
            if args.cake_command == "run":
                report = run_cake_pipeline(
                    args.source,
                    limit=args.limit,
                    dry_run=args.dry_run,
                    allow_http=args.allow_http,
                    transport_type=args.transport,
                    allow_partial=args.allow_partial,
                    incremental_mode=args.incremental,
                )
                print(render_report(report))
                if report.status == "CAKE_FAILED":
                    raise SystemExit(2)
                return
            if args.cake_command == "report":
                import json as _json
                from pathlib import Path as _Path
                report_path = _Path(args.report_file)
                if not report_path.exists():
                    print(render_error("FILE_NOT_FOUND", f"report file not found: {report_path}"), file=sys.stderr)
                    raise SystemExit(2)
                data = _json.loads(report_path.read_text())
                print(render_report_summary_from_dict(data))
                return
            cake_parser.print_help()
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
        CoverageBenchmarkError,
        DomainSpecError,
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
