"""DSL compiler."""

from __future__ import annotations

from vcse.dsl.schema import (
    CapabilityBundle,
    ClarificationRule,
    DSLDocument,
    GenerationTemplateRule,
    IngestionTemplateRule,
    ParserPatternRule,
    ProposerRule,
    RendererTemplateRule,
    SynonymRule,
    VerifierRuleStub,
)


class DSLCompiler:
    @staticmethod
    def compile(document: DSLDocument) -> CapabilityBundle:
        artifacts = sorted(
            [artifact for artifact in document.artifacts if artifact.enabled],
            key=lambda item: (item.priority, item.id),
        )
        bundle = CapabilityBundle(name=document.name, version=document.version)
        for artifact in artifacts:
            payload = artifact.payload
            if artifact.type == "synonym":
                patterns = payload.get("patterns", [])
                replacement = str(payload.get("replacement", ""))
                for pattern in patterns:
                    bundle.synonyms.append(
                        SynonymRule(
                            id=artifact.id,
                            pattern=str(pattern).strip().lower(),
                            replacement=replacement.strip().lower(),
                            priority=artifact.priority,
                        )
                    )
            elif artifact.type == "parser_pattern":
                output = payload.get("output", {})
                bundle.parser_patterns.append(
                    ParserPatternRule(
                        id=artifact.id,
                        pattern=str(payload.get("pattern", "")),
                        output={
                            "frame_type": str(output.get("frame_type", "claim")),
                            "relation": str(output.get("relation", "is_a")),
                            "subject": str(output.get("subject", "{subject}")),
                            "object": str(output.get("object", "{object}")),
                        },
                        priority=artifact.priority,
                    )
                )
            elif artifact.type == "relation_schema":
                bundle.relation_schemas.append(
                    {
                        "id": artifact.id,
                        "name": str(payload.get("name", "")),
                        "properties": list(payload.get("properties", [])),
                        "priority": artifact.priority,
                    }
                )
            elif artifact.type == "ingestion_template":
                bundle.ingestion_templates.append(
                    IngestionTemplateRule(
                        id=artifact.id,
                        patterns=[str(item) for item in payload.get("patterns", [])],
                        output=dict(payload.get("output", {})),
                        priority=artifact.priority,
                    )
                )
            elif artifact.type == "generation_template":
                bundle.generation_templates.append(
                    GenerationTemplateRule(
                        id=artifact.id,
                        artifact_type=str(payload.get("artifact_type", "")),
                        required_fields=[str(item) for item in payload.get("required_fields", [])],
                        optional_fields=[str(item) for item in payload.get("optional_fields", [])],
                        body=dict(payload.get("body", {})),
                        constraints=[dict(item) for item in payload.get("constraints", [])],
                        priority=artifact.priority,
                    )
                )
            elif artifact.type == "proposer_rule":
                bundle.proposer_rules.append(
                    ProposerRule(
                        id=artifact.id,
                        when=[dict(item) for item in payload.get("when", [])],
                        then=dict(payload.get("then", {})),
                        priority=artifact.priority,
                    )
                )
            elif artifact.type == "clarification_rule":
                bundle.clarification_rules.append(
                    ClarificationRule(
                        id=artifact.id,
                        trigger=dict(payload.get("trigger", {})),
                        message=str(payload.get("message", "")),
                        priority=artifact.priority,
                    )
                )
            elif artifact.type == "renderer_template":
                bundle.renderer_templates.append(
                    RendererTemplateRule(
                        id=artifact.id,
                        relation=str(payload.get("relation", "")),
                        template=str(payload.get("template", "")),
                        priority=artifact.priority,
                    )
                )
            elif artifact.type == "verifier_rule_stub":
                bundle.verifier_stubs.append(
                    VerifierRuleStub(
                        id=artifact.id,
                        description=str(payload.get("description", artifact.description)),
                        status=str(payload.get("status", "registered")),
                        priority=artifact.priority,
                    )
                )
        return bundle
