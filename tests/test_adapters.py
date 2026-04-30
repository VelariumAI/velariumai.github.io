import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from vcse.adapters.csv_adapter import CSVAdapter
from vcse.adapters.json_adapter import JSONAdapter
from vcse.adapters.jsonl_adapter import JSONLAdapter
from vcse.adapters.registry import get_adapter


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-m", "vcse.cli", *args], capture_output=True, env=env, text=True)


def test_json_adapter_loads_correctly(tmp_path: Path) -> None:
    source = tmp_path / "in.json"
    _write_json(source, [{"id": "x", "name": " France "}])
    out = JSONAdapter().run(source)
    assert out == [{"id": "x", "name": "France"}]


def test_jsonl_adapter_loads_correctly(tmp_path: Path) -> None:
    source = tmp_path / "in.jsonl"
    _write_jsonl(source, [{"name": " Spain "}])
    out = JSONLAdapter().run(source)
    assert out == [{"id": "row_1", "name": "Spain"}]


def test_csv_adapter_loads_correctly(tmp_path: Path) -> None:
    source = tmp_path / "in.csv"
    _write_csv(source, ["country", "capital"], [[" France ", " Paris "]])
    out = CSVAdapter().run(source)
    assert out == [{"id": "row_1", "country": "France", "capital": "Paris"}]


def test_id_generation_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "in.json"
    _write_json(source, [{"name": "A"}, {"name": "B"}])
    out = JSONAdapter().run(source)
    assert [row["id"] for row in out] == ["row_1", "row_2"]


def test_empty_values_normalized_to_none(tmp_path: Path) -> None:
    source = tmp_path / "in.json"
    _write_json(source, [{"id": "x", "name": "   ", "langs": ["English", "  "]}])
    out = JSONAdapter().run(source)
    assert out[0]["name"] is None
    assert out[0]["langs"] == ["English", None]


def test_adapter_output_stable_across_runs(tmp_path: Path) -> None:
    source = tmp_path / "in.json"
    _write_json(source, [{"name": "France"}, {"name": "Spain"}])
    a = JSONAdapter().run(source)
    b = JSONAdapter().run(source)
    assert a == b


def test_adapter_does_not_alter_values_semantically(tmp_path: Path) -> None:
    source = tmp_path / "in.json"
    _write_json(source, [{"id": "x", "name": "Türkiye", "code": "TR", "count": 5}])
    out = JSONAdapter().run(source)
    assert out[0]["name"] == "Türkiye"
    assert out[0]["code"] == "TR"
    assert out[0]["count"] == 5


def test_registry_returns_correct_adapter() -> None:
    assert isinstance(get_adapter("json"), JSONAdapter)
    assert isinstance(get_adapter("jsonl"), JSONLAdapter)
    assert isinstance(get_adapter("csv"), CSVAdapter)


def test_invalid_adapter_type_fails() -> None:
    with pytest.raises(ValueError, match="UNKNOWN_ADAPTER"):
        get_adapter("yaml")


def test_cli_adapter_run_works(tmp_path: Path) -> None:
    source = tmp_path / "in.json"
    output = tmp_path / "out.jsonl"
    _write_json(source, [{"name": "France"}])

    result = run_cli("adapter", "run", "--type", "json", "--source", str(source), "--output", str(output), "--json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ADAPTER_RUN_COMPLETE"
    assert payload["record_count"] == 1
    line = output.read_text().strip()
    assert json.loads(line)["id"] == "row_1"


def test_cli_adapter_inspect_works(tmp_path: Path) -> None:
    source = tmp_path / "in.json"
    _write_json(source, [{"name": "France"}, {"name": "Spain"}])

    result = run_cli("adapter", "inspect", "--type", "json", "--source", str(source), "--json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ADAPTER_INSPECT"
    assert payload["record_count"] == 2
    assert len(payload["sample_records"]) == 2
