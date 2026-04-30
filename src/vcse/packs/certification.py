"""Candidate pack certification workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CertificationReport:
    source_pack_id: str
    output_pack_id: str
    status: str
    claim_count: int
    duplicate_count: int
    missing_provenance_count: int
    certified_claim_count: int
    reasons: list[str]


def certify_candidate_pack(
    source_pack_id: str,
    output_pack_id: str,
    packs_root: Path = Path("examples") / "packs",
) -> CertificationReport:
    source_dir = packs_root / source_pack_id
    output_dir = packs_root / output_pack_id
    reasons: list[str] = []
    duplicate_count = 0
    missing_provenance_count = 0
    claim_count = 0

    if not source_dir.exists():
        reasons.append(f"source pack not found: {source_pack_id}")
        return CertificationReport(
            source_pack_id=source_pack_id,
            output_pack_id=output_pack_id,
            status="CERTIFICATION_FAILED",
            claim_count=0,
            duplicate_count=0,
            missing_provenance_count=0,
            certified_claim_count=0,
            reasons=reasons,
        )

    pack_path = source_dir / "pack.json"
    claims_path = source_dir / "claims.jsonl"
    provenance_path = source_dir / "provenance.jsonl"
    trust_report_path = source_dir / "trust_report.json"
    metrics_path = source_dir / "metrics.json"

    if not pack_path.exists():
        reasons.append("missing pack.json")
    if not claims_path.exists():
        reasons.append("missing claims.jsonl")
    if not provenance_path.exists():
        reasons.append("missing provenance.jsonl")
    if not trust_report_path.exists():
        reasons.append("missing trust_report.json")
    if not metrics_path.exists():
        reasons.append("missing metrics.json")
    if output_dir.exists():
        reasons.append(f"output pack already exists: {output_pack_id}")
    if reasons:
        return CertificationReport(
            source_pack_id=source_pack_id,
            output_pack_id=output_pack_id,
            status="CERTIFICATION_FAILED",
            claim_count=0,
            duplicate_count=0,
            missing_provenance_count=0,
            certified_claim_count=0,
            reasons=sorted(reasons),
        )

    try:
        source_manifest = json.loads(pack_path.read_text())
    except json.JSONDecodeError as exc:
        reasons.append(f"invalid pack.json: {exc.msg}")
        source_manifest = {}
    if source_manifest.get("lifecycle_status") != "candidate":
        reasons.append("source lifecycle_status must be candidate")

    claims_rows: list[dict] = []
    seen_keys: set[str] = set()
    for idx, line in enumerate(claims_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            reasons.append(f"invalid claims.jsonl line {idx}: {exc.msg}")
            continue
        claims_rows.append(payload)
        subject = str(payload.get("subject", "")).strip()
        relation = str(payload.get("relation", "")).strip()
        obj = str(payload.get("object", "")).strip()
        if not subject or not relation or not obj:
            reasons.append(f"invalid claim shape at line {idx}")
            continue
        key = "|".join([subject, relation, obj])
        if key in seen_keys:
            duplicate_count += 1
        seen_keys.add(key)
        provenance = payload.get("provenance")
        if not isinstance(provenance, dict):
            missing_provenance_count += 1
            continue
        required = ["source_type", "source_id", "location", "evidence_text", "confidence", "trust_level"]
        if any(str(provenance.get(item, "")).strip() == "" for item in required):
            missing_provenance_count += 1

    provenance_rows = []
    for idx, line in enumerate(provenance_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            reasons.append(f"invalid provenance.jsonl line {idx}: {exc.msg}")
            continue
        provenance_rows.append(payload)
        required = ["source_type", "source_id", "location", "evidence_text", "confidence", "trust_level"]
        missing = [item for item in required if str(payload.get(item, "")).strip() == ""]
        if missing:
            reasons.append(f"incomplete provenance row at line {idx}")

    claim_count = len(claims_rows)
    if duplicate_count > 0:
        reasons.append(f"duplicate claims detected: {duplicate_count}")
    if missing_provenance_count > 0:
        reasons.append(f"claims missing complete provenance: {missing_provenance_count}")
    if len(provenance_rows) != claim_count:
        reasons.append("provenance.jsonl row count must match claims.jsonl row count")

    if reasons:
        return CertificationReport(
            source_pack_id=source_pack_id,
            output_pack_id=output_pack_id,
            status="CERTIFICATION_FAILED",
            claim_count=claim_count,
            duplicate_count=duplicate_count,
            missing_provenance_count=missing_provenance_count,
            certified_claim_count=0,
            reasons=sorted(reasons),
        )

    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "claims.jsonl").write_bytes(claims_path.read_bytes())
    (output_dir / "provenance.jsonl").write_bytes(provenance_path.read_bytes())
    (output_dir / "pack.json").write_text(
        json.dumps(
            {
                "pack_id": output_pack_id,
                "id": output_pack_id,
                "version": "1.0.0",
                "lifecycle_status": "certified",
                "certified_from": source_pack_id,
                "claim_count": claim_count,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    (output_dir / "trust_report.json").write_text(
        json.dumps(
            {
                "status": "CERTIFIED",
                "source_pack": source_pack_id,
                "output_pack": output_pack_id,
                "certified_claim_count": claim_count,
                "conflicts": [],
                "decisions": [],
                "staleness": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(
            {
                "certification_status": "CERTIFICATION_PASSED",
                "source_pack": source_pack_id,
                "output_pack": output_pack_id,
                "claim_count": claim_count,
                "duplicate_count": 0,
                "missing_provenance_count": 0,
                "certified_claim_count": claim_count,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return CertificationReport(
        source_pack_id=source_pack_id,
        output_pack_id=output_pack_id,
        status="CERTIFICATION_PASSED",
        claim_count=claim_count,
        duplicate_count=0,
        missing_provenance_count=0,
        certified_claim_count=claim_count,
        reasons=[],
    )
