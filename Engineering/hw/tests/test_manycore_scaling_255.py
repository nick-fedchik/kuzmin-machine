"""Automated verification suite for Issue #255: CFG-P Many-Core Scaling (N = 1, 2, 4, 8).

Evidence classes covered (honestly labeled per AGENTS.md §4.2 — NOT physical board HIL):
  1. Immutability of base single-core CFG-P RTL files.
  2. Clean Verilator `-Wall` static lint on `km_event_crossbar.sv` and `km_manycore_cluster.sv`
     across `NUM_CORES = 1, 2, 4, 8`.
  3. Recorded Z3 formal SMT proof artifacts on `N = 2` (`MC1_event_conservation`,
     `MC2_rr_fairness`, `MC3_dag_progress`, constructive `MC4_cyclic_deadlock_witness` with VCD,
     zero `assume` statements inside `FORMAL_INDUCTION`, and 3 mutants `M1..M3` with VCDs)
     + live Z3 `--fast` verification run.
  4. Recorded OpenXC7 (`Yosys 0.69` + `nextpnr-himbaechel` on `xc7z020clg400-1`) synthesis,
     Place & Route, and STA artifacts for `N = 1, 2, 4, 8` verifying `RAMB36E1 == N`,
     `PAD <= 125`, `SLICE_LUTX`, `SLICE_FFX`, `F_max(N)`, and analytical area fit.
  5. Recorded `iverilog` cycle-accurate traffic profiles (`local`, `uniform`, `hotspot`,
     `many-to-one`, >= 1,000 primary events each) for `N = 4` and `N = 8` + live `iverilog`
     simulation and negative crossbar mutant control (`AGENTS.md §4.1`).
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
HW_DIR = HERE.parent
REPO_ROOT = HW_DIR.parent.parent
RTL_CORE = HW_DIR / "rtl" / "core"
RTL_BUS = HW_DIR / "rtl" / "bus"
RTL_CLUSTER = HW_DIR / "rtl" / "cluster"

WP_DIR = REPO_ROOT / "Engineering" / "validation" / "kpol-cme" / "manycore-scaling-255"
SCRIPTS_DIR = WP_DIR / "scripts"
RAW_DIR = WP_DIR / "raw"
CME2_PROV_PATH = (
    REPO_ROOT / "Engineering" / "validation" / "kpol-cme" / "cme2-formal-227" / "raw" / "cme2_provenance.json"
)
EXPECTED_AXI_CFG_P_SHA256 = "99ccf4907785ad9e20509367ae1977fc64264cc73de4e34cc5cc71c55771a4e1"


def test_base_cfg_p_rtl_untouched():
    """Verifies zero byte modifications to single-core CFG-P baseline RTL files."""
    cme2_prov = json.loads(CME2_PROV_PATH.read_text(encoding="utf-8"))
    for fname in (
        "kpol_txn_gate_v2.sv",
        "km_concept_micro_engine.sv",
        "km_concept_bram.sv",
        "km_autonomous_sequencer.sv",
    ):
        actual = hashlib.sha256((RTL_CORE / fname).read_bytes()).hexdigest()
        assert actual == cme2_prov["sha256"][fname], f"Base CFG-P file {fname} was modified"

    axi_actual = hashlib.sha256((RTL_BUS / "kpol_bram_pipeline_axi.sv").read_bytes()).hexdigest()
    assert axi_actual == EXPECTED_AXI_CFG_P_SHA256, "Base kpol_bram_pipeline_axi.sv was modified"


@pytest.mark.skipif(shutil.which("verilator") is None, reason="Потрібен verilator")
def test_cluster_rtl_verilator_lint_all_scales(tmp_path):
    """Verifies Verilator -Wall passes cleanly on crossbar & cluster for N = 1, 2, 4, 8 and PIPELINE_STAGES = 1, 2."""
    env = {**os.environ, "TMPDIR": str(tmp_path)}
    for p_stages in (1, 2):
        for n in (1, 2, 4, 8):
            res_xbar = subprocess.run(
                [
                    "verilator",
                    "--lint-only",
                    "-Wall",
                    f"-GNUM_CORES={n}",
                    f"-GPIPELINE_STAGES={p_stages}",
                    "--top-module",
                    "km_event_crossbar",
                    str(RTL_CLUSTER / "km_event_crossbar.sv"),
                ],
                env=env,
                capture_output=True,
                text=True,
            )
            assert res_xbar.returncode == 0, f"Crossbar lint failed for N={n} P={p_stages}:\n{res_xbar.stderr}"

            res_clus = subprocess.run(
                [
                    "verilator",
                    "--lint-only",
                    "-Wall",
                    "-Wno-fatal",
                    f"-GNUM_CORES={n}",
                    f"-GPIPELINE_STAGES={p_stages}",
                    "--top-module",
                    "km_manycore_cluster",
                    str(RTL_CORE / "kpol_txn_gate_v2.sv"),
                    str(RTL_CORE / "km_concept_micro_engine.sv"),
                    str(RTL_CORE / "km_concept_bram.sv"),
                    str(RTL_CLUSTER / "km_event_crossbar.sv"),
                    str(RTL_CLUSTER / "km_manycore_cluster.sv"),
                ],
                env=env,
                capture_output=True,
                text=True,
            )
            assert res_clus.returncode == 0, res_clus.stderr
            assert "km_event_crossbar.sv" not in res_clus.stderr
            assert "km_manycore_cluster.sv" not in res_clus.stderr


def test_committed_formal_smt_n2_artifacts_and_no_vacuous_assumes():
    """Checks Z3 formal SMT proof artifacts for N=2 (1-stage & 2-stage), zero assumes in FORMAL_INDUCTION, MC4 VCD, and M1..M4."""
    prov_path = RAW_DIR / "manycore_formal_provenance.json"
    csv_path = RAW_DIR / "manycore_formal_results.csv"
    props_path = SCRIPTS_DIR / "manycore_formal_props.sv"

    assert prov_path.is_file()
    assert csv_path.is_file()

    # Guard: zero `assume` statements inside FORMAL_INDUCTION block
    props_src = props_path.read_text(encoding="utf-8")
    ind_block = props_src.split("`ifdef FORMAL_INDUCTION", 1)[1].split("`endif", 1)[0]
    for line in ind_block.splitlines():
        stripped = line.split("//", 1)[0].strip()
        assert "assume" not in stripped, f"Prohibited assume inside FORMAL_INDUCTION: {line}"

    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    assert prov["issue"] == 255
    assert prov["evidence_kind"] == "formal_smt_z3_verification"
    assert prov["verdict"] == "PASSED"
    assert prov["parameters"] == {
        "NUM_CORES": 2,
        "NUM_EXT_PORTS": 2,
        "QUEUE_DEPTH": 4,
        "NUM_CONCEPTS": 4,
        "DATA_WIDTH": 32,
        "ADDR_WIDTH": 4,
    }

    expected_files = {
        "kpol_txn_gate_v2.sv": RTL_CORE / "kpol_txn_gate_v2.sv",
        "km_concept_micro_engine.sv": RTL_CORE / "km_concept_micro_engine.sv",
        "km_concept_bram.sv": RTL_CORE / "km_concept_bram.sv",
        "km_event_crossbar.sv": RTL_CLUSTER / "km_event_crossbar.sv",
        "km_manycore_cluster.sv": RTL_CLUSTER / "km_manycore_cluster.sv",
        "manycore_formal_props.sv": props_path,
    }
    for fname, fpath in expected_files.items():
        assert prov["sha256"][fname] == hashlib.sha256(fpath.read_bytes()).hexdigest()

    with csv_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_check = {r["check"]: r for r in rows if r["design"].startswith("original")}
    for req in (
        "MC1_MC4_base_bmc",
        "MC1_MC4_safety_ind",
        "MC1_MC4_base_bmc_p2",
        "MC1_MC4_safety_ind_p2",
        "MC3_dag_progress_bmc",
        "MC3_dag_progress_bmc_p2",
        "MC4_cyclic_deadlock_witness",
        "cover_dag_and_contention",
        "cover_dag_and_contention_p2",
    ):
        assert by_check[req]["status"] == "PASSED"

    assert "MC4_cyclic_deadlock_witness" in by_check["MC4_cyclic_deadlock_witness"]["reached"]
    mc4_vcd = RAW_DIR / by_check["MC4_cyclic_deadlock_witness"]["vcd"]
    assert mc4_vcd.is_file() and mc4_vcd.stat().st_size > 0

    for cov_key in ("cover_dag_and_contention", "cover_dag_and_contention_p2"):
        c12_reached = set(by_check[cov_key]["reached"].split(";"))
        assert {"C1_interbank_cascade_to_idle", "C2_many_to_one_contention"} <= c12_reached

    by_mut = {r["design"].split(":")[0]: r for r in rows if not r["design"].startswith("original")}
    expected_mutants = {
        "M1_fixed_priority_starvation": "MC2_rr_fairness",
        "M2_drop_crossbar_backpressure": "MC1_event_conservation",
        "M3_duplicate_broadcast": "MC1_event_conservation",
        "M4_stage2_skid_overwrite": "MC1_event_conservation",
        "M5_multigroup_arbiter_fault": "MC1_event_conservation",
    }
    for mid, exp_prop in expected_mutants.items():
        r = by_mut[mid]
        assert r["status"] == "FAILED"
        assert exp_prop in r["failed"]
        vcd = RAW_DIR / r["vcd"]
        assert vcd.is_file() and vcd.stat().st_size > 0


@pytest.mark.skipif(
    shutil.which("yosys") is None or shutil.which("yosys-smtbmc") is None or shutil.which("z3") is None,
    reason="Потрібні yosys, yosys-smtbmc і z3",
)
def test_live_formal_smt_n2_induction_and_mutants(tmp_path):
    """Runs live Z3 k-induction (1-stage & 2-stage) + all 5 crossbar mutants in --fast mode."""
    env = {**os.environ, "TMPDIR": str(tmp_path)}
    res = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "run_manycore_formal.py"), "--out-dir", str(tmp_path), "--fast"],
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "VERDICT: PASSED" in res.stdout
    for mid in (
        "M1_fixed_priority_starvation",
        "M2_drop_crossbar_backpressure",
        "M3_duplicate_broadcast",
        "M4_stage2_skid_overwrite",
        "M5_multigroup_arbiter_fault",
    ):
        assert (tmp_path / f"{mid}.vcd").is_file()


def test_committed_openxc7_pnr_sta_artifacts_n1_n2_n4_n8():
    """Verifies OpenXC7 post-Place-&-Route and STA metrics for N = 1, 2, 4, 8 on xc7z020clg400-1."""
    sum_path = RAW_DIR / "manycore_pnr_summary.json"
    csv_path = RAW_DIR / "manycore_pnr_scaling.csv"
    assert sum_path.is_file()
    assert csv_path.is_file()

    summary = json.loads(sum_path.read_text(encoding="utf-8"))
    assert summary["evidence_kind"] == "openxc7_place_and_route_sta"
    assert summary["not_physical_hil"] is True
    assert summary["device"] == "xc7z020clg400-1"

    with csv_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert [int(r["num_cores"]) for r in rows] == [1, 2, 4, 8]

    prev_luts = 0
    prev_ffs = 0
    for r in rows:
        n = int(r["num_cores"])
        assert int(r["yosys_ramb36e1"]) == n
        assert int(r["pnr_ramb36e1"]) == n
        assert int(r["pnr_pads"]) <= 125

        luts = int(r["pnr_slice_lutx"])
        ffs = int(r["pnr_slice_ffx"])
        fmax = float(r["fmax_mhz"])
        assert luts > prev_luts
        assert ffs > prev_ffs
        assert 40.0 < fmax < 300.0
        prev_luts = luts
        prev_ffs = ffs

        rep_json = json.loads((RAW_DIR / f"nextpnr_report_n{n}.json").read_text(encoding="utf-8"))
        assert int(rep_json["utilization"]["RAMB36E1"]["used"]) == n
        assert int(rep_json["utilization"]["SLICE_LUTX"]["used"]) == luts
        assert int(rep_json["utilization"]["SLICE_FFX"]["used"]) == ffs

    # Issue #263: Verify 2-stage pipelined crossbar OpenXC7 P&R and STA artifacts for N = 2, 4, 8
    sum_p2_path = RAW_DIR / "manycore_pnr_summary_p2.json"
    csv_p2_path = RAW_DIR / "manycore_pnr_scaling_p2.csv"
    assert sum_p2_path.is_file()
    assert csv_p2_path.is_file()

    sum_p2 = json.loads(sum_p2_path.read_text(encoding="utf-8"))
    assert sum_p2["issue"] == 263
    assert sum_p2["pipeline_stages"] == 2
    assert sum_p2["evidence_kind"] == "openxc7_place_and_route_sta"
    assert sum_p2["not_physical_hil"] is True

    with csv_p2_path.open("r", encoding="utf-8") as f:
        rows_p2 = list(csv.DictReader(f))

    assert [int(r["num_cores"]) for r in rows_p2] == [2, 4, 8]
    by_n_p1 = {int(r["num_cores"]): r for r in rows}
    by_n_p2 = {int(r["num_cores"]): r for r in rows_p2}

    for n in (2, 4, 8):
        r1 = by_n_p1[n]
        r2 = by_n_p2[n]
        assert int(r2["pnr_ramb36e1"]) == n
        assert int(r2["pnr_pads"]) <= 125
        assert float(r2["fmax_mhz"]) > float(r1["fmax_mhz"])
        assert int(r2["pnr_slice_ffx"]) > int(r1["pnr_slice_ffx"])

        rep2_json = json.loads((RAW_DIR / f"nextpnr_report_p2_n{n}.json").read_text(encoding="utf-8"))
        assert int(rep2_json["utilization"]["RAMB36E1"]["used"]) == n
        assert int(rep2_json["utilization"]["SLICE_LUTX"]["used"]) == int(r2["pnr_slice_lutx"])
        assert int(rep2_json["utilization"]["SLICE_FFX"]["used"]) == int(r2["pnr_slice_ffx"])

    assert float(by_n_p2[2]["fmax_mhz"]) >= 100.0
    assert float(by_n_p2[4]["fmax_mhz"]) >= 100.0
    assert float(by_n_p2[8]["fmax_mhz"]) > 85.0


def test_committed_traffic_profiles_n4_n8_and_raw_log_headers():
    """Checks recorded N=4 and N=8 traffic profile results (1,000+ primary events) and raw log provenance."""
    sum_path = RAW_DIR / "manycore_traffic_summary.json"
    csv_path = RAW_DIR / "manycore_traffic_profiles.csv"
    assert sum_path.is_file()
    assert csv_path.is_file()

    summary = json.loads(sum_path.read_text(encoding="utf-8"))
    assert summary["evidence_kind"] == "rtl_simulation_iverilog"
    assert summary["not_physical_hil"] is True
    assert summary["events_per_profile"] >= 1000

    with csv_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_np = {(int(r["num_cores"]), r["profile"]): r for r in rows}
    for n in (4, 8):
        for prof in ("local", "uniform", "hotspot", "many-to-one"):
            r = by_np[(n, prof)]
            assert int(r["primary_events"]) >= 1000
            assert int(r["dropped_accepted_events"]) == 0
            assert int(r["w0_golden_mismatches"]) == 0
            assert float(r["throughput_mcps_at_100mhz"]) > 0.0
            assert float(r["avg_latency_cycles"]) >= 8.0
            assert int(r["max_latency_cycles"]) >= float(r["avg_latency_cycles"])

    # Scaling sanity checks (1-stage and 2-stage)
    mcps_local_4 = float(by_np[(4, "local")]["throughput_mcps_at_100mhz"])
    mcps_local_8 = float(by_np[(8, "local")]["throughput_mcps_at_100mhz"])
    assert mcps_local_4 > 45.0
    assert mcps_local_8 > 90.0
    assert int(by_np[(8, "many-to-one")]["backpressure_stalls"]) > 0

    sum_p2_path = RAW_DIR / "manycore_traffic_summary_p2.json"
    csv_p2_path = RAW_DIR / "manycore_traffic_profiles_p2.csv"
    assert sum_p2_path.is_file()
    assert csv_p2_path.is_file()
    sum_p2 = json.loads(sum_p2_path.read_text(encoding="utf-8"))
    assert sum_p2["issue"] == 263
    assert sum_p2["pipeline_stages"] == 2
    assert sum_p2["not_physical_hil"] is True

    with csv_p2_path.open("r", encoding="utf-8") as f:
        rows_p2 = list(csv.DictReader(f))
    by_np2 = {(int(r["num_cores"]), r["profile"]): r for r in rows_p2}
    for n in (4, 8):
        for prof in ("local", "uniform", "hotspot", "many-to-one"):
            r1 = by_np[(n, prof)]
            r2 = by_np2[(n, prof)]
            assert int(r2["primary_events"]) >= 1000
            assert int(r2["dropped_accepted_events"]) == 0
            assert int(r2["w0_golden_mismatches"]) == 0
            assert float(r2["throughput_mcps_at_fmax"]) > float(r1["throughput_mcps_at_fmax"])

    # Provenance header check on every raw/*.log
    log_files = list(RAW_DIR.glob("*.log"))
    assert len(log_files) >= 18
    for lf in log_files:
        lines = lf.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("# cmd: "), f"Missing # cmd header in {lf.name}"
        assert lines[1].startswith("# timestamp: "), f"Missing # timestamp header in {lf.name}"


@pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Потрібні iverilog і vvp",
)
def test_live_iverilog_cluster_tb_and_negative_drop_mutant(tmp_path):
    """Runs live Icarus Verilog simulation on N=4 (1-stage & 2-stage) AND proves negative mutants fail."""
    env = {**os.environ, "TMPDIR": str(tmp_path)}
    rtl_sources = [
        RTL_CORE / "kpol_txn_gate_v2.sv",
        RTL_CORE / "km_concept_micro_engine.sv",
        RTL_CORE / "km_concept_bram.sv",
        RTL_CLUSTER / "km_event_crossbar.sv",
        RTL_CLUSTER / "km_manycore_cluster.sv",
        HW_DIR / "tests" / "km_manycore_cluster_tb.sv",
    ]
    for p_stages in (1, 2):
        vvp_ok = tmp_path / f"cluster_ok_p{p_stages}.vvp"
        subprocess.run(
            [
                "iverilog",
                "-g2012",
                "-Pkm_manycore_cluster_tb.NUM_CORES=4",
                f"-Pkm_manycore_cluster_tb.PIPELINE_STAGES={p_stages}",
                "-s",
                "km_manycore_cluster_tb",
                "-o",
                str(vvp_ok),
                *map(str, rtl_sources),
            ],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        sum_json = tmp_path / f"live_n4_p{p_stages}.json"
        run_ok = subprocess.run(
            ["vvp", "-n", str(vvp_ok), "+events_per_profile=128", f"+summary_json={sum_json}"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert run_ok.returncode == 0, run_ok.stdout + run_ok.stderr
        assert "PASS: km_manycore_cluster_tb N=4 verified all 4 profiles" in run_ok.stdout
        live_data = json.loads(sum_json.read_text(encoding="utf-8"))
        assert live_data["total_errors"] == 0
        assert live_data["pipeline_stages"] == p_stages

    # Negative mutant control 1 (1-stage): ignoring dst_ready_i == 0 in crossbar must fail TB
    xbar_src = (RTL_CLUSTER / "km_event_crossbar.sv").read_text(encoding="utf-8")
    old_line = "            wire pipe_can_accept_w = !pipe_valid_q[gj] || dst_ready_i[gj];"
    assert xbar_src.count(old_line) == 1
    mut_xbar = tmp_path / "mut_xbar.sv"
    mut_xbar.write_text(
        xbar_src.replace(old_line, "            wire pipe_can_accept_w = 1'b1;"),
        encoding="utf-8",
    )
    mut_sources = [mut_xbar if p.name == "km_event_crossbar.sv" else p for p in rtl_sources]
    vvp_mut = tmp_path / "cluster_mut.vvp"
    subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-Pkm_manycore_cluster_tb.NUM_CORES=4",
            "-s",
            "km_manycore_cluster_tb",
            "-o",
            str(vvp_mut),
            *map(str, mut_sources),
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    run_mut = subprocess.run(
        ["vvp", "-n", str(vvp_mut), "+events_per_profile=128"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    combined = run_mut.stdout + run_mut.stderr
    assert run_mut.returncode != 0 or "[FAIL]" in combined
    assert "[FAIL]" in combined

    # Negative mutant control 2 (2-stage #263): breaking Stage 1 skid handshake must fail TB
    old_s1 = "            wire s1_can_accept_w   = !s1_valid_q[gj] || !pipe_valid_q[gj];"
    assert xbar_src.count(old_s1) == 1
    mut_s1_xbar = tmp_path / "mut_s1_xbar.sv"
    mut_s1_xbar.write_text(
        xbar_src.replace(old_s1, "            wire s1_can_accept_w   = 1'b1;"),
        encoding="utf-8",
    )
    mut_s1_sources = [mut_s1_xbar if p.name == "km_event_crossbar.sv" else p for p in rtl_sources]
    vvp_mut_s1 = tmp_path / "cluster_mut_s1.vvp"
    subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-Pkm_manycore_cluster_tb.NUM_CORES=4",
            "-Pkm_manycore_cluster_tb.PIPELINE_STAGES=2",
            "-s",
            "km_manycore_cluster_tb",
            "-o",
            str(vvp_mut_s1),
            *map(str, mut_s1_sources),
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    run_mut_s1 = subprocess.run(
        ["vvp", "-n", str(vvp_mut_s1), "+events_per_profile=128"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    combined_s1 = run_mut_s1.stdout + run_mut_s1.stderr
    assert run_mut_s1.returncode != 0 or "[FAIL]" in combined_s1
    assert "[FAIL]" in combined_s1

    # Negative mutant control 3 (2-stage #263 M5): breaking inter-group arbiter at N=4 must fail TB
    old_m5 = "                assign grp_eff_any = (|grp_hi_any) ? grp_hi_any : grp_lo_any;"
    assert xbar_src.count(old_m5) == 1
    mut_m5_xbar = tmp_path / "mut_m5_xbar.sv"
    mut_m5_xbar.write_text(
        xbar_src.replace(old_m5, "                assign grp_eff_any = grp_hi_any;"),
        encoding="utf-8",
    )
    mut_m5_sources = [mut_m5_xbar if p.name == "km_event_crossbar.sv" else p for p in rtl_sources]
    vvp_mut_m5 = tmp_path / "cluster_mut_m5.vvp"
    subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-Pkm_manycore_cluster_tb.NUM_CORES=4",
            "-Pkm_manycore_cluster_tb.PIPELINE_STAGES=2",
            "-s",
            "km_manycore_cluster_tb",
            "-o",
            str(vvp_mut_m5),
            *map(str, mut_m5_sources),
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    run_mut_m5 = subprocess.run(
        ["vvp", "-n", str(vvp_mut_m5), "+events_per_profile=128"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    combined_m5 = run_mut_m5.stdout + run_mut_m5.stderr
    assert run_mut_m5.returncode != 0 or "[FAIL]" in combined_m5
    assert "[FAIL]" in combined_m5
