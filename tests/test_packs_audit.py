from pathlib import Path

from vcse.packs.auditor import PackAuditor
from vcse.packs.installer import PackInstaller


def _pack_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "packs" / name


def test_pack_audit_report(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VCSE_PACK_HOME", str(tmp_path / "vcse_home"))
    installer = PackInstaller()
    installer.install(_pack_path("logic_basic"))

    report = PackAuditor().audit("vrm.logic.basic")

    assert report.claims_count >= 1
    assert report.provenance_coverage_percent > 0.0
    assert report.hash_integrity_status in {"PASS", "FAIL"}
