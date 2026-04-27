from __future__ import annotations

import argparse
import json
from pathlib import Path

from vcse.benchmark import format_benchmark_text, run_benchmark


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    summary = run_benchmark(Path(args.path))
    if args.json_output:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(format_benchmark_text(summary))


if __name__ == "__main__":
    main()
