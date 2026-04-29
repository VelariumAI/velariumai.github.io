"""SQLite runtime store compiler and reader for pack claims/provenance."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vcse.packs.integrity import compute_pack_hash

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RuntimeStoreReport:
    pack_id: str
    pack_path: str
    output_path: str
    claim_count: int
    provenance_count: int
    store_size_bytes: int
    compile_time_ms: float
    load_time_ms: float
    avg_query_latency_ms: float
    backend: str
    status: str
    reasons: list[str]


def runtime_store_dir() -> Path:
    return Path(".vcse") / "runtime_stores"


def runtime_store_path_for_pack(pack_id: str) -> Path:
    return runtime_store_dir() / f"{pack_id}.sqlite"


class RuntimeStoreCompiler:
    def compile_pack(self, pack_path: Path, output_path: Path) -> RuntimeStoreReport:
        return self._compile_full(pack_path=pack_path, output_path=output_path, status_on_success="REBUILT")

    def compile_incremental(self, pack_path: Path, output_path: Path) -> RuntimeStoreReport:
        pack_root = Path(pack_path)
        output = Path(output_path)
        claims_path = pack_root / "claims.jsonl"
        provenance_path = pack_root / "provenance.jsonl"
        if not claims_path.exists() or not provenance_path.exists():
            return self._compile_full(pack_path=pack_root, output_path=output, status_on_success="REBUILT")

        current_claims_hash = _content_hash(claims_path)
        current_provenance_hash = _content_hash(provenance_path)
        if output.exists():
            try:
                store = RuntimeStore(output)
                meta = store.metadata()
                store.close()
                if (
                    meta.get("claims_hash", "") == current_claims_hash
                    and meta.get("provenance_hash", "") == current_provenance_hash
                ):
                    info_store = RuntimeStore(output)
                    try:
                        stats = info_store.stats()
                    finally:
                        info_store.close()
                    return RuntimeStoreReport(
                        pack_id=str(stats.get("pack_id", pack_root.name)),
                        pack_path=str(pack_root),
                        output_path=str(output),
                        claim_count=int(stats.get("claim_count", 0)),
                        provenance_count=int(stats.get("provenance_count", 0)),
                        store_size_bytes=int(stats.get("store_size_bytes", 0)),
                        compile_time_ms=0.0,
                        load_time_ms=float(stats.get("load_time_ms", 0.0)),
                        avg_query_latency_ms=float(stats.get("avg_query_latency_ms", 0.0)),
                        backend="sqlite",
                        status="NO_CHANGES",
                        reasons=[],
                    )
            except Exception:
                pass

        return self._compile_full(pack_path=pack_root, output_path=output, status_on_success="REBUILT")

    def _compile_full(self, pack_path: Path, output_path: Path, status_on_success: str) -> RuntimeStoreReport:
        started = time.perf_counter()
        reasons: list[str] = []
        pack_root = Path(pack_path)
        output = Path(output_path)
        pack_json = pack_root / "pack.json"
        claims_path = pack_root / "claims.jsonl"
        provenance_path = pack_root / "provenance.jsonl"

        if not pack_json.exists():
            reasons.append("missing pack.json")
        if not claims_path.exists():
            reasons.append("missing claims.jsonl")
        if not provenance_path.exists():
            reasons.append("missing provenance.jsonl")
        if reasons:
            return RuntimeStoreReport(
                pack_id=str(pack_root.name),
                pack_path=str(pack_root),
                output_path=str(output),
                claim_count=0,
                provenance_count=0,
                store_size_bytes=0,
                compile_time_ms=0.0,
                load_time_ms=0.0,
                avg_query_latency_ms=0.0,
                backend="sqlite",
                status="STORE_COMPILE_FAILED",
                reasons=sorted(reasons),
            )

        try:
            pack_meta = json.loads(pack_json.read_text())
        except json.JSONDecodeError as exc:
            return RuntimeStoreReport(
                pack_id=str(pack_root.name),
                pack_path=str(pack_root),
                output_path=str(output),
                claim_count=0,
                provenance_count=0,
                store_size_bytes=0,
                compile_time_ms=0.0,
                load_time_ms=0.0,
                avg_query_latency_ms=0.0,
                backend="sqlite",
                status="STORE_COMPILE_FAILED",
                reasons=[f"invalid pack.json: {exc.msg}"],
            )

        pack_id = str(pack_meta.get("id") or pack_meta.get("pack_id") or pack_root.name)
        pack_version = str(pack_meta.get("version", ""))
        pack_hash = compute_pack_hash(pack_root).pack_hash
        compiled_at = datetime.now(UTC).isoformat()
        claims_hash = _content_hash(claims_path)
        provenance_hash = _content_hash(provenance_path)

        claim_rows: list[dict[str, Any]] = []
        for idx, line in enumerate(claims_path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                return RuntimeStoreReport(
                    pack_id=pack_id,
                    pack_path=str(pack_root),
                    output_path=str(output),
                    claim_count=0,
                    provenance_count=0,
                    store_size_bytes=0,
                    compile_time_ms=0.0,
                    load_time_ms=0.0,
                    avg_query_latency_ms=0.0,
                    backend="sqlite",
                    status="STORE_COMPILE_FAILED",
                    reasons=[f"invalid claims.jsonl line {idx}: {exc.msg}"],
                )
            if not isinstance(item, dict):
                return RuntimeStoreReport(
                    pack_id=pack_id,
                    pack_path=str(pack_root),
                    output_path=str(output),
                    claim_count=0,
                    provenance_count=0,
                    store_size_bytes=0,
                    compile_time_ms=0.0,
                    load_time_ms=0.0,
                    avg_query_latency_ms=0.0,
                    backend="sqlite",
                    status="STORE_COMPILE_FAILED",
                    reasons=[f"invalid claims.jsonl line {idx}: expected object"],
                )
            claim_rows.append(item)

        prov_rows: list[dict[str, Any]] = []
        for idx, line in enumerate(provenance_path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                return RuntimeStoreReport(
                    pack_id=pack_id,
                    pack_path=str(pack_root),
                    output_path=str(output),
                    claim_count=0,
                    provenance_count=0,
                    store_size_bytes=0,
                    compile_time_ms=0.0,
                    load_time_ms=0.0,
                    avg_query_latency_ms=0.0,
                    backend="sqlite",
                    status="STORE_COMPILE_FAILED",
                    reasons=[f"invalid provenance.jsonl line {idx}: {exc.msg}"],
                )
            if not isinstance(item, dict):
                return RuntimeStoreReport(
                    pack_id=pack_id,
                    pack_path=str(pack_root),
                    output_path=str(output),
                    claim_count=0,
                    provenance_count=0,
                    store_size_bytes=0,
                    compile_time_ms=0.0,
                    load_time_ms=0.0,
                    avg_query_latency_ms=0.0,
                    backend="sqlite",
                    status="STORE_COMPILE_FAILED",
                    reasons=[f"invalid provenance.jsonl line {idx}: expected object"],
                )
            prov_rows.append(item)

        output.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(output))
        try:
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("BEGIN")
            self._create_schema(conn)
            claim_records = sorted(
                [
                    (
                        _claim_key(row),
                        str(row.get("subject", "")),
                        str(row.get("relation", "")),
                        str(row.get("object", "")),
                        str(row.get("trust_tier", "")),
                        json.dumps(row, sort_keys=True),
                    )
                    for row in claim_rows
                ],
                key=lambda item: item[0],
            )
            conn.executemany(
                (
                    "INSERT INTO claims (claim_key, subject, relation, object, trust_tier, raw_json) "
                    "VALUES (?, ?, ?, ?, ?, ?)"
                ),
                claim_records,
            )

            claim_keys_by_index = [_claim_key(row) for row in claim_rows]
            prov_records = sorted(
                [
                    (
                        _claim_key_from_provenance(row, idx=idx, claim_keys_by_index=claim_keys_by_index),
                        str(row.get("source_id", "")),
                        str(row.get("inference_type", "")),
                        _encode_source_claims(row.get("derived_from", row.get("source_claims"))),
                        json.dumps(row, sort_keys=True),
                    )
                    for idx, row in enumerate(prov_rows)
                ],
                key=lambda item: (item[0], item[1]),
            )
            conn.executemany(
                (
                    "INSERT INTO provenance (claim_key, source_id, inference_type, source_claims, raw_json) "
                    "VALUES (?, ?, ?, ?, ?)"
                ),
                prov_records,
            )
            metadata_rows = sorted(
                [
                    ("pack_id", pack_id),
                    ("pack_version", pack_version),
                    ("pack_hash", pack_hash),
                    ("claims_hash", claims_hash),
                    ("provenance_hash", provenance_hash),
                    ("compiled_at", compiled_at),
                    ("last_compiled_at", compiled_at),
                    ("claim_count", str(len(claim_records))),
                    ("provenance_count", str(len(prov_records))),
                    ("schema_version", str(SCHEMA_VERSION)),
                ],
                key=lambda item: item[0],
            )
            conn.executemany("INSERT INTO metadata (key, value) VALUES (?, ?)", metadata_rows)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        load_time_ms, avg_query_latency_ms = _measure_store_performance(output)
        compile_time_ms = round((time.perf_counter() - started) * 1000, 3)
        _update_runtime_metrics_metadata(
            output,
            compile_time_ms=compile_time_ms,
            load_time_ms=load_time_ms,
            avg_query_latency_ms=avg_query_latency_ms,
        )

        return RuntimeStoreReport(
            pack_id=pack_id,
            pack_path=str(pack_root),
            output_path=str(output),
            claim_count=len(claim_rows),
            provenance_count=len(prov_rows),
            store_size_bytes=output.stat().st_size if output.exists() else 0,
            compile_time_ms=compile_time_ms,
            load_time_ms=load_time_ms,
            avg_query_latency_ms=avg_query_latency_ms,
            backend="sqlite",
            status=status_on_success,
            reasons=[],
        )

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            DROP TABLE IF EXISTS metadata;
            DROP TABLE IF EXISTS claims;
            DROP TABLE IF EXISTS provenance;

            CREATE TABLE metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE claims (
                claim_key TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                relation TEXT NOT NULL,
                object TEXT NOT NULL,
                trust_tier TEXT,
                raw_json TEXT NOT NULL
            );
            CREATE INDEX idx_claim_subject_relation ON claims(subject, relation);
            CREATE INDEX idx_claim_relation ON claims(relation);
            CREATE INDEX idx_claim_object ON claims(object);

            CREATE TABLE provenance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_key TEXT NOT NULL,
                source_id TEXT,
                inference_type TEXT,
                source_claims TEXT,
                raw_json TEXT NOT NULL
            );
            CREATE INDEX idx_provenance_claim_key ON provenance(claim_key);
            CREATE INDEX idx_provenance_source_id ON provenance(source_id);
            """
        )


class RuntimeStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self._conn.close()

    def get_claim(self, subject: str, relation: str, object: str | None = None) -> list[dict[str, Any]]:
        if object is None:
            cur = self._conn.execute(
                "SELECT raw_json FROM claims WHERE subject = ? AND relation = ? ORDER BY claim_key",
                (subject, relation),
            )
        else:
            cur = self._conn.execute(
                "SELECT raw_json FROM claims WHERE subject = ? AND relation = ? AND object = ? ORDER BY claim_key",
                (subject, relation, object),
            )
        return [json.loads(row["raw_json"]) for row in cur.fetchall()]

    def get_claim_by_key(self, claim_key: str) -> dict[str, Any] | None:
        cur = self._conn.execute("SELECT raw_json FROM claims WHERE claim_key = ?", (claim_key,))
        row = cur.fetchone()
        if row is None:
            return None
        return json.loads(row["raw_json"])

    def get_claims_for_subject_relation(self, subject: str, relation: str) -> list[dict[str, Any]]:
        return self.get_claim(subject, relation)

    def get_provenance(self, claim_key: str) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT raw_json FROM provenance WHERE claim_key = ? ORDER BY source_id, id",
            (claim_key,),
        )
        return [json.loads(row["raw_json"]) for row in cur.fetchall()]

    def iter_claim_rows(self) -> list[dict[str, str]]:
        cur = self._conn.execute("SELECT subject, relation, object FROM claims ORDER BY claim_key")
        return [
            {
                "subject": str(row["subject"]),
                "relation": str(row["relation"]),
                "object": str(row["object"]),
            }
            for row in cur.fetchall()
        ]

    def iter_claim_objects(self) -> list[dict[str, Any]]:
        cur = self._conn.execute("SELECT raw_json FROM claims ORDER BY claim_key")
        return [json.loads(row["raw_json"]) for row in cur.fetchall()]

    def metadata(self) -> dict[str, str]:
        cur = self._conn.execute("SELECT key, value FROM metadata ORDER BY key")
        return {str(row["key"]): str(row["value"]) for row in cur.fetchall()}

    def stats(self) -> dict[str, Any]:
        meta = self.metadata()
        claim_count = int(meta.get("claim_count", "0"))
        provenance_count = int(meta.get("provenance_count", "0"))
        return {
            "schema_version": int(meta.get("schema_version", "0")),
            "pack_id": meta.get("pack_id", ""),
            "pack_version": meta.get("pack_version", ""),
            "pack_hash": meta.get("pack_hash", ""),
            "claims_hash": meta.get("claims_hash", ""),
            "provenance_hash": meta.get("provenance_hash", ""),
            "compiled_at": meta.get("compiled_at", ""),
            "last_compiled_at": meta.get("last_compiled_at", ""),
            "claim_count": claim_count,
            "provenance_count": provenance_count,
            "compile_time_ms": float(meta.get("compile_time_ms", "0") or 0),
            "load_time_ms": float(meta.get("load_time_ms", "0") or 0),
            "avg_query_latency_ms": float(meta.get("avg_query_latency_ms", "0") or 0),
            "backend": meta.get("backend", "sqlite") or "sqlite",
            "store_size_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
        }


