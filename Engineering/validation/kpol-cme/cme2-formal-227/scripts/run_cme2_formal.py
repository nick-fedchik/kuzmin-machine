#!/usr/bin/env python3
"""Issue #227: Formal verification of CFG-P and KPOL-CME-2 cascades via Yosys + Z3.

Engines & checks:
  * P1 (Fail-Closed State Preservation & No Cascade on Reject):
      - Unbounded k-induction (`yosys-smtbmc -s z3 -i -t 5`) for P1a, P1b, P1c, P1f;
      - Bounded Model Checking (`yosys-smtbmc -s z3 -t 20`) for P1a..P1f (incl. event conservation).
  * P2 (Bounded Acyclic Cascade Termination) & P3 (Exact Single-Transaction Latency):
      - Bounded Model Checking (`yosys-smtbmc -s z3 -t 52`) covering 16-cycle BRAM init + 36 active cycles (> 8*N+2 = 34).
  * Cover (Non-vacuity):
      - `yosys-smtbmc -s z3 -c -t 45` reaching >= 3 cascade commits and reject_pulse_o.
  * Negative controls (AGENTS.md §4.1):
      - M1_we_on_reject: asserts bram_b_we_o on reject (caught by P1a/P1c);
      - M2_cascade_on_reject: triggers cascade on reject (caught by P1d/P1e);
      - M3_cyclic_cascade: self-loop cascade cid (caught by P2).
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
PROPS = os.path.join(HERE, "cme2_formal_props.sv")
DEFAULT_OUT = os.path.join(HERE, "..", "raw")

MUTANTS = [
    (
        "M1_we_on_reject",
        "safety_bmc",
        20,
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
        "M2_cascade_on_reject",
        "safety_bmc",
        20,
        "cascade subscription requested on reject",
        "    wire cascade_req   = (state_q == ST_EVAL_GATE) && cme_committed &&\n"
        "                         cme_trigger_subscriber && (cme_subscriber_cid[5:0] != active_cid_q);",
        "    wire cascade_req   = (state_q == ST_EVAL_GATE) &&\n"
        "                         (cme_committed || cme_rejected) &&\n"
        "                         (cme_trigger_subscriber || cme_rejected) &&\n"
        "                         (cme_subscriber_cid[5:0] != active_cid_q);",
    ),
    (
        "M3_cyclic_cascade",
        "liveness_bmc",
        53,
        "self-loop cascade_cid violates acyclic termination",
        "    wire [5:0]            cascade_cid   = cascade_pending_valid_q ? cascade_pending_cid_q\n"
        "                                                                  : cme_subscriber_cid[5:0];",
        "    wire [5:0]            cascade_cid   = cascade_pending_valid_q ? cascade_pending_cid_q\n"
        "                                                                  : active_cid_q;",
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


def build_smt2(work, out_dir, seq_path, defines, tag):
    smt2 = os.path.join(work, f"{tag}.smt2")
    ys = os.path.join(work, f"{tag}.ys")
    def_flags = " ".join(f"-D{d}" for d in defines)
    script = (
        f"read_verilog -sv -formal {def_flags} "
        f"{RTL_GATE} {RTL_CME} {RTL_BRAM} {seq_path} {PROPS}\n"
        "prep -top cme2_formal_props\n"
        "flatten\n"
        "async2sync\n"
        "chformal -assume -early\n"
        "opt_clean\n"
        "memory_map\n"
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


def run_smtbmc(work, out_dir, seq_path, defines, mode, depth, tag, keep_vcd=False):
    smt2 = build_smt2(work, out_dir, seq_path, defines, tag)
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
    ap.add_argument("--skip-liveness", action="store_true",
                    help="Skip 52-step liveness BMC (for fast safety/mutant smoke runs)")
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
        # 1. Original RTL: P1 k-induction
        rows.append({
            "design": "original (CFG-P)",
            "check": "P1_safety_ind",
            **run_smtbmc(work, out_dir, RTL_SEQ, ["FORMAL_SAFETY", "FORMAL_INDUCTION"],
                         "ind", 5, "orig_safety_ind"),
        })
        # 2. Original RTL: P1 BMC (full event conservation)
        rows.append({
            "design": "original (CFG-P)",
            "check": "P1_safety_bmc",
            **run_smtbmc(work, out_dir, RTL_SEQ, ["FORMAL_SAFETY"],
                         "bmc", 20, "orig_safety_bmc"),
        })
        # 3. Original RTL: P2 & P3 Liveness/Latency BMC
        if not args.skip_liveness:
            rows.append({
                "design": "original (CFG-P)",
                "check": "P2_P3_liveness_bmc",
                **run_smtbmc(work, out_dir, RTL_SEQ, ["FORMAL_LIVENESS"],
                             "bmc", 52, "orig_liveness_bmc"),
            })
        # 4. Original RTL: Cover (non-vacuity)
        rows.append({
            "design": "original (CFG-P)",
            "check": "cover_non_vacuity",
            **run_smtbmc(work, out_dir, RTL_SEQ, ["FORMAL_COVER"],
                         "cover", 45, "orig_cover"),
        })

        # 5. Mutants (negative controls)
        for mid, mode_kind, depth, desc, old, new in MUTANTS:
            if args.skip_liveness and mode_kind == "liveness_bmc":
                continue
            n = seq_src.count(old)
            if n != 1:
                raise RuntimeError(f"{mid}: expected 1 match in {RTL_SEQ}, found {n}")
            mpath = os.path.join(work, f"{mid}_seq.sv")
            with open(mpath, "w", encoding="utf-8") as f:
                f.write(seq_src.replace(old, new))
            defines = ["FORMAL_LIVENESS"] if mode_kind == "liveness_bmc" else ["FORMAL_SAFETY"]
            rows.append({
                "design": f"{mid}: {desc}",
                "check": mode_kind,
                **run_smtbmc(work, out_dir, mpath, defines,
                             "bmc", depth, mid, keep_vcd=True),
            })
    finally:
        if os.path.isdir(work):
            shutil.rmtree(work)

    csv_path = os.path.join(out_dir, "cme2_results.csv")
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
        "issue": 227,
        "parameters": {"NUM_CONCEPTS": 4, "QUEUE_DEPTH": 4, "DATA_WIDTH": 32, "ADDR_WIDTH": 4},
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
            "cme2_formal_props.sv": hashlib.sha256(open(PROPS, "rb").read()).hexdigest(),
        },
        "verdict": verdict,
        "rows": rows,
    }
    with open(os.path.join(out_dir, "cme2_provenance.json"), "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2)

    print("=" * 88)
    print("CME2-FORMAL-227 SUMMARY (Issue #227)")
    print("=" * 88)
    for r in rows:
        extra = ""
        if r["failed"]:
            extra += f" [failed: {r['failed']}]"
        if r["reached"]:
            extra += f" [reached: {r['reached']}]"
        if r["vcd"]:
            extra += f" [vcd: {r['vcd']}]"
        print(f"  {r['design']:<44} | {r['engine']:<22} | {r['status']:<6}{extra} ({r['seconds']}s)")
    print("-" * 88)
    print(f"VERDICT: {verdict}")
    print("=" * 88)

    if verdict != "PASSED":
        sys.exit(1)


if __name__ == "__main__":
    main()
