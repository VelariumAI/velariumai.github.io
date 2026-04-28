#!/usr/bin/env python3
"""Deterministically generate a CAKE wikidata_json seed from merged world dataset."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FACT_TABLE_PATH = ROOT / "examples" / "knowledge" / "general_world_expanded.json"
OUTPUT_PATH = ROOT / "examples" / "cake" / "general_world_seed.json"


def _qid(kind: str, value: str) -> str:
    safe = "".join(ch for ch in value.lower() if ch.isalnum())
    return f"Q_{kind}_{safe}"


def _label(value: str) -> dict[str, dict[str, str]]:
    return {"en": {"language": "en", "value": value}}


def _snak(target_qid: str) -> dict[str, object]:
    return {
        "mainsnak": {
            "datavalue": {
                "type": "wikibase-entityid",
                "value": {"entity-type": "item", "id": target_qid},
            }
        }
    }


def _string_snak(value: str) -> dict[str, object]:
    return {
        "mainsnak": {
            "datavalue": {
                "type": "string",
                "value": value,
            }
        }
    }


def main() -> None:
    rows = json.loads(FACT_TABLE_PATH.read_text())
    rows = sorted(rows, key=lambda row: str(row["country"]))
    by_cca3 = {str(row.get("cca3", "")).strip(): str(row["country"]) for row in rows if str(row.get("cca3", "")).strip()}

    entities: dict[str, dict[str, object]] = {}
    continent_qids: dict[str, str] = {}
    region_qids: dict[str, str] = {}
    subregion_qids: dict[str, str] = {}
    currency_qids: dict[str, str] = {}
    language_qids: dict[str, str] = {}

    for row in rows:
        continent = str(row["continent"])
        region = str(row["region"])
        subregion = str(row["subregion"])
        currency = str(row["currency"])
        for value, cache, kind in (
            (continent, continent_qids, "continent"),
            (region, region_qids, "region"),
            (subregion, subregion_qids, "subregion"),
            (currency, currency_qids, "currency"),
        ):
            if value and value not in cache:
                qid = _qid(kind, value)
                cache[value] = qid
                entities[qid] = {"id": qid, "labels": _label(value), "claims": {}}

        for language in sorted(set(row.get("languages", []))):
            if language and language not in language_qids:
                qid = _qid("language", language)
                language_qids[language] = qid
                entities[qid] = {"id": qid, "labels": _label(language), "claims": {}}

        if continent not in continent_qids:
            continent_qid = _qid("continent", continent)
            continent_qids[continent] = continent_qid
            entities[continent_qid] = {
                "id": continent_qid,
                "labels": _label(continent),
                "claims": {},
            }

    for row in rows:
        country = str(row["country"])
        capital = str(row["capital"])
        continent = str(row["continent"])
        region = str(row["region"])
        subregion = str(row["subregion"])
        currency = str(row["currency"])
        currency_code = str(row["currency_code"])
        country_code = str(row["country_code"])
        cca3 = str(row["cca3"])

        country_qid = _qid("country", country)
        capital_qid = _qid("capital", capital)
        continent_qid = continent_qids[continent]
        region_qid = region_qids[region]
        subregion_qid = subregion_qids[subregion]
        currency_qid = currency_qids[currency]

        capital_claims = {
            "P31": [_snak(_qid("type", "City"))],
            "P17": [_snak(country_qid)],
        }
        if capital != country:
            capital_claims["P36"] = [_snak(country_qid)]

        entities[capital_qid] = {
            "id": capital_qid,
            "labels": _label(capital),
            "claims": capital_claims,
        }

        entities[country_qid] = {
            "id": country_qid,
            "labels": _label(country),
            "claims": {
                "P36": [_snak(capital_qid)],
                "P2003": [_snak(capital_qid)],
                "P30": [_snak(continent_qid)],
                "P31": [_snak(_qid("type", "Country"))],
                "P2853": [_snak(currency_qid)],
                "P498": [_string_snak(currency_code)],
                "P297": [_string_snak(country_code)],
                "P298": [_string_snak(cca3)],
                "P300": [_snak(region_qid)],
                "P150": [_snak(subregion_qid)],
                "P1448": [_string_snak(str(row["official_name"]))],
            },
        }
        if str(row.get("demonym", "")).strip():
            entities[country_qid]["claims"].setdefault("P551", []).append(_string_snak(str(row["demonym"])))
        for tld in sorted(set(row.get("tlds", []))):
            if tld:
                entities[country_qid]["claims"].setdefault("P960", []).append(_string_snak(str(tld)))
        for alt in sorted(set(row.get("alt_spellings", []))):
            if alt:
                entities[country_qid]["claims"].setdefault("P1813", []).append(_string_snak(str(alt)))
        for border_cca3 in sorted(set(row.get("borders_cca3", []))):
            border_country = by_cca3.get(str(border_cca3).strip())
            if border_country:
                entities[country_qid]["claims"].setdefault("P47", []).append(_snak(_qid("country", border_country)))
        for language in sorted(set(row.get("languages", []))):
            language_qid = language_qids.get(language)
            if language_qid:
                entities[language_qid].setdefault("claims", {}).setdefault("P37", []).append(_snak(country_qid))

    entities[_qid("type", "Country")] = {
        "id": _qid("type", "Country"),
        "labels": _label("Country"),
        "claims": {},
    }
    entities[_qid("type", "City")] = {
        "id": _qid("type", "City"),
        "labels": _label("City"),
        "claims": {},
    }

    payload = {
        "entities": {key: entities[key] for key in sorted(entities)},
        "meta": {
            "schema": "vcse.general_world.seed.v2",
            "source": "examples/knowledge/general_world_expanded.json",
            "deterministic": True,
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
