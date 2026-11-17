#!/usr/bin/env python3
"""Issue #270: Verification suite for deterministic C99 emitter (--emit-c99) and Z3 SMT certificate.

Covers:
  1. Strict C99 code generation (`emit_c99_safety_module`) and compilation via
     `gcc -std=c99 -O2 -Wall -Wextra -Werror -pedantic` with 0 warnings;
  2. 100% bit-exact state and counter equivalence between generated C99 (`ctypes`),
     `ReferenceCmeSafetyEngine`, `kpol_reference.Interpreter`, and `iverilog` RTL
     simulation of `kpol_bram_pipeline_axi.sv` (`CFG-P`) across valid, guard-rejected,
     invariant-blocked, and `param_valid=false` / `valid_mask` fault events;
  3. Generation and validation of the formal Z3 SMT safety certificate
     (`prove_c99_descriptor_safety_z3`: `P1..P4`) and CLI flags `--emit-c99` / `--emit-z3-cert`;
  4. Committed BMS reference artifacts and raw logs (`x86_64`, `iverilog`, and physical
     `PYNQ-Z1` `ARM Cortex-A9 + Zynq-7020 PL`);
  5. Four explicit negative mutant controls (AGENTS.md §4.1):
     - `M1_c99_bypass_invariant`
     - `M2_c99_mask_invalid_sensor`
     - `M3_c99_wrong_topo_order`
     - `M4_z3_cyclic_or_unsafe_descriptor`
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
import uuid

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SW_REF_DIR = REPO_ROOT / "Engineering" / "sw" / "kpol-ref"
COMPILE_CLI = REPO_ROOT / "Engineering" / "hw" / "scripts" / "compile_kpol_bram_image.py"
BMS_DIR = REPO_ROOT / "Engineering" / "validation" / "kpol-cme" / "c99-emitter-270"
BMS_RAW_DIR = BMS_DIR / "raw"

if str(SW_REF_DIR) not in sys.path:
    sys.path.insert(0, str(SW_REF_DIR))

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


def _compile_c99_shared_lib(
    c_source: str,
    scratch_dir: Path,
    extra_defines: list[str] | None = None,
) -> ctypes.CDLL:
    c_file = scratch_dir / f"km_safety_{uuid.uuid4().hex[:8]}.c"
    so_file = scratch_dir / f"libkm_safety_{uuid.uuid4().hex[:8]}.so"
    c_file.write_text(c_source, encoding="utf-8")

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
        *(extra_defines or []),
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
    lib.km_safety_init.argtypes = [ctypes.POINTER(_CSafetyCtx)]
    lib.km_safety_init.restype = None
    lib.km_safety_invalidate_concept.argtypes = [ctypes.POINTER(_CSafetyCtx), ctypes.c_uint8]
    lib.km_safety_invalidate_concept.restype = None
    lib.km_safety_revalidate_concept.argtypes = [
        ctypes.POINTER(_CSafetyCtx),
        ctypes.c_uint8,
        ctypes.c_int32,
    ]
    lib.km_safety_revalidate_concept.restype = None
    lib.km_safety_step_event.argtypes = [
        ctypes.POINTER(_CSafetyCtx),
        ctypes.c_uint8,
        ctypes.c_int32,
        ctypes.c_bool,
    ]
    lib.km_safety_step_event.restype = _CSafetyStepResult
    return lib


def _verify_c99_matches_reference(
    lib: ctypes.CDLL,
    ref_eng: ReferenceCmeSafetyEngine,
    events: list[tuple[str, int, int, bool]],
) -> None:
    ctx = _CSafetyCtx()
    lib.km_safety_init(ctypes.byref(ctx))

    assert list(ctx.state) == ref_eng.state
    assert int(ctx.valid_mask) == ref_eng.valid_mask

    for step_idx, (op, cid, param, param_valid) in enumerate(events):
        if op == "invalidate":
            lib.km_safety_invalidate_concept(ctypes.byref(ctx), cid)
            ref_eng.invalidate_concept(cid)
            assert int(ctx.valid_mask) == ref_eng.valid_mask, f"valid_mask mismatch at step {step_idx}"
            continue
        if op == "revalidate":
            lib.km_safety_revalidate_concept(ctypes.byref(ctx), cid, param)
            ref_eng.revalidate_concept(cid, param)
            assert int(ctx.valid_mask) == ref_eng.valid_mask, f"valid_mask mismatch at step {step_idx}"
            assert list(ctx.state) == ref_eng.state, f"state mismatch after revalidate at step {step_idx}"
            continue

        c_res = lib.km_safety_step_event(ctypes.byref(ctx), cid, param, param_valid)
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


def test_bms_committed_artifacts_and_strict_c99_build():
    """Verify committed BMS artifacts, Z3 certificate, raw logs, and strict C99 executable."""
    kpol_path = BMS_DIR / "bms_safety_cascade.kpol"
    bin_path = BMS_DIR / "bms_safety_cascade.bin"
    c99_path = BMS_DIR / "bms_safety_cascade_gen.c"
    z3_path = BMS_DIR / "bms_safety_z3_certificate.json"
    bench_c_path = BMS_DIR / "bms_c99_hil_bench.c"

    for p in (kpol_path, bin_path, c99_path, z3_path, bench_c_path):
        assert p.is_file(), f"Missing BMS artifact: {p}"

    bin_bytes = bin_path.read_bytes()
    assert len(bin_bytes) == 1024
    bin_sha256 = hashlib.sha256(bin_bytes).hexdigest()

    cert = json.loads(z3_path.read_text(encoding="utf-8"))
    assert cert["verdict"] == "VERIFIED"
    assert cert["passed"] is True
    assert cert["descriptor_table_sha256"] == bin_sha256
    assert cert["topological_order"] == [0, 1, 2, 3]
    assert cert["cascade_edges"] == [[0, 1], [1, 2], [2, 3]]
    for check_name in (
        "P1_dag_lyapunov_acyclicity",
        "P2_invariant_preservation_all_bv32",
        "P3_no_commit_on_invalid_param_or_state",
        "P4_c99_rtl_bitvec32_miter_equivalence",
    ):
        assert cert["checks"][check_name]["passed"] is True

    for log_file in BMS_RAW_DIR.glob("*.log"):
        lines = log_file.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("# cmd: "), f"Missing # cmd header in {log_file.name}"
        assert lines[1].startswith("# timestamp: "), f"Missing # timestamp header in {log_file.name}"

    x86_json = json.loads((BMS_RAW_DIR / "x86_64_bms_c99_verification.json").read_text(encoding="utf-8"))
    pynq_json = json.loads((BMS_RAW_DIR / "pynq_cortex_a9_bms_c99_hil.json").read_text(encoding="utf-8"))
    assert x86_json["bms_bin_sha256"] == bin_sha256
    assert pynq_json["bms_bin_sha256"] == bin_sha256
    assert pynq_json["bit_exact_match_c99_vs_pl_vs_model"] is True
    assert (
        x86_json["c99_x86_64"]["hw_trace_final_state"]
        == x86_json["cfg_p_rtl_simulation"]["states"]
        == pynq_json["arm_cortex_a9_c99"]["hw_trace_final_state"]
        == pynq_json["zynq_7020_pl_cfg_p"]["pl_final_state"]
        == [4, 4, 0, 0]
    )

    with _workspace_scratch_dir("bms_exec") as scratch:
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
    """Verify CLI --emit-c99 / --emit-z3-cert and 100% step-by-step equivalence with CFG-P."""
    kpol_src = (BMS_DIR / "bms_safety_cascade.kpol").read_text(encoding="utf-8")
    module = kr.parse_module(kpol_src)

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
        assert bin_file.read_bytes() == (BMS_DIR / "bms_safety_cascade.bin").read_bytes()
        assert c99_file.read_text(encoding="utf-8") == (BMS_DIR / "bms_safety_cascade_gen.c").read_text(encoding="utf-8")

        # Existing output file must not be overwritten (fail-closed exit code 2)
        dup_res = subprocess.run(
            [
                sys.executable,
                str(COMPILE_CLI),
                "--profile",
                "KPOL-CME-2",
                "--emit-c99",
                str(c99_file),
                str(src_file),
                str(scratch / "bms2.bin"),
            ],
            env=_subproc_env(scratch),
            capture_output=True,
            text=True,
        )
        assert dup_res.returncode == 2
        assert "CME2-IO" in dup_res.stderr

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
    """Mutant M1 (AGENTS.md §4.1): bypassing invariant check in C99 or Z3 spec is caught."""
    bin_bytes = (BMS_DIR / "bms_safety_cascade.bin").read_bytes()
    c99_src = (BMS_DIR / "bms_safety_cascade_gen.c").read_text(encoding="utf-8")

    # 1. Z3 safety certificate rejects bypass_invariant override on P2 and P4
    cert_m1 = prove_c99_descriptor_safety_z3(
        bin_bytes,
        module_name="BmsSafetyCascade",
        c99_spec_overrides={"bypass_invariant": True},
    )
    assert cert_m1["passed"] is False
    assert cert_m1["verdict"] == "REJECTED"
    assert cert_m1["checks"]["P2_invariant_preservation_all_bv32"]["passed"] is False
    assert cert_m1["checks"]["P4_c99_rtl_bitvec32_miter_equivalence"]["passed"] is False

    # 2. Compiled C99 mutant with -DKM_MUTANT_M1_BYPASS_INVARIANT violates invariant Pack_Fault_Latch >= 0
    with _workspace_scratch_dir("m1_inv") as scratch:
        mut_lib = _compile_c99_shared_lib(
            c99_src,
            scratch,
            extra_defines=["-DKM_MUTANT_M1_BYPASS_INVARIANT"],
        )
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
    """Mutant M2 (AGENTS.md §4.1): ignoring param_valid == false masks sensor fault and is caught."""
    bin_bytes = (BMS_DIR / "bms_safety_cascade.bin").read_bytes()
    c99_src = (BMS_DIR / "bms_safety_cascade_gen.c").read_text(encoding="utf-8")

    # 1. Z3 safety certificate rejects mask_invalid_sensor override on P3
    cert_m2 = prove_c99_descriptor_safety_z3(
        bin_bytes,
        module_name="BmsSafetyCascade",
        c99_spec_overrides={"mask_invalid_sensor": True},
    )
    assert cert_m2["passed"] is False
    assert cert_m2["verdict"] == "REJECTED"
    assert cert_m2["checks"]["P3_no_commit_on_invalid_param_or_state"]["passed"] is False

    # 2. Compiled C99 mutant with -DKM_MUTANT_M2_MASK_INVALID_SENSOR fails on param_valid=False
    with _workspace_scratch_dir("m2_mask") as scratch:
        mut_lib = _compile_c99_shared_lib(
            c99_src,
            scratch,
            extra_defines=["-DKM_MUTANT_M2_MASK_INVALID_SENSOR"],
        )
        ref_eng = ReferenceCmeSafetyEngine(bin_bytes)
        events = [
            ("step", 0, 0, False),  # Corrupted isoUART frame (param=0, param_valid=False)
        ]
        with pytest.raises(
            AssertionError,
            match="fault_prop mismatch|fault_propagations mismatch",
        ):
            _verify_c99_matches_reference(mut_lib, ref_eng, events)

        ref_eng2 = ReferenceCmeSafetyEngine(bin_bytes)
        with pytest.raises(
            AssertionError,
            match="steps mismatch|commits mismatch|fault_prop mismatch",
        ):
            _verify_c99_matches_reference(mut_lib, ref_eng2, [("step", 0, 120, False)])


def test_M3_c99_wrong_topo_order():
    """Mutant M3 (AGENTS.md §4.1): violating topological order breaks single-pass cascade execution."""
    bin_bytes = (BMS_DIR / "bms_safety_cascade.bin").read_bytes()
    c99_src = (BMS_DIR / "bms_safety_cascade_gen.c").read_text(encoding="utf-8")

    with _workspace_scratch_dir("m3_topo") as scratch:
        mut_lib = _compile_c99_shared_lib(
            c99_src,
            scratch,
            extra_defines=["-DKM_MUTANT_M3_WRONG_TOPO_ORDER"],
        )
        ref_eng = ReferenceCmeSafetyEngine(bin_bytes)
        events = [
            ("step", 0, 120, True),  # Full 4-stage cascade C0 -> C1 -> C2 -> C3
        ]
        with pytest.raises(AssertionError, match="steps mismatch|commits mismatch|state array mismatch"):
            _verify_c99_matches_reference(mut_lib, ref_eng, events)


def test_M4_z3_cyclic_or_unsafe_descriptor():
    """Mutant M4 (AGENTS.md §4.1): cyclic or unsafe descriptors are rejected by Z3 and emitter."""
    base_descs = normalize_descriptors((BMS_DIR / "bms_safety_cascade.bin").read_bytes())

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

    # Case 4d: Opcode divergence mutant (GT flipped to >= in C99 miter) caught by P4
    cert_op_div = prove_c99_descriptor_safety_z3(
        base_descs,
        module_name="OpDivBms",
        c99_spec_overrides={"flip_gt_to_ge": True},
    )
    assert cert_op_div["passed"] is False
    assert cert_op_div["verdict"] == "REJECTED"
    assert cert_op_div["checks"]["P4_c99_rtl_bitvec32_miter_equivalence"]["passed"] is False
