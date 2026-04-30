import json
from pathlib import Path

import pytest

from vcse.packs import PackError
from vcse.packs.registry import PackRegistry


def test_registry_corrupt_file_fails_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    registry = PackRegistry(path=path)

    with pytest.raises(PackError) as exc:
        registry.load()

    assert exc.value.error_type == "REGISTRY_CORRUPT"


def test_registry_empty_default(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VCSE_PACK_HOME", str(tmp_path / "vcse_home"))
    registry = PackRegistry()

    assert registry.list() == []
    payload = registry.load()
    assert payload == {"installed_packs": []}
