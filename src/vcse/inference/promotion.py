"""Controlled promotion of stable inferred claims into candidate knowledge."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromotedClaim:
    subject: str
    relation: str
    object: str
    source_claims: tuple[str, ...]
    inference_type: str
    promoted_at: str

    @property
    def claim_key(self) -> str:
        return "|".join([self.subject, self.relation, self.object])

@dataclass(frozen=True)
class PromotionPackBuildResult:
    pack_dir: Path
    claim_count: int


def _extract_source_claims(stable_claim: object) -> tuple[str, ...]:
    source_claims = getattr(stable_claim, "source_claims", None)
    if isinstance(source_claims, tuple):
        return source_claims
    if isinstance(source_claims, list):
        return tuple(str(item) for item in source_claims)
    derived_from = getattr(stable_claim, "derived_from", None)
    if isinstance(derived_from, tuple):
        return tuple(str(item) for item in derived_from)
    if isinstance(derived_from, str):
        return (derived_from,)
    return ()


def promote_stable_claims(
    stable_claims,
    threshold: int,
    promoted_at: str = "1970-01-01T00:00:00+00:00",
) -> list[PromotedClaim]:
    if threshold < 1:
        raise ValueError("threshold must be >= 1")
    promoted: list[PromotedClaim] = []
    for stable_claim in stable_claims:
        occurrences = int(getattr(stable_claim, "occurrences", 0))
        if occurrences < threshold:
            continue
        claim_key = str(getattr(stable_claim, "claim_key", ""))
        parts = claim_key.split("|", 2)
        if len(parts) != 3:
            continue
        promoted.append(
            PromotedClaim(
                subject=parts[0],
                relation=parts[1],
                object=parts[2],
                source_claims=_extract_source_claims(stable_claim),
                inference_type=str(getattr(stable_claim, "inference_type", "")),
                promoted_at=promoted_at,
            )
        )
    return sorted(promoted, key=lambda item: item.claim_key)


def build_pack_from_promoted_claims(
    promoted_claims: list[PromotedClaim],
    pack_id: str,
    source_pack: str,
    threshold: int,
    packs_root: Path = Path("examples") / "packs",
) -> PromotionPackBuildResult:
    ordered = sorted(promoted_claims, key=lambda item: item.claim_key)
    pack_dir = packs_root / pack_id
    pack_dir.mkdir(parents=True, exist_ok=False)

    claims_lines = []
    provenance_lines = []
    for claim in ordered:
        evidence_text = f"{claim.inference_type} from {','.join(claim.source_claims)}"
        provenance = {
            "source_type": "inference_promotion",
            "source_id": source_pack,
            "location": "infer/promote",
            "evidence_text": evidence_text,
            "confidence": 1.0,
            "trust_level": "candidate",
            "inference_type": claim.inference_type,
            "derived_from": list(claim.source_claims),
            "promoted_at": claim.promoted_at,
        }
        claims_lines.append(
            json.dumps(
                {
                    "subject": claim.subject,
                    "relation": claim.relation,
                    "object": claim.object,
                    "trust_tier": "T0_CANDIDATE",
                    "source_ids": [],
                    "created_at": claim.promoted_at,
                    "provenance": provenance,
                    "qualifiers": {
                        "inference_type": claim.inference_type,
                        "derived_from": list(claim.source_claims),
                    },
                    "confidence": 1.0,
                    "trust_flags": ["PROMOTED_FROM_INFERENCE"],
                    "claim_hash": "",
                    "certified_at": None,
                    "supersedes": None,
                },
                sort_keys=True,
            )
        )
        provenance_lines.append(json.dumps(provenance, sort_keys=True))

    (pack_dir / "claims.jsonl").write_text("\n".join(claims_lines) + ("\n" if claims_lines else ""))
    (pack_dir / "provenance.jsonl").write_text("\n".join(provenance_lines) + ("\n" if provenance_lines else ""))
    (pack_dir / "pack.json").write_text(
        json.dumps(
            {
                "id": pack_id,
                "version": "0.1.0",
                "domain": "general",
                "lifecycle_status": "candidate",
                "created_at": ordered[0].promoted_at if ordered else "",
                "claim_count": len(ordered),
                "provenance_count": len(ordered),
                "constraint_count": 0,
                "template_count": 0,
                "conflict_count": 0,
                "metrics": {},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    (pack_dir / "metrics.json").write_text(
        json.dumps(
            {
                "source_pack": source_pack,
                "promotion_threshold": threshold,
                "stable_inferred_count": len(ordered),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    (pack_dir / "trust_report.json").write_text(
        json.dumps({"conflicts": [], "decisions": [], "staleness": []}, indent=2, sort_keys=True) + "\n"
    )
    return PromotionPackBuildResult(pack_dir=pack_dir, claim_count=len(ordered))
