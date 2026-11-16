#!/usr/bin/env python3
"""Deterministic across-run repeatability aggregator for Issue #240 (EXP-GPU-01).

Aggregates R=5 independent process runs x N=10,000 events across the 3x2 matrix
at geometry 16x64 = 1024 subscribers on NVIDIA Jetson AGX Orin (816.0 MHz):
  ingress_mode in {shared_1line, shared_2line, partitioned}
  mask         in {rand, none}

Computes across-run mean_of_means, sample standard deviation sd_across_runs (ddof=1),
CV%, min, and max, and enforces metrological invariants (mismatch_count == 0,
locked 816 MHz sysfs clock, dual-timer agreement, and Host RT = T_host_pub + T_wait_ack).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
DEFAULT_REP240_DIR = EXP_DIR.parents[1] / "data" / "exp-gpu-01-phase3" / "repeatability-240"

CELLS_240: tuple[tuple[str, str], ...] = (
    ("shared_1line", "rand"),
    ("shared_1line", "none"),
    ("shared_2line", "rand"),
    ("shared_2line", "none"),
    ("partitioned", "rand"),
    ("partitioned", "none"),
)

REQUIRED_PUB_FIELDS: tuple[str, ...] = (
    "host_pub_ns_mean",
    "host_pub_ns_sigma",
    "host_pub_ns_p50",
    "host_pub_ns_p99",
)

SUMMARY_METRICS: tuple[str, ...] = (
    "e2e_sm_ns_mean",
    "e2e_sm_ns_p50",
    "e2e_sm_ns_p99",
    "e2e_sm_ns_p999",
    "e2e_gt_ns_mean",
    "math_ns_mean",
    "math_ns_p999",
    "host_pub_ns_mean",
    "host_pub_ns_p50",
    "host_pub_ns_p99",
    "host_wait_ack_ns_mean",
    "host_rt_ns_mean",
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


def validate_rep240_record(
    rec: dict[str, Any],
    expected_ingress: str,
    expected_mask: str,
    max_clock_gt_rel_err: float = 0.03,
) -> None:
    """Validate metrological integrity of a single R=5 repeatability JSON record."""
    if rec.get("blocks") != 16 or rec.get("threads") != 64 or rec.get("subscribers") != 1024:
        raise ValueError(
            f"Unexpected geometry: {rec.get('blocks')}x{rec.get('threads')}={rec.get('subscribers')}"
        )
    if rec.get("events") != 10000:
        raise ValueError(f"Expected 10000 events, got {rec.get('events')}")
    if rec.get("ingress_mode") != expected_ingress:
        raise ValueError(f"Expected ingress_mode={expected_ingress}, got {rec.get('ingress_mode')}")
    if rec.get("mask") != expected_mask:
        raise ValueError(f"Expected mask={expected_mask}, got {rec.get('mask')}")
    if rec.get("ack_mode") != "isolated":
        raise ValueError(f"Expected ack_mode=isolated, got {rec.get('ack_mode')}")

    mismatch_count = rec.get("mismatch_count")
    mismatches = rec.get("mismatches")
    mid_mismatches = rec.get("mid_run_mismatches")
    if mismatch_count is None or mismatch_count != 0 or mismatches != 0 or mid_mismatches != 0:
        raise ValueError(
            f"Non-zero CPU oracle mismatch: mismatch_count={mismatch_count}, "
            f"mismatches={mismatches}, mid_run_mismatches={mid_mismatches}"
        )

    cur_hz = rec.get("sysfs_cur_freq_hz")
    max_hz = rec.get("sysfs_max_freq_hz")
    if cur_hz != 816_000_000 or max_hz != 816_000_000:
        raise ValueError(f"GPU clock not locked to 816 MHz: cur={cur_hz}, max={max_hz}")

    for field in REQUIRED_PUB_FIELDS:
        if field not in rec:
            raise ValueError(f"Missing required host publication field: {field}")
        if float(rec[field]) < 0.0:
            raise ValueError(f"Negative host publication metric {field}={rec[field]}")

    if "host_wait_ack_ns_mean" not in rec or "host_rt_us_mean" not in rec:
        raise ValueError("Missing host_wait_ack_ns_mean or host_rt_us_mean")

    computed_ns = rec["e2e_sm_cycles_mean"] * (1e9 / cur_hz)
    if abs(computed_ns - rec["e2e_sm_ns_mean"]) > 0.05:
        raise ValueError("Inconsistent cycle-to-ns conversion in e2e_sm_ns_mean")

    gt_ns = rec["e2e_gt_ns_mean"]
    rel_err = abs(computed_ns - gt_ns) / gt_ns
    if rel_err > max_clock_gt_rel_err:
        raise ValueError(
            f"Clock/globaltimer divergence {rel_err:.4f} exceeds {max_clock_gt_rel_err}: "
            f"sm={computed_ns:.2f}ns vs gt={gt_ns:.2f}ns"
        )

    rt_sum_ns = rec["host_pub_ns_mean"] + rec["host_wait_ack_ns_mean"]
    if abs(rt_sum_ns - rec["host_rt_ns_mean"]) > 0.05:
        raise ValueError(
            f"Host RT decomposition mismatch: pub+wait={rt_sum_ns:.3f} vs rt={rec['host_rt_ns_mean']:.3f}"
        )
    if abs(rec["host_rt_ns_mean"] / 1000.0 - rec["host_rt_us_mean"]) > 0.001:
        raise ValueError("Inconsistent host_rt_ns_mean vs host_rt_us_mean")


def summarize_repeatability_dir(
    data_dir: Path = DEFAULT_REP240_DIR,
    runs_per_cell: int = 5,
    max_clock_gt_rel_err: float = 0.03,
) -> dict[str, Any]:
    """Load, validate, and aggregate all 6 x R JSON files in repeatability-240."""
    data_dir = Path(data_dir)
    cells_summary: dict[str, dict[str, Any]] = {}
    file_sha256: dict[str, str] = {}
    total_runs = 0
    total_events = 0

    for ingress_mode, mask in CELLS_240:
        cell_key = f"{ingress_mode}__{mask}"
        records: list[dict[str, Any]] = []
        for r in range(1, runs_per_cell + 1):
            fname = f"rep240_16x64_{ingress_mode}_{mask}_r{r}.json"
            fpath = data_dir / fname
            if not fpath.is_file():
                raise FileNotFoundError(f"Missing repeatability artifact: {fpath}")
            raw_bytes = fpath.read_bytes()
            file_sha256[fname] = hashlib.sha256(raw_bytes).hexdigest()
            rec = json.loads(raw_bytes.decode("utf-8"))
            validate_rep240_record(
                rec,
                expected_ingress=ingress_mode,
                expected_mask=mask,
                max_clock_gt_rel_err=max_clock_gt_rel_err,
            )
            records.append(rec)
            total_runs += 1
            total_events += int(rec["events"])

        metrics_agg: dict[str, dict[str, float]] = {}
        for metric in SUMMARY_METRICS:
            vals = [float(rec[metric]) for rec in records]
            metrics_agg[metric] = compute_across_run_stats(vals)

        clock_gt_errs = [
            abs(rec["e2e_sm_ns_mean"] - rec["e2e_gt_ns_mean"]) / rec["e2e_gt_ns_mean"]
            for rec in records
        ]
        cells_summary[cell_key] = {
            "ingress_mode": ingress_mode,
            "mask": mask,
            "runs": runs_per_cell,
            "events_per_run": 10000,
            "total_mismatches": 0,
            "max_clock_gt_rel_err": max(clock_gt_errs),
            "metrics": metrics_agg,
        }

    return {
        "geometry": "16x64",
        "subscribers": 1024,
        "runs_per_cell": runs_per_cell,
        "total_runs": total_runs,
        "total_events": total_events,
        "all_mismatches_zero": True,
        "cells": cells_summary,
        "file_sha256": file_sha256,
    }


def format_markdown_summary(summary: dict[str, Any]) -> str:
    """Render concise deterministic Markdown tables for console inspection."""
    lines = [
        f"Geometry: {summary['geometry']} ({summary['subscribers']} subscribers), "
        f"total_runs={summary['total_runs']}, total_events={summary['total_events']}, "
        f"all_mismatches_zero={summary['all_mismatches_zero']}",
        "",
        "| Cell (`ingress` / `mask`) | `e2e_sm_ns_mean` (mean ± SD, CV%, min..max) | `e2e_sm_ns_p999` (mean ± SD, CV%, min..max) | `math_ns_mean` (mean ± SD) | `host_pub_ns_mean` (mean ± SD, CV%) | `host_wait_ack_ns_mean` (mean ± SD) | `host_rt_us_mean` (mean ± SD, CV%, min..max) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for cell_key, cell in summary["cells"].items():
        m = cell["metrics"]
        e2e = m["e2e_sm_ns_mean"]
        p999 = m["e2e_sm_ns_p999"]
        math_m = m["math_ns_mean"]
        pub = m["host_pub_ns_mean"]
        wait = m["host_wait_ack_ns_mean"]
        rt = m["host_rt_us_mean"]
        lines.append(
            f"| `{cell['ingress_mode']}` / `{cell['mask']}` | "
            f"`{e2e['mean_of_means']:.2f} ± {e2e['sd_across_runs']:.2f}` (`{e2e['cv_pct']:.2f}%`, `{e2e['min']:.2f}..{e2e['max']:.2f}`) | "
            f"`{p999['mean_of_means']:.2f} ± {p999['sd_across_runs']:.2f}` (`{p999['cv_pct']:.2f}%`, `{p999['min']:.2f}..{p999['max']:.2f}`) | "
            f"`{math_m['mean_of_means']:.2f} ± {math_m['sd_across_runs']:.2f}` | "
            f"`{pub['mean_of_means']:.2f} ± {pub['sd_across_runs']:.2f}` (`{pub['cv_pct']:.2f}%`) | "
            f"`{wait['mean_of_means']:.2f} ± {wait['sd_across_runs']:.2f}` | "
            f"`{rt['mean_of_means']:.3f} ± {rt['sd_across_runs']:.3f}` (`{rt['cv_pct']:.2f}%`, `{rt['min']:.3f}..{rt['max']:.3f}`) |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize Issue #240 R=5 repeatability dataset.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_REP240_DIR)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    summary = summarize_repeatability_dir(args.data_dir)
    print(format_markdown_summary(summary))
    if args.json_out is not None:
        args.json_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
