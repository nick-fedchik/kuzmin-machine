#!/usr/bin/env python3
"""AV-08: resource and f_max scaling vs N on xc7z020 (openXC7: yosys + nextpnr-himbaechel).

Series (all RTL from hw/rtl is used unmodified):
  S1_lanes  N parallel concept lanes, each = km_predicate_evaluator + kpol_txn_gate
            (invariant from the evaluator, current_state fed back from the gate).
  S1_stub   control: same harness, lanes replaced by wires (no DUT logic).
            DUT cost = S1_lanes - S1_stub.
  S2_bram   km_concept_bram, NUM_CONCEPTS = N (ADDR_WIDTH = clog2(4N)).
  S3_rcfc   km_rcfc_engine, NUM_SLOTS = N (synthesis only; N <= 64 because slot_sel_i is 6 bit).

Harness: inputs come from a 1-pin serial shift register (S1: then a per-lane registered
systolic chain), outputs are folded by a pipelined XOR tree into 1 pin (xc7z020clg400 has ~125 user IOs, the DUTs need more).
Clock: PYNQ-Z1 sysclk pin H16, constraint 100 MHz. Synthesis as in build_pynq_z1_openxc7.sh
plus -nosrl, so harness delay lines stay as FFs identically in S1_lanes and S1_stub.

Pre-registered criterion (AV plan, sec. 4.2): the N at which median f_max < 100 MHz is the
limit; the form of the dependence is taken from data. nextpnr STA is not sign-off.

Usage: python3 run_av08_scaling.py [--seeds 1 2 3] [--jobs 6] [--series S1_lanes ...] [--ns 4 8 ...]
"""
import argparse
import concurrent.futures as cf
import csv
import datetime
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
KM = REPO_ROOT
RTL = os.path.join(REPO_ROOT, "hw", "rtl")
# Повторний прогін пише в окремий каталог (сирі дані незмінні): AV08_OUT_DIR=/tmp/av08
OUT = os.environ.get("AV08_OUT_DIR", os.path.join(HERE, "..", "raw", "av08_scaling"))


def rtl_path(name):
    """Шукає RTL-файл за іменем у hw/rtl/**."""
    for root, _, files in sorted(os.walk(RTL)):
        if name in files:
            return os.path.join(root, name)
    raise FileNotFoundError(name)
OPENXC7 = os.environ.get("OPENXC7_DIR", os.path.expanduser("~/opt/openxc7"))
BUILD = os.environ.get("AV08_BUILD_DIR", os.path.expanduser("~/opt/openxc7-build/av08"))
CHIPDB = os.path.join(OPENXC7, "share/nextpnr/himbaechel/xilinx/chipdb-xc7z020.bin")
NS = [4, 8, 16, 32, 64, 128]

XDC = """set_property LOC H16 [get_ports clk]
set_property IOSTANDARD LVCMOS33 [get_ports clk]
set_property LOC D19 [get_ports rst_btn]
set_property IOSTANDARD LVCMOS33 [get_ports rst_btn]
set_property LOC D20 [get_ports din]
set_property IOSTANDARD LVCMOS33 [get_ports din]
set_property LOC R14 [get_ports dout]
set_property IOSTANDARD LVCMOS33 [get_ports dout]
"""

# ---------------------------------------------------------------- harness

def xor_tree(src, width):
    """Pipelined XOR reduction: 6 inputs per LUT, one register stage per level."""
    lines, level, cur, cw = [], 0, src, width
    while cw > 1:
        nw = (cw + 5) // 6
        pad = nw * 6 - cw
        rhs = f"{{{pad}'b0, {cur}}}" if pad else cur
        lines += [
            f"    wire [{nw*6-1}:0] xp{level} = {rhs};",
            f"    reg  [{nw-1}:0] xr{level};",
            f"    genvar xg{level};",
            f"    for (xg{level} = 0; xg{level} < {nw}; xg{level} = xg{level} + 1) begin : gx{level}",
            f"        always @(posedge clk) xr{level}[xg{level}] <= ^xp{level}[xg{level}*6 +: 6];",
            "    end",
        ]
        cur, cw, level = f"xr{level}", nw, level + 1
    return lines, cur