def resolve_runtime_store_for_pack(pack_root: Path, pack_id: str) -> Path:
    return runtime_store_path_for_pack(pack_id)


def load_runtime_claims_if_valid(pack_root: Path, pack_id: str) -> list[dict[str, str]] | None:
    if os.getenv("VCSE_DISABLE_RUNTIME_STORE", "").strip() == "1":
        return None
    db_path = resolve_runtime_store_for_pack(pack_root, pack_id)
    if not db_path.exists():
        return None
    current_hash = compute_pack_hash(pack_root).pack_hash
    current_claims_hash = _content_hash(pack_root / "claims.jsonl")
    current_provenance_hash = _content_hash(pack_root / "provenance.jsonl")
    store = RuntimeStore(db_path)
    try:
        meta = store.metadata()
        if meta.get("pack_hash", "") != current_hash:
            return None
        if meta.get("claims_hash", "") != current_claims_hash:
            return None
        if meta.get("provenance_hash", "") != current_provenance_hash:
            return None
        return store.iter_claim_rows()
    finally:
        store.close()


def load_runtime_claim_objects_if_valid(pack_root: Path, pack_id: str) -> list[dict[str, Any]] | None:
    if os.getenv("VCSE_DISABLE_RUNTIME_STORE", "").strip() == "1":
        return None
    db_path = resolve_runtime_store_for_pack(pack_root, pack_id)
    if not db_path.exists():
        return None
    current_hash = compute_pack_hash(pack_root).pack_hash
    current_claims_hash = _content_hash(pack_root / "claims.jsonl")
    current_provenance_hash = _content_hash(pack_root / "provenance.jsonl")
    store = RuntimeStore(db_path)
    try:
        meta = store.metadata()
        if meta.get("pack_hash", "") != current_hash:
            return None
        if meta.get("claims_hash", "") != current_claims_hash:
            return None
        if meta.get("provenance_hash", "") != current_provenance_hash:
            return None
        return store.iter_claim_objects()
    finally:
        store.close()


