#!/usr/bin/env python3
"""Structural evidence lint, not S1 acceptance; see report-provenance.md."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PLACEHOLDERS = {"unknown", "n/a", "none", "null", "todo", "tbd", "...", "—"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def experiment_root(root):
    relocated = root / "Engineering" / "validation" / "experiments"
    return relocated if relocated.is_dir() else root / "experiments"


def required_text(record, key):
    value = record.get(key)
    if not isinstance(value, str) or not value.strip() or value.strip().lower() in PLACEHOLDERS:
        raise ValueError(f"{key}: required non-placeholder string")
    return value


def validate_run(root, report, run, numeric_lines):
    if not isinstance(run, dict):
        raise ValueError("run must be an object")
    required_text(run, "command")
    required_text(run, "host")
    commit = required_text(run, "git_commit")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
        raise ValueError("git_commit: full hexadecimal commit SHA required")
    result = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-t", commit],
        capture_output=True, text=True,
    )
    if result.returncode or result.stdout.strip() != "commit":
        raise ValueError("git_commit: commit unavailable in this repository")
    timestamp = datetime.fromisoformat(required_text(run, "timestamp"))
    if timestamp.tzinfo is None:
        raise ValueError("timestamp: timezone required")
    committed = subprocess.check_output(
        ["git", "-C", str(root), "show", "-s", "--format=%ct", commit], text=True,
    )
    if timestamp < datetime.fromtimestamp(int(committed), timezone.utc):
        raise ValueError("timestamp: earlier than source commit")
    if timestamp > datetime.now(timezone.utc):
        raise ValueError("timestamp: later than audit time")
    raw = run.get("raw")
    if not isinstance(raw, list) or not raw:
        raise ValueError("raw: nonempty list required")
    for evidence in raw:
        if not isinstance(evidence, dict):
            raise ValueError("raw entry must be an object")
        relative = Path(required_text(evidence, "path"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("raw path must be repository-relative without '..'")
        path = (root / relative).resolve()
        relative_report = report.relative_to(experiment_root(root))
        experiment = experiment_root(root)
        if len(relative_report.parts) > 1:
            experiment /= relative_report.parts[0]
        if not path.is_relative_to(root) or not path.is_relative_to(experiment / "raw"):
            raise ValueError("raw path must stay inside this experiment's raw directory")
        expected = required_text(evidence, "sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or digest(path) != expected:
            raise ValueError(f"raw digest mismatch: {relative.as_posix()}")
    lines = run.get("lines")
    if not isinstance(lines, list) or not lines:
        raise ValueError("lines: nonempty list required")
    if any(type(line) is not int or line not in numeric_lines for line in lines):
        raise ValueError("lines must reference existing numeric lines of the pinned report")
    return set(lines)


def check_report(root, report):
    result = {
        "report": report.relative_to(root).as_posix(),
        "numeric_lines": [],
        "covered_lines": [],
        "uncovered_lines": [],
        "errors": [],
    }
    try:
        if not report.resolve().is_relative_to(root):
            raise ValueError("report resolves outside repository")
        result["report_sha256"] = digest(report)
        numeric_lines = {
            n for n, line in enumerate(report.read_text(encoding="utf-8").splitlines(), 1)
            if any(char.isnumeric() for char in line)
        }
        result["numeric_lines"] = sorted(numeric_lines)
        if not numeric_lines:
            raise ValueError("report contains no numeric evidence to check")
        metadata = json.loads(report.with_suffix(".provenance.json").read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("provenance must be an object")
        if metadata.get("report_sha256") != result["report_sha256"]:
            raise ValueError("report_sha256 mismatch: stale provenance")
        runs = metadata.get("runs")
        if not isinstance(runs, list) or not runs:
            raise ValueError("runs: nonempty list required")
        covered = set()
        for index, run in enumerate(runs):
            try:
                covered.update(validate_run(root, report, run, numeric_lines))
            except (OSError, ValueError) as error:
                result["errors"].append(f"run[{index}]: {error}")
        result["covered_lines"] = sorted(covered)
    except (OSError, ValueError) as error:
        result["errors"].append(str(error))
    result["uncovered_lines"] = sorted(
        set(result["numeric_lines"]) - set(result["covered_lines"])
    )
    if result["uncovered_lines"]:
        result["errors"].append("numeric lines lack validated provenance")
    return result


def check(root):
    root = Path(root).resolve()
    experiments = experiment_root(root)
    reports = [
        check_report(root, path)
        for path in sorted(experiments.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}
        and not {"raw", "scripts"}.intersection(path.relative_to(experiments).parts[:-1])
        and path != experiments / "PLAN.md"
    ]
    errors = [] if reports else ["no experimental report documents found"]
    return {
        "status": "STRUCTURAL_FAIL" if errors or any(report["errors"] for report in reports)
        else "STRUCTURAL_PASS",
        "s1_status": "NOT_ASSESSED",
        "result_values_verified": False,
        "metadata_authenticated": False,
        "reports": reports,
        "errors": errors,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true", help="emit full machine-readable diagnostics")
    args = parser.parse_args(argv)
    result = check(args.root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{result['status']}; documents: {len(result['reports'])}; S1: NOT_ASSESSED")
        for report in result["reports"]:
            for error in report["errors"]:
                print(f"{report['report']}: {error}")
        for error in result["errors"]:
            print(error)
    return int(result["status"] != "STRUCTURAL_PASS")


if __name__ == "__main__":
    raise SystemExit(main())
