"""S3-62: Formal verification regression test for KPOL v0.2 Fail-Closed Transaction Gate."""
import csv
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).with_name("run_s3_formal.py")

pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("yosys", "yosys-abc", "yosys-smtbmc", "z3")),
    reason="yosys, yosys-abc, yosys-smtbmc and z3 are required",
)


def test_s3_formal_not_refuted_and_mutants_detected(tmp_path):
    env = dict(os.environ, S3_OUT_DIR=str(tmp_path))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--bmc-depth", "4", "--cover-depth", "4"],
        env=env, capture_output=True, text=True, timeout=300,
    )
    assert "VERDICT: NOT_REFUTED" in result.stdout, result.stdout + result.stderr
    with open(tmp_path / "s3_results.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    pdr = {r["design"].split(":")[0].strip(): r["status"] for r in rows if r["engine"] == "abc pdr"}
    assert pdr == {
        "original (kpol_txn_gate_v2)": "PASSED",
        "M_hazard_bypass": "FAILED",
        "M_inv_bypass": "FAILED",
        "M_state_leak": "FAILED",
        "M_f03_strobe": "FAILED",
    }

    cover_row = next(r for r in rows if "cover" in r["engine"])
    assert cover_row["status"] == "PASSED"
    reached = [c.strip() for c in cover_row["reached"].replace("[", "").replace("]", "").replace("'", "").split(",") if c.strip()]
    assert set(reached) == {
        "C1_commit",
        "C2_reject_hazard",
        "C3_reject_inv",
        "C4_reject_input",
        "C5_alert_observed",
        "C6_state_changed",
    }
