import pytest
from pathlib import Path
from analyze_av10_burst import analyze_capture

def test_av10_run03_statistical_latency():
    base_dir = Path(__file__).resolve().parent.parent
    lac_file = base_dir / "raw" / "av10_pynq_100burst_run03.lac"
    assert lac_file.exists(), f"Raw capture file {lac_file} must exist"

    stats, events = analyze_capture(lac_file)
    assert stats["n"] == 100, f"Expected 100 events, got {stats['n']}"
    assert stats["min_ns"] >= 10.0
    assert stats["max_ns"] <= 20.0
    assert stats["p99_ns"] <= 60.0, f"Falsification threshold violated: p99={stats['p99_ns']} > 60.0 ns"
    assert stats["mean_ns"] < 25.0
