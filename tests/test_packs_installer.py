from pathlib import Path

import pytest

from vcse.packs import PackError
from vcse.packs.installer import PackInstaller


def _logic_pack_path() -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "packs" / "logic_basic"


def test_install_list_get_and_uninstall(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VCSE_PACK_HOME", str(tmp_path / "vcse_home"))
    installer = PackInstaller()

    result = installer.install(_logic_pack_path())
    listed = installer.list_installed()
    fetched = installer.get_pack("vrm.logic.basic", "1.0.0")
    removed = installer.uninstall("vrm.logic.basic", "1.0.0")

    assert result.pack_id == "vrm.logic.basic"
    assert listed
    assert fetched["id"] == "vrm.logic.basic"
    assert removed == 1


def test_install_does_not_overwrite_without_force(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VCSE_PACK_HOME", str(tmp_path / "vcse_home"))
    installer = PackInstaller()
    installer.install(_logic_pack_path())

    with pytest.raises(PackError) as exc:
        installer.install(_logic_pack_path())

    assert exc.value.error_type == "PACK_EXISTS"
