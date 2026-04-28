"""Deterministic DBpedia N-Triples extractor for CAKE."""

from __future__ import annotations

import re
import warnings
from datetime import datetime, timezone

from vcse.cake.errors import CakeExtractionError
from vcse.cake.snapshot import FetchedSource
from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgeProvenance

# Matches: <uri> <uri> <uri_or_literal> .
_TRIPLE_RE = re.compile(
    r'^<([^>]+)>\s+<([^>]+)>\s+(?:<([^>]+)>|"([^"]*)"(?:\^\^<[^>]+>)?)\s*\.\s*$'
)


def _last_segment(uri: str) -> str:
    """Extract last path segment from a URI, underscored."""
    segment = uri.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    return segment


class DBpediaExtractor:
    """Extract KnowledgeClaims from DBpedia N-Triples / simple TTL."""

    def extract(
        self,
        fetched: FetchedSource,
        snapshot_id: str,
        *,
        limit: int | None = None,
    ) -> list[KnowledgeClaim]:
        try:
            text = fetched.raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CakeExtractionError("ENCODING_ERROR", f"UTF-8 decode failed: {exc}") from exc

        claims: list[KnowledgeClaim] = []
        now = datetime.now(timezone.utc).isoformat()

        for line in text.splitlines():
            if limit is not None and len(claims) >= limit:
                break
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _TRIPLE_RE.match(line)
            if not m:
                warnings.warn(f"CAKE DBpedia: skipping malformed line: {line[:80]!r}", stacklevel=2)
                continue
            subj_uri, pred_uri, obj_uri, obj_literal = m.groups()
            subject = _last_segment(subj_uri)
            relation = _last_segment(pred_uri)
            obj = _last_segment(obj_uri) if obj_uri else (obj_literal or "")
            if not subject or not relation or not obj:
                continue
            prov = KnowledgeProvenance(
                source_id=fetched.source_id,
                source_type="dbpedia_ttl",
                location=snapshot_id,
                evidence_text=f"{subject} {relation} {obj}",
                trust_level="unrated",
                confidence=0.85,
            )
            claim = KnowledgeClaim(
                subject=subject,
                relation=relation,
                object=obj,
                provenance=prov,
                qualifiers={"snapshot_id": snapshot_id},
                confidence=0.85,
            )
            claims.append(claim)

        return claims