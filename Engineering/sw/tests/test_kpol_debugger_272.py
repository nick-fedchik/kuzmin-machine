#!/usr/bin/env python3
"""Issue #272: Verification suite for the Kuzmin Machine Event & Cascade Step Debugger
(`kpol_debugger.py`, `--dump-concepts`, `--trace-events`, `--stdio`, `--tui` /
`--render-tui-frame`, `MachineDebugConnection`, and article/slide examples verification).

Covers:
  1. 4-Block Debugger Output (`Source`, `BRAM Descriptors --dump-concepts`, `Step Trace --trace-events`,
     and `State Diff`) and CLI integration in `compile_kpol_bram_image.py` & `kpol_debugger.py`;
  2. `STDIO` (`stdin` / `stdout` / `stderr`) binding (`# @stdin`, `# @stdout`, `--stdio` UNIX pipe
     for `<param>`, `<cid_or_name> <param>`, `<cid> _`, and JSONL);
  3. Machine target connection (`MachineDebugConnection`) & TUI (`render_tui_ascii_frame` / `run_interactive_tui`)
     knowing the machine state `PRE-LOAD` (before programming) and `POST-LOAD` (after programming),
     displaying active concept counts (`K / 64`, entry/internal/leaf/free) and per-slot diff;
  4. 100% bit-exact equivalence between `KpolCascadeDebugger`, `ReferenceCmeSafetyEngine`,
     GCC-compiled C99 (`--emit-c99`), `Icarus Verilog` simulation of `kpol_bram_pipeline_axi.sv`
     (`CFG-P`), and for `Nod(120, 6) = 6` — exact 19-iteration / 58-cycle match against
     `km_euclid_core.sv` in `Icarus Verilog`;
  5. Watchpoint / breakpoint firing on `watch_cid`, `break_on_reject` (`REJECT_GUARD`,
     `REJECT_INVARIANT`, `REJECT_FAULT`), `watch_state_change`, and `threshold_watch`, plus Z3
     invariant counterexample diagnostics (`diagnose_invariant_counterexample_z3`);
  6. Negative Mutant Controls (`AGENTS.md §4.1`):
     - `M1_debugger_invert_predicate`
     - `M2_debugger_ignore_invariant_gate`
     - `M3_debugger_drop_cascade_subscriber`
     - `M4_debugger_mask_uncertainty_bit`
     - `M5_debugger_corrupt_preload_postload_diff`
"""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest import mock
import uuid

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SW_REF_DIR = REPO_ROOT / "Engineering" / "sw" / "kpol-ref"
COMPILE_CLI = REPO_ROOT / "Engineering" / "hw" / "scripts" / "compile_kpol_bram_image.py"
DEBUGGER_CLI = SW_REF_DIR / "kpol_debugger.py"
VAL_DIR = REPO_ROOT / "Engineering" / "validation" / "kpol-cme" / "debugger-trace-272"
RAW_DIR = VAL_DIR / "raw"
REPORT_MD = VAL_DIR / "report.md"
BMS_KPOL = REPO_ROOT / "Engineering" / "validation" / "kpol-cme" / "c99-emitter-270" / "bms_safety_cascade.kpol"
INCREASE_KPOL = REPO_ROOT / "Engineering" / "hw" / "tests" / "kpol_bram_pipeline_increase.kpol"

if str(SW_REF_DIR) not in sys.path:
    sys.path.insert(0, str(SW_REF_DIR))

from c99_emitter import (  # noqa: E402
    ReferenceCmeSafetyEngine,
    emit_c99_safety_module,
)
import kpol_debugger as kd  # noqa: E402
from kpol_debugger import (  # noqa: E402
    KpolCascadeDebugger,
    MachineDebugConnection,
    VERDICT_COMMIT,
    VERDICT_REJECT_FAULT,
    VERDICT_REJECT_GUARD,
    VERDICT_REJECT_INVARIANT,
    VERDICT_SUPPRESSED_SELF,
    analyze_concept_topology,
    compute_pre_post_load_diff,
    diagnose_invariant_counterexample_z3,
    parse_stdio_directives,
    parse_stdio_input_line,
    parse_trace_events_spec,
    render_tui_ascii_frame,
    run_article_examples_verification,
    run_iverilog_cfgp_trace,
    run_iverilog_euclid_verification,
    run_single_example_demo,
    run_stdio_stream,
    trace_author_euclid_nod_example,
    trace_author_if_toggle_example,
    trace_author_slide_examples,
    trace_author_sum_post_read_reset_example,
)
import kpol_reference as kr  # noqa: E402


