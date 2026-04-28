"""Knowledge pack builder and installer."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from vcse.knowledge.errors import KnowledgeError
from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgePack, KnowledgeProvenance
from vcse.knowledge.registry import installed_pack_root
from vcse.ledger import build_integrity


class KnowledgePackBuilder:
    def write_pack(self, pack: KnowledgePack, output_path: str | Path) -> Path:
        root = Path(output_path)
        root.mkdir(parents=True, exist_ok=True)

        provenance = pack.provenance or [claim.provenance for claim in pack.claims]
        metadata = pack.metadata()
        _write_json(root / "pack.json", metadata)
        _write_yaml_like(root / "pack.yaml", metadata)
        _write_jsonl(root / "claims.jsonl", [claim.to_dict() for claim in pack.claims])
        _write_jsonl(root / "constraints.jsonl", pack.constraints)
        _write_json(root / "templates.json", pack.templates)
        _write_jsonl(root / "provenance.jsonl", [item.to_dict() for item in provenance])
        _write_jsonl(root / "conflicts.jsonl", [item.to_dict() for item in pack.conflicts])
        _write_json(root / "metrics.json", pack.metrics)
        _write_json(root / "trust_report.json", {"decisions": [], "conflicts": [], "staleness": []})
        _write_json(root / "ledger_snapshot.json", [])
        _write_jsonl(root / "staleness.jsonl", [])
        _write_json(root / "integrity.json", build_integrity(root))
        return root


def read_pack(path: str | Path) -> KnowledgePack:
    root = Path(path)
    metadata_path = root / "pack.json"
    claims_path = root / "claims.jsonl"
    if not metadata_path.exists() or not claims_path.exists():
        raise KnowledgeError("INVALID_PACK", f"missing pack files in {root}")
    metadata = json.loads(metadata_path.read_text())
    claims = [
        KnowledgeClaim.from_dict(json.loads(line))
        for line in claims_path.read_text().splitlines()
        if line.strip()
    ]
    provenance_path = root / "provenance.jsonl"
    provenance = []
    if provenance_path.exists():
        provenance = [
            KnowledgeProvenance.from_dict(json.loads(line))
            for line in provenance_path.read_text().splitlines()
            if line.strip()
        ]
    return KnowledgePack(
        id=str(metadata["id"]),
        version=str(metadata["version"]),
        domain=str(metadata.get("domain", "general")),
        claims=claims,
        provenance=provenance,
        metrics=dict(metadata.get("metrics", {})),
    )


def install_pack(pack_path: str | Path, root: str | Path | None = None) -> Path:
    pack = read_pack(pack_path)
    destination_root = installed_pack_root(root)
    destination_root.mkdir(parents=True, exist_ok=True)
    destination = destination_root / pack.id
    if destination.exists():
        raise KnowledgeError("PACK_EXISTS", f"installed pack already exists: {pack.id}")
    shutil.copytree(pack_path, destination)
    return destination


def list_installed_packs(root: str | Path | None = None) -> list[str]:
    destination_root = installed_pack_root(root)
    if not destination_root.exists():
        return []
    return sorted(path.name for path in destination_root.iterdir() if path.is_dir())


def pack_stats(path: str | Path) -> dict[str, Any]:
    pack = read_pack(path)
    return pack.metadata()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def _write_yaml_like(path: Path, payload: dict[str, Any]) -> None:
    lines = []
    for key, value in payload.items():
        rendered = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
        lines.append(f"{key}: {rendered}")
    path.write_text("\n".join(lines) + "\n")
