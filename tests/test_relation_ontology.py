from __future__ import annotations

import subprocess
import os
import sys
from pathlib import Path

from vcse.knowledge.pack_model import KnowledgeClaim, KnowledgeProvenance
from vcse.semantic.relation_ontology import canonicalize_relation
from vcse.semantic.region_builder import build_regions


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
    return subprocess.run([sys.executable, "-m", "vcse.cli", *args], capture_output=True, text=True, env=env)


def test_canonicalization_maps_inverse_to_canonical() -> None:
    assert canonicalize_relation("has_capital") == "has_capital"
    assert canonicalize_relation("capital_of") == "has_capital"


def test_canonicalization_leaves_unknown_unchanged() -> None:
    assert canonicalize_relation("located_in_region") == "located_in_region"


def test_region_builder_split_vs_canonical_merge() -> None:
    claims = [
        _claim("France", "has_capital", "Paris"),
        _claim("Paris", "capital_of", "France"),
    ]

    split = build_regions(claims, canonicalize=False)
    merged = build_regions(claims, canonicalize=True)

    assert len(split) == 2
    assert len(merged) == 1
    assert merged[0].relations == {"has_capital"}


def test_ask_output_unchanged_for_general_world_pack() -> None:
    result = _run_cli("ask", "What is the capital of France?", "--pack", "general_world")
    assert result.returncode == 0
    assert "Paris is the capital of France." in result.stdout
