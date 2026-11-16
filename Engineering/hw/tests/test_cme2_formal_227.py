import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FORMAL_DIR = REPO_ROOT / "Engineering" / "validation" / "kpol-cme" / "cme2-formal-227"
SCRIPT_PATH = FORMAL_DIR / "scripts" / "run_cme2_formal.py"
PROPS_PATH = FORMAL_DIR / "scripts" / "cme2_formal_props.sv"
RAW_DIR = FORMAL_DIR / "raw"
N16_SCRIPT_PATH = FORMAL_DIR / "scripts" / "run_cme2_formal_n16.py"
N16_PROPS_PATH = FORMAL_DIR / "scripts" / "cme2_formal_n16_props.sv"
N16_RAW_DIR = RAW_DIR / "n16_compositional"
RTL_DIR = REPO_ROOT / "Engineering" / "hw" / "rtl" / "core"


def test_cme2_formal_227_committed_artifacts():
    prov_path = RAW_DIR / "cme2_provenance.json"
    csv_path = RAW_DIR / "cme2_results.csv"
    assert prov_path.is_file()
    assert csv_path.is_file()

    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    assert prov["issue"] == 227
    assert prov["verdict"] == "PASSED"
    assert prov["parameters"] == {
        "NUM_CONCEPTS": 4,
        "QUEUE_DEPTH": 4,
        "DATA_WIDTH": 32,
        "ADDR_WIDTH": 4,
    }

    for fname in (
        "kpol_txn_gate_v2.sv",
        "km_concept_micro_engine.sv",
        "km_concept_bram.sv",
        "km_autonomous_sequencer.sv",
    ):
        actual = hashlib.sha256((RTL_DIR / fname).read_bytes()).hexdigest()
        assert prov["sha256"][fname] == actual, f"SHA-256 mismatch for {fname}"

    assert prov["sha256"]["cme2_formal_props.sv"] == hashlib.sha256(
        PROPS_PATH.read_bytes()
    ).hexdigest()

    with csv_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_check = {r["check"]: r for r in rows}
    for req_check in ("P1_safety_ind", "P1_safety_bmc", "P2_P3_liveness_bmc", "cover_non_vacuity"):
        assert by_check[req_check]["status"] == "PASSED"

    reached = set(by_check["cover_non_vacuity"]["reached"].split(";"))
    assert {"C1_cascade_3_commits", "C2_reject_reached", "C3_commit_and_idle"} <= reached

    by_design_prefix = {r["design"].split(":")[0]: r for r in rows}
    expected_mutants = {
        "M1_we_on_reject": "P1a_no_we_on_reject",
        "M2_cascade_on_reject": "P1e_idle_after_isolated_reject",
        "M3_cyclic_cascade": "P2_bounded_termination",
    }
    for mid, expected_prop in expected_mutants.items():
        row = by_design_prefix[mid]
        assert row["status"] == "FAILED"
        assert expected_prop in row["failed"]
        assert row["vcd"]
        assert (RAW_DIR / row["vcd"]).is_file()

    for log_file in RAW_DIR.glob("*.log"):
        lines = log_file.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("# cmd: "), f"Missing # cmd header in {log_file.name}"
        assert lines[1].startswith("# timestamp: "), f"Missing # timestamp header in {log_file.name}"


@pytest.mark.skipif(
    shutil.which("yosys") is None
    or shutil.which("yosys-smtbmc") is None
    or shutil.which("z3") is None,
    reason="Потрібні yosys, yosys-smtbmc і z3",
)
def test_cme2_formal_227_live_safety_and_mutants(tmp_path):
    res = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--out-dir", str(tmp_path), "--skip-liveness"],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "VERDICT: PASSED" in res.stdout

    prov = json.loads((tmp_path / "cme2_provenance.json").read_text(encoding="utf-8"))
    assert prov["verdict"] == "PASSED"
    statuses = {r["design"].split(":")[0] + ":" + r["check"]: r["status"] for r in prov["rows"]}
    assert statuses["original (CFG-P):P1_safety_ind"] == "PASSED"
    assert statuses["original (CFG-P):P1_safety_bmc"] == "PASSED"
    assert statuses["original (CFG-P):cover_non_vacuity"] == "PASSED"
    assert statuses["M1_we_on_reject:safety_bmc"] == "FAILED"
    assert statuses["M2_cascade_on_reject:safety_bmc"] == "FAILED"
    assert (tmp_path / "M1_we_on_reject.vcd").is_file()
    assert (tmp_path / "M2_cascade_on_reject.vcd").is_file()


