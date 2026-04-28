"""Deterministic Wikidata JSON extractor for CAKE."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from vcse.cake.errors import CakeExtractionError
from vcse.cake.snapshot import FetchedSource
from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgeProvenance

PROPERTY_MAP: dict[str, str] = {
    "P36": "capital_of",
    "P17": "located_in_country",
    "P31": "instance_of",
}


class WikidataExtractor:
    """Extract KnowledgeClaims from a simplified Wikidata JSON entity dump."""

    def extract(
        self,
        fetched: FetchedSource,
        snapshot_id: str,
        *,
        limit: int | None = None,
    ) -> list[KnowledgeClaim]:
        try:
            data = json.loads(fetched.raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CakeExtractionError("MALFORMED_JSON", f"wikidata parse error: {exc}") from exc

        entities: dict[str, Any] = data.get("entities", {})
        if not isinstance(entities, dict):
            raise CakeExtractionError("INVALID_STRUCTURE", "'entities' must be a dict")

        # Build label lookup for object resolution
        label_map: dict[str, str] = {}
        for qid, entity in entities.items():
            label = _get_en_label(entity)
            if label:
                label_map[qid] = label

        claims: list[KnowledgeClaim] = []
        now = datetime.now(timezone.utc).isoformat()

        for qid, entity in entities.items():
            if limit is not None and len(claims) >= limit:
                break
            subject_label = label_map.get(qid, qid)
            raw_claims = entity.get("claims", {})
            if not isinstance(raw_claims, dict):
                continue
            for prop_id, relation in PROPERTY_MAP.items():
                if prop_id not in raw_claims:
                    continue
                for statement in raw_claims[prop_id]:
                    obj_label = _extract_object_label(statement, label_map)
                    if obj_label is None:
                        continue
                    prov = KnowledgeProvenance(
                        source_id=fetched.source_id,
                        source_type="wikidata_json",
                        location=snapshot_id,
                        evidence_text=f"{subject_label} {prop_id}={relation} {obj_label}",
                        trust_level="unrated",
                        confidence=0.9,
                    )
                    claim = KnowledgeClaim(
                        subject=subject_label,
                        relation=relation,
                        object=obj_label,
                        provenance=prov,
                        qualifiers={"snapshot_id": snapshot_id, "wikidata_entity": qid, "wikidata_prop": prop_id},
                        confidence=0.9,
                    )
                    claims.append(claim)
                    if limit is not None and len(claims) >= limit:
                        break

        return claims


def _get_en_label(entity: dict[str, Any]) -> str | None:
    labels = entity.get("labels", {})
    en = labels.get("en", {})
    return en.get("value") if isinstance(en, dict) else None


def _extract_object_label(statement: dict[str, Any], label_map: dict[str, str]) -> str | None:
    try:
        mainsnak = statement.get("mainsnak", {})
        datavalue = mainsnak.get("datavalue", {})
        value = datavalue.get("value", {})
        if isinstance(value, dict):
            obj_qid = value.get("id")
            if obj_qid:
                return label_map.get(obj_qid, obj_qid)
        if isinstance(value, str):
            return value
    except (AttributeError, TypeError):
        pass
    return None