"""Response modes for human-friendly output."""

from __future__ import annotations

from enum import Enum
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.search.result import SearchResult
from vcse.verifier.final_state import FinalStateEvaluation


class ResponseMode(Enum):
    """Output mode for responses."""
    SIMPLE = "simple"
    EXPLAIN = "explain"
    DEBUG = "debug"
    STRICT = "strict"


RELATION_DISPLAY_MAP = {
    "is_a": "is",
    "equals": "equals",
    "part_of": "is part of",
    "has_capital": "has capital",
    "capital_of": "capital of",
}

QUESTION_AUXILIARIES = {"can", "could", "would", "should", "does", "do", "did", "is", "are"}
IS_A_NO_ARTICLE_OBJECTS = {"mortal", "alive", "dead", "eligible", "valid", "done"}


def render_response(
    evaluation: FinalStateEvaluation | SearchResult,
    mode: ResponseMode,
    state: WorldStateMemory | None = None,
    renderer_templates: dict[str, str] | None = None,
) -> str:
    """Render evaluated result in the specified mode."""
    search_result = evaluation if isinstance(evaluation, SearchResult) else None
    final = search_result.evaluation if search_result is not None else evaluation
    render_state = search_result.state if search_result is not None else state

    if mode == ResponseMode.SIMPLE:
        return _render_simple(final, renderer_templates=renderer_templates)
    elif mode == ResponseMode.EXPLAIN:
        return _render_explain(final, render_state, renderer_templates=renderer_templates)
    elif mode == ResponseMode.DEBUG:
        return _render_debug(final, search_result, render_state, renderer_templates=renderer_templates)
    else:  # STRICT
        return _render_strict(final, search_result)


def _render_simple(
    evaluation: FinalStateEvaluation,
    renderer_templates: dict[str, str] | None = None,
) -> str:
    """Simple yes/no style response."""
    status = evaluation.status.value
    answer = _humanize_claim(
        evaluation.answer,
        include_article_for_is_a=False,
        renderer_templates=renderer_templates,
    )

    if status == "VERIFIED":
        return f"Yes — {answer or 'verified'}."
    elif status == "CONTRADICTORY":
        return "Contradiction detected."
    elif status == "UNSATISFIABLE":
        return "Requirements cannot be satisfied."
    elif status == "INCONCLUSIVE":
        return "Insufficient information."
    return f"Status: {status}"


def _humanize_claim(
    answer: str | None,
    include_article_for_is_a: bool = False,
    renderer_templates: dict[str, str] | None = None,
) -> str | None:
    """Render internal canonical triples in a friendlier sentence form."""
    if not answer:
        return answer

    clean = " ".join(answer.strip().split())
    subject, relation, obj = _split_claim_text(clean)
    if relation is None:
        return clean

    subject = _strip_leading_question_aux(subject)
    subject_display = _display_subject(subject)
    if relation == "has_capital":
        return f"{_display_subject(obj)} is the capital of {subject_display}"
    if relation == "capital_of":
        return f"{subject_display} is the capital of {_display_subject(obj)}"
    if renderer_templates and relation in renderer_templates:
        return renderer_templates[relation].format(subject=subject_display, object=_display_object(obj, relation, include_article_for_is_a))
    relation_display = RELATION_DISPLAY_MAP.get(relation, relation.replace("_", " "))
    object_display = _display_object(obj, relation, include_article_for_is_a)
    return f"{subject_display} {relation_display} {object_display}"


def _split_claim_text(answer: str) -> tuple[str, str | None, str]:
    for relation in RELATION_DISPLAY_MAP:
        token = f" {relation} "
        if token in answer:
            subject, obj = answer.split(token, 1)
            return subject.strip(), relation, obj.strip()
    return answer, None, ""


def _strip_leading_question_aux(subject: str) -> str:
    parts = subject.split()
    if parts and parts[0].lower() in QUESTION_AUXILIARIES:
        return " ".join(parts[1:]).strip()
    return subject


def _display_subject(subject: str) -> str:
    if not subject:
        return subject
    words = subject.split()
    if len(words) == 1 and len(words[0]) == 1:
        return words[0]
    return " ".join(word.capitalize() for word in words)


def _display_object(obj: str, relation: str, include_article_for_is_a: bool) -> str:
    if relation == "is_a":
        lowered = obj.lower()
        if include_article_for_is_a and _needs_indefinite_article(lowered):
            article = "an" if lowered[:1] in {"a", "e", "i", "o", "u"} else "a"
            return f"{article} {lowered}"
        return lowered
    return obj


def _needs_indefinite_article(obj: str) -> bool:
    if obj in IS_A_NO_ARTICLE_OBJECTS:
        return False
    if " " in obj:
        return False
    return obj.isalpha()


