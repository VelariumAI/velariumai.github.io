# CI

VCSE uses a deterministic offline-safe GitHub Actions CI pipeline.

## What CI Runs

- Matrix test job on Python `3.11` and `3.12` (Ubuntu)
- Full test suite: `python -m pytest -q`
- Acceptance checks:
  - `python -m vcse.cli ask "What is the capital of France?" --pack general_world`
  - `python -m vcse.cli ask "What currency does France use?" --pack general_world`
  - `python -m vcse.cli benchmark coverage --pack general_world --json`
  - `python -m vcse.cli pack verify examples/packs/general_world`
  - `python -m vcse.cli pack hash examples/packs/general_world`
  - `python -m vcse.cli gauntlet benchmarks/gauntlet/ --search mcts --ts3 --index`
- Fast smoke job on Python `3.11`:
  - install/import/CLI sanity checks

## Security and Permissions

- Workflow permissions are least-privilege: `contents: read`
- No secrets required
- No `pull_request_target`
- Concurrency enabled to cancel redundant runs

## Offline Policy

Standard CI must be offline-safe:

- Tests use committed fixtures and local packs
- No live dataset/API fetches
- Network-dependent behavior is not part of required CI path

## Failure Artifacts

On failure, CI uploads diagnostic artifacts when present:

- `coverage-result.json`
- `gauntlet-result.txt`
- `coverage.xml`
- `/tmp/cake_report.json`
- `.pytest_cache`

## Reproducing CI Locally

Run from repository root:

```bash
python -m pytest -q
python -m vcse.cli benchmark coverage --pack general_world --json
python -m vcse.cli gauntlet benchmarks/gauntlet/ --search mcts --ts3 --index
```
