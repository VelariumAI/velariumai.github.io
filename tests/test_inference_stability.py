from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from vcse.inference.stability import InferenceStabilityTracker


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


def test_stability_tracker_deterministic_counts() -> None:
    tracker = InferenceStabilityTracker()
    tracker.record("Paris|capital_of|France", "inverse")
    tracker.record("Paris|capital_of|France", "inverse")
    tracker.record("Paris|located_in_region|Europe", "transitive")
    counts = tracker.get_counts()
    assert [(item.claim_key, item.inference_type, item.occurrences) for item in counts] == [
        ("Paris|capital_of|France", "inverse", 2),
        ("Paris|located_in_region|Europe", "transitive", 1),
    ]


def test_stability_threshold_filtering() -> None:
    tracker = InferenceStabilityTracker()
    tracker.record("A|r|B", "inverse")
    tracker.record("A|r|B", "inverse")
    tracker.record("C|r|D", "transitive")
    stable = tracker.get_stable(2)
    assert len(stable) == 1
    assert stable[0].claim_key == "A|r|B"
    assert stable[0].inference_type == "inverse"
    assert stable[0].occurrences == 2


def test_stability_cli_is_deterministic_across_runs(tmp_path: Path) -> None:
    home = tmp_path / "vcse_home"
    repo_root = Path(__file__).resolve().parents[1]
    indexed = run_cli("pack", "index", "--dirs", str(repo_root / "examples" / "packs"), pack_home=home)
    assert indexed.returncode == 0

    first = run_cli("infer", "stability", "--pack", "general_world", "--json", pack_home=home)
    second = run_cli("infer", "stability", "--pack", "general_world", "--json", pack_home=home)
    assert first.returncode == 0
    assert second.returncode == 0
    assert json.loads(first.stdout) == json.loads(second.stdout)


def test_infer_commands_do_not_mutate_pack(tmp_path: Path) -> None:
    home = tmp_path / "vcse_home"
    repo_root = Path(__file__).resolve().parents[1]
    indexed = run_cli("pack", "index", "--dirs", str(repo_root / "examples" / "packs"), pack_home=home)
    assert indexed.returncode == 0
    info = run_cli("pack", "info", "general_world", "--json", pack_home=home)
    assert info.returncode == 0
    pack_path = Path(json.loads(info.stdout)["pack_path"])
    claims_path = pack_path / "claims.jsonl"
    before = _sha256(claims_path)

    stable = run_cli("infer", "stability", "--pack", "general_world", pack_home=home)
    promote = run_cli("infer", "promote", "--pack", "general_world", "--threshold", "2", pack_home=home)
    assert stable.returncode == 0
    assert promote.returncode == 0
    after = _sha256(claims_path)
    assert before == after


def test_promotion_output_is_deterministic(tmp_path: Path) -> None:
    home = tmp_path / "vcse_home"
    repo_root = Path(__file__).resolve().parents[1]
    indexed = run_cli("pack", "index", "--dirs", str(repo_root / "examples" / "packs"), pack_home=home)
    assert indexed.returncode == 0

    first = run_cli("infer", "promote", "--pack", "general_world", "--threshold", "2", pack_home=home)
    second = run_cli("infer", "promote", "--pack", "general_world", "--threshold", "2", pack_home=home)
    assert first.returncode == 0
    assert second.returncode == 0
    assert first.stdout == second.stdout


def test_stability_threshold_changes_results(tmp_path: Path) -> None:
    home = tmp_path / "vcse_home"
    repo_root = Path(__file__).resolve().parents[1]
    indexed = run_cli("pack", "index", "--dirs", str(repo_root / "examples" / "packs"), pack_home=home)
    assert indexed.returncode == 0

    low = run_cli("infer", "stability", "--pack", "general_world", "--threshold", "1", "--json", pack_home=home)
    high = run_cli("infer", "stability", "--pack", "general_world", "--threshold", "2", "--json", pack_home=home)
    assert low.returncode == 0
    assert high.returncode == 0
    low_payload = json.loads(low.stdout)
    high_payload = json.loads(high.stdout)
    assert low_payload["stable_inferred_claims"] >= high_payload["stable_inferred_claims"]