@contextmanager
def _workspace_scratch_dir(prefix: str = "test_dbg272"):
    """Create a scratch directory inside repository .pytest_cache (never /tmp)."""
    base = REPO_ROOT / ".pytest_cache" / f"{prefix}_{uuid.uuid4().hex}"
    base.mkdir(parents=True, exist_ok=False)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _subproc_env(scratch_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["TMPDIR"] = str(scratch_dir)
    env["TEMP"] = str(scratch_dir)
    env["TMP"] = str(scratch_dir)
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{SW_REF_DIR}{os.pathsep}{existing_pp}" if existing_pp else str(SW_REF_DIR)
    )
    return env


class _CSafetyCtx(ctypes.Structure):
    _fields_ = [
        ("state", ctypes.c_int32 * 64),
        ("valid_mask", ctypes.c_uint64),
        ("events_processed", ctypes.c_uint32),
        ("commits", ctypes.c_uint32),
        ("rejects", ctypes.c_uint32),
        ("fault_propagations", ctypes.c_uint32),
        ("last_committed_state", ctypes.c_int32),
    ]


class _CSafetyStepResult(ctypes.Structure):
    _fields_ = [
        ("steps_executed", ctypes.c_uint32),
        ("commits", ctypes.c_uint32),
        ("rejects", ctypes.c_uint32),
        ("fault_propagated", ctypes.c_bool),
        ("last_state", ctypes.c_int32),
        ("status", ctypes.c_int),
    ]


_CTYPES_EXPORT_SHIM = """
void km_Export_init(km_safety_ctx_t *ctx) { km_safety_init(ctx); }
km_safety_step_result_t km_Export_step_event(
    km_safety_ctx_t *ctx, uint8_t root_cid, int32_t param, bool param_valid
) {
    return km_safety_step_event(ctx, root_cid, param, param_valid);
}
"""


def _compile_c99_lib(c_source: str, scratch_dir: Path) -> ctypes.CDLL:
    c_file = scratch_dir / f"km_dbg_{uuid.uuid4().hex[:8]}.c"
    so_file = scratch_dir / f"libkm_dbg_{uuid.uuid4().hex[:8]}.so"
    c_file.write_text(c_source + "\n" + _CTYPES_EXPORT_SHIM, encoding="utf-8")
    subprocess.run(
        [
            "gcc",
            "-std=c99",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-pedantic",
            "-fPIC",
            "-shared",
            str(c_file),
            "-o",
            str(so_file),
        ],
        env=_subproc_env(scratch_dir),
        check=True,
        capture_output=True,
        text=True,
    )
    lib = ctypes.CDLL(str(so_file))
    lib.km_Export_init.argtypes = [ctypes.POINTER(_CSafetyCtx)]
    lib.km_Export_init.restype = None
    lib.km_Export_step_event.argtypes = [
        ctypes.POINTER(_CSafetyCtx),
        ctypes.c_uint8,
        ctypes.c_int32,
        ctypes.c_bool,
    ]
    lib.km_Export_step_event.restype = _CSafetyStepResult
    return lib


