"""Tests for compression CLI commands."""

import json
from pathlib import Path


def test_compress_pack_command(tmp_path):
    """vcse compress pack <path> --output <dir>"""
    output = tmp_path / "compressed"
    import subprocess
    result = subprocess.run(
        ["python", "-m", "vcse.cli", "compress", "pack", "examples/packs/logic_basic", "--output", str(output)],
        capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert (output / "pack.json").exists()
    assert (output / "intern_table.json").exists()
    assert (output / "encoded_claims.jsonl").exists()


def test_decompress_pack_command(tmp_path):
    """vcse decompress pack <path> --output <dir>"""
    compress_out = tmp_path / "compressed"
    decompress_out = tmp_path / "decompressed"

    import subprocess
    subprocess.run(
        ["python", "-m", "vcse.cli", "compress", "pack", "examples/packs/logic_basic", "--output", str(compress_out)],
        capture_output=True
    )
    result = subprocess.run(
        ["python", "-m", "vcse.cli", "decompress", "pack", str(compress_out), "--output", str(decompress_out)],
        capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert (decompress_out / "original_claims.jsonl").exists()


def test_compress_stats_command(tmp_path):
    """vcse compress stats <compressed_dir>"""
    compress_out = tmp_path / "compressed"
    import subprocess
    subprocess.run(
        ["python", "-m", "vcse.cli", "compress", "pack", "examples/packs/logic_basic", "--output", str(compress_out)],
        capture_output=True
    )
    result = subprocess.run(
        ["python", "-m", "vcse.cli", "compress", "stats", str(compress_out)],
        capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "Original claims" in result.stdout or "original_claims" in result.stdout


def test_decompress_verify_command(tmp_path):
    """vcse decompress verify <compressed_dir>"""
    compress_out = tmp_path / "compressed"
    import subprocess
    subprocess.run(
        ["python", "-m", "vcse.cli", "compress", "pack", "examples/packs/logic_basic", "--output", str(compress_out)],
        capture_output=True
    )
    result = subprocess.run(
        ["python", "-m", "vcse.cli", "decompress", "verify", str(compress_out)],
        capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "VALID" in result.stdout


def test_compress_invalid_path():
    """Compress fails cleanly on invalid input."""
    import subprocess
    result = subprocess.run(
        ["python", "-m", "vcse.cli", "compress", "pack", "nonexistent_pack_xyz", "--output", "/tmp/out"],
        capture_output=True, text=True
    )
    assert result.returncode != 0


def test_decompress_invalid_path():
    """Decompress fails cleanly on invalid input."""
    import subprocess
    result = subprocess.run(
        ["python", "-m", "vcse.cli", "decompress", "pack", "nonexistent_compressed_xyz", "--output", "/tmp/out"],
        capture_output=True, text=True
    )
    assert result.returncode != 0