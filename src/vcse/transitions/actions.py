"""Named transition action constants."""

ADD_CLAIM = "AddClaim"
ADD_CONSTRAINT = "AddConstraint"
UPDATE_TRUTH_STATUS = "UpdateTruthStatus"
BIND_SYMBOL = "BindSymbol"
ADD_GOAL = "AddGoal"
ADD_EVIDENCE = "AddEvidence"
RECORD_CONTRADICTION = "RecordContradiction"

ALL_ACTIONS = {
    ADD_CLAIM,
    ADD_CONSTRAINT,
    UPDATE_TRUTH_STATUS,
    BIND_SYMBOL,
    ADD_GOAL,
    ADD_EVIDENCE,
    RECORD_CONTRADICTION,
}
