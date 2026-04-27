from pathlib import Path

from vcse.knowledge.extractor import KnowledgeExtractor
from vcse.knowledge.sources import Source


def test_text_extractor_handles_capital_pattern(tmp_path: Path) -> None:
    source_path = tmp_path / "facts.txt"
    source_path.write_text("Paris is the capital of France.\n")
    source = Source(
        id="cities",
        type="text",
        path=str(source_path),
        trust_level="trusted",
        update_frequency="manual",
        schema_hint="text_policy",
    )

    result = KnowledgeExtractor().extract(source)

    assert result.claims[0].subject == "Paris"
    assert result.claims[0].relation == "is_a"
    assert result.claims[0].object == "capital_of_France"
    assert result.claims[0].provenance.source_id == "cities"


def test_structured_extraction_is_deterministic(tmp_path: Path) -> None:
    source_path = tmp_path / "claims.json"
    source_path.write_text('{"facts":[{"subject":"employee","relation":"is_a","object":"worker"}]}')
    source = Source(id="claims", type="json", path=str(source_path))

    first = KnowledgeExtractor().extract(source)
    second = KnowledgeExtractor().extract(source)

    assert [claim.to_dict() for claim in first.claims] == [claim.to_dict() for claim in second.claims]
