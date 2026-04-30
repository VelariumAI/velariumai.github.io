"""In-memory source and pack registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vcse.knowledge.errors import KnowledgeError
from vcse.knowledge.sources import Source


@dataclass
class SourceRegistry:
    sources: dict[str, Source] = field(default_factory=dict)

    def register(self, source: Source) -> None:
        if source.id in self.sources:
            raise KnowledgeError("DUPLICATE_SOURCE", f"source already registered: {source.id}")
        self.sources[source.id] = source

    def get(self, source_id: str) -> Source:
        try:
            return self.sources[source_id]
        except KeyError as exc:
            raise KnowledgeError("UNKNOWN_SOURCE", f"unknown source: {source_id}") from exc

    def list_sources(self) -> list[str]:
        return sorted(self.sources)


def installed_pack_root(base: str | Path | None = None) -> Path:
    root = Path(base) if base is not None else Path(".vcse") / "packs"
    return root
