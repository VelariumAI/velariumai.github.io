"""CAKE pipeline orchestrator."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vcse.cake.errors import CakePipelineError, CakeTransportError, CakeExtractionError
from vcse.cake.extractor_dbpedia import DBpediaExtractor
from vcse.cake.extractor_wikidata import WikidataExtractor
from vcse.cake.fetcher import FileTransport, HttpStaticTransport, fetch_source
from vcse.cake.normalizer_adapter import CakeNormalizerAdapter
from vcse.cake.pack_updater import CakePackUpdater
from vcse.cake.snapshot import CakeSnapshotStore
from vcse.cake.sources import CakeSource, load_source_config
from vcse.cake.trust_runner import CakeTrustRunner
from vcse.knowledge.pack_model import KnowledgeClaim
from vcse.knowledge.validator import KnowledgeValidator, KNOWN_RELATIONS

CAKE_COMPLETE = "CAKE_COMPLETE"
CAKE_PARTIAL = "CAKE_PARTIAL"
CAKE_DRY_RUN = "CAKE_DRY_RUN"
CAKE_FAILED = "CAKE_FAILED"

_CAKE_RELATIONS: frozenset[str] = frozenset(
    KNOWN_RELATIONS | {"capital_of", "located_in_country", "instance_of", "country"}
)

_EXTRACTORS = {
    "wikidata_json": WikidataExtractor(),
    "dbpedia_ttl": DBpediaExtractor(),
}


@dataclass
class CakeRunReport:
    run_id: str
    source_ids: list[str]
    snapshot_ids: list[str]
    source_reports: list[dict[str, Any]]
    status: str
    claims_extracted: int
    claims_normalized: int
    claims_ingested: int
    trust_decisions: int
    errors: list[str]
    warnings: list[str]
    dry_run: bool
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source_ids": self.source_ids,
            "snapshot_ids": self.snapshot_ids,
            "source_reports": self.source_reports,
            "status": self.status,
            "claims_extracted": self.claims_extracted,
            "claims_normalized": self.claims_normalized,
            "claims_ingested": self.claims_ingested,
            "trust_decisions": self.trust_decisions,
            "errors": self.errors,
            "warnings": self.warnings,
            "dry_run": self.dry_run,
            "timestamp": self.timestamp,
        }


def run_cake_pipeline(
    source_config_path: str | Path,
    *,
    limit: int | None = None,
    dry_run: bool = False,
    allow_http: bool = False,
    transport_type: str = "file",
    allow_partial: bool = False,
    pack_output_dir: str | Path | None = None,
    snapshot_root: Path | None = None,
) -> CakeRunReport:
    """Run the full CAKE acquisition pipeline. Returns a CakeRunReport."""
    run_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    output_dir = Path(pack_output_dir) if pack_output_dir else Path.home() / ".vcse" / "cake" / "packs"

    config = load_source_config(source_config_path)
    snapshot_store = CakeSnapshotStore(root=snapshot_root)
    normalizer = CakeNormalizerAdapter()
    trust_runner = CakeTrustRunner()
    pack_updater = CakePackUpdater()

    source_ids: list[str] = []
    snapshot_ids: list[str] = []
    source_reports: list[dict] = []
    all_errors: list[str] = []
    all_warnings: list[str] = []
    total_extracted = 0
    total_normalized = 0
    total_ingested = 0
    total_trust = 0
    any_success = False
    any_failure = False

    for source in config.sources:
        if not source.enabled:
            continue

        src_report: dict[str, Any] = {
            "source_id": source.id,
            "status": "PENDING",
            "claims_extracted": 0,
            "claims_normalized": 0,
            "snapshot_id": None,
            "errors": [],
            "warnings": [],
        }

        try:
            transport = _make_transport(source, transport_type, allow_http)
            fetched = fetch_source(source, transport, limit=limit)
            snap = snapshot_store.save(fetched)

            src_report["snapshot_id"] = snap.snapshot_id
            source_ids.append(source.id)
            snapshot_ids.append(snap.snapshot_id)

            extractor = _get_extractor(source.format)
            claims = extractor.extract(fetched, snap.snapshot_id, limit=limit)
            src_report["claims_extracted"] = len(claims)
            total_extracted += len(claims)

            normalized = normalizer.normalize(claims)
            src_report["claims_normalized"] = len(normalized)
            total_normalized += len(normalized)

            if dry_run:
                src_report["status"] = "DRY_RUN"
                any_success = True
                continue

            pack_path = output_dir / source.id
            ingested = pack_updater.update(pack_path, normalized)
            total_ingested += ingested
            src_report["claims_ingested"] = ingested

            trust_report = trust_runner.evaluate(normalized)
            total_trust += len(trust_report.decisions)

            src_report["status"] = "COMPLETE"
            any_success = True

        except (CakeTransportError, CakeExtractionError, CakePipelineError) as exc:
            msg = f"{source.id}: {exc.error_type}: {exc.reason}"
            src_report["status"] = "FAILED"
            src_report["errors"].append(msg)
            all_errors.append(msg)
            any_failure = True
            if not allow_partial:
                source_reports.append(src_report)
                status = CAKE_FAILED
                break
        except Exception as exc:
            msg = f"{source.id}: UNEXPECTED_ERROR: {exc}"
            src_report["status"] = "FAILED"
            src_report["errors"].append(msg)
            all_errors.append(msg)
            any_failure = True
            if not allow_partial:
                source_reports.append(src_report)
                status = CAKE_FAILED
                break

        source_reports.append(src_report)

    if dry_run:
        status = CAKE_DRY_RUN
    elif any_failure and not any_success:
        status = CAKE_FAILED
    elif any_failure and any_success:
        status = CAKE_PARTIAL
    else:
        status = CAKE_COMPLETE

    return CakeRunReport(
        run_id=run_id,
        source_ids=source_ids,
        snapshot_ids=snapshot_ids,
        source_reports=source_reports,
        status=status,
        claims_extracted=total_extracted,
        claims_normalized=total_normalized,
        claims_ingested=total_ingested,
        trust_decisions=total_trust,
        errors=all_errors,
        warnings=all_warnings,
        dry_run=dry_run,
        timestamp=timestamp,
    )


def _make_transport(source: CakeSource, transport_type: str, allow_http: bool):
    if source.source_type == "local_file" or transport_type == "file":
        return FileTransport()
    return HttpStaticTransport(allow_http=allow_http)


def _get_extractor(fmt: str):
    if fmt not in _EXTRACTORS:
        # json/jsonl not yet supported by specialized extractors; treat as empty
        class _NoOpExtractor:
            def extract(self, fetched, snapshot_id, *, limit=None):
                return []
        return _NoOpExtractor()
    return _EXTRACTORS[fmt]