"""Compression metrics and statistics."""

from __future__ import annotations

from typing import Any


def compute_metrics(pack_dir: str | Path) -> dict[str, Any]:
    """Compute compression statistics for a pack directory."""
    import json
    from pathlib import Path

    root = Path(pack_dir)
    metrics: dict[str, Any] = {}

    metrics_path = root / "metrics.json"
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text())
    else:
        original = root / "original_claims.jsonl"
        encoded = root / "encoded_claims.jsonl"
        intern = root / "intern_table.json"

        if original.exists() and encoded.exists():
            orig_lines = [l for l in original.read_text().splitlines() if l.strip()]
            enc_lines = [l for l in encoded.read_text().splitlines() if l.strip()]
            orig_size = sum(len(json.dumps(json.loads(l))) for l in orig_lines)
            enc_size = sum(len(l) for l in enc_lines)
            metrics["original_claims"] = len(orig_lines)
            metrics["compressed_claims"] = len(enc_lines)
            metrics["original_size_bytes"] = orig_size
            metrics["compressed_size_bytes"] = enc_size
            if intern.exists():
                metrics["intern_table_size_bytes"] = len(intern.read_text())
            if orig_size > 0:
                metrics["compression_ratio"] = round(enc_size / orig_size, 4)

    return metrics


def format_metrics(metrics: dict[str, Any]) -> str:
    """Format metrics as a human-readable string."""
    lines = [
        f"  Original claims:   {metrics.get('original_claims', '?')}",
        f"  Compressed claims: {metrics.get('compressed_claims', '?')}",
        f"  Unique strings:    {metrics.get('unique_strings', '?')}",
        f"  Original size:     {metrics.get('original_size_bytes', '?')} bytes",
        f"  Compressed size:   {metrics.get('compressed_size_bytes', '?')} bytes",
        f"  Intern table:      {metrics.get('intern_table_size_bytes', '?')} bytes",
        f"  Total compressed:  {metrics.get('total_compressed_size_bytes', '?')} bytes",
        f"  Compression ratio: {metrics.get('compression_ratio', '?')}",
        f"  Provenance dedup:  {metrics.get('provenance_unique', '?')} / {metrics.get('provenance_total', '?')}",
        f"  Graph nodes:       {metrics.get('graph_nodes', '?')}",
        f"  Graph edges:       {metrics.get('graph_edges', '?')}",
    ]
    return "\n".join(lines)