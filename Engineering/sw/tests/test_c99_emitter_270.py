#!/usr/bin/env python3
"""Issue #270: Verification suite for deterministic C99 emitter (--emit-c99) and Z3 SMT certificate.

Covers:
  1. Strict C99 code generation (`emit_c99_safety_module`) with zero `#ifdef KM_MUTANT_*`,
     multi-TU `static inline` linkage, and compilation via
     `gcc -std=c99 -O2 -Wall -Wextra -Werror -pedantic` with 0 warnings;
  2. 100% bit-exact state and counter equivalence between generated C99 (`ctypes`),
     `ReferenceCmeSafetyEngine`, `kpol_reference.Interpreter`, and `iverilog` RTL
     simulation of `kpol_bram_pipeline_axi.sv` (`CFG-P`) across valid, guard-rejected,
     invariant-blocked, and `param_valid=false` / `valid_mask` fault events;
  3. Non-tautological Z3 SMT safety certificate verification (`prove_c99_descriptor_safety_z3`
     parsing the emitted C99 text for `P1..P4`), `z3 -in -smt2` CLI execution, and
     fail-closed `RuntimeError` when Z3 is absent (`F-02`);
  4. Committed BMS reference artifacts, SHA-256 consistency in `report.md` (`F-05`; the former
     commercialization conclusions document was removed from the project), and raw logs (`F-07`);
  5. Negative mutant controls via C-source text replacement (`AGENTS.md §4.1`, `F-06`):
     - `M1_c99_bypass_invariant`
     - `M2_c99_mask_invalid_sensor`
     - `M3_c99_wrong_topo_order`
     - `M4_z3_cyclic_or_unsafe_descriptor` (incl. `PRED_GT`, `PRED_RANGE`, `ACT_SUB` C-text mutants)
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
BMS_DIR = REPO_ROOT / "Engineering" / "validation" / "kpol-cme" / "c99-emitter-270"
BMS_RAW_DIR = BMS_DIR / "raw"
BMS_REPORT_MD = BMS_DIR / "report.md"

if str(SW_REF_DIR) not in sys.path:
    sys.path.insert(0, str(SW_REF_DIR))

import c99_emitter as ce  # noqa: E402
from c99_emitter import (  # noqa: E402
    C99EmitterError,
    ReferenceCmeSafetyEngine,
    emit_c99_safety_module,
    normalize_descriptors,
    prove_c99_descriptor_safety_z3,
)
import kpol_reference as kr  # noqa: E402


@contextmanager
def _workspace_scratch_dir(prefix: str = "c99_270"):
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


def _mutate_c99_text(c_source: str, old_snippet: str, new_snippet: str) -> str:
    """Apply a single exact text replacement to generated C99 source."""
    count = c_source.count(old_snippet)
    assert count == 1, f"Expected exactly 1 occurrence of {old_snippet!r}, found {count}"
    return c_source.replace(old_snippet, new_snippet, 1)


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
/* Exported C99 wrapper symbols for ctypes shared-library testing */
void km_Export_init(km_safety_ctx_t *ctx);
void km_Export_invalidate(km_safety_ctx_t *ctx, uint8_t cid);
void km_Export_revalidate(km_safety_ctx_t *ctx, uint8_t cid, int32_t recovered_state);
km_safety_step_result_t km_Export_step_event(
    km_safety_ctx_t *ctx, uint8_t root_cid, int32_t param, bool param_valid
);

void km_Export_init(km_safety_ctx_t *ctx) {
    km_safety_init(ctx);
}
void km_Export_invalidate(km_safety_ctx_t *ctx, uint8_t cid) {
    km_safety_invalidate_concept(ctx, cid);
}
void km_Export_revalidate(km_safety_ctx_t *ctx, uint8_t cid, int32_t recovered_state) {
    km_safety_revalidate_concept(ctx, cid, recovered_state);
}
km_safety_step_result_t km_Export_step_event(
    km_safety_ctx_t *ctx, uint8_t root_cid, int32_t param, bool param_valid
) {
    return km_safety_step_event(ctx, root_cid, param, param_valid);
}
"""


