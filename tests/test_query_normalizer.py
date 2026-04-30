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

    six = normalize_query("What currency does France use?")
    assert six is not None
    assert six.subject == "France"
    assert six.relation == "uses_currency"
    assert six.object is None

    seven = normalize_query("What language is spoken in Germany?")
    assert seven is not None
    assert seven.subject == "Germany"
    assert seven.relation == "language_of"
    assert seven.object is None

    eight = normalize_query("What is the country code of Japan?")
    assert eight is not None
    assert eight.subject == "Japan"
    assert eight.relation == "has_country_code"
    assert eight.object is None

    nine = normalize_query("What region is Brazil in?")
    assert nine is not None
    assert nine.subject == "Brazil"
    assert nine.relation == "located_in_region"
    assert nine.object is None

    ten = normalize_query("What subregion is Germany in?")
    assert ten is not None
    assert ten.subject == "Germany"
    assert ten.relation == "located_in_subregion"
    assert ten.object is None


def test_query_normalizer_near_matches_fail() -> None:
    assert normalize_query("What is capital of France?") is None
    assert normalize_query("What is the capital for France?") is None
    assert normalize_query("What continent is France in?") is None
    assert normalize_query("Is Paris city?") is None
    assert normalize_query("Tell me about France") is None
    assert normalize_query("Tell me the currency of France") is None
    assert normalize_query("Currency France?") is None
    assert normalize_query("What money does France use?") is None


def test_ask_uses_normalizer_for_capital_and_falls_back_for_non_pattern() -> None:
    capital = run_cli("ask", "What is the capital of France?", "--pack", "general_world")
    assert capital.returncode == 0
    assert capital.stdout.strip() == "Paris is the capital of France."
    assert "has_capital" not in capital.stdout

    fallback = run_cli("ask", "Tell me about France")
    assert fallback.returncode == 0
    assert fallback.stdout.strip() == "No result."


def test_query_normalizer_no_false_positive() -> None:
    assert normalize_query("What is the capital of?") is None
    assert normalize_query("Is a country?") is None


def test_query_normalizer_language_plural_pattern() -> None:
    parsed = normalize_query("What languages are spoken in Germany?")
    assert parsed is not None
    assert parsed.subject == "Germany"
    assert parsed.relation == "language_of"


def test_socrates_rendering_still_human_readable() -> None:
    result = run_cli("ask", "All men are mortal. Socrates is a man. Can Socrates die?")
    assert result.returncode == 0
    assert "Socrates is mortal" in result.stdout


def test_fact_question_omits_yes_prefix() -> None:
    result = run_cli("ask", "What is the capital of France?", "--pack", "general_world")
    assert result.returncode == 0
    assert result.stdout.strip() == "Paris is the capital of France."
    assert "Yes —" not in result.stdout


def test_boolean_question_keeps_yes_prefix() -> None:
    result = run_cli("ask", "Is Paris the capital of France?", "--pack", "general_world")
    assert result.returncode == 0
    assert "Yes —" in result.stdout


def test_ask_uses_normalizer_for_new_fact_patterns() -> None:
    currency = run_cli("ask", "What currency does France use?", "--pack", "general_world")
    assert currency.returncode == 0
    assert currency.stdout.strip() == "France uses the Euro."

    language = run_cli("ask", "What language is spoken in Germany?", "--pack", "general_world")
    assert language.returncode == 0
    assert language.stdout.strip() == "German is a language of Germany."

    code = run_cli("ask", "What is the country code of Japan?", "--pack", "general_world")
    assert code.returncode == 0
    assert code.stdout.strip() == "Japan has country code JP."

    region = run_cli("ask", "What region is Brazil in?", "--pack", "general_world")
    assert region.returncode == 0
    assert region.stdout.strip() == "Brazil is in the Americas region."

    subregion = run_cli("ask", "What subregion is Germany in?", "--pack", "general_world")
    assert subregion.returncode == 0
    assert subregion.stdout.strip() == "Germany is in the Western Europe subregion."