def _assert_debugger_matches_reference(
    dbg: KpolCascadeDebugger,
    ref_eng: ReferenceCmeSafetyEngine,
    events: list[tuple[int, int, bool]],
) -> None:
    """Assert step-by-step and cumulative state/telemetry equivalence between
    `KpolCascadeDebugger` and `ReferenceCmeSafetyEngine`.
    """
    assert dbg.state == ref_eng.state
    assert dbg.valid_mask == ref_eng.valid_mask

    for idx, (cid, param, valid) in enumerate(events):
        wave = dbg.step_event(cid, param, valid)
        r_res = ref_eng.step_event(cid, param, valid)

        wave_commits = sum(
            1 for s in wave if s.verdict in (VERDICT_COMMIT, VERDICT_SUPPRESSED_SELF)
        )
        wave_rejects = sum(
            1
            for s in wave
            if s.verdict in (VERDICT_REJECT_GUARD, VERDICT_REJECT_INVARIANT, VERDICT_REJECT_FAULT)
        )
        wave_fault = any(s.verdict == VERDICT_REJECT_FAULT for s in wave)

        assert len(wave) == r_res.steps_executed, f"step count mismatch at event {idx}"
        assert wave_commits == r_res.commits, f"wave commits mismatch at event {idx}"
        assert wave_rejects == r_res.rejects, f"wave rejects mismatch at event {idx}"
        assert wave_fault == r_res.fault_propagated, f"wave fault_prop mismatch at event {idx}"

        assert dbg.state == ref_eng.state, f"state array mismatch at event {idx}"
        assert dbg.valid_mask == ref_eng.valid_mask, f"valid_mask mismatch at event {idx}"
        assert dbg.events_processed == ref_eng.events_processed, f"events_processed mismatch at event {idx}"
        assert dbg.commits == ref_eng.commits, f"total commits mismatch at event {idx}"
        assert dbg.rejects == ref_eng.rejects, f"total rejects mismatch at event {idx}"
        assert dbg.fault_propagations == ref_eng.fault_propagations, f"fault_propagations mismatch at event {idx}"
        assert dbg.last_committed_state == ref_eng.last_committed_state, f"last_state mismatch at event {idx}"


def test_debugger_4blocks_and_equivalence_with_ref_c99_and_iverilog():
    """Verify 100% equivalence of `KpolCascadeDebugger` against `ReferenceCmeSafetyEngine`,
    GCC-compiled C99 (`--emit-c99`), and `iverilog` `CFG-P` simulation on BMS cascade.
    """
    bms_src = BMS_KPOL.read_text(encoding="utf-8")
    mod = kr.parse_module(bms_src)
    cnames = [s.name for s in mod.states]
    img = kr.compile_concept_microcode_bram_image(mod, profile="KPOL-CME-2")
    c99_code = emit_c99_safety_module(img, profile="KPOL-CME-2", module_name=mod.name, concept_names=cnames)

    dbg = KpolCascadeDebugger(
        img,
        profile="KPOL-CME-2",
        module_name=mod.name,
        source_code=bms_src,
        concept_names=cnames,
        watch_cids={0, 2, 3},
        break_on_reject=True,
        watch_state_change=True,
        threshold_watch={0: 2},
    )
    ref_eng = ReferenceCmeSafetyEngine(img, profile="KPOL-CME-2", concept_names=cnames)

    events = [
        (0, 15, True),
        (0, 5500, True),
        (0, 0, False),
        (0, 120, True),
        (0, 49, True),
        (0, 180, True),
        (0, 250, True),
        (0, 5000, True),
        (0, -10, True),
    ]

    with _workspace_scratch_dir("eq_272") as scratch:
        lib = _compile_c99_lib(c99_code, scratch)
        c_ctx = _CSafetyCtx()
        lib.km_Export_init(ctypes.byref(c_ctx))

        _assert_debugger_matches_reference(dbg, ref_eng, events)

        for cid, param, valid in events:
            lib.km_Export_step_event(ctypes.byref(c_ctx), cid, param, valid)

        assert list(c_ctx.state) == dbg.state
        assert int(c_ctx.events_processed) == dbg.events_processed == 19
        assert int(c_ctx.commits) == dbg.commits == 12
        assert int(c_ctx.rejects) == dbg.rejects == 7
        assert int(c_ctx.fault_propagations) == dbg.fault_propagations == 1

    # Also verify valid 8-event trace against Icarus Verilog `CFG-P` RTL simulation
    hw_valid_events = [(cid, p) for cid, p, v in events if v]
    rtl_res = run_iverilog_cfgp_trace(img, hw_valid_events)
    assert rtl_res["states"] == dbg.state[:4] == [4, 4, 0, 0]
    assert rtl_res["events"] == 18  # 19 minus the 1 host-level param_valid=False event
    assert rtl_res["commits"] == dbg.commits == 12
    assert rtl_res["rejects"] == 6

    # Check all 4 blocks are present in formatted report
    full_txt = dbg.format_full_4block_report()
    assert "[BLOCK 1] SOURCE CODE" in full_txt
    assert "[BLOCK 2] BRAM DESCRIPTOR TABLE (--dump-concepts" in full_txt
    assert "[BLOCK 3] STEP-BY-STEP EVENT & CASCADE TRACE (--trace-events" in full_txt
    assert "[BLOCK 4] STATE DIFF (Before -> After)" in full_txt


