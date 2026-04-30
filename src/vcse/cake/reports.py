"""CAKE report rendering."""

from __future__ import annotations

import json

from vcse.cake.pipeline import CakeRunReport


def render_report(report: CakeRunReport) -> str:
    """Render report as JSON string."""
    return json.dumps(report.to_dict(), indent=2, sort_keys=True)


def render_report_summary(report: CakeRunReport) -> str:
    """Render a short human-readable summary."""
    lines = [
        f"status: {report.status}",
        f"run_id: {report.run_id}",
        f"timestamp: {report.timestamp}",
        f"sources_processed: {len(report.source_ids)}",
        f"claims_extracted: {report.claims_extracted}",
        f"claims_normalized: {report.claims_normalized}",
        f"claims_ingested: {report.claims_ingested}",
        f"trust_decisions: {report.trust_decisions}",
        f"dry_run: {report.dry_run}",
    ]
    if report.errors:
        lines.append("errors:")
        for e in report.errors:
            lines.append(f"  - {e}")
    if report.warnings:
        lines.append("warnings:")
        for w in report.warnings:
            lines.append(f"  - {w}")
    return "\n".join(lines)