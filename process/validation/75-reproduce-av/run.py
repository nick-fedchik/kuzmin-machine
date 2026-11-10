#!/usr/bin/env python3
"""Execute the preregistered #75 comparison without modifying the source clone."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from compare import compare_rows, csv_rows, mutation_rows

PIN = "2518fa3d856e6ebbe9d894171018d19310de809b"
HERE = Path(__file__).resolve().parent
AV07_CHILD = """
import importlib.util
from pathlib import Path
import sys
import tempfile
spec = importlib.util.spec_from_file_location("av07_repeat", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory(prefix="km75-av07-") as work:
    module.TMP_DIR = Path(work)
    try:
        module.main()
    finally:
        generated = module.REPORTS_DIR / "report.md"
        if generated.exists():
            generated.unlink()
"""


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def git(source, *args):
    return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()


def save(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def execute(source, folder, command, overrides):
    folder.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **overrides}
    started = now()
    log = folder / "console.txt"
    with log.open("x") as stream:
        result = subprocess.run(command, cwd=source, env=env, stdout=stream, stderr=subprocess.STDOUT)
    receipt = {
        "command": command, "cwd": str(source), "environment_overrides": overrides,
        "started": started, "finished": now(), "returncode": result.returncode,
        "console_sha256": sha(log),
    }
    save(folder / "execution.json", receipt)
    print(folder.name, "exit", result.returncode, flush=True)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--openxc7", type=Path, default=Path.home() / "opt/openxc7")
    args = parser.parse_args()
    source, out, build = args.source.resolve(), args.out.resolve(), args.build.resolve()
    if git(source, "rev-parse", "HEAD") != PIN or git(source, "status", "--porcelain"):
        raise ValueError("source must be the clean preregistered commit")
    if out.is_relative_to(source) or build.is_relative_to(source):
        raise ValueError("outputs must stay outside the source clone")
    if out.is_relative_to(build) or build.is_relative_to(out):
        raise ValueError("raw outputs and disposable builds must be separate")
    if out.exists() or build.exists():
        raise ValueError("output and build directories must not already exist")
    out.mkdir(parents=True)
    build.mkdir(parents=True)
    names = subprocess.check_output([
        "git", "-C", str(source), "ls-files", "-z", "hw/rtl", "hw/tb",
        "experiments/AV-04/scripts", "experiments/AV-07/scripts", "experiments/AV-08/scripts",
    ]).decode().split("\0")
    versions = {}
    for command in (
        ["yosys", "-V"], ["z3", "--version"], ["cvc5", "--version"], ["iverilog", "-V"],
        [str(args.openxc7 / "bin/yosys"), "-V"],
        [str(args.openxc7 / "bin/nextpnr-himbaechel"), "--version"],
    ):
        probe = subprocess.run(command, capture_output=True, text=True)
        versions[" ".join(command)] = {
            "returncode": probe.returncode, "output": probe.stdout + probe.stderr,
        }
    preflight = {
        "timestamp": now(), "host": platform.node(), "platform": platform.platform(),
        "python": sys.version, "source_commit": PIN, "source_clean_before": True,
        "driver_commit": git(HERE, "rev-parse", "HEAD"),
        "driver_sha256": sha(Path(__file__)), "comparator_sha256": sha(HERE / "compare.py"),
        "protocol_sha256": sha(HERE / "protocol.md"), "tool_versions": versions,
        "source_sha256": {name: sha(source / name) for name in names if name},
        "reference_sha256": {
            name: sha(source / name) for name in (
                "experiments/AV-04/raw/av04_formal/av04_results.csv",
                "experiments/AV-04/raw/av04_formal/av04_provenance.json",
                "experiments/AV-04/raw/av04_formal_cvc5/av04_results.csv",
                "experiments/AV-04/raw/av04_formal_cvc5/av04_provenance.json",
                "experiments/AV-07/raw/av07_mutation_results.json",
                "experiments/AV-08/raw/av08_scaling/av08_results.csv",
                "experiments/AV-08/raw/av08_scaling/av08_provenance.json",
            )
        },
        "historical_revision_identity": "not established; see preregistered protocol",
    }
    save(out / "preflight.json", preflight)
    results = []

    def record(name, receipt, differences):
        status = "EXECUTION_FAILED" if receipt["returncode"] else (
            "DIFFERENT" if differences else "MATCH"
        )
        results.append({"case": name, "status": status, "differences": differences})
        print(name, status, "differences", len(differences), flush=True)

    for solver, reference in (("z3", "av04_formal"), ("cvc5", "av04_formal_cvc5")):
        folder = out / f"av04_{solver}"
        destination = folder / "results"
        receipt = execute(
            source, folder,
            ["python3", "experiments/AV-04/scripts/run_av04_formal.py", "--depth", "25", "--solver", solver],
            {"AV04_OUT_DIR": str(destination)},
        )
        actual = Path(str(destination) + ("_cvc5" if solver == "cvc5" else "")) / "av04_results.csv"
        differences = compare_rows(
            csv_rows(source / f"experiments/AV-04/raw/{reference}/av04_results.csv"),
            csv_rows(actual) if actual.exists() else [],
            ["design", "width", "mode"],
            ["status", "asserts", "covers", "reached_covers", "unreached_covers"],
        )
        record(f"AV-04/{solver}", receipt, differences)

    folder = out / "av07"
    receipt = execute(
        source, folder,
        ["python3", "-c", AV07_CHILD, str(source / "experiments/AV-07/scripts/run_av07_mutation.py")],
        {"AV07_OUT_DIR": str(folder)},
    )
    expected = mutation_rows(source / "experiments/AV-07/raw/av07_mutation_results.json")
    actual_path = folder / "raw/av07_mutation_results.json"
    actual = mutation_rows(actual_path) if actual_path.exists() else []
    differences = compare_rows(
        expected[:1], actual[:1], ["id"],
        ["total_mutants", "killed_mutants", "survived_mutants", "mutation_score_pct"],
    ) + compare_rows(expected[1:], actual[1:], ["id"], ["status", "stage"])
    record("AV-07", receipt, differences)

    reference = csv_rows(source / "experiments/AV-08/raw/av08_scaling/av08_results.csv")
    cases = [
        (series, n) for series in ("S1_lanes", "S1_stub", "S2_bram", "S3_rcfc")
        for n in sorted({int(row["N"]) for row in reference if row["series"] == series})
    ]
    skipped = []
    for index, (series, n) in enumerate(cases):
        name = f"{series}_N{n}"
        folder = out / "av08" / name
        receipt = execute(
            source, folder,
            ["python3", "experiments/AV-08/scripts/run_av08_scaling.py",
             "--series", series, "--ns", str(n), "--seeds", "1", "2", "3",
             "--jobs", "1", "--pnr-timeout", "3600"],
            {"AV08_OUT_DIR": str(folder), "AV08_BUILD_DIR": str(build / name),
             "OPENXC7_DIR": str(args.openxc7.resolve())},
        )
        expected = [row for row in reference if row["series"] == series and int(row["N"]) == n]
        actual_path = folder / "av08_results.csv"
        differences = compare_rows(
            expected, csv_rows(actual_path) if actual_path.exists() else [],
            ["series", "N", "seed"], list(expected[0]),
        )
        record(f"AV-08/{name}", receipt, differences)
        if results[-1]["status"] != "MATCH":
            skipped = [f"{s}_N{count}" for s, count in cases[index + 1:]]
            break
    clean_after = not git(source, "status", "--porcelain")
    result = {
        "timestamp": now(), "source_commit": PIN, "source_clean_after": clean_after,
        "results": results, "av08_not_executed": skipped,
        "issue75": "NOT_ESTABLISHED: identical historical source SHA unavailable",
        "raw_sha256": {
            path.relative_to(out).as_posix(): sha(path)
            for path in sorted(out.rglob("*")) if path.is_file()
        },
    }
    save(out / "comparison.json", result)
    print(json.dumps({"results": results, "av08_not_executed": skipped}, ensure_ascii=False, indent=2))
    different = not clean_after or any(item["status"] != "MATCH" for item in results)
    return 1 if different else 2


if __name__ == "__main__":
    raise SystemExit(main())
