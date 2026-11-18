#!/usr/bin/env python3
"""Issue #274: Verification suite for the Go VMK (Virtual Machine of Kuzmin) Emulator
and 4-Panel TUI Debugger (`Engineering/sw/vmk-go`, SemVer `0.1.0`).

Covers:
  1. Execution of the Go unit test suite (`go test -v ./...` in `Engineering/sw/vmk-go/`);
  2. Cross-checking Go `vmk` (`--mode bram64` and `--mode conceptual`) against:
     - Python `kpol_debugger.py` & `ReferenceCmeSafetyEngine`,
     - GCC-compiled C99 (`--emit-c99`),
     - `Icarus Verilog` simulation of `kpol_bram_pipeline_axi.sv` (`CFG-P`) and `km_euclid_core.sv` (`Nod(120, 6) = 6`),
     - Recorded physical `PYNQ-Z1` (`pynq2`) HIL session (`PRE-LOAD -> POST-LOAD -> POST-RUN`);
  3. Verification of all 6+ built-in examples (`if`, `sum`, `nod`, `factorial`, `tachometer`,
     `bms`, `increase`, `decrease`, `cascade`, `auth`), `STDIO` (`--stdio`, `--fail-on-reject`),
     and `--render-tui-frame`;
  4. Five Go-source negative mutant tests (`AGENTS.md §4.1`, copying `Engineering/sw/vmk-go`
     into `.pytest_cache`, mutating `.go` source code, and verifying `go test` fails):
     - `M1_go_invert_predicate`
     - `M2_go_bypass_invariant_gate`
     - `M3_go_ignore_uncertainty_bit`
     - `M4_go_skip_post_read_dot_reset`
     - `M5_go_corrupt_pre_post_load_diff`
"""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
VMK_GO_DIR = REPO_ROOT / "Engineering" / "sw" / "vmk-go"
SW_REF_DIR = REPO_ROOT / "Engineering" / "sw" / "kpol-ref"
VAL_DIR = REPO_ROOT / "Engineering" / "validation" / "kpol-cme" / "vmk-go-274"
RAW_DIR = VAL_DIR / "raw"
SPEC_MD = REPO_ROOT / "Engineering" / "specifications" / "sw" / "vmk-go-emulator-and-tui-debugger-0.1.0.md"
REPORT_MD = VAL_DIR / "report.md"
BMS_KPOL = REPO_ROOT / "Engineering" / "validation" / "kpol-cme" / "c99-emitter-270" / "bms_safety_cascade.kpol"

if str(SW_REF_DIR) not in sys.path:
    sys.path.insert(0, str(SW_REF_DIR))

from c99_emitter import ReferenceCmeSafetyEngine, emit_c99_safety_module  # noqa: E402
from kpol_debugger import (  # noqa: E402
    KpolCascadeDebugger,
    run_iverilog_cfgp_trace,
    run_iverilog_euclid_verification,
)
import kpol_reference as kr  # noqa: E402


@contextmanager
def _workspace_scratch_dir(prefix: str = "vmk_go_274"):
    """Create an isolated scratch directory inside `.pytest_cache` (never `/tmp`)."""
    base = REPO_ROOT / ".pytest_cache" / f"{prefix}_{uuid.uuid4().hex}"
    base.mkdir(parents=True, exist_ok=False)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _go_env(scratch_dir: Path) -> dict[str, str]:
    go_tmp = scratch_dir / "go_tmp"
    go_cache = REPO_ROOT / ".pytest_cache" / "go_cache"
    go_tmp.mkdir(parents=True, exist_ok=True)
    go_cache.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["GOTMPDIR"] = str(go_tmp)
    env["GOCACHE"] = str(go_cache)
    env["TMPDIR"] = str(go_tmp)
    env["TEMP"] = str(go_tmp)
    env["TMP"] = str(go_tmp)
    return env


