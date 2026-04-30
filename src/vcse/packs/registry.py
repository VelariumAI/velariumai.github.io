"""Local pack registry."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from vcse.packs.errors import PackError
from vcse.packs.manifest import PackManifest


def pack_home() -> Path:
    base = os.getenv("VCSE_PACK_HOME")
    if base:
        return Path(base).expanduser()
    return Path.home() / ".vcse"


def pack_store_dir() -> Path:
    return pack_home() / "packs"


def registry_path() -> Path:
    return pack_home() / "registry.json"


@dataclass(frozen=True)
class InstalledPackRecord:
    id: str
    version: str
    name: str
    domain: str
    install_path: str
    source_path: str
    installed_at: str
    validation_passed: bool
    dependencies: list[dict[str, str]]

    @classmethod
    def from_manifest(
        cls,
        manifest: PackManifest,
        *,
        install_path: Path,
        source_path: Path,
        validation_passed: bool,
    ) -> "InstalledPackRecord":
        return cls(
            id=manifest.id,
            version=manifest.version,
            name=manifest.name,
            domain=manifest.domain,
            install_path=str(install_path),
            source_path=str(source_path),
            installed_at=datetime.now(timezone.utc).isoformat(),
            validation_passed=validation_passed,
            dependencies=[{"id": dep.id, "version": dep.version} for dep in manifest.dependencies],
        )


class PackRegistry:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or registry_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"installed_packs": []}
        try:
            payload = json.loads(self.path.read_text())
        except json.JSONDecodeError as exc:
            raise PackError(
                "REGISTRY_CORRUPT",
                f"registry is corrupt at {self.path}; remove or fix the file and retry",
            ) from exc
        if not isinstance(payload, dict) or "installed_packs" not in payload:
            raise PackError("REGISTRY_CORRUPT", f"registry format invalid at {self.path}")
        if not isinstance(payload["installed_packs"], list):
            raise PackError("REGISTRY_CORRUPT", "installed_packs must be list")
        return payload

    def save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", delete=False, dir=self.path.parent) as tmp:
            json.dump(payload, tmp, indent=2, sort_keys=True)
            tmp.write("\n")
            tmp_path = Path(tmp.name)
        tmp_path.replace(self.path)

    def add(self, record: InstalledPackRecord, *, force: bool = False) -> None:
        payload = self.load()
        packs = payload["installed_packs"]
        existing = [
            item for item in packs if item.get("id") == record.id and item.get("version") == record.version
        ]
        if existing and not force:
            raise PackError("PACK_EXISTS", f"pack already installed: {record.id}@{record.version}")
        packs = [
            item for item in packs if not (item.get("id") == record.id and item.get("version") == record.version)
        ]
        packs.append(record.__dict__)
        payload["installed_packs"] = sorted(packs, key=lambda item: (item.get("id", ""), item.get("version", "")))
        self.save(payload)

    def remove(self, pack_id: str, version: str | None = None) -> int:
        payload = self.load()
        packs = payload["installed_packs"]
        before = len(packs)
        if version is None:
            filtered = [item for item in packs if item.get("id") != pack_id]
        else:
            filtered = [
                item
                for item in packs
                if not (item.get("id") == pack_id and item.get("version") == version)
            ]
        payload["installed_packs"] = filtered
        self.save(payload)
        return before - len(filtered)

    def list(self) -> list[dict[str, Any]]:
        payload = self.load()
        return list(payload["installed_packs"])

    def find(self, pack_id: str, version: str | None = None) -> dict[str, Any] | None:
        candidates = [item for item in self.list() if item.get("id") == pack_id]
        if not candidates:
            return None
        if version is None:
            return sorted(candidates, key=lambda item: item.get("version", ""), reverse=True)[0]
        for item in candidates:
            if item.get("version") == version:
                return item
        return None

    def search(
        self,
        *,
        pack_id: str | None = None,
        domain: str | None = None,
        name: str | None = None,
        artifact_type: str | None = None,
    ) -> list[dict[str, Any]]:
        items = self.list()
        if pack_id:
            items = [item for item in items if pack_id in str(item.get("id", ""))]
        if domain:
            items = [item for item in items if domain in str(item.get("domain", ""))]
        if name:
            items = [item for item in items if name.lower() in str(item.get("name", "")).lower()]
        if artifact_type:
            # artifact_type requires reading manifest; keep deterministic by checking install path manifest
            filtered: list[dict[str, Any]] = []
            for item in items:
                manifest_path = Path(item["install_path"]) / "pack.json"
                if not manifest_path.exists():
                    continue
                manifest = json.loads(manifest_path.read_text())
                if artifact_type in manifest.get("artifacts", {}):
                    filtered.append(item)
            items = filtered
        return items