def top(in_w, out_w, body):
    tree, last = xor_tree("dut_o", out_w)
    return "\n".join([
        "`timescale 1ns/1ps",
        "module av08_top (input wire clk, input wire rst_btn, input wire din, output reg dout);",
        "    reg [1:0] rsync;",
        "    always @(posedge clk) rsync <= {rsync[0], ~rst_btn};",
        "    wire rst_n = rsync[1];",
        f"    reg [{in_w-1}:0] sr;",
        f"    always @(posedge clk) sr <= {{sr[{in_w-2}:0], din}};",
        f"    wire [{out_w-1}:0] dut_o;",
        *body,
        *tree,
        f"    always @(posedge clk) dout <= {last};",
        "endmodule",
        "",
    ])


LANE_IN = 32 + 32 + 32 + 8 + 6   # cand, lo, hi, rule_cfg, 6 control bits
LANE_OUT = 32 + 7 + 8   # state, 7 gate flags, predicate vector


def lane_inputs(i):
    """Systolic input chain: lane i registers a 7-bit rotation of lane i-1's input word.
    Keeps fan-out local (no shared high-fan-out net) and makes every lane distinct.
    Harness cost is 110 FF per lane, identical in S1_stub, so it cancels in S1_net."""
    if i == 0:
        # mix neighbours once, otherwise w0 bits are provably equal to delayed sr bits and get merged
        d = f"sr ^ {{sr[0], sr[{LANE_IN-1}:1]}}"
    else:
        d = f"{{w{i-1}[6:0], w{i-1}[{LANE_IN-1}:7]}}"
    return [f"    reg [{LANE_IN-1}:0] w{i};",
            f"    always @(posedge clk) w{i} <= {d};"]


def s1_lanes(n, stub=False):
    body = []
    for i in range(n):
        body += lane_inputs(i)
        o = i * LANE_OUT
        if stub:
            body.append(f"    assign dut_o[{o} +: {LANE_OUT}] = w{i}[{LANE_OUT-1}:0];")
            continue
        body += [
            f"    wire [31:0] st{i}; wire inv{i}, bd{i}; wire [7:0] pv{i};",
            f"    km_predicate_evaluator #(.DATA_WIDTH(32)) pe{i} (",
            f"        .candidate_value_i(w{i}[31:0]), .candidate_known_i(w{i}[104]),",
            f"        .current_state_i(st{i}), .lower_bound_i(w{i}[63:32]), .upper_bound_i(w{i}[95:64]),",
            f"        .rule_cfg_i(w{i}[103:96]), .predicate_vector_o(pv{i}),",
            f"        .hw_invariant_ok_o(inv{i}), .big_dot_flag_o(bd{i}));",
            f"    kpol_txn_gate #(.DATA_WIDTH(32)) g{i} (",
            f"        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w{i}[105]),",
            f"        .candidate_known_i(w{i}[104]), .candidate_value_i(w{i}[31:0]),",
            f"        .assumption_known_i(w{i}[106]), .assumption_true_i(w{i}[107]),",
            f"        .invariant_known_i(1'b1), .invariant_true_i(inv{i}),",
            f"        .hazard_known_i(w{i}[108]), .hazard_true_i(w{i}[109]),",
            f"        .state_o(st{i}), .committed_o(dut_o[{o+32}]),",
            f"        .rejected_o(dut_o[{o+33}]), .rejected_input_o(dut_o[{o+34}]),",
            f"        .rejected_invariant_o(dut_o[{o+35}]), .changed_o(dut_o[{o+36}]),",
            f"        .hazard_observed_o(dut_o[{o+37}]), .unknown_hazard_o(dut_o[{o+38}]));",
            f"    assign dut_o[{o} +: 32] = st{i};",
            f"    assign dut_o[{o+39} +: 8] = pv{i};",
        ]
    # the last chain word is also observed so that no chain register is pruned
    body.append(f"    assign dut_o[{n*LANE_OUT} +: {LANE_IN}] = w{n-1};")
    return top(LANE_IN, n * LANE_OUT + LANE_IN, body), ["km_predicate_evaluator.sv", "kpol_txn_gate.sv"]


