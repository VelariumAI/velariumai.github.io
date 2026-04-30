from vcse.ingestion.source import SourceDocument
from vcse.ingestion.templates import BUILTIN_TEMPLATES, extract_frames
from vcse.interaction.frames import ClaimFrame


def test_text_template_extracts_claims() -> None:
    source = SourceDocument(
        id="src:test",
        source_type="text",
        path_or_uri="sample.txt",
        content="All employees are workers.",
    )
    frames, warnings = extract_frames(source, BUILTIN_TEMPLATES["text_policy"])
    assert any(isinstance(frame, ClaimFrame) for frame in frames)
    assert any(frame.relation == "is_a" for frame in frames if isinstance(frame, ClaimFrame))
    assert not warnings or isinstance(warnings, list)


def test_csv_template_extracts_claim() -> None:
    source = SourceDocument(
        id="src:test",
        source_type="csv",
        path_or_uri="sample.csv",
        content=[{"subject": "a", "relation": "is_a", "object": "b"}],
    )
    frames, _ = extract_frames(source, BUILTIN_TEMPLATES["csv_triples"])
    assert len(frames) == 1
    frame = frames[0]
    assert isinstance(frame, ClaimFrame)
    assert frame.subject == "a"
    assert frame.relation == "is_a"
    assert frame.object == "b"


def test_failed_template_match_returns_warning() -> None:
    source = SourceDocument(
        id="src:test",
        source_type="text",
        path_or_uri="sample.txt",
        content="nonsense phrase",
    )
    frames, warnings = extract_frames(source, BUILTIN_TEMPLATES["text_policy"])
    assert frames == []
    assert warnings
