from pathlib import Path

from vcse.ledger.merkle import pack_integrity_report


def test_merkle_root_changes_when_artifact_changes(tmp_path: Path) -> None:
    (tmp_path / "pack.json").write_text('{"id":"p"}')
    (tmp_path / "claims.jsonl").write_text('{"subject":"a","relation":"is_a","object":"b"}\n')
    report1 = pack_integrity_report(tmp_path, ["pack.json", "claims.jsonl"])

    (tmp_path / "claims.jsonl").write_text('{"subject":"a","relation":"is_a","object":"c"}\n')
    report2 = pack_integrity_report(tmp_path, ["pack.json", "claims.jsonl"])

    assert report1.merkle_root != report2.merkle_root
