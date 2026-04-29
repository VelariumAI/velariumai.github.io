"""Automated pack pipeline report models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PIPELINE_PASSED = "PIPELINE_PASSED"
PIPELINE_FAILED = "PIPELINE_FAILED"


@dataclass(frozen=True)
class PipelineConfig:
    pipeline_id: str
    domain: Path
    adapter_type: str
    adapter_source: Path
    compiler_mapping: Path
    compiler_pack_id: str
    compiler_output_root: Path
    compiler_benchmark_output: Path
    validation_validate_pack: bool
    validation_review_pack: bool
    runtime_store_compile: bool


@dataclass(frozen=True)
class PipelineStageReport:
    stage: str
    status: str
    details: dict[str, object]
    reasons: list[str]


@dataclass(frozen=True)
class PipelineRunReport:
    status: str
    pipeline_id: str
    run_id: str
    pack_id: str
    stages: list[PipelineStageReport]
    output_dir: str
    reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "pipeline_id": self.pipeline_id,
            "run_id": self.run_id,
            "pack_id": self.pack_id,
            "stages": [
                {
                    "stage": stage.stage,
                    "status": stage.status,
                    "details": stage.details,
                    "reasons": list(stage.reasons),
                }
                for stage in self.stages
            ],
            "output_dir": self.output_dir,
            "reasons": list(self.reasons),
        }
