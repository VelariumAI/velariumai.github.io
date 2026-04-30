"""End-to-end knowledge automation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vcse.knowledge.extractor import ExtractionResult, KnowledgeExtractor
from vcse.knowledge.metrics import KnowledgeMetrics
from vcse.knowledge.normalizer import KnowledgeNormalizer
from vcse.knowledge.pack_builder import KnowledgePackBuilder
from vcse.knowledge.pack_model import KnowledgePack
from vcse.knowledge.resolver import ConflictResolver
from vcse.knowledge.sources import Source
from vcse.knowledge.validator import KnowledgeValidator


@dataclass
class KnowledgePipelineResult:
    status: str
    pack: KnowledgePack
    metrics: KnowledgeMetrics
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    output_path: Path | None = None


class KnowledgePipeline:
    def __init__(
        self,
        extractor: KnowledgeExtractor | None = None,
        normalizer: KnowledgeNormalizer | None = None,
        validator: KnowledgeValidator | None = None,
        resolver: ConflictResolver | None = None,
        builder: KnowledgePackBuilder | None = None,
    ) -> None:
        self.extractor = extractor or KnowledgeExtractor()
        self.normalizer = normalizer or KnowledgeNormalizer()
        self.validator = validator or KnowledgeValidator()
        self.resolver = resolver or ConflictResolver()
        self.builder = builder or KnowledgePackBuilder()

    def validate_source(self, source: Source) -> KnowledgePipelineResult:
        return self.build(source, pack_id=f"{source.id}_validation", write=False)

    def build(
        self,
        source: Source,
        pack_id: str,
        *,
        version: str = "1.0.0",
        domain: str = "general",
        output_path: str | Path | None = None,
        write: bool = False,
    ) -> KnowledgePipelineResult:
        metrics = KnowledgeMetrics(sources_processed=1)
        extraction: ExtractionResult = self.extractor.extract(source)
        metrics.claims_extracted = len(extraction.claims)
        normalized = [self.normalizer.normalize_claim(claim) for claim in extraction.claims]
        validation = self.validator.validate(normalized)
        metrics.valid_claims = len(validation.valid_claims)
        metrics.invalid_claims_rejected = len(validation.rejected_claims)
        resolution = self.resolver.resolve(validation.valid_claims)
        metrics.duplicate_claims = len(resolution.duplicates)
        metrics.conflicts_detected = len(resolution.conflicts)

        pack = KnowledgePack(
            id=pack_id,
            version=version,
            domain=domain,
            claims=resolution.claims,
            provenance=[claim.provenance for claim in resolution.claims],
            conflicts=resolution.conflicts,
            metrics=metrics.to_dict(),
        )
        status = "VALID" if not validation.errors else "PARTIAL"
        written_path = None
        if write:
            written_path = self.builder.write_pack(pack, output_path or pack_id)
        return KnowledgePipelineResult(
            status=status,
            pack=pack,
            metrics=metrics,
            warnings=[*extraction.warnings, *validation.warnings],
            errors=list(validation.errors),
            output_path=written_path,
        )
