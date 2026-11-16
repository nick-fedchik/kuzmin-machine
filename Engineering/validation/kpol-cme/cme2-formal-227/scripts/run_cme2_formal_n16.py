#!/usr/bin/env python3
"""Issues #237, #242: Compositional formal verification of CFG-P / KPOL-CME-2 at NUM_CONCEPTS=16.

Parameters:
  NUM_CONCEPTS = 16, QUEUE_DEPTH = 16, DATA_WIDTH = 32, ADDR_WIDTH = 6 (64 words in BRAM).

Checks:
  1. P1_n16_ind (unbounded k-induction, `yosys-smtbmc -s z3 -i -t 5`):
     - P_bigdot_mutex_pulse / P_bigdot_mutex_cme: !(commit && reject)
     - P1a..P1e: bram_b_we_o == 0, all 16 W0 slots preserved, no cascade on reject
  2. P2_rank_step_n16 (unbounded k-induction, `yosys-smtbmc -s z3 -i -t 10`):
     - Lyapunov rank V(cid) = 15 - cid strictly decreases on any cascade step
  3. P3_liveness_n16_ind (unbounded k-induction, `yosys-smtbmc -s z3 -i -t 12`):
     - Exact 8-cycle transaction step with/without cascade and 2 external triggers (closes #237)
  4. cover_n16 (`yosys-smtbmc -s z3 -c -t 42`):
     - Non-vacuity: 4-commit cascade reaching cid=15, reject_pulse_o, 2 external triggers
  5. Mutants (AGENTS.md §4.1):
     - M_bigdot_dual_pulse, M_we_on_reject, M_cascade_on_reject, M_rank_violation_self_sub
"""

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
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", ".."))
RTL_DIR = os.path.join(REPO_ROOT, "Engineering", "hw", "rtl", "core")
RTL_GATE = os.path.join(RTL_DIR, "kpol_txn_gate_v2.sv")
RTL_CME = os.path.join(RTL_DIR, "km_concept_micro_engine.sv")
RTL_BRAM = os.path.join(RTL_DIR, "km_concept_bram.sv")
RTL_SEQ = os.path.join(RTL_DIR, "km_autonomous_sequencer.sv")
PROPS = os.path.join(HERE, "cme2_formal_n16_props.sv")
DEFAULT_OUT = os.path.join(HERE, "..", "raw", "n16_compositional")

CONNECT_LINES = "\n".join([
    "cd cme2_formal_n16_props",
    "connect -set obs_state_q \\dut_seq.state_q",
    "connect -set obs_fifo_count_q \\dut_seq.fifo_count_q",
    "connect -set obs_fifo_wr_ptr_q \\dut_seq.fifo_wr_ptr_q",
    "connect -set obs_fifo_rd_ptr_q \\dut_seq.fifo_rd_ptr_q",
    "connect -set obs_cme_event_valid \\dut_seq.cme_event_valid",
    "connect -set obs_cme_committed \\dut_seq.cme_committed",
    "connect -set obs_cme_rejected \\dut_seq.cme_rejected",
    "connect -set obs_cme_trigger_subscriber \\dut_seq.cme_trigger_subscriber",
    "connect -set obs_cme_subscriber_cid \\dut_seq.cme_subscriber_cid",
    "connect -set obs_cascade_req \\dut_seq.cascade_req",
    "connect -set obs_active_cid_q \\dut_seq.active_cid_q",
    "connect -set obs_cascade_pending_valid_q \\dut_seq.cascade_pending_valid_q",
    "connect -set obs_cascade_pending_cid_q \\dut_seq.cascade_pending_cid_q",
    "connect -set obs_desc_w2_q \\dut_seq.desc_w2_q",
    "cd ..",
])

