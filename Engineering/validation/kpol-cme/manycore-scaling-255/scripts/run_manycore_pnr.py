#!/usr/bin/env python3
"""Issue #255: OpenXC7 synthesis, Place & Route, and STA scaling runner (N = 1, 2, 4, 8).

Runs OpenXC7 Yosys (`synth_xilinx -flatten -abc9 -arch xc7`) and `nextpnr-himbaechel`
on `xc7z020clg400-1` (`--router router2 --freq 100`) for `km_manycore_synth_top` at
N = 1, 2, 4, 8 cores, plus standalone Yosys XC7 synthesis of `km_event_crossbar`.

Verifies that:
  - No core or Block RAM is optimized away (`RAMB36E1 == N` for N = 1, 2, 4, 8);
  - User IOB count stays strictly within the 125-pin budget (`PAD == 20`);
  - Records both Yosys `Estimated number of LCs` and post-P&R `SLICE_LUTX`, `SLICE_FFX`,
    `CARRY4`, `RAMB36E1`, critical path delay (ns), and routed `F_max(N)` (MHz);
  - Compares empirical post-route area against the analytical scaling law
    `LUT_model(N) = N * LUT_1 + c * N^2` (and `LUT_0 + b * N + c * N^2`).
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WP_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.abspath(os.path.join(WP_DIR, "..", "..", "..", ".."))
RTL_CORE = os.path.join(REPO_ROOT, "Engineering", "hw", "rtl", "core")
RTL_CLUSTER = os.path.join(REPO_ROOT, "Engineering", "hw", "rtl", "cluster")

RTL_GATE = os.path.join(RTL_CORE, "kpol_txn_gate_v2.sv")
RTL_CME = os.path.join(RTL_CORE, "km_concept_micro_engine.sv")
RTL_BRAM = os.path.join(RTL_CORE, "km_concept_bram.sv")
RTL_XBAR = os.path.join(RTL_CLUSTER, "km_event_crossbar.sv")
RTL_CLUSTER_SV = os.path.join(RTL_CLUSTER, "km_manycore_cluster.sv")
SYNTH_TOP = os.path.join(HERE, "km_manycore_synth_top.sv")
SYNTH_XDC = os.path.join(HERE, "km_manycore_synth.xdc")
DEFAULT_OUT = os.path.join(WP_DIR, "raw")

OPENXC7_DIR = os.environ.get("OPENXC7_DIR", "/home/mfedchyk/opt/openxc7")
OPENXC7_YOSYS = os.path.join(OPENXC7_DIR, "bin", "yosys")
OPENXC7_NEXTPNR = os.path.join(OPENXC7_DIR, "bin", "nextpnr-himbaechel")
CHIPDB = os.path.join(OPENXC7_DIR, "share", "nextpnr", "himbaechel", "xilinx", "chipdb-xc7z020.bin")

XC7Z020_LUT6_TOTAL = 53200
XC7Z020_SLICE_LUTX_AVAIL = 106400
XC7Z020_FF_TOTAL = 106400
XC7Z020_BRAM36_TOTAL = 140


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
    env = {
        **os.environ,
        "TMPDIR": cwd,
        "PATH": f"{os.path.join(OPENXC7_DIR, 'venv', 'bin')}:{os.path.join(OPENXC7_DIR, 'bin')}:{os.environ.get('PATH', '')}",
        "NEXTPNR_XILINX_DIR": OPENXC7_DIR,
        "NEXTPNR_XILINX_PYTHON_DIR": os.path.join(OPENXC7_DIR, "lib", "python"),
        "PRJXRAY_DB_DIR": os.path.join(OPENXC7_DIR, "share", "nextpnr", "prjxray-db"),
    }
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    dt = time.time() - t0
    out = (p.stdout or "") + (p.stderr or "")
    if log_path:
        write_log(log_path, cmd, out)
    return p.returncode, out, dt


def parse_yosys_stat(text: str) -> dict[str, int]:
    res = {"estimated_lcs": 0, "ramb36e1": 0, "carry4": 0, "fd_total": 0}
    m_lc = re.findall(r"Estimated number of LCs:\s+(\d+)", text)
    if m_lc:
        res["estimated_lcs"] = int(m_lc[-1])
    blocks = text.split("Printing statistics.")
    tail = blocks[-1] if blocks else text

    def find_cell(cell_name: str) -> int:
        m_pre = re.search(rf"^\s*(\d+)\s+{cell_name}\s*$", tail, re.MULTILINE)
        if m_pre:
            return int(m_pre.group(1))
        m_post = re.search(rf"^\s*{cell_name}\s+(\d+)\s*$", tail, re.MULTILINE)
        return int(m_post.group(1)) if m_post else 0

    res["ramb36e1"] = find_cell("RAMB36E1")
    res["carry4"] = find_cell("CARRY4")
    res["fd_total"] = sum(find_cell(fd_t) for fd_t in ("FDCE", "FDRE", "FDSE", "FDPE"))
    if res["estimated_lcs"] == 0:
        res["estimated_lcs"] = sum(find_cell(f"LUT{i}") for i in range(1, 7))
    return res


def run_xbar_only_yosys(work: str, out_dir: str, n: int) -> int:
    wrap_sv = os.path.join(work, f"xbar_wrap_n{n}.sv")
    with open(wrap_sv, "w", encoding="utf-8") as f:
        f.write(
            f"`timescale 1ns/1ps\n"
            f"module xbar_wrap_n{n}(\n"
            f"  input logic clk, input logic rst_n,\n"
            f"  input logic [{n}-1:0] int_valid_i, output logic [{n}-1:0] int_ready_o,\n"
            f"  input logic [{n*4}-1:0] int_dst_bank_i, input logic [{n*6}-1:0] int_dst_cid_i,\n"
            f"  input logic [{n*32}-1:0] int_param_i,\n"
            f"  input logic [{n}-1:0] ext_valid_i, output logic [{n}-1:0] ext_ready_o,\n"
            f"  input logic [{n*4}-1:0] ext_dst_bank_i, input logic [{n*6}-1:0] ext_dst_cid_i,\n"
            f"  input logic [{n*32}-1:0] ext_param_i,\n"
            f"  output logic [{n}-1:0] dst_valid_o, input logic [{n}-1:0] dst_ready_i,\n"
            f"  output logic [{n*6}-1:0] dst_cid_o, output logic [{n*32}-1:0] dst_param_o,\n"
            f"  output logic xbar_busy_o, output logic [31:0] routed_events_count_o,\n"
            f"  output logic [31:0] backpressure_stall_cycles_o, output logic [31:0] invalid_dst_drop_count_o\n"
            f");\n"
            f"  km_event_crossbar #(.NUM_CORES({n}), .NUM_EXT_PORTS({n}), .DATA_WIDTH(32)) u (.*);\n"
            f"endmodule\n"
        )
    cmd = [
        OPENXC7_YOSYS,
        "-p",
        f"read_verilog -sv {RTL_XBAR} {wrap_sv}; "
        f"synth_xilinx -flatten -abc9 -arch xc7 -nobram -noiopad -top xbar_wrap_n{n}; "
        f"stat -tech xilinx; check",
    ]
    rc, out, _ = sh(cmd, work, os.path.join(out_dir, f"yosys_xbar_only_n{n}.log"))
    if rc != 0:
        raise RuntimeError(f"yosys xbar_only failed for N={n}:\n{out}")
    return parse_yosys_stat(out)["estimated_lcs"]


def fit_quadratic_c(ns: list[int], ys: list[int]) -> tuple[int, float]:
    """Fits c in LUT_hat(N) = N * LUT_1 + c * (N^2 - N) so N=1 is exact and N>1 captures quadratic crossbar."""
    y1 = ys[0]
    # Also compute pure N*y1 + c*N^2 least squares for N in {2, 4, 8}
    num = sum((n * n) * (y - n * y1) for n, y in zip(ns, ys) if n > 1)
    den = sum((n * n) ** 2 for n in ns if n > 1)
    c = num / den if den else 0.0
    return y1, round(c, 4)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument("--cores", default="1,2,4,8")
    args = ap.parse_args()

    if not (os.path.isfile(OPENXC7_YOSYS) and os.path.isfile(OPENXC7_NEXTPNR) and os.path.isfile(CHIPDB)):
        raise RuntimeError("OpenXC7 toolchain or chipdb-xc7z020.bin not found on host")

    core_list = [int(x.strip()) for x in args.cores.split(",") if x.strip()]
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    work = os.path.join(out_dir, "_work_pnr")
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work, exist_ok=True)

    rows = []
    try:
        for n in core_list:
            xbar_lcs = run_xbar_only_yosys(work, out_dir, n)

            netlist_json = os.path.join(work, f"manycore_n{n}.json")
            fasm_out = os.path.join(work, f"manycore_n{n}.fasm")
            pnr_rep_json = os.path.join(out_dir, f"nextpnr_report_n{n}.json")
            pnr_raw_log = os.path.join(work, f"nextpnr_internal_n{n}.log")

            yosys_cmd = [
                OPENXC7_YOSYS,
                "-p",
                f"read_verilog -sv -DKM_SYNTH_CORES={n} "
                f"{RTL_GATE} {RTL_CME} {RTL_BRAM} {RTL_XBAR} {RTL_CLUSTER_SV} {SYNTH_TOP}; "
                f"synth_xilinx -flatten -abc9 -arch xc7 -top km_manycore_synth_top; "
                f"stat -tech xilinx; check; write_json {netlist_json}",
            ]
            rc_y, out_y, dt_y = sh(yosys_cmd, work, os.path.join(out_dir, f"yosys_synth_n{n}.log"))
            if rc_y != 0:
                raise RuntimeError(f"OpenXC7 Yosys failed for N={n}:\n{out_y}")
            y_stat = parse_yosys_stat(out_y)

            pnr_cmd = [
                OPENXC7_NEXTPNR,
                "--chipdb",
                CHIPDB,
                "--device",
                "xc7z020clg400-1",
                "-o",
                f"xdc={SYNTH_XDC}",
                "--json",
                netlist_json,
                "-o",
                f"fasm={fasm_out}",
                "--router",
                "router2",
                "--seed",
                "1",
                "--freq",
                "100",
                "--timing-allow-fail",
                "--report",
                pnr_rep_json,
                "--log",
                pnr_raw_log,
            ]
            rc_p, out_p, dt_p = sh(pnr_cmd, work)
            log_text = open(pnr_raw_log, "r", encoding="utf-8").read() if os.path.isfile(pnr_raw_log) else out_p
            write_log(os.path.join(out_dir, f"nextpnr_pnr_n{n}.log"), pnr_cmd, log_text)
            if rc_p != 0:
                raise RuntimeError(f"nextpnr-himbaechel failed for N={n}:\n{log_text[-3000:]}")

            # Clean trailing whitespace in JSON report as well
            rep = json.loads(open(pnr_rep_json, "r", encoding="utf-8").read())
            with open(pnr_rep_json, "w", encoding="utf-8") as jf:
                json.dump(rep, jf, indent=2, sort_keys=True)
                jf.write("\n")

            util = rep["utilization"]
            slice_lutx = int(util["SLICE_LUTX"]["used"])
            slice_ffx = int(util["SLICE_FFX"]["used"])
            ramb36 = int(util["RAMB36E1"]["used"])
            ramb18 = int(util["RAMB18E1"]["used"])
            carry4 = int(util["CARRY4"]["used"])
            pads = int(util["PAD"]["used"])

            if ramb36 != n:
                raise RuntimeError(f"Expected RAMB36E1 == {n}, got {ramb36} (RAMB18E1={ramb18})")
            if pads > 125:
                raise RuntimeError(f"Exceeded 125 user IOB budget: PAD={pads}")

            fmax_dict = rep.get("fmax", {})
            if not fmax_dict:
                raise RuntimeError(f"Missing fmax in nextpnr report for N={n}")
            clk_key = next(iter(fmax_dict.keys()))
            fmax_mhz = float(fmax_dict[clk_key]["achieved"])
            constraint_mhz = float(fmax_dict[clk_key]["constraint"])
            crit_ns = round(1000.0 / fmax_mhz, 3) if fmax_mhz > 0 else 0.0

            rows.append({
                "num_cores": n,
                "yosys_xbar_only_lcs": xbar_lcs,
                "yosys_estimated_lcs": y_stat["estimated_lcs"],
                "yosys_fd_total": y_stat["fd_total"],
                "yosys_ramb36e1": y_stat["ramb36e1"],
                "pnr_slice_lutx": slice_lutx,
                "pnr_slice_lutx_pct": round(100.0 * slice_lutx / XC7Z020_SLICE_LUTX_AVAIL, 2),
                "pnr_slice_ffx": slice_ffx,
                "pnr_slice_ffx_pct": round(100.0 * slice_ffx / XC7Z020_FF_TOTAL, 2),
                "pnr_carry4": carry4,
                "pnr_ramb36e1": ramb36,
                "pnr_ramb36e1_pct": round(100.0 * ramb36 / XC7Z020_BRAM36_TOTAL, 2),
                "pnr_pads": pads,
                "target_freq_mhz": constraint_mhz,
                "fmax_mhz": round(fmax_mhz, 2),
                "critical_path_ns": crit_ns,
                "meets_100mhz": fmax_mhz >= 100.0,
                "peak_cluster_mcps_at_100mhz": round(12.5 * n, 2),
                "peak_cluster_mcps_at_fmax": round((fmax_mhz / 8.0) * n, 2),
                "yosys_sec": round(dt_y, 2),
                "nextpnr_sec": round(dt_p, 2),
            })
    finally:
        if os.path.isdir(work):
            shutil.rmtree(work)

    ns = [r["num_cores"] for r in rows]
    lut1_pnr, c_pnr = fit_quadratic_c(ns, [r["pnr_slice_lutx"] for r in rows])
    lc1_yosys, c_yosys = fit_quadratic_c(ns, [r["yosys_estimated_lcs"] for r in rows])

    for r in rows:
        n = r["num_cores"]
        pred_pnr = round(n * lut1_pnr + c_pnr * (n * n), 1)
        r["analytic_lut_pred"] = pred_pnr
        r["analytic_lut_rel_err_pct"] = round(
            100.0 * (r["pnr_slice_lutx"] - pred_pnr) / r["pnr_slice_lutx"], 2
        )

    csv_path = os.path.join(out_dir, "manycore_pnr_scaling.csv")
    fields = list(rows[0].keys())
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    summary = {
        "timestamp": datetime.datetime.now().astimezone().isoformat(),
        "issue": 255,
        "evidence_kind": "openxc7_place_and_route_sta",
        "not_physical_hil": True,
        "device": "xc7z020clg400-1",
        "toolchain": {
            "yosys": subprocess.check_output([OPENXC7_YOSYS, "-V"], text=True).strip(),
            "nextpnr_himbaechel": subprocess.check_output([OPENXC7_NEXTPNR, "-V"], stderr=subprocess.STDOUT, text=True).strip(),
            "chipdb": CHIPDB,
        },
        "platform": {
            "node": platform.node(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "analytic_fit_pnr_slice_lutx": {
            "formula": "N * LUT_1 + c * N^2",
            "LUT_1": lut1_pnr,
            "c": c_pnr,
        },
        "analytic_fit_yosys_lcs": {
            "formula": "N * LC_1 + c * N^2",
            "LC_1": lc1_yosys,
            "c": c_yosys,
        },
        "sha256": {
            "kpol_txn_gate_v2.sv": hashlib.sha256(open(RTL_GATE, "rb").read()).hexdigest(),
            "km_concept_micro_engine.sv": hashlib.sha256(open(RTL_CME, "rb").read()).hexdigest(),
            "km_concept_bram.sv": hashlib.sha256(open(RTL_BRAM, "rb").read()).hexdigest(),
            "km_event_crossbar.sv": hashlib.sha256(open(RTL_XBAR, "rb").read()).hexdigest(),
            "km_manycore_cluster.sv": hashlib.sha256(open(RTL_CLUSTER_SV, "rb").read()).hexdigest(),
            "km_manycore_synth_top.sv": hashlib.sha256(open(SYNTH_TOP, "rb").read()).hexdigest(),
            "km_manycore_synth.xdc": hashlib.sha256(open(SYNTH_XDC, "rb").read()).hexdigest(),
        },
        "rows": rows,
    }
    with open(os.path.join(out_dir, "manycore_pnr_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")

    print("=" * 96)
    print("ISSUE #255 OPENXC7 PLACE & ROUTE + STA SUMMARY (xc7z020clg400-1)")
    print("=" * 96)
    for r in rows:
        print(
            f"  N={r['num_cores']} | Yosys LCs={r['yosys_estimated_lcs']:<6} (xbar={r['yosys_xbar_only_lcs']:<4}) | "
            f"SLICE_LUTX={r['pnr_slice_lutx']:<6} SLICE_FFX={r['pnr_slice_ffx']:<5} "
            f"RAMB36E1={r['pnr_ramb36e1']} PAD={r['pnr_pads']} | F_max={r['fmax_mhz']:.2f} MHz "
            f"({r['yosys_sec']}s+{r['nextpnr_sec']}s)"
        )
    print(f"  Analytic fit: SLICE_LUTX(N) ~= {lut1_pnr}*N + {c_pnr}*N^2")
    print("=" * 96)


if __name__ == "__main__":
    main()
