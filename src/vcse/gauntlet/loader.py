"""Gauntlet JSONL loader."""

from __future__ import annotations

import json
from pathlib import Path

from vcse.gauntlet.case import GauntletCase
from vcse.gauntlet.errors import GauntletError


def load_gauntlet_cases(path_like: str | Path) -> list[GauntletCase]:
    path = Path(path_like)
    if not path.exists():
        raise GauntletError("FILE_ERROR", f"Path not found: {path}")

    files: list[Path]
    if path.is_dir():
        files = sorted(path.glob("*.jsonl"))
        if not files:
            raise GauntletError("FILE_ERROR", f"No .jsonl files found in {path}")
    else:
        if path.suffix.lower() != ".jsonl":
            raise GauntletError("UNSUPPORTED_FORMAT", "Gauntlet only supports .jsonl")
        files = [path]

    seen_ids: set[str] = set()
    cases: list[GauntletCase] = []
    for file in files:
        lines = _read_lines(file)
        for line_num, line in enumerate(lines, start=1):
            if not line.strip():
                raise GauntletError(
                    "MALFORMED_JSONL",
                    f"{file}:{line_num}: blank lines are not allowed",
                )
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise GauntletError(
                    "MALFORMED_JSONL",
                    f"{file}:{line_num}: {exc.msg}",
                ) from exc
            case = GauntletCase.from_dict(payload, f"{file}:{line_num}")
            if case.id in seen_ids:
                raise GauntletError("INVALID_CASE", f"Duplicate case id: {case.id}")
            seen_ids.add(case.id)
            cases.append(case)
    return cases


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text().splitlines()
    except OSError as exc:
        raise GauntletError("FILE_ERROR", str(exc)) from exc
