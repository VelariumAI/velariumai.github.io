import json
from pathlib import Path


def test_general_world_pack_files_and_metadata() -> None:
    root = Path(__file__).resolve().parents[1]
    pack_dir = root / "examples" / "packs" / "general_world"

    assert (pack_dir / "pack.json").exists()
    assert (pack_dir / "claims.jsonl").exists()
    assert (pack_dir / "provenance.jsonl").exists()
    assert (pack_dir / "metrics.json").exists()

    pack = json.loads((pack_dir / "pack.json").read_text())
    assert pack["id"] == "general_world"
    assert pack["version"] == "1.0.0"
    assert pack["domain"] == "general"
    assert pack["lifecycle_status"] == "candidate"

    claims = [json.loads(line) for line in (pack_dir / "claims.jsonl").read_text().splitlines() if line.strip()]
    assert len(claims) >= 100
    assert all("subject" in row and "relation" in row and "object" in row for row in claims)

    metrics = json.loads((pack_dir / "metrics.json").read_text())
    assert metrics["claim_count"] == len(claims)
