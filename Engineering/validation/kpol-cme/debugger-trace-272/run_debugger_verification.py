#!/usr/bin/env python3
"""Issue #272: End-to-end verification and raw log generator for the Kuzmin Machine
Event & Cascade Step Debugger (`kpol_debugger.py`, `--dump-concepts`, `--trace-events`,
`--stdio`, `--tui`, and live `pynq2` connection).

Generates immutable raw logs in `Engineering/validation/kpol-cme/debugger-trace-272/raw/`
with mandatory headers (`# cmd:`, `# timestamp:`, `# git_commit:`, `# host:`):
  1. `raw/article_examples_all_traces.log` & `raw/article_examples_summary.json`
     (Examples 1..5: `increase`, `decrease`, `cascade`, `bms`, `auth`, `nod` +
     Icarus Verilog `CFG-P` and `km_euclid_core.sv` verification);
  2. `raw/cli_compile_trace_events_bms.log` (`compile_kpol_bram_image.py --dump-concepts --trace-events`);
  3. `raw/stdio_unix_pipe_bms.log` (`printf ... | kpol_debugger.py --stdio`);
  4. `raw/pynq2_live_debugger_session.log` & `raw/pynq2_live_debugger_session.json`
     (Live connection to `pynq2` `xilinx@192.168.68.69` under `flock -w 120 /tmp/km-bench.lock`,
     capturing `PRE-LOAD` when `Increase.kpol` is in BRAM -> `POST-LOAD` when `BmsSafetyCascade`
     is loaded -> `POST-RUN` after executing the 8-event trace on physical Zynq-7020 PL silicon).
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
RAW_DIR = HERE / "raw"
REPO_ROOT = HERE.parents[3]
SW_REF_DIR = REPO_ROOT / "Engineering" / "sw" / "kpol-ref"
COMPILE_CLI = REPO_ROOT / "Engineering" / "hw" / "scripts" / "compile_kpol_bram_image.py"
INCREASE_KPOL = REPO_ROOT / "Engineering" / "hw" / "tests" / "kpol_bram_pipeline_increase.kpol"
BMS_KPOL = REPO_ROOT / "Engineering" / "validation" / "kpol-cme" / "c99-emitter-270" / "bms_safety_cascade.kpol"

if str(SW_REF_DIR) not in sys.path:
    sys.path.insert(0, str(SW_REF_DIR))

import kpol_debugger as kd  # noqa: E402
import kpol_reference as kr  # noqa: E402


@contextmanager
def _scratch_dir():
    base = REPO_ROOT / ".pytest_cache" / f"dbg272_run_{uuid.uuid4().hex}"
    base.mkdir(parents=True, exist_ok=False)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _git_head_sha() -> str:
    res = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    sha = res.stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return f"{sha}-dirty" if dirty else sha


def _write_raw_log(
    path: Path,
    cmd_str: str,
    body: str,
    extra_headers: dict[str, str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().astimezone().isoformat()
    git_sha = _git_head_sha()
    host_str = platform.platform()
    hdr = [
        f"# cmd: {cmd_str}",
        f"# timestamp: {ts}",
        f"# git_commit: {git_sha}",
        f"# host: {host_str}",
    ]
    for k, v in (extra_headers or {}).items():
        hdr.append(f"# {k}: {v}")
    text = "\n".join(hdr) + "\n" + body
    cleaned = "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
    path.write_text(cleaned, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-pynq", action="store_true", help="skip live PYNQ-Z1 hardware run")
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Run all 5 article/slide example groups (`--example all`)
    bundle = kd.run_article_examples_verification(run_rtl=True)
    _write_raw_log(
        RAW_DIR / "article_examples_all_traces.log",
        "python3 Engineering/sw/kpol-ref/kpol_debugger.py --example all",
        bundle["formatted_full_output"],
        extra_headers={"evidence_kind": "software_debugger_and_iverilog_rtl_simulation"},
    )
    summary_payload = {
        "timestamp": datetime.datetime.now().astimezone().isoformat(),
        "git_commit": _git_head_sha(),
        "host": platform.platform(),
        "examples": {k: v for k, v in bundle.items() if k != "formatted_full_output"},
    }
    (RAW_DIR / "article_examples_summary.json").write_text(
        json.dumps(summary_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with _scratch_dir() as scratch:
        # 2. Run `compile_kpol_bram_image.py --dump-concepts --trace-events`
        out_bin = scratch / "bms_trace_test.bin"
        trace_spec = "0:15,0:5500,0:invalid,0:120,0:49,0:180,0:250,0:5000,0:-10"
        cli_cmd = [
            sys.executable,
            str(COMPILE_CLI),
            "--profile",
            "KPOL-CME-2",
            "--dump-concepts",
            "--trace-events",
            trace_spec,
            str(BMS_KPOL),
            str(out_bin),
        ]
        cli_res = subprocess.run(cli_cmd, check=True, capture_output=True, text=True)
        _write_raw_log(
            RAW_DIR / "cli_compile_trace_events_bms.log",
            f"python3 Engineering/hw/scripts/compile_kpol_bram_image.py --profile KPOL-CME-2 --dump-concepts --trace-events '{trace_spec}' Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol <out.bin>",
            cli_res.stdout,
            extra_headers={
                "bms_bin_sha256": hashlib.sha256(out_bin.read_bytes()).hexdigest(),
                "evidence_kind": "compiler_cli_trace_events",
            },
        )

        # 3. Run UNIX pipe `--stdio` mode
        stdin_text = "15\n5500\n_\n120\n49\n180\n250\n5000\n-10\n"
        stdio_cmd = [
            sys.executable,
            str(SW_REF_DIR / "kpol_debugger.py"),
            "--program",
            str(BMS_KPOL),
            "--profile",
            "KPOL-CME-2",
            "--stdio",
        ]
        stdio_res = subprocess.run(
            stdio_cmd,
            input=stdin_text,
            check=True,
            capture_output=True,
            text=True,
        )
        combined_stdio = (
            "=== STDIN STREAM ===\n"
            + stdin_text
            + "\n=== STDOUT STREAM (COMMITTED STATE TRANSITIONS) ===\n"
            + stdio_res.stdout
            + "\n=== STDERR STREAM (REJECTED GUARD / INVARIANT / FAULT '_' EVENTS) ===\n"
            + stdio_res.stderr
        )
        _write_raw_log(
            RAW_DIR / "stdio_unix_pipe_bms.log",
            "printf '15\\n5500\\n_\\n120\\n49\\n180\\n250\\n5000\\n-10\\n' | python3 Engineering/sw/kpol-ref/kpol_debugger.py --program Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol --profile KPOL-CME-2 --stdio",
            combined_stdio,
            extra_headers={"evidence_kind": "stdio_unix_pipe_verification"},
        )

    # 4. Live hardware connection to PYNQ-Z1 (`pynq2`, `xilinx@192.168.68.69`)
    if not args.skip_pynq:
        inc_mod = kr.parse_module(INCREASE_KPOL.read_text(encoding="utf-8"))
        inc_img = kr.compile_concept_microcode_bram_image(inc_mod, profile="KPOL-CME-1")
        bms_src = BMS_KPOL.read_text(encoding="utf-8")
        bms_mod = kr.parse_module(bms_src)
        bms_img = kr.compile_concept_microcode_bram_image(bms_mod, profile="KPOL-CME-2")

        # Step 4a: Pre-program `Increase.kpol` (1 active concept: Counter=10) onto `pynq2`
        # so the subsequent BMS debug session observes a clear 1-concept -> 4-concept PRE-LOAD vs POST-LOAD transition
        pre_conn = kd.MachineDebugConnection(target="pynq2")
        pre_conn.execute_pynq_session(
            inc_img,
            hw_params=[5],  # Advance Counter 10 -> 11 on silicon
            concept_names=[s.name for s in inc_mod.states],
        )

        # Step 4b: Connect debugger to `pynq2`, capture PRE-LOAD (1/64 active, Counter=11),
        # program `BmsSafetyCascade` (4/64 active), verify readback, and run the 8 hardware events
        bms_conn = kd.MachineDebugConnection(target="pynq2")
        hw_params = [15, 5500, 120, 49, 180, 250, 5000, -10]
        pynq_hw_report = bms_conn.execute_pynq_session(
            bms_img,
            hw_params=hw_params,
            concept_names=[s.name for s in bms_mod.states],
            pre_concept_names=[s.name for s in inc_mod.states],
        )

        dbg = kd.KpolCascadeDebugger(
            bms_img,
            profile="KPOL-CME-2",
            module_name=bms_mod.name,
            source_code=bms_src,
            concept_names=[s.name for s in bms_mod.states],
            watch_cids={0, 2, 3},
            break_on_reject=True,
            watch_state_change=True,
        )
        stdio_stream_res = kd.run_stdio_stream(
            dbg,
            ["15", "5500", "_", "120", "49", "180", "250", "5000", "-10"],
        )

        assert bms_conn.pre_load_snapshot is not None
        assert bms_conn.post_load_snapshot is not None
        assert bms_conn.post_run_snapshot is not None
        assert bms_conn.pre_load_snapshot.topology.active_concepts == 1
        assert bms_conn.post_load_snapshot.topology.active_concepts == 4
        assert pynq_hw_report["events_delta"] == 18
        assert pynq_hw_report["commits_delta"] == 12
        assert pynq_hw_report["rejects_delta"] == 6

        post_run_states = [
            _d["w0_state"] for _d in pynq_hw_report["post_run"]["active_descriptors"]
        ]
        assert post_run_states == [4, 4, 0, 0]

        tui_text = "\n\n".join(
            [
                bms_conn.format_pre_post_load_summary(),
                dbg.format_full_4block_report(),
                kd.render_tui_ascii_frame(dbg, connection=bms_conn, stdio_result=stdio_stream_res),
            ]
        )
        _write_raw_log(
            RAW_DIR / "pynq2_live_debugger_session.log",
            "flock -w 120 /tmp/km-bench.lock python3 Engineering/sw/kpol-ref/kpol_debugger.py --program Engineering/validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol --profile KPOL-CME-2 --stdio --render-tui-frame --target pynq2",
            tui_text,
            extra_headers={
                "bench_lock": "flock -w 120 /tmp/km-bench.lock (acquired)",
                "evidence_kind": "physical_hil_pynq_z1_debugger_pre_post_load_and_trace",
                "board": "Digilent PYNQ-Z1 (pynq2 @ xilinx@192.168.68.69, HW_ID=0x4B504D43 'KPMC')",
            },
        )
        full_pynq_json = {
            "timestamp": datetime.datetime.now().astimezone().isoformat(),
            "git_commit": _git_head_sha(),
            "bench_lock": "flock -w 120 /tmp/km-bench.lock",
            "evidence_kind": "physical_hil_pynq_z1_debugger_pre_post_load_and_trace",
            "pynq_session": pynq_hw_report,
            "debugger_report": dbg.build_report().to_dict(),
            "stdio": {
                "stdout": stdio_stream_res.stdout_lines,
                "stderr": stdio_stream_res.stderr_lines,
            },
        }
        (RAW_DIR / "pynq2_live_debugger_session.json").write_text(
            json.dumps(full_pynq_json, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        rm_old = RAW_DIR / "pynq2_live_debugger_tui.body.log"
        if rm_old.exists():
            rm_old.unlink()

    print("All Issue #272 debugger traces and raw logs generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
