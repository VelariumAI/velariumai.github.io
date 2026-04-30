"""Pack loader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vcse.packs.errors import PackError
from vcse.packs.manifest import PackManifest


def load_manifest(pack_path: str | Path) -> tuple[PackManifest, Path]:
    root = Path(pack_path)
    if not root.exists():
        raise PackError("PACK_NOT_FOUND", f"pack path not found: {root}")
    if root.is_file():
        root = root.parent

    manifest_file = _detect_manifest(root)
    payload = _load_payload(manifest_file)
    manifest = PackManifest.from_dict(payload)
    return manifest, root


def _detect_manifest(root: Path) -> Path:
    for name in ("pack.json", "pack.yaml", "pack.yml"):
        candidate = root / name
        if candidate.exists():
            return candidate
    raise PackError("INVALID_MANIFEST", f"manifest not found in {root}")


def _load_payload(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise PackError("INVALID_MANIFEST", f"malformed manifest json: {exc.msg}") from exc
        if not isinstance(data, dict):
            raise PackError("INVALID_MANIFEST", "manifest root must be object")
        return data
    try:
        import yaml  # type: ignore[import-not-found]
    except Exception as exc:
        raise PackError("INVALID_MANIFEST", "yaml manifest requires PyYAML") from exc
    try:
        data = yaml.safe_load(path.read_text())
    except Exception as exc:
        raise PackError("INVALID_MANIFEST", f"malformed yaml manifest: {exc}") from exc
    if not isinstance(data, dict):
        raise PackError("INVALID_MANIFEST", "manifest root must be object")
    return data
