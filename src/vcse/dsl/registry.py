"""In-memory capability registry."""

from __future__ import annotations

from dataclasses import dataclass, field

from vcse.dsl.schema import CapabilityBundle


@dataclass
class CapabilityRegistry:
    bundles: dict[str, CapabilityBundle] = field(default_factory=dict)

    def register_bundle(self, bundle: CapabilityBundle) -> None:
        self.bundles[bundle.name] = bundle

    def unregister_bundle(self, name: str) -> None:
        self.bundles.pop(name, None)

    def list_bundles(self) -> list[str]:
        return sorted(self.bundles.keys())

    def _ordered(self) -> list[CapabilityBundle]:
        return [self.bundles[name] for name in sorted(self.bundles.keys())]

    def get_synonyms(self):
        return [item for bundle in self._ordered() for item in bundle.synonyms]

    def get_parser_patterns(self):
        return [item for bundle in self._ordered() for item in bundle.parser_patterns]

    def get_relation_schemas(self):
        return [item for bundle in self._ordered() for item in bundle.relation_schemas]

    def get_ingestion_templates(self):
        return [item for bundle in self._ordered() for item in bundle.ingestion_templates]

    def get_proposer_rules(self):
        return [item for bundle in self._ordered() for item in bundle.proposer_rules]

    def get_renderer_templates(self):
        return [item for bundle in self._ordered() for item in bundle.renderer_templates]

    def get_clarification_rules(self):
        return [item for bundle in self._ordered() for item in bundle.clarification_rules]


GLOBAL_REGISTRY = CapabilityRegistry()
