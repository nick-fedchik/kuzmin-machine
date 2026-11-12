"""
Tests for Raspberry Pi Pico Logic Analyzer Capture and VCD Exporter.
"""

import os
import tempfile
import importlib.util
from pathlib import Path
import pytest

PICO_DIR = Path(__file__).resolve().parents[1] / "boards/pynq-z1/pico/pico_capture.py"
spec = importlib.util.spec_from_file_location("pico_capture", PICO_DIR)
pico_capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pico_capture)

def test_mock_sample_generation():
    samples = pico_capture.generate_mock_capture_samples(sample_rate_hz=125_000_000, total_samples=100)
    assert len(samples) == 100
    assert any(s != 0 for s in samples)

def test_vcd_export():
    samples = pico_capture.generate_mock_capture_samples(sample_rate_hz=125_000_000, total_samples=50)
    with tempfile.NamedTemporaryFile(suffix=".vcd", delete=False) as tf:
        tmp_name = tf.name
    try:
        vcd_str = pico_capture.export_samples_to_vcd(samples, sample_rate_hz=125_000_000, output_path=tmp_name)
        assert "$scope module km_bench $end" in vcd_str
        assert "$var wire 1 ! EXT_STIMULUS $end" in vcd_str
        assert os.path.exists(tmp_name)
        assert os.path.getsize(tmp_name) > 0
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)

def test_latency_measurement():
    samples = pico_capture.generate_mock_capture_samples(sample_rate_hz=125_000_000, total_samples=100)
    res = pico_capture.analyze_capture_latency(samples, sample_rate_hz=125_000_000, trigger_ch=1, response_ch=2)
    assert res["success"] is True
    # 80 ns execution + 20 ns CDC = ~100 ns measured latency (within 1 sample resolution 8 ns)
    assert 90.0 <= res["measured_latency_ns"] <= 110.0
