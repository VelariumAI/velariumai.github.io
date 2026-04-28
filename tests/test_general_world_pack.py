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
    assert len(claims) >= 5000
    assert all("subject" in row and "relation" in row and "object" in row for row in claims)
    assert all(isinstance(row.get("provenance"), dict) for row in claims)
    keys = {(row["subject"], row["relation"], row["object"]) for row in claims}
    assert len(keys) == len(claims)

    metrics = json.loads((pack_dir / "metrics.json").read_text())
    if "claim_count" in metrics:
        assert metrics["claim_count"] == len(claims)