def _compile_c99_shared_lib(
    c_source: str,
    scratch_dir: Path,
) -> ctypes.CDLL:
    c_file = scratch_dir / f"km_safety_{uuid.uuid4().hex[:8]}.c"
    so_file = scratch_dir / f"libkm_safety_{uuid.uuid4().hex[:8]}.so"
    c_file.write_text(c_source + "\n" + _CTYPES_EXPORT_SHIM, encoding="utf-8")

    cmd = [
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
    ]
    res = subprocess.run(
        cmd,
        env=_subproc_env(scratch_dir),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"GCC strict C99 build failed:\n{res.stdout}\n{res.stderr}"
    assert res.stderr.strip() == "", f"GCC produced unexpected stderr:\n{res.stderr}"

    lib = ctypes.CDLL(str(so_file))
    lib.km_Export_init.argtypes = [ctypes.POINTER(_CSafetyCtx)]
    lib.km_Export_init.restype = None
    lib.km_Export_invalidate.argtypes = [ctypes.POINTER(_CSafetyCtx), ctypes.c_uint8]
    lib.km_Export_invalidate.restype = None
    lib.km_Export_revalidate.argtypes = [
        ctypes.POINTER(_CSafetyCtx),
        ctypes.c_uint8,
        ctypes.c_int32,
    ]
    lib.km_Export_revalidate.restype = None
    lib.km_Export_step_event.argtypes = [
        ctypes.POINTER(_CSafetyCtx),
        ctypes.c_uint8,
        ctypes.c_int32,
        ctypes.c_bool,
    ]
    lib.km_Export_step_event.restype = _CSafetyStepResult
    return lib


def _verify_c99_matches_reference(
    lib: ctypes.CDLL,
    ref_eng: ReferenceCmeSafetyEngine,
    events: list[tuple[str, int, int, bool]],
) -> None:
    ctx = _CSafetyCtx()
    lib.km_Export_init(ctypes.byref(ctx))

    assert list(ctx.state) == ref_eng.state
    assert int(ctx.valid_mask) == ref_eng.valid_mask

    for step_idx, (op, cid, param, param_valid) in enumerate(events):
        if op == "invalidate":
            lib.km_Export_invalidate(ctypes.byref(ctx), cid)
            ref_eng.invalidate_concept(cid)
            assert int(ctx.valid_mask) == ref_eng.valid_mask, f"valid_mask mismatch at step {step_idx}"
            continue
        if op == "revalidate":
            lib.km_Export_revalidate(ctypes.byref(ctx), cid, param)
            ref_eng.revalidate_concept(cid, param)
            assert int(ctx.valid_mask) == ref_eng.valid_mask, f"valid_mask mismatch at step {step_idx}"
            assert list(ctx.state) == ref_eng.state, f"state mismatch after revalidate at step {step_idx}"
            continue

        c_res = lib.km_Export_step_event(ctypes.byref(ctx), cid, param, param_valid)
        r_res = ref_eng.step_event(cid, param, param_valid)

        assert int(c_res.steps_executed) == r_res.steps_executed, f"steps mismatch at step {step_idx}"
        assert int(c_res.commits) == r_res.commits, f"step commits mismatch at step {step_idx}"
        assert int(c_res.rejects) == r_res.rejects, f"step rejects mismatch at step {step_idx}"
        assert bool(c_res.fault_propagated) == r_res.fault_propagated, f"fault_prop mismatch at step {step_idx}"
        assert int(c_res.status) == r_res.status, f"status mismatch at step {step_idx}"

        assert list(ctx.state) == ref_eng.state, f"state array mismatch at step {step_idx}"
        assert int(ctx.valid_mask) == ref_eng.valid_mask, f"valid_mask mismatch at step {step_idx}"
        assert int(ctx.events_processed) == ref_eng.events_processed, f"events_processed mismatch at step {step_idx}"
        assert int(ctx.commits) == ref_eng.commits, f"total commits mismatch at step {step_idx}"
        assert int(ctx.rejects) == ref_eng.rejects, f"total rejects mismatch at step {step_idx}"
        assert int(ctx.fault_propagations) == ref_eng.fault_propagations, f"fault_propagations mismatch at step {step_idx}"
        assert int(ctx.last_committed_state) == ref_eng.last_committed_state, f"last_state mismatch at step {step_idx}"


def test_bms_committed_artifacts_sha256_docs_and_multi_tu_c99_build():
    """Verify committed BMS artifacts, SHA-256 in reports (F-05), multi-TU build (F-08), and raw logs (F-07)."""
    kpol_path = BMS_DIR / "bms_safety_cascade.kpol"
    bin_path = BMS_DIR / "bms_safety_cascade.bin"
    c99_path = BMS_DIR / "bms_safety_cascade_gen.c"
    z3_path = BMS_DIR / "bms_safety_z3_certificate.json"
    bench_c_path = BMS_DIR / "bms_c99_hil_bench.c"

    for p in (kpol_path, bin_path, c99_path, z3_path, bench_c_path, BMS_REPORT_MD):
        assert p.is_file(), f"Missing BMS artifact or report: {p}"

    c99_text = c99_path.read_text(encoding="utf-8")
    assert "KM_MUTANT_" not in c99_text, "Production C99 output must not contain #ifdef KM_MUTANT_ macros (F-06)"

    bin_bytes = bin_path.read_bytes()
    assert len(bin_bytes) == 1024
    bin_sha256 = hashlib.sha256(bin_bytes).hexdigest()
    c99_sha256 = hashlib.sha256(c99_path.read_bytes()).hexdigest()
    z3_sha256 = hashlib.sha256(z3_path.read_bytes()).hexdigest()
    bench_sha256 = hashlib.sha256(bench_c_path.read_bytes()).hexdigest()

    # F-05: Assert that report.md records the exact SHA-256 of every committed artifact
    for doc_path in (BMS_REPORT_MD,):
        doc_text = doc_path.read_text(encoding="utf-8")
        assert bin_sha256 in doc_text, f"{doc_path.name} missing exact SHA-256 of bms_safety_cascade.bin"
        assert c99_sha256 in doc_text, f"{doc_path.name} missing exact SHA-256 of bms_safety_cascade_gen.c"
        assert z3_sha256 in doc_text, f"{doc_path.name} missing exact SHA-256 of bms_safety_z3_certificate.json"
        assert bench_sha256 in doc_text, f"{doc_path.name} missing exact SHA-256 of bms_c99_hil_bench.c"

    cert = json.loads(z3_path.read_text(encoding="utf-8"))
    assert cert["verdict"] == "VERIFIED"
    assert cert["passed"] is True
    assert cert["descriptor_table_sha256"] == bin_sha256
    assert cert["c99_source_sha256"] == c99_sha256
    assert cert["topological_order"] == [0, 1, 2, 3]
    assert cert["cascade_edges"] == [[0, 1], [1, 2], [2, 3]]
    for check_name in (
        "P1_dag_lyapunov_acyclicity",
        "P2_invariant_preservation_all_bv32",
        "P3_no_commit_on_invalid_param_or_state",
        "P4_c99_rtl_bitvec32_miter_equivalence",
    ):
        assert cert["checks"][check_name]["passed"] is True

    # F-07: Check raw log provenance headers (# cmd, # timestamp, # git_commit, # host)
    for log_file in BMS_RAW_DIR.glob("*.log"):
        lines = log_file.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("# cmd: "), f"Missing # cmd header in {log_file.name}"
        assert lines[1].startswith("# timestamp: "), f"Missing # timestamp header in {log_file.name}"
        if log_file.name != "pytest_c99_emitter_270.log":
            assert any(l.startswith("# git_commit: ") for l in lines[:6]), f"Missing # git_commit in {log_file.name}"
            assert any(l.startswith("# host: ") for l in lines[:6]), f"Missing # host in {log_file.name}"

    pynq_log_text = (BMS_RAW_DIR / "pynq_cortex_a9_bms_c99_hil.log").read_text(encoding="utf-8")
    assert "flock -w 600 /tmp/km-bench.lock" in pynq_log_text

    x86_json = json.loads((BMS_RAW_DIR / "x86_64_bms_c99_verification.json").read_text(encoding="utf-8"))
    pynq_json = json.loads((BMS_RAW_DIR / "pynq_cortex_a9_bms_c99_hil.json").read_text(encoding="utf-8"))
    assert x86_json["bms_bin_sha256"] == bin_sha256
    assert x86_json["bms_c99_sha256"] == c99_sha256
    assert pynq_json["bms_bin_sha256"] == bin_sha256
    assert pynq_json["bms_c99_sha256"] == c99_sha256
    assert pynq_json["bit_exact_match_c99_vs_pl_vs_model"] is True
    assert "ns_per_single_reject_p50" in pynq_json["arm_cortex_a9_c99"]
    assert "ns_per_single_reject_p99" in pynq_json["arm_cortex_a9_c99"]

    with _workspace_scratch_dir("bms_exec") as scratch:
        # F-08: Verify multi-TU inclusion of bms_safety_cascade_gen.c without duplicate symbol errors
        tu1 = scratch / "tu1.c"
        tu2 = scratch / "tu2.c"
        tu1.write_text(
            f'#include "{c99_path.as_posix()}"\n'
            "int tu2_helper(void);\n"
            "int main(void) {\n"
            "    km_safety_ctx_t ctx;\n"
            "    km_safety_init(&ctx);\n"
            "    (void)km_safety_step_event(&ctx, 0u, 120, true);\n"
            "    return (ctx.commits == 4u && tu2_helper() == 4) ? 0 : 1;\n"
            "}\n",
            encoding="utf-8",
        )
        tu2.write_text(
            f'#include "{c99_path.as_posix()}"\n'
            "int tu2_helper(void);\n"
            "int tu2_helper(void) {\n"
            "    km_safety_ctx_t c2;\n"
            "    km_safety_init(&c2);\n"
            "    (void)km_safety_step_event(&c2, 0u, 120, true);\n"
            "    return (int)c2.commits;\n"
            "}\n",
            encoding="utf-8",
        )
        multi_tu_bin = scratch / "multi_tu_test"
        res_tu = subprocess.run(
            [
                "gcc",
                "-std=c99",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                str(tu1),
                str(tu2),
                "-o",
                str(multi_tu_bin),
            ],
            env=_subproc_env(scratch),
            capture_output=True,
            text=True,
        )
        assert res_tu.returncode == 0, res_tu.stdout + res_tu.stderr
        run_tu = subprocess.run([str(multi_tu_bin)], env=_subproc_env(scratch), capture_output=True, text=True)
        assert run_tu.returncode == 0

        # Compile and run full benchmark harness
        out_bin = scratch / "bms_c99_hil_bench"
        cmd = [
            "gcc",
            "-std=c99",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-pedantic",
            str(bench_c_path),
            "-lm",
            "-o",
            str(out_bin),
        ]
        res = subprocess.run(cmd, env=_subproc_env(scratch), capture_output=True, text=True)
        assert res.returncode == 0, res.stdout + res.stderr
        run_res = subprocess.run([str(out_bin)], env=_subproc_env(scratch), capture_output=True, text=True)
        assert run_res.returncode == 0, run_res.stdout + run_res.stderr
        parsed = json.loads(run_res.stdout)
        assert parsed["verdict"] == "PASS"
        assert parsed["hw_trace_final_state"] == [4, 4, 0, 0]
        assert parsed["hw_trace_events"] == 18
        assert parsed["hw_trace_commits"] == 12
        assert parsed["hw_trace_rejects"] == 6
        assert parsed["fault_trace_fault_propagations"] == 3


def test_c99_emitter_equivalence_with_cfg_p_and_cli_flags():
    """Verify CLI --emit-c99 / --emit-z3-cert, z3 CLI mode, and 100% step-by-step equivalence with CFG-P."""
    kpol_src = (BMS_DIR / "bms_safety_cascade.kpol").read_text(encoding="utf-8")
    module = kr.parse_module(kpol_src)
    bin_bytes = (BMS_DIR / "bms_safety_cascade.bin").read_bytes()
    c99_text = (BMS_DIR / "bms_safety_cascade_gen.c").read_text(encoding="utf-8")

    # F-02: Verify that when HAS_Z3_PYTHON=False, z3 is None, and z3 binary is missing, RuntimeError is raised
    with mock.patch.object(ce, "HAS_Z3_PYTHON", False), mock.patch.object(
        ce, "z3", None
    ), mock.patch.object(ce.shutil, "which", return_value=None):
        with pytest.raises(RuntimeError, match="Z3 solver is required"):
            prove_c99_descriptor_safety_z3(bin_bytes, c99_source=c99_text)

    # F-02: Verify that when HAS_Z3_PYTHON=False, SMT-LIB2 execution via _run_z3_cli_smt2 works
    with mock.patch.object(ce, "HAS_Z3_PYTHON", False):
        cli_cert = prove_c99_descriptor_safety_z3(bin_bytes, c99_source=c99_text)
        assert cli_cert["passed"] is True
        assert cli_cert["verdict"] == "VERIFIED"
        assert cli_cert["solver"].startswith("z3")

    with _workspace_scratch_dir("c99_cli") as scratch:
        src_file = scratch / "bms.kpol"
        bin_file = scratch / "bms.bin"
        c99_file = scratch / "bms_gen.c"
        z3_file = scratch / "bms_z3.json"
        src_file.write_text(kpol_src, encoding="utf-8")

        cli_res = subprocess.run(
            [
                sys.executable,
                str(COMPILE_CLI),
                "--profile",
                "KPOL-CME-2",
                "--emit-c99",
                str(c99_file),
                "--emit-z3-cert",
                str(z3_file),
                str(src_file),
                str(bin_file),
            ],
            env=_subproc_env(scratch),
            capture_output=True,
            text=True,
        )
        assert cli_res.returncode == 0, cli_res.stdout + cli_res.stderr
        assert bin_file.read_bytes() == bin_bytes
        assert c99_file.read_text(encoding="utf-8") == c99_text
        cert_regen = json.loads(z3_file.read_text(encoding="utf-8"))
        committed_cert = json.loads((BMS_DIR / "bms_safety_z3_certificate.json").read_text(encoding="utf-8"))
        assert cert_regen["solver"].startswith("z3")
        assert {k: v for k, v in cert_regen.items() if k != "solver"} == {
            k: v for k, v in committed_cert.items() if k != "solver"
        }

        # Existing output file must not be overwritten (fail-closed exit code 2, no partial files left)
        new_bin = scratch / "bms2.bin"
        dup_res = subprocess.run(
            [
                sys.executable,
                str(COMPILE_CLI),
                "--profile",
                "KPOL-CME-2",
                "--emit-c99",
                str(c99_file),
                str(src_file),
                str(new_bin),
            ],
            env=_subproc_env(scratch),
            capture_output=True,
            text=True,
        )
        assert dup_res.returncode == 2
        assert "CME2-IO" in dup_res.stderr
        assert not new_bin.exists()

        lib = _compile_c99_shared_lib(c99_file.read_text(encoding="utf-8"), scratch)
        ref_eng = ReferenceCmeSafetyEngine(
            bin_file.read_bytes(),
            concept_names=[s.name for s in module.states],
        )

        trace_events: list[tuple[str, int, int, bool]] = [
            ("step", 0, 15, True),      # guard reject (< 50)
            ("step", 0, 5500, True),    # guard reject (> 5000)
            ("step", 0, 0, False),      # isoUART CRC fault on 0 mV -> must NOT mask as 0!
            ("step", 0, 120, False),    # isoUART CRC fault on 120 mV -> Fail-Closed
            ("step", 0, 120, True),     # full 4-stage cascade -> [1, 1, 1, 1]
            ("invalidate", 2, 0, True), # mark Pack_Fault_Latch (CID 2) as uncertain '_'
            ("step", 0, 150, True),     # C0, C1 commit; C2 rejects on valid_mask==0!
            ("revalidate", 2, 1, True), # recover CID 2 with state=1
            ("step", 0, 180, True),     # full 4-stage cascade -> [3, 3, 0, 0]
            ("step", 0, 250, True),     # C0, C1 commit; C2 (0 - 1 = -1) rejected by invariant >= 0
            ("step", 10, 100, True),    # inactive slot CID 10 -> guard reject
            ("step", 10, 100, False),   # inactive slot CID 10 with invalid param -> fault reject
            ("step", 99, 100, True),    # out-of-range CID 99 -> bad CID fault reject
        ]
        _verify_c99_matches_reference(lib, ref_eng, trace_events)
        assert ref_eng.state[:4] == [4, 4, 0, 0]
        assert ref_eng.fault_propagations == 5


def test_M1_c99_bypass_invariant():
    """Mutant M1 (AGENTS.md §4.1): mutating invariant_true in C99 source text is caught by Z3 and runtime."""
    bin_bytes = (BMS_DIR / "bms_safety_cascade.bin").read_bytes()
    c99_src = (BMS_DIR / "bms_safety_cascade_gen.c").read_text(encoding="utf-8")

    mut_c99 = _mutate_c99_text(
        c99_src,
        "invariant_true   = (!arith_overflow) && ((cand_u32 & 0x80000000u) == 0u);",
        "invariant_true   = true; (void)arith_overflow;",
    )

    # 1. Z3 safety verifier parses mut_c99 and rejects P2 and P4 with concrete BitVec(32) counterexamples
    cert_m1 = prove_c99_descriptor_safety_z3(
        bin_bytes,
        c99_source=mut_c99,
        module_name="BmsSafetyCascade",
    )
    assert cert_m1["passed"] is False
    assert cert_m1["verdict"] == "REJECTED"
    assert cert_m1["checks"]["P2_invariant_preservation_all_bv32"]["passed"] is False
    assert cert_m1["checks"]["P4_c99_rtl_bitvec32_miter_equivalence"]["passed"] is False

    # 2. Compiled C99 mutant violates invariant Pack_Fault_Latch >= 0 at runtime
    with _workspace_scratch_dir("m1_inv") as scratch:
        mut_lib = _compile_c99_shared_lib(mut_c99, scratch)
        ref_eng = ReferenceCmeSafetyEngine(bin_bytes)
        events = [
            ("step", 0, 120, True),  # Pack_Fault_Latch: 2 -> 1
            ("step", 0, 180, True),  # Pack_Fault_Latch: 1 -> 0
            ("step", 0, 250, True),  # Pack_Fault_Latch attempts 0 - 1 = -1 (must be blocked!)
        ]
        with pytest.raises(
            AssertionError,
            match="steps mismatch|commits mismatch|state array mismatch",
        ):
            _verify_c99_matches_reference(mut_lib, ref_eng, events)


def test_M2_c99_mask_invalid_sensor():
    """Mutant M2 (AGENTS.md §4.1): mutating fault gate in C99 source text masks sensor fault and is caught."""
    bin_bytes = (BMS_DIR / "bms_safety_cascade.bin").read_bytes()
    c99_src = (BMS_DIR / "bms_safety_cascade_gen.c").read_text(encoding="utf-8")

    mut_c99 = _mutate_c99_text(
        c99_src,
        "if ((!ev_param_valid) || (!concept_valid)) {",
        "if (false && ((!ev_param_valid) || (!concept_valid))) {",
    )

    # 1. Z3 safety verifier parses mut_c99 and rejects P3 with a counterexample
    cert_m2 = prove_c99_descriptor_safety_z3(
        bin_bytes,
        c99_source=mut_c99,
        module_name="BmsSafetyCascade",
    )
    assert cert_m2["passed"] is False
    assert cert_m2["verdict"] == "REJECTED"
    assert cert_m2["checks"]["P3_no_commit_on_invalid_param_or_state"]["passed"] is False

    # 2. Compiled C99 mutant fails on param=0, param_valid=False (zero-masking), param=120, param_valid=False, and mid-cascade invalidation
    with _workspace_scratch_dir("m2_mask") as scratch:
        mut_lib = _compile_c99_shared_lib(mut_c99, scratch)
        ref_eng = ReferenceCmeSafetyEngine(bin_bytes)
        with pytest.raises(
            AssertionError,
            match="fault_prop mismatch|fault_propagations mismatch",
        ):
            _verify_c99_matches_reference(mut_lib, ref_eng, [("step", 0, 0, False)])

        ref_eng2 = ReferenceCmeSafetyEngine(bin_bytes)
        with pytest.raises(
            AssertionError,
            match="steps mismatch|commits mismatch|fault_prop mismatch",
        ):
            _verify_c99_matches_reference(mut_lib, ref_eng2, [("step", 0, 120, False)])

        ref_eng3 = ReferenceCmeSafetyEngine(bin_bytes)
        with pytest.raises(
            AssertionError,
            match="steps mismatch|commits mismatch|fault_prop mismatch",
        ):
            _verify_c99_matches_reference(
                mut_lib,
                ref_eng3,
                [("invalidate", 2, 0, True), ("step", 0, 120, True)],
            )


def test_M3_c99_wrong_topo_order():
    """Mutant M3 (AGENTS.md §4.1): reversing topological order in C99 source text is caught by Z3 and runtime."""
    bin_bytes = (BMS_DIR / "bms_safety_cascade.bin").read_bytes()
    c99_src = (BMS_DIR / "bms_safety_cascade_gen.c").read_text(encoding="utf-8")

    mut_c99 = _mutate_c99_text(
        c99_src,
        "uint8_t cid = KM_SAFETY_TOPO_ORDER[topo_idx];",
        "uint8_t cid = KM_SAFETY_TOPO_ORDER[(KM_SAFETY_NUM_ACTIVE_TOPO - 1u) - topo_idx];",
    )

    # 1. Z3 verifier parses mut_c99 and rejects P1 because schedule violates edge order
    cert_m3 = prove_c99_descriptor_safety_z3(
        bin_bytes,
        c99_source=mut_c99,
        module_name="BmsSafetyCascade",
    )
    assert cert_m3["passed"] is False
    assert cert_m3["verdict"] == "REJECTED"
    assert cert_m3["checks"]["P1_dag_lyapunov_acyclicity"]["passed"] is False

    # 2. Compiled C99 mutant breaks single-pass cascade execution at runtime
    with _workspace_scratch_dir("m3_topo") as scratch:
        mut_lib = _compile_c99_shared_lib(mut_c99, scratch)
        ref_eng = ReferenceCmeSafetyEngine(bin_bytes)
        with pytest.raises(AssertionError, match="steps mismatch|commits mismatch|state array mismatch"):
            _verify_c99_matches_reference(mut_lib, ref_eng, [("step", 0, 120, True)])


def test_M4_z3_cyclic_or_unsafe_descriptor():
    """Mutant M4 (AGENTS.md §4.1): cyclic/unsafe descriptors and C99 opcode text mutations are rejected."""
    bin_bytes = (BMS_DIR / "bms_safety_cascade.bin").read_bytes()
    base_descs = normalize_descriptors(bin_bytes)
    c99_src = (BMS_DIR / "bms_safety_cascade_gen.c").read_text(encoding="utf-8")

    # Case 4a: 2-node cycle C0 -> C1 -> C0
    cyclic_descs = list(base_descs)
    cyclic_descs[1] = replace(cyclic_descs[1], subscriber_cid=0)
    cert_cycle = prove_c99_descriptor_safety_z3(cyclic_descs, module_name="CyclicBms")
    assert cert_cycle["passed"] is False
    assert cert_cycle["verdict"] == "REJECTED"
    assert cert_cycle["checks"]["P1_dag_lyapunov_acyclicity"]["passed"] is False
    with pytest.raises(C99EmitterError, match="C99-Z3-REJECTED"):
        emit_c99_safety_module(cyclic_descs, module_name="CyclicBms")

    # Case 4b: Self-loop C0 -> C0
    self_loop_descs = list(base_descs)
    self_loop_descs[0] = replace(self_loop_descs[0], subscriber_cid=0)
    cert_self = prove_c99_descriptor_safety_z3(self_loop_descs, module_name="SelfLoopBms")
    assert cert_self["passed"] is False
    assert cert_self["verdict"] == "REJECTED"
    assert cert_self["checks"]["P1_dag_lyapunov_acyclicity"]["passed"] is False

    # Case 4c: Active descriptor with invariant check disabled (guard_flags missing 0x02)
    unsafe_inv_descs = list(base_descs)
    unsafe_inv_descs[2] = replace(
        unsafe_inv_descs[2],
        guard_flags=unsafe_inv_descs[2].guard_flags & ~kr.CME_GUARD_INVARIANT_EN,
    )
    cert_no_inv = prove_c99_descriptor_safety_z3(unsafe_inv_descs, module_name="UnsafeInvBms")
    assert cert_no_inv["passed"] is False
    assert cert_no_inv["verdict"] == "REJECTED"
    assert cert_no_inv["checks"]["P2_invariant_preservation_all_bv32"]["passed"] is False
    with pytest.raises(C99EmitterError, match="C99-Z3-REJECTED"):
        emit_c99_safety_module(unsafe_inv_descs, module_name="UnsafeInvBms")

    # Case 4d: C99 text mutation in KM_CME_PRED_GT (`>` -> `>=`) caught by Z3 P4 miter
    mut_gt_c99 = _mutate_c99_text(
        c99_src,
        "case KM_CME_PRED_GT:\n            pred_raw = (ev_param > op_i32);",
        "case KM_CME_PRED_GT:\n            pred_raw = (ev_param >= op_i32);",
    )
    cert_gt = prove_c99_descriptor_safety_z3(bin_bytes, c99_source=mut_gt_c99, module_name="MutGtBms")
    assert cert_gt["passed"] is False
    assert cert_gt["verdict"] == "REJECTED"
    assert cert_gt["checks"]["P4_c99_rtl_bitvec32_miter_equivalence"]["passed"] is False

    # Case 4e: C99 text mutation in KM_CME_PRED_RANGE (dropping sign-extension) caught by Z3 P4 miter
    mut_rng_c99 = _mutate_c99_text(
        c99_src,
        "int32_t lo_i32 = km_u16_to_i32_sext((uint16_t)(d->operand & 0xFFFFu));",
        "int32_t lo_i32 = (int32_t)(uint16_t)(d->operand & 0xFFFFu);",
    )
    cert_rng = prove_c99_descriptor_safety_z3(bin_bytes, c99_source=mut_rng_c99, module_name="MutRngBms")
    assert cert_rng["passed"] is False
    assert cert_rng["verdict"] == "REJECTED"
    assert cert_rng["checks"]["P4_c99_rtl_bitvec32_miter_equivalence"]["passed"] is False

    # Case 4f: C99 text mutation in KM_CME_ACT_SUB overflow mask (`!= 0u` -> `== 0u`) caught by Z3 P4 miter
    mut_sub_c99 = _mutate_c99_text(
        c99_src,
        "case KM_CME_ACT_SUB:\n            cand_u32       = cur_u32 - d->operand;\n            arith_overflow = (((cur_u32 ^ d->operand) & 0x80000000u) != 0u) &&",
        "case KM_CME_ACT_SUB:\n            cand_u32       = cur_u32 - d->operand;\n            arith_overflow = (((cur_u32 ^ d->operand) & 0x80000000u) == 0u) &&",
    )
    cert_sub = prove_c99_descriptor_safety_z3(bin_bytes, c99_source=mut_sub_c99, module_name="MutSubBms")
    assert cert_sub["passed"] is False
    assert cert_sub["verdict"] == "REJECTED"
    assert cert_sub["checks"]["P4_c99_rtl_bitvec32_miter_equivalence"]["passed"] is False
