#!/usr/bin/env python3
"""AXI-64: formal check of the AXI4-Lite slave produced by compile_axi_lite_wrapper.

Criterion and properties are pre-registered in Issue #64 (comment 6820456204).
Flow (deviation from the pre-registered smtbmc k-induction recorded in #64):
  * proof: yosys -> AIGER -> yosys-abc `pdr` (unbounded IC3/PDR, as SymbiYosys
    `abc pdr`); a counterexample frame means FAIL;
  * cross-check: yosys-smtbmc z3 BMC of the original at --bmc-depth;
  * non-vacuity: yosys-smtbmc z3 cover at --cover-depth;
  * mutants: `pdr` must find a counterexample; z3 BMC at that depth names
    the failing property.

Usage: python3 run_axi64_formal.py [--bmc-depth 8] [--cover-depth 10]
Rerun into another directory: AXI64_OUT_DIR=/tmp/axi64 python3 ...
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
GEN = os.path.join(REPO_ROOT, "sw", "kpol-ref", "kpol_reference.py")
PROPS = os.path.join(HERE, "axi64_props.sv")
OUT = os.environ.get("AXI64_OUT_DIR", os.path.join(HERE, "..", "raw", "axi64_formal"))

# Same module as test_v08_compile_axi_lite_wrapper.
SOURCE = """
Problem AxiModule {}
Solution AxiModule {
    state Counter: Int32 = 0;
}
Proof AxiModule {}
"""

# (id, F-04 defect class, exact fragment, replacement)
MUTANTS = [
    ("M_noaw", "write without AW handshake",
     "if ((aw_latched || (s_axi_awvalid && s_axi_awready)) &&",
     "if (1'b1 &&"),
    ("M_araddr", "write address taken from AR instead of AW",
     "case (eff_addr[5:2])",
     "case (s_axi_araddr[5:2])"),
    ("M_nostrb", "WSTRB ignored",
     "apply_wstrb[7:0]   = strb[0] ? new_val[7:0]   : old_val[7:0];",
     "apply_wstrb[7:0]   = new_val[7:0];"),
    ("M_bdrop", "BVALID dropped without BREADY",
     "if (s_axi_bready && bvalid_q) begin",
     "if (bvalid_q) begin"),
]


def sh(cmd, cwd, log):
    t0 = time.monotonic()
    p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    dt = time.monotonic() - t0
    text = ("$ " + " ".join(cmd) + "\n" + p.stdout).replace(REPO_ROOT + os.sep, "")
    text = re.sub(r"/tmp/axi64_\w+/", "", text)
    with open(log, "w") as f:
        f.write(text)
    return p.returncode, p.stdout, dt


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def tool_version(cmd):
    try:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True).stdout.strip().splitlines()[0]
    except (OSError, IndexError):
        return "unavailable"


def abc_version():
    try:
        out = subprocess.run(["yosys-abc", "-c", "version"], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True).stdout
    except OSError:
        return "unavailable"
    return next((l.strip() for l in out.splitlines() if "ABC " in l and "Berkeley" in l),
                "unavailable")


def generate():
    sys.path.insert(0, os.path.dirname(GEN))
    from kpol_reference import compile_axi_lite_wrapper, parse_module
    return compile_axi_lite_wrapper(parse_module(SOURCE))


YS_FRONT = "read_verilog -sv -formal {rtl} {props}\nprep -top axi64_formal\n"
YS_SMT2 = "async2sync\ndffunmap\nwrite_smt2 -wires {out}\n"
YS_AIG = ("flatten\nasync2sync\nchformal -assume -early\nchformal -cover -remove\n"
          "opt_clean\nmemory_map\nopt -full\ntechmap\nopt -fast\ndffunmap\n"
          "abc -g AND -fast\nopt_clean\nwrite_aiger -I -B -zinit -no-startoffset {out}\n")


def yosys(work, rtl, tail, out, tag):
    ys = os.path.join(work, f"{tag}.ys")
    with open(ys, "w") as f:
        f.write(YS_FRONT.format(rtl=rtl, props=PROPS) + tail.format(out=out))
    rc, log, _ = sh(["yosys", "-q", ys], work, os.path.join(OUT, f"{tag}.yosys.log"))
    if rc != 0:
        raise RuntimeError(f"yosys failed for {tag}:\n{log}")
    return out


def pdr(work, rtl, tag):
    aig = yosys(work, rtl, YS_AIG, os.path.join(work, f"{tag}.aig"), f"{tag}.aig")
    rc, out, dt = sh(["yosys-abc", "-c", f"read_aiger {aig}; fold; strash; pdr"],
                     work, os.path.join(OUT, f"{tag}.pdr.log"))
    m = re.search(r"asserted in frame (\d+)", out)
    if "Property proved" in out:
        status, frame = "PASSED", None
    elif m:
        status, frame = "FAILED", int(m.group(1))
    else:
        status, frame = "ERROR", None
    return {"engine": "abc pdr", "status": status, "frame": frame, "seconds": round(dt, 3),
            "failed": [], "reached": [], "unreached": []}


def smtbmc(work, rtl, mode, depth, tag):
    smt2 = yosys(work, rtl, YS_SMT2, os.path.join(work, f"{tag}.smt2"), f"{tag}.smt2")
    vcd = os.path.join(OUT, f"{tag}.{mode}.vcd")
    cmd = ["yosys-smtbmc", "-s", "z3", "-t", str(depth)]
    cmd += ["-c"] if mode == "cover" else ["--dump-vcd", vcd]
    cmd.append(smt2)
    rc, out, dt = sh(cmd, work, os.path.join(OUT, f"{tag}.{mode}.log"))
    m = re.findall(r"Status: (\w+)", out)
    status = m[-1] if m else "ERROR"
    if status == "PASSED" and os.path.exists(vcd):
        os.remove(vcd)
    return {"engine": f"smtbmc z3 {mode} t={depth}", "status": status, "frame": None,
            "seconds": round(dt, 3),
            "failed": sorted(set(re.findall(r"Assert failed in \S+: (\w+)", out))),
            "reached": sorted(set(re.findall(r"Reached cover statement .*: (\w+)", out))),
            "unreached": sorted(set(re.findall(r"Unreached cover statement .*: (\w+)", out)))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bmc-depth", type=int, default=8)
    ap.add_argument("--cover-depth", type=int, default=10)
    args = ap.parse_args()

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    work = tempfile.mkdtemp(prefix="axi64_")
    src = generate()
    gen_path = os.path.join(OUT, "km_aximodule_axi_lite_slave.sv")
    with open(gen_path, "w") as f:
        f.write(src)

    rows = [{"design": "original", **pdr(work, gen_path, "orig")},
            {"design": "original", **smtbmc(work, gen_path, "bmc", args.bmc_depth, "orig")},
            {"design": "original", **smtbmc(work, gen_path, "cover", args.cover_depth, "orig")}]
    for mid, desc, old, new in MUTANTS:
        n = src.count(old)
        if n != 1:
            raise RuntimeError(f"{mid}: fragment found {n} times, expected 1")
        path = os.path.join(work, f"{mid}.sv")
        with open(path, "w") as f:
            f.write(src.replace(old, new))
        r = pdr(work, path, mid)
        rows.append({"design": f"{mid}: {desc}", **r})
        if r["status"] == "FAILED":
            rows.append({"design": f"{mid}: {desc}",
                         **smtbmc(work, path, "bmc", r["frame"] + 1, mid)})
    shutil.rmtree(work)

    with open(os.path.join(OUT, "axi64_results.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["design", "engine", "status", "cex_frame", "seconds",
                    "failed_asserts", "reached_covers", "unreached_covers"])
        for r in rows:
            w.writerow([r["design"], r["engine"], r["status"],
                        "" if r["frame"] is None else r["frame"], r["seconds"],
                        ";".join(r["failed"]), ";".join(r["reached"]), ";".join(r["unreached"])])

    def git(*a):
        return subprocess.run(["git", *a], cwd=REPO_ROOT, stdout=subprocess.PIPE,
                              text=True).stdout.strip()

    prov = {
        "experiment": "AXI-64",
        "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "host": platform.node(),
        "platform": platform.platform(),
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty_generator": bool(git("status", "--porcelain", "--", GEN)),
        "generator_sha256": sha256_bytes(open(GEN, "rb").read()),
        "generated_sv_sha256": sha256_bytes(src.encode()),
        "props_sha256": sha256_bytes(open(PROPS, "rb").read()),
        "yosys": tool_version(["yosys", "-V"]),
        "abc": abc_version(),
        "z3": tool_version(["z3", "--version"]),
        "python": sys.version.split()[0],
        "bmc_depth": args.bmc_depth,
        "cover_depth": args.cover_depth,
        "mutants": [{"id": m[0], "desc": m[1]} for m in MUTANTS],
    }
    with open(os.path.join(OUT, "axi64_provenance.json"), "w") as f:
        json.dump(prov, f, indent=2, ensure_ascii=False)

    for r in rows:
        print(f"{r['design'][:48]:48} {r['engine']:22} {r['status']:7} "
              f"{r['seconds']:8.3f}s {','.join(r['failed'])}")
    proof, bmc, cov = rows[0], rows[1], rows[2]
    muts = [r for r in rows[3:] if r["engine"] == "abc pdr"]
    if proof["status"] == "FAILED" or bmc["status"] == "FAILED":
        verdict = "REFUTED"
    elif (proof["status"] == "PASSED" and bmc["status"] == "PASSED"
          and cov["status"] == "PASSED" and not cov["unreached"]
          and all(m["status"] == "FAILED" for m in muts)):
        verdict = "NOT_REFUTED"
    else:
        verdict = "UNDETERMINED"
    print("AXI-64 VERDICT:", verdict)
    return 0 if verdict == "NOT_REFUTED" else 1


if __name__ == "__main__":
    sys.exit(main())
