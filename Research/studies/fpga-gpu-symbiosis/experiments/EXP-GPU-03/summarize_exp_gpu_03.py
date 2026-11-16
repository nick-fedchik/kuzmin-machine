#!/usr/bin/env python3
"""Deterministic across-run aggregator and independent Python reference model for EXP-GPU-03 (#256).

Aggregates R=5 independent process runs x N=10,000 events across the 5 experimental series S1..S5
at geometry 16x64 = 1024 subscribers (per-SM partitioned 128-B L2 ingress, isolated 128-B ack, mask=rand)
on NVIDIA Jetson AGX Orin (GA10B, sm_87):
  - S1: MODE_50W (816.0 MHz), layout=homo_pid, rt_pin=0
  - S2: MODE_50W (816.0 MHz), layout=mixed_warp, rt_pin=0
  - S3: MODE_50W (816.0 MHz), layout=grouped_warp, rt_pin=0
  - S4: MAXN (1300.5 MHz), layout=grouped_warp, rt_pin=0
  - S5: MAXN (1300.5 MHz), layout=grouped_warp, --rt-pin (CPU 11 + SCHED_FIFO prio 80)

Enforces metrological invariants (mismatch_count == 0, sysfs clock lock, dual-timer agreement,
Host RT = T_host_pub + T_wait_ack, non-vacuous nonlinear state transitions, and RT scheduler state)
and computes across-run mean_of_means, sample standard deviation sd_across_runs (ddof=1), CV%, min, max.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = EXP_DIR.parents[1] / "data" / "exp-gpu-03"

OP_0_PID_Q8 = 0
OP_1_BIQUAD_Q12 = 1
OP_2_HYST_WINDOW = 2
OP_3_EWMA_SLEW = 3

PID_INT_MIN = -32768
PID_INT_MAX = 32767


@dataclass(frozen=True)
class SeriesSpec:
    series_id: str
    file_prefix: str
    profile: str
    expected_freq_hz: int
    expected_layout: str
    expected_op_counts: tuple[int, int, int, int]
    expected_rt_pin: bool
    expected_sched_fifo: bool


SERIES_EXP03: tuple[SeriesSpec, ...] = (
    SeriesSpec(
        series_id="S1",
        file_prefix="exp03_S1_50w_homo_pid",
        profile="MODE_50W",
        expected_freq_hz=816_000_000,
        expected_layout="homo_pid",
        expected_op_counts=(1024, 0, 0, 0),
        expected_rt_pin=False,
        expected_sched_fifo=False,
    ),
    SeriesSpec(
        series_id="S2",
        file_prefix="exp03_S2_50w_mixed_warp",
        profile="MODE_50W",
        expected_freq_hz=816_000_000,
        expected_layout="mixed_warp",
        expected_op_counts=(256, 256, 256, 256),
        expected_rt_pin=False,
        expected_sched_fifo=False,
    ),
    SeriesSpec(
        series_id="S3",
        file_prefix="exp03_S3_50w_grouped_warp",
        profile="MODE_50W",
        expected_freq_hz=816_000_000,
        expected_layout="grouped_warp",
        expected_op_counts=(256, 256, 256, 256),
        expected_rt_pin=False,
        expected_sched_fifo=False,
    ),
    SeriesSpec(
        series_id="S4",
        file_prefix="exp03_S4_maxn_grouped_warp",
        profile="MAXN",
        expected_freq_hz=1_300_500_000,
        expected_layout="grouped_warp",
        expected_op_counts=(256, 256, 256, 256),
        expected_rt_pin=False,
        expected_sched_fifo=False,
    ),
    SeriesSpec(
        series_id="S5",
        file_prefix="exp03_S5_maxn_grouped_warp_rtpin",
        profile="MAXN",
        expected_freq_hz=1_300_500_000,
        expected_layout="grouped_warp",
        expected_op_counts=(256, 256, 256, 256),
        expected_rt_pin=True,
        expected_sched_fifo=True,
    ),
)

SUMMARY_METRICS: tuple[str, ...] = (
    "math_cycles_mean",
    "math_cycles_p50",
    "math_cycles_p999",
    "math_ns_mean",
    "math_ns_p50",
    "math_ns_p999",
    "math_ns_max",
    "e2e_sm_cycles_p50",
    "e2e_sm_cycles_p999",
    "e2e_sm_ns_mean",
    "e2e_sm_ns_p50",
    "e2e_sm_ns_p99",
    "e2e_sm_ns_p999",
    "e2e_sm_ns_max",
    "e2e_sm_b0_ns_mean",
    "e2e_gt_ns_mean",
    "e2e_gt_ns_p50",
    "e2e_gt_ns_p999",
    "e2e_gt_ns_max",
    "host_pub_ns_mean",
    "host_pub_ns_p50",
    "host_pub_ns_p99",
    "host_pub_ns_max",
    "host_wait_ack_ns_mean",
    "host_wait_ack_ns_p50",
    "host_wait_ack_ns_p999",
    "host_wait_ack_ns_max",
    "host_rt_ns_mean",
    "host_rt_ns_p50",
    "host_rt_ns_p99",
    "host_rt_ns_p999",
    "host_rt_ns_max",
    "host_rt_us_mean",
)


def compute_across_run_stats(values: list[float]) -> dict[str, float]:
    """Compute across-run mean, unbiased sample SD (ddof=1), CV%, min, and max."""
    r = len(values)
    if r < 2:
        raise ValueError(f"Across-run SD with ddof=1 requires at least 2 runs, got {r}")
    mean_val = math.fsum(values) / r
    var_val = math.fsum((v - mean_val) ** 2 for v in values) / (r - 1)
    sd_val = math.sqrt(var_val)
    cv_pct = (sd_val / mean_val * 100.0) if mean_val != 0.0 else 0.0
    return {
        "runs": r,
        "mean_of_means": mean_val,
        "sd_across_runs": sd_val,
        "cv_pct": cv_pct,
        "min": min(values),
        "max": max(values),
    }


def init_python_subscriber(gid: int, layout: str) -> dict[str, int]:
    """Independent Python specification of subscriber descriptor and initial state."""
    warp_global = gid >> 5
    lane_id = gid & 31
    if layout == "homo_pid":
        op_type = OP_0_PID_Q8
        inst_id = gid & 255
    elif layout == "mixed_warp":
        op_type = lane_id & 3
        inst_id = ((warp_global * 8) + (lane_id >> 2)) & 255
    elif layout == "grouped_warp":
        op_type = warp_global & 3
        inst_id = (((warp_global >> 2) * 32) + lane_id) & 255
    else:
        raise ValueError(f"Unknown layout: {layout}")

    if op_type == OP_0_PID_Q8:
        p0 = -120 + (inst_id & 31) * 8
        p1 = 512 + (inst_id & 7) * 32
        p2 = 48 + ((inst_id >> 3) & 15) * 4
        p3 = 256 + ((inst_id >> 5) & 3) * 64
        p4 = PID_INT_MAX
    elif op_type == OP_1_BIQUAD_Q12:
        b0_tab = (768, 519, 1048, 832)
        b1_tab = (1536, 1038, 0, 1664)
        b2_tab = (768, 519, -1048, 832)
        a1_tab = (-2048, -3620, 0, -3072)
        a2_tab = (1024, 1600, 2000, 2304)
        k = inst_id & 3
        p0, p1, p2, p3, p4 = b0_tab[k], b1_tab[k], b2_tab[k], a1_tab[k], a2_tab[k]
    elif op_type == OP_2_HYST_WINDOW:
        p0 = -20 + (inst_id & 15) * 4
        p1 = 24 + ((inst_id >> 4) & 3) * 8
        p2 = 140 + (inst_id & 7) * 12
        p3 = 60 + (inst_id & 7) * 8
        p4 = 3 + ((inst_id >> 3) & 3)
    else:
        p0 = 48 + (inst_id & 7) * 16
        p1 = 18 + ((inst_id >> 3) & 7) * 4
        p2 = 180 + ((inst_id >> 5) & 3) * 20
        p3 = 4
        p4 = 0

    return {
        "op_type": op_type,
        "inst_id": inst_id,
        "p0": p0,
        "p1": p1,
        "p2": p2,
        "p3": p3,
        "p4": p4,
        "s0": 0,
        "s1": 0,
        "s2": 0,
        "s3": 0,
        "out_val": -7777,
        "trigger_count": 0,
    }


def python_hetero_step(state: dict[str, int], c_val: int, active: bool) -> dict[str, int]:
    """Independent Python oracle for all 4 stateful subscriber operators."""
    nxt = dict(state)
    if not active:
        return nxt

    in_val = c_val + ((state["inst_id"] & 31) * 4) - 60
    op_type = state["op_type"]
    p0, p1, p2, p3, p4 = state["p0"], state["p1"], state["p2"], state["p3"], state["p4"]
    s0, s1, s2, s3 = state["s0"], state["s1"], state["s2"], state["s3"]

    if op_type == OP_0_PID_Q8:
        err = in_val - p0
        raw_int = s0 + err
        clamped = 1 if (raw_int > p4 or raw_int < PID_INT_MIN) else 0
        cand_int = max(PID_INT_MIN, min(p4, raw_int))
        p_term = (err * p1) >> 8
        i_term = (cand_int * p2) >> 8
        d_term = ((err - s1) * p3) >> 8
        nxt["s0"] = cand_int
        nxt["s1"] = err
        nxt["s2"] = s2 + clamped
        nxt["out_val"] = p_term + i_term + d_term
    elif op_type == OP_1_BIQUAD_Q12:
        y_val = (p0 * in_val + s0 + 2048) >> 12
        cand_z1 = p1 * in_val - p3 * y_val + s1
        cand_z2 = p2 * in_val - p4 * y_val
        nxt["s0"] = cand_z1
        nxt["s1"] = cand_z2
        nxt["s2"] = max(s2, abs(y_val))
        nxt["out_val"] = y_val
    elif op_type == OP_2_HYST_WINDOW:
        d = in_val - p0
        if d > p1:
            x_db = d - p1
        elif d < -p1:
            x_db = d + p1
        else:
            x_db = 0

        cand_st = s0
        if s0 == 1:
            if x_db < p3:
                cand_st = -1 if x_db <= -p2 else 0
        elif s0 == -1:
            if x_db > -p3:
                cand_st = 1 if x_db >= p2 else 0
        else:
            if x_db >= p2:
                cand_st = 1
            elif x_db <= -p2:
                cand_st = -1

        if cand_st != 0:
            cand_dwell = (s1 + 1) if (cand_st == s0) else 1
        else:
            cand_dwell = 0
        cand_trans = s2 + (1 if cand_st != s0 else 0)
        qual_term = (cand_st * 1000) if cand_dwell >= p4 else 0
        nxt["s0"] = cand_st
        nxt["s1"] = cand_dwell
        nxt["s2"] = cand_trans
        nxt["out_val"] = qual_term + (cand_st * 100) + min(cand_dwell, 64)
    elif op_type == OP_3_EWMA_SLEW:
        cand_ewma_q8 = s0 + ((p0 * ((in_val << 8) - s0)) >> 8)
        ewma_val = cand_ewma_q8 >> 8
        raw_delta = ewma_val - s1
        step_delta = max(-p1, min(p1, raw_delta))
        cand_slew = s1 + step_delta
        deriv = in_val - s2
        is_jump = abs(deriv) > p2
        jump_term = (p3 if deriv > 0 else -p3) if is_jump else 0
        nxt["s0"] = cand_ewma_q8
        nxt["s1"] = cand_slew
        nxt["s2"] = in_val
        nxt["s3"] = s3 + (1 if is_jump else 0)
        nxt["out_val"] = cand_slew + jump_term
    else:
        raise ValueError(f"Unknown op_type: {op_type}")

    nxt["trigger_count"] = state["trigger_count"] + 1
    return nxt


def validate_exp03_record(
    rec: dict[str, Any],
    spec: SeriesSpec,
    max_clock_gt_rel_err: float = 0.03,
) -> None:
    """Validate metrological, topological, and functional integrity of one EXP-GPU-03 JSON record."""
    if rec.get("experiment") != "EXP-GPU-03" or rec.get("issue") != 256:
        raise ValueError(f"Unexpected experiment/issue metadata: {rec.get('experiment')} #{rec.get('issue')}")
    if rec.get("blocks") != 16 or rec.get("threads") != 64 or rec.get("subscribers") != 1024:
        raise ValueError(
            f"Unexpected geometry: {rec.get('blocks')}x{rec.get('threads')}={rec.get('subscribers')}"
        )
    if rec.get("events") != 10000:
        raise ValueError(f"Expected 10000 events, got {rec.get('events')}")
    if rec.get("ingress_mode") != "partitioned" or rec.get("ack_mode") != "isolated":
        raise ValueError(f"Expected partitioned/isolated, got {rec.get('ingress_mode')}/{rec.get('ack_mode')}")
    if rec.get("mask") != "rand":
        raise ValueError(f"Expected mask=rand, got {rec.get('mask')}")
    if rec.get("layout") != spec.expected_layout:
        raise ValueError(f"Expected layout={spec.expected_layout}, got {rec.get('layout')}")
    if tuple(rec.get("op_counts", ())) != spec.expected_op_counts:
        raise ValueError(f"Expected op_counts={list(spec.expected_op_counts)}, got {rec.get('op_counts')}")

    mismatch_count = rec.get("mismatch_count")
    mismatches = rec.get("mismatches")
    mid_mismatches = rec.get("mid_run_mismatches")
    if mismatch_count is None or mismatch_count != 0 or mismatches != 0 or mid_mismatches != 0:
        raise ValueError(
            f"Non-zero CPU oracle mismatch: mismatch_count={mismatch_count}, "
            f"mismatches={mismatches}, mid_run_mismatches={mid_mismatches}"
        )

    if int(rec.get("pid_sat_events_total", 0)) <= 0:
        raise ValueError("PID anti-windup saturation did not fire (vacuous OP_0_PID_Q8 coverage)")
    if spec.expected_layout != "homo_pid":
        if int(rec.get("biquad_max_peak_y", 0)) <= 0:
            raise ValueError("Biquad peak output is zero (vacuous OP_1_BIQUAD_Q12 coverage)")
        if int(rec.get("hyst_transitions_total", 0)) <= 0:
            raise ValueError("Hysteresis transitions did not fire (vacuous OP_2_HYST_WINDOW coverage)")
        if int(rec.get("ewma_jumps_total", 0)) <= 0:
            raise ValueError("EWMA derivative jumps did not fire (vacuous OP_3_EWMA_SLEW coverage)")

    cur_hz = rec.get("sysfs_cur_freq_hz")
    min_hz = rec.get("sysfs_min_freq_hz")
    max_hz = rec.get("sysfs_max_freq_hz")
    if cur_hz != spec.expected_freq_hz or min_hz != spec.expected_freq_hz or max_hz != spec.expected_freq_hz:
        raise ValueError(
            f"GPU clock not locked to {spec.expected_freq_hz} Hz: cur={cur_hz}, min={min_hz}, max={max_hz}"
        )

    if bool(rec.get("rt_pin_requested")) != spec.expected_rt_pin:
        raise ValueError(f"Expected rt_pin_requested={spec.expected_rt_pin}, got {rec.get('rt_pin_requested')}")
    if bool(rec.get("cpu_affinity_active")) != spec.expected_rt_pin:
        raise ValueError(f"Expected cpu_affinity_active={spec.expected_rt_pin}, got {rec.get('cpu_affinity_active')}")
    if bool(rec.get("sched_fifo_active")) != spec.expected_sched_fifo:
        raise ValueError(f"Expected sched_fifo_active={spec.expected_sched_fifo}, got {rec.get('sched_fifo_active')}")

    if spec.expected_rt_pin:
        if rec.get("pinned_cpu") != 11 or rec.get("observed_cpu_start") != 11 or rec.get("observed_cpu_end") != 11:
            raise ValueError(
                f"Expected publisher pinned on CPU 11, got pinned={rec.get('pinned_cpu')} "
                f"obs={rec.get('observed_cpu_start')}->{rec.get('observed_cpu_end')}"
            )
    if spec.expected_sched_fifo and rec.get("sched_fifo_priority") != 80:
        raise ValueError(f"Expected sched_fifo_priority=80, got {rec.get('sched_fifo_priority')}")

    ns_per_cyc = 1e9 / float(cur_hz)
    computed_e2e_ns = float(rec["e2e_sm_cycles_mean"]) * ns_per_cyc
    if abs(computed_e2e_ns - float(rec["e2e_sm_ns_mean"])) > 0.05:
        raise ValueError("Inconsistent cycle-to-ns conversion in e2e_sm_ns_mean")

    computed_math_p50_ns = float(rec["math_cycles_p50"]) * ns_per_cyc
    if abs(computed_math_p50_ns - float(rec["math_ns_p50"])) > 0.05:
        raise ValueError("Inconsistent cycle-to-ns conversion in math_ns_p50")

    gt_ns = float(rec["e2e_gt_ns_mean"])
    rel_err = abs(computed_e2e_ns - gt_ns) / gt_ns
    if rel_err > max_clock_gt_rel_err:
        raise ValueError(
            f"Clock/globaltimer divergence {rel_err:.4f} exceeds {max_clock_gt_rel_err}: "
            f"sm={computed_e2e_ns:.2f}ns vs gt={gt_ns:.2f}ns"
        )

    rt_sum_ns = float(rec["host_pub_ns_mean"]) + float(rec["host_wait_ack_ns_mean"])
    if abs(rt_sum_ns - float(rec["host_rt_ns_mean"])) > 0.05:
        raise ValueError(
            f"Host RT decomposition mismatch: pub+wait={rt_sum_ns:.3f} vs rt={rec['host_rt_ns_mean']:.3f}"
        )
    if abs(float(rec["host_rt_ns_mean"]) / 1000.0 - float(rec["host_rt_us_mean"])) > 0.001:
        raise ValueError("Inconsistent host_rt_ns_mean vs host_rt_us_mean")


def summarize_exp03_dir(
    data_dir: Path = DEFAULT_DATA_DIR,
    runs_per_series: int = 5,
    max_clock_gt_rel_err: float = 0.03,
) -> dict[str, Any]:
    """Load, validate, and aggregate all 5 series x R=5 JSON files in data/exp-gpu-03."""
    data_dir = Path(data_dir)
    series_summary: dict[str, dict[str, Any]] = {}
    file_sha256: dict[str, str] = {}
    total_runs = 0
    total_events = 0

    for aux_name in ("sass-sm87-hetero.txt", "run-01-exp-gpu-03-s1-s5.log"):
        aux_path = data_dir / aux_name
        if aux_path.is_file():
            file_sha256[aux_name] = hashlib.sha256(aux_path.read_bytes()).hexdigest()

    for spec in SERIES_EXP03:
        records: list[dict[str, Any]] = []
        for r in range(1, runs_per_series + 1):
            fname = f"{spec.file_prefix}_r{r}.json"
            fpath = data_dir / fname
            if not fpath.is_file():
                raise FileNotFoundError(f"Missing EXP-GPU-03 raw JSON artifact: {fpath}")
            raw_bytes = fpath.read_bytes()
            file_sha256[fname] = hashlib.sha256(raw_bytes).hexdigest()
            rec = json.loads(raw_bytes.decode("utf-8"))
            validate_exp03_record(rec, spec=spec, max_clock_gt_rel_err=max_clock_gt_rel_err)
            records.append(rec)
            total_runs += 1
            total_events += int(rec["events"])

        metrics_agg: dict[str, dict[str, float]] = {}
        for metric in SUMMARY_METRICS:
            vals = [float(rec[metric]) for rec in records]
            metrics_agg[metric] = compute_across_run_stats(vals)

        clock_gt_errs = [
            abs(float(rec["e2e_sm_ns_mean"]) - float(rec["e2e_gt_ns_mean"])) / float(rec["e2e_gt_ns_mean"])
            for rec in records
        ]
        e2e_spikes_list = [int(rec["e2e_sm_spikes_gt_100us"]) for rec in records]
        e2e_1ms_list = [int(rec["e2e_sm_spikes_gt_1ms"]) for rec in records]
        math_spikes_list = [int(rec["math_spikes_gt_100us"]) for rec in records]
        host_spikes_list = [int(rec["host_rt_spikes_gt_100us"]) for rec in records]

        series_summary[spec.series_id] = {
            "series_id": spec.series_id,
            "profile": spec.profile,
            "sysfs_cur_freq_hz": spec.expected_freq_hz,
            "cpu_cur_freq_khz": int(records[0]["cpu_cur_freq_khz"]),
            "layout": spec.expected_layout,
            "op_counts": list(spec.expected_op_counts),
            "rt_pin_requested": spec.expected_rt_pin,
            "cpu_affinity_active": spec.expected_rt_pin,
            "sched_fifo_active": spec.expected_sched_fifo,
            "runs": runs_per_series,
            "events_per_run": 10000,
            "total_mismatches": 0,
            "max_clock_gt_rel_err": max(clock_gt_errs),
            "spikes_gt_100us": {
                "e2e_sm_per_run": e2e_spikes_list,
                "e2e_sm_total": sum(e2e_spikes_list),
                "e2e_sm_runs_affected": sum(1 for x in e2e_spikes_list if x > 0),
                "e2e_sm_gt_1ms_total": sum(e2e_1ms_list),
                "math_total": sum(math_spikes_list),
                "host_rt_per_run": host_spikes_list,
                "host_rt_total": sum(host_spikes_list),
                "host_rt_runs_affected": sum(1 for x in host_spikes_list if x > 0),
            },
            "metrics": metrics_agg,
        }

    s1 = series_summary["S1"]["metrics"]
    s2 = series_summary["S2"]["metrics"]
    s3 = series_summary["S3"]["metrics"]
    s4 = series_summary["S4"]["metrics"]
    s5 = series_summary["S5"]["metrics"]

    comparisons = {
        "mixed_vs_grouped_50w_math_p50_ratio": (
            s2["math_ns_p50"]["mean_of_means"] / s3["math_ns_p50"]["mean_of_means"]
        ),
        "mixed_vs_grouped_50w_math_p999_ratio": (
            s2["math_ns_p999"]["mean_of_means"] / s3["math_ns_p999"]["mean_of_means"]
        ),
        "mixed_vs_grouped_50w_e2e_p50_delta_ns": (
            s2["e2e_sm_ns_p50"]["mean_of_means"] - s3["e2e_sm_ns_p50"]["mean_of_means"]
        ),
        "mixed_vs_grouped_50w_e2e_p999_delta_ns": (
            s2["e2e_sm_ns_p999"]["mean_of_means"] - s3["e2e_sm_ns_p999"]["mean_of_means"]
        ),
        "grouped_vs_homo_50w_math_p50_delta_ns": (
            s3["math_ns_p50"]["mean_of_means"] - s1["math_ns_p50"]["mean_of_means"]
        ),
        "grouped_50w_vs_maxn_freq_ratio": 1_300_500_000 / 816_000_000,
        "grouped_50w_vs_maxn_math_p50_speedup": (
            s3["math_ns_p50"]["mean_of_means"] / s4["math_ns_p50"]["mean_of_means"]
        ),
        "grouped_50w_vs_maxn_e2e_p50_speedup": (
            s3["e2e_sm_ns_p50"]["mean_of_means"] / s4["e2e_sm_ns_p50"]["mean_of_means"]
        ),
        "grouped_50w_vs_maxn_e2e_p999_speedup": (
            s3["e2e_sm_ns_p999"]["mean_of_means"] / s4["e2e_sm_ns_p999"]["mean_of_means"]
        ),
        "grouped_50w_vs_maxn_host_rt_p50_speedup": (
            s3["host_rt_ns_p50"]["mean_of_means"] / s4["host_rt_ns_p50"]["mean_of_means"]
        ),
        "s4_p999_e2e_sm_ns_mean_of_means": s4["e2e_sm_ns_p999"]["mean_of_means"],
        "s5_p999_e2e_sm_ns_mean_of_means": s5["e2e_sm_ns_p999"]["mean_of_means"],
        "adr_b6_p999_le_1500ns_met_in_s4": s4["e2e_sm_ns_p999"]["mean_of_means"] <= 1500.0,
        "adr_b6_p999_le_1500ns_met_in_s5": s5["e2e_sm_ns_p999"]["mean_of_means"] <= 1500.0,
    }

    return {
        "experiment": "EXP-GPU-03",
        "issue": 256,
        "geometry": "16x64",
        "subscribers": 1024,
        "mask": "rand",
        "ingress_mode": "partitioned",
        "ack_mode": "isolated",
        "runs_per_series": runs_per_series,
        "total_runs": total_runs,
        "total_events": total_events,
        "all_mismatches_zero": True,
        "series": series_summary,
        "comparisons": comparisons,
        "file_sha256": file_sha256,
    }


def format_markdown_summary(summary: dict[str, Any]) -> str:
    """Render concise deterministic Markdown table of S1..S5 across-run results."""
    lines = [
        f"EXP-GPU-03 (#256): geometry={summary['geometry']} ({summary['subscribers']} subscribers), "
        f"total_runs={summary['total_runs']}, total_events={summary['total_events']}, "
        f"all_mismatches_zero={summary['all_mismatches_zero']}",
        "",
        "| Series | Profile (GPU MHz) | Layout / RT-pin | `math_ns` `p50` / `p99.9` (ns) | `e2e_sm_ns` `mean` (ns) | `e2e_sm_ns` `p50` (ns) | `e2e_sm_ns` `p99.9` (ns) | `Host RT` `p50` / `mean` (us) | SM spikes >100us (runs) |",
        "| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for sid in ("S1", "S2", "S3", "S4", "S5"):
        s = summary["series"][sid]
        m = s["metrics"]
        sp = s["spikes_gt_100us"]
        mhz = s["sysfs_cur_freq_hz"] / 1e6
        rt_tag = "CPU11+FIFO80" if s["sched_fifo_active"] else "CFS"
        lines.append(
            f"| `{sid}` | `{s['profile']}` (`{mhz:.1f}`) | `{s['layout']}` / `{rt_tag}` | "
            f"`{m['math_ns_p50']['mean_of_means']:.2f}` / `{m['math_ns_p999']['mean_of_means']:.2f}` | "
            f"`{m['e2e_sm_ns_mean']['mean_of_means']:.2f} ± {m['e2e_sm_ns_mean']['sd_across_runs']:.2f}` | "
            f"`{m['e2e_sm_ns_p50']['mean_of_means']:.2f} ± {m['e2e_sm_ns_p50']['sd_across_runs']:.2f}` | "
            f"`{m['e2e_sm_ns_p999']['mean_of_means']:.2f} ± {m['e2e_sm_ns_p999']['sd_across_runs']:.2f}` | "
            f"`{m['host_rt_ns_p50']['mean_of_means'] / 1000.0:.3f}` / `{m['host_rt_us_mean']['mean_of_means']:.3f} ± {m['host_rt_us_mean']['sd_across_runs']:.3f}` | "
            f"`{sp['e2e_sm_total']}` (`{sp['e2e_sm_runs_affected']}/5`) |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize EXP-GPU-03 (#256) R=5 S1..S5 dataset.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    summary = summarize_exp03_dir(args.data_dir)
    print(format_markdown_summary(summary))
    if args.json_out is not None:
        args.json_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
