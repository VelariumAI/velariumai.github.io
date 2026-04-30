"""Planned query executor with shard/index locality metrics and safe fallback."""

from __future__ import annotations

from dataclasses import dataclass

from vcse.inference.transitive import infer_transitive_claims
from vcse.knowledge.pack_model import KnowledgeClaim
from vcse.packs.runtime_store import RuntimeStore
from vcse.query.planner import QueryPlan


@dataclass(frozen=True)
class QueryResult:
    answer_claim: dict[str, str] | None
    touched_shards: tuple[str, ...]
    touched_indexes: tuple[str, ...]
    rows_examined: int
    fallback_used: bool


class QueryExecutor:
    def execute(self, plan: QueryPlan | None, store: RuntimeStore) -> QueryResult:
        if plan is None:
            return QueryResult(None, tuple(), tuple(), 0, True)

        touched_shards: list[str] = []
        rows_examined = 0

        for shard_id in plan.required_shards:
            rows, row_count = store.get_claim_with_metrics(plan.subject, plan.target_relation, shard_id=shard_id)
            touched_shards.append(shard_id)
            rows_examined += row_count
            if rows:
                best = sorted(rows, key=lambda row: str(row.get("object", "")))[0]
                return QueryResult(
                    answer_claim={
                        "subject": str(best.get("subject", "")),
                        "relation": str(best.get("relation", "")),
                        "object": str(best.get("object", "")),
                    },
                    touched_shards=tuple(sorted(set(touched_shards))),
                    touched_indexes=plan.required_indexes,
                    rows_examined=rows_examined,
                    fallback_used=False,
                )

        if "transitive" in plan.inference_rules and plan.max_hops > 0:
            seed_rows, seed_count = store.get_claim_with_metrics(plan.subject, "located_in_country", shard_id="geography.location")
            rows_examined += seed_count
            if seed_rows:
                all_claims = [KnowledgeClaim.from_dict(item) for item in store.iter_claim_objects()]
                inferred = [
                    claim
                    for claim in infer_transitive_claims(all_claims)
                    if claim.subject.lower() == plan.subject.lower() and claim.relation.lower() == "located_in_region"
                ]
                if inferred:
                    pick = sorted(inferred, key=lambda item: item.key)[0]
                    return QueryResult(
                        answer_claim={"subject": pick.subject, "relation": pick.relation, "object": pick.object},
                        touched_shards=tuple(sorted(set(touched_shards + ["geography.location"]))),
                        touched_indexes=plan.required_indexes,
                        rows_examined=rows_examined,
                        fallback_used=False,
                    )

        return QueryResult(
            answer_claim=None,
            touched_shards=tuple(sorted(set(touched_shards))),
            touched_indexes=plan.required_indexes,
            rows_examined=rows_examined,
            fallback_used=True,
        )