def s2_bram(n):
    aw = max(1, math.ceil(math.log2(4 * n)))
    in_w = 2 * (aw + 37)
    b = aw + 37
    body = [
        f"    km_concept_bram #(.NUM_CONCEPTS({n}), .DATA_WIDTH(32), .ADDR_WIDTH({aw})) dut (",
        "        .clk(clk), .rst_n(rst_n),",
        f"        .a_addr_i(sr[{aw-1}:0]), .a_wdata_i(sr[{aw+31}:{aw}]), .a_wstrb_i(sr[{aw+35}:{aw+32}]),",
        f"        .a_we_i(sr[{aw+36}]), .a_rdata_o(dut_o[31:0]),",
        f"        .b_addr_i(sr[{b+aw-1}:{b}]), .b_wdata_i(sr[{b+aw+31}:{b+aw}]),",
        f"        .b_wstrb_i(sr[{b+aw+35}:{b+aw+32}]), .b_we_i(sr[{b+aw+36}]), .b_rdata_o(dut_o[63:32]),",
        "        .collision_detected_o(dut_o[64]));",
    ]
    return top(in_w, 65, body), ["km_concept_bram.sv"]


def s3_rcfc(n):
    body = [
        f"    km_rcfc_engine #(.NUM_SLOTS({n})) dut (",
        "        .clk(clk), .rst_n(rst_n), .start_i(sr[0]), .cmd_i(sr[3:1]),",
        "        .delay_param_i(sr[11:4]), .slot_sel_i(sr[17:12]),",
        "        .busy_o(dut_o[0]), .done_o(dut_o[1]), .tc01_pass_o(dut_o[2]), .tc02_pass_o(dut_o[3]),",
        "        .tc03_pass_o(dut_o[4]), .tc04_pass_o(dut_o[5]), .timeout_deadlock_error_o(dut_o[6]),",
        "        .event_drop_error_o(dut_o[7]), .current_tc_o(dut_o[11:8]),",
        "        .events_processed_o(dut_o[27:12]), .cycle_count_o(dut_o[59:28]),",
        "        .events_enqueued_o(dut_o[75:60]), .events_dropped_o(dut_o[91:76]),",
        "        .result_o(dut_o[123:92]), .slot_state_o(dut_o[126:124]),",
        "        .slot_wait_cycles_o(dut_o[134:127]), .slot_payload_lo_o(dut_o[150:135]));",
    ]
    return top(18, 151, body), ["km_rcfc_engine.sv"]


# name -> (generator, N list, run place&route)
SERIES = {
    "S1_lanes": (lambda n: s1_lanes(n), NS, True),
    "S1_stub": (lambda n: s1_lanes(n, stub=True), NS, True),
    "S2_bram": (s2_bram, NS, True),
    "S3_rcfc": (s3_rcfc, [4, 8, 16, 32, 64], False),
}

# ---------------------------------------------------------------- tools

def env():
    e = dict(os.environ)
    e["PATH"] = f"{OPENXC7}/venv/bin:{OPENXC7}/bin:" + e["PATH"]
    return e


def run(cmd, cwd, log, timeout=None):
    # Stream straight to the log so long runs can be inspected while in progress.
    with open(log, "w") as f:
        p = subprocess.Popen(cmd, cwd=cwd, env=env(), stdout=f, stderr=subprocess.STDOUT, text=True)
        try:
            rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            f.write(f"\nAV08: killed after timeout {timeout} s\n")
            rc = "TIMEOUT"
    return rc, open(log).read()


