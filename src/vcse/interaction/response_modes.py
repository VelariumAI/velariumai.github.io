"""Response modes for human-friendly output."""

from __future__ import annotations

from enum import Enum

from vcse.interaction.frames import ClaimFrame, GoalFrame, ConstraintFrame
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.search.result import SearchResult
from vcse.verifier.final_state import FinalStateEvaluation


class ResponseMode(Enum):
    """Output mode for responses."""
    SIMPLE = "simple"
    EXPLAIN = "explain"
    DEBUG = "debug"
    STRICT = "strict"


def render_response(
    evaluation: FinalStateEvaluation | SearchResult,
    mode: ResponseMode,
    state: WorldStateMemory | None = None,
) -> str:
    """Render evaluated result in the specified mode."""
    search_result = evaluation if isinstance(evaluation, SearchResult) else None
    final = search_result.evaluation if search_result is not None else evaluation
    render_state = search_result.state if search_result is not None else state

    if mode == ResponseMode.SIMPLE:
        return _render_simple(final)
    elif mode == ResponseMode.EXPLAIN:
        return _render_explain(final, render_state)
    elif mode == ResponseMode.DEBUG:
        return _render_debug(final, search_result, render_state)
    else:  # STRICT
        return _render_strict(final, search_result)


def _render_simple(evaluation: FinalStateEvaluation) -> str:
    """Simple yes/no style response."""
    status = evaluation.status.value
    answer = evaluation.answer

    if status == "VERIFIED":
        return f"Yes — {answer or 'verified'}."
    elif status == "CONTRADICTORY":
        return "Contradiction detected."
    elif status == "UNSATISFIABLE":
        return "Requirements cannot be satisfied."
    elif status == "INCONCLUSIVE":
        return "Insufficient information."
    return f"Status: {status}"


def _render_explain(evaluation: FinalStateEvaluation, state: WorldStateMemory | None) -> str:
    """Explain with reasoning."""
    status = evaluation.status.value
    answer = evaluation.answer

    if status == "VERIFIED" and evaluation.proof_trace:
        trace = " → ".join(evaluation.proof_trace[:3])
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
) -> str:
    """Full debug output."""
    lines = [f"status: {evaluation.status.value}"]

    if evaluation.answer is not None:
        lines.append(f"answer: {evaluation.answer}")
    else:
        lines.append("answer: null")

    lines.append("proof_trace:")
    if evaluation.proof_trace:
        for step in evaluation.proof_trace:
            lines.append(f"  - {step}")
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
        lines.append(f"  nodes_expanded: {stats.nodes_expanded}")
        lines.append(f"  max_depth_reached: {stats.max_depth_reached}")
        lines.append(f"  best_score: {stats.best_score}")

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
