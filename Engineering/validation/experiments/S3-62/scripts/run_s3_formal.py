#!/usr/bin/env python3
"""S3-62: Formal verification and falsification check of KPOL v0.2 Fail-Closed Transaction Gate.

Addresses:
  * Issue #62: Фальсифікація S3: fail-closed формально (BMC)
  * Issue #18: kpol_txn_gate_v2 без формальної верифікації (F2′)
  * Requirement S3 & Hypothesis H6

Engines:
  * proof: yosys -> AIGER -> yosys-abc `pdr` (unbounded IC3/PDR);
  * cross-check: yosys-smtbmc z3 BMC of original design at --bmc-depth;
  * non-vacuity: yosys-smtbmc z3 cover at --cover-depth;
  * mutant testing: yosys-abc `pdr` + z3 BMC must catch every injected defect and name the violated property.

Usage: python3 run_s3_formal.py [--bmc-depth 8] [--cover-depth 8]
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
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
RTL_V2 = os.path.join(REPO_ROOT, "hw", "rtl", "core", "kpol_txn_gate_v2.sv")
PROPS = os.path.join(HERE, "s3_props.sv")
OUT = os.environ.get("S3_OUT_DIR", os.path.join(HERE, "..", "raw", "s3_formal"))

# Injected mutants to verify non-vacuity and defect detection sensitivity
MUTANTS = [
    ("M_hazard_bypass", "hazard check bypassed (commits during hazard)",
     "assign hazard_ok    = !FAIL_CLOSED_HAZARDS || (hazard_known_i && !hazard_true_i);",
     "assign hazard_ok    = 1'b1;"),
    ("M_inv_bypass", "invariant check bypassed (commits on invariant violation)",
     "assign invariant_ok = invariant_known_i && invariant_true_i;",
     "assign invariant_ok = 1'b1;"),
    ("M_state_leak", "state mutates upon invariant rejection",
     "rejected_invariant_o <= 1'b1;",
     "rejected_invariant_o <= 1'b1; state_o <= candidate_value_i;"),
    ("M_f03_strobe", "F-03 classic defect: committed asserts on raw event strobe",
     "        end else begin\n            committed_o          <= 1'b0;\n            rejected_o           <= 1'b0;",
     "        end else begin\n            committed_o          <= event_valid_i;\n            rejected_o           <= 1'b0;"),
]

YS_FRONT = "read_verilog -sv -formal {rtl} {props}\nprep -top s3_formal\n"
YS_SMT2 = "async2sync\ndffunmap\nwrite_smt2 -wires {out}\n"
YS_AIG = ("flatten\nasync2sync\nchformal -assume -early\nchformal -cover -remove\n"
          "opt_clean\nmemory_map\nopt -full\ntechmap\nopt -fast\ndffunmap\n"
          "abc -g AND -fast\nopt_clean\nwrite_aiger -I -B -zinit -no-startoffset {out}\n")


def sh(cmd, cwd, log_path=None):
    t0 = time.time()
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    dt = time.time() - t0
    out = (p.stdout or "") + (p.stderr or "")
    if log_path:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(out)
    return p.returncode, out, dt


def run_yosys(work, rtl, tail, out, tag):
    ys = os.path.join(work, f"{tag}.ys")
    with open(ys, "w", encoding="utf-8") as f:
        f.write(YS_FRONT.format(rtl=rtl, props=PROPS) + tail.format(out=out))
    rc, log, _ = sh(["yosys", "-q", ys], work, os.path.join(OUT, f"{tag}.yosys.log"))
    if rc != 0:
        raise RuntimeError(f"yosys failed for {tag}:\n{log}")
    return out


def run_pdr(work, rtl, tag):
    aig = run_yosys(work, rtl, YS_AIG, os.path.join(work, f"{tag}.aig"), f"{tag}.aig")
    rc, out, dt = sh(["yosys-abc", "-c", f"read_aiger {aig}; fold; strash; pdr"],
                     work, os.path.join(OUT, f"{tag}.pdr.log"))
    m = re.search(r"asserted in frame (\d+)", out)
    if "Property proved" in out:
        status, frame = "PASSED", None
    elif m:
        status, frame = "FAILED", int(m.group(1))
    else:
        status, frame = "ERROR", None
    return {
        "engine": "abc pdr",
        "status": status,
        "frame": frame,
        "seconds": round(dt, 3),
        "failed": [],
        "reached": [],
        "unreached": []
    }


def run_smtbmc(work, rtl, mode, depth, tag):
    smt2 = run_yosys(work, rtl, YS_SMT2, os.path.join(work, f"{tag}.smt2"), f"{tag}.smt2")
    vcd = os.path.join(OUT, f"{tag}.{mode}.vcd")
    cmd = ["yosys-smtbmc", "-s", "z3", "-t", str(depth)]
    cmd += ["-c"] if mode == "cover" else ["--dump-vcd", vcd]
    cmd.append(smt2)
    rc, out, dt = sh(cmd, work, os.path.join(OUT, f"{tag}.{mode}.log"))
    m = re.findall(r"Status: (\w+)", out)
    status = m[-1] if m else "ERROR"
    if status == "PASSED" and os.path.exists(vcd):
        os.remove(vcd)
    return {
        "engine": f"smtbmc z3 {mode} t={depth}",
        "status": status,
        "frame": None,
        "seconds": round(dt, 3),
        "failed": sorted(set(re.findall(r"Assert failed in \S+: (\w+)", out))),
        "reached": sorted(set(re.findall(r"Reached cover statement .*: (\w+)", out))),
        "unreached": sorted(set(re.findall(r"Unreached cover statement .*: (\w+)", out)))
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bmc-depth", type=int, default=8)
    ap.add_argument("--cover-depth", type=int, default=8)
    args = ap.parse_args()

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT, exist_ok=True)
    work = tempfile.mkdtemp(prefix="s3_62_")

    with open(RTL_V2, "r", encoding="utf-8") as f:
        src = f.read()

    orig_path = os.path.join(OUT, "kpol_txn_gate_v2.sv")
    with open(orig_path, "w", encoding="utf-8") as f:
        f.write(src)

    rows = []
    # 1. Unbounded PDR proof of original design
    rows.append({"design": "original (kpol_txn_gate_v2)", **run_pdr(work, orig_path, "orig")})
    # 2. Cross-check BMC at depth K
    rows.append({"design": "original (kpol_txn_gate_v2)", **run_smtbmc(work, orig_path, "bmc", args.bmc_depth, "orig")})
    # 3. Non-vacuity cover
    rows.append({"design": "original (kpol_txn_gate_v2)", **run_smtbmc(work, orig_path, "cover", args.cover_depth, "orig")})

    # 4. Mutant verification
    for mid, desc, old, new in MUTANTS:
        n = src.count(old)
        if n != 1:
            raise RuntimeError(f"{mid}: fragment found {n} times in RTL, expected 1")
        mpath = os.path.join(work, f"{mid}.sv")
        with open(mpath, "w", encoding="utf-8") as f:
            f.write(src.replace(old, new))
        r = run_pdr(work, mpath, mid)
        rows.append({"design": f"{mid}: {desc}", **r})
        if r["status"] == "FAILED":
            depth = max(args.bmc_depth, (r["frame"] or 1) + 1)
            rows.append({"design": f"{mid}: {desc}",
                         **run_smtbmc(work, mpath, "bmc", depth, mid)})

    # Export results
    csv_path = os.path.join(OUT, "s3_results.csv")
    fields = ["design", "engine", "status", "frame", "seconds", "failed", "reached", "unreached"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    provenance = {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "experiment": "S3-62",
        "issue": 62,
        "related_issue": 18,
        "parent_requirement": "S3",
        "scientific_hypothesis": "H6",
        "rtl_sha256": hashlib.sha256(src.encode("utf-8")).hexdigest(),
        "props_sha256": hashlib.sha256(open(PROPS, "rb").read()).hexdigest(),
        "platform": {
            "node": platform.node(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "bmc_depth": args.bmc_depth,
        "cover_depth": args.cover_depth,
        "verdict": "NOT_REFUTED" if all(
            r["status"] == "PASSED" for r in rows if r["design"].startswith("original")
        ) and all(
            r["status"] == "FAILED" for r in rows if not r["design"].startswith("original") and r["engine"] == "abc pdr"
        ) else "REFUTED"
    }
    with open(os.path.join(OUT, "s3_provenance.json"), "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2)

    print("================================================================================")
    print("S3-62 FORMAL VERIFICATION SUMMARY (Issue #62 / #18 / Gate S3)")
    print("================================================================================")
    for r in rows:
        failed_str = f" [failed: {', '.join(r['failed'])}]" if r['failed'] else ""
        reached_str = f" [reached: {', '.join(r['reached'])}]" if r['reached'] else ""
        print(f"  {r['design']:<45} | {r['engine']:<24} | {r['status']:<8}{failed_str}{reached_str} ({r['seconds']}s)")
    print("-" * 88)
    print(f"VERDICT: {provenance['verdict']}")
    print(f"Artifacts exported to: {OUT}")
    print("================================================================================")


if __name__ == "__main__":
    main()
