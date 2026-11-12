"""S4-07: Regression test for two programs running on single bitstream via BRAM."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "raw"


def test_s4_hil_results_and_bitstream_hash():
    results_path = RAW / "s4_hil_results.json"
    assert results_path.exists(), "s4_hil_results.json not found"
    data = json.loads(results_path.read_text(encoding="utf-8"))

    assert data["verdict"] == "NOT_REFUTED"
    assert data["image_a"]["states"] == [11, 11]
    assert data["image_a"]["counts"] == [2, 1, 1]
    assert data["image_b"]["states"] == [9, 9]
    assert data["image_b"]["counts"] == [4, 2, 2]

    # Verify bitstream hash matches recorded sha256 file
    sha_file = RAW / "bitstream.sha256"
    assert sha_file.exists(), "bitstream.sha256 not found"
    expected_hash = sha_file.read_text(encoding="utf-8").split()[0]
    assert data["bitstream_sha256"] == expected_hash

    # Verify two different program images were used
    assert data["image_sha256"][0] != data["image_sha256"][1]
