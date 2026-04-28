import json
from pathlib import Path

from vcse.packs.validator import PackValidator


def _logic_pack_path() -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "packs" / "logic_basic"


def test_pack_validator_accepts_valid_example_pack() -> None:
    result = PackValidator().validate(_logic_pack_path())

    assert result.passed is True
    assert result.errors == []
    assert result.artifact_count >= 4


def test_pack_validator_fails_when_manifest_invalid_semver(tmp_path: Path) -> None:
    src = _logic_pack_path()
    dst = tmp_path / "bad_pack"
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        target = dst / item.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.read_bytes())

    manifest = json.loads((dst / "pack.json").read_text())
    manifest["version"] = "1.0"
    (dst / "pack.json").write_text(json.dumps(manifest, indent=2))

    result = PackValidator().validate(dst)

    assert result.passed is False
    assert any("invalid manifest version semver" in error for error in result.errors)
