"""Explicit state transition model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from vcse.memory.constraints import Constraint
from vcse.memory.world_state import TruthStatus, WorldStateMemory
from vcse.transitions.actions import (
    ADD_CLAIM,
    ADD_CONSTRAINT,
    ADD_EVIDENCE,
    ADD_GOAL,
    ALL_ACTIONS,
    BIND_SYMBOL,
    RECORD_CONTRADICTION,
    UPDATE_TRUTH_STATUS,
)
from vcse.verifier.base import VerificationResult


@dataclass(frozen=True)
class Transition:
    type: str
    args: dict[str, Any]
    description: str
    expected_effect: str
    source: str = "proposer"

    def validate(self, state: WorldStateMemory) -> VerificationResult:
        if self.type not in ALL_ACTIONS:
            return VerificationResult.fail_result(
                status="INVALID_TRANSITION",
                reasons=[f"Unsupported transition type: {self.type}"],
            )

        validators: dict[str, Callable[[WorldStateMemory], VerificationResult]] = {
            ADD_CLAIM: self._validate_add_claim,
            ADD_CONSTRAINT: self._validate_add_constraint,
            UPDATE_TRUTH_STATUS: self._validate_update_truth_status,
            BIND_SYMBOL: self._validate_bind_symbol,
            ADD_GOAL: self._validate_add_goal,
            ADD_EVIDENCE: self._validate_add_evidence,
            RECORD_CONTRADICTION: self._validate_record_contradiction,
        }
        return validators[self.type](state)

    def apply(self, state: WorldStateMemory) -> tuple[WorldStateMemory, VerificationResult]:
        validation = self.validate(state)
        new_state = state.clone()
        if not validation.passed:
            return new_state, validation

        appliers: dict[str, Callable[[WorldStateMemory], VerificationResult]] = {
            ADD_CLAIM: self._apply_add_claim,
            ADD_CONSTRAINT: self._apply_add_constraint,
            UPDATE_TRUTH_STATUS: self._apply_update_truth_status,
            BIND_SYMBOL: self._apply_bind_symbol,
            ADD_GOAL: self._apply_add_goal,
            ADD_EVIDENCE: self._apply_add_evidence,
            RECORD_CONTRADICTION: self._apply_record_contradiction,
        }
        result = appliers[self.type](new_state)
        return new_state, result

    def _missing_required(self, keys: tuple[str, ...]) -> list[str]:
        return [key for key in keys if self.args.get(key) is None or self.args.get(key) == ""]

    def _validate_add_claim(self, state: WorldStateMemory) -> VerificationResult:
        missing = self._missing_required(("subject", "relation", "object"))
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

    def _validate_add_constraint(self, state: WorldStateMemory) -> VerificationResult:
        missing = self._missing_required(("kind", "target", "operator", "value"))
        if missing:
            return VerificationResult.fail_result(
                status="INVALID_TRANSITION",
                reasons=[f"Missing required AddConstraint args: {', '.join(missing)}"],
            )
        try:
            Constraint(
                kind=str(self.args["kind"]),
                target=str(self.args["target"]),
                operator=str(self.args["operator"]),
                value=self.args["value"],
                description=str(self.args.get("description", "")),
            )
        except (KeyError, ValueError) as exc:
            return VerificationResult.fail_result(
                status="INVALID_TRANSITION",
                reasons=[str(exc)],
            )
        return VerificationResult.pass_result(status="VALID_TRANSITION")

    def _validate_update_truth_status(self, state: WorldStateMemory) -> VerificationResult:
        missing = self._missing_required(("claim_id", "status"))
        if missing:
            return VerificationResult.fail_result(
                status="INVALID_TRANSITION",
                reasons=[f"Missing required UpdateTruthStatus args: {', '.join(missing)}"],
            )
        claim_id = str(self.args["claim_id"])
        if state.get_claim(claim_id) is None:
            return VerificationResult.fail_result(
                status="INVALID_TRANSITION",
                reasons=[f"Unknown claim_id: {claim_id}"],
            )
        try:
            self._truth_status_from_arg(self.args["status"])
        except ValueError as exc:
            return VerificationResult.fail_result(
                status="INVALID_TRANSITION",
                reasons=[str(exc)],
            )
        return VerificationResult.pass_result(status="VALID_TRANSITION")

    def _validate_bind_symbol(self, state: WorldStateMemory) -> VerificationResult:
        missing = self._missing_required(("name", "value"))
        if missing:
            return VerificationResult.fail_result(
                status="INVALID_TRANSITION",
                reasons=[f"Missing required BindSymbol args: {', '.join(missing)}"],
            )
        return VerificationResult.pass_result(status="VALID_TRANSITION")

    def _validate_add_goal(self, state: WorldStateMemory) -> VerificationResult:
        missing = self._missing_required(("subject", "relation", "object"))
        if missing:
            return VerificationResult.fail_result(
                status="INVALID_TRANSITION",
                reasons=[f"Missing required AddGoal args: {', '.join(missing)}"],
            )
        return VerificationResult.pass_result(status="VALID_TRANSITION")

    def _validate_add_evidence(self, state: WorldStateMemory) -> VerificationResult:
        missing = self._missing_required(("target_id", "content"))
        if missing:
            return VerificationResult.fail_result(
                status="INVALID_TRANSITION",
                reasons=[f"Missing required AddEvidence args: {', '.join(missing)}"],
            )
        return VerificationResult.pass_result(status="VALID_TRANSITION")

    def _validate_record_contradiction(self, state: WorldStateMemory) -> VerificationResult:
        missing = self._missing_required(("element_id", "reason"))
        if missing:
            return VerificationResult.fail_result(
                status="INVALID_TRANSITION",
                reasons=[f"Missing required RecordContradiction args: {', '.join(missing)}"],
            )
        related = self.args.get("related_element_ids", [])
        if not isinstance(related, list):
            return VerificationResult.fail_result(
                status="INVALID_TRANSITION",
                reasons=["related_element_ids must be a list when provided"],
            )
        return VerificationResult.pass_result(status="VALID_TRANSITION")

    def _apply_add_claim(self, new_state: WorldStateMemory) -> VerificationResult:
        dependencies = self.args.get("dependencies")
        if dependencies is not None and not isinstance(dependencies, list):
            return VerificationResult.fail_result(
                status="INVALID_TRANSITION",
                reasons=["dependencies must be a list when provided"],
            )

        try:
            status = self._truth_status_from_arg(self.args.get("status", TruthStatus.SUPPORTED))
        except ValueError as exc:
            return VerificationResult.fail_result(
                status="INVALID_TRANSITION",
                reasons=[str(exc)],
            )
        claim_id = new_state.add_claim(
            self.args["subject"],
            self.args["relation"],
            self.args["object"],
            status=status,
            qualifiers=self.args.get("qualifiers"),
            dependencies=dependencies,
            source=self.source,
        )
        return VerificationResult.pass_result(
            status="APPLIED",
            reasons=[self.expected_effect],
            affected_elements=[claim_id],
        )

    def _apply_add_constraint(self, new_state: WorldStateMemory) -> VerificationResult:
        constraint = Constraint(
            kind=str(self.args["kind"]),
            target=str(self.args["target"]),
            operator=str(self.args["operator"]),
            value=self.args["value"],
            description=str(self.args.get("description", "")),
        )
        new_state.add_constraint(constraint)
        constraint_id = new_state.constraint_id_for_index(len(new_state.constraints) - 1)
        return VerificationResult.pass_result(
            status="APPLIED",
            reasons=[self.expected_effect],
            affected_elements=[constraint_id],
        )

    def _apply_update_truth_status(self, new_state: WorldStateMemory) -> VerificationResult:
        claim_id = str(self.args["claim_id"])
        status = self._truth_status_from_arg(self.args["status"])
        new_state.update_truth_status(claim_id, status)
        return VerificationResult.pass_result(
            status="APPLIED",
            reasons=[self.expected_effect],
            affected_elements=[claim_id],
        )

    def _apply_bind_symbol(self, new_state: WorldStateMemory) -> VerificationResult:
        symbol_id = new_state.bind_symbol(self.args["name"], self.args["value"])
        return VerificationResult.pass_result(
            status="APPLIED",
            reasons=[self.expected_effect],
            affected_elements=[symbol_id],
        )

    def _apply_add_goal(self, new_state: WorldStateMemory) -> VerificationResult:
        goal_id = new_state.add_goal(
            self.args["subject"],
            self.args["relation"],
            self.args["object"],
        )
        return VerificationResult.pass_result(
            status="APPLIED",
            reasons=[self.expected_effect],
            affected_elements=[goal_id],
        )

    def _apply_add_evidence(self, new_state: WorldStateMemory) -> VerificationResult:
        evidence_id = new_state.add_evidence(
            target_id=str(self.args["target_id"]),
            content=self.args["content"],
            source=str(self.args.get("source", self.source)),
        )
        return VerificationResult.pass_result(
            status="APPLIED",
            reasons=[self.expected_effect],
            affected_elements=[evidence_id],
        )

    def _apply_record_contradiction(self, new_state: WorldStateMemory) -> VerificationResult:
        contradiction_id = new_state.record_contradiction(
            element_id=str(self.args["element_id"]),
            reason=str(self.args["reason"]),
            related_element_ids=[str(item) for item in self.args.get("related_element_ids", [])],
            severity=str(self.args.get("severity", "high")),
        )
        return VerificationResult.pass_result(
            status="APPLIED",
            reasons=[self.expected_effect],
            affected_elements=[contradiction_id],
        )

    def _truth_status_from_arg(self, raw_status: Any) -> TruthStatus:
        if isinstance(raw_status, TruthStatus):
            return raw_status
        try:
            return TruthStatus(str(raw_status))
        except ValueError as exc:
            allowed = ", ".join(item.value for item in TruthStatus)
            raise ValueError(f"Invalid TruthStatus {raw_status!r}; expected one of: {allowed}") from exc
