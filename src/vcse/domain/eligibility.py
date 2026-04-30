"""Eligibility domain pack (stub): returns clarification if criteria missing."""

from vcse.domain.base import DomainPack, RelationSchema


class EligibilityDomainPack(DomainPack):
    """Domain pack for eligibility reasoning.

    This is a stub. It provides no fake eligibility assumptions.
    If a user asks about eligibility without defining criteria,
    the system returns a clarification request.
    """

    def __init__(self) -> None:
        super().__init__(
            name="eligibility",
            relation_schemas=[
                RelationSchema(name="eligible", transitive=False, description="Eligibility status"),
                RelationSchema(name="meets_criteria", transitive=False, description="Meets requirements"),
            ],
            synonyms={
                "qualifies": "eligible",
                "is qualified": "eligible",
            },
            patterns=[
                "{subject} is eligible",
                "{subject} meets criteria",
                "is {subject} eligible",
            ],
        )
