import pytest
import subprocess
import sys
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


def test_existing_event_export_is_not_overwritten(tmp_path):
    lac_file = Path(__file__).resolve().parent.parent / "raw/av10_pynq_100burst_run03.lac"
    output = tmp_path / "events.csv"
    output.write_text("preserved export\n")
    with pytest.raises(FileExistsError):
        analyze_capture(lac_file, output)
    assert output.read_text() == "preserved export\n"


def test_cli_uses_new_export_directory_without_overwrite(tmp_path):
    script = Path(__file__).with_name("analyze_av10_burst.py")
    output = tmp_path / "derived"
    command = [sys.executable, str(script), "--output-dir", str(output)]
    first = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    before = {path.name: path.read_bytes() for path in output.glob("*.csv")}
    assert len(before) == 1
    second = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert second.returncode != 0
    assert {path.name: path.read_bytes() for path in output.glob("*.csv")} == before
