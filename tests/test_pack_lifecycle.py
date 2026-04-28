from __future__ import annotations

import json
from pathlib import Path

import pytest

from vcse.packs.lifecycle import PackLifecycleError, PackLifecycleManager


def _write_pack(path: Path, pack_id: str = "capitals", version: str = "1.0.0", status: str = "candidate") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "pack.json").write_text(
        json.dumps(
            {
                "id": pack_id,
                "version": version,
                "domain": "general",
                "lifecycle_status": status,
            }
        )
        + "\n"
    )
    (path / "claims.jsonl").write_text("")
    (path / "provenance.jsonl").write_text("")
    return path


def test_transition_and_invalid_transition(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path / "pack")
    manager = PackLifecycleManager()
    manager.transition(pack_path, "certified")
    assert manager.get_status(pack_path) == "certified"
    manager.freeze_pack(pack_path)
    assert manager.get_status(pack_path) == "frozen"
    with pytest.raises(PackLifecycleError, match="INVALID_TRANSITION"):
        manager.transition(pack_path, "candidate")


def test_assert_writable_blocks_frozen_and_archived(tmp_path: Path) -> None:
    manager = PackLifecycleManager()
    frozen = _write_pack(tmp_path / "frozen", status="frozen")
    archived = _write_pack(tmp_path / "archived", status="archived")

    with pytest.raises(PackLifecycleError, match="PACK_FROZEN"):
        manager.assert_writable(frozen)
    with pytest.raises(PackLifecycleError, match="PACK_ARCHIVED"):
        manager.assert_writable(archived)


def test_create_version_validates_semver_and_copies(tmp_path: Path) -> None:
    manager = PackLifecycleManager()
    pack_path = _write_pack(tmp_path / "source", pack_id="capitals", version="1.0.0", status="frozen")
    new_path = manager.create_version(pack_path, "1.0.1")

    assert new_path.name == "capitals@v1.0.1"
    payload = json.loads((new_path / "pack.json").read_text())
    assert payload["version"] == "1.0.1"
    assert payload["lifecycle_status"] == "candidate"
    source_payload = json.loads((pack_path / "pack.json").read_text())
    assert source_payload["version"] == "1.0.0"
    assert source_payload["lifecycle_status"] == "frozen"

    with pytest.raises(PackLifecycleError, match="INVALID_SEMVER"):
        manager.create_version(pack_path, "1.0")
    with pytest.raises(PackLifecycleError, match="VERSION_EXISTS"):
        manager.create_version(pack_path, "1.0.1")
