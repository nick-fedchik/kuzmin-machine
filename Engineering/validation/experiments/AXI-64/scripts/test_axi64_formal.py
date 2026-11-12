"""Reruns the AXI-64 formal check at reduced BMC depth into a temporary directory."""
import csv
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).with_name("run_axi64_formal.py")

pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("yosys", "yosys-abc", "yosys-smtbmc", "z3")),
    reason="yosys, yosys-abc, yosys-smtbmc and z3 are required",
)


def test_generated_slave_not_refuted_and_mutants_detected(tmp_path):
    env = dict(os.environ, AXI64_OUT_DIR=str(tmp_path))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--bmc-depth", "3", "--cover-depth", "6"],
        env=env, capture_output=True, text=True, timeout=600,
    )
    assert "AXI-64 VERDICT: NOT_REFUTED" in result.stdout, result.stdout + result.stderr
    with open(tmp_path / "axi64_results.csv") as f:
        rows = list(csv.DictReader(f))
    pdr = {r["design"].split(":")[0]: r["status"] for r in rows if r["engine"] == "abc pdr"}
    assert pdr == {"original": "PASSED", "M_noaw": "FAILED", "M_araddr": "FAILED",
                   "M_nostrb": "FAILED", "M_bdrop": "FAILED"}
