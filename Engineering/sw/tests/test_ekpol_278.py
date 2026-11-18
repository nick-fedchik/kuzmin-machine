#!/usr/bin/env python3
"""Issue #278: Comprehensive verification suite for EKPOL (`Ergonomic KPOL 0.1.0`)
and Go `VMK v0.2.0` (`Engineering/sw/kpol-ref/ekpol_frontend.py`,
`Engineering/hw/scripts/compile_kpol_bram_image.py`, `Engineering/sw/vmk-go/`).

Covers:
  1. Bit-for-bit SHA-256 identity of 1024-byte BRAM images (`CME-RAW-1`) compiled from
     `.ekpol` (both symbolic `<- / ~ / :: / .` and keyword `on write / on change / when / commit`)
     vs classic `.kpol` (`increase`, `decrease`, `cascade`, `bms`) in both Python and Go `vmk v0.2.0`;
  2. Bidirectional lossless transpilation `KPOL -> EKPOL -> KPOL -> BRAM` (`--emit-ekpol`,
     `--emit-kpol`, `--to-ekpol`, `--to-kpol`, `--ekpol-style symbolic|keyword`) with 0 non-ASCII characters;
  3. Direct `--emit-c99` and `--emit-z3-cert` generation from `.ekpol` and `kpol_debugger.py` execution;
  4. Execution of all 9 canonical `.ekpol` examples (`bms_safety_cascade.ekpol`,
     `cascade_4concept.ekpol`, `increase.ekpol`, `decrease.ekpol`, `if_toggle.ekpol`,
     `sum_autoreset.ekpol`, `nod_euclid.ekpol`, `factorial.ekpol`, `tachometer.ekpol`) in Go `vmk v0.2.0`;
  5. Five negative mutant tests (`M1..M5`, `AGENTS.md §4 п. 1` and Issue #278 C6):
     - `M1_ekpol_cycle_detection`
     - `M2_ekpol_range_bounds_swap`
     - `M3_ekpol_keyword_vs_symbolic_divergence`
     - `M4_ekpol_post_read_dot_order`
     - `M5_ekpol_invariant_bracket_drop`
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib.util
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
VMK_GO_DIR = REPO_ROOT / "Engineering" / "sw" / "vmk-go"
EXAMPLES_DIR = VMK_GO_DIR / "examples"
COMPILER_CLI = REPO_ROOT / "Engineering" / "hw" / "scripts" / "compile_kpol_bram_image.py"
DEBUGGER_CLI = SW_REF_DIR / "kpol_debugger.py"

INC_KPOL = REPO_ROOT / "Engineering" / "hw" / "tests" / "kpol_bram_pipeline_increase.kpol"
DEC_KPOL = REPO_ROOT / "Engineering" / "hw" / "tests" / "kpol_bram_pipeline_decrease.kpol"
BMS_KPOL = REPO_ROOT / "Engineering" / "validation" / "kpol-cme" / "c99-emitter-270" / "bms_safety_cascade.kpol"

SPEC_EKPOL_MD = REPO_ROOT / "Engineering" / "specifications" / "kpol" / "ekpol-specification-0.1.0.md"
REPORT_EKPOL_MD = REPO_ROOT / "Engineering" / "validation" / "kpol-cme" / "ekpol-278" / "report.md"
RAW_EKPOL_DIR = REPO_ROOT / "Engineering" / "validation" / "kpol-cme" / "ekpol-278" / "raw"

if str(SW_REF_DIR) not in sys.path:
    sys.path.insert(0, str(SW_REF_DIR))

from c99_emitter import emit_c99_safety_module, prove_c99_descriptor_safety_z3  # noqa: E402
import ekpol_frontend as ef  # noqa: E402
import kpol_debugger as kd  # noqa: E402
import kpol_reference as kr  # noqa: E402

EXPECTED_SHA256 = {
    "increase": "4df05b189b9bf12052d98ab6084e0256454c60cae4afd4449469c060ba8dcc5d",
    "decrease": "00ba66e57e21d14913c95d7d2fc8c45c3c450548510ca3155721d7eec67b78c3",
    "cascade": "032c4705c91cea6ddddb7d449cd0dcbd6ba62359af1f9e7a846f33c341a7ef38",
    "bms": "de03442454424b5cf64478506f118c13f095ae24ba58db8894583c43567ea3ee",
}


@contextmanager
def _workspace_scratch_dir(prefix: str = "ekpol_278"):
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


def _load_mutated_ekpol_module(scratch_dir: Path, mut_name: str, orig_snippet: str, mut_snippet: str):
    """Load a mutated copy of `ekpol_frontend.py` from `scratch_dir` to verify mutant detection."""
    src_path = SW_REF_DIR / "ekpol_frontend.py"
    src_txt = src_path.read_text(encoding="utf-8")
    assert orig_snippet in src_txt, f"Original snippet for {mut_name} not found in ekpol_frontend.py"
    mut_txt = src_txt.replace(orig_snippet, mut_snippet, 1)
    mut_file = scratch_dir / f"ekpol_frontend_{mut_name}.py"
    mut_file.write_text(mut_txt, encoding="utf-8")

    spec = importlib.util.spec_from_file_location(f"ekpol_frontend_{mut_name}", mut_file)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_classic_kpol_files_unmodified_and_sha256_preserved():
    """Step 1.1: Verify classic `.kpol` files and classic profiles `KPOL-CME-1/2/AUTH` are 100% preserved."""
    inc_src = INC_KPOL.read_text(encoding="utf-8")
    dec_src = DEC_KPOL.read_text(encoding="utf-8")
    bms_src = BMS_KPOL.read_text(encoding="utf-8")
    cas_src = kd.EXAMPLE_2_CASCADE_4STAGE_SOURCE

    for name, src, prof in [
        ("increase", inc_src, "KPOL-CME-1"),
        ("decrease", dec_src, "KPOL-CME-1"),
        ("cascade", cas_src, "KPOL-CME-2"),
        ("bms", bms_src, "KPOL-CME-2"),
    ]:
        mod = kr.parse_module(src)
        img = kr.compile_concept_microcode_bram_image(mod, profile=prof)
        assert hashlib.sha256(img).hexdigest() == EXPECTED_SHA256[name]


def test_ekpol_bit_identical_bram_and_bidirectional_roundtrip_python_and_go():
    """Steps 2 & 3: Verify 100% bit-for-bit SHA-256 identity of 1024-byte BRAM images across:
      - `examples/*.ekpol` (`increase`, `decrease`, `cascade_4concept`, `bms_safety_cascade`),
      - Both `"symbolic"` (`<- / ~ / :: / .`) and `"keyword"` (`on write / on change / when / commit`) styles,
      - Bidirectional roundtrip `KPOL -> EKPOL -> KPOL -> BRAM` in both Python and Go `vmk v0.2.0`.
    """
    classic_sources = {
        "increase": (INC_KPOL.read_text(encoding="utf-8"), "KPOL-CME-1", EXAMPLES_DIR / "increase.ekpol"),
        "decrease": (DEC_KPOL.read_text(encoding="utf-8"), "KPOL-CME-1", EXAMPLES_DIR / "decrease.ekpol"),
        "cascade": (kd.EXAMPLE_2_CASCADE_4STAGE_SOURCE, "KPOL-CME-2", EXAMPLES_DIR / "cascade_4concept.ekpol"),
        "bms": (BMS_KPOL.read_text(encoding="utf-8"), "KPOL-CME-2", EXAMPLES_DIR / "bms_safety_cascade.ekpol"),
    }

    with _workspace_scratch_dir("roundtrip") as scratch:
        vmk_bin = _build_vmk_binary(scratch)

        # Check VMK version is v0.3.0
        ver_res = subprocess.run(
            [str(vmk_bin), "--version"],
            env=_go_env(scratch),
            check=True,
            capture_output=True,
            text=True,
        )
        assert ver_res.stdout.strip() == "VMK (Virtual Machine of Kuzmin) v0.3.0"

        for name, (kpol_src, cme_prof, ekpol_example_path) in classic_sources.items():
            assert ekpol_example_path.is_file(), f"Missing canonical example {ekpol_example_path}"
            ekpol_file_src = ekpol_example_path.read_text(encoding="utf-8")
            assert all(ord(ch) < 128 for ch in ekpol_file_src), f"{ekpol_example_path.name} must be pure 7-bit ASCII"

            # 1. Direct Python compilation of examples/<name>.ekpol
            py_img = ef.compile_ekpol_to_bram_image(ekpol_file_src)
            assert len(py_img) == 1024
            assert hashlib.sha256(py_img).hexdigest() == EXPECTED_SHA256[name]

            # 2. Both symbolic and keyword transpilation in Python
            for style in ("symbolic", "keyword"):
                ek_transpiled = ef.transpile_kpol_to_ekpol(kpol_src, style=style)
                assert all(ord(ch) < 128 for ch in ek_transpiled)
                if style == "symbolic":
                    assert "<-" in ek_transpiled and "=>" in ek_transpiled and " ." in ek_transpiled
                else:
                    assert "on " in ek_transpiled and "when " in ek_transpiled and "commit;" in ek_transpiled

                img_style = ef.compile_ekpol_to_bram_image(ek_transpiled)
                assert hashlib.sha256(img_style).hexdigest() == EXPECTED_SHA256[name]

                back_kpol = ef.transpile_ekpol_to_kpol(ek_transpiled)
                back_mod = kr.parse_module(back_kpol)
                back_img = kr.compile_concept_microcode_bram_image(back_mod, profile=cme_prof)
                assert hashlib.sha256(back_img).hexdigest() == EXPECTED_SHA256[name]

            # 3. Go `vmk` --to-ekpol (symbolic & keyword), --to-kpol, and --program <file.ekpol>
            for style in ("symbolic", "keyword"):
                res_to_ek = subprocess.run(
                    [str(vmk_bin), "--program", str(ekpol_example_path), "--to-ekpol", "--ekpol-style", style],
                    env=_go_env(scratch),
                    check=True,
                    capture_output=True,
                    text=True,
                )
                go_ek_txt = res_to_ek.stdout
                assert all(ord(ch) < 128 for ch in go_ek_txt)
                assert hashlib.sha256(ef.compile_ekpol_to_bram_image(go_ek_txt)).hexdigest() == EXPECTED_SHA256[name]

                res_to_kpol = subprocess.run(
                    [str(vmk_bin), "--program", str(ekpol_example_path), "--to-kpol"],
                    env=_go_env(scratch),
                    check=True,
                    capture_output=True,
                    text=True,
                )
                go_kpol_mod = kr.parse_module(res_to_kpol.stdout)
                go_kpol_img = kr.compile_concept_microcode_bram_image(go_kpol_mod, profile=cme_prof)
                assert hashlib.sha256(go_kpol_img).hexdigest() == EXPECTED_SHA256[name]

            # 4. Go `vmk` execution on .ekpol with --json-out
            json_out = scratch / f"vmk_{name}.json"
            res_run = subprocess.run(
                [str(vmk_bin), "--program", str(ekpol_example_path), "--dump-concepts", "--json-out", str(json_out)],
                env=_go_env(scratch),
                check=True,
                capture_output=True,
                text=True,
            )
            assert EXPECTED_SHA256[name][:16] in res_run.stdout
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            assert payload["post_load"]["bram_sha256"] == EXPECTED_SHA256[name]


def test_compile_cli_c99_z3_and_debugger_on_ekpol():
    """Verify `compile_kpol_bram_image.py` (`--emit-kpol`, `--emit-ekpol`, `--emit-c99`,
    `--emit-z3-cert`, `--dump-concepts`, `--trace-events`) and `kpol_debugger.py` on `.ekpol`.
    """
    bms_ekpol = EXAMPLES_DIR / "bms_safety_cascade.ekpol"
    with _workspace_scratch_dir("cli_c99_z3") as scratch:
        out_bin = scratch / "bms_from_ekpol.bin"
        out_kpol = scratch / "bms_emitted.kpol"
        out_ekpol_kw = scratch / "bms_keyword.ekpol"
        out_c99 = scratch / "bms_safety.c"
        out_z3 = scratch / "bms_z3_cert.json"

        res = subprocess.run(
            [
                sys.executable,
                str(COMPILER_CLI),
                str(bms_ekpol),
                str(out_bin),
                "--emit-kpol",
                str(out_kpol),
                "--emit-ekpol",
                str(out_ekpol_kw),
                "--ekpol-style",
                "keyword",
                "--emit-c99",
                str(out_c99),
                "--emit-z3-cert",
                str(out_z3),
                "--dump-concepts",
                "--trace-events",
                "0:15,0:120,0:invalid",
            ],
            env=_go_env(scratch),
            check=True,
            capture_output=True,
            text=True,
        )
        assert out_bin.is_file()
        assert hashlib.sha256(out_bin.read_bytes()).hexdigest() == EXPECTED_SHA256["bms"]
        assert "Problem BmsSafetyCascade" in out_kpol.read_text(encoding="utf-8")
        assert "on change(Cell_Delta_mV)" in out_ekpol_kw.read_text(encoding="utf-8")
        assert "km_safety_step_event" in out_c99.read_text(encoding="utf-8")
        z3_data = json.loads(out_z3.read_text(encoding="utf-8"))
        assert z3_data["passed"] is True
        assert "=== [BLOCK 3] STEP-BY-STEP EVENT & CASCADE TRACE" in res.stdout

        # Also test kpol_debugger.py directly on bms_safety_cascade.ekpol
        dbg_json = scratch / "dbg_bms.json"
        res_dbg = subprocess.run(
            [
                sys.executable,
                str(DEBUGGER_CLI),
                "--program",
                str(bms_ekpol),
                "--trace-events",
                "0:15,0:120,0:180",
                "--json-out",
                str(dbg_json),
            ],
            env=_go_env(scratch),
            check=True,
            capture_output=True,
            text=True,
        )
        assert res_dbg.returncode == 0
        dbg_payload = json.loads(dbg_json.read_text(encoding="utf-8"))
        assert dbg_payload["post_load"]["bram_sha256"] == EXPECTED_SHA256["bms"]
        assert dbg_payload["report"]["telemetry"]["commits"] == 8
        assert dbg_payload["report"]["telemetry"]["rejects"] == 1


def test_all_nine_ekpol_examples_in_vmk_v020():
    """Verify all 9 canonical `.ekpol` examples (`bms_safety_cascade`, `cascade_4concept`,
    `increase`, `decrease`, `if_toggle`, `sum_autoreset`, `nod_euclid`, `factorial`,
    `tachometer`) execute in Go `vmk v0.2.0` and produce expected states/hashes.
    """
    bram_cases = [
        ("increase.ekpol", EXPECTED_SHA256["increase"]),
        ("decrease.ekpol", EXPECTED_SHA256["decrease"]),
        ("cascade_4concept.ekpol", EXPECTED_SHA256["cascade"]),
        ("bms_safety_cascade.ekpol", EXPECTED_SHA256["bms"]),
    ]
    conceptual_cases = [
        ("if_toggle.ekpol", "COMMIT: If[cid=0] = !"),
        ("sum_autoreset.ekpol", "READ: Sum = 35 (post-dot → • reset Sum = 0)"),
        ("nod_euclid.ekpol", "COMMIT: Nod[cid=2] = 6"),
        ("factorial.ekpol", "COMMIT: Factorial[cid=1] = 120"),
        ("tachometer.ekpol", "COMMIT: Tachometer._Tick -> Speed=6, Revolutions=0 (Distance=6)"),
    ]
    with _workspace_scratch_dir("all9_ekpol") as scratch:
        vmk_bin = _build_vmk_binary(scratch)

        for filename, expected_sha in bram_cases:
            ek_path = EXAMPLES_DIR / filename
            assert ek_path.is_file(), f"Missing {ek_path}"
            ek_txt = ek_path.read_text(encoding="utf-8")
            assert all(ord(ch) < 128 for ch in ek_txt), f"{filename} contains non-ASCII characters"
            json_out = scratch / f"{filename}.json"
            res = subprocess.run(
                [str(vmk_bin), "--program", str(ek_path), "--json-out", str(json_out)],
                env=_go_env(scratch),
                check=True,
                capture_output=True,
                text=True,
            )
            assert res.returncode == 0
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            assert payload["post_load"]["bram_sha256"] == expected_sha

        for filename, expected_stdout_marker in conceptual_cases:
            ek_path = EXAMPLES_DIR / filename
            assert ek_path.is_file(), f"Missing {ek_path}"
            ek_txt = ek_path.read_text(encoding="utf-8")
            assert all(ord(ch) < 128 for ch in ek_txt), f"{filename} contains non-ASCII characters"

            json_out = scratch / f"{filename}.json"
            res = subprocess.run(
                [str(vmk_bin), "--program", str(ek_path), "--json-out", str(json_out)],
                env=_go_env(scratch),
                check=True,
                capture_output=True,
                text=True,
            )
            assert "VMK (Virtual Machine of Kuzmin) v0.3.0" in res.stdout
            payload = json.loads(json_out.read_text(encoding="utf-8"))
            assert payload["mode"] == "conceptual"
            assert payload["profile"] == "EKPOL"
            joined_stdout = "\n".join(payload["stdout"])
            assert expected_stdout_marker in joined_stdout, (
                f"{filename}: expected {expected_stdout_marker!r} in stdout {payload['stdout']}"
            )


def test_mutants_m1_to_m5_all_killed():
    """Verify all 5 required mutants (`M1..M5`, `AGENTS.md §4 п. 1` and Issue #278 C6) are deterministically killed."""
    bms_ekpol_src = (EXAMPLES_DIR / "bms_safety_cascade.ekpol").read_text(encoding="utf-8")
    bms_kpol_src = BMS_KPOL.read_text(encoding="utf-8")

    # Baseline check: cyclic EKPOL is rejected with EKPOL-CYCLE-ERR
    cyclic_ekpol = """
    concept C0: i32 = 0 [>= 0] { ~ C1 :: C1 >= 1 => C0 += 1 . }
    concept C1: i32 = 0 [>= 0] { ~ C0 :: C0 >= 1 => C1 += 1 . }
    """
    with pytest.raises(ef.EkpolError, match="EKPOL-CYCLE-ERR"):
        ef.compile_ekpol_to_bram_image(cyclic_ekpol)

    with _workspace_scratch_dir("mutants_278") as scratch:
        # M1: Disable cycle detection in ekpol_frontend.py -> cyclic program is not rejected by validate_ekpol_for_bram64
        m1_mod = _load_mutated_ekpol_module(
            scratch,
            "M1_ekpol_cycle_detection",
            "if cur is not None and visit_state[cur] == 1:",
            "if False and cur is not None and visit_state[cur] == 1:",
        )
        m1_prog = m1_mod.parse_ekpol(cyclic_ekpol)
        # In the unmutated frontend, validate_ekpol_for_bram64 raises EKPOL-CYCLE-ERR; in M1 it survives!
        with pytest.raises(ef.EkpolError, match="EKPOL-CYCLE-ERR"):
            ef.validate_ekpol_for_bram64(ef.parse_ekpol(cyclic_ekpol))
        m1_descs = m1_mod.validate_ekpol_for_bram64(m1_prog)
        assert m1_descs[0].subscriber_cid == 1 and m1_descs[1].subscriber_cid == 0

        # M2: Swap LO and HI bounds in range packing in ekpol_frontend.py -> caught by BRAM SHA-256 check
        m2_mod = _load_mutated_ekpol_module(
            scratch,
            "M2_ekpol_range_bounds_swap",
            "guard_op_u32 = ((pred.hi & 0xFFFF) << 16) | (pred.lo & 0xFFFF)",
            "guard_op_u32 = ((pred.lo & 0xFFFF) << 16) | (pred.hi & 0xFFFF)",
        )
        m2_prog = m2_mod.parse_ekpol(bms_ekpol_src)
        m2_descs = m2_mod.validate_ekpol_for_bram64(m2_prog)
        m2_bytes = b"".join(d.pack() for d in m2_descs)
        assert hashlib.sha256(m2_bytes).hexdigest() != EXPECTED_SHA256["bms"], "M2 range swap survived BRAM check!"

        # M3: Diverge keyword `on change` vs symbolic `~` mapping in ekpol_frontend.py -> caught by equivalence check
        m3_mod = _load_mutated_ekpol_module(
            scratch,
            "M3_ekpol_keyword_vs_symbolic_divergence",
            'lines.append(f"    on change({watch_var}) when {guard_str} => {act_str} commit;")',
            'lines.append(f"    on write({watch_var}) when {guard_str} => {act_str} commit;")',
        )
        sym_ek = m3_mod.transpile_kpol_to_ekpol(bms_kpol_src, style="symbolic")
        kw_ek = m3_mod.transpile_kpol_to_ekpol(bms_kpol_src, style="keyword")
        sym_descs = m3_mod.validate_ekpol_for_bram64(m3_mod.parse_ekpol(sym_ek))
        kw_descs = m3_mod.validate_ekpol_for_bram64(m3_mod.parse_ekpol(kw_ek))
        assert b"".join(d.pack() for d in sym_descs) != b"".join(d.pack() for d in kw_descs), (
            "M3 keyword vs symbolic divergence was not detected!"
        )

        # M4: Mutate post-read Big Dot barrier in Go `internal/vmk/ekpol.go` -> caught by `go test ./...`
        mut_go_repo = scratch / "vmk-go-m4"
        shutil.copytree(VMK_GO_DIR, mut_go_repo)
        ekpol_go_path = mut_go_repo / "internal" / "vmk" / "ekpol.go"
        ekpol_go_txt = ekpol_go_path.read_text(encoding="utf-8")
        orig_m4 = "PostReadBarrier: postReadDot,"
        mut_m4 = "PostReadBarrier: false,"
        assert orig_m4 in ekpol_go_txt
        ekpol_go_path.write_text(ekpol_go_txt.replace(orig_m4, mut_m4, 1), encoding="utf-8")
        res_m4 = subprocess.run(
            ["go", "test", "./..."],
            cwd=str(mut_go_repo),
            env=_go_env(scratch),
            capture_output=True,
            text=True,
        )
        assert res_m4.returncode != 0, f"M4 Go post-read barrier mutant survived `go test`!\n{res_m4.stdout}"

        # M5: Drop CME_GUARD_INVARIANT_EN flag when lowering `[>= 0]` in ekpol_frontend.py -> caught by BRAM & Z3 check
        m5_mod = _load_mutated_ekpol_module(
            scratch,
            "M5_ekpol_invariant_bracket_drop",
            "guard_flags = CME_GUARD_ASSUMPTION_EN | CME_GUARD_INVARIANT_EN",
            "guard_flags = CME_GUARD_ASSUMPTION_EN",
        )
        m5_prog = m5_mod.parse_ekpol(bms_ekpol_src)
        m5_descs = m5_mod.validate_ekpol_for_bram64(m5_prog)
        m5_bytes = b"".join(d.pack() for d in m5_descs)
        assert hashlib.sha256(m5_bytes).hexdigest() != EXPECTED_SHA256["bms"], "M5 invariant drop survived BRAM check!"
        m5_c99 = emit_c99_safety_module(
            m5_descs,
            profile="KPOL-CME-2",
            module_name="BmsSafetyCascade",
            concept_names=[c.name for c in m5_prog.concepts],
            require_z3_verified=False,
        )
        m5_z3 = prove_c99_descriptor_safety_z3(
            m5_descs,
            c99_source=m5_c99,
            profile="KPOL-CME-2",
            module_name="BmsSafetyCascade",
            concept_names=[c.name for c in m5_prog.concepts],
        )
        assert m5_z3["passed"] is False, "M5 invariant drop survived Z3 safety verification!"


def test_ekpol_spec_report_raw_provenance_and_wp_index():
    """Verify `ekpol-specification-0.1.0.md`, `ekpol-278/report.md`, raw logs provenance, and `wp-index.json`."""
    assert SPEC_EKPOL_MD.is_file(), f"Missing {SPEC_EKPOL_MD}"
    assert REPORT_EKPOL_MD.is_file(), f"Missing {REPORT_EKPOL_MD}"
    spec_txt = SPEC_EKPOL_MD.read_text(encoding="utf-8")
    rep_txt = REPORT_EKPOL_MD.read_text(encoding="utf-8")

    for marker in [
        "* **Версія:** 1.0.1",
        "* **Тип WP:** Specification",
        "AGENTS.md §4 п. 1",
        "ekpol_program",
        "EKPOL-CYCLE-ERR",
        "## Історія версій",
        "## Абревіатури та глосарій",
    ]:
        assert marker in spec_txt, f"Spec missing {marker!r}"

    for marker in [
        "* **Версія:** 1.0.1",
        "* **Тип WP:** Report",
        "AGENTS.md §4 п. 1",
        "AGENTS.md §4 п. 2",
        "PASS (програмна компіляція / симуляція VMK, без запуску на FPGA)",
        "a19bca2157ec1a6fd632b7bcd9b34654a96adea0",
        "test_all_nine_ekpol_examples_in_vmk_v020",
        "M1_ekpol_cycle_detection",
        "M2_ekpol_range_bounds_swap",
        "M3_ekpol_keyword_vs_symbolic_divergence",
        "M4_ekpol_post_read_dot_order",
        "M5_ekpol_invariant_bracket_drop",
        "de03442454424b5cf64478506f118c13f095ae24ba58db8894583c43567ea3ee",
        "## Історія версій",
        "## Абревіатури та глосарій",
    ]:
        assert marker in rep_txt, f"Report missing {marker!r}"

    log_files = list(RAW_EKPOL_DIR.glob("*.log"))
    assert len(log_files) >= 3
    for lf in log_files:
        head = lf.read_text(encoding="utf-8")[:500]
        assert "# cmd:" in head
        assert "# timestamp:" in head
        assert "# git_commit: a19bca2157ec1a6fd632b7bcd9b34654a96adea0" in head
        assert "# host:" in head

    wp_index = json.loads((REPO_ROOT / "Project" / "registers" / "wp-index.json").read_text(encoding="utf-8"))
    by_path = {e["path"]: e for e in wp_index["entries"]}
    assert by_path.get("Engineering/specifications/kpol/ekpol-specification-0.1.0.md", {}).get("wp_type") == "Specification"
    assert by_path.get("Engineering/validation/kpol-cme/ekpol-278/report.md", {}).get("wp_type") == "Report"
    assert by_path.get("Engineering/sw/kpol-ref/ekpol_frontend.py", {}).get("wp_type") == "Source Code"
    assert by_path.get("Engineering/sw/vmk-go/internal/vmk/ekpol.go", {}).get("wp_type") == "Source Code"
