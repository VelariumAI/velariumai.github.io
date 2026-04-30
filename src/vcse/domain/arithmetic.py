"""Arithmetic domain pack: numeric constraints and comparisons."""

from vcse.domain.base import DomainPack, RelationSchema


class ArithmeticDomainPack(DomainPack):
    """Domain pack for numeric reasoning."""

    def __init__(self) -> None:
        super().__init__(
            name="arithmetic",
            relation_schemas=[
                RelationSchema(name="equals", transitive=False, symmetric=True, description="Numeric equality"),
            ],
            synonyms={
                "greater than": ">",
                "less than": "<",
                "greater than or equal to": ">=",
                "less than or equal to": "<=",
                "at least": ">=",
                "at most": "<=",
                "more than": ">",
                "under": "<",
            },
            patterns=[
                "{target} = {value}",
                "{target} equals {value}",
                "{target} > {value}",
                "{target} < {value}",
                "{target} >= {value}",
                "{target} <= {value}",
                "{target} is greater than {value}",
                "{target} is less than {value}",
                "{target} is at least {value}",
                "{target} is at most {value}",
            ],
        )
