"""Synthetic provenance fixtures: not experimental or hardware evidence."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

TOOL = Path(__file__).resolve().parents[1] / "check_report_provenance.py"
spec = importlib.util.spec_from_file_location("report_provenance", TOOL)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


@pytest.fixture()
def experiment(tmp_path):
    root = tmp_path / "repo"
    raw = root / "experiments/AV-01/raw/samples.csv"
    raw.parent.mkdir(parents=True)
    raw.write_text("latency_ns\n10\n")
    report = raw.parent.parent / "report.md"
    report.write_text("# Synthetic fixture\nLatency: 10 ns\nCount: 1\n")

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    git("init", "-q")
    git("add", "experiments")
    git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "fixture")
    metadata = {
        "report_sha256": tool.digest(report),
        "runs": [{
            "command": "python3 synthetic_measurement.py",
            "git_commit": git("rev-parse", "HEAD"),
            "timestamp": "2026-11-10T09:00:00+00:00",
            "host": "synthetic-fixture",
            "raw": [{
                "path": raw.relative_to(root).as_posix(),
                "sha256": tool.digest(raw),
            }],
            "lines": [2, 3],
        }],
    }
    sidecar = report.with_suffix(".provenance.json")
    sidecar.write_text(json.dumps(metadata))
    return root, report, raw, sidecar, metadata


def test_complete_fixture_and_cli_pass(experiment):
    root, _, _, _, _ = experiment
    result = subprocess.run(
        [sys.executable, str(TOOL), "--root", str(root), "--json"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "PASS"


@pytest.mark.parametrize("field", ["command", "git_commit", "timestamp", "host", "raw", "lines"])
def test_missing_required_provenance_fails(experiment, field):
    root, _, _, sidecar, metadata = experiment
    del metadata["runs"][0][field]
    sidecar.write_text(json.dumps(metadata))
    result = tool.check(root)
    assert result["status"] == "FAIL"
    assert result["reports"][0]["uncovered_lines"] == [2, 3]


@pytest.mark.parametrize("field,value", [
    ("git_commit", "unknown"),
    ("git_commit", "0" * 40),
    ("timestamp", "2026-11-10T09:00:00"),
    ("timestamp", "2026-02-30T09:00:00+00:00"),
    ("command", "TBD"),
    ("host", "unknown"),
    ("lines", [2]),
    ("lines", [2, 3, 999]),
    ("raw", []),
])
def test_invalid_or_partial_provenance_fails(experiment, field, value):
    root, _, _, sidecar, metadata = experiment
    metadata["runs"][0][field] = value
    sidecar.write_text(json.dumps(metadata))
    assert tool.check(root)["status"] == "FAIL"


@pytest.mark.parametrize("mutation", ["report", "raw", "missing_raw", "missing_sidecar", "invalid_json"])
def test_changed_or_missing_evidence_fails(experiment, mutation):
    root, report, raw, sidecar, _ = experiment
    if mutation == "report":
        report.write_text(report.read_text().replace("10 ns", "999 ns"))
    elif mutation == "raw":
        raw.write_text("latency_ns\n999\n")
    elif mutation == "missing_raw":
        raw.unlink()
    elif mutation == "missing_sidecar":
        sidecar.unlink()
    else:
        sidecar.write_text("{")
    result = subprocess.run(
        [sys.executable, str(TOOL), "--root", str(root), "--json"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "FAIL"


def test_new_report_is_not_silently_skipped(experiment):
    root, _, _, _, _ = experiment
    other = root / "experiments/AV-02"
    other.mkdir()
    (other / "report.md").write_text("Latency: 7 ns\n")
    result = tool.check(root)
    assert result["status"] == "FAIL"
    assert len(result["reports"]) == 2


def test_empty_scope_fails(tmp_path):
    assert tool.check(tmp_path)["status"] == "FAIL"


def test_multiple_runs_jointly_cover_report(experiment):
    root, _, _, sidecar, metadata = experiment
    second = copy.deepcopy(metadata["runs"][0])
    metadata["runs"][0]["lines"] = [2]
    second["lines"] = [3]
    metadata["runs"].append(second)
    sidecar.write_text(json.dumps(metadata))
    assert tool.check(root)["status"] == "PASS"


def test_valid_run_cannot_hide_invalid_run(experiment):
    root, _, _, sidecar, metadata = experiment
    second = copy.deepcopy(metadata["runs"][0])
    second["git_commit"] = "unknown"
    metadata["runs"].append(second)
    sidecar.write_text(json.dumps(metadata))
    result = tool.check(root)
    assert result["status"] == "FAIL"
    assert result["reports"][0]["uncovered_lines"] == []


def test_foreign_or_traversing_raw_path_fails(experiment):
    root, _, _, sidecar, original = experiment
    for path in ("../samples.csv", str(root / "samples.csv"), "experiments/AV-02/raw/samples.csv"):
        metadata = copy.deepcopy(original)
        metadata["runs"][0]["raw"][0]["path"] = path
        sidecar.write_text(json.dumps(metadata))
        assert tool.check(root)["status"] == "FAIL"


def test_regenerated_report_hash_does_not_hide_uncovered_unicode_number(experiment):
    root, report, _, sidecar, metadata = experiment
    report.write_text(report.read_text() + "Additional value: ²\n")
    metadata["report_sha256"] = tool.digest(report)
    sidecar.write_text(json.dumps(metadata))
    result = tool.check(root)
    assert result["status"] == "FAIL"
    assert result["reports"][0]["uncovered_lines"] == [4]