def synth(series, n):
    gen = SERIES[series][0]
    src, deps = gen(n)
    d = os.path.join(BUILD, f"{series}_N{n}")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "av08_top.v"), "w") as f:
        f.write(src)
    with open(os.path.join(d, "av08.xdc"), "w") as f:
        f.write(XDC)
    files = " ".join(rtl_path(x) for x in deps)
    script = (f"read_verilog -sv {files} av08_top.v; "
              "synth_xilinx -flatten -abc9 -nosrl -arch xc7 -top av08_top; "
              "tee -o stat.txt stat; tee -q -o stat.json stat -json; write_json synth.json")
    rc, _ = run(["yosys", "-p", script], d, os.path.join(d, "yosys.log"))
    if rc:
        raise RuntimeError(f"yosys failed {series} N={n}: see {d}/yosys.log")
    return synth_stats(series, n)


def synth_stats(series, n):
    d = os.path.join(BUILD, f"{series}_N{n}")
    cells = json.load(open(os.path.join(d, "stat.json")))["design"]["num_cells_by_type"]
    pick = lambda pat: sum(v for k, v in cells.items() if re.fullmatch(pat, k))
    return {"series": series, "N": n,
            "lut": pick(r"LUT[1-6]"), "ff": pick(r"FD[CPRS]E?"), "srl": pick(r"SRL.*"),
            "carry4": pick(r"CARRY4"), "bram": pick(r"RAMB.*"),
            "lutram": pick(r"RAM(?!B).*"), "dsp": pick(r"DSP.*"), "dir": d}


def pnr(d, seed, timeout=None):
    rep = os.path.join(d, f"report_s{seed}.json")
    cmd = ["nextpnr-himbaechel", "--chipdb", CHIPDB, "--device", "xc7z020clg400-1",
           "-o", "xdc=av08.xdc", "--json", "synth.json", "--router", "router2",
           "--freq", "100", "--seed", str(seed), "--report", rep]
    if os.path.exists(rep):
        os.remove(rep)
    run(cmd, d, os.path.join(d, f"nextpnr_s{seed}.log"), timeout)
    return pnr_result(d, seed)


def pnr_result(d, seed):
    """Classify from artefacts only. nextpnr exits non-zero when the clock
    constraint is missed even though routing completed, so the exit code alone
    must not be read as a routing failure."""
    rep = os.path.join(d, f"report_s{seed}.json")
    log = os.path.join(d, f"nextpnr_s{seed}.log")
    text = open(log).read() if os.path.exists(log) else ""
    routed = "Router2 time" in text and "Program finished normally" in text
    if not os.path.exists(rep) or not routed:
        return {"seed": seed, "status": "NOT_ROUTED", "fmax_mhz": ""}
    r = json.load(open(rep))
    fm = [v["achieved"] for v in r["fmax"].values()]
    u = r["utilization"]
    met = bool(fm) and min(fm) >= 100
    return {"seed": seed, "status": "OK" if met else "TIMING_FAIL",
            "fmax_mhz": round(min(fm), 2) if fm else "",
            "placed_lutx": u["SLICE_LUTX"]["used"], "placed_ffx": u["SLICE_FFX"]["used"],
            "placed_carry4": u["CARRY4"]["used"],
            "placed_ramb18": u["RAMB18E1"]["used"] + 2 * u["RAMB36E1"]["used"]}


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def ver(cmd):
    try:
        out = subprocess.run(cmd, env=env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True).stdout.strip().splitlines()
        return out[0] if out else "unknown"
    except OSError:
        return "unavailable"


