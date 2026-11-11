#!/usr/bin/env python3
"""Replay a pinned new baseline; optionally reuse explicitly verified prior P&R."""

import argparse
import gzip
import json
from pathlib import Path
import platform
import shutil
import subprocess

from compare import compare_rows, csv_rows, mutation_rows
from run import AV07_CHILD, HERE, PIN, execute, git, now, save, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--openxc7", type=Path, default=Path.home() / "opt/openxc7")
    parser.add_argument("--reuse-recorded-pnr", action="store_true")
    args = parser.parse_args()
    source, out, build = args.source.resolve(), args.out.resolve(), args.build.resolve()
    baseline = HERE / "baseline-20261111"
    manifest = json.loads((baseline / "manifest.json").read_text())
    if git(source, "rev-parse", "HEAD") != PIN or git(source, "status", "--porcelain"):
        raise ValueError("source must be the clean pinned commit")
    if out.exists() or build.exists():
        raise ValueError("output and build must be new")
    if (out.is_relative_to(source) or build.is_relative_to(source) or
            out.is_relative_to(build) or build.is_relative_to(out)):
        raise ValueError("source, raw output and build must be separate")
    for name, digest in manifest["source_sha256"].items():
        if sha(source / name) != digest:
            raise ValueError(f"source mismatch: {name}")
    for name, digest in manifest["reference_sha256"].items():
        if sha(baseline / name) != digest:
            raise ValueError(f"reference mismatch: {name}")

    recorded_rows = []
    recorded_cases = []
    if args.reuse_recorded_pnr:
        recorded = HERE / manifest["recorded_replay"]["root"]
        for name, digest in manifest["recorded_replay"]["anchors"].items():
            if sha(recorded / name) != digest:
                raise ValueError(f"recorded replay anchor mismatch: {name}")
        preflight = json.loads((recorded / "preflight.json").read_text())
        comparison = json.loads((recorded / "comparison.json").read_text())
        if not (preflight["source_commit"] == PIN and preflight["source_clean_before"] and
                comparison["source_clean_after"] and
                preflight["source_sha256"] == manifest["source_sha256"]):
            raise ValueError("recorded replay source identity is not established")
        for name, digest in comparison["raw_sha256"].items():
            if sha(recorded / name) != digest:
                raise ValueError(f"recorded raw mismatch: {name}")
        for case in manifest["recorded_replay"]["cases"]:
            folder = recorded / "av08" / case
            provenance = json.loads((folder / "av08_provenance.json").read_text())
            execution = json.loads((folder / "execution.json").read_text())
            if (provenance["git_commit"] != PIN or provenance["git_dirty_rtl"] or
                    provenance["script_sha256"] != manifest["source_sha256"]["experiments/AV-08/scripts/run_av08_scaling.py"] or
                    execution["returncode"] != 0):
                raise ValueError(f"recorded case provenance mismatch: {case}")
            for name, digest in provenance["rtl_sha256"].items():
                if manifest["source_sha256"].get("hw/rtl/" + name) != digest:
                    raise ValueError(f"recorded case RTL mismatch: {case}/{name}")
            recorded_rows.extend(csv_rows(folder / "av08_results.csv"))
            recorded_cases.append({"case": case, "started": execution["started"],
                                   "finished": execution["finished"]})

    out.mkdir(parents=True)
    build.mkdir(parents=True)
    versions = {}
    for command in (["yosys", "-V"], ["z3", "--version"], ["cvc5", "--version"],
                    ["iverilog", "-V"], [str(args.openxc7 / "bin/yosys"), "-V"],
                    [str(args.openxc7 / "bin/nextpnr-himbaechel"), "--version"]):
        probe = subprocess.run(command, capture_output=True, text=True)
        versions[" ".join(command)] = {"returncode": probe.returncode,
                                      "output": probe.stdout + probe.stderr}
    save(out / "preflight.json", {
        "started": now(), "host": platform.node(), "source_commit": PIN,
        "source_clean_before": True, "source_sha256": manifest["source_sha256"],
        "driver_commit": git(HERE, "rev-parse", "HEAD"),
        "driver_sha256": sha(Path(__file__)),
        "baseline_manifest_sha256": sha(baseline / "manifest.json"),
        "protocol_sha256": sha(HERE / "baseline-protocol.md"), "tool_versions": versions,
        "pnr_execution": "REUSED_RECORDED_REPLAY" if args.reuse_recorded_pnr else "FRESH",
        "reused_cases": recorded_cases,
    })
    results = []

    def record(case, receipt, differences):
        status = "EXECUTION_FAILED" if receipt["returncode"] else (
            "DIFFERENT" if differences else "MATCH")
        results.append({"case": case, "status": status, "differences": differences})
        print(case, status, flush=True)

    for solver in ("z3", "cvc5"):
        folder = out / f"av04_{solver}"
        destination = folder / "results"
        receipt = execute(source, folder, [
            "python3", "experiments/AV-04/scripts/run_av04_formal.py",
            "--depth", "25", "--solver", solver,
        ], {"AV04_OUT_DIR": str(destination)})
        actual = Path(str(destination) + ("_cvc5" if solver == "cvc5" else "")) / "av04_results.csv"
        record(f"AV-04/{solver}", receipt, compare_rows(
            csv_rows(baseline / f"av04_{solver}.csv"),
            csv_rows(actual) if actual.exists() else [], ["design", "width", "mode"],
            ["status", "asserts", "covers", "reached_covers", "unreached_covers"],
        ))

    folder = out / "av07"
    receipt = execute(source, folder, [
        "python3", "-c", AV07_CHILD, str(source / "experiments/AV-07/scripts/run_av07_mutation.py"),
    ], {"AV07_OUT_DIR": str(folder)})
    actual = folder / "raw/av07_mutation_results.json"
    before = mutation_rows(baseline / "av07.json")
    after = mutation_rows(actual) if actual.exists() else []
    record("AV-07", receipt,
           compare_rows(before[:1], after[:1], ["id"],
                        ["total_mutants", "killed_mutants", "survived_mutants", "mutation_score_pct"]) +
           compare_rows(before[1:], after[1:], ["id"], ["status", "stage"]))

    folder = out / "av08"
    command = ["python3", "experiments/AV-08/scripts/run_av08_scaling.py",
               "--seeds", "1", "2", "3", "--jobs", "1", "--pnr-timeout", "3600"]
    if args.reuse_recorded_pnr:
        command += ["--series", "S3_rcfc"]
    receipt = execute(source, folder, command, {
        "AV08_OUT_DIR": str(folder), "AV08_BUILD_DIR": str(build / "av08"),
        "OPENXC7_DIR": str(args.openxc7.resolve()),
    })
    for path in (build / "av08").glob("*/stat.json"):
        shutil.copyfile(path, folder / f"{path.parent.name}_stat.json")
        with gzip.open(folder / f"{path.parent.name}_yosys.log.gz", "xb") as stream:
            stream.write((path.parent / "yosys.log").read_bytes())
    actual = folder / "av08_results.csv"
    expected = csv_rows(baseline / "av08.csv")
    record("AV-08", receipt, compare_rows(
        expected, recorded_rows + (csv_rows(actual) if actual.exists() else []),
        ["series", "N", "seed"], list(expected[0]),
    ))
    unchanged = (not git(source, "status", "--porcelain") and
                 all(sha(source / name) == digest for name, digest in manifest["source_sha256"].items()) and
                 all(sha(baseline / name) == digest for name, digest in manifest["reference_sha256"].items()))
    success = unchanged and all(item["status"] == "MATCH" for item in results)
    save(out / "comparison.json", {
        "finished": now(), "source_commit": PIN, "source_and_references_unchanged": unchanged,
        "results": results, "av08_expected_rows": len(expected),
        "av08_reused_rows": len(recorded_rows),
        "issue75": "NEW_BASELINE_MATCH" if success else "NOT_ESTABLISHED",
        "s1_status": "NOT_ASSESSED", "historical_full_revision_identity": "NOT_ESTABLISHED",
        "raw_sha256": {p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob("*")) if p.is_file()},
    })
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
