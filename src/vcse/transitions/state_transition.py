"""Explicit state transition model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.transitions.actions import ADD_CLAIM
from vcse.verifier.base import VerificationResult


@dataclass(frozen=True)
class Transition:
    type: str
    args: dict[str, Any]
    description: str
    expected_effect: str
    source: str = "proposer"

    def validate(self, state: WorldStateMemory) -> VerificationResult:
        if self.type != ADD_CLAIM:
            return VerificationResult.fail_result(
                status="INVALID_TRANSITION",
                reasons=[f"Unsupported transition type: {self.type}"],
            )

        missing = [key for key in ("subject", "relation", "object") if not self.args.get(key)]
        if missing:
            return VerificationResult.fail_result(
                status="INVALID_TRANSITION",
                reasons=[f"Missing required AddClaim args: {', '.join(missing)}"],
            )

        relation = str(self.args["relation"]).strip()
        if state.relation_schemas and state.get_relation_schema(relation) is None:
            return VerificationResult.fail_result(
                status="INVALID_TRANSITION",
                reasons=[f"Unknown relation schema: {relation}"],
            )

        return VerificationResult.pass_result(status="VALID_TRANSITION")

    def apply(self, state: WorldStateMemory) -> tuple[WorldStateMemory, VerificationResult]:
        validation = self.validate(state)
        if not validation.passed:
            return state.clone(), validation

        new_state = state.clone()
        dependencies = self.args.get("dependencies")
        if dependencies is not None and not isinstance(dependencies, list):
            return new_state, VerificationResult.fail_result(
                status="INVALID_TRANSITION",
                reasons=["dependencies must be a list when provided"],
            )

        raw_status = self.args.get("status", TruthStatus.SUPPORTED)
        status = raw_status if isinstance(raw_status, TruthStatus) else TruthStatus(str(raw_status))
        claim_id = new_state.add_claim(
            self.args["subject"],
            self.args["relation"],
            self.args["object"],
            status=status,
            dependencies=dependencies,
            source=self.source,
        )
        return new_state, VerificationResult.pass_result(
            status="APPLIED",
            reasons=[self.expected_effect],
            affected_elements=[claim_id],
        )
