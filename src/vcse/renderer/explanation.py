"""Explanation renderer."""

from __future__ import annotations

from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.search.result import SearchResult
from vcse.verifier.final_state import FinalStateEvaluation


class ExplanationRenderer:
    """Renders final evaluated state without deciding truth."""

    def render(
        self,
        evaluation: FinalStateEvaluation | SearchResult,
        state: WorldStateMemory | None = None,
    ) -> str:
        search_result = evaluation if isinstance(evaluation, SearchResult) else None
        final = search_result.evaluation if search_result is not None else evaluation
        render_state = search_result.state if search_result is not None else state

        lines = [f"status: {final.status.value}"]
        if final.answer is not None:
            lines.append(f"answer: {final.answer}")
        else:
            lines.append("answer: null")

        self._append_list(lines, "proof_trace", final.proof_trace)
        self._append_list(lines, "assumptions_used", self._assumptions(render_state))
        self._append_list(lines, "contradictions", self._contradictions(render_state, final))
        self._append_list(lines, "verifier_reasons", final.reasons)
        self._append_search_stats(lines, search_result)
        return "\n".join(lines)

    def _append_list(self, lines: list[str], title: str, values: list[str]) -> None:
        lines.append(f"{title}:")
        if values:
            lines.extend(f"  - {value}" for value in values)
        else:
            lines.append("  - null")

    def _append_search_stats(self, lines: list[str], search_result: SearchResult | None) -> None:
        lines.append("search_stats:")
        if search_result is None:
            lines.extend(
                [
                    "  nodes_expanded: null",
                    "  max_depth_reached: null",
                    "  terminal_status: null",
                    "  best_score: null",
                    "  max_frontier_size: null",
                ]
            )
            return

        stats = search_result.stats
        lines.extend(
            [
                f"  nodes_expanded: {stats.nodes_expanded}",
                f"  max_depth_reached: {stats.max_depth_reached}",
                f"  terminal_status: {stats.terminal_status}",
                f"  best_score: {stats.best_score}",
                f"  max_frontier_size: {stats.max_frontier_size}",
            ]
        )

    def _assumptions(self, state: WorldStateMemory | None) -> list[str]:
        if state is None:
            return []
        return [
            claim.text
            for claim in state.claims.values()
            if claim.status == TruthStatus.ASSUMED
        ]

    def _contradictions(
        self, state: WorldStateMemory | None, evaluation: FinalStateEvaluation
    ) -> list[str]:
        values: list[str] = []
        seen: set[str] = set()
        if state is not None:
            for contradictions in state.contradictions.values():
                for contradiction in contradictions:
                    if contradiction.id in seen:
                        continue
                    seen.add(contradiction.id)
                    values.append(contradiction.reason)

        if not values and evaluation.status.value in {"CONTRADICTORY", "UNSATISFIABLE"}:
            values.extend(evaluation.reasons)

        return values
