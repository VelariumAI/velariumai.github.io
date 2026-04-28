from pathlib import Path

import pytest

from vcse.packs import PackError
from vcse.packs.installer import PackInstaller
from vcse.packs.resolver import DependencyResolver


def _pack_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "packs" / name


def test_dependency_ordering(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VCSE_PACK_HOME", str(tmp_path / "vcse_home"))
    installer = PackInstaller()
    installer.install(_pack_path("logic_basic"))
    installer.install(_pack_path("mortality_basic"))

    ordered = DependencyResolver().resolve(["vrm.mortality.basic@1.0.0"]).ordered
    names = [f"{item.id}@{item.version}" for item in ordered]

    assert names == ["vrm.logic.basic@1.0.0", "vrm.mortality.basic@1.0.0"]


def test_missing_dependency_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VCSE_PACK_HOME", str(tmp_path / "vcse_home"))
    installer = PackInstaller()
    installer.install(_pack_path("mortality_basic"), force=True)

    with pytest.raises(PackError) as exc:
        DependencyResolver().resolve(["vrm.mortality.basic@1.0.0"])

    assert exc.value.error_type == "MISSING_DEPENDENCY"
