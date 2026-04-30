from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from vcse.inference.explanation import (
    build_inverse_explanation,
    build_transitive_explanation,
)
from vcse.inference.inverse import infer_inverse_claims
from vcse.inference.transitive import infer_transitive_claims
from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgeProvenance


def _claim(subject: str, relation: str, obj: str) -> KnowledgeClaim:
    return KnowledgeClaim(
        subject=subject,
        relation=relation,
        object=obj,
        provenance=KnowledgeProvenance(
            source_id="src",
            source_type="test",
            location="unit",
            evidence_text="evidence",
        ),
    )


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "vcse.cli", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_inverse_explanation_correctness() -> None:
    claims = [_claim("France", "has_capital", "Paris")]
    inferred = infer_inverse_claims(claims)
    assert len(inferred) == 1
    explanation = build_inverse_explanation(inferred[0])
    assert explanation.conclusion == ("Paris", "capital_of", "France")
    assert explanation.rule == "inverse_relation"
    assert len(explanation.steps) == 1
    assert explanation.steps[0].subject == "France"
    assert explanation.steps[0].relation == "has_capital"
    assert explanation.steps[0].object == "Paris"


def test_transitive_explanation_correctness() -> None:
    claims = [
        _claim("Paris", "located_in_country", "France"),
        _claim("France", "part_of", "Europe"),
    ]
    inferred = infer_transitive_claims(claims)
    assert len(inferred) == 1
    explanation = build_transitive_explanation(inferred[0])
    assert explanation.conclusion == ("Paris", "located_in_region", "Europe")
    assert explanation.rule == "transitive_location_containment"
    assert [(step.subject, step.relation, step.object) for step in explanation.steps] == [
        ("Paris", "located_in_country", "France"),
        ("France", "part_of", "Europe"),
    ]


def test_explanation_uses_only_real_claims() -> None:
    claims = [
        _claim("Paris", "located_in_country", "France"),
        _claim("France", "part_of", "Europe"),
    ]
    inferred = infer_transitive_claims(claims)
    explanation = build_transitive_explanation(inferred[0])
    explicit_keys = {claim.key for claim in claims}
    assert {f"{step.subject}|{step.relation}|{step.object}" for step in explanation.steps}.issubset(explicit_keys)


def test_explanation_deterministic_ordering() -> None:
    claims = [
        _claim("Paris", "located_in_country", "France"),
        _claim("France", "part_of", "Europe"),
    ]
    inferred = infer_transitive_claims(claims)
    first = build_transitive_explanation(inferred[0])
    second = build_transitive_explanation(inferred[0])
    assert first.steps == second.steps
    assert len(first.steps) == 2


def test_explicit_claims_produce_no_explanation_output() -> None:
    result = _run_cli("ask", "What is the capital of France?", "--pack", "general_world")
    assert result.returncode == 0
    assert result.stdout.strip() == "Paris is the capital of France."
    assert "because:" not in result.stdout


def test_no_mutation_of_claims() -> None:
    claims = [
        _claim("Paris", "located_in_country", "France"),
        _claim("France", "part_of", "Europe"),
    ]
    before = [claim.key for claim in claims]
    inferred = infer_transitive_claims(claims)
    _ = build_transitive_explanation(inferred[0])
    after = [claim.key for claim in claims]
    assert after == before


def test_inferred_answer_renders_bullets_deterministically() -> None:
    result = _run_cli("ask", "What continent is Paris in?", "--pack", "general_world")
    assert result.returncode == 0
    assert result.stdout.strip() == (
        "Paris is in the Europe region because:\n"
        "- Paris is in France.\n"
        "- France is part of Europe."
    )


def test_inferred_answer_can_disable_explanation() -> None:
    result = _run_cli("ask", "What continent is Paris in?", "--pack", "general_world", "--no-explain")
    assert result.returncode == 0
    assert result.stdout.strip() == "Europe"
