"""Candidate generation from templates."""

from __future__ import annotations

from dataclasses import dataclass

from vcse.generation.artifact import GeneratedArtifact
from vcse.generation.spec import GenerationSpec
from vcse.generation.templates import GenerationTemplate, render_template_body


@dataclass
class CandidateGenerator:
    def generate(
        self,
        spec: GenerationSpec,
        templates: list[GenerationTemplate],
    ) -> list[GeneratedArtifact]:
        candidates: list[GeneratedArtifact] = []
        ordered = sorted(templates, key=lambda item: (item.priority, item.id))
        for template in ordered:
            missing = [field for field in template.required_fields if field not in spec.required_fields]
            if missing:
                candidates.append(
                    GeneratedArtifact(
                        id=f"{spec.id}:{template.id}",
                        artifact_type=spec.artifact_type,
                        content={},
                        template_id=template.id,
                        fields_used=dict(spec.required_fields),
                        provenance={
                            "source": "generation",
                            "template_id": template.id,
                            "template_constraints": list(template.constraints),
                            "missing_fields": missing,
                        },
                        status="NEEDS_CLARIFICATION",
                        verifier_reasons=[f"missing required fields: {', '.join(missing)}"],
                    )
                )
                continue

            rendered = render_template_body(template.body, dict(spec.required_fields))
            candidates.append(
                GeneratedArtifact(
                    id=f"{spec.id}:{template.id}",
                    artifact_type=spec.artifact_type,
                    content=rendered,
                    template_id=template.id,
                    fields_used=dict(spec.required_fields),
                    provenance={
                        "source": "generation",
                        "template_id": template.id,
                        "template_constraints": list(template.constraints),
                        "spec_id": spec.id,
                    },
                )
            )
        return candidates