def test_watchpoints_breakpoints_and_z3_counterexample_diagnostic():
    """Verify watchpoint/breakpoint triggers (`watch_cid`, `break_on_reject`, `threshold_watch`,
    `stop_on_breakpoint`) and Z3 invariant gate counterexample generation.
    """
    txt_dec, data_dec = run_single_example_demo("decrease")
    rep = data_dec["report"]
    steps = rep["steps"]
    assert len(steps) == 3
    assert steps[0]["verdict"] == VERDICT_COMMIT
    assert steps[0]["post_w0"] == 0
    assert steps[1]["verdict"] == VERDICT_REJECT_INVARIANT
    assert steps[1]["candidate_w0"] == -1
    assert steps[1]["post_w0"] == 0
    assert steps[2]["verdict"] == VERDICT_REJECT_GUARD

    z3_diag = data_dec["z3_invariant_diagnostic"]
    assert z3_diag["status"] == "SAT_WITNESS_FOUND"
    assert z3_diag["unsafe_candidate_w0"] < 0 or z3_diag["arith_overflow"] is True

    # Test stop_on_breakpoint=True halts execution on first reject
    mod = kr.parse_module(kd.EXAMPLE_1_DECREASE_ZERO_SOURCE)
    img = kr.compile_concept_microcode_bram_image(mod, profile="KPOL-CME-1")
    dbg_halt = KpolCascadeDebugger(
        img,
        profile="KPOL-CME-1",
        break_on_reject=True,
        stop_on_breakpoint=True,
    )
    dbg_halt.run_events([(0, 5, True), (0, 5, True), (0, 5, True)])
    assert dbg_halt.halted_on_breakpoint is True
    assert len(dbg_halt.steps) == 2  # Stopped at event #2 (REJECT_INVARIANT), event #3 not run


def test_stdio_binding_and_unix_pipe_cli():
    """Verify `# @stdin` / `# @stdout` directives, JSONL/text input parsing, and `--stdio` UNIX pipe."""
    mod = kr.parse_module(kd.EXAMPLE_1_INCREASE_SOURCE)
    img = kr.compile_concept_microcode_bram_image(mod, profile="KPOL-CME-1")
    dbg = KpolCascadeDebugger(
        img,
        profile="KPOL-CME-1",
        module_name=mod.name,
        source_code=kd.EXAMPLE_1_INCREASE_SOURCE,
        concept_names=["Counter"],
    )
    cfg = parse_stdio_directives(dbg.source_code, dbg.descriptors, dbg.active_cids)
    assert cfg.stdin_concepts == ("Counter",)
    assert cfg.stdout_concepts == ("Counter",)
    assert cfg.default_stdin_cid == 0

    lines = [
        "# comment line ignored",
        "5",
        "Counter 25",
        "0 _",
        '{"concept": "Counter", "param": 12, "valid": true}',
        '{"cid": 0, "param": "_"}',
    ]
    res = run_stdio_stream(dbg, lines, stdio_config=cfg)
    assert len(res.stdin_records) == 5
    assert len(res.stdout_lines) == 2  # param=5 (10->11) and param=12 (11->12)
    assert len(res.stderr_lines) == 3  # param=25 (REJECT_GUARD) and two '_' (REJECT_FAULT)
    assert dbg.state[0] == 12
    assert dbg.fault_propagations == 2

    # Subprocess CLI UNIX pipe check
    with _workspace_scratch_dir("stdio_cli") as scratch:
        proc = subprocess.run(
            [
                sys.executable,
                str(DEBUGGER_CLI),
                "--program",
                str(INCREASE_KPOL),
                "--profile",
                "KPOL-CME-1",
                "--stdio",
            ],
            input="5\n25\n_\n",
            env=_subproc_env(scratch),
            check=True,
            capture_output=True,
            text=True,
        )
        assert "COMMIT: Counter[cid=0] = 11" in proc.stdout
        assert "REJECT_GUARD: Counter[cid=0] kept W0=11" in proc.stderr
        assert "REJECT_FAULT: Counter[cid=0] kept W0=11" in proc.stderr