KEYS = ["series", "N", "seed", "status", "lut", "ff", "srl", "carry4", "bram", "lutram", "dsp",
        "fmax_mhz", "placed_lutx", "placed_ffx", "placed_carry4", "placed_ramb18"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--series", nargs="+", default=list(SERIES))
    ap.add_argument("--ns", type=int, nargs="+")
    ap.add_argument("--pnr-timeout", type=int, default=3600,
                    help="seconds per nextpnr run; exceeded runs are recorded as NOT_ROUTED")
    ap.add_argument("--reparse", action="store_true",
                    help="rebuild CSV from existing build dirs without running yosys/nextpnr")
    args = ap.parse_args()
    os.makedirs(BUILD, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)

    jobs = [(s, n) for s in args.series for n in SERIES[s][1] if not args.ns or n in args.ns]
    if args.reparse:
        syn = [synth_stats(s, n) for s, n in jobs]
    else:
        with cf.ProcessPoolExecutor(args.jobs) as ex:
            syn = list(ex.map(synth, *zip(*jobs)))
    pjobs = [(i, sd) for i, r in enumerate(syn) if SERIES[r["series"]][2] for sd in args.seeds]
    if args.reparse:
        pres = [pnr_result(syn[i]["dir"], sd) for i, sd in pjobs]
    else:
        with cf.ProcessPoolExecutor(args.jobs) as ex:
            pres = list(ex.map(pnr, [syn[i]["dir"] for i, _ in pjobs], [sd for _, sd in pjobs],
                               [args.pnr_timeout] * len(pjobs)))

    rows = []
    for i, r in enumerate(syn):
        base = {k: v for k, v in r.items() if k != "dir"}
        mine = [p for (j, _), p in zip(pjobs, pres) if j == i]
        if not mine:
            rows.append({**base, "seed": "", "status": "SYNTH_ONLY", "fmax_mhz": ""})
        rows += [{**base, **p} for p in mine]
        for f in ("stat.txt", "av08_top.v"):
            shutil.copy(os.path.join(r["dir"], f), os.path.join(OUT, f"{r['series']}_N{r['N']}_{f}"))
        for f in os.listdir(r["dir"]):
            if f.startswith("nextpnr_s") or f.startswith("report_s"):
                shutil.copy(os.path.join(r["dir"], f), os.path.join(OUT, f"{r['series']}_N{r['N']}_{f}"))

    path = os.path.join(OUT, "av08_results.csv")
    old = []
    if os.path.exists(path):
        done = {(r["series"], r["N"]) for r in rows}
        old = [r for r in csv.DictReader(open(path)) if (r["series"], int(r["N"])) not in done]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, KEYS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(old + rows, key=lambda r: (r["series"], int(r["N"]), str(r["seed"]))):
            w.writerow(r)

    def git(*a):
        return subprocess.run(["git", *a], cwd=KM, stdout=subprocess.PIPE, text=True).stdout.strip()

    prov = {
        "experiment": "AV-08",
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "host": platform.node(), "platform": platform.platform(), "cpus": os.cpu_count(),
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty_rtl": bool(git("status", "--porcelain", "--", RTL)),
        "rtl_sha256": {os.path.relpath(os.path.join(r, x), RTL): sha(os.path.join(r, x)) for r, _, fs in sorted(os.walk(RTL)) for x in sorted(fs)},
        "script_sha256": sha(os.path.abspath(__file__)),
        "yosys": ver(["yosys", "-V"]),
        "nextpnr": ver(["nextpnr-himbaechel", "--version"]),
        "chipdb_sha256": sha(CHIPDB),
        "device": "xc7z020clg400-1", "freq_constraint_mhz": 100,
        "seeds": args.seeds, "series": args.series, "ns": args.ns or "default",
        "pnr_timeout_s": args.pnr_timeout, "reparse_only": args.reparse,
    }
    with open(os.path.join(OUT, "av08_provenance.json"), "w") as f:
        json.dump(prov, f, indent=2)

    for r in rows:
        print(f"{r['series']:9} N={r['N']:<4} seed={r['seed']!s:2} {r['status']:10} LUT={r['lut']:<6} "
              f"FF={r['ff']:<6} SRL={r['srl']:<4} CARRY4={r['carry4']:<5} BRAM={r['bram']} "
              f"LUTRAM={r['lutram']} fmax={r['fmax_mhz']}")


if __name__ == "__main__":
    sys.exit(main())
