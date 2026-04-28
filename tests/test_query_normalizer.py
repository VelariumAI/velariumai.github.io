import os
import subprocess
import sys
from pathlib import Path

from vcse.interaction.query_normalizer import normalize_query


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "vcse.cli", *args],
        capture_output=True,
        env=env,
        text=True,
    )


def test_query_normalizer_exact_patterns() -> None:
    one = normalize_query("What is the capital of France?")
    assert one is not None
    assert one.subject == "France"
    assert one.relation == "capital_of"
    assert one.object is None

    two = normalize_query("What country is Paris in?")
    assert two is not None
    assert two.subject == "Paris"
    assert two.relation == "located_in_country"
    assert two.object is None

    three = normalize_query("What continent is France part of?")
    assert three is not None
    assert three.subject == "France"
    assert three.relation == "part_of"
    assert three.object is None

    four = normalize_query("Is Paris a city?")
    assert four is not None
    assert four.subject == "Paris"
    assert four.relation == "instance_of"
    assert four.object == "City"

    five = normalize_query("Is France a country?")
    assert five is not None
    assert five.subject == "France"
    assert five.relation == "instance_of"
    assert five.object == "Country"


def test_query_normalizer_near_matches_fail() -> None:
    assert normalize_query("What is capital of France?") is None
    assert normalize_query("What is the capital for France?") is None
    assert normalize_query("What continent is France in?") is None
    assert normalize_query("Is Paris city?") is None
    assert normalize_query("Tell me about France") is None


def test_ask_uses_normalizer_for_capital_and_falls_back_for_non_pattern() -> None:
    capital = run_cli("ask", "What is the capital of France?", "--pack", "general_world")
    assert capital.returncode == 0
    assert "Paris is the capital of France" in capital.stdout
    assert "has_capital" not in capital.stdout

    fallback = run_cli("ask", "Tell me about France")
    assert fallback.returncode == 0
    assert fallback.stdout.strip() == "No result."


def test_query_normalizer_no_false_positive() -> None:
    assert normalize_query("What is the capital of?") is None
    assert normalize_query("Is a country?") is None


def test_socrates_rendering_still_human_readable() -> None:
    result = run_cli("ask", "All men are mortal. Socrates is a man. Can Socrates die?")
    assert result.returncode == 0
    assert "Socrates is mortal" in result.stdout
