"""Pack activation for runtime usage."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vcse.dsl import CapabilityBundle, DSLCompiler, DSLLoader, DSLValidator
from vcse.compression.runtime_index import CompressedRuntimeIndex
from vcse.memory.constraints import Constraint
from vcse.packs.errors import PackError
from vcse.packs.loader import load_manifest
from vcse.packs.registry import PackRegistry
from vcse.packs.resolver import DependencyResolver


@dataclass(frozen=True)
class ActivatedPack:
    id: str
    version: str
    path: str


@dataclass
class ActivationResult:
    selected_packs: list[str]
    ordered_dependencies: list[str]
    dsl_bundle: CapabilityBundle
    knowledge_claims: list[dict[str, str]] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    relation_schemas: list[dict[str, Any]] = field(default_factory=list)
    parser_rules: int = 0
    synonyms: int = 0
    ingestion_templates: int = 0
    generation_templates: int = 0
    proposer_rules: int = 0
    renderer_templates: int = 0
    clarification_rules: int = 0


class PackActivator:
    def __init__(self, registry: PackRegistry | None = None, resolver: DependencyResolver | None = None) -> None:
        self.registry = registry or PackRegistry()
        self.resolver = resolver or DependencyResolver(self.registry)

    def activate(self, pack_specs: list[str]) -> ActivationResult:
        resolution = self.resolver.resolve(pack_specs)
        ordered = resolution.ordered
        if not ordered:
            return ActivationResult(
                selected_packs=[],
                ordered_dependencies=[],
                dsl_bundle=CapabilityBundle(name="runtime", version="1.0.0"),
            )

        merged = CapabilityBundle(name="runtime_packs", version="1.0.0")
        knowledge_claims: list[dict[str, str]] = []
        constraints: list[Constraint] = []

        for item in ordered:
            manifest, root = load_manifest(item.install_path)
            for rel_path in manifest.artifacts.get("dsl", []):
                document = DSLLoader.load(root / rel_path)
                validation = DSLValidator.validate(document)
                if not validation.passed:
                    raise PackError("INVALID_PACK", f"dsl validation failed for {manifest.id}: {'; '.join(validation.errors)}")
                bundle = DSLCompiler.compile(document)
                _merge_bundle(merged, bundle)
            compressed_claims_loaded = False
            if (root / "intern_table.json").exists() and (root / "encoded_claims.jsonl").exists():
                try:
                    knowledge_claims.extend(CompressedRuntimeIndex(root).iter_claims())
                    compressed_claims_loaded = True
                except Exception:
                    compressed_claims_loaded = False
            if not compressed_claims_loaded:
                for rel_path in manifest.artifacts.get("claims", []):
                    for line in (root / rel_path).read_text().splitlines():
                        if not line.strip():
                            continue
                        payload = json.loads(line)
                        knowledge_claims.append(
                            {
                                "subject": str(payload.get("subject", "")),
                                "relation": str(payload.get("relation", "")),
                                "object": str(payload.get("object", "")),
                            }
                        )
            for rel_path in manifest.artifacts.get("constraints", []):
                for line in (root / rel_path).read_text().splitlines():
                    if not line.strip():
                        continue
                    payload = json.loads(line)
                    try:
                        constraints.append(Constraint.from_dict(payload))
                    except Exception:
                        continue

        return ActivationResult(
            selected_packs=[f"{item.id}@{item.version}" for item in ordered],
            ordered_dependencies=[f"{item.id}@{item.version}" for item in ordered],
            dsl_bundle=merged,
            knowledge_claims=knowledge_claims,
            constraints=constraints,
            relation_schemas=list(merged.relation_schemas),
            parser_rules=len(merged.parser_patterns),
            synonyms=len(merged.synonyms),
            ingestion_templates=len(merged.ingestion_templates),
            generation_templates=len(merged.generation_templates),
            proposer_rules=len(merged.proposer_rules),
            renderer_templates=len(merged.renderer_templates),
            clarification_rules=len(merged.clarification_rules),
        )


def _merge_bundle(target: CapabilityBundle, source: CapabilityBundle) -> None:
    target.synonyms.extend(source.synonyms)
    target.parser_patterns.extend(source.parser_patterns)
    target.relation_schemas.extend(source.relation_schemas)
    target.ingestion_templates.extend(source.ingestion_templates)
    target.generation_templates.extend(source.generation_templates)
    target.proposer_rules.extend(source.proposer_rules)
    target.clarification_rules.extend(source.clarification_rules)
    target.renderer_templates.extend(source.renderer_templates)
    target.verifier_stubs.extend(source.verifier_stubs)
