"""Retrieval pipeline over symbolic artifact index."""

from __future__ import annotations

from dataclasses import dataclass

from vcse.dsl.schema import CapabilityBundle
from vcse.index.bm25 import BM25Scorer
from vcse.index.features import extract_bundle_features
from vcse.index.index import CapabilityPackIndex, SymbolicIndex
from vcse.index.pack_selector import PackSelector
from vcse.index.scoring import score_artifact
from vcse.index.tokenizer import normalize_text, normalized_tokens


@dataclass(frozen=True)
class RetrievalCandidate:
    artifact_id: str
    score: float


@dataclass(frozen=True)
class RetrievalResult:
    selected_artifact_ids: list[str]
    selected_pack_ids: list[str]
    top_scores: list[tuple[str, float]]
    filtered_out_count: int
    candidate_count: int


@dataclass(frozen=True)
class RetrievalConfig:
    top_k_rules: int = 20
    top_k_packs: int = 5


class SymbolicRetriever:
    def __init__(self, index: SymbolicIndex) -> None:
        self.index = index
        self._bm25 = BM25Scorer(index)
        self._pack_selector = PackSelector()

    @staticmethod
    def from_bundles(bundles: list[CapabilityBundle]) -> "SymbolicRetriever":
        index = SymbolicIndex()
        features = []
        packs: list[CapabilityPackIndex] = []
        for bundle in bundles:
            bundle_features = extract_bundle_features(bundle)
            features.extend(bundle_features)

            token_set: set[str] = set()
            relation_set: set[str] = set()
            type_set: set[str] = set()
            min_priority = 100
            for feature in bundle_features:
                token_set.update(feature.token_freq.keys())
                relation_set.update(feature.relations)
                type_set.add(feature.artifact_type)
                min_priority = min(min_priority, feature.priority)
            packs.append(
                CapabilityPackIndex(
                    pack_id=bundle.name,
                    tokens=tuple(sorted(token_set)),
                    relations=tuple(sorted(relation_set)),
                    artifact_types=tuple(sorted(type_set)),
                    priority=min_priority,
                )
            )

        index.build(features)
        index.set_packs(packs)
        return SymbolicRetriever(index)

    def retrieve(
        self,
        query_text: str,
        relation_hints: set[str] | None = None,
        config: RetrievalConfig | None = None,
    ) -> RetrievalResult:
        if config is None:
            config = RetrievalConfig()
        relation_hints = relation_hints or set()

        normalized = normalize_text(query_text)
        qtokens = normalized_tokens(query_text)
        normalized_qtokens = normalized_tokens(normalized)

        candidate_ids = self._candidate_ids(qtokens)
        if not candidate_ids:
            return RetrievalResult(
                selected_artifact_ids=[],
                selected_pack_ids=[],
                top_scores=[],
                filtered_out_count=0,
                candidate_count=0,
            )

        scored: list[RetrievalCandidate] = []
        for artifact_id in sorted(candidate_ids):
            artifact = self.index.artifacts[artifact_id]
            score = score_artifact(
                artifact,
                qtokens,
                normalized_qtokens,
                relation_hints,
                bm25=self._bm25,
            )
            if score > 0:
                scored.append(RetrievalCandidate(artifact_id=artifact_id, score=score))

        scored.sort(key=lambda item: (-item.score, item.artifact_id))
        top = scored[: config.top_k_rules]
        selected_ids = [item.artifact_id for item in top]

        selected_packs = self._pack_selector.select(
            list(self.index.packs.values()),
            query_tokens=qtokens,
            relation_hints=relation_hints,
            top_k=config.top_k_packs,
        )

        return RetrievalResult(
            selected_artifact_ids=selected_ids,
            selected_pack_ids=[item.pack_id for item in selected_packs],
            top_scores=[(item.artifact_id, item.score) for item in top[:5]],
            filtered_out_count=max(0, self.index.artifact_count - len(selected_ids)),
            candidate_count=len(candidate_ids),
        )

    def _candidate_ids(self, query_tokens: list[str]) -> set[str]:
        candidate_ids: set[str] = set()
        for token in query_tokens:
            ids = self.index.inverted_index.get(token)
            if ids:
                candidate_ids.update(ids)
        return candidate_ids


def filter_bundle_by_artifact_ids(
    bundle: CapabilityBundle,
    selected_artifact_ids: set[str],
) -> CapabilityBundle:
    """Create filtered bundle view. Empty selection keeps original bundle for monotonicity."""
    if not selected_artifact_ids:
        return bundle

    relation_schemas = [
        item for item in bundle.relation_schemas
        if str(item.get("id", "")) in selected_artifact_ids
    ]

    return CapabilityBundle(
        name=bundle.name,
        version=bundle.version,
        synonyms=[item for item in bundle.synonyms if item.id in selected_artifact_ids],
        parser_patterns=[item for item in bundle.parser_patterns if item.id in selected_artifact_ids],
        relation_schemas=relation_schemas,
        ingestion_templates=[
            item for item in bundle.ingestion_templates if item.id in selected_artifact_ids
        ],
        proposer_rules=[item for item in bundle.proposer_rules if item.id in selected_artifact_ids],
        clarification_rules=[
            item for item in bundle.clarification_rules if item.id in selected_artifact_ids
        ],
        renderer_templates=[
            item for item in bundle.renderer_templates if item.id in selected_artifact_ids
        ],
        verifier_stubs=[item for item in bundle.verifier_stubs if item.id in selected_artifact_ids],
        warnings=list(bundle.warnings),
    )
