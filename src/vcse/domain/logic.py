"""Logic domain pack: transitive reasoning with is_a, equals, part_of."""

from vcse.domain.base import DomainPack, RelationSchema


class LogicDomainPack(DomainPack):
    """Domain pack for logical transitive reasoning."""

    def __init__(self) -> None:
        super().__init__(
            name="logic",
            relation_schemas=[
                RelationSchema(name="is_a", transitive=True, description="Type membership"),
                RelationSchema(name="equals", transitive=False, symmetric=True, description="Equality"),
                RelationSchema(name="part_of", transitive=True, description="Part-whole relationship"),
            ],
            synonyms={
                "kind of": "is_a",
                "type of": "is_a",
                "same as": "equals",
                "identical to": "equals",
                "part of": "part_of",
                "belongs to": "part_of",
            },
            patterns=[
                "{subject} is a {object}",
                "{subject} is {object}",
                "all {subject} are {object}",
                "every {subject} is {object}",
                "{subject} equals {object}",
                "{subject} is part of {object}",
            ],
        )