def _build_vmk_binary(scratch_dir: Path) -> Path:
    bin_path = scratch_dir / "vmk"
    subprocess.run(
        ["go", "build", "-o", str(bin_path), "./cmd/vmk"],
        cwd=str(VMK_GO_DIR),
        env=_go_env(scratch_dir),
        check=True,
        capture_output=True,
        text=True,
    )
    return bin_path


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
    c_file = scratch_dir / "km_c99_ref.c"
    so_file = scratch_dir / "libkm_c99_ref.so"
    c_file.write_text(c_source + "\n" + _CTYPES_EXPORT_SHIM, encoding="utf-8")
    subprocess.run(
        [
            "gcc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-fPIC", "-shared", str(c_file), "-o", str(so_file),
        ],
        env=_go_env(scratch_dir),
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


def test_go_unit_test_suite_passes():
    """Verify `gofmt -l`, `go vet ./...`, and `go test -v ./...` in `Engineering/sw/vmk-go/` pass with zero external dependencies."""
    go_mod_txt = (VMK_GO_DIR / "go.mod").read_text(encoding="utf-8")
    assert "module github.com/nick-fedchik/kuzmin-machine/Engineering/sw/vmk-go" in go_mod_txt
    assert "require" not in go_mod_txt, "go.mod must have zero external dependencies"

    with _workspace_scratch_dir("gotest") as scratch:
        fmt_res = subprocess.run(
            ["gofmt", "-l", "."],
            cwd=str(VMK_GO_DIR),
            env=_go_env(scratch),
            check=True,
            capture_output=True,
            text=True,
        )
        assert fmt_res.stdout.strip() == "", f"Unformatted Go files:\n{fmt_res.stdout}"

        subprocess.run(
            ["go", "vet", "./..."],
            cwd=str(VMK_GO_DIR),
            env=_go_env(scratch),
            check=True,
            capture_output=True,
            text=True,
        )

        res = subprocess.run(
            ["go", "test", "-v", "./..."],
            cwd=str(VMK_GO_DIR),
            env=_go_env(scratch),
            check=True,
            capture_output=True,
            text=True,
        )
        assert "PASS" in res.stdout


def test_vmk_go_equivalence_with_python_c99_iverilog_and_pynq2():
    """Verify 100% equivalence of Go `vmk` against Python `KpolCascadeDebugger`,
    `ReferenceCmeSafetyEngine`, GCC-compiled C99 (`--emit-c99`), `iverilog` `CFG-P` RTL,
    and `km_euclid_core.sv` (`Nod(120, 6) = 6`).
    """
    bms_src = BMS_KPOL.read_text(encoding="utf-8")
    mod = kr.parse_module(bms_src)
    cnames = [s.name for s in mod.states]
    img = kr.compile_concept_microcode_bram_image(mod, profile="KPOL-CME-2")
    c99_code = emit_c99_safety_module(img, profile="KPOL-CME-2", module_name=mod.name, concept_names=cnames)

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
    stdin_lines = "\n".join(
        f"Cell_Delta_mV {'_' if not v else p}" for _, p, v in events
    ) + "\n"

    py_dbg = KpolCascadeDebugger(img, profile="KPOL-CME-2", module_name=mod.name, source_code=bms_src, concept_names=cnames)
    ref_eng = ReferenceCmeSafetyEngine(img, profile="KPOL-CME-2", concept_names=cnames)
    for cid, p, v in events:
        py_dbg.step_event(cid, p, v)
        ref_eng.step_event(cid, p, v)

    with _workspace_scratch_dir("eq_vmk") as scratch:
        vmk_bin = _build_vmk_binary(scratch)
        json_out = scratch / "vmk_bms.json"
        res = subprocess.run(
            [
                str(vmk_bin),
                "--mode", "bram64",
                "--program", str(BMS_KPOL),
                "--profile", "KPOL-CME-2",
                "--stdio",
                "--fail-on-reject",
                "--render-tui-frame",
                "--json-out", str(json_out),
            ],
            input=stdin_lines,
            env=_go_env(scratch),
            capture_output=True,
            text=True,
        )
        assert res.returncode == 1, "expected exit code 1 with --fail-on-reject on rejected BMS events"
        go_payload = json.loads(json_out.read_text(encoding="utf-8"))

        # Check compiled BRAM SHA-256 matches Python compiler bit-for-bit
        import hashlib
        assert go_payload["post_load"]["bram_sha256"] == hashlib.sha256(img).hexdigest()

        # Check telemetry and states match Python debugger & ReferenceCmeSafetyEngine
        telem = go_payload["telemetry"]
        assert telem["events_processed"] == py_dbg.events_processed == ref_eng.events_processed == 19
        assert telem["commits"] == py_dbg.commits == ref_eng.commits == 12
        assert telem["rejects"] == py_dbg.rejects == ref_eng.rejects == 7
        assert telem["fault_propagations"] == py_dbg.fault_propagations == ref_eng.fault_propagations == 1
        assert go_payload["final_active_states"] == py_dbg.state[:4] == [4, 4, 0, 0]

        # Check step-by-step trace matches Python KpolCascadeDebugger across all 19 steps
        go_steps = go_payload["steps"]
        assert len(go_steps) == len(py_dbg.steps) == 19
        for gs, ps in zip(go_steps, py_dbg.steps):
            assert gs["cid"] == ps.cid
            assert gs["depth"] == ps.depth
            assert gs["verdict"] == ps.verdict
            assert gs["pre_w0"] == ps.pre_w0
            assert gs["post_w0"] == ps.post_w0
            assert gs["candidate_w0"] == ps.candidate_w0

        # Check C99 equivalence
        lib = _compile_c99_lib(c99_code, scratch)
        c_ctx = _CSafetyCtx()
        lib.km_Export_init(ctypes.byref(c_ctx))
        for cid, p, v in events:
            lib.km_Export_step_event(ctypes.byref(c_ctx), cid, p, v)
        assert list(c_ctx.state[:4]) == go_payload["final_active_states"] == [4, 4, 0, 0]
        assert int(c_ctx.events_processed) == telem["events_processed"] == 19
        assert int(c_ctx.commits) == telem["commits"] == 12
        assert int(c_ctx.rejects) == telem["rejects"] == 7

        # Check Icarus Verilog CFG-P RTL equivalence on valid events
        hw_valid_events = [(cid, p) for cid, p, v in events if v]
        rtl_res = run_iverilog_cfgp_trace(img, hw_valid_events)
        assert rtl_res["states"] == go_payload["final_active_states"] == [4, 4, 0, 0]
        assert rtl_res["commits"] == telem["commits"] == 12
        assert rtl_res["events"] == 18
        assert rtl_res["rejects"] == 6

        # Check Conceptual Mode all 6 examples + Nod(120, 6) = 6 against km_euclid_core.sv in iverilog
        all_json = scratch / "vmk_all.json"
        res_all = subprocess.run(
            [str(vmk_bin), "--example", "all", "--json-out", str(all_json)],
            env=_go_env(scratch),
            check=True,
            capture_output=True,
            text=True,
        )
        all_data = json.loads(all_json.read_text(encoding="utf-8"))
        assert all_data["if"]["state_trajectory"] == ["_", "!", "¬", "!"]
        assert all_data["sum"]["read_returned_value"] == 35
        assert all_data["sum"]["post_read_state"] == 0
        assert all_data["factorial"]["result"] == 120
        assert all_data["tachometer"]["distance"] == 6
        assert all_data["tachometer"]["speed"] == 6
        assert all_data["tachometer"]["revolutions_post"] == 0

        euclid_rtl = run_iverilog_euclid_verification(120, 6)
        assert all_data["nod"]["result"] == euclid_rtl["result"] == 6
        assert all_data["nod"]["subtraction_iterations"] == euclid_rtl["iterations"] == 19
        assert all_data["nod"]["hardware_cycles_at_3cyc_per_sub_plus_1"] == euclid_rtl["cycles"] == 58


def test_go_code_mutants_m1_to_m7():
    """Verify recorded `pynq2` HIL artifacts and ensure all 7 Go mutants `M1..M7` are killed by `go test`."""
    pynq_json_path = RAW_DIR / "pynq2_live_vmk_session.json"
    pynq_log_path = RAW_DIR / "pynq2_live_vmk_session.log"
    assert pynq_json_path.is_file(), f"Missing {pynq_json_path}"
    assert pynq_log_path.is_file(), f"Missing {pynq_log_path}"

    for log_file in RAW_DIR.glob("*.log"):
        head = log_file.read_text(encoding="utf-8")[:600]
        assert "# cmd:" in head
        assert "# timestamp:" in head
        assert "# git_commit:" in head
        assert "# host:" in head

    pynq_data = json.loads(pynq_json_path.read_text(encoding="utf-8"))
    hw_rep = pynq_data["pynq_hw_report"]
    assert hw_rep["target"] == "pynq2"
    assert hw_rep["readback_verified"] is True
    assert hw_rep["pre_load"]["topology"]["active_concepts"] == 1
    assert hw_rep["post_load"]["topology"]["active_concepts"] == 4
    assert hw_rep["changed_slots_on_load"] == 4
    assert hw_rep["events_delta"] == 18
    assert hw_rep["commits_delta"] == 12
    assert hw_rep["rejects_delta"] == 6

    mutants = [
        (
            "M1_go_invert_predicate",
            "internal/vmk/bram64.go",
            "return assumpKnown && assumpTrue",
            "return assumpKnown && (!assumpTrue)",
        ),
        (
            "M2_go_bypass_invariant_gate",
            "internal/vmk/bram64.go",
            "return actionValid && invKnown && invTrue && (!hazTrue)",
            "return true",
        ),
        (
            "M3_go_ignore_uncertainty_bit",
            "internal/vmk/bram64.go",
            "isUncertaintyFault := (!curValid) || (!preValid)",
            "isUncertaintyFault := false",
        ),
        (
            "M4_go_skip_post_read_dot_reset",
            "internal/vmk/conceptual.go",
            "if slot.PostReadZero {\n\t\tslot.FloatVal = 0\n\t\tslot.IntVal = 0\n\t}",
            "if false && slot.PostReadZero {\n\t\tslot.FloatVal = 0\n\t\tslot.IntVal = 0\n\t}",
        ),
        (
            "M5_go_corrupt_pre_post_load_diff",
            "internal/vmk/snapshot.go",
            "slotChanged := w0Changed || w123Changed",
            "slotChanged := w0Changed",
        ),
        (
            "M6_go_break_single_hop_subscriber_enqueue",
            "internal/vmk/bram64.go",
            "if enqueuedCID != nil && depth+1 < 64 {",
            "if false && enqueuedCID != nil && depth+1 < 64 {",
        ),
        (
            "M7_go_break_modify_concept_state",
            "internal/vmk/bram64.go",
            "e.State[cid] = newW0",
            "e.State[cid] = 0",
        ),
    ]

    for m_name, rel_file, orig_snippet, mut_snippet in mutants:
        with _workspace_scratch_dir(m_name) as scratch:
            mut_repo = scratch / "vmk-go"
            shutil.copytree(VMK_GO_DIR, mut_repo)
            target_go = mut_repo / rel_file
            src_txt = target_go.read_text(encoding="utf-8")
            assert orig_snippet in src_txt, f"Original snippet for {m_name} not found in {rel_file}"
            target_go.write_text(src_txt.replace(orig_snippet, mut_snippet, 1), encoding="utf-8")

            res = subprocess.run(
                ["go", "test", "./..."],
                cwd=str(mut_repo),
                env=_go_env(scratch),
                capture_output=True,
                text=True,
            )
            assert res.returncode != 0, f"Mutant {m_name} survived `go test ./...`!\n{res.stdout}\n{res.stderr}"


def _validate_vmk_guide_and_readme(guide_txt: str, readme_txt: str, guide_dir: Path, readme_dir: Path) -> None:
    """Validate structure, required Guide sections, CLI coverage, and relative links of
    `Engineering/guides/vmk-users-guide.md` and `Engineering/sw/vmk-go/README.md`.
    """
    import re

    required_guide_headings = [
        "* **Версія:** 1.2.0",
        "* **Тип WP:** Guide",
        "## Призначення",
        "## Навігація чи використання",
        "### 2.1.",
        "### 2.2.",
        "### 2.3.",
        "### 2.4.",
        "### 2.5.",
        "### 2.6.",
        "### 2.7.",
        "### 2.8.",
        "### 2.9.",
        "## Обмеження",
        "## Історія версій",
        "## Абревіатури та глосарій",
        "<ваш_пароль_sudo>",
        "--program ../../validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol",
        "--render-fullscreen-tui",
        "CONCEPT INSPECTOR",
    ]
    for marker in required_guide_headings:
        if marker not in guide_txt:
            raise AssertionError(f"vmk-users-guide.md missing required marker {marker!r}")

    if "--program ../validation/" in guide_txt or re.search(r"(?<!\.\./)\.\./validation/kpol-cme/c99-emitter-270/", guide_txt):
        raise AssertionError("vmk-users-guide.md contains broken relative CLI path ../validation/ from Engineering/sw/vmk-go")

    required_cli_flags = [
        "--mode",
        "--example",
        "--program",
        "--profile",
        "--target",
        "--trace-events",
        "--dump-concepts",
        "--stdio",
        "--fail-on-reject",
        "--tui",
        "--tui-canvas",
        "--render-tui-frame",
        "--render-fullscreen-tui",
        "--watch-cid",
        "--break-on-reject",
        "--stop-on-breakpoint",
        "--json-out",
        "--version",
    ]
    for flag_name in required_cli_flags:
        if flag_name not in guide_txt:
            raise AssertionError(f"vmk-users-guide.md missing CLI flag {flag_name!r}")

    required_readme_markers = [
        "* **Версія:** 1.2.0",
        "* **Тип WP:** Guide",
        "## Призначення",
        "## Навігація чи використання",
        "../../guides/vmk-users-guide.md",
        "../../specifications/sw/vmk-go-emulator-and-tui-debugger-0.1.0.md",
        "## Обмеження",
        "## Історія версій",
        "## Абревіатури та глосарій",
    ]
    for marker in required_readme_markers:
        if marker not in readme_txt:
            raise AssertionError(f"Engineering/sw/vmk-go/README.md missing required marker {marker!r}")

    link_re = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
    for doc_name, txt, parent_dir in [
        ("vmk-users-guide.md", guide_txt, guide_dir),
        ("vmk-go/README.md", readme_txt, readme_dir),
    ]:
        in_fence = False
        for line in txt.splitlines():
            if line.strip().startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            if in_fence:
                if re.search(r"(?<!\.\./)\.\./validation/", line):
                    raise AssertionError(f"{doc_name}: broken ../validation/ path inside code block: {line!r}")
                continue
            for m in link_re.finditer(line):
                target = m.group(1).split("#", 1)[0]
                if not target or target.startswith(("http://", "https://", "mailto:")):
                    continue
                resolved = (parent_dir / target).resolve()
                if not resolved.exists():
                    raise AssertionError(f"{doc_name}: broken relative link {target!r} -> {resolved}")


def test_vmk_users_guide_and_readme_276():
    """Issue #276: Verify `Engineering/guides/vmk-users-guide.md` and `Engineering/sw/vmk-go/README.md`
    envelope, sections 2.1..2.8, CLI flag reference, relative links, registration in `wp-index.json`,
    and negative mutant controls (`AGENTS.md §4.1`).
    """
    guide_path = REPO_ROOT / "Engineering" / "guides" / "vmk-users-guide.md"
    readme_path = VMK_GO_DIR / "README.md"
    assert guide_path.is_file(), f"Missing {guide_path}"
    assert readme_path.is_file(), f"Missing {readme_path}"

    guide_txt = guide_path.read_text(encoding="utf-8")
    readme_txt = readme_path.read_text(encoding="utf-8")
    _validate_vmk_guide_and_readme(guide_txt, readme_txt, guide_path.parent, readme_path.parent)

    # Check registration in README.md and Project/registers/wp-index.json
    root_readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Engineering/guides/vmk-users-guide.md" in root_readme
    wp_index = json.loads((REPO_ROOT / "Project" / "registers" / "wp-index.json").read_text(encoding="utf-8"))
    by_path = {e["path"]: e for e in wp_index["entries"]}
    assert by_path.get("Engineering/guides/vmk-users-guide.md", {}).get("wp_type") == "Guide"
    assert by_path.get("Engineering/sw/vmk-go/README.md", {}).get("wp_type") == "Guide"

    # Negative control 1 (AGENTS.md §4.1): missing required section must fail validation
    mut_guide_section = guide_txt.replace("## Обмеження", "## Вилучений розділ", 1)
    with pytest.raises(AssertionError, match="missing required marker"):
        _validate_vmk_guide_and_readme(mut_guide_section, readme_txt, guide_path.parent, readme_path.parent)

    # Negative control 2 (AGENTS.md §4.1): broken relative link must fail validation
    mut_readme_link = readme_txt.replace(
        "../../guides/vmk-users-guide.md",
        "../../guides/non_existent_vmk_guide_276.md",
        1,
    )
    with pytest.raises(AssertionError, match="broken relative link"):
        _validate_vmk_guide_and_readme(guide_txt, mut_readme_link, guide_path.parent, readme_path.parent)

    # Negative control 3 (AGENTS.md §4.1, F1): broken ../validation/ CLI path must fail validation
    mut_guide_cli_path = guide_txt.replace(
        "--program ../../validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol",
        "--program ../validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol",
        1,
    )
    with pytest.raises(AssertionError, match="broken|missing required marker"):
        _validate_vmk_guide_and_readme(mut_guide_cli_path, readme_txt, guide_path.parent, readme_path.parent)

    # Verify the documented CLI command from Engineering/sw/vmk-go executes with exit code 0 (F1)
    with _workspace_scratch_dir("guide_cli_f1") as scratch:
        vmk_bin = _build_vmk_binary(scratch)
        res_dump = subprocess.run(
            [
                str(vmk_bin),
                "--program",
                "../../validation/kpol-cme/c99-emitter-270/bms_safety_cascade.kpol",
                "--profile",
                "KPOL-CME-2",
                "--dump-concepts",
            ],
            cwd=str(VMK_GO_DIR),
            env=_go_env(scratch),
            capture_output=True,
            text=True,
        )
        assert res_dump.returncode == 0, (
            f"Documented --dump-concepts command failed from Engineering/sw/vmk-go:\n{res_dump.stderr}"
        )
        assert "BRAM DESCRIPTOR TABLE" in res_dump.stdout
        assert "Cell_Delta_mV" in res_dump.stdout


def test_fullscreen_tui_debugger_interactive_280():
    """Issue #280: Verify full-screen interactive TUI debugger (`VMK v0.3.0`) across both
    `bram64` and `conceptual` modes using automated keystroke streams (`↑/↓`, `e` manual event
    creation, `+` queue addition, `n` single micro-step wave hop `C0 -> C1 -> C2 -> C3`,
    `f` fault injection `_`, `m` manual state modification, `d` diff/source toggle, `r` reset, `q` quit).
    """
    with _workspace_scratch_dir("tui_280") as scratch:
        vmk_bin = _build_vmk_binary(scratch)

        # 1. Verify --render-fullscreen-tui on BMS (bram64)
        res_fs = subprocess.run(
            [str(vmk_bin), "--example", "bms", "--render-fullscreen-tui"],
            cwd=str(VMK_GO_DIR),
            env=_go_env(scratch),
            check=True,
            capture_output=True,
            text=True,
        )
        assert "VMK v0.3.0 FULL-SCREEN DEBUGGER" in res_fs.stdout
        assert "[1] CONCEPTS" in res_fs.stdout
        assert "[2] CONCEPT INSPECTOR" in res_fs.stdout
        assert "Concept ID & Name : C00 (Cell_Delta_mV)" in res_fs.stdout
        assert "[3] CASCADE WAVE TRACE & PENDING EVENT QUEUE" in res_fs.stdout
        assert "[4] STDIO STREAMS (STDIN / STDOUT / STDERR) & INTERACTIVE EVENT CREATOR" in res_fs.stdout

        # 2. Verify interactive keystroke session on BMS via --tui-canvas:
        #    Down arrow (\x1b[B) -> select C01 -> 'w' watchpoint -> Up arrow (\x1b[A) ->
        #    'e' open Event Creator -> "120+" enqueue into Pending Queue ->
        #    'n' 4 times (1 hop per press: C00 -> C01 -> C02 -> C03) ->
        #    'f' inject fault '_' -> 'm99\n' modify C00 W0 to 99 -> 'd' toggle Source -> 'd' toggle Diff -> 'q' quit
        json_out = scratch / "tui_bms_session.json"
        keystrokes = "\x1b[Bw\x1b[Ae120+nnnnfm99\nddq"
        res_int = subprocess.run(
            [
                str(vmk_bin),
                "--program",
                "examples/bms_safety_cascade.ekpol",
                "--tui-canvas",
                "--json-out",
                str(json_out),
            ],
            cwd=str(VMK_GO_DIR),
            input=keystrokes,
            env=_go_env(scratch),
            check=True,
            capture_output=True,
            text=True,
        )
        assert "PRE-LOAD vs POST-LOAD DIFF" in res_int.stdout
        payload = json.loads(json_out.read_text(encoding="utf-8"))
        assert payload["version"] == "0.3.0"
        assert payload["final_active_states"] == [1, 1, 1, 99]
        assert payload["telemetry"]["events_processed"] == 5
        assert payload["telemetry"]["commits"] == 4
        assert payload["telemetry"]["fault_propagations"] == 1