MUTANTS = [
    (
        "M_bigdot_dual_pulse",
        "safety_bmc",
        ["FORMAL_SAFETY"],
        15,
        False,
        "simultaneous commit_pulse_o and reject_pulse_o",
        "    assign commit_pulse_o           = (state_q == ST_EVAL_GATE) && cme_committed;\n"
        "    assign reject_pulse_o           = (state_q == ST_EVAL_GATE) && !cme_committed;",
        "    assign commit_pulse_o           = (state_q == ST_EVAL_GATE) && cme_committed;\n"
        "    assign reject_pulse_o           = (state_q == ST_EVAL_GATE);",
    ),
    (
        "M_we_on_reject",
        "safety_bmc",
        ["FORMAL_SAFETY"],
        15,
        False,
        "bram_b_we_o asserted on reject",
        "                    end else begin\n"
        "                        rej_count_q <= rej_count_q + 32'd1;\n"
        "                        state_q     <= ST_IDLE; // Відхилена транзакція не оновлює пам'ять\n"
        "                    end",
        "                    end else begin\n"
        "                        rej_count_q    <= rej_count_q + 32'd1;\n"
        "                        bram_b_addr_o  <= {active_cid_q, 2'b00};\n"
        "                        bram_b_wdata_o <= cme_updated_state ^ 32'h1;\n"
        "                        bram_b_wstrb_o <= 4'b1111;\n"
        "                        bram_b_we_o    <= 1'b1;\n"
        "                        state_q        <= ST_IDLE;\n"
        "                    end",
    ),
    (
        "M_cascade_on_reject",
        "safety_bmc",
        ["FORMAL_SAFETY"],
        15,
        False,
        "cascade subscription requested on reject",
        "    wire cascade_req   = (state_q == ST_EVAL_GATE) && cme_committed &&\n"
        "                         cme_trigger_subscriber && (cme_subscriber_cid[5:0] != active_cid_q);",
        "    wire cascade_req   = (state_q == ST_EVAL_GATE) &&\n"
        "                         (cme_committed || cme_rejected) &&\n"
        "                         (cme_trigger_subscriber || cme_rejected) &&\n"
        "                         (cme_subscriber_cid[5:0] != active_cid_q);",
    ),
    (
        "M_rank_violation_self_sub",
        "rank_step_bmc",
        ["FORMAL_RANK_STEP"],
        15,
        False,
        "backward cascade cid violates Lyapunov rank monotonicity",
        "                ST_CAP_W3_STROBE: begin\n"
        "                    // BRAM видає Word 3 на цьому такті\n"
        "                    desc_w3_q       <= bram_b_rdata_i;",
        "                ST_CAP_W3_STROBE: begin\n"
        "                    // Mutant: backward/cyclic subscriber cid\n"
        "                    desc_w3_q       <= (active_cid_q > 6'd0) ? {26'd0, active_cid_q - 6'd1} : bram_b_rdata_i;",
    ),
]


def clean_lines(text):
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


def write_log(log_path, cmd, text):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    ts = datetime.datetime.now().astimezone().isoformat()
    header = f"# cmd: {' '.join(cmd)}\n# timestamp: {ts}\n"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(clean_lines(header + text))


def sh(cmd, cwd, log_path=None):
    t0 = time.time()
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    dt = time.time() - t0
    out = (p.stdout or "") + (p.stderr or "")
    if log_path:
        write_log(log_path, cmd, out)
    return p.returncode, out, dt


def build_smt2(work, out_dir, seq_path, defines, tag, use_memory_map=True):
    smt2 = os.path.join(work, f"{tag}.smt2")
    ys = os.path.join(work, f"{tag}.ys")
    def_flags = " ".join(f"-D{d}" for d in defines)
    mem_pass = "memory_map\n" if use_memory_map else ""
    script = (
        f"read_verilog -sv -formal {def_flags} "
        f"{RTL_GATE} {RTL_CME} {RTL_BRAM} {seq_path} {PROPS}\n"
        "prep -top cme2_formal_n16_props\n"
        "flatten\n"
        f"{CONNECT_LINES}\n"
        "async2sync\n"
        "chformal -assume -early\n"
        "opt_clean\n"
        f"{mem_pass}"
        "opt -fast\n"
        "dffunmap\n"
        f"write_smt2 -wires {smt2}\n"
    )
    with open(ys, "w", encoding="utf-8") as f:
        f.write(script)
    rc, log, _ = sh(["yosys", "-q", ys], work, os.path.join(out_dir, f"{tag}.yosys.log"))
    if rc != 0:
        raise RuntimeError(f"yosys failed for {tag}:\n{log}")
    return smt2