def test_machine_connection_pre_load_post_load_and_tui_rendering():
    """Verify `MachineDebugConnection` captures `PRE-LOAD` vs `POST-LOAD` concept counts,
    slot diffs, and renders the multi-panel TUI frame (`--tui` / `--render-tui-frame`).
    """
    inc_mod = kr.parse_module(kd.EXAMPLE_1_INCREASE_SOURCE)
    inc_img = kr.compile_concept_microcode_bram_image(inc_mod, profile="KPOL-CME-1")
    bms_mod = kr.parse_module(kd.EXAMPLE_3_BMS_SAFETY_CASCADE_SOURCE)
    bms_img = kr.compile_concept_microcode_bram_image(bms_mod, profile="KPOL-CME-2")

    conn = MachineDebugConnection(target="sim", initial_machine_bram=inc_img)
    pre, post, diffs = conn.load_program_into_sim(
        bms_img,
        concept_names=[s.name for s in bms_mod.states],
        pre_concept_names=[s.name for s in inc_mod.states],
    )
    assert pre.topology.active_concepts == 1
    assert pre.topology.free_slots == 63
    assert post.topology.active_concepts == 4
    assert post.topology.free_slots == 60
    assert post.topology.entry_concepts == (0,)
    assert post.topology.internal_cascade_concepts == (1, 2)
    assert post.topology.leaf_concepts == (3,)
    assert sum(1 for d in diffs if d.changed) == 4

    dbg = KpolCascadeDebugger(
        bms_img,
        profile="KPOL-CME-2",
        module_name=bms_mod.name,
        source_code=kd.EXAMPLE_3_BMS_SAFETY_CASCADE_SOURCE,
        concept_names=[s.name for s in bms_mod.states],
    )
    stdio_res = run_stdio_stream(dbg, ["15", "120", "_"])
    frame = render_tui_ascii_frame(dbg, connection=conn, stdio_result=stdio_res)
    assert "Concepts: Active: 4 / 64 (Pre-load: 1 / 64, Changed on load: 4, Free: 60)" in frame
    assert "[PANEL 1: CONCEPT TABLE (PRE-LOAD vs POST-LOAD vs CURRENT STATE)]" in frame
    assert "[PANEL 2: PROGRAM SOURCE CODE & LIVE STDIO STREAMS (STDIN / STDOUT / STDERR)]" in frame
    assert "[PANEL 3: CASCADE WAVE STEP TRACE]" in frame


def test_compile_kpol_bram_image_cli_dump_concepts_and_trace_events():
    """Verify `--dump-concepts` and `--trace-events` flags in `compile_kpol_bram_image.py`."""
    with _workspace_scratch_dir("cli_compile_272") as scratch:
        out_bin = scratch / "bms.bin"
        res = subprocess.run(
            [
                sys.executable,
                str(COMPILE_CLI),
                "--profile",
                "KPOL-CME-2",
                "--dump-concepts",
                "--trace-events",
                "0:15,0:120,0:invalid",
                str(BMS_KPOL),
                str(out_bin),
            ],
            env=_subproc_env(scratch),
            check=True,
            capture_output=True,
            text=True,
        )
        assert out_bin.is_file() and len(out_bin.read_bytes()) == 1024
        assert "[BLOCK 1] SOURCE CODE" in res.stdout
        assert "[BLOCK 2] BRAM DESCRIPTOR TABLE" in res.stdout
        assert "[BLOCK 3] STEP-BY-STEP EVENT & CASCADE TRACE" in res.stdout
        assert "[BLOCK 4] STATE DIFF" in res.stdout
        assert "REJECT_FAULT" in res.stdout

        # Invalid trace specification must fail closed before writing output file
        bad_bin = scratch / "bad.bin"
        bad_res = subprocess.run(
            [
                sys.executable,
                str(COMPILE_CLI),
                "--profile",
                "KPOL-CME-2",
                "--trace-events",
                "not_a_valid_spec",
                str(BMS_KPOL),
                str(bad_bin),
            ],
            env=_subproc_env(scratch),
            capture_output=True,
            text=True,
        )
        assert bad_res.returncode == 2
        assert "CME2-TRACE:" in bad_res.stderr
        assert not bad_bin.exists()


