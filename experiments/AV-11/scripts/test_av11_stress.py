import pytest
from pathlib import Path
from analyze_av11 import process_lac

def test_av11_axi_stress_immunity():
    base_dir = Path(__file__).resolve().parent.parent
    raw_dir = base_dir / "raw"

    quiet_lac = raw_dir / "av11_ps_quiet_run01.lac"
    stressed_lac = raw_dir / "av11_ps_stressed_run02.lac"

    assert quiet_lac.exists(), f"Missing {quiet_lac}"
    assert stressed_lac.exists(), f"Missing {stressed_lac}"

    q_csv_raw = raw_dir / "av11_ps_quiet_run01.csv"
    q_csv_ev = raw_dir / "av11_ps_quiet_run01_events.csv"
    s_csv_raw = raw_dir / "av11_ps_stressed_run02.csv"
    s_csv_ev = raw_dir / "av11_ps_stressed_run02_events.csv"

    stats_q = process_lac(quiet_lac, q_csv_raw, q_csv_ev)
    stats_s = process_lac(stressed_lac, s_csv_raw, s_csv_ev)

    assert stats_q["n"] == 100
    assert stats_s["n"] == 100

    # Falsification check: p99 must be <= 60.0 ns in both runs
    assert stats_q["p99_ns"] <= 60.0
    assert stats_s["p99_ns"] <= 60.0

    # Stress impact check: p99 under stress must not exceed 20.0 ns
    assert stats_s["p99_ns"] == 20.0
    assert stats_s["max_ns"] <= 20.0
