#!/usr/bin/env python3
"""Deterministically generate a CAKE wikidata_json seed from static country facts."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FACT_TABLE_PATH = ROOT / "examples" / "general_world" / "countries_fact_table.json"
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


def main() -> None:
    rows = json.loads(FACT_TABLE_PATH.read_text())
    rows = sorted(rows, key=lambda row: str(row["country"]))

    entities: dict[str, dict[str, object]] = {}
    continent_qids: dict[str, str] = {}

    for row in rows:
        continent = str(row["continent"])
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

        country_qid = _qid("country", country)
        capital_qid = _qid("capital", capital)
        continent_qid = continent_qids[continent]

        entities[capital_qid] = {
            "id": capital_qid,
            "labels": _label(capital),
            "claims": {
                "P31": [_snak(_qid("type", "capital city"))],
            },
        }

        entities[country_qid] = {
            "id": country_qid,
            "labels": _label(country),
            "claims": {
                "P36": [_snak(capital_qid)],
                "P30": [_snak(continent_qid)],
                "P31": [_snak(_qid("type", "country"))],
            },
        }

    entities[_qid("type", "country")] = {
        "id": _qid("type", "country"),
        "labels": _label("country"),
        "claims": {},
    }
    entities[_qid("type", "capital city")] = {
        "id": _qid("type", "capital city"),
        "labels": _label("capital city"),
        "claims": {},
    }

    payload = {
        "entities": {key: entities[key] for key in sorted(entities)},
        "meta": {
            "schema": "vcse.general_world.seed.v1",
            "source": "examples/general_world/countries_fact_table.json",
            "deterministic": True,
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
