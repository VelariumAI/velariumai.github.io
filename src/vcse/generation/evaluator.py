"""Deterministic artifact evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vcse.generation.artifact import GeneratedArtifact
from vcse.generation.constraints import evaluate_constraints
from vcse.generation.spec import GenerationSpec
from vcse.memory.world_state import WorldStateMemory


@dataclass
class ArtifactEvaluationResult:
    status: str
    reasons: list[str] = field(default_factory=list)
    constraints_satisfied: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)


class ArtifactEvaluator:
    def evaluate(
        self,
        artifact: GeneratedArtifact,
        spec: GenerationSpec,
        memory: WorldStateMemory,
    ) -> ArtifactEvaluationResult:
        if artifact.status == "NEEDS_CLARIFICATION":
            return ArtifactEvaluationResult(
                status="NEEDS_CLARIFICATION",
                reasons=list(artifact.verifier_reasons),
            )

        if not artifact.provenance:
            return ArtifactEvaluationResult(
                status="FAILED_ARTIFACT",
                reasons=["missing provenance"],
                violations=["missing provenance"],
            )

        constraints = [*artifact.provenance.get("template_constraints", []), *spec.constraints]
        satisfied, violations = evaluate_constraints(artifact, constraints)

        for key, value in spec.required_fields.items():
            if value is None or (isinstance(value, str) and not value.strip()):
                violations.append(f"missing required field: {key}")
            elif key not in artifact.fields_used:
                violations.append(f"missing required field: {key}")

        for criterion in spec.success_criteria:
            criterion_l = criterion.lower().strip()
            if not criterion_l:
                continue
            whole = f"{artifact.content} {artifact.fields_used}".lower()
            if criterion_l in whole:
                satisfied.append(f"success_criterion:{criterion}")
            else:
                violations.append(f"success criterion not satisfied: {criterion}")

        contradiction = _detect_contradiction(artifact, memory)
        if contradiction:
            return ArtifactEvaluationResult(
                status="CONTRADICTORY_ARTIFACT",
                reasons=[contradiction],
                constraints_satisfied=satisfied,
                violations=[*violations, contradiction],
            )

        violations.extend(_type_specific_violations(artifact, spec))

        if artifact.artifact_type == "simple_code" and spec.required_fields.get("tests"):
            return ArtifactEvaluationResult(
                status="INCONCLUSIVE_ARTIFACT",
                reasons=["CODE_EXECUTION_NOT_ENABLED"],
                constraints_satisfied=satisfied,
                violations=violations,
            )

        if violations:
            return ArtifactEvaluationResult(
                status="FAILED_ARTIFACT",
                reasons=["artifact validation failed"],
                constraints_satisfied=satisfied,
                violations=violations,
            )

        return ArtifactEvaluationResult(
            status="VERIFIED_ARTIFACT",
            reasons=["artifact verified"],
            constraints_satisfied=satisfied,
        )


def _type_specific_violations(artifact: GeneratedArtifact, spec: GenerationSpec) -> list[str]:
    violations: list[str] = []
    content = artifact.content

    if artifact.artifact_type == "plan":
        if not isinstance(content, dict):
            return ["plan content must be object"]
        for key in ("steps", "preconditions", "effects"):
            val = content.get(key)
            if val is None or (isinstance(val, str) and not val.strip()):
                violations.append(f"plan missing {key}")

    elif artifact.artifact_type == "config":
        if not isinstance(content, dict):
            return ["config content must be object"]
        for key in spec.required_fields:
            if key not in content:
                violations.append(f"missing config key: {key}")

    elif artifact.artifact_type in {"policy", "structured_document"}:
        if not isinstance(content, dict):
            return ["document content must be object"]
        sections = content.get("sections")
        if not isinstance(sections, list) or not sections:
            violations.append("missing required section: sections")

    elif artifact.artifact_type == "simple_code":
        if not isinstance(content, dict):
            return ["simple_code content must be object"]
        code = str(content.get("code", ""))
        if "def " not in code:
            violations.append("simple_code must contain python function")

    return violations


def _detect_contradiction(artifact: GeneratedArtifact, memory: WorldStateMemory) -> str | None:
    fields = artifact.fields_used
    if not isinstance(fields, dict):
        return None
    subject = fields.get("subject")
    relation = fields.get("relation")
    obj = fields.get("object")
    if subject and relation == "equals" and obj is not None:
        subject_norm = str(subject).strip().lower()
        obj_norm = str(obj).strip().lower()
        for claim in memory.claims.values():
            if claim.subject == subject_norm and claim.relation == "equals" and claim.object != obj_norm:
                return f"contradiction with memory: {subject} equals both {claim.object} and {obj}"
    return None
