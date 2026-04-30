"""Knowledge automation pipeline."""

from vcse.knowledge.extractor import ExtractionResult, KnowledgeExtractor
from vcse.knowledge.metrics import KnowledgeMetrics
from vcse.knowledge.pack_builder import (
    KnowledgePackBuilder,
    install_pack,
    list_installed_packs,
    pack_stats,
    read_pack,
)
from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgeConflict, KnowledgePack, KnowledgeProvenance
from vcse.knowledge.pipeline import KnowledgePipeline, KnowledgePipelineResult
from vcse.knowledge.sources import Source

__all__ = [
    "ExtractionResult",
    "KnowledgeClaim",
    "KnowledgeConflict",
    "KnowledgeExtractor",
    "KnowledgeMetrics",
    "KnowledgePack",
    "KnowledgePackBuilder",
    "KnowledgePipeline",
    "KnowledgePipelineResult",
    "KnowledgeProvenance",
    "Source",
    "install_pack",
    "list_installed_packs",
    "pack_stats",
    "read_pack",
]
