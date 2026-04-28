"""Session-scoped fixtures for VCSE tests.

Sets VCSE_PACK_HOME to an isolated temp directory pre-populated with
example packs so subprocess-based CLI tests work without machine-local
state (~/.vcse/registry.json or ~/.vcse/packs/index.json).
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLES_PACKS = _REPO_ROOT / "examples" / "packs"

# Packs to pre-index: id → path relative to repo root
_EXAMPLE_PACK_DIRS: dict[str, Path] = {}
if _EXAMPLES_PACKS.exists():
    for _pack_dir in _EXAMPLES_PACKS.iterdir():
        if _pack_dir.is_dir() and (_pack_dir / "pack.json").exists():
            _meta = json.loads((_pack_dir / "pack.json").read_text())
            _pack_id = str(_meta.get("id", _pack_dir.name))
            _EXAMPLE_PACK_DIRS[_pack_id] = _pack_dir


@pytest.fixture(scope="session", autouse=True)
def vcse_pack_home(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    Create an isolated VCSE_PACK_HOME for the entire test session.

    Builds a PackIndex pre-populated with all example packs so that
    subprocess CLI tests using --pack <name> succeed on a clean machine
    (CI) without requiring manual `vcse pack install` steps.
    """
    home = tmp_path_factory.mktemp("vcse_pack_home", numbered=False)
    packs_dir = home / "packs"
    packs_dir.mkdir(parents=True, exist_ok=True)

    # Build index.json with entries for all example packs
    index: dict[str, dict] = {}
    for pack_id, pack_path in _EXAMPLE_PACK_DIRS.items():
        meta_path = pack_path / "pack.json"
        meta = json.loads(meta_path.read_text())
        version = str(meta.get("version", "1.0.0"))
        claims_path = pack_path / "claims.jsonl"
        claim_count = 0
        certified_count = 0
        if claims_path.exists():
            for line in claims_path.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                claim_count += 1
                if row.get("trust_tier") == "T5_CERTIFIED":
                    certified_count += 1
        key = f"{pack_id}@{version}"
        index[key] = {
            "pack_id": pack_id,
            "version": version,
            "domain": str(meta.get("domain", "general")),
            "lifecycle_status": str(meta.get("lifecycle_status", "candidate")),
            "claim_count": claim_count,
            "certified_count": certified_count,
            "candidate_count": claim_count - certified_count,
            "source_ids": list(meta.get("source_ids", [])),
            "last_updated": str(meta.get("created_at", "2026-01-01T00:00:00+00:00")),
            "pack_path": str(pack_path.resolve()),
            "stale": False,
        }

    (packs_dir / "index.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")

    # Also write an empty registry.json so PackRegistry doesn't fail
    registry_path = home / "registry.json"
    registry_path.write_text(json.dumps({"installed_packs": []}, indent=2) + "\n")

    os.environ["VCSE_PACK_HOME"] = str(home)
    yield home
    # Cleanup env (pytest does not restore os.environ automatically)
    os.environ.pop("VCSE_PACK_HOME", None)
