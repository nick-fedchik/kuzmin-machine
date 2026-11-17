#!/usr/bin/env python3
"""Issue #255: RTL cycle-accurate traffic profiler (`iverilog`) for N = 4 and N = 8.

Compiles and runs `km_manycore_cluster_tb.sv` across the four canonical traffic profiles
(`local`, `uniform`, `hotspot`, `many-to-one`, >= 1,024 primary events per profile) for
`NUM_CORES = 4` and `NUM_CORES = 8`, recording throughput (`MCPS @ 100 MHz`, and scaled to
routed `F_max(N)` if `manycore_pnr_summary.json` is present), average/min/max latency in
clock cycles, `backpressure_stalls`, and verifying `0` dropped accepted events and `0`
golden state mismatches.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WP_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.abspath(os.path.join(WP_DIR, "..", "..", "..", ".."))
HW_DIR = os.path.join(REPO_ROOT, "Engineering", "hw")
RTL_CORE = os.path.join(HW_DIR, "rtl", "core")
RTL_CLUSTER = os.path.join(HW_DIR, "rtl", "cluster")

RTL_GATE = os.path.join(RTL_CORE, "kpol_txn_gate_v2.sv")
RTL_CME = os.path.join(RTL_CORE, "km_concept_micro_engine.sv")
RTL_BRAM = os.path.join(RTL_CORE, "km_concept_bram.sv")
RTL_XBAR = os.path.join(RTL_CLUSTER, "km_event_crossbar.sv")
RTL_CLUSTER_SV = os.path.join(RTL_CLUSTER, "km_manycore_cluster.sv")
TB_SV = os.path.join(HW_DIR, "tests", "km_manycore_cluster_tb.sv")
DEFAULT_OUT = os.path.join(WP_DIR, "raw")


def clean_lines(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


def write_log(log_path: str, cmd: list[str], text: str) -> None:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    ts = datetime.datetime.now().astimezone().isoformat()
    header = f"# cmd: {' '.join(cmd)}\n# timestamp: {ts}\n"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(clean_lines(header + text))


def sh(cmd: list[str], cwd: str, log_path: str | None = None) -> tuple[int, str, float]:
    t0 = time.time()
    env = {**os.environ, "TMPDIR": cwd}
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    dt = time.time() - t0
    out = (p.stdout or "") + (p.stderr or "")
    if log_path:
        write_log(log_path, cmd, out)
    return p.returncode, out, dt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument("--cores", default="4,8")
    ap.add_argument("--events-per-profile", type=int, default=1024)
    args = ap.parse_args()

    core_list = [int(x.strip()) for x in args.cores.split(",") if x.strip()]
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    work = os.path.join(out_dir, "_work_traffic")
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work, exist_ok=True)

    fmax_by_n: dict[int, float] = {}
    pnr_json_path = os.path.join(out_dir, "manycore_pnr_summary.json")
    if os.path.isfile(pnr_json_path):
        pnr_data = json.loads(open(pnr_json_path, "r", encoding="utf-8").read())
        for r in pnr_data.get("rows", []):
            fmax_by_n[int(r["num_cores"])] = float(r["fmax_mhz"])

    csv_rows = []
    runs = []
    try:
        for n in core_list:
            vvp_bin = os.path.join(work, f"cluster_tb_n{n}.vvp")
            sum_json = os.path.join(work, f"traffic_n{n}.json")
            comp_cmd = [
                "iverilog",
                "-g2012",
                f"-Pkm_manycore_cluster_tb.NUM_CORES={n}",
                "-s",
                "km_manycore_cluster_tb",
                "-o",
                vvp_bin,
                RTL_GATE,
                RTL_CME,
                RTL_BRAM,
                RTL_XBAR,
                RTL_CLUSTER_SV,
                TB_SV,
            ]
            rc_c, out_c, _ = sh(comp_cmd, work)
            if rc_c != 0:
                raise RuntimeError(f"iverilog failed for N={n}:\n{out_c}")

            run_cmd = [
                "vvp",
                "-n",
                vvp_bin,
                f"+events_per_profile={args.events_per_profile}",
                f"+summary_json={sum_json}",
            ]
            rc_r, out_r, dt_r = sh(run_cmd, work, os.path.join(out_dir, f"iverilog_traffic_n{n}.log"))
            if rc_r != 0 or "[FAIL]" in out_r:
                raise RuntimeError(f"Simulation failed for N={n}:\n{out_r}")

            data = json.loads(open(sum_json, "r", encoding="utf-8").read())
            runs.append(data)
            fmax_n = fmax_by_n.get(n)
            for p in data["profiles"]:
                mcps_100 = float(p["throughput_mcps_at_100mhz"])
                row = {
                    "evidence_kind": "rtl_simulation_iverilog",
                    "num_cores": n,
                    "profile": p["profile"],
                    "primary_events": p["primary_events"],
                    "total_events_evaluated": p["total_events_evaluated"],
                    "local_cascades": p["local_cascades"],
                    "remote_cascades": p["remote_cascades"],
                    "xbar_routed_events": p["xbar_routed_events"],
                    "active_cycles": p["active_cycles"],
                    "throughput_mcps_at_100mhz": round(mcps_100, 3),
                    "throughput_mcps_at_fmax": round(mcps_100 * (fmax_n / 100.0), 3) if fmax_n else "",
                    "avg_latency_cycles": round(float(p["avg_latency_cycles"]), 2),
                    "min_latency_cycles": p["min_latency_cycles"],
                    "max_latency_cycles": p["max_latency_cycles"],
                    "backpressure_stalls": p["backpressure_stalls"],
                    "ext_port_wait_cycles": p["ext_port_wait_cycles"],
                    "dropped_accepted_events": p["dropped_accepted_events"],
                    "w0_golden_mismatches": p["w0_golden_mismatches"],
                }
                csv_rows.append(row)
    finally:
        if os.path.isdir(work):
            shutil.rmtree(work)

    csv_path = os.path.join(out_dir, "manycore_traffic_profiles.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(csv_rows)

    summary_out = {
        "timestamp": datetime.datetime.now().astimezone().isoformat(),
        "issue": 255,
        "evidence_kind": "rtl_simulation_iverilog",
        "not_physical_hil": True,
        "events_per_profile": args.events_per_profile,
        "platform": {
            "node": platform.node(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "sha256": {
            "km_event_crossbar.sv": hashlib.sha256(open(RTL_XBAR, "rb").read()).hexdigest(),
            "km_manycore_cluster.sv": hashlib.sha256(open(RTL_CLUSTER_SV, "rb").read()).hexdigest(),
            "km_manycore_cluster_tb.sv": hashlib.sha256(open(TB_SV, "rb").read()).hexdigest(),
        },
        "rows": csv_rows,
    }
    with open(os.path.join(out_dir, "manycore_traffic_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary_out, f, indent=2)
        f.write("\n")

    print("=" * 100)
    print("ISSUE #255 MANY-CORE TRAFFIC BENCHMARK SUMMARY (iverilog, 100 MHz nominal)")
    print("=" * 100)
    for r in csv_rows:
        print(
            f"  N={r['num_cores']} | {r['profile']:<12} | ev={r['total_events_evaluated']:<5} "
            f"(rem={r['remote_cascades']:<4}) | MCPS@100={r['throughput_mcps_at_100mhz']:<7} | "
            f"lat avg/max={r['avg_latency_cycles']}/{r['max_latency_cycles']} cyc | "
            f"bp_stalls={r['backpressure_stalls']:<5} | drops={r['dropped_accepted_events']}"
        )
    print("=" * 100)


if __name__ == "__main__":
    main()
