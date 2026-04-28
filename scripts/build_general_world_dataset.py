#!/usr/bin/env python3
"""Build deterministic general_world validation + merged dataset + coverage benchmark."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "examples" / "knowledge" / "raw"
KNOWLEDGE_DIR = ROOT / "examples" / "knowledge"
BENCHMARK_PATH = ROOT / "benchmarks" / "general_knowledge.jsonl"

ISO_SOURCE = {
    "source_id": "iso_countries",
    "url": "https://raw.githubusercontent.com/mledoze/countries/master/countries.json",
    "required": True,
    "path": RAW_DIR / "iso_countries.json",
}
OPTIONAL_SOURCES = [
    {
        "source_id": "country_capitals",
        "url": "https://raw.githubusercontent.com/samayo/country-json/master/src/country-by-capital-city.json",
        "required": False,
        "path": RAW_DIR / "country_capitals.json",
    },
    {
        "source_id": "country_languages",
        "url": "https://raw.githubusercontent.com/samayo/country-json/master/src/country-by-languages.json",
        "required": False,
        "path": RAW_DIR / "country_languages.json",
    },
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized_name(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _iso_language_names(row: dict[str, Any], fallback_map: dict[str, list[str]]) -> list[str]:
    lang_map = row.get("languages") or {}
    langs = [str(v).strip() for v in lang_map.values() if str(v).strip()]
    if langs:
        return sorted(set(langs))
    name = str((row.get("name") or {}).get("common", "")).strip()
    return sorted(set(fallback_map.get(_normalized_name(name), [])))


def _optional_capital_map(raw: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in raw:
        country = str(row.get("country", "")).strip()
        capital = str(row.get("city", "")).strip()
        if country and capital:
            out[_normalized_name(country)] = capital
    return out


def _optional_language_map(raw: list[dict[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in raw:
        country = str(row.get("country", "")).strip()
        langs = row.get("languages")
        if not country or not isinstance(langs, list):
            continue
        cleaned = sorted({str(v).strip() for v in langs if str(v).strip()})
        if cleaned:
            out[_normalized_name(country)] = cleaned
    return out


def _validate_source(source: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    path = Path(source["path"])
    report = {
        "source_id": source["source_id"],
        "url": source["url"],
        "record_count": 0,
        "status": "ok",
        "errors": [],
        "warnings": [],
        "sha256": None,
    }
    if not path.exists():
        if source["required"]:
            report["status"] = "error"
            report["errors"].append(f"missing required file: {path}")
        else:
            report["status"] = "warning"
            report["warnings"].append(f"optional file missing: {path}")
        return report, None
    try:
        data = _read_json(path)
    except Exception as exc:  # noqa: BLE001
        report["status"] = "error" if source["required"] else "warning"
        bucket = "errors" if source["required"] else "warnings"
        report[bucket].append(f"json parse failed: {exc}")
        return report, None
    report["sha256"] = _sha256(path)
    if not isinstance(data, list) or not data:
        report["status"] = "error" if source["required"] else "warning"
        bucket = "errors" if source["required"] else "warnings"
        report[bucket].append("expected non-empty top-level list")
        return report, None
    report["record_count"] = len(data)
    if source["source_id"] == "iso_countries":
        malformed = 0
        for row in data:
            if not isinstance(row, dict):
                malformed += 1
                continue
            common = str((row.get("name") or {}).get("common", "")).strip()
            if not common:
                malformed += 1
        if malformed:
            report["status"] = "error"
            report["errors"].append(f"{malformed} records missing country name")
    return report, data


def _build_merged(
    iso_rows: list[dict[str, Any]],
    capital_map: dict[str, str],
    language_map: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], list[str]]:
    merged: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_countries: set[str] = set()

    for row in sorted(iso_rows, key=lambda x: str((x.get("name") or {}).get("common", "")).strip()):
        name = str((row.get("name") or {}).get("common", "")).strip()
        if not name:
            continue
        normalized = _normalized_name(name)
        if normalized in seen_countries:
            raise ValueError(f"duplicate country after merge: {name}")
        seen_countries.add(normalized)

        official = str((row.get("name") or {}).get("official", "")).strip() or name
        cca2 = str(row.get("cca2", "")).strip()
        cca3 = str(row.get("cca3", "")).strip()
        region = str(row.get("region", "")).strip()
        subregion = str(row.get("subregion", "")).strip()
        capitals = row.get("capital") if isinstance(row.get("capital"), list) else []
        capital = str(capitals[0]).strip() if capitals else ""
        if not capital:
            capital = capital_map.get(normalized, "")
        currencies = row.get("currencies") if isinstance(row.get("currencies"), dict) else {}
        currency_code = ""
        currency_name = ""
        for code in sorted(currencies):
            value = currencies.get(code)
            if isinstance(value, dict):
                maybe_name = str(value.get("name", "")).strip()
                if maybe_name:
                    currency_code = str(code).strip()
                    currency_name = maybe_name
                    break
        languages = _iso_language_names(row, language_map)

        if not name:
            warnings.append(f"skip missing country name: {row!r}")
            continue
        if not capital:
            warnings.append(f"skip missing capital: {name}")
            continue
        if not (region or subregion):
            warnings.append(f"skip missing region/subregion: {name}")
            continue
        if not (currency_name or currency_code):
            warnings.append(f"skip missing currency: {name}")
            continue
        if not languages:
            warnings.append(f"skip missing languages: {name}")
            continue
        if not cca2:
            warnings.append(f"skip missing country_code: {name}")
            continue

        source_ids = ["iso_countries"]
        if (row.get("capital") in (None, []) or not row.get("capital")) and normalized in capital_map:
            source_ids.append("country_capitals")
        if (not row.get("languages")) and normalized in language_map:
            source_ids.append("country_languages")

        merged.append(
            {
                "country": name,
                "official_name": official,
                "capital": capital,
                "continent": region or subregion,
                "region": region or subregion,
                "subregion": subregion or region,
                "currency": currency_name,
                "currency_code": currency_code,
                "languages": languages,
                "country_code": cca2,
                "cca3": cca3,
                "alt_spellings": sorted({str(v).strip() for v in row.get("altSpellings", []) if str(v).strip()}),
                "tlds": sorted({str(v).strip() for v in row.get("tld", []) if str(v).strip()}),
                "demonym": str((((row.get("demonyms") or {}).get("eng") or {}).get("m", ""))).strip(),
                "borders_cca3": sorted({str(v).strip() for v in row.get("borders", []) if str(v).strip()}),
                "source_ids": source_ids,
            }
        )

    return merged, warnings


def _build_coverage_cases(merged: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for row in merged:
        country = row["country"]
        capital = row["capital"]
        region = row["continent"]
        currency = row["currency"]
        country_code = row["country_code"]
        languages = row["languages"]
        prefix = _normalized_name(country).replace(" ", "_")

        cases.append(
            {
                "id": f"gk_capital_{prefix}_001",
                "question": f"What is the capital of {country}?",
                "expected_answer": capital,
                "expected_relation": "capital_of",
                "expected_status": "VERIFIED_OR_CANDIDATE",
                "subject": country,
                "relation": "capital_of",
                "object": capital,
                "expected": "candidate",
            }
        )
        cases.append(
            {
                "id": f"gk_city_country_{prefix}_001",
                "question": f"What country is {capital} in?",
                "expected_answer": country,
                "expected_relation": "located_in_country",
                "expected_status": "VERIFIED_OR_CANDIDATE",
                "subject": capital,
                "relation": "located_in_country",
                "object": country,
                "expected": "candidate",
            }
        )
        cases.append(
            {
                "id": f"gk_continent_{prefix}_001",
                "question": f"What continent is {country} part of?",
                "expected_answer": region,
                "expected_relation": "part_of",
                "expected_status": "VERIFIED_OR_CANDIDATE",
                "subject": country,
                "relation": "part_of",
                "object": region,
                "expected": "candidate",
            }
        )
        cases.append(
            {
                "id": f"gk_country_type_{prefix}_001",
                "question": f"Is {country} a country?",
                "expected_answer": "Country",
                "expected_relation": "instance_of",
                "expected_status": "VERIFIED_OR_CANDIDATE",
                "subject": country,
                "relation": "instance_of",
                "object": "Country",
                "expected": "candidate",
            }
        )
        cases.append(
            {
                "id": f"gk_city_type_{prefix}_001",
                "question": f"Is {capital} a city?",
                "expected_answer": "City",
                "expected_relation": "instance_of",
                "expected_status": "VERIFIED_OR_CANDIDATE",
                "subject": capital,
                "relation": "instance_of",
                "object": "City",
                "expected": "candidate",
            }
        )
        cases.append(
            {
                "id": f"gk_currency_{prefix}_001",
                "question": f"What currency does {country} use?",
                "expected_answer": currency,
                "expected_relation": "uses_currency",
                "expected_status": "VERIFIED_OR_CANDIDATE",
                "subject": country,
                "relation": "uses_currency",
                "object": currency,
                "expected": "candidate",
            }
        )
        cases.append(
            {
                "id": f"gk_code_{prefix}_001",
                "question": f"What is the country code of {country}?",
                "expected_answer": country_code,
                "expected_relation": "has_country_code",
                "expected_status": "VERIFIED_OR_CANDIDATE",
                "subject": country,
                "relation": "has_country_code",
                "object": country_code,
                "expected": "candidate",
            }
        )
        if languages:
            language = languages[0]
            cases.append(
                {
                    "id": f"gk_language_{prefix}_001",
                    "question": f"What language is spoken in {country}?",
                    "expected_answer": language,
                    "expected_relation": "language_of",
                    "expected_status": "VERIFIED_OR_CANDIDATE",
                    "subject": language,
                    "relation": "language_of",
                    "object": country,
                    "expected": "candidate",
                }
            )
    cases.sort(key=lambda x: x["id"])
    return cases


def main() -> None:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    raw_sources = [ISO_SOURCE, *OPTIONAL_SOURCES]
    reports: list[dict[str, Any]] = []
    raw_data: dict[str, Any] = {}

    for source in raw_sources:
        report, data = _validate_source(source)
        reports.append(report)
        if data is not None:
            raw_data[source["source_id"]] = data

    validation_report = {
        "schema": "vcse.general_world.source_validation.v2",
        "sources": reports,
    }
    (KNOWLEDGE_DIR / "general_world_source_validation.json").write_text(
        json.dumps(validation_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    iso_report = next(item for item in reports if item["source_id"] == "iso_countries")
    if iso_report["status"] != "ok":
        raise SystemExit("required source validation failed: iso_countries")

    capitals = raw_data.get("country_capitals", [])
    languages = raw_data.get("country_languages", [])
    capital_map = _optional_capital_map(capitals) if isinstance(capitals, list) else {}
    language_map = _optional_language_map(languages) if isinstance(languages, list) else {}

    merged, merge_warnings = _build_merged(raw_data["iso_countries"], capital_map, language_map)
    if len(merged) < 100:
        raise SystemExit(f"merged dataset too small: {len(merged)}")

    merged_path = KNOWLEDGE_DIR / "general_world_expanded.json"
    merged_path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    validation_report["merge"] = {
        "country_count": len(merged),
        "warnings": merge_warnings,
    }
    (KNOWLEDGE_DIR / "general_world_source_validation.json").write_text(
        json.dumps(validation_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    cases = _build_coverage_cases(merged)
    BENCHMARK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with BENCHMARK_PATH.open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(json.dumps(case, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
