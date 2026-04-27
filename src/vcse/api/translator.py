"""Deterministic request translator for API-compatible inputs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from vcse.generation import spec_from_dict, VerifiedGenerator
from vcse.interaction.response_modes import ResponseMode, render_response
from vcse.interaction.session import Session
from vcse.memory.relations import RelationSchema
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.perf import increment, stage


@dataclass(frozen=True)
class TranslationResult:
    status: str
    content: str
    answer: Any | None
    proof_trace: list[str]
    reasons: list[str]
    debug: dict[str, Any]


def translate_user_input(
    user_text: str,
    enable_debug: bool = False,
    search_backend: str = "beam",
    enable_ts3: bool = False,
    enable_index: bool = False,
) -> TranslationResult:
    mode = _infer_mode(user_text)
    if mode == "generate":
        return _run_generate(user_text, enable_index=enable_index)
    return _run_ask(
        user_text,
        enable_debug=enable_debug,
        search_backend=search_backend,
        enable_ts3=enable_ts3,
        enable_index=enable_index,
    )


def _infer_mode(user_text: str) -> str:
    text = user_text.strip()
    if not text:
        return "ask"
    if text.startswith("{") and text.endswith("}"):
        try:
            payload = json.loads(text)
            if isinstance(payload, dict) and "artifact_type" in payload and "required_fields" in payload:
                return "generate"
        except json.JSONDecodeError:
            return "ask"
    lowered = text.lower()
    if "artifact_type" in lowered and "required_fields" in lowered and "generate" in lowered:
        return "generate"
    return "ask"


def _run_ask(
    text: str,
    enable_debug: bool,
    search_backend: str,
    enable_ts3: bool,
    enable_index: bool,
) -> TranslationResult:
    with stage("api.ask"):
        if _looks_ambiguous(text):
            clarification = "What does that refer to?"
            return TranslationResult(
                status="NEEDS_CLARIFICATION",
                content=f"Additional information required: {clarification}",
                answer=clarification,
                proof_trace=[],
                reasons=[clarification],
                debug={"status": "NEEDS_CLARIFICATION"},
            )

        session = Session.create(enable_indexing=enable_index)
        session.ingest(text)
        increment("api.ask.ingested")
        result = session.solve(enable_ts3=enable_ts3, search_backend=search_backend)

        if result is None:
            return TranslationResult(
                status="INCONCLUSIVE",
                content="Cannot determine with current information.",
                answer=None,
                proof_trace=[],
                reasons=["no result"],
                debug={"status": "INCONCLUSIVE"},
            )

        if hasattr(result, "user_message"):
            message = getattr(result, "user_message", "Additional information required.")
            return TranslationResult(
                status="NEEDS_CLARIFICATION",
                content=f"Additional information required: {message}",
                answer=message,
                proof_trace=[],
                reasons=[message],
                debug={"status": "NEEDS_CLARIFICATION"},
            )

        evaluation = result.evaluation
        status = evaluation.status.value
        answer = evaluation.answer
        reasons = list(evaluation.reasons)
        proof_trace = list(evaluation.proof_trace)
        content = render_response(result, ResponseMode.SIMPLE, session.memory)

        debug = {
            "status": status,
            "proof_trace": proof_trace,
            "search_stats": result.stats.__dict__,
            "ts3_stats": (result.ts3_analysis.__dict__ if result.ts3_analysis else None),
            "selected_packs": (result.retrieval_stats or {}).get("selected_packs", []),
            "selected_rules": (result.retrieval_stats or {}).get("selected_artifacts_count", 0),
        }
        return TranslationResult(
            status=status,
            content=content,
            answer=answer,
            proof_trace=proof_trace,
            reasons=reasons,
            debug=debug,
        )


def _run_generate(text: str, enable_index: bool) -> TranslationResult:
    with stage("api.generate"):
        payload = json.loads(text)
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

        result = VerifiedGenerator().generate(spec, memory, enable_index=enable_index)
        best = result.best_artifact
        answer = best.content if best is not None else None
        status = result.status
        content = _status_to_text(status, answer, list(result.evaluation_reasons))
        debug = {
            "status": status,
            "proof_trace": [],
            "search_stats": result.search_stats,
            "ts3_stats": None,
            "selected_packs": result.template_stats.get("selected_templates", []),
            "selected_rules": result.template_stats.get("selected_templates_count", 0),
        }
        return TranslationResult(
            status=status,
            content=content,
            answer=answer,
            proof_trace=[],
            reasons=list(result.evaluation_reasons),
            debug=debug,
        )


def _status_to_text(status: str, answer: Any | None, reasons: list[str]) -> str:
    if status == "VERIFIED":
        return f"Yes — {answer}." if answer else "Yes — verified."
    if status == "INCONCLUSIVE":
        return "Cannot determine with current information."
    if status == "NEEDS_CLARIFICATION":
        suffix = reasons[0] if reasons else "please provide additional details."
        return f"Additional information required: {suffix}"
    if status == "CONTRADICTORY":
        suffix = reasons[0] if reasons else "conflicting facts were found."
        return f"Contradiction detected: {suffix}"
    if status == "UNSATISFIABLE":
        return "Constraints cannot be satisfied."
    if status == "VERIFIED_ARTIFACT":
        return json.dumps(answer, sort_keys=True)
    if status == "INCONCLUSIVE_ARTIFACT":
        suffix = reasons[0] if reasons else "artifact could not be fully verified."
        return f"Artifact is inconclusive: {suffix}"
    if status == "FAILED_ARTIFACT":
        suffix = reasons[0] if reasons else "validation failed."
        return f"Artifact generation failed: {suffix}"
    if status == "CONTRADICTORY_ARTIFACT":
        suffix = reasons[0] if reasons else "artifact contradicts known facts."
        return f"Contradiction detected: {suffix}"
    return f"Status: {status}"


def _looks_ambiguous(text: str) -> bool:
    return bool(re.match(r"^\s*(is|can|does|do|did|are)\s+(it|this|that|they|he|she)\b", text, re.IGNORECASE))
