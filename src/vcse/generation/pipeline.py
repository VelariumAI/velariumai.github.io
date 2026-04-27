"""Verified generation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vcse.dsl.schema import GenerationTemplateRule
from vcse.dsl.schema import CapabilityBundle
from vcse.generation.artifact import GeneratedArtifact
from vcse.generation.candidate import CandidateGenerator
from vcse.generation.evaluator import ArtifactEvaluator
from vcse.generation.repair import ArtifactRepairer
from vcse.generation.spec import GenerationSpec
from vcse.generation.templates import (
    BUILTIN_GENERATION_TEMPLATES,
    GenerationTemplate,
    templates_from_bundle,
)
from vcse.index.retrieval import RetrievalConfig, SymbolicRetriever
from vcse.memory.world_state import WorldStateMemory
from vcse.perf import increment, stage


@dataclass
class GenerationResult:
    status: str
    best_artifact: GeneratedArtifact | None = None
    candidates: list[GeneratedArtifact] = field(default_factory=list)
    evaluation_reasons: list[str] = field(default_factory=list)
    clarification_request: str | None = None
    search_stats: dict[str, Any] = field(default_factory=dict)
    template_stats: dict[str, Any] = field(default_factory=dict)


class GenerationPipeline:
    def __init__(
        self,
        candidate_generator: CandidateGenerator | None = None,
        evaluator: ArtifactEvaluator | None = None,
        repairer: ArtifactRepairer | None = None,
    ) -> None:
        self.candidate_generator = candidate_generator or CandidateGenerator()
        self.evaluator = evaluator or ArtifactEvaluator()
        self.repairer = repairer or ArtifactRepairer()

    def generate(
        self,
        spec: GenerationSpec,
        memory: WorldStateMemory,
        bundle: CapabilityBundle | None = None,
        enable_index: bool = False,
        top_k_rules: int = 20,
    ) -> GenerationResult:
        with stage("generation.pipeline"):
            missing = spec.validate()
            if missing:
                return GenerationResult(
                    status="NEEDS_CLARIFICATION",
                    clarification_request=f"Missing required fields: {', '.join(sorted(missing))}",
                    evaluation_reasons=["incomplete spec"],
                )

            templates = self._select_templates(spec, bundle)
            index_stats: dict[str, Any] = {}
            if enable_index:
                templates, index_stats = self._filter_templates_by_index(
                    spec, templates, top_k_rules=top_k_rules
                )

            if not templates:
                return GenerationResult(
                    status="INCONCLUSIVE_ARTIFACT",
                    evaluation_reasons=["no matching templates"],
                    template_stats={"templates_considered": 0, **index_stats},
                )

            candidates = self.candidate_generator.generate(spec, templates)
            increment("generation.candidates", len(candidates))
            evaluated: list[GeneratedArtifact] = []

            for candidate in candidates:
                eval_result = self.evaluator.evaluate(candidate, spec, memory)
                candidate.constraints_satisfied = list(eval_result.constraints_satisfied)
                candidate.violations = list(eval_result.violations)
                candidate.status = eval_result.status
                candidate.verifier_reasons = list(eval_result.reasons)

                if eval_result.status == "FAILED_ARTIFACT":
                    repaired = self.repairer.repair(candidate, eval_result, spec, templates)
                    repaired_result = self.evaluator.evaluate(repaired, spec, memory)
                    repaired.constraints_satisfied = list(repaired_result.constraints_satisfied)
                    repaired.violations = list(repaired_result.violations)
                    repaired.status = repaired_result.status
                    repaired.verifier_reasons = list(repaired_result.reasons)
                    candidate = repaired

                evaluated.append(candidate)

            ranked = sorted(evaluated, key=_rank_key)
            best = ranked[0] if ranked else None

            if best is None:
                return GenerationResult(
                    status="FAILED_ARTIFACT",
                    candidates=[],
                    evaluation_reasons=["no candidates generated"],
                    template_stats={"templates_considered": len(templates), **index_stats},
                )

            clarification = None
            if best.status == "NEEDS_CLARIFICATION":
                clarification = "; ".join(best.verifier_reasons) or "Spec requires clarification"

            return GenerationResult(
                status=best.status,
                best_artifact=best,
                candidates=ranked,
                evaluation_reasons=list(best.verifier_reasons),
                clarification_request=clarification,
                search_stats={"candidate_count": len(ranked)},
                template_stats={"templates_considered": len(templates), **index_stats},
            )

    def _select_templates(
        self,
        spec: GenerationSpec,
        bundle: CapabilityBundle | None,
    ) -> list[GenerationTemplate]:
        templates = [
            item
            for item in [*BUILTIN_GENERATION_TEMPLATES, *templates_from_bundle(bundle)]
            if item.artifact_type == spec.artifact_type
        ]
        if spec.allowed_templates:
            allowed = set(spec.allowed_templates)
            templates = [item for item in templates if item.id in allowed]
        return sorted(templates, key=lambda item: (item.priority, item.id))

    def _filter_templates_by_index(
        self,
        spec: GenerationSpec,
        templates: list[GenerationTemplate],
        top_k_rules: int,
    ) -> tuple[list[GenerationTemplate], dict[str, Any]]:
        synthetic_bundle = CapabilityBundle(
            name="generation_runtime",
            version="1.0.0",
            generation_templates=[
                GenerationTemplateRule(
                    id=t.id,
                    artifact_type=t.artifact_type,
                    required_fields=list(t.required_fields),
                    optional_fields=list(t.optional_fields),
                    body=dict(t.body),
                    constraints=[dict(c) for c in t.constraints],
                    priority=t.priority,
                )
                for t in templates
            ],
        )
        retriever = SymbolicRetriever.from_bundles([synthetic_bundle])
        query = f"{spec.goal} {spec.source_text} {' '.join(spec.required_fields.keys())}"
        result = retriever.retrieve(query, config=RetrievalConfig(top_k_rules=top_k_rules, top_k_packs=1))
        selected = set(result.selected_artifact_ids)
        if not selected:
            return templates, {
                "selected_templates": [],
                "selected_templates_count": 0,
                "filtered_out_count": 0,
                "top_scores": [],
            }
        filtered = [template for template in templates if template.id in selected]
        return filtered, {
            "selected_templates": [template.id for template in filtered],
            "selected_templates_count": len(filtered),
            "filtered_out_count": max(0, len(templates) - len(filtered)),
            "top_scores": result.top_scores,
        }


def _rank_key(artifact: GeneratedArtifact) -> tuple[int, int, int, int, str]:
    status_order = {
        "VERIFIED_ARTIFACT": 0,
        "CONTRADICTORY_ARTIFACT": 1,
        "INCONCLUSIVE_ARTIFACT": 2,
        "NEEDS_CLARIFICATION": 3,
        "FAILED_ARTIFACT": 4,
    }
    return (
        status_order.get(artifact.status, 9),
        len(artifact.violations),
        -len(artifact.constraints_satisfied),
        -len(artifact.provenance),
        artifact.template_id,
    )