def _render_explain(
    evaluation: FinalStateEvaluation,
    state: WorldStateMemory | None,
    renderer_templates: dict[str, str] | None = None,
) -> str:
    """Explain with reasoning."""
    status = evaluation.status.value
    answer = _humanize_claim(
        evaluation.answer,
        include_article_for_is_a=False,
        renderer_templates=renderer_templates,
    )

    if status == "VERIFIED" and evaluation.proof_trace:
        trace = " → ".join(
            _humanize_claim(step, include_article_for_is_a=True, renderer_templates=renderer_templates) or step
            for step in evaluation.proof_trace[:3]
        )
        return f"Yes — {answer} because {trace}."
    elif status == "CONTRADICTORY":
        reasons = "; ".join(evaluation.reasons[:2])
        return f"Contradiction: {reasons}."
    elif status == "UNSATISFIABLE":
        reasons = "; ".join(evaluation.reasons[:2])
        return f"Unsatisfiable: {reasons}."
    elif status == "INCONCLUSIVE":
        return "Insufficient information to verify."
    return f"Status: {status}"


def _render_debug(
    evaluation: FinalStateEvaluation,
    search_result: SearchResult | None,
    state: WorldStateMemory | None,
    renderer_templates: dict[str, str] | None = None,
) -> str:
    """Full debug output."""
    lines = [f"status: {evaluation.status.value}"]

    if evaluation.answer is not None:
        lines.append(f"answer: {evaluation.answer}")
        lines.append(
            f"answer_human: {_humanize_claim(evaluation.answer, include_article_for_is_a=False)}"
            if renderer_templates is None
            else f"answer_human: {_humanize_claim(evaluation.answer, include_article_for_is_a=False, renderer_templates=renderer_templates)}"
        )
    else:
        lines.append("answer: null")
        lines.append("answer_human: null")

    lines.append("proof_trace_canonical:")
    if evaluation.proof_trace:
        for step in evaluation.proof_trace:
            lines.append(f"  - {step}")
    else:
        lines.append("  - null")

    lines.append("proof_trace_human:")
    if evaluation.proof_trace:
        for step in evaluation.proof_trace:
            human_step = _humanize_claim(step, include_article_for_is_a=True, renderer_templates=renderer_templates) or step
            lines.append(f"  - {human_step}")
    else:
        lines.append("  - null")

    lines.append("verifier_reasons:")
    if evaluation.reasons:
        for reason in evaluation.reasons:
            lines.append(f"  - {reason}")
    else:
        lines.append("  - null")

    if search_result:
        stats = search_result.stats
        lines.append("search_stats:")
        lines.append(f"  backend: {stats.backend}")
        lines.append(f"  nodes_expanded: {stats.nodes_expanded}")
        lines.append(f"  max_depth_reached: {stats.max_depth_reached}")
        lines.append(f"  best_score: {stats.best_score}")
        if stats.iterations:
            lines.append(f"  iterations: {stats.iterations}")
        if search_result.ts3_analysis is not None:
            ts3 = search_result.ts3_analysis
            lines.append("ts3:")
            lines.append(f"  loop_detected: {ts3.loop_detected}")
            lines.append(f"  reachable_by_depth: {ts3.reachable_by_depth}")
            lines.append(f"  absorption_counts: {ts3.absorption_counts}")
            lines.append(f"  novelty_score: {ts3.novelty_score}")
            lines.append(f"  contradiction_risk: {ts3.contradiction_risk}")
        if search_result.retrieval_stats is not None:
            retrieval = search_result.retrieval_stats
            lines.append("index:")
            lines.append(f"  selected_packs: {retrieval.get('selected_packs', [])}")
            lines.append(
                f"  selected_artifacts_count: {retrieval.get('selected_artifacts_count', 0)}"
            )
            lines.append(f"  top_scores: {retrieval.get('top_scores', [])}")
            lines.append(f"  filtered_out_count: {retrieval.get('filtered_out_count', 0)}")

    return "\n".join(lines)


def _render_strict(evaluation: FinalStateEvaluation, search_result: SearchResult | None) -> str:
    """Machine-oriented structured output."""
    import json
    output = {
        "status": evaluation.status.value,
        "answer": evaluation.answer,
        "proof_trace": evaluation.proof_trace,
        "reasons": evaluation.reasons,
    }
    if search_result:
        output["search_stats"] = {
            "nodes_expanded": search_result.stats.nodes_expanded,
            "max_depth_reached": search_result.stats.max_depth_reached,
            "best_score": search_result.stats.best_score,
        }
    return json.dumps(output, sort_keys=True)
