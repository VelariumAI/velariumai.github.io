"""Deterministic repair loop for generated artifacts."""

from __future__ import annotations

from copy import deepcopy

from vcse.generation.artifact import GeneratedArtifact
from vcse.generation.evaluator import ArtifactEvaluationResult
from vcse.generation.spec import GenerationSpec
from vcse.generation.templates import GenerationTemplate, render_template_body


class ArtifactRepairer:
    def __init__(self, max_repair_attempts: int = 2) -> None:
        self.max_repair_attempts = max_repair_attempts

    def repair(
        self,
        artifact: GeneratedArtifact,
        evaluation_result: ArtifactEvaluationResult,
        spec: GenerationSpec,
        templates: list[GenerationTemplate],
    ) -> GeneratedArtifact:
        current = deepcopy(artifact)
        attempts = 0
        while attempts < self.max_repair_attempts and evaluation_result.status != "VERIFIED_ARTIFACT":
            attempts += 1
            # deterministic optional defaults only when explicit in spec.constraints
            defaults = {
                str(item.get("target")): item.get("default")
                for item in spec.constraints
                if str(item.get("kind", "")).lower() == "default_if_missing" and "default" in item
            }
            changed = False
            for key, value in defaults.items():
                if key not in current.fields_used or current.fields_used.get(key) in (None, ""):
                    current.fields_used[key] = value
                    changed = True

            if not changed:
                alt_templates = [
                    template
                    for template in sorted(templates, key=lambda item: (item.priority, item.id))
                    if template.id != current.template_id
                ]
                if not alt_templates:
                    break
                template = alt_templates[0]
                current.template_id = template.id
                current.provenance["template_id"] = template.id
                current.provenance["template_constraints"] = list(template.constraints)
                current.content = render_template_body(template.body, current.fields_used)
                changed = True

            if not changed:
                break
        return current