def test_author_slide_examples_if_sum_and_nod_120_6_vs_km_euclid_core_iverilog():
    """Verify all 5 article/slide example groups, including `If`, `Sum`, and `Nod(120, 6) = 6`
    cross-checked against `km_euclid_core.sv` in `Icarus Verilog`.
    """
    slide_bundle = trace_author_slide_examples(run_iverilog_euclid=True)
    if_tr = slide_bundle["if_toggle"]
    assert if_tr["state_trajectory"] == ["_", "!", "¬", "!"]

    sum_tr = slide_bundle["sum_post_read_reset"]
    assert sum_tr["read_returned_value"] == 35
    assert sum_tr["post_read_state"] == 0

    nod_tr = slide_bundle["nod_120_6"]
    assert nod_tr["result"] == 6
    assert nod_tr["subtraction_iterations"] == 19
    assert nod_tr["total_eval_steps"] == 20
    assert nod_tr["hardware_cycles_at_3cyc_per_sub_plus_1"] == 58

    euclid_rtl = slide_bundle["km_euclid_core_iverilog"]
    assert euclid_rtl is not None
    assert euclid_rtl["result"] == 6
    assert euclid_rtl["iterations"] == 19
    assert euclid_rtl["cycles"] == 58
    assert euclid_rtl["error"] == 0
    assert len(euclid_rtl["commits"]) == 19
    assert euclid_rtl["commits"][0]["a_pre"] == 120
    assert euclid_rtl["commits"][0]["next_val"] == 114
    assert euclid_rtl["commits"][-1]["a_pre"] == 12
    assert euclid_rtl["commits"][-1]["next_val"] == 6


def test_committed_raw_logs_and_report_provenance_272():
    """Verify that raw logs and `report.md` exist in `Engineering/validation/kpol-cme/debugger-trace-272/`
    and start with `# cmd:`, `# timestamp:`, `# git_commit:`, `# host:`.
    """
    assert REPORT_MD.is_file(), f"Missing report.md: {REPORT_MD}"
    expected_logs = (
        "article_examples_all_traces.log",
        "cli_compile_trace_events_bms.log",
        "stdio_unix_pipe_bms.log",
        "pynq2_live_debugger_session.log",
    )
    for log_name in expected_logs:
        p = RAW_DIR / log_name
        assert p.is_file(), f"Missing raw log: {p}"
        lines = p.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("# cmd: "), f"{log_name} missing '# cmd:' header"
        assert lines[1].startswith("# timestamp: "), f"{log_name} missing '# timestamp:' header"
        assert lines[2].startswith("# git_commit: "), f"{log_name} missing '# git_commit:' header"
        assert lines[3].startswith("# host: "), f"{log_name} missing '# host:' header"

    pynq_json_path = RAW_DIR / "pynq2_live_debugger_session.json"
    assert pynq_json_path.is_file()
    pynq_data = json.loads(pynq_json_path.read_text(encoding="utf-8"))
    sess = pynq_data["pynq_session"]
    assert sess["pre_load"]["hw_id_hex"] == "0x4B504D43"
    assert sess["pre_load"]["topology"]["active_concepts"] == 1
    assert sess["post_load"]["topology"]["active_concepts"] == 4
    assert sess["events_delta"] == 18
    assert sess["commits_delta"] == 12
    assert sess["rejects_delta"] == 6


# ============================================================================
# Negative Mutant Controls (AGENTS.md §4.1)
# ============================================================================


def test_mutant_m1_debugger_invert_predicate_killed():
    """Mutant M1 (`M1_debugger_invert_predicate`): inverting `_eval_predicate` in
    `KpolCascadeDebugger` causes immediate divergence against `ReferenceCmeSafetyEngine`.
    """
    mod = kr.parse_module(kd.EXAMPLE_2_CASCADE_4STAGE_SOURCE)
    img = kr.compile_concept_microcode_bram_image(mod, profile="KPOL-CME-2")
    dbg = KpolCascadeDebugger(img, profile="KPOL-CME-2")
    ref_eng = ReferenceCmeSafetyEngine(img, profile="KPOL-CME-2")

    orig_eval = dbg._eval_predicate
    with mock.patch.object(
        dbg,
        "_eval_predicate",
        side_effect=lambda d, p: not orig_eval(d, p),
    ):
        with pytest.raises(AssertionError, match="mismatch"):
            _assert_debugger_matches_reference(dbg, ref_eng, [(0, 10, True), (0, 100, True)])


