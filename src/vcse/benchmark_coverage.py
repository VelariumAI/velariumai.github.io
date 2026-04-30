"""Deterministic pack coverage benchmark."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from vcse.benchmark_inference_classification import InferenceType, classify_resolution_for_claim
from vcse.inference.inverse import infer_inverse_claims
from vcse.inference.transitive import infer_transitive_claims
from vcse.inference.stability import InferenceStabilityTracker
from vcse.knowledge.pack_model import KnowledgeClaim
from vcse.packs.runtime_store import RuntimeStore, load_runtime_claim_objects_if_valid, runtime_store_path_for_pack
from vcse.query.planner import QueryPlanner


class CoverageBenchmarkError(ValueError):
    def __init__(self, error_type: str, reason: str) -> None:
        super().__init__(f"{error_type}: {reason}")
        self.error_type = error_type
        self.reason = reason


def run_coverage_benchmark(pack_path: Path, benchmark_path: Path, planned: bool = False) -> dict[str, Any]:
    load_started = time.perf_counter()
    runtime_claims = load_runtime_claim_objects_if_valid(pack_path, pack_path.name)
    backend_used = "sqlite" if runtime_claims is not None else "jsonl"
    claims = runtime_claims if runtime_claims is not None else _load_claims(pack_path)
    claim_models = _load_claim_models(claims)
    cases = _load_cases(benchmark_path)
    load_time_ms = round((time.perf_counter() - load_started) * 1000, 3)
    query_started = time.perf_counter()
    claim_map = {
        (str(claim.get("subject", "")), str(claim.get("relation", "")), str(claim.get("object", ""))): claim
        for claim in claims
        if isinstance(claim, dict)
    }
    results: list[dict[str, str]] = []
    verified = 0
    candidate = 0
    unknown = 0
    incorrect = 0
    explicit_answer_count = 0
    inverse_inferred_count = 0
    transitive_inferred_count = 0
    unknown_count = 0
    unsupported_query_count = 0
    false_verified_count = 0
    planned_rows_examined_total = 0
    planned_shards_total = 0
    planned_fallback_count = 0
    planned_cases = 0
    planned_plan_time_ms = 0.0
    planned_explicit_lookup_ms = 0.0
    planned_inference_lookup_ms = 0.0
    planned_fallback_ms = 0.0
    planned_render_ms = 0.0
    planned_total_query_ms = 0.0
    stability_threshold_used = 2
    tracker = InferenceStabilityTracker()
    planner = QueryPlanner()
    runtime_store: RuntimeStore | None = None
    inverse_map: dict[tuple[str, str], set[str]] = {}
    transitive_map: dict[tuple[str, str], set[str]] = {}
    if planned:
        pack_json = pack_path / "pack.json"
        pack_id = pack_path.name
        if pack_json.exists():
            try:
                payload = json.loads(pack_json.read_text())
                pack_id = str(payload.get("id") or payload.get("pack_id") or pack_id)
            except Exception:
                pass
        db_path = runtime_store_path_for_pack(pack_id)
        if db_path.exists():
            runtime_store = RuntimeStore(db_path)
    if planned:
        inverse_map = _build_inference_map(infer_inverse_claims(claim_models))
        transitive_map = _build_inference_map(infer_transitive_claims(claim_models))

    try:
        for case in cases:
            key = (case["subject"], case["relation"], case["object"])
            hit = claim_map.get(key)
            resolution_type = classify_resolution_for_claim(
                claim_models,
                subject=case["subject"],
                relation=case["relation"],
                object_=case["object"],
            )

            if planned and runtime_store is not None:
                query_started = time.perf_counter()
                plan_started = time.perf_counter()
                plan = planner.plan_for_claim(case["subject"], case["relation"])
                planned_plan_time_ms += (time.perf_counter() - plan_started) * 1000

                rows_examined = 0
                touched_shards = 0
                fallback_used = True
                explicit_started = time.perf_counter()
                if plan is not None:
                    for shard_id in plan.required_shards:
                        rows, row_count = runtime_store.get_claim_with_metrics(
                            case["subject"],
                            case["relation"],
                            shard_id=shard_id,
                        )
                        rows_examined += row_count
                        touched_shards += 1
                        if rows:
                            fallback_used = False
                            break
                planned_explicit_lookup_ms += (time.perf_counter() - explicit_started) * 1000

                inference_started = time.perf_counter()
                if fallback_used and plan is not None:
                    lookup_key = (case["subject"].lower(), case["relation"].lower())
                    inferred_objects = inverse_map.get(lookup_key, set()) | transitive_map.get(lookup_key, set())
                    if case["object"].lower() in inferred_objects:
                        fallback_used = False
                planned_inference_lookup_ms += (time.perf_counter() - inference_started) * 1000

                fallback_started = time.perf_counter()
                if fallback_used:
                    planned_fallback_count += 1
                planned_fallback_ms += (time.perf_counter() - fallback_started) * 1000

                render_started = time.perf_counter()
                _ = (rows_examined, touched_shards)
                planned_render_ms += (time.perf_counter() - render_started) * 1000

                planned_rows_examined_total += rows_examined
                planned_shards_total += touched_shards
                planned_cases += 1
                planned_total_query_ms += (time.perf_counter() - query_started) * 1000

            if hit is None and resolution_type in {InferenceType.INVERSE, InferenceType.TRANSITIVE}:
                observed = "candidate"
                candidate += 1
            elif hit is None:
                observed = "unknown"
                unknown += 1
            elif str(hit.get("trust_tier", "")) == "T5_CERTIFIED":
                observed = "verified"
                verified += 1
            else:
                observed = "candidate"
                candidate += 1

            expected = case["expected"]
            ok = observed == expected
            if not ok:
                incorrect += 1
            if expected == "unknown" and observed in {"verified", "candidate"}:
                false_verified_count += 1

            if resolution_type == InferenceType.EXPLICIT:
                explicit_answer_count += 1
            elif resolution_type == InferenceType.INVERSE:
                inverse_inferred_count += 1
                tracker.record("|".join(key), InferenceType.INVERSE.value)
            elif resolution_type == InferenceType.TRANSITIVE:
                transitive_inferred_count += 1
                tracker.record("|".join(key), InferenceType.TRANSITIVE.value)
            elif resolution_type == InferenceType.UNSUPPORTED:
                unsupported_query_count += 1
            else:
                unknown_count += 1

            results.append(
                {
                    "id": case["id"],
                    "expected": expected,
                    "observed": observed,
                    "resolution_type": resolution_type.value,
                    "status": "PASS" if ok else "FAIL",
                }
            )
    finally:
        if runtime_store is not None:
            runtime_store.close()

    total = len(cases)
    answered = verified + candidate
    query_latency_ms = round((time.perf_counter() - query_started) * 1000, 3)
    compression_metrics = _compression_metrics(pack_path)
    stable_inferred_count = len(tracker.get_stable(stability_threshold_used))
    return {
        "status": "COVERAGE_COMPLETE" if incorrect == 0 else "COVERAGE_MISMATCH",
        "pack_path": str(pack_path),
        "benchmark_path": str(benchmark_path),
        "total": total,
        "answered": answered,
        "verified": verified,
        "candidate": candidate,
        "unknown": unknown,
        "incorrect": incorrect,
        "coverage_rate": _rate(answered, total),
        "verified_rate": _rate(verified, total),
        "candidate_rate": _rate(candidate, total),
        "unknown_rate": _rate(unknown, total),
        "total_queries": total,
        "explicit_answer_count": explicit_answer_count,
        "inverse_inferred_count": inverse_inferred_count,
        "transitive_inferred_count": transitive_inferred_count,
        "unknown_count": unknown_count,
        "unsupported_query_count": unsupported_query_count,
        "false_verified_count": false_verified_count,
        "stable_inferred_count": stable_inferred_count,
        "stability_threshold_used": stability_threshold_used,
        "compression_ratio": compression_metrics["compression_ratio"],
        "compressed_size": compression_metrics["compressed_size"],
        "uncompressed_size": compression_metrics["uncompressed_size"],
        "load_time_ms": load_time_ms,
        "query_latency_ms": query_latency_ms,
        "backend_used": backend_used,
        "avg_rows_examined": (planned_rows_examined_total / planned_cases) if planned_cases else 0.0,
        "avg_touched_shards": (planned_shards_total / planned_cases) if planned_cases else 0.0,
        "fallback_rate": (planned_fallback_count / planned_cases) if planned_cases else 0.0,
        "planned_timing_breakdown_ms": {
            "plan_time_ms": round(planned_plan_time_ms, 3),
            "explicit_lookup_ms": round(planned_explicit_lookup_ms, 3),
            "inference_lookup_ms": round(planned_inference_lookup_ms, 3),
            "fallback_ms": round(planned_fallback_ms, 3),
            "render_ms": round(planned_render_ms, 3),
            "total_query_ms": round(planned_total_query_ms, 3),
        },
        "results": results,
    }


def format_coverage_text(summary: dict[str, Any]) -> str:
    lines = [
        f"status: {summary['status']}",
        f"total: {summary['total']}",
        f"total_queries: {summary['total_queries']}",
        f"answered: {summary['answered']}",
        f"verified: {summary['verified']}",
        f"candidate: {summary['candidate']}",
        f"unknown: {summary['unknown']}",
        f"incorrect: {summary['incorrect']}",
        f"coverage_rate: {summary['coverage_rate']}",
        "inference_coverage:",
        f"  explicit_answer_count: {summary['explicit_answer_count']}",
        f"  inverse_inferred_count: {summary['inverse_inferred_count']}",
        f"  transitive_inferred_count: {summary['transitive_inferred_count']}",
        f"  unknown_count: {summary['unknown_count']}",
        f"  unsupported_query_count: {summary['unsupported_query_count']}",
        f"  false_verified_count: {summary['false_verified_count']}",
        f"  stable_inferred_count: {summary['stable_inferred_count']}",
        f"  stability_threshold_used: {summary['stability_threshold_used']}",
        f"verified_rate: {summary['verified_rate']}",
        f"candidate_rate: {summary['candidate_rate']}",
        f"unknown_rate: {summary['unknown_rate']}",
        f"compression_ratio: {summary['compression_ratio']}",
        f"compressed_size: {summary['compressed_size']}",
        f"uncompressed_size: {summary['uncompressed_size']}",
        f"load_time_ms: {summary['load_time_ms']}",
        f"query_latency_ms: {summary['query_latency_ms']}",
        f"backend_used: {summary.get('backend_used', 'jsonl')}",
        f"avg_rows_examined: {summary.get('avg_rows_examined', 0.0)}",
        f"avg_touched_shards: {summary.get('avg_touched_shards', 0.0)}",
        f"fallback_rate: {summary.get('fallback_rate', 0.0)}",
    ]
    return "\n".join(lines)


def _load_claims(pack_path: Path) -> list[dict[str, Any]]:
    claims_path = pack_path / "claims.jsonl"
    if not claims_path.exists():
        raise CoverageBenchmarkError("MISSING_CLAIMS", f"missing claims.jsonl in {pack_path}")
    claims: list[dict[str, Any]] = []
    for idx, line in enumerate(claims_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CoverageBenchmarkError("MALFORMED_CLAIMS", f"claims.jsonl line {idx}: {exc.msg}") from exc
        if not isinstance(row, dict):
            raise CoverageBenchmarkError("MALFORMED_CLAIMS", f"claims.jsonl line {idx} must be an object")
        claims.append(row)
    return claims


def _load_claim_models(claims: list[dict[str, Any]]) -> list[KnowledgeClaim]:
    return [KnowledgeClaim.from_dict(row) for row in claims]


def _load_cases(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise CoverageBenchmarkError("FILE_NOT_FOUND", f"benchmark file not found: {path}")
    cases: list[dict[str, str]] = []
    for idx, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CoverageBenchmarkError("MALFORMED_JSON", f"line {idx}: {exc.msg}") from exc
        if not isinstance(row, dict):
            raise CoverageBenchmarkError("INVALID_CASE", f"line {idx} root must be object")
        case = {
            "id": str(row.get("id", f"case_{idx}")),
            "subject": str(row.get("subject", "")).strip(),
            "relation": str(row.get("relation", "")).strip(),
            "object": str(row.get("object", "")).strip(),
            "expected": str(row.get("expected", "")).strip().lower(),
        }
        if not case["subject"] or not case["relation"] or not case["object"]:
            raise CoverageBenchmarkError("INVALID_CASE", f"line {idx} requires subject/relation/object")
        if case["expected"] not in {"verified", "candidate", "unknown"}:
            raise CoverageBenchmarkError("INVALID_EXPECTED", f"line {idx} expected must be verified/candidate/unknown")
        cases.append(case)
    return cases


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _build_inference_map(claims: list[KnowledgeClaim]) -> dict[tuple[str, str], set[str]]:
    out: dict[tuple[str, str], set[str]] = {}
    for claim in claims:
        key = (claim.subject.lower(), claim.relation.lower())
        out.setdefault(key, set()).add(claim.object.lower())
    return out


def _compression_metrics(pack_path: Path) -> dict[str, float | int]:
    metrics_path = pack_path / "metrics.json"
    if metrics_path.exists():
        try:
            payload = json.loads(metrics_path.read_text())
            if isinstance(payload, dict):
                uncompressed = int(payload.get("original_size_bytes", 0) or 0)
                compressed = int(payload.get("total_compressed_size_bytes", 0) or payload.get("compressed_size_bytes", 0) or 0)
                ratio = float(payload.get("compression_ratio", 0.0) or 0.0)
                return {
                    "compression_ratio": ratio,
                    "compressed_size": compressed,
                    "uncompressed_size": uncompressed,
                }
        except Exception:
            pass
    claims_path = pack_path / "claims.jsonl"
    uncompressed = claims_path.stat().st_size if claims_path.exists() else 0
    return {
        "compression_ratio": 1.0 if uncompressed > 0 else 0.0,
        "compressed_size": uncompressed,
        "uncompressed_size": uncompressed,
    }