def run_smtbmc(work, out_dir, seq_path, defines, mode, depth, tag, keep_vcd=False, use_memory_map=True):
    smt2 = build_smt2(work, out_dir, seq_path, defines, tag, use_memory_map=use_memory_map)
    vcd = os.path.join(out_dir, f"{tag}.vcd")
    cmd = ["yosys-smtbmc", "-s", "z3"]
    if mode == "ind":
        cmd += ["-i", "-t", str(depth)]
    elif mode == "cover":
        cmd += ["-c", "-t", str(depth)]
    else:
        cmd += ["-t", str(depth)]
        if keep_vcd:
            cmd += ["--dump-vcd", vcd]
    cmd.append(smt2)

    rc, out, dt = sh(cmd, work, os.path.join(out_dir, f"{tag}.log"))
    m = re.findall(r"Status: (\w+)", out)
    status = m[-1] if m else "ERROR"
    if not keep_vcd and os.path.exists(vcd):
        os.remove(vcd)
    return {
        "engine": f"smtbmc z3 {mode} t={depth}",
        "status": status,
        "seconds": round(dt, 3),
        "failed": ";".join(sorted(set(re.findall(r"Assert failed in \S+: (\w+)", out)))),
        "reached": ";".join(sorted(set(re.findall(r"Reached cover statement .*: (\w+)", out)))),
        "unreached": ";".join(sorted(set(re.findall(r"Unreached cover statement .*: (\w+)", out)))),
        "vcd": os.path.basename(vcd) if (keep_vcd and os.path.exists(vcd)) else "",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument("--fast", action="store_true",
                    help="Run fast P1/P2 k-induction + 4 mutants (skip P3 induction & cover)")
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    work = os.path.join(out_dir, "_work")
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work, exist_ok=True)

    with open(RTL_SEQ, "r", encoding="utf-8") as f:
        seq_src = f.read()

    rows = []
    try:
        # 1. P1_n16_ind: Unbounded k-induction for Big Dot mutex & Fail-Closed preservation
        rows.append({
            "design": "original (CFG-P N=16)",
            "check": "P1_n16_ind",
            **run_smtbmc(work, out_dir, RTL_SEQ, ["FORMAL_SAFETY", "FORMAL_INDUCTION"],
                         "ind", 5, "orig_n16_safety_ind", use_memory_map=True),
        })
        # 2. P2_rank_step_n16: Unbounded k-induction for Lyapunov rank monotonicity
        rows.append({
            "design": "original (CFG-P N=16)",
            "check": "P2_rank_step_n16",
            **run_smtbmc(work, out_dir, RTL_SEQ, ["FORMAL_RANK_STEP", "FORMAL_INDUCTION"],
                         "ind", 10, "orig_n16_rank_ind", use_memory_map=True),
        })
        if not args.fast:
            # 3. P3_liveness_n16_ind: Unbounded k-induction for 8-cycle step w/ & w/o cascade + 2 triggers
            rows.append({
                "design": "original (CFG-P N=16)",
                "check": "P3_liveness_n16_ind",
                **run_smtbmc(work, out_dir, RTL_SEQ, ["FORMAL_LIVENESS", "FORMAL_INDUCTION"],
                             "ind", 12, "orig_n16_liveness_ind", use_memory_map=False),
            })
            # 4. cover_n16: Non-vacuity (4-commit cascade to cid=15, reject, 2 external triggers)
            rows.append({
                "design": "original (CFG-P N=16)",
                "check": "cover_n16",
                **run_smtbmc(work, out_dir, RTL_SEQ, ["FORMAL_COVER"],
                             "cover", 42, "orig_n16_cover", use_memory_map=True),
            })

        # 5. Mutants (negative controls)
        for mid, check_name, defines, depth, use_mm, desc, old, new in MUTANTS:
            n = seq_src.count(old)
            if n != 1:
                raise RuntimeError(f"{mid}: expected 1 match in {RTL_SEQ}, found {n}")
            mpath = os.path.join(work, f"{mid}_seq.sv")
            with open(mpath, "w", encoding="utf-8") as f:
                f.write(seq_src.replace(old, new))
            rows.append({
                "design": f"{mid}: {desc}",
                "check": check_name,
                **run_smtbmc(work, out_dir, mpath, defines,
                             "bmc", depth, mid, keep_vcd=True, use_memory_map=use_mm),
            })
    finally:
        if os.path.isdir(work):
            shutil.rmtree(work)

    csv_path = os.path.join(out_dir, "cme2_n16_results.csv")
    fields = ["design", "check", "engine", "status", "seconds", "failed", "reached", "unreached", "vcd"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    orig_ok = all(r["status"] == "PASSED" for r in rows if r["design"].startswith("original"))
    muts_ok = all(r["status"] == "FAILED" and bool(r["vcd"]) for r in rows if not r["design"].startswith("original"))
    verdict = "PASSED" if (orig_ok and muts_ok) else "FAILED"

    provenance = {
        "timestamp": datetime.datetime.now().astimezone().isoformat(),
        "issues": [237, 242],
        "parameters": {"NUM_CONCEPTS": 16, "QUEUE_DEPTH": 16, "DATA_WIDTH": 32, "ADDR_WIDTH": 6},
        "platform": {
            "node": platform.node(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "sha256": {
            "kpol_txn_gate_v2.sv": hashlib.sha256(open(RTL_GATE, "rb").read()).hexdigest(),
            "km_concept_micro_engine.sv": hashlib.sha256(open(RTL_CME, "rb").read()).hexdigest(),
            "km_concept_bram.sv": hashlib.sha256(open(RTL_BRAM, "rb").read()).hexdigest(),
            "km_autonomous_sequencer.sv": hashlib.sha256(open(RTL_SEQ, "rb").read()).hexdigest(),
            "cme2_formal_n16_props.sv": hashlib.sha256(open(PROPS, "rb").read()).hexdigest(),
        },
        "verdict": verdict,
        "rows": rows,
    }
    with open(os.path.join(out_dir, "cme2_n16_provenance.json"), "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2)

    print("=" * 92)
    print("CME2-FORMAL-242 SUMMARY (Issues #237, #242 — NUM_CONCEPTS=16 Compositional)")
    print("=" * 92)
    for r in rows:
        extra = ""
        if r["failed"]:
            extra += f" [failed: {r['failed']}]"
        if r["reached"]:
            extra += f" [reached: {r['reached']}]"
        if r["vcd"]:
            extra += f" [vcd: {r['vcd']}]"
        print(f"  {r['design']:<48} | {r['engine']:<22} | {r['status']:<6}{extra} ({r['seconds']}s)")
    print("-" * 92)
    print(f"VERDICT: {verdict}")
    print("=" * 92)

    if verdict != "PASSED":
        sys.exit(1)


if __name__ == "__main__":
    main()
