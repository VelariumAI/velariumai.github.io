"""Ledger audit helpers."""

from __future__ import annotations

import json
from pathlib import Path

from vcse.ledger.merkle import pack_integrity_report
from vcse.ledger.store import LedgerStore


def verify_ledger(path: str | Path) -> dict[str, object]:
    ok, errors = LedgerStore(path).verify()
    return {"ok": ok, "errors": errors}


def verify_pack_ledger(pack_path: str | Path) -> dict[str, object]:
    root = Path(pack_path)
    ledger_path = root / "ledger_snapshot.json"
    ok, errors = LedgerStore(ledger_path).verify()
    return {"ok": ok, "errors": errors, "ledger_path": str(ledger_path)}


def export_ledger(ledger_path: str | Path, output_path: str | Path) -> Path:
    source = Path(ledger_path)
    out = Path(output_path)
    out.write_text(source.read_text())
    return out


def build_integrity(pack_path: str | Path) -> dict[str, object]:
    root = Path(pack_path)
    manifest_path = root / "pack.json"
    if not manifest_path.exists():
        return {"error": "missing pack.json"}
    manifest = json.loads(manifest_path.read_text())
    artifacts: list[str] = []
    for values in manifest.get("artifacts", {}).values():
        artifacts.extend([str(v) for v in values])
    artifacts.extend(["pack.json"])
    artifacts = sorted(set(artifacts))
    report = pack_integrity_report(root, artifacts)
    return report.to_dict()
