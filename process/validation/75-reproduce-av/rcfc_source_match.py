#!/usr/bin/env python3
"""Replay AV-08 RCFC synthesis with two pinned RTL versions, not a full S1 audit."""

import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from compare import compare_rows, csv_rows

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PIN = "2518fa3d856e6ebbe9d894171018d19310de809b"
HISTORICAL = "62219ef0927bc0ca427deabc533833fa41960e43"
CHANGE = "ecdc04902a47f9f037b95aab5dc196e980b6faaf"
OLD_PATH = "KuzminMachine/02-engineering-hardware/rtl/km_rcfc_engine.sv"
RTL_PATH = "hw/rtl/poc-demo/km_rcfc_engine.sv"
RUNNER_PATH = "experiments/AV-08/scripts/run_av08_scaling.py"
REFERENCE_PATH = "experiments/AV-08/raw/av08_scaling/av08_results.csv"
NS = [4, 8, 16, 32, 64]


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_file(repo, ref, path):
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{ref}:{path}"])


def save(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drafts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--openxc7", type=Path, default=Path.home() / "opt/openxc7")
    args = parser.parse_args()
    out, build, drafts = args.out.resolve(), args.build.resolve(), args.drafts.resolve()
    if out.exists() or build.exists():
        raise ValueError("output and build must not already exist")
    if out.is_relative_to(build) or build.is_relative_to(out) or build.is_relative_to(ROOT):
        raise ValueError("build must be outside raw outputs and the working repository")
    if out.is_relative_to(drafts) or build.is_relative_to(drafts):
        raise ValueError("do not write into the historical source repository")

    old = git_file(drafts, HISTORICAL, OLD_PATH)
    current = git_file(ROOT, PIN, RTL_PATH)
    reference = ROOT / REFERENCE_PATH
    previous = HERE / "raw/run-20261110-01/av08/S3_rcfc_N4/av08_results.csv"
    provenance = json.loads((reference.parent / "av08_provenance.json").read_text())
    if sha(old) != provenance["rtl_sha256"]["km_rcfc_engine.sv"]:
        raise ValueError("historical RTL does not match the primary provenance")
    if old != git_file(drafts, CHANGE + "^", OLD_PATH):
        raise ValueError("historical RTL is not the pre-change version")
    if current != git_file(drafts, CHANGE, OLD_PATH):
        raise ValueError("control RTL is not the post-change version")
    runner_file = ROOT / RUNNER_PATH
    if runner_file.read_bytes() != git_file(ROOT, PIN, RUNNER_PATH):
        raise ValueError("runner differs from the original private reproduction")

    out.mkdir(parents=True)
    build.mkdir(parents=True)
    spec = importlib.util.spec_from_file_location("av08_source_match", runner_file)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    runner.OPENXC7 = str(args.openxc7.resolve())
    yosys = Path(shutil.which("yosys", path=runner.env()["PATH"]))
    version = subprocess.check_output([str(yosys), "-V"], env=runner.env(), text=True).strip()
    if version != provenance["yosys"]:
        raise ValueError("Yosys version differs from the primary provenance")
    preflight = {
        "started": now(), "host": platform.node(), "python": sys.version,
        "driver_commit": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "driver_sha256": sha(Path(__file__).read_bytes()),
        "protocol_sha256": sha((HERE / "rcfc-source-match-protocol.md").read_bytes()),
        "runner_commit": PIN, "runner_sha256": sha(runner_file.read_bytes()),
        "historical_rtl_commit": HISTORICAL, "historical_rtl_sha256": sha(old),
        "control_rtl_commit": PIN, "control_rtl_sha256": sha(current),
        "change_commit": CHANGE, "yosys": version, "yosys_path": str(yosys),
        "yosys_sha256": sha(yosys.read_bytes()),
        "reference_sha256": sha(reference.read_bytes()), "previous_n4_sha256": sha(previous.read_bytes()),
        "historical_runner_sha256_claim": provenance["script_sha256"],
        "historical_full_revision_identity": "NOT_ESTABLISHED",
        "N": NS, "mode": "SYNTH_ONLY", "build": str(build),
    }
    save(out / "preflight.json", preflight)
    patch = subprocess.check_output(["git", "-C", str(drafts), "diff", CHANGE + "^", CHANGE, "--", OLD_PATH])
    with (out / "source-change.patch").open("xb") as stream:
        stream.write(patch)

    original_run = runner.run
    results, errors, harnesses = {}, [], {}
    for label, rtl in (("historical", old), ("control", current)):
        source_dir = build / label / "rtl"
        source_dir.mkdir(parents=True)
        (source_dir / "km_rcfc_engine.sv").write_bytes(rtl)
        runner.RTL, runner.BUILD = str(source_dir), str(build / label / "build")
        rows = []
        for n in NS:
            case = out / label / f"N{n}"
            case.mkdir(parents=True)
            calls = []

            def audited_run(command, cwd, log, timeout=None):
                call = {"command": command, "cwd": cwd, "started": now()}
                calls.append(call)
                result = original_run(command, cwd, log, timeout)
                call.update({"finished": now(), "returncode": result[0]})
                return result

            runner.run = audited_run
            try:
                stats = runner.synth("S3_rcfc", n)
                rows.append({**{k: v for k, v in stats.items() if k != "dir"},
                             "seed": "", "status": "SYNTH_ONLY", "fmax_mhz": ""})
            except Exception as error:
                errors.append({"variant": label, "N": n, "error": repr(error)})
            finally:
                generated = Path(runner.BUILD) / f"S3_rcfc_N{n}"
                for name in ("av08_top.v", "stat.json"):
                    if (generated / name).exists():
                        shutil.copyfile(generated / name, case / name)
                log = generated / "yosys.log"
                if log.exists():
                    data = log.read_bytes()
                    with gzip.open(case / "yosys.log.gz", "xb") as stream:
                        stream.write(data)
                    save(case / "execution.json", {
                        "calls": calls, "yosys_log_sha256": sha(data),
                        "compressed_log_sha256": sha((case / "yosys.log.gz").read_bytes()),
                    })
            if (case / "av08_top.v").exists():
                harnesses[f"{label}/{n}"] = sha((case / "av08_top.v").read_bytes())
            print(label, f"N={n}", rows[-1] if rows and rows[-1]["N"] == n else "EXECUTION_FAILED", flush=True)

        with (out / f"{label}.csv").open("x", newline="") as stream:
            writer = csv.DictWriter(stream, runner.KEYS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        results[label] = csv_rows(out / f"{label}.csv")

    keys, fields = ["series", "N", "seed"], [k for k in runner.KEYS if k not in ("series", "N", "seed")]
    expected = [row for row in csv_rows(reference) if row["series"] == "S3_rcfc"]
    historical_differences = compare_rows(expected, results["historical"], keys, fields)
    n4_differences = compare_rows(csv_rows(previous), [r for r in results["control"] if r["N"] == "4"], keys, fields)
    all_executed = all({row["N"] for row in results[label]} == {str(n) for n in NS} for label in results)
    same_harness = all(harnesses.get(f"historical/{n}") == harnesses.get(f"control/{n}") and
                       f"historical/{n}" in harnesses for n in NS)
    inputs_unchanged = (
        sha(yosys.read_bytes()) == preflight["yosys_sha256"] and
        sha(runner_file.read_bytes()) == preflight["runner_sha256"] and
        sha(reference.read_bytes()) == preflight["reference_sha256"] and
        sha(previous.read_bytes()) == preflight["previous_n4_sha256"] and
        (build / "historical/rtl/km_rcfc_engine.sv").read_bytes() == old and
        (build / "control/rtl/km_rcfc_engine.sv").read_bytes() == current
    )
    success = not errors and all_executed and same_harness and inputs_unchanged and not historical_differences and not n4_differences
    save(out / "comparison.json", {
        "finished": now(), "execution_errors": errors, "all_N_executed": all_executed,
        "harnesses_identical": same_harness, "harness_sha256": harnesses, "inputs_unchanged": inputs_unchanged,
        "historical_differences": historical_differences, "control_n4_differences": n4_differences,
        "diagnosis": "SOURCE_CHANGE_REPRODUCES_N4_DIFFERENCE" if success else "NOT_ESTABLISHED",
        "s1_status": "NOT_PASSED", "historical_full_revision_identity": "NOT_ESTABLISHED",
        "files": {str(p.relative_to(out)): sha(p.read_bytes()) for p in sorted(out.rglob("*")) if p.is_file()},
    })
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
