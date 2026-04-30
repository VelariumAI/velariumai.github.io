"""Capability pack export for ingestion outputs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vcse.memory.world_state import WorldStateMemory


def export_capability_pack(
    pack_dir: str | Path,
    source_count: int,
    memory: WorldStateMemory,
    frames: list[object],
) -> None:
    root = Path(pack_dir)
    root.mkdir(parents=True, exist_ok=True)

    claims = list(memory.claims.values())
    constraints = list(memory.constraints)

    pack = {
        "name": root.name,
        "version": "1.0",
        "description": "VCSE capability pack exported from ingestion pipeline",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_count": source_count,
        "claim_count": len(claims),
        "constraint_count": len(constraints),
    }
    _write_yaml_like(root / "pack.yaml", pack)

    _write_jsonl(
        root / "claims.jsonl",
        [
            {
                "id": claim.id,
                "subject": claim.subject,
                "relation": claim.relation,
                "object": claim.object,
                "status": claim.status.value,
                "source": claim.source,
            }
            for claim in claims
        ],
    )
    _write_jsonl(
        root / "constraints.jsonl",
        [constraint.to_dict() for constraint in constraints],
    )
    _write_yaml_like(
        root / "templates.yaml",
        {"extracted_frame_types": [type(frame).__name__ for frame in frames]},
    )

    provenance_records: list[dict[str, Any]] = []
    for frame in frames:
        provenance = getattr(frame, "provenance", None)
        if isinstance(provenance, dict):
            provenance_records.append(provenance)
    _write_jsonl(root / "provenance.jsonl", provenance_records)

    _write_jsonl(
        root / "benchmarks.jsonl",
        [
            {
                "id": f"pack_case_{index:03d}",
                "facts": [
                    {
                        "subject": claim.subject,
                        "relation": claim.relation,
                        "object": claim.object,
                    }
                    for claim in claims
                ],
                "constraints": [constraint.to_dict() for constraint in constraints],
                "expected_status": "INCONCLUSIVE",
            }
            for index in range(1, 2)
        ],
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def _write_yaml_like(path: Path, payload: dict[str, Any]) -> None:
    lines = [f"{key}: {json.dumps(value) if isinstance(value, (list, dict)) else value}" for key, value in payload.items()]
    path.write_text("\n".join(lines) + "\n")
