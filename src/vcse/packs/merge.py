"""Controlled merge of certified packs into canonical packs."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class MergeReport:
    source_pack_id: str
    target_pack_id: str
    merged_claim_count: int
    skipped_duplicate_count: int
    final_claim_count: int
    status: str
    reasons: list[str]


def merge_certified_pack(
    source_pack_id: str,
    target_pack_id: str,
    *,
    output_pack_id: str | None = None,
    packs_root: Path = Path("examples") / "packs",
) -> tuple[MergeReport, Path, Path]:
    source_dir = packs_root / source_pack_id
    target_dir = packs_root / target_pack_id
    output_id = output_pack_id or target_pack_id
    output_dir = packs_root / output_id
    reasons: list[str] = []

    if not source_dir.exists():
        reasons.append(f"source pack not found: {source_pack_id}")
    if not target_dir.exists():
        reasons.append(f"target pack not found: {target_pack_id}")
    if output_pack_id and output_dir.exists():
        reasons.append(f"output pack already exists: {output_id}")
    if reasons:
        return (
            MergeReport(
                source_pack_id=source_pack_id,
                target_pack_id=target_pack_id,
                merged_claim_count=0,
                skipped_duplicate_count=0,
                final_claim_count=0,
                status="MERGE_FAILED",
                reasons=sorted(reasons),
            ),
            Path(""),
            output_dir,
        )

    source_meta_path = source_dir / "pack.json"
    source_claims_path = source_dir / "claims.jsonl"
    source_prov_path = source_dir / "provenance.jsonl"
    target_meta_path = target_dir / "pack.json"
    target_claims_path = target_dir / "claims.jsonl"
    target_prov_path = target_dir / "provenance.jsonl"
    for path, label in (
        (source_meta_path, "source missing pack.json"),
        (source_claims_path, "source missing claims.jsonl"),
        (source_prov_path, "source missing provenance.jsonl"),
        (target_meta_path, "target missing pack.json"),
        (target_claims_path, "target missing claims.jsonl"),
        (target_prov_path, "target missing provenance.jsonl"),
    ):
        if not path.exists():
            reasons.append(label)
    if reasons:
        return (
            MergeReport(
                source_pack_id=source_pack_id,
                target_pack_id=target_pack_id,
                merged_claim_count=0,
                skipped_duplicate_count=0,
                final_claim_count=0,
                status="MERGE_FAILED",
                reasons=sorted(reasons),
            ),
            Path(""),
            output_dir,
        )

    try:
        source_meta = json.loads(source_meta_path.read_text())
    except json.JSONDecodeError as exc:
        reasons.append(f"invalid source pack.json: {exc.msg}")
        source_meta = {}
    try:
        target_meta = json.loads(target_meta_path.read_text())
    except json.JSONDecodeError as exc:
        reasons.append(f"invalid target pack.json: {exc.msg}")
        target_meta = {}

    if str(source_meta.get("lifecycle_status", "")).strip() != "certified":
        reasons.append("source lifecycle_status must be certified")

    source_claims = _read_jsonl(source_claims_path, "source claims", reasons)
    source_prov = _read_jsonl(source_prov_path, "source provenance", reasons)
    target_claims = _read_jsonl(target_claims_path, "target claims", reasons)
    target_prov = _read_jsonl(target_prov_path, "target provenance", reasons)

    if reasons:
        return (
            MergeReport(
                source_pack_id=source_pack_id,
                target_pack_id=target_pack_id,
                merged_claim_count=0,
                skipped_duplicate_count=0,
                final_claim_count=0,
                status="MERGE_FAILED",
                reasons=sorted(reasons),
            ),
            Path(""),
            output_dir,
        )

    target_keys = {_claim_key(item) for item in target_claims}
    merged_rows: list[dict] = []
    merged_prov_rows: list[dict] = []
    skipped_duplicate_count = 0

    for idx, row in enumerate(source_claims):
        key = _claim_key(row)
        if key in target_keys:
            skipped_duplicate_count += 1
            continue
        target_keys.add(key)
        merged_rows.append(row)
        prov_from_claim = row.get("provenance")
        if isinstance(prov_from_claim, dict):
            merged_prov_rows.append(prov_from_claim)
        elif idx < len(source_prov) and isinstance(source_prov[idx], dict):
            merged_prov_rows.append(source_prov[idx])
        else:
            reasons.append(f"missing provenance for source claim key: {key}")

    if reasons:
        return (
            MergeReport(
                source_pack_id=source_pack_id,
                target_pack_id=target_pack_id,
                merged_claim_count=0,
                skipped_duplicate_count=skipped_duplicate_count,
                final_claim_count=len(target_claims),
                status="MERGE_FAILED",
                reasons=sorted(reasons),
            ),
            Path(""),
            output_dir,
        )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    snapshot_dir = packs_root / f"{target_pack_id}_snapshot_{timestamp}"
    shutil.copytree(target_dir, snapshot_dir)

    final_claims = sorted([*target_claims, *merged_rows], key=_claim_key)
    final_provenance = [*target_prov, *merged_prov_rows]

    if output_pack_id:
        shutil.copytree(target_dir, output_dir)

    write_dir = output_dir if output_pack_id else target_dir
    _write_jsonl(write_dir / "claims.jsonl", final_claims)
    _write_jsonl(write_dir / "provenance.jsonl", final_provenance)

    old_version = str(target_meta.get("version", "1.0.0"))
    target_meta["version"] = _next_minor_version(old_version)
    target_meta["claim_count"] = len(final_claims)
    target_meta["provenance_count"] = len(final_provenance)
    target_meta["merged_from"] = source_pack_id
    if output_pack_id:
        target_meta["id"] = output_pack_id
        target_meta["pack_id"] = output_pack_id
    (write_dir / "pack.json").write_text(json.dumps(target_meta, indent=2, sort_keys=True) + "\n")

    return (
        MergeReport(
            source_pack_id=source_pack_id,
            target_pack_id=target_pack_id,
            merged_claim_count=len(merged_rows),
            skipped_duplicate_count=skipped_duplicate_count,
            final_claim_count=len(final_claims),
            status="MERGE_PASSED",
            reasons=[],
        ),
        snapshot_dir,
        write_dir,
    )


def _claim_key(claim: dict) -> str:
    subject = str(claim.get("subject", "")).strip()
    relation = str(claim.get("relation", "")).strip()
    obj = str(claim.get("object", "")).strip()
    return "|".join([subject, relation, obj])


def _read_jsonl(path: Path, label: str, reasons: list[str]) -> list[dict]:
    rows: list[dict] = []
    for idx, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            reasons.append(f"invalid {label} line {idx}: {exc.msg}")
            continue
        if not isinstance(payload, dict):
            reasons.append(f"invalid {label} line {idx}: expected object")
            continue
        rows.append(payload)
    return rows


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    lines = [json.dumps(item, sort_keys=True) for item in rows]
    path.write_text(("\n".join(lines) + "\n") if lines else "")


def _next_minor_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"invalid semantic version: {version}")
    major, minor, _patch = [int(item) for item in parts]
    return f"{major}.{minor + 1}.0"