def test_cme2_formal_n16_committed_artifacts():
    prov_path = N16_RAW_DIR / "cme2_n16_provenance.json"
    csv_path = N16_RAW_DIR / "cme2_n16_results.csv"
    assert prov_path.is_file()
    assert csv_path.is_file()

    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    assert set(prov["issues"]) >= {237, 242}
    assert prov["verdict"] == "PASSED"
    assert prov["parameters"] == {
        "NUM_CONCEPTS": 16,
        "QUEUE_DEPTH": 16,
        "DATA_WIDTH": 32,
        "ADDR_WIDTH": 6,
    }

    for fname in (
        "kpol_txn_gate_v2.sv",
        "km_concept_micro_engine.sv",
        "km_concept_bram.sv",
        "km_autonomous_sequencer.sv",
    ):
        actual = hashlib.sha256((RTL_DIR / fname).read_bytes()).hexdigest()
        assert prov["sha256"][fname] == actual, f"SHA-256 mismatch for {fname}"

    assert prov["sha256"]["cme2_formal_n16_props.sv"] == hashlib.sha256(
        N16_PROPS_PATH.read_bytes()
    ).hexdigest()

    with csv_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_check = {r["check"]: r for r in rows}
    for req_check in ("P1_n16_ind", "P2_rank_step_n16", "P3_liveness_n16_ind", "cover_n16"):
        assert by_check[req_check]["status"] == "PASSED"

    reached = set(by_check["cover_n16"]["reached"].split(";"))
    assert {
        "C1_n16_cascade_4_commits",
        "C2_n16_reject_reached",
        "C3_n16_two_ext_triggers",
    } <= reached

    by_design_prefix = {r["design"].split(":")[0]: r for r in rows}
    expected_mutants = {
        "M_bigdot_dual_pulse": "P_bigdot_mutex_pulse",
        "M_we_on_reject": "P1a_no_we_on_reject",
        "M_cascade_on_reject": "P1d_no_cascade_on_reject",
        "M_rank_violation_self_sub": "P2_rank_step_n16",
    }
    for mid, expected_prop in expected_mutants.items():
        row = by_design_prefix[mid]
        assert row["status"] == "FAILED"
        assert expected_prop in row["failed"]
        assert row["vcd"]
        assert (N16_RAW_DIR / row["vcd"]).is_file()

    for log_file in N16_RAW_DIR.glob("*.log"):
        lines = log_file.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("# cmd: "), f"Missing # cmd header in {log_file.name}"
        assert lines[1].startswith("# timestamp: "), f"Missing # timestamp header in {log_file.name}"


@pytest.mark.skipif(
    shutil.which("yosys") is None
    or shutil.which("yosys-smtbmc") is None
    or shutil.which("z3") is None,
    reason="Потрібні yosys, yosys-smtbmc і z3",
)
def test_cme2_formal_n16_live_induction_and_mutants(tmp_path):
    res = subprocess.run(
        [sys.executable, str(N16_SCRIPT_PATH), "--out-dir", str(tmp_path), "--fast"],
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "VERDICT: PASSED" in res.stdout

    prov = json.loads((tmp_path / "cme2_n16_provenance.json").read_text(encoding="utf-8"))
    assert prov["verdict"] == "PASSED"
    statuses = {r["design"].split(":")[0] + ":" + r["check"]: r["status"] for r in prov["rows"]}
    assert statuses["original (CFG-P N=16):P1_n16_ind"] == "PASSED"
    assert statuses["original (CFG-P N=16):P2_rank_step_n16"] == "PASSED"
    for mid, check_name in (
        ("M_bigdot_dual_pulse", "safety_bmc"),
        ("M_we_on_reject", "safety_bmc"),
        ("M_cascade_on_reject", "safety_bmc"),
        ("M_rank_violation_self_sub", "rank_step_bmc"),
    ):
        assert statuses[f"{mid}:{check_name}"] == "FAILED"
        assert (tmp_path / f"{mid}.vcd").is_file()
