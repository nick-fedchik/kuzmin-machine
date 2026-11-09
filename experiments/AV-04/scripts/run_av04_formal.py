#!/usr/bin/env python3
"""AV-04: formal verification of kpol_txn_gate.sv with mutant sensitivity check.

Flow: yosys (read_verilog -sv -formal, prep, async2sync, dffunmap, write_smt2)
-> yosys-smtbmc (BMC depth N, k-induction depth N, cover depth N).

Pass criteria (pre-registered, AV plan sec. 4.2):
  * original RTL: BMC PASS, induction PASS, all covers reached, for W=8 and W=32;
  * every mutant: BMC FAIL (a counterexample is found);
  * SPEC_POL_HAZARD_BLOCKS on original RTL: reported as-is (expected FAIL,
    documents the KPOL draft vs POL spec conflict).

Usage: python3 run_av04_formal.py [--depth 25] [--solver z3]
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
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
KM = REPO_ROOT
RTL = os.path.join(REPO_ROOT, "hw", "rtl", "core", "kpol_txn_gate.sv")
PROPS = os.path.join(HERE, "av04_gate_props.sv")
# Повторний прогін пише в окремий каталог (сирі дані незмінні): AV04_OUT_DIR=/tmp/av04
OUT = os.environ.get("AV04_OUT_DIR", os.path.join(HERE, "..", "raw", "av04_formal"))

# (id, description, exact source fragment, replacement)
# a..d are pre-registered in the plan; e..h are additional.
MUTANTS = [
    ("M_a", "ignore invariant_known",
     "assign invariant_ok = invariant_known_i && invariant_true_i;",
     "assign invariant_ok = invariant_true_i;"),
    ("M_b", "decide without event_valid",
     "if (event_valid_i === 1'b1) begin",
     "if (1'b1) begin"),
    ("M_c", "ignore assumption_true",
     "assign input_ok = candidate_known_i && assumption_known_i && assumption_true_i;",
     "assign input_ok = candidate_known_i && assumption_known_i;"),
    ("M_d", "never raise unknown_hazard",
     "unknown_hazard_o <= 1'b1;",
     "unknown_hazard_o <= 1'b0;"),
    ("M_e", "changed always 1 on commit",
     "changed_o   <= candidate_value_i != state_o;",
     "changed_o   <= 1'b1;"),
    ("M_f", "reset state to 0 instead of RESET_VALUE",
     "state_o              <= RESET_VALUE;",
     "state_o              <= '0;"),
    ("M_g", "ignore hazard_known in unknown-hazard check",
     "if (hazard_known_i !== 1'b1 || (hazard_true_i !== 1'b0 && hazard_true_i !== 1'b1)) begin",
     "if (hazard_true_i !== 1'b0 && hazard_true_i !== 1'b1) begin"),
    ("M_h", "report invariant reason for input rejection",
     "rejected_o       <= 1'b1;\n                    rejected_input_o <= 1'b1;",
     "rejected_o       <= 1'b1;\n                    rejected_invariant_o <= 1'b1;"),
]

WIDTHS = [8, 32]


def sh(cmd, cwd, log):
    t0 = time.monotonic()
    p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    dt = time.monotonic() - t0
    text = ("$ " + " ".join(cmd) + "\n" + p.stdout).replace(KM + os.sep, "")
    text = re.sub(r"/tmp/av04_\w+/", "", text)
    with open(log, "w") as f:
        f.write(text)
    return p.returncode, p.stdout, dt


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def tool_version(cmd):
    try:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True).stdout.strip().splitlines()[0]
    except (OSError, IndexError):
        return "unavailable"


def build_smt2(work, rtl, width, defines, tag):
    ys = os.path.join(work, f"{tag}.ys")
    smt2 = os.path.join(work, f"{tag}.smt2")
    dflags = " ".join(f"-D{d}" for d in defines)
    with open(ys, "w") as f:
        f.write(
            f"read_verilog -sv -formal {dflags} {rtl} {PROPS}\n"
            f"chparam -set W {width} av04_gate_formal\n"
            "prep -top av04_gate_formal\n"
            "async2sync\n"
            "dffunmap\n"
            f"write_smt2 -wires {smt2}\n"
        )
    rc, out, _ = sh(["yosys", "-q", ys], work, os.path.join(OUT, f"{tag}.yosys.log"))
    if rc != 0:
        raise RuntimeError(f"yosys failed for {tag}:\n{out}")
    with open(smt2) as f:
        txt = f.read()
    return smt2, txt.count("yosys-smt2-assert"), txt.count("yosys-smt2-cover")


def smtbmc(work, smt2, mode, depth, solver, tag):
    cmd = ["yosys-smtbmc", "-s", solver, "-t", str(depth)]
    if mode == "bmc":
        cmd += ["--presat", "--dump-vcd", os.path.join(OUT, f"{tag}.bmc.vcd")]
    elif mode == "ind":
        cmd += ["-i"]
    elif mode == "cover":
        cmd += ["-c"]
    cmd.append(smt2)
    rc, out, dt = sh(cmd, work, os.path.join(OUT, f"{tag}.{mode}.log"))
    m = re.findall(r"Status: (\w+)", out)
    status = m[-1] if m else "ERROR"
    failed = sorted(set(re.findall(r"Assert failed in \S+: (\w+)", out)))
    reached = sorted(set(re.findall(r"Reached cover statement .*: (\w+)", out)))
    unreached = sorted(set(re.findall(r"Unreached cover statement .*: (\w+)", out)))
    vcd = os.path.join(OUT, f"{tag}.bmc.vcd")
    if mode == "bmc" and status == "PASSED" and os.path.exists(vcd):
        os.remove(vcd)
    return {"status": status, "rc": rc, "seconds": round(dt, 3), "failed": failed,
            "reached": reached, "unreached": unreached}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--depth", type=int, default=25)
    ap.add_argument("--solver", default="z3")
    args = ap.parse_args()
    global OUT
    if args.solver != "z3":
        OUT = OUT + "_" + args.solver

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    work = tempfile.mkdtemp(prefix="av04_")
    src = open(RTL).read()

    rows = []
    for width in WIDTHS:
        tag = f"orig_W{width}"
        smt2, na, nc = build_smt2(work, RTL, width, [], tag)
        for mode in ("bmc", "ind", "cover"):
            r = smtbmc(work, smt2, mode, args.depth, args.solver, tag)
            rows.append({"design": "original", "width": width, "mode": mode,
                         "asserts": na, "covers": nc, **r})

        tag = f"origPOL_W{width}"
        smt2, na, nc = build_smt2(work, RTL, width, ["SPEC_POL_HAZARD_BLOCKS"], tag)
        r = smtbmc(work, smt2, "bmc", args.depth, args.solver, tag)
        rows.append({"design": "original+POL_hazard_blocks", "width": width, "mode": "bmc",
                     "asserts": na, "covers": nc, **r})

    for mid, desc, old, new in MUTANTS:
        n = src.count(old)
        if n != 1:
            raise RuntimeError(f"{mid}: fragment found {n} times, expected 1")
        path = os.path.join(work, f"{mid}.sv")
        with open(path, "w") as f:
            f.write(src.replace(old, new))
        for width in WIDTHS:
            tag = f"{mid}_W{width}"
            smt2, na, nc = build_smt2(work, path, width, [], tag)
            r = smtbmc(work, smt2, "bmc", args.depth, args.solver, tag)
            rows.append({"design": f"{mid}: {desc}", "width": width, "mode": "bmc",
                         "asserts": na, "covers": nc, **r})

    shutil.rmtree(work)

    with open(os.path.join(OUT, "av04_results.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["design", "width", "mode", "status", "seconds", "asserts", "covers",
                    "failed_asserts", "reached_covers", "unreached_covers"])
        for r in rows:
            w.writerow([r["design"], r["width"], r["mode"], r["status"], r["seconds"],
                        r["asserts"], r["covers"], ";".join(r["failed"]),
                        ";".join(r["reached"]), ";".join(r["unreached"])])

    def git(*a):
        return subprocess.run(["git", *a], cwd=KM, stdout=subprocess.PIPE,
                              text=True).stdout.strip()

    prov = {
        "experiment": "AV-04",
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "host": platform.node(),
        "platform": platform.platform(),
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty_rtl": bool(git("status", "--porcelain", "--", RTL)),
        "rtl_sha256": sha256(RTL),
        "props_sha256": sha256(PROPS),
        "yosys": tool_version(["yosys", "-V"]),
        "solver": args.solver,
        "solver_version": tool_version([args.solver, "--version"]),
        "python": sys.version.split()[0],
        "depth": args.depth,
        "widths": WIDTHS,
        "mutants": [{"id": m[0], "desc": m[1]} for m in MUTANTS],
    }
    with open(os.path.join(OUT, "av04_provenance.json"), "w") as f:
        json.dump(prov, f, indent=2, ensure_ascii=False)

    ok = True
    for r in rows:
        exp = None
        if r["design"] == "original":
            exp = "PASSED"
            if r["mode"] == "cover" and r["unreached"]:
                ok = False
        elif r["design"].startswith("M_"):
            exp = "FAILED"
        mark = "" if exp is None else ("ok" if r["status"] == exp else "UNEXPECTED")
        if mark == "UNEXPECTED":
            ok = False
        print(f"{r['design'][:48]:48} W={r['width']:<3} {r['mode']:5} {r['status']:7} "
              f"{r['seconds']:7.3f}s {','.join(r['failed'])[:60]} {mark}")
    print("AV-04 OVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
