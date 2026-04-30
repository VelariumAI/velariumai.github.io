from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from vcse.inference.promotion import promote_stable_claims


def run_cli(*args: str, pack_home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    env["VCSE_PACK_HOME"] = str(pack_home)
    return subprocess.run(
        [sys.executable, "-m", "vcse.cli", *args],
        capture_output=True,
        env=env,
        text=True,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _Stable:
    def __init__(self, claim_key: str, inference_type: str, occurrences: int, source_claims: tuple[str, ...]) -> None:
        self.claim_key = claim_key
        self.inference_type = inference_type
        self.occurrences = occurrences
        self.source_claims = source_claims


def test_promotion_correctness_and_threshold_filtering() -> None:
    stable = [
        _Stable("Paris|capital_of|France", "inverse", 3, ("France|has_capital|Paris",)),
        _Stable("Lyon|located_in_region|Europe", "transitive", 1, ("Lyon|located_in_country|France", "France|part_of|Europe")),
    ]
    promoted = promote_stable_claims(stable, threshold=2)
    assert len(promoted) == 1
    claim = promoted[0]
    assert claim.subject == "Paris"
    assert claim.relation == "capital_of"
    assert claim.object == "France"
    assert claim.source_claims == ("France|has_capital|Paris",)
    assert claim.inference_type == "inverse"


def test_promotion_deterministic_ordering() -> None:
    stable = [
        _Stable("b|r|x", "inverse", 2, ("s2",)),
        _Stable("a|r|x", "inverse", 2, ("s1",)),
    ]
    promoted = promote_stable_claims(stable, threshold=2)
    assert [item.claim_key for item in promoted] == ["a|r|x", "b|r|x"]


def test_promotion_write_output_and_provenance(tmp_path: Path) -> None:
    home = tmp_path / "vcse_home"
    repo_root = Path(__file__).resolve().parents[1]
    indexed = run_cli("pack", "index", "--dirs", str(repo_root / "examples" / "packs"), pack_home=home)
    assert indexed.returncode == 0

    output_path = tmp_path / "promoted_claims.jsonl"
    result = run_cli(
        "infer",
        "promote",
        "--pack",
        "general_world",
        "--threshold",
        "2",
        "--write",
        "--output",
        str(output_path),
        "--json",
        pack_home=home,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["write"] is True
    assert output_path.exists()
    lines = [json.loads(line) for line in output_path.read_text().splitlines() if line.strip()]
    assert len(lines) == payload["stable_inferred_count"]
    if lines:
        first = lines[0]
        assert "source_claims" in first
        assert "inference_type" in first
        assert "promoted_at" in first
        assert isinstance(first["source_claims"], list)


def test_infer_promote_does_not_mutate_original_pack(tmp_path: Path) -> None:
    home = tmp_path / "vcse_home"
    repo_root = Path(__file__).resolve().parents[1]
    indexed = run_cli("pack", "index", "--dirs", str(repo_root / "examples" / "packs"), pack_home=home)
    assert indexed.returncode == 0

    info = run_cli("pack", "info", "general_world", "--json", pack_home=home)
    assert info.returncode == 0
    pack_path = Path(json.loads(info.stdout)["pack_path"])
    claims_path = pack_path / "claims.jsonl"
    before = _sha256(claims_path)

    output_path = tmp_path / "promoted_claims.jsonl"
    promoted = run_cli(
        "infer",
        "promote",
        "--pack",
        "general_world",
        "--threshold",
        "2",
        "--write",
        "--output",
        str(output_path),
        pack_home=home,
    )
    assert promoted.returncode == 0
    after = _sha256(claims_path)
    assert before == after

