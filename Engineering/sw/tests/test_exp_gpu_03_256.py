"""Verification and mutant negative-control tests for EXP-GPU-03 (#256, ADR B6).

Covers:
1. Offline source contracts for heterogeneous_subscribers.cu (128-B L2 cache-line isolation,
   4 stateful register operators, 3 warp layouts, --rt-pin CPU 11 + SCHED_FIFO, dual timers).
2. Immutable SHA-256 and provenance header checks across all 25 raw JSON runs, sm_87 SASS dump,
   and run-01 log (including verified post-MAXN restoration to MODE_50W 816.0 MHz).
3. Independent hand-calculated analytical vectors for all 4 operators (OP_0_PID_Q8 anti-windup,
   OP_1_BIQUAD_Q12 z1/z2, OP_2_HYST_WINDOW Schmitt hysteresis + dwell, OP_3_EWMA_SLEW slew + jump)
   and bijective equivalence of mixed_warp vs grouped_warp subscriber multisets (AGENTS.md §4.3).
4. Explicit mutant / negative-control tests proving every validator and oracle check fails when
   defects or tampered records are injected (AGENTS.md §4.1).
5. Optional live hardware smoke check on Jetson AGX Orin (192.168.68.68) under flock /tmp/km-bench.lock.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
EXP_DIR = REPO_ROOT / "Research" / "studies" / "fpga-gpu-symbiosis" / "experiments" / "EXP-GPU-03"
DATA_DIR = REPO_ROOT / "Research" / "studies" / "fpga-gpu-symbiosis" / "data" / "exp-gpu-03"
CU_FILE = EXP_DIR / "heterogeneous_subscribers.cu"
REPORT_FILE = EXP_DIR / "report.md"
README_FILE = EXP_DIR / "README.md"

if str(EXP_DIR) not in sys.path:
    sys.path.insert(0, str(EXP_DIR))

from summarize_exp_gpu_03 import (  # noqa: E402
    OP_0_PID_Q8,
    OP_1_BIQUAD_Q12,
    OP_2_HYST_WINDOW,
    OP_3_EWMA_SLEW,
    SERIES_EXP03,
    compute_across_run_stats,
    init_python_subscriber,
    python_hetero_step,
    summarize_exp03_dir,
    validate_exp03_record,
)

JETSON_HOST = "mfedchyk@192.168.68.68"

EXPECTED_DATA_SHA256: dict[str, str] = {
    "sass-sm87-hetero.txt": "482740047adbb3c9b4630adaddd906cf5fc94abb05cf0d8ae2255df491181405",
    "run-01-exp-gpu-03-s1-s5.log": "ba06965f9cdbe2d4bb930231edc4276f25109a3cfcdde1ae902b6cdf1dc1ca31",
    "summary_exp_gpu_03.json": "322996c12da5a12ba00b1e5b15d3987106e9916e821d9e2a30e8541e56f0fa16",
    "exp03_S1_50w_homo_pid_r1.json": "dd76e7027acfa67437aad66662b82198ce5e85f924c2d5d1725996d6f149bd45",
    "exp03_S1_50w_homo_pid_r2.json": "a5c48616ecf9d49420ee897424e228bf2dd42957df68f4968d9b9d0d710aa1e4",
    "exp03_S1_50w_homo_pid_r3.json": "1f0575e358ddc10139d21f6c2525c33a9198fa35a042d34958a2c747ef50e185",
    "exp03_S1_50w_homo_pid_r4.json": "52d6f300e0894bc15ac681b537a5b83210c9d6b100631a57f50617f5a811a864",
    "exp03_S1_50w_homo_pid_r5.json": "018ed865bcfab2d4887e11887999b63fda344a989fc940b2529f0d666ca7d03a",
    "exp03_S2_50w_mixed_warp_r1.json": "66ff60cc6aa8ebdfaec03c81442f922f11660b0bff5e5a94c3e338af26a7cbb8",
    "exp03_S2_50w_mixed_warp_r2.json": "7a22e01dc186f7dcaae3882b5523f169bce00e3532f9be970a8395c796ad49a4",
    "exp03_S2_50w_mixed_warp_r3.json": "354fd78c3889729568744114ba48eea164c403a1c241fafb6f030df68a9192b9",
    "exp03_S2_50w_mixed_warp_r4.json": "bbb25c880e0b0b8ef81f1e830a48876a8f809385c65dc37239d3662ed3c5ea3d",
    "exp03_S2_50w_mixed_warp_r5.json": "fc5af543e8b939682752386bb5c17159c607dc710166536a5fedf33865490742",
    "exp03_S3_50w_grouped_warp_r1.json": "bb0cbea24a6037eafaf2858c8b117dbe1c7be817f498c06649f9a2cf4274193c",
    "exp03_S3_50w_grouped_warp_r2.json": "c155d3d75582ed246c1edfd92cf5ec064c898774a6c68e08da9bff2cf8bc3375",
    "exp03_S3_50w_grouped_warp_r3.json": "ebd7737728abf473feab56fe6e6b4008fcc642994a953d3346c7998c49774197",
    "exp03_S3_50w_grouped_warp_r4.json": "07f9631621cd500d320071b286270368919d991078ac6af40efb29da34e5afb2",
    "exp03_S3_50w_grouped_warp_r5.json": "a420f7813ae0ee2e88a4d25c039e2451e4355cff4d3d24b884a8a668165c5d65",
    "exp03_S4_maxn_grouped_warp_r1.json": "af1e7d195040deaebfe81ee6d6f7d555f4c59e16d1fa0c6812f5bf447d6130ca",
    "exp03_S4_maxn_grouped_warp_r2.json": "ce6f91077dca82324bca6498785fe537106135c9a398ee6344bc63c81e31f738",
    "exp03_S4_maxn_grouped_warp_r3.json": "023d6b2a96b6f8b3296d63bba7888e58ebc5ebda0eb67014ac7fdc4ab0dc181a",
    "exp03_S4_maxn_grouped_warp_r4.json": "7ae2acf49cc562df51714515b5965d71348c15f18b1d9edda8fd503bd5554ca2",
    "exp03_S4_maxn_grouped_warp_r5.json": "24de7a4296b3d8b258798cc34d8830b86cb79bfe8adc2843967037a03d602de8",
    "exp03_S5_maxn_grouped_warp_rtpin_r1.json": "f624234dfba218410bb49531233e88875edad041e3e7a6f80f104c1bea43144a",
    "exp03_S5_maxn_grouped_warp_rtpin_r2.json": "264b64c272b004ee70c7218f8a3cdcad800e1b308d2c49aa73c121a5ba6e42c0",
    "exp03_S5_maxn_grouped_warp_rtpin_r3.json": "fa9cc8f746a2a804bc49e2d90a1f93e720eb9172816addbfba69aca7820d856d",
    "exp03_S5_maxn_grouped_warp_rtpin_r4.json": "9624b7540620fa4eabc4fa8b910a2962dc7e3d354c51f033b7ee6c7d315dd6e8",
    "exp03_S5_maxn_grouped_warp_rtpin_r5.json": "7423c789fe3855ede0cebcfcee19b981787387b4706a5d199119d1ccc7133cba",
}


def test_cu_source_contracts_operators_layouts_and_rt_pin():
    src = CU_FILE.read_text(encoding="utf-8")
    assert "GPU_CLOCK_KHZ" not in src, "Hardcoded GPU frequency constant is prohibited"
    assert "static_assert(sizeof(km_event_ingress_t) == 128" in src
    assert "static_assert(sizeof(km_ack_line_t) == 128" in src
    assert "static_assert(offsetof(km_event_egress_t, isolated_ack) == 128" in src
    assert "static_assert(offsetof(km_event_egress_t, outputs) == 128 + KM_MAX_BLOCKS * 128" in src

    for op_name in ("OP_0_PID_Q8", "OP_1_BIQUAD_Q12", "OP_2_HYST_WINDOW", "OP_3_EWMA_SLEW"):
        assert op_name in src
    assert "#define KM_PID_INT_MIN       (-32768)" in src
    assert "#define KM_PID_INT_MAX        32767" in src

    for layout in ("homo_pid", "mixed_warp", "grouped_warp"):
        assert f'"{layout}"' in src

    assert "--rt-pin" in src
    assert "sched_setaffinity" in src
    assert "sched_setscheduler(0, SCHED_FIFO" in src
    assert "sched_fifo_active" in src
    assert "s_warp_math_cyc" in src
    assert "%%globaltimer" in src
    assert "ld.global.acquire.sys.u32" in src
    assert "st.global.release.sys.u32" in src


def test_raw_artifacts_sha256_provenance_and_mode_50w_restore():
    cu_sha = hashlib.sha256(CU_FILE.read_bytes()).hexdigest()

    for fname, expected_sha in EXPECTED_DATA_SHA256.items():
        fpath = DATA_DIR / fname
        assert fpath.is_file(), f"Missing raw artifact {fname}"
        actual_sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
        assert actual_sha == expected_sha, f"SHA-256 mismatch for {fname}"

    for text_name in ("sass-sm87-hetero.txt", "run-01-exp-gpu-03-s1-s5.log"):
        lines = (DATA_DIR / text_name).read_text(encoding="utf-8").splitlines()
        head = lines[:6]
        assert head[0].startswith("# cmd: ")
        assert re.match(r"^# timestamp: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$", head[1])
        assert head[2].startswith("# host: jetson | kernel: 5.15.148-tegra")
        assert head[3] == f"# cu_sha256: {cu_sha}"
        assert head[4].startswith("# nvcc_version: ") and "-O3 -arch=sm_87 -lineinfo" in head[4]
        assert re.match(r"^# git_base_sha: [0-9a-f]{40}$", head[5])
        assert all(not ln.endswith(" ") and not ln.endswith("\t") for ln in lines)

    log_text = (DATA_DIR / "run-01-exp-gpu-03-s1-s5.log").read_text(encoding="utf-8")
    assert "# profile_phase1_mode_50w: NV Power Mode: MODE_50W,3 | gpu_hz: cur=816000000 min=816000000 max=816000000" in log_text
    assert "# profile_phase2_maxn: NV Power Mode: MAXN,0 | gpu_hz: cur=1300500000 min=1300500000 max=1300500000" in log_text
    assert "# profile_restored_mode_50w: NV Power Mode: MODE_50W,3 | gpu_hz: cur=816000000 min=816000000 max=816000000" in log_text


def test_sass_sm87_hetero_reconvergence_predication_and_zero_spill():
    sass = (DATA_DIR / "sass-sm87-hetero.txt").read_text(encoding="utf-8")
    assert "arch = sm_87" in sass
    assert "0 bytes stack frame, 0 bytes spill stores, 0 bytes spill loads" in sass
    assert "BSSY B" in sass and "BSYNC B" in sass
    assert "SEL R" in sass
    assert re.search(r"@P\d+\s+STG\.E\s+\[R\d+\.64\+0x880\]", sass)
    assert "LDG.E.STRONG.SYS" in sass
    assert "STG.E.STRONG.SYS" in sass
    assert "SR_GLOBALTIMERLO" in sass


def test_independent_hand_calculated_operator_vectors_and_bijection():
    """AGENTS.md §4.3: verify all 4 operators against manual arithmetic, not self-copied outputs."""
    mixed_pairs = {(init_python_subscriber(g, "mixed_warp")["op_type"], init_python_subscriber(g, "mixed_warp")["inst_id"]) for g in range(1024)}
    grouped_pairs = {(init_python_subscriber(g, "grouped_warp")["op_type"], init_python_subscriber(g, "grouped_warp")["inst_id"]) for g in range(1024)}
    expected_pairs = {(op, inst) for op in range(4) for inst in range(256)}
    assert mixed_pairs == expected_pairs
    assert grouped_pairs == expected_pairs

    # 1. OP_0_PID_Q8 manual check including +32767 and -32768 anti-windup saturation
    # inst_id=15 -> offset=(15*4)-60=0 => in_val == c_val
    pid_st = {
        "op_type": OP_0_PID_Q8, "inst_id": 15,
        "p0": 10, "p1": 512, "p2": 64, "p3": 256, "p4": 32767,
        "s0": 32760, "s1": 5, "s2": 0, "s3": 0, "out_val": -7777, "trigger_count": 0,
    }
    assert python_hetero_step(pid_st, c_val=30, active=False) == pid_st
    # c_val=30 -> in_val=30, err=20, raw_int=32780 -> clamped to 32767 (s2=1)
    # P=(20*512)>>8 = 40; I=(32767*64)>>8 = 8191; D=((20-5)*256)>>8 = 15 => out = 8246
    pid_hi = python_hetero_step(pid_st, c_val=30, active=True)
    assert pid_hi["s0"] == 32767 and pid_hi["s1"] == 20 and pid_hi["s2"] == 1
    assert pid_hi["out_val"] == 8246 and pid_hi["trigger_count"] == 1

    pid_lo_in = {**pid_st, "s0": -32760, "s1": -10}
    # c_val=-10 -> in_val=-10, err=-20, raw_int=-32780 -> clamped to -32768
    # P=(-20*512)>>8 = -40; I=(-32768*64)>>8 = -8192; D=((-20 - (-10))*256)>>8 = -10 => out = -8242
    pid_lo = python_hetero_step(pid_lo_in, c_val=-10, active=True)
    assert pid_lo["s0"] == -32768 and pid_lo["s2"] == 1 and pid_lo["out_val"] == -8242

    # 2. OP_1_BIQUAD_Q12 manual 2-step check (inst_id=15 -> in_val == c_val)
    # b0=768, b1=1536, b2=768, a1=-2048, a2=1024
    biq_st = {
        "op_type": OP_1_BIQUAD_Q12, "inst_id": 15,
        "p0": 768, "p1": 1536, "p2": 768, "p3": -2048, "p4": 1024,
        "s0": 0, "s1": 0, "s2": 0, "s3": 0, "out_val": -7777, "trigger_count": 0,
    }
    # Step 1 (x=100): y = (76800 + 0 + 2048) >> 12 = 19
    # z1 = 153600 - (-2048*19) + 0 = 192512; z2 = 76800 - 1024*19 = 57344
    biq_1 = python_hetero_step(biq_st, c_val=100, active=True)
    assert (biq_1["out_val"], biq_1["s0"], biq_1["s1"], biq_1["s2"]) == (19, 192512, 57344, 19)
    # Step 2 (x=100): y = (76800 + 192512 + 2048) >> 12 = 271360 >> 12 = 66
    # z1 = 153600 - (-2048*66) + 57344 = 346112; z2 = 76800 - 1024*66 = 9216
    biq_2 = python_hetero_step(biq_1, c_val=100, active=True)
    assert (biq_2["out_val"], biq_2["s0"], biq_2["s1"], biq_2["s2"]) == (66, 346112, 9216, 66)

    # 3. OP_2_HYST_WINDOW manual check: deadband + hysteresis latch + dwell qualification
    hyst_st = {
        "op_type": OP_2_HYST_WINDOW, "inst_id": 15,
        "p0": 0, "p1": 20, "p2": 100, "p3": 40, "p4": 2,
        "s0": 0, "s1": 0, "s2": 0, "s3": 0, "out_val": -7777, "trigger_count": 0,
    }
    # Inside deadband (x=15 -> x_db=0): stays 0
    h1 = python_hetero_step(hyst_st, c_val=15, active=True)
    assert (h1["s0"], h1["s1"], h1["s2"], h1["out_val"]) == (0, 0, 0, 0)
    # Above th_hi (x=130 -> x_db=110 >= 100): state=1, dwell=1 (< min_dwell=2) -> out = 101
    h2 = python_hetero_step(h1, c_val=130, active=True)
    assert (h2["s0"], h2["s1"], h2["s2"], h2["out_val"]) == (1, 1, 1, 101)
    # Drops between th_lo and th_hi (x=70 -> x_db=50 >= th_lo=40): Schmitt holds state=1, dwell=2 (>=2) -> out = 1102
    h3 = python_hetero_step(h2, c_val=70, active=True)
    assert (h3["s0"], h3["s1"], h3["s2"], h3["out_val"]) == (1, 2, 1, 1102)
    # Drops below th_lo (x=50 -> x_db=30 < 40): releases to state=0, dwell=0, transitions=2 -> out = 0
    h4 = python_hetero_step(h3, c_val=50, active=True)
    assert (h4["s0"], h4["s1"], h4["s2"], h4["out_val"]) == (0, 0, 2, 0)

    # 4. OP_3_EWMA_SLEW manual check: EWMA Q8 + slew-rate clamp + derivative jump flag
    ewma_st = {
        "op_type": OP_3_EWMA_SLEW, "inst_id": 15,
        "p0": 128, "p1": 15, "p2": 200, "p3": 4, "p4": 0,
        "s0": 0, "s1": 0, "s2": 0, "s3": 0, "out_val": -7777, "trigger_count": 0,
    }
    # x=300: target_q8=76800, cand_ewma_q8 = (128*76800)>>8 = 38400 -> ewma_val = 150
    # raw_delta = 150 -> clamped to max_delta=15 => cand_slew = 15
    # deriv = 300 - 0 = 300 > 200 => jump (+4), s3=1, out = 15 + 4 = 19
    e1 = python_hetero_step(ewma_st, c_val=300, active=True)
    assert (e1["s0"], e1["s1"], e1["s2"], e1["s3"], e1["out_val"]) == (38400, 15, 300, 1, 19)


def test_all_25_raw_json_records_and_summary_aggregation_accuracy():
    hand = compute_across_run_stats([10.0, 20.0, 30.0, 40.0, 50.0])
    assert hand["runs"] == 5
    assert hand["mean_of_means"] == pytest.approx(30.0)
    assert hand["sd_across_runs"] == pytest.approx(math.sqrt(250.0))

    summary = summarize_exp03_dir(DATA_DIR)
    committed = json.loads((DATA_DIR / "summary_exp_gpu_03.json").read_text(encoding="utf-8"))
    assert summary == committed
    assert summary["total_runs"] == 25
    assert summary["total_events"] == 250000
    assert summary["all_mismatches_zero"] is True

    comp = summary["comparisons"]
    # Warp specialization cuts register math latency ~2.0x and saves >300 ns on p99.9 SM e2e
    assert comp["mixed_vs_grouped_50w_math_p50_ratio"] > 1.95
    assert comp["mixed_vs_grouped_50w_math_p999_ratio"] > 1.95
    assert comp["mixed_vs_grouped_50w_e2e_p50_delta_ns"] > 250.0
    assert comp["mixed_vs_grouped_50w_e2e_p999_delta_ns"] > 250.0

    # Pure register math scales linearly with 1300.5 / 816.0 = 1.59375 clock ratio
    assert comp["grouped_50w_vs_maxn_math_p50_speedup"] == pytest.approx(1300.5 / 816.0, rel=0.005)
    assert comp["grouped_50w_vs_maxn_e2e_p50_speedup"] > 1.25
    assert comp["grouped_50w_vs_maxn_e2e_p999_speedup"] > 1.20

    # Honest reporting check: 16x64 heterogeneous p99.9 remains > 1500 ns even at MAXN
    assert comp["adr_b6_p999_le_1500ns_met_in_s4"] is False
    assert comp["adr_b6_p999_le_1500ns_met_in_s5"] is False

    # S5 (--rt-pin CPU 11 + SCHED_FIFO:80) stabilizes across-run Host RT mean SD vs unpinned S4
    s4_rt_sd = summary["series"]["S4"]["metrics"]["host_rt_ns_mean"]["sd_across_runs"]
    s5_rt_sd = summary["series"]["S5"]["metrics"]["host_rt_ns_mean"]["sd_across_runs"]
    assert s5_rt_sd < s4_rt_sd


def test_wp_documents_envelope_and_sober_tone_guard():
    assert REPORT_FILE.is_file() and README_FILE.is_file()
    report_text = REPORT_FILE.read_text(encoding="utf-8")
    readme_text = README_FILE.read_text(encoding="utf-8")

    assert "* **Версія:** 0.1.0" in report_text
    assert "* **Дата:** 2026-11-16" in report_text
    assert "* **Тип WP редакції NG:** Report" in report_text
    assert "## 1. Що не вдалося і обмеження" in report_text
    assert "## Історія версій" in report_text
    assert "## Абревіатури та глосарій" in report_text
    assert "!" not in report_text, "Exclamation marks violate AGENTS.md §3 in report.md"

    assert "* **Версія:** 0.1.0" in readme_text
    assert "* **Дата:** 2026-11-16" in readme_text
    assert "* **Тип WP редакції NG:** Guide" in readme_text
    assert "## Історія версій" in readme_text
    assert "## Абревіатури та глосарій" in readme_text
    assert "!" not in readme_text, "Exclamation marks violate AGENTS.md §3 in README.md"


def test_mutant_negative_controls_catch_defects():
    """AGENTS.md §4.1: prove validators and operator checks fail on mutants and tampered records."""
    spec_s3 = SERIES_EXP03[2]  # S3: MODE_50W grouped_warp
    spec_s5 = SERIES_EXP03[4]  # S5: MAXN grouped_warp --rt-pin
    rec_s3 = json.loads((DATA_DIR / "exp03_S3_50w_grouped_warp_r1.json").read_text(encoding="utf-8"))
    rec_s5 = json.loads((DATA_DIR / "exp03_S5_maxn_grouped_warp_rtpin_r1.json").read_text(encoding="utf-8"))

    validate_exp03_record(rec_s3, spec_s3)
    validate_exp03_record(rec_s5, spec_s5)

    # Mutant 1: CPU oracle mismatch_count != 0 or mid_run_mismatches != 0
    with pytest.raises(ValueError, match="Non-zero CPU oracle mismatch"):
        validate_exp03_record({**rec_s3, "mismatch_count": 1}, spec_s3)
    with pytest.raises(ValueError, match="Non-zero CPU oracle mismatch"):
        validate_exp03_record({**rec_s3, "mid_run_mismatches": 1}, spec_s3)

    # Mutant 2: Fake / unlocked GPU frequency or timer disagreement
    fake_maxn_on_50w = {
        **rec_s3,
        "sysfs_cur_freq_hz": 1_300_500_000,
        "sysfs_min_freq_hz": 1_300_500_000,
        "sysfs_max_freq_hz": 1_300_500_000,
        "e2e_sm_ns_mean": rec_s3["e2e_sm_cycles_mean"] * (1e9 / 1_300_500_000),
        "math_ns_p50": rec_s3["math_cycles_p50"] * (1e9 / 1_300_500_000),
    }
    with pytest.raises(ValueError, match="Clock/globaltimer divergence"):
        validate_exp03_record(fake_maxn_on_50w, SERIES_EXP03[3])

    # Mutant 3: Broken Host RT = T_host_pub + T_wait_ack additive identity
    with pytest.raises(ValueError, match="Host RT decomposition mismatch"):
        validate_exp03_record({**rec_s5, "host_pub_ns_mean": rec_s5["host_pub_ns_mean"] + 25.0}, spec_s5)

    # Mutant 4: Missing SCHED_FIFO or wrong CPU affinity in S5
    with pytest.raises(ValueError, match="Expected sched_fifo_active=True"):
        validate_exp03_record({**rec_s5, "sched_fifo_active": False}, spec_s5)
    with pytest.raises(ValueError, match="Expected publisher pinned on CPU 11"):
        validate_exp03_record({**rec_s5, "observed_cpu_end": 4}, spec_s5)

    # Mutant 5: Vacuous nonlinear operator excitation
    for vac_field in ("pid_sat_events_total", "biquad_max_peak_y", "hyst_transitions_total", "ewma_jumps_total"):
        with pytest.raises(ValueError, match="vacuous"):
            validate_exp03_record({**rec_s3, vac_field: 0}, spec_s3)

    # Mutant 6a..6d: Broken operator arithmetic mutants vs specification oracle
    # 6a: PID mutant without [-32768, 32767] anti-windup clamp
    pid_st = {
        "op_type": OP_0_PID_Q8, "inst_id": 15,
        "p0": 10, "p1": 512, "p2": 64, "p3": 256, "p4": 32767,
        "s0": 32760, "s1": 5, "s2": 0, "s3": 0, "out_val": -7777, "trigger_count": 0,
    }
    ref_pid = python_hetero_step(pid_st, c_val=30, active=True)
    mutant_pid_no_clamp_s0 = pid_st["s0"] + (30 - pid_st["p0"])  # 32780 != 32767
    assert mutant_pid_no_clamp_s0 != ref_pid["s0"]

    # 6b: Biquad mutant omitting z2 feedback term in z1 update
    biq_st = init_python_subscriber(32, "grouped_warp")  # warp 1 -> OP_1_BIQUAD_Q12
    b1 = python_hetero_step(biq_st, c_val=200, active=True)
    b2 = python_hetero_step(b1, c_val=-150, active=True)
    in_val_b2 = -150 + ((b1["inst_id"] & 31) * 4) - 60
    y_b2 = (b1["p0"] * in_val_b2 + b1["s0"] + 2048) >> 12
    mutant_biq_no_z2 = b1["p1"] * in_val_b2 - b1["p3"] * y_b2  # drops + b1["s1"]
    assert mutant_biq_no_z2 != b2["s0"]

    # 6c: Hysteresis mutant using th_hi instead of th_lo on release (destroys Schmitt memory)
    hyst_latched = {
        "op_type": OP_2_HYST_WINDOW, "inst_id": 15,
        "p0": 0, "p1": 20, "p2": 100, "p3": 40, "p4": 2,
        "s0": 1, "s1": 1, "s2": 1, "s3": 0, "out_val": 101, "trigger_count": 1,
    }
    ref_hyst = python_hetero_step(hyst_latched, c_val=70, active=True)  # x_db=50 in [th_lo, th_hi) -> stays 1
    mutant_single_thresh_state = 1 if (70 - 20) >= 100 else 0  # drops to 0 prematurely
    assert mutant_single_thresh_state != ref_hyst["s0"]

    # 6d: EWMA mutant bypassing slew-rate limiter max_delta
    ewma_st = {
        "op_type": OP_3_EWMA_SLEW, "inst_id": 15,
        "p0": 128, "p1": 15, "p2": 200, "p3": 4, "p4": 0,
        "s0": 0, "s1": 0, "s2": 0, "s3": 0, "out_val": -7777, "trigger_count": 0,
    }
    ref_ewma = python_hetero_step(ewma_st, c_val=300, active=True)
    mutant_unslewed_out = ((128 * (300 << 8)) >> 16) + 4  # 150 + 4 = 154 != 19
    assert mutant_unslewed_out != ref_ewma["out_val"]

    # Mutant 7: Directory-level detection of injected mismatch_count and corrupted JSON (in project-local dir)
    scratch_dir = EXP_DIR / ".scratch_mutant_exp03"
    try:
        shutil.rmtree(scratch_dir, ignore_errors=True)
        shutil.copytree(DATA_DIR, scratch_dir)
        target_json = scratch_dir / "exp03_S4_maxn_grouped_warp_r3.json"
        tampered = json.loads(target_json.read_text(encoding="utf-8"))
        tampered["mismatch_count"] = 2
        target_json.write_text(json.dumps(tampered), encoding="utf-8")
        with pytest.raises(ValueError, match="Non-zero CPU oracle mismatch"):
            summarize_exp03_dir(scratch_dir)

        target_json.write_text("{corrupted_json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            summarize_exp03_dir(scratch_dir)
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def _is_jetson_reachable() -> bool:
    if os.environ.get("KM_SKIP_LIVE_HIL") == "1":
        return False
    res = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=2", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no", JETSON_HOST, "echo OK"],
        capture_output=True,
        text=True,
    )
    return res.returncode == 0 and "OK" in res.stdout


@pytest.mark.skipif(not _is_jetson_reachable(), reason="Jetson AGX Orin stand not reachable via SSH")
def test_live_jetson_hil_hetero_layouts_smoke():
    """Live hardware smoke test on Jetson AGX Orin in default MODE_50W under /tmp/km-bench.lock."""
    cmd = [
        "flock", "-w", "120", "/tmp/km-bench.lock",
        "bash", "-c",
        (
            f"ssh -o StrictHostKeyChecking=no {JETSON_HOST} 'mkdir -p $HOME/.km_pytest_256' && "
            f"scp -q {CU_FILE} {JETSON_HOST}:~/.km_pytest_256/hetero.cu && "
            f"ssh -o StrictHostKeyChecking=no {JETSON_HOST} '"
            "/usr/local/cuda/bin/nvcc -O3 -arch=sm_87 $HOME/.km_pytest_256/hetero.cu -o $HOME/.km_pytest_256/hetero -lm && "
            "$HOME/.km_pytest_256/hetero --events 1000 --blocks 16 --threads 64 --layout mixed_warp --mask rand --json-out $HOME/.km_pytest_256/mixed.json >/dev/null && "
            "$HOME/.km_pytest_256/hetero --events 1000 --blocks 16 --threads 64 --layout grouped_warp --mask rand --json-out $HOME/.km_pytest_256/grouped.json >/dev/null && "
            "cat $HOME/.km_pytest_256/mixed.json && echo ---SPLIT--- && "
            "cat $HOME/.km_pytest_256/grouped.json && "
            "rm -rf $HOME/.km_pytest_256'"
        ),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Live Jetson HIL smoke failed: {res.stderr}\n{res.stdout}"
    part_mixed, part_grouped = res.stdout.split("---SPLIT---")
    rec_mixed = json.loads(part_mixed.strip())
    rec_grouped = json.loads(part_grouped.strip())
    assert rec_mixed["mismatch_count"] == 0 and rec_mixed["op_counts"] == [256, 256, 256, 256]
    assert rec_grouped["mismatch_count"] == 0 and rec_grouped["op_counts"] == [256, 256, 256, 256]
    assert rec_mixed["math_ns_p50"] > 1.8 * rec_grouped["math_ns_p50"]
