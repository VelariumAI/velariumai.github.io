"""Explanation renderer."""

from __future__ import annotations

from vcse.verifier.final_state import FinalStateEvaluation


class ExplanationRenderer:
    """Renders final evaluated state without deciding truth."""

    def render(self, evaluation: FinalStateEvaluation) -> str:
        lines = [f"status: {evaluation.status.value}"]
        if evaluation.answer is not None:
            lines.append(f"answer: {evaluation.answer}")
        else:
            lines.append("answer: null")

        lines.append("proof_trace:")
        if evaluation.proof_trace:
            lines.extend(f"  - {item}" for item in evaluation.proof_trace)
        else:
            lines.append("  - null")

        if evaluation.reasons:
            lines.append("verifier_reasons:")
            lines.extend(f"  - {reason}" for reason in evaluation.reasons)
        return "\n".join(lines)
