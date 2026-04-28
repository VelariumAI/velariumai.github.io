"""Pack installer."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from vcse.packs.errors import PackError
from vcse.packs.loader import load_manifest
from vcse.packs.registry import InstalledPackRecord, PackRegistry, pack_store_dir
from vcse.packs.validator import PackValidationResult, PackValidator


@dataclass(frozen=True)
class InstallResult:
    pack_id: str
    version: str
    install_path: Path
    validation: PackValidationResult


class PackInstaller:
    def __init__(self, validator: PackValidator | None = None, registry: PackRegistry | None = None) -> None:
        self.validator = validator or PackValidator()
        self.registry = registry or PackRegistry()

    def install(self, pack_path: str | Path, *, force: bool = False) -> InstallResult:
        validation = self.validator.validate(pack_path)
        if not validation.passed or validation.manifest is None:
            message = "; ".join(validation.errors) or "pack validation failed"
            raise PackError("PACK_VALIDATION_FAILED", message)

        manifest, root = load_manifest(pack_path)
        install_path = pack_store_dir() / manifest.id / manifest.version
        install_path.parent.mkdir(parents=True, exist_ok=True)
        if install_path.exists():
            if not force:
                raise PackError("PACK_EXISTS", f"pack already installed: {manifest.id}@{manifest.version}")
            shutil.rmtree(install_path)
        shutil.copytree(root, install_path)

        record = InstalledPackRecord.from_manifest(
            manifest,
            install_path=install_path,
            source_path=root,
            validation_passed=True,
        )
        self.registry.add(record, force=force)
        return InstallResult(
            pack_id=manifest.id,
            version=manifest.version,
            install_path=install_path,
            validation=validation,
        )

    def uninstall(self, pack_id: str, version: str | None = None) -> int:
        records = self.registry.list()
        targets = [
            item
            for item in records
            if item.get("id") == pack_id and (version is None or item.get("version") == version)
        ]
        for target in targets:
            path = Path(str(target.get("install_path", "")))
            if path.exists():
                shutil.rmtree(path)
        removed = self.registry.remove(pack_id, version)
        if removed == 0:
            raise PackError("PACK_NOT_FOUND", f"pack not installed: {pack_id}{'@' + version if version else ''}")
        return removed

    def list_installed(self) -> list[dict[str, str]]:
        return self.registry.list()

    def get_pack(self, pack_id: str, version: str | None = None) -> dict[str, str]:
        record = self.registry.find(pack_id, version)
        if record is None:
            raise PackError("PACK_NOT_FOUND", f"pack not installed: {pack_id}{'@' + version if version else ''}")
        return record