def _claim_key(row: dict[str, Any]) -> str:
    return "|".join([str(row.get("subject", "")), str(row.get("relation", "")), str(row.get("object", ""))])


def _claim_key_from_provenance(row: dict[str, Any], *, idx: int, claim_keys_by_index: list[str]) -> str:
    direct = str(row.get("claim_key", "")).strip()
    if direct:
        return direct
    if idx < len(claim_keys_by_index):
        return claim_keys_by_index[idx]
    evidence = str(row.get("evidence_text", "")).strip()
    if "|" in evidence:
        parts = [item.strip() for item in evidence.split("|")]
        if len(parts) >= 3:
            return "|".join(parts[:3])
    return ""


def _encode_source_claims(value: Any) -> str:
    if isinstance(value, list):
        return json.dumps(value, sort_keys=True)
    if isinstance(value, tuple):
        return json.dumps(list(value), sort_keys=True)
    if value is None:
        return ""
    return str(value)


def _content_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _measure_store_performance(db_path: Path) -> tuple[float, float]:
    load_started = time.perf_counter()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("SELECT 1").fetchone()
    load_time_ms = round((time.perf_counter() - load_started) * 1000, 3)
    latency_started = time.perf_counter()
    for _ in range(10):
        conn.execute("SELECT claim_key FROM claims ORDER BY claim_key LIMIT 1").fetchone()
    total_ms = (time.perf_counter() - latency_started) * 1000
    conn.close()
    avg_query_latency_ms = round(total_ms / 10.0, 3)
    return load_time_ms, avg_query_latency_ms


def _update_runtime_metrics_metadata(
    db_path: Path,
    *,
    compile_time_ms: float,
    load_time_ms: float,
    avg_query_latency_ms: float,
) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("compile_time_ms", str(compile_time_ms)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("load_time_ms", str(load_time_ms)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("avg_query_latency_ms", str(avg_query_latency_ms)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("backend", "sqlite"),
        )
        conn.commit()
    finally:
        conn.close()
