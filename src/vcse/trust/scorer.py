"""Source authority registry and scoring."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceAuthority:
    id: str
    name: str
    domain: str
    trust_score: float
    source_type: str
    requires_multi_source: bool = False
    requires_recency: bool = False
    freshness_days: int | None = None
    notes: str = ""


DEFAULT_AUTHORITIES: dict[str, SourceAuthority] = {
    "official_government": SourceAuthority(
        id="official_government",
        name="Official Government Source",
        domain="general",
        trust_score=0.95,
        source_type="api",
        requires_multi_source=False,
        requires_recency=True,
        freshness_days=30,
    ),
    "standards_body": SourceAuthority(
        id="standards_body",
        name="Standards Body",
        domain="general",
        trust_score=0.9,
        source_type="text",
    ),
    "academic_reference": SourceAuthority(
        id="academic_reference",
        name="Academic Reference",
        domain="general",
        trust_score=0.85,
        source_type="text",
    ),
    "wikidata": SourceAuthority(
        id="wikidata",
        name="Wikidata",
        domain="general",
        trust_score=0.8,
        source_type="api",
        requires_multi_source=True,
    ),
    "wikipedia": SourceAuthority(
        id="wikipedia",
        name="Wikipedia",
        domain="general",
        trust_score=0.7,
        source_type="text",
        requires_multi_source=True,
    ),
    "local_file": SourceAuthority(
        id="local_file",
        name="Local File",
        domain="general",
        trust_score=0.5,
        source_type="file",
        requires_multi_source=True,
    ),
    "unknown": SourceAuthority(
        id="unknown",
        name="Unknown",
        domain="general",
        trust_score=0.2,
        source_type="unknown",
        requires_multi_source=True,
    ),
}


class SourceAuthorityRegistry:
    def __init__(self, authorities: dict[str, SourceAuthority] | None = None) -> None:
        self._authorities = dict(DEFAULT_AUTHORITIES)
        if authorities:
            self._authorities.update(authorities)

    def get(self, source_id: str) -> SourceAuthority:
        return self._authorities.get(source_id, self._authorities["unknown"])

    def score(self, source_id: str) -> float:
        return self.get(source_id).trust_score

    def all(self) -> list[SourceAuthority]:
        return sorted(self._authorities.values(), key=lambda item: item.id)
