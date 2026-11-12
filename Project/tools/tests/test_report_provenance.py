"""Synthetic provenance fixtures: not experimental or hardware evidence."""

import copy
from datetime import datetime, timedelta, timezone
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
    data = json.loads(result.stdout)
    assert data["status"] == "STRUCTURAL_PASS"
    assert data["s1_status"] == "NOT_ASSESSED"
    assert data["result_values_verified"] is False
    assert data["metadata_authenticated"] is False


@pytest.mark.parametrize("field", ["command", "git_commit", "timestamp", "host", "raw", "lines"])
def test_missing_required_provenance_fails(experiment, field):
    root, _, _, sidecar, metadata = experiment
    del metadata["runs"][0][field]
    sidecar.write_text(json.dumps(metadata))
    result = tool.check(root)
    assert result["status"] == "STRUCTURAL_FAIL"
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
    assert tool.check(root)["status"] == "STRUCTURAL_FAIL"


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
    assert json.loads(result.stdout)["status"] == "STRUCTURAL_FAIL"


def test_new_report_is_not_silently_skipped(experiment):
    root, _, _, _, _ = experiment
    other = root / "experiments/AV-02"
    other.mkdir()
    (other / "report.md").write_text("Latency: 7 ns\n")
    result = tool.check(root)
    assert result["status"] == "STRUCTURAL_FAIL"
    assert len(result["reports"]) == 2


def test_empty_scope_fails(tmp_path):
    assert tool.check(tmp_path)["status"] == "STRUCTURAL_FAIL"


def test_relocated_ng_experiments_use_same_provenance_contract(experiment):
    root, _, _, _, metadata = experiment
    target = root / "Engineering/validation"
    target.mkdir(parents=True)
    (root / "experiments").rename(target / "experiments")
    report = target / "experiments/AV-01/report.md"
    metadata["runs"][0]["raw"][0]["path"] = (
        "Engineering/validation/experiments/AV-01/raw/samples.csv"
    )
    report.with_suffix(".provenance.json").write_text(json.dumps(metadata))
    assert tool.check(root)["status"] == "STRUCTURAL_PASS"
    (target / "experiments/AV-01/raw/samples.csv").write_text("latency_ns\n999\n")
    assert tool.check(root)["status"] == "STRUCTURAL_FAIL"


def test_multiple_runs_jointly_cover_report(experiment):
    root, _, _, sidecar, metadata = experiment
    second = copy.deepcopy(metadata["runs"][0])
    metadata["runs"][0]["lines"] = [2]
    second["lines"] = [3]
    metadata["runs"].append(second)
    sidecar.write_text(json.dumps(metadata))
    assert tool.check(root)["status"] == "STRUCTURAL_PASS"


def test_valid_run_cannot_hide_invalid_run(experiment):
    root, _, _, sidecar, metadata = experiment
    second = copy.deepcopy(metadata["runs"][0])
    second["git_commit"] = "unknown"
    metadata["runs"].append(second)
    sidecar.write_text(json.dumps(metadata))
    result = tool.check(root)
    assert result["status"] == "STRUCTURAL_FAIL"
    assert result["reports"][0]["uncovered_lines"] == []


def test_foreign_or_traversing_raw_path_fails(experiment):
    root, _, _, sidecar, original = experiment
    for path in ("../samples.csv", str(root / "samples.csv"), "experiments/AV-02/raw/samples.csv"):
        metadata = copy.deepcopy(original)
        metadata["runs"][0]["raw"][0]["path"] = path
        sidecar.write_text(json.dumps(metadata))
        assert tool.check(root)["status"] == "STRUCTURAL_FAIL"


def test_regenerated_report_hash_does_not_hide_uncovered_unicode_number(experiment):
    root, report, _, sidecar, metadata = experiment
    report.write_text(report.read_text() + "Additional value: ²\n")
    metadata["report_sha256"] = tool.digest(report)
    sidecar.write_text(json.dumps(metadata))
    result = tool.check(root)
    assert result["status"] == "STRUCTURAL_FAIL"
    assert result["reports"][0]["uncovered_lines"] == [4]


@pytest.mark.parametrize("relative", [
    "experiments/AV-01/Report.md",
    "experiments/AV-01/report.txt",
    "experiments/AV-01/notes/report.md",
    "experiments/KPOL-FIX/report.md",
    "experiments/AV-01/results.MD",
])
def test_renamed_nested_and_non_av_reports_cannot_escape(experiment, relative):
    root, _, _, _, _ = experiment
    other = root / relative
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("New measurement: 999 ns\n")
    result = tool.check(root)
    assert result["status"] == "STRUCTURAL_FAIL"
    assert any(item["report"] == relative and item["uncovered_lines"] for item in result["reports"])


@pytest.mark.parametrize("timestamp", [
    "1990-01-01T00:00:00+00:00",
    (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
])
def test_impossible_chronology_fails(experiment, timestamp):
    root, _, _, sidecar, metadata = experiment
    metadata["runs"][0]["timestamp"] = timestamp
    sidecar.write_text(json.dumps(metadata))
    result = tool.check(root)
    assert result["status"] == "STRUCTURAL_FAIL"
    assert any("timestamp:" in error for error in result["reports"][0]["errors"])


def test_rehashed_false_value_is_not_certified_as_s1(experiment):
    root, report, _, sidecar, metadata = experiment
    report.write_text(report.read_text().replace("10 ns", "999 ns"))
    metadata["report_sha256"] = tool.digest(report)
    sidecar.write_text(json.dumps(metadata))
    result = tool.check(root)
    assert result["status"] == "STRUCTURAL_PASS"
    assert result["s1_status"] == "NOT_ASSESSED"
    assert result["result_values_verified"] is False
    assert result["metadata_authenticated"] is False


def test_nested_report_uses_experiment_raw_directory(experiment):
    root, report, _, sidecar, _ = experiment
    nested = report.parent / "notes"
    nested.mkdir()
    report.rename(nested / report.name)
    sidecar.rename(nested / sidecar.name)
    assert tool.check(root)["status"] == "STRUCTURAL_PASS"


@pytest.mark.parametrize("shape", [None, [], 42, "text"])
def test_invalid_provenance_object_shapes_fail_closed(experiment, shape):
    root, _, _, sidecar, _ = experiment
    sidecar.write_text(json.dumps(shape))
    assert tool.check(root)["status"] == "STRUCTURAL_FAIL"


def test_command_and_host_strings_do_not_authenticate_execution(experiment):
    root, _, _, sidecar, metadata = experiment
    metadata["runs"][0].update(command="echo 999", host="x")
    sidecar.write_text(json.dumps(metadata))
    result = tool.check(root)
    assert result["status"] == "STRUCTURAL_PASS"
    assert result["metadata_authenticated"] is False
    assert result["s1_status"] == "NOT_ASSESSED"
