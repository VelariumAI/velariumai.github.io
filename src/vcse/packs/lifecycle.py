"""Pack lifecycle transitions for mutable/frozen states."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from vcse.packs.errors import PackError

_ALLOWED_TRANSITIONS = {
    ("candidate", "certified"),
    ("candidate", "frozen"),
    ("candidate", "archived"),
    ("certified", "frozen"),
    ("certified", "archived"),
    ("frozen", "archived"),
}


class PackLifecycleError(PackError):
    def __init__(self, error_type: str, reason: str) -> None:
        super().__init__(error_type, reason)


class PackLifecycleManager:
    def _pack_json_path(self, pack_path: Path) -> Path:
        return Path(pack_path) / "pack.json"

    def _load_pack_metadata(self, pack_path: Path) -> dict:
        path = self._pack_json_path(pack_path)
        if not path.exists():
            raise PackLifecycleError("MISSING_PACK", f"missing pack.json in {pack_path}")
        payload = json.loads(path.read_text())
        if not isinstance(payload, dict):
            raise PackLifecycleError("INVALID_PACK", f"pack metadata must be object: {path}")
        return payload

    def _write_pack_metadata(self, pack_path: Path, payload: dict) -> None:
        path = self._pack_json_path(pack_path)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def get_status(self, pack_path: Path) -> str:
        payload = self._load_pack_metadata(pack_path)
        status = str(payload.get("lifecycle_status", "candidate")).strip()
        return status or "candidate"

    def transition(self, pack_path: Path, new_status: str) -> None:
        new_status = str(new_status).strip()
        payload = self._load_pack_metadata(pack_path)
        current = str(payload.get("lifecycle_status", "candidate")).strip() or "candidate"
        if current == new_status:
            raise PackLifecycleError("INVALID_TRANSITION", f"invalid lifecycle transition: {current} -> {new_status}")
        if (current, new_status) not in _ALLOWED_TRANSITIONS:
            raise PackLifecycleError("INVALID_TRANSITION", f"invalid lifecycle transition: {current} -> {new_status}")
        payload["lifecycle_status"] = new_status
        self._write_pack_metadata(pack_path, payload)

    def freeze_pack(self, pack_path: Path) -> None:
        self.transition(pack_path, "frozen")

    def archive_pack(self, pack_path: Path) -> None:
        self.transition(pack_path, "archived")

    def create_version(self, pack_path: Path, new_version: str) -> Path:
        if re.match(r"^\d+\.\d+\.\d+$", str(new_version).strip()) is None:
            raise PackLifecycleError("INVALID_SEMVER", f"invalid semantic version: {new_version}")
        payload = self._load_pack_metadata(pack_path)
        pack_id = str(payload.get("id", "")).strip()
        if not pack_id:
            raise PackLifecycleError("INVALID_PACK", f"pack id missing in {pack_path / 'pack.json'}")

        target = Path(pack_path).parent / f"{pack_id}@v{new_version}"
        if target.exists():
            raise PackLifecycleError("VERSION_EXISTS", f"target version already exists: {target}")
        shutil.copytree(pack_path, target)
        target_payload = self._load_pack_metadata(target)
        target_payload["version"] = new_version
        target_payload["lifecycle_status"] = "candidate"
        self._write_pack_metadata(target, target_payload)
        return target

    def assert_writable(self, pack_path: Path) -> None:
        status = self.get_status(pack_path)
        if status == "frozen":
            raise PackLifecycleError("PACK_FROZEN", f"pack is frozen: {pack_path}")
        if status == "archived":
            raise PackLifecycleError("PACK_ARCHIVED", f"pack is archived: {pack_path}")