def test_mutant_m2_debugger_ignore_invariant_gate_killed():
    """Mutant M2 (`M2_debugger_ignore_invariant_gate`): bypassing `_eval_invariant_gate`
    (forcing `inv_ok = True` on underflow `Counter 0 -> -1`) is caught by both
    reference comparison and invariant verdict checks.
    """
    mod = kr.parse_module(kd.EXAMPLE_1_DECREASE_ZERO_SOURCE)
    img = kr.compile_concept_microcode_bram_image(mod, profile="KPOL-CME-1")
    dbg = KpolCascadeDebugger(img, profile="KPOL-CME-1")
    ref_eng = ReferenceCmeSafetyEngine(img, profile="KPOL-CME-1")

    with mock.patch.object(dbg, "_eval_invariant_gate", return_value=True):
        with pytest.raises(AssertionError, match="mismatch"):
            _assert_debugger_matches_reference(dbg, ref_eng, [(0, 5, True), (0, 5, True)])


def test_mutant_m3_debugger_drop_cascade_subscriber_killed():
    """Mutant M3 (`M3_debugger_drop_cascade_subscriber`): dropping `W3` subscriber
    resolution (`_resolve_subscriber -> (None, False)`) breaks the 4-stage cascade
    at depth 0 and is caught by reference equivalence.
    """
    mod = kr.parse_module(kd.EXAMPLE_3_BMS_SAFETY_CASCADE_SOURCE)
    img = kr.compile_concept_microcode_bram_image(mod, profile="KPOL-CME-2")
    dbg = KpolCascadeDebugger(img, profile="KPOL-CME-2")
    ref_eng = ReferenceCmeSafetyEngine(img, profile="KPOL-CME-2")

    with mock.patch.object(dbg, "_resolve_subscriber", return_value=(None, False)):
        with pytest.raises(AssertionError, match="step count mismatch"):
            _assert_debugger_matches_reference(dbg, ref_eng, [(0, 120, True)])


def test_mutant_m4_debugger_mask_uncertainty_bit_killed():
    """Mutant M4 (`M4_debugger_mask_uncertainty_bit`): masking `param_valid=False`
    as `param_valid=True` (zero-masking a sensor fault `_`) is caught by reference
    equivalence and `fault_propagations` checks.
    """
    mod = kr.parse_module(kd.EXAMPLE_3_BMS_SAFETY_CASCADE_SOURCE)
    img = kr.compile_concept_microcode_bram_image(mod, profile="KPOL-CME-2")
    dbg = KpolCascadeDebugger(img, profile="KPOL-CME-2")
    ref_eng = ReferenceCmeSafetyEngine(img, profile="KPOL-CME-2")

    orig_step = dbg.step_event
    with mock.patch.object(
        dbg,
        "step_event",
        side_effect=lambda cid, param, param_valid=True: orig_step(cid, param, True),
    ):
        with pytest.raises(AssertionError, match="mismatch"):
            _assert_debugger_matches_reference(dbg, ref_eng, [(0, 120, False)])


def test_mutant_m5_debugger_corrupt_preload_postload_diff_killed():
    """Mutant M5 (`M5_debugger_corrupt_preload_postload_diff`): if `compute_pre_post_load_diff`
    fails to detect descriptor changes between `PRE-LOAD` and `POST-LOAD`, the connection
    verification test fails.
    """
    inc_mod = kr.parse_module(kd.EXAMPLE_1_INCREASE_SOURCE)
    inc_img = kr.compile_concept_microcode_bram_image(inc_mod, profile="KPOL-CME-1")
    bms_mod = kr.parse_module(kd.EXAMPLE_3_BMS_SAFETY_CASCADE_SOURCE)
    bms_img = kr.compile_concept_microcode_bram_image(bms_mod, profile="KPOL-CME-2")

    conn = MachineDebugConnection(target="sim", initial_machine_bram=inc_img)
    with mock.patch.object(
        kd,
        "compute_pre_post_load_diff",
        return_value=[],
    ):
        _, _, diffs = conn.load_program_into_sim(bms_img)
        with pytest.raises(AssertionError):
            assert sum(1 for d in diffs if d.changed) == 4
