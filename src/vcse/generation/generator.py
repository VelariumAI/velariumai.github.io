"""Public generator facade."""

from __future__ import annotations

from vcse.dsl.schema import CapabilityBundle
from vcse.generation.pipeline import GenerationPipeline, GenerationResult
from vcse.generation.spec import GenerationSpec
from vcse.memory.world_state import WorldStateMemory


class VerifiedGenerator:
    def __init__(self, pipeline: GenerationPipeline | None = None) -> None:
        self.pipeline = pipeline or GenerationPipeline()

    def generate(
        self,
        spec: GenerationSpec,
        memory: WorldStateMemory,
        bundle: CapabilityBundle | None = None,
        enable_index: bool = False,
        top_k_rules: int = 20,
    ) -> GenerationResult:
        return self.pipeline.generate(
            spec=spec,
            memory=memory,
            bundle=bundle,
            enable_index=enable_index,
            top_k_rules=top_k_rules,
        )
