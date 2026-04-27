"""Gauntlet execution runner."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from vcse.dsl.schema import CapabilityBundle
from vcse.engine import build_search, state_from_case
from vcse.gauntlet.case import GauntletCase
from vcse.gauntlet.errors import GauntletError
from vcse.generation import VerifiedGenerator, spec_from_dict
from vcse.ingestion.pipeline import ingest_file
from vcse.interaction.session import Session
from vcse.memory.relations import RelationSchema
from vcse.memory.world_state import TruthStatus, WorldStateMemory


@dataclass(frozen=True)
class GauntletRunConfig:
    search_backend: str = "beam"
    enable_ts3: bool = False
    enable_index: bool = False
    top_k_rules: int = 20
    top_k_packs: int = 5
    dsl_bundle: CapabilityBundle | None = None
    debug: bool = False


@dataclass
class GauntletCaseResult:
    case_id: str
    category: str
    mode: str
    status: str
    answer: Any | None = None
    proof_trace: list[str] = field(default_factory=list)
    artifact: dict[str, Any] | None = None
    search_stats: dict[str, Any] | None = None
    ts3_stats: dict[str, Any] | None = None
    runtime_ms: float = 0.0
    raw_result: dict[str, Any] = field(default_factory=dict)


class GauntletRunner:
    def run(
        self,
        cases: list[GauntletCase],
        config: GauntletRunConfig,
    ) -> list[GauntletCaseResult]:
        results: list[GauntletCaseResult] = []
        for case in cases:
            started = time.perf_counter()
            result = self._run_case(case, config)
            elapsed_ms = (time.perf_counter() - started) * 1000
            result.runtime_ms = elapsed_ms
            results.append(result)
        return results

    def _run_case(self, case: GauntletCase, config: GauntletRunConfig) -> GauntletCaseResult:
        if case.mode == "ask":
            return self._run_ask_case(case, config)
        if case.mode == "generate":
            return self._run_generate_case(case, config)
        if case.mode == "ingest":
            return self._run_ingest_case(case, config)
        raise GauntletError("INVALID_CASE", f"Unsupported mode: {case.mode}")

    def _run_ask_case(self, case: GauntletCase, config: GauntletRunConfig) -> GauntletCaseResult:
        if isinstance(case.input, str):
            session = Session.create(
                dsl_bundle=config.dsl_bundle,
                enable_indexing=config.enable_index,
                top_k_rules=config.top_k_rules,
                top_k_packs=config.top_k_packs,
            )
            session.ingest(case.input)
            solve_result = session.solve(
                enable_ts3=config.enable_ts3,
                search_backend=config.search_backend,
            )
            if solve_result is None:
                return GauntletCaseResult(
                    case_id=case.id,
                    category=case.category,
                    mode=case.mode,
                    status="INCONCLUSIVE",
                    raw_result={"result": None},
                )
            if hasattr(solve_result, "user_message"):
                return GauntletCaseResult(
                    case_id=case.id,
                    category=case.category,
                    mode=case.mode,
                    status="NEEDS_CLARIFICATION",
                    answer=getattr(solve_result, "user_message", None),
                    raw_result={"user_message": getattr(solve_result, "user_message", None)},
                )
            eval_result = solve_result.evaluation
            ts3 = solve_result.ts3_analysis
            return GauntletCaseResult(
                case_id=case.id,
                category=case.category,
                mode=case.mode,
                status=eval_result.status.value,
                answer=eval_result.answer,
                proof_trace=list(eval_result.proof_trace),
                search_stats=asdict(solve_result.stats),
                ts3_stats=(asdict(ts3) if ts3 is not None else None),
                raw_result={
                    "reasons": list(eval_result.reasons),
                    "retrieval_stats": solve_result.retrieval_stats,
                },
            )

        payload = dict(case.input)
        state = state_from_case(payload)
        if config.dsl_bundle is not None:
            for schema in getattr(config.dsl_bundle, "relation_schemas", []):
                name = str(schema.get("name", "")).strip()
                if not name:
                    continue
                if state.get_relation_schema(name) is None:
                    properties = set(schema.get("properties", []))
                    state.add_relation_schema(
                        RelationSchema(
                            name=name,
                            transitive="transitive" in properties,
                            symmetric="symmetric" in properties,
                            reflexive="reflexive" in properties,
                            functional="functional" in properties,
                        )
                    )
        result = build_search(
            enable_ts3=config.enable_ts3,
            search_backend=config.search_backend,
            dsl_bundle=config.dsl_bundle,
        ).run(state)
        eval_result = result.evaluation
        return GauntletCaseResult(
            case_id=case.id,
            category=case.category,
            mode=case.mode,
            status=eval_result.status.value,
            answer=eval_result.answer,
            proof_trace=list(eval_result.proof_trace),
            search_stats=asdict(result.stats),
            ts3_stats=(asdict(result.ts3_analysis) if result.ts3_analysis is not None else None),
            raw_result={"reasons": list(eval_result.reasons)},
        )

    def _run_generate_case(self, case: GauntletCase, config: GauntletRunConfig) -> GauntletCaseResult:
        payload: dict[str, Any]
        if isinstance(case.input, str):
            path = Path(case.input)
            try:
                payload = json.loads(path.read_text())
            except json.JSONDecodeError as exc:
                raise GauntletError("MALFORMED_SPEC", exc.msg) from exc
            except OSError as exc:
                raise GauntletError("FILE_ERROR", str(exc)) from exc
        else:
            payload = dict(case.input)

        spec = spec_from_dict(payload)
        memory = WorldStateMemory()
        for fact in payload.get("memory_claims", []):
            if not isinstance(fact, dict):
                continue
            subject = str(fact.get("subject", "")).strip()
            relation = str(fact.get("relation", "")).strip()
            obj = str(fact.get("object", "")).strip()
            if not (subject and relation and obj):
                continue
            if memory.get_relation_schema(relation) is None:
                memory.add_relation_schema(RelationSchema(name=relation, transitive=(relation == "is_a")))
            memory.add_claim(subject, relation, obj, TruthStatus.ASSERTED)

        result = VerifiedGenerator().generate(
            spec=spec,
            memory=memory,
            bundle=config.dsl_bundle,
            enable_index=config.enable_index,
            top_k_rules=config.top_k_rules,
        )
        artifact_dict = result.best_artifact.to_dict() if result.best_artifact is not None else None
        return GauntletCaseResult(
            case_id=case.id,
            category=case.category,
            mode=case.mode,
            status=result.status,
            answer=(artifact_dict.get("content") if artifact_dict else None),
            artifact=artifact_dict,
            search_stats=dict(result.search_stats),
            raw_result={
                "evaluation_reasons": list(result.evaluation_reasons),
                "clarification_request": result.clarification_request,
                "template_stats": dict(result.template_stats),
            },
        )

    def _run_ingest_case(self, case: GauntletCase, config: GauntletRunConfig) -> GauntletCaseResult:
        if not isinstance(case.input, dict):
            raise GauntletError("INVALID_CASE", f"{case.id}: ingest mode requires object input")
        payload = case.input
        result = ingest_file(
            path=payload.get("path", ""),
            template_name=payload.get("template_name"),
            auto=bool(payload.get("auto", True)),
            dry_run=bool(payload.get("dry_run", True)),
            dsl_bundle=config.dsl_bundle,
        )
        status = _map_ingestion_status(result.import_result.status)
        return GauntletCaseResult(
            case_id=case.id,
            category=case.category,
            mode=case.mode,
            status=status,
            answer=result.import_result.created_elements,
            raw_result={
                "import_status": result.import_result.status,
                "warnings": list(result.import_result.warnings),
                "errors": list(result.import_result.errors),
                "contradictions_detected": list(result.import_result.contradictions_detected),
            },
        )


def _map_ingestion_status(status: str) -> str:
    if status in {"IMPORTED", "PARTIAL"}:
        return "VERIFIED"
    if status == "CONTRADICTORY":
        return "CONTRADICTORY"
    if status in {"REJECTED", "UNSUPPORTED_FORMAT", "VALIDATION_FAILED"}:
        return "FAILED_ARTIFACT"
    return "INCONCLUSIVE"
