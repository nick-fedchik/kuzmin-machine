#!/usr/bin/env python3
"""
Consolidated S5 Compiler Acceptance Verification Suite (Issue #8).

Covers the end-to-end KPOL compiler chain across all three supported contours
with honest evidence labels (`rtl_simulation`, `software_vm`, `negative_control`,
`mutant_control` per AGENTS.md §4.1–§4.4 — NOT physical FPGA HIL):

  1. KPOL-CME-1 (`compile_kpol_bram_image.py --profile KPOL-CME-1` +
     `compile_signed_bram_image` / `verify_bram_signature`):
     - Compilation of valid programs into 1024-byte `CME-RAW-1` images and
       1088-byte HMAC-SHA256 `Secure Boot` containers;
     - Bit-exact equivalence between `Interpreter` and `iverilog` RTL simulation
       of `kpol_bram_pipeline_axi.sv` (`CFG-P`);
     - Deterministic fail-closed rejection of out-of-profile constructs (`B3-*`)
       prior to file emission.

  2. KPOL-CME-2 (`compile_kpol_bram_image.py --profile KPOL-CME-2`):
     - Compilation of multi-concept 4-stage acyclic cascades (`C0 -> C1 -> C2 -> C3`
       and `C3 -> C2 -> C1 -> C0` targeting `CID 0`) into 1024-byte `CME-RAW-1`;
     - Bit-exact equivalence between `Interpreter`, single-bank RTL
       `kpol_bram_pipeline_axi.sv` (`CFG-P`), and dual-bank high-availability RTL
       `kpol_bram_pipeline_axi_ha.sv` (`CFG-P-HA`, including live shadow-bank rule
       hot-swap via `0x030..0x038`);
     - Deterministic rejection of operand collisions (`CME2-OPERAND-COLLISION`)
       and cycles/self-loops/fan-out (`CME2-CASCADE`) prior to file emission.

  3. KPOL-AUTH (`Engineering/sw/kpol-auth` CLI + `lowering.py`):
     - Compilation of the supported deterministic subset (`Concept` + `•` +
       `OnPositive` + `OnAbort`) via CLI into 1024-byte `CME-RAW-1` and 32-bit
       `Do/Go` bytecode (`code_o`), verified on `ReferenceDoGoVM`;
     - Deterministic rejection of self-loops (`C0 -> C0`), multi-node cycles
       (`A -> B -> A`), and rank violations (`dst_cid <= src_cid`) with
       `KPOL-LOWER-CYCLE` (the static DAG precondition of formal lemma `P2`);
     - Deterministic fail-closed rejection of all 12 open uncertainty points
       `KPOL-AUTH-U01..U12` (which remain open in Issue #186).

  4. Negative & Mutant Controls (AGENTS.md §4.1):
     - M1: Byte/bit corruption and nonce replay in `Secure Boot` container caught
       by `verify_bram_signature` without pre-auth nonce poisoning;
     - M2: Opcode (`INC -> DEC`) and threshold (`W1` / `guard_flags`) mutations
       in compiled 1024-byte `CME-RAW-1` images caught by `Interpreter <-> RTL`
       equivalence on both `kpol_bram_pipeline_axi.sv` and `kpol_bram_pipeline_axi_ha.sv`;
     - M3: `Do/Go` opcode (`ADD -> SUB`) and missing `KM_OPC_EXIT` mutations
       caught by `ReferenceDoGoVM`;
     - M4: Cyclic graph compilation blocked before file emission in both
       `KPOL-CME-2` and `KPOL-AUTH`, plus monkeypatch mutant controls proving
       cycle-gate tests fail when `_validate_bram_acyclic` is weakened;
     - M5: Monkeypatch mutant control proving `U01..U12` tests fail if
       `emit_uncertainty` silently suppresses diagnostics.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
from unittest import mock
import uuid

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HW_DIR = REPO_ROOT / "Engineering" / "hw"
SW_DIR = REPO_ROOT / "Engineering" / "sw"
KPOL_REF_DIR = SW_DIR / "kpol-ref"
KPOL_AUTH_DIR = SW_DIR / "kpol-auth"
COMPILE_CLI = HW_DIR / "scripts" / "compile_kpol_bram_image.py"
GOLDEN_CME1_BIN = KPOL_REF_DIR / "tests" / "fixtures" / "cme1_single_ca9dbb3.bin"
EXPECTED_GOLDEN_CME1_SHA256 = (
    "da1d69c5be5f52482ab39b9e549b5a736db7789f319a035494aa422f0a1835bb"
)
VALIDATION_DIR = REPO_ROOT / "Engineering" / "validation" / "kpol-cme" / "s5-compiler-8"
RAW_DIR = VALIDATION_DIR / "raw"
SUMMARY_JSON_PATH = RAW_DIR / "s5_acceptance_summary.json"
RUN_LOG_PATH = RAW_DIR / "s5_acceptance_run.log"

if str(KPOL_REF_DIR) not in sys.path:
    sys.path.insert(0, str(KPOL_REF_DIR))

import kpol_reference as kr  # noqa: E402
from kpol_reference import (  # noqa: E402
    EventInput,
    Interpreter,
    KpolError,
    compile_concept_microcode_bram_image,
    compile_signed_bram_image,
    parse_module,
    verify_bram_signature,
)


def _load_kpol_auth():
    if "kpol_auth" in sys.modules:
        return sys.modules["kpol_auth"]
    spec = importlib.util.spec_from_file_location(
        "kpol_auth",
        KPOL_AUTH_DIR / "__init__.py",
        submodule_search_locations=[str(KPOL_AUTH_DIR)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["kpol_auth"] = module
    spec.loader.exec_module(module)
    return module


def _load_kpol_auth_lowering_tests():
    spec = importlib.util.spec_from_file_location(
        "test_kpol_auth_lowering_mod",
        KPOL_AUTH_DIR / "tests" / "test_kpol_auth_lowering.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ka = _load_kpol_auth()
lowering_mod = sys.modules["kpol_auth.lowering"]
ka_lowering_tests = _load_kpol_auth_lowering_tests()
ReferenceDoGoVM = ka_lowering_tests.ReferenceDoGoVM
THERMAL_GRAPH_SOURCE = ka_lowering_tests.THERMAL_GRAPH_SOURCE


@contextmanager
def _workspace_scratch_dir(prefix: str = "s5_acc"):
    """Create a scratch directory inside the repository .pytest_cache (never /tmp)."""
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
        f"{KPOL_AUTH_DIR}{os.pathsep}{KPOL_REF_DIR}{os.pathsep}{existing_pp}"
        if existing_pp
        else f"{KPOL_AUTH_DIR}{os.pathsep}{KPOL_REF_DIR}"
    )
    return env


def _u32(val: int) -> int:
    return val & 0xFFFFFFFF


# --- KPOL-CME-1 & KPOL-CME-2 canonical programs ---

CME1_GOLDEN_SOURCE = """
Problem SingleCme1 { Invariants { Inv: S >= 0; } }
Solution SingleCme1 {
    state S: Int32 = 1;
    event E(p: Int32);
    rule R on E when p > 0 { set S := S + 1; }
}
Proof SingleCme1 { scenario Check { step E(p = 5); expect S == 2; } }
"""

CME2_CASCADE_4STAGE_SOURCE = """
Problem Cascade4Stage {
    Invariants {
        I0: C0 >= 0;
        I1: C1 >= 0;
        I2: C2 >= 0;
        I3: C3 >= 0;
    }
}
Solution Cascade4Stage {
    state C0: Int32 = 10;
    state C1: Int32 = 0;
    state C2: Int32 = 2;
    state C3: Int32 = 0;

    event E0(p0: Int32);

    rule R0 on E0 when p0 >= 10 and p0 <= 1000 { set C0 := C0 + 1; }
    rule R1 on change(C0) when C0 > 10 { set C1 := C1 + 1; }
    rule R2 on change(C1) when C1 >= 1 { set C2 := C2 - 1; }
    rule R3 on change(C2) when not (C2 == 2) { set C3 := C2; }
}
Proof Cascade4Stage {
    scenario FullCascadeAndUnderflow {
        step E0(p0 = 5);
        expect C0 == 10;
        expect C3 == 0;
        step E0(p0 = 25);
        expect C0 == 11;
        expect C1 == 1;
        expect C2 == 1;
        expect C3 == 1;
        step E0(p0 = 25);
        expect C2 == 0;
        expect C3 == 0;
        step E0(p0 = 25);
        expect C0 == 13;
        expect C1 == 3;
        expect C2 == 0;
    }
}
"""

CME2_CHAIN_TO_CID0_SOURCE = """
Problem ChainToCid0 {
    Invariants {
        I0: Digest0 >= 0;
        I1: Stage1 >= 0;
        I2: Stage2 >= 0;
        I3: Ingest3 >= 0;
    }
}
Solution ChainToCid0 {
    state Digest0: Int32 = 0;
    state Stage1: Int32 = 10;
    state Stage2: Int32 = 0;
    state Ingest3: Int32 = 0;

    event EvIngest(x: Int32);

    rule RIngest on EvIngest when true { set Ingest3 := Ingest3 + 5; }
    rule RStage2 on change(Ingest3) when Ingest3 >= 5 { set Stage2 := Stage2 + 1; }
    rule RStage1 on change(Stage2) when Stage2 > 0 { set Stage1 := Stage1 - 1; }
    rule RDigest0 on change(Stage1) when Stage1 < 10 { set Digest0 := Stage1; }
}
Proof ChainToCid0 {
    scenario CascadeIntoZero {
        step EvIngest(x = 1);
        expect Ingest3 == 5;
        expect Stage2 == 1;
        expect Stage1 == 9;
        expect Digest0 == 9;
    }
}
"""

AUTH_CASCADE_4STAGE_SOURCE = """
Concept(Sensor, 10)
Concept(Filter, 0, Lower=0, Upper=500)
Concept(Actuator, 0, Lower=0, Upper=1000)
Concept(FaultFlag, 0)
Sensor • Assign(Filter, (Sensor - 10) * 4)
OnPositive(Filter) • Assign(Actuator, Filter + 20)
OnAbort(Filter) • Assign(FaultFlag, 1)
"""


def _reference_execute_cme(
    module: kr.Module,
    profile: str,
    triggers: list[tuple[int, str, str, int]],
) -> dict:
    """Execute triggers through kpol_reference.Interpreter and compute expected 64 slots + telemetry."""
    image = compile_concept_microcode_bram_image(module, profile=profile)
    init_words = list(struct.unpack("<256I", image))
    interp = Interpreter(module)
    interp.run([])

    rules_by_target = {r.actions[0].name: r for r in module.rules}
    subscriber_of: dict[str, str] = {}
    for dst_name, r in rules_by_target.items():
        if r.event == "change":
            subscriber_of[r.watch[0]] = dst_name

    events_cnt = 0
    commits_cnt = 0
    rejects_cnt = 0
    last_state_u32 = 0

    for _cid, ev_name, param_name, param_val in triggers:
        prev_state = dict(interp.state)
        res = interp.run([EventInput(ev_name, {param_name: param_val})])
        events_cnt += res.steps
        cur_target = next(r.actions[0].name for r in module.rules if r.event == ev_name)
        env_cur = dict(prev_state)
        for hop in range(res.steps):
            rule = rules_by_target[cur_target]
            call_env = {**env_cur, param_name: param_val} if hop == 0 else dict(env_cur)
            g_ok = kr._eval(rule.guard, call_env) is True
            if not g_ok:
                rejects_cnt += 1
                break
            cand_val = kr._eval(rule.actions[0].expression, call_env)
            if cand_val < 0 or cand_val > 2147483647:
                rejects_cnt += 1
                break
            commits_cnt += 1
            last_state_u32 = _u32(cand_val)
            env_cur[cur_target] = cand_val
            if cur_target in subscriber_of:
                cur_target = subscriber_of[cur_target]
            else:
                break
        assert interp.state == env_cur

    slots = []
    state_names = [st.name for st in module.states]
    for cid in range(64):
        w0 = _u32(interp.state[state_names[cid]]) if cid < len(state_names) else 0
        w1, w2, w3 = init_words[cid * 4 + 1 : cid * 4 + 4]
        slots.append((w0, w1, w2, w3))

    return {
        "image": image,
        "slots": slots,
        "summary": {
            "events": events_cnt,
            "commits": commits_cnt,
            "rejects": rejects_cnt,
            "last_state": last_state_u32,
        },
    }


def _build_axi_rtl_sim(scratch_dir: Path, ha_mode: bool = False) -> Path:
    """Compile either single-bank kpol_bram_pipeline_axi.sv or dual-bank kpol_bram_pipeline_axi_ha.sv."""
    top_name = "s5_cfgp_ha_tb" if ha_mode else "s5_cfgp_tb"
    dut_inst = (
        """
    wire inject_strobe_o, bank_swap_commit_o, stimulus_accepted_o, reaction_out_o, seq_cycle_done_o;
    kpol_bram_pipeline_axi_ha dut (
        .clk(clk), .rst_n(rst_n),
        .awaddr(awaddr), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(4'hf), .wvalid(wvalid), .wready(wready),
        .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arvalid(arvalid), .arready(arready),
        .rdata(rdata), .rresp(rresp), .rvalid(rvalid), .rready(rready),
        .ext_hw_trigger_valid_i(ext_hw_trigger_valid_i),
        .ext_hw_trigger_cid_i(ext_hw_trigger_cid_i),
        .ext_hw_trigger_param_i(ext_hw_trigger_param_i),
        .hw_trigger_ready_o(hw_trigger_ready_o),
        .hw_commit_pulse_o(hw_commit_pulse_o),
        .hw_reject_pulse_o(hw_reject_pulse_o),
        .hw_pipeline_busy_o(), .fifo_overflow_o(), .events_dropped_count_o(),
        .hw_commit_cid_o(), .hw_last_committed_state_o(),
        .inject_strobe_o(inject_strobe_o),
        .bank_swap_commit_o(bank_swap_commit_o),
        .stimulus_accepted_o(stimulus_accepted_o),
        .reaction_out_o(reaction_out_o),
        .seq_cycle_done_o(seq_cycle_done_o),
        .busy(busy)
    );
"""
        if ha_mode
        else """
    kpol_bram_pipeline_axi dut (
        .clk(clk), .rst_n(rst_n),
        .awaddr(awaddr), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(4'hf), .wvalid(wvalid), .wready(wready),
        .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arvalid(arvalid), .arready(arready),
        .rdata(rdata), .rresp(rresp), .rvalid(rvalid), .rready(rready),
        .ext_hw_trigger_valid_i(ext_hw_trigger_valid_i),
        .ext_hw_trigger_cid_i(ext_hw_trigger_cid_i),
        .ext_hw_trigger_param_i(ext_hw_trigger_param_i),
        .hw_trigger_ready_o(hw_trigger_ready_o),
        .hw_commit_pulse_o(hw_commit_pulse_o),
        .hw_reject_pulse_o(hw_reject_pulse_o),
        .hw_pipeline_busy_o(), .fifo_overflow_o(), .events_dropped_count_o(),
        .hw_commit_cid_o(), .hw_last_committed_state_o(),
        .busy(busy)
    );
"""
    )

    ha_extra_read = (
        """
        begin
            logic [31:0] swap_cnt, swap_stat, seq_mon;
            axi_read(13'h038, swap_stat);
            axi_read(13'h03c, swap_cnt);
            axi_read(13'h044, seq_mon);
            $display("HA_TELEM swap_stat=%08x swap_count=%0d seq_mon=%08x", swap_stat, swap_cnt, seq_mon);
        end
"""
        if ha_mode
        else ""
    )

    tb_sv = scratch_dir / f"{top_name}.sv"
    tb_sv.write_text(
        f"""`timescale 1ns/1ps
module {top_name};
    logic clk = 0, rst_n = 0;
    always #5 clk = ~clk;

    logic [12:0] awaddr = 0, araddr = 0;
    logic awvalid = 0, wvalid = 0, bready = 0, arvalid = 0, rready = 0;
    logic [31:0] wdata = 0;
    wire awready, wready, bvalid, arready, rvalid, busy;
    wire [1:0] bresp, rresp;
    wire [31:0] rdata;
    logic ext_hw_trigger_valid_i = 0;
    logic [5:0] ext_hw_trigger_cid_i = 0;
    logic [31:0] ext_hw_trigger_param_i = 0;
    wire hw_trigger_ready_o, hw_commit_pulse_o, hw_reject_pulse_o;
{dut_inst}
    task automatic axi_write(input [12:0] addr, input [31:0] data);
        @(negedge clk);
        awaddr = addr; wdata = data; awvalid = 1; wvalid = 1; bready = 1;
        do @(posedge clk); while (!awready || !wready);
        @(negedge clk); awvalid = 0; wvalid = 0;
        while (!bvalid) @(negedge clk);
        if (bresp !== 2'b00) $fatal(1, "AXI write 0x%03h resp=%0d", addr, bresp);
        @(negedge clk); bready = 0;
    endtask

    task automatic axi_read(input [12:0] addr, output [31:0] data);
        @(negedge clk);
        araddr = addr; arvalid = 1; rready = 1;
        do @(posedge clk); while (!arready);
        @(negedge clk); arvalid = 0;
        while (!rvalid) @(negedge clk);
        if (rresp !== 2'b00) $fatal(1, "AXI read 0x%03h resp=%0d", addr, rresp);
        data = rdata;
        @(negedge clk); rready = 0;
    endtask

    reg [4095:0] image_hex_path, events_hex_path;
    logic [31:0] img [0:255];
    logic [31:0] event_words [0:511];
    int num_events;

    initial begin
        logic [31:0] ev_cnt, cm_cnt, rj_cnt, last_st;
        rst_n = 0;
        repeat (4) @(posedge clk);
        @(negedge clk); rst_n = 1;
        repeat (2) @(posedge clk);

        if (!$value$plusargs("image_hex=%s", image_hex_path)) $fatal(1, "no image_hex");
        if (!$value$plusargs("events_hex=%s", events_hex_path)) $fatal(1, "no events_hex");
        if (!$value$plusargs("num_events=%d", num_events)) num_events = 0;

        $readmemh(image_hex_path, img);
        for (int i = 0; i < 256; i++) begin
            axi_write(13'h004, i);
            axi_write(13'h008, img[i]);
        end

        $readmemh(events_hex_path, event_words);
        for (int e = 0; e < num_events; e++) begin
            logic [31:0] cmd_w, arg_w;
            int cyc, n_comm, n_rej;
            cmd_w = event_words[e * 2];
            arg_w = event_words[e * 2 + 1];
            if (cmd_w[31:24] == 8'h02) begin
                // Live shadow bank write + optional swap while busy or idle
                axi_write(13'h030, {{24'd0, cmd_w[7:0]}});
                axi_write(13'h034, arg_w);
                if (cmd_w[16]) begin
                    axi_write(13'h038, 32'd1);
                    // Wait for swap_pending and sync_busy (bits [2:1] of 0x038) to clear
                    begin
                        logic [31:0] st;
                        int wait_c;
                        wait_c = 0;
                        do begin
                            axi_read(13'h038, st);
                            wait_c++;
                            if (wait_c > 256) $fatal(1, "HA swap sync watchdog");
                        end while (st[2:1] != 2'b00);
                    end
                end
            end else begin
                cyc = 0; n_comm = 0; n_rej = 0;
                @(negedge clk);
                while (!hw_trigger_ready_o) @(negedge clk);
                ext_hw_trigger_cid_i = cmd_w[5:0];
                ext_hw_trigger_param_i = arg_w;
                ext_hw_trigger_valid_i = 1;
                @(posedge clk);
                @(negedge clk);
                ext_hw_trigger_valid_i = 0;
                while (busy) begin
                    @(posedge clk);
                    cyc++;
                    if (hw_commit_pulse_o) n_comm++;
                    if (hw_reject_pulse_o) n_rej++;
                    #1;
                    if (cyc > 1024) $fatal(1, "RTL watchdog");
                end
                $display("STEP %0d cycles=%0d commits=%0d rejects=%0d", e, cyc, n_comm, n_rej);
            end
        end

        for (int c = 0; c < 64; c++) begin
            logic [31:0] w0, w1, w2, w3;
            axi_write(13'h004, c * 4 + 0); axi_read(13'h008, w0);
            axi_write(13'h004, c * 4 + 1); axi_read(13'h008, w1);
            axi_write(13'h004, c * 4 + 2); axi_read(13'h008, w2);
            axi_write(13'h004, c * 4 + 3); axi_read(13'h008, w3);
            $display("SLOT %0d %08x %08x %08x %08x", c, w0, w1, w2, w3);
        end
        axi_read(13'h018, ev_cnt);
        axi_read(13'h01c, cm_cnt);
        axi_read(13'h020, rj_cnt);
        axi_read(13'h024, last_st);
        $display("SUMMARY events=%0d commits=%0d rejects=%0d last_state=%08x",
                 ev_cnt, cm_cnt, rj_cnt, last_st);
{ha_extra_read}
        $finish;
    end
endmodule
""",
        encoding="utf-8",
    )

    vvp_out = scratch_dir / f"{top_name}.vvp"
    rtl_files = [
        HW_DIR / "rtl" / "core" / "kpol_txn_gate_v2.sv",
        HW_DIR / "rtl" / "core" / "km_concept_micro_engine.sv",
        HW_DIR / "rtl" / "core" / "km_concept_bram.sv",
        HW_DIR / "rtl" / "core" / "km_autonomous_sequencer.sv",
    ]
    if ha_mode:
        rtl_files.extend([
            HW_DIR / "rtl" / "core" / "km_concept_bram_dual_ha.sv",
            HW_DIR / "rtl" / "bus" / "kpol_bram_pipeline_axi_ha.sv",
        ])
    else:
        rtl_files.append(HW_DIR / "rtl" / "bus" / "kpol_bram_pipeline_axi.sv")

    subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-s",
            top_name,
            "-o",
            str(vvp_out),
            *map(str, rtl_files),
            str(tb_sv),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=_subproc_env(scratch_dir),
    )
    return vvp_out


def _run_axi_rtl_trace(
    vvp_bin: Path,
    scratch_dir: Path,
    image_bytes: bytes,
    ops: list[tuple[str, int, int]],
    tag: str,
) -> dict:
    words = struct.unpack("<256I", image_bytes)
    img_hex = scratch_dir / f"{tag}_img.hex"
    img_hex.write_text("".join(f"{w:08x}\n" for w in words), encoding="utf-8")

    ev_lines = []
    for kind, a, b in ops:
        if kind == "trig":
            cmd_w = a & 0x3F
        elif kind == "shadow_write":
            cmd_w = (0x02 << 24) | (a & 0xFF)
        elif kind == "shadow_write_and_swap":
            cmd_w = (0x02 << 24) | (1 << 16) | (a & 0xFF)
        else:
            raise ValueError(f"Unknown op kind: {kind}")
        ev_lines.append(f"{_u32(cmd_w):08x} {_u32(b):08x}\n")
    ev_hex = scratch_dir / f"{tag}_ev.hex"
    ev_hex.write_text("".join(ev_lines), encoding="utf-8")

    res = subprocess.run(
        [
            "vvp",
            "-n",
            str(vvp_bin),
            f"+image_hex={img_hex}",
            f"+events_hex={ev_hex}",
            f"+num_events={len(ops)}",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env=_subproc_env(scratch_dir),
    )

    slots: list[tuple[int, int, int, int]] = []
    summary: dict[str, int] = {}
    ha_telem: dict[str, int] = {}
    for line in res.stdout.splitlines():
        if line.startswith("SLOT "):
            parts = line.split()
            slots.append((
                int(parts[2], 16),
                int(parts[3], 16),
                int(parts[4], 16),
                int(parts[5], 16),
            ))
        elif line.startswith("SUMMARY "):
            for kv in line.split()[1:]:
                k, v = kv.split("=")
                summary[k] = int(v, 16) if k == "last_state" else int(v, 10)
        elif line.startswith("HA_TELEM "):
            for kv in line.split()[1:]:
                k, v = kv.split("=")
                ha_telem[k] = int(v, 10) if k == "swap_count" else int(v, 16)

    assert len(slots) == 64
    return {"slots": slots, "summary": summary, "ha_telem": ha_telem}


@pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Requires iverilog and vvp for RTL simulation",
)
def test_s5_kpol_cme1_cli_secure_boot_and_rtl_simulation_equivalence():
    """
    Contour 1 (KPOL-CME-1, [rtl_simulation]):
    CLI compilation into 1024-byte CME-RAW-1, golden byte-identity, Secure Boot
    1088-byte HMAC-SHA256 signing/verification, Interpreter <-> kpol_bram_pipeline_axi.sv
    equivalence, and deterministic B3-* rejection before file emission.
    """
    with _workspace_scratch_dir("s5_cme1") as scratch:
        env = _subproc_env(scratch)
        vvp_cfgp = _build_axi_rtl_sim(scratch, ha_mode=False)

        # 1. Golden fixture byte-identity & default --profile == KPOL-CME-1
        golden_src = scratch / "golden_cme1.kpol"
        golden_src.write_text(CME1_GOLDEN_SOURCE, encoding="utf-8")
        out_default = scratch / "golden_default.bin"
        out_explicit = scratch / "golden_explicit.bin"

        subprocess.run(
            [sys.executable, str(COMPILE_CLI), str(golden_src), str(out_default)],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        subprocess.run(
            [
                sys.executable,
                str(COMPILE_CLI),
                "--profile",
                "KPOL-CME-1",
                str(golden_src),
                str(out_explicit),
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        img_default = out_default.read_bytes()
        img_explicit = out_explicit.read_bytes()
        assert len(img_default) == 1024
        assert img_default == img_explicit
        assert img_default == GOLDEN_CME1_BIN.read_bytes()
        assert hashlib.sha256(img_default).hexdigest() == EXPECTED_GOLDEN_CME1_SHA256

        # 2. Secure Boot HMAC-SHA256 signing & verification on compiled CME-RAW-1
        secret_key = b"S5-KPOL-CME1-SECRET-KEY-32BYTES!"
        seen_nonces: set[bytes] = set()
        signed_container = compile_signed_bram_image(img_explicit, secret_key, key_id=7)
        assert len(signed_container) == 1088
        assert signed_container[64:1088] == img_explicit
        ok, msg = verify_bram_signature(signed_container, secret_key, seen_nonces=seen_nonces)
        assert ok is True and "Valid signature" in msg
        assert len(seen_nonces) == 1

        # 3. Interpreter <-> kpol_bram_pipeline_axi.sv bit-exact equivalence
        for name in ("increase", "decrease"):
            src_path = HW_DIR / "tests" / f"kpol_bram_pipeline_{name}.kpol"
            bin_path = scratch / f"{name}.bin"
            subprocess.run(
                [
                    sys.executable,
                    str(COMPILE_CLI),
                    "--profile",
                    "KPOL-CME-1",
                    str(src_path),
                    str(bin_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            mod = parse_module(src_path.read_text(encoding="utf-8"))
            triggers = [
                (0, "Pulse", "param", 5),
                (0, "Pulse", "param", 25),
                (0, "Pulse", "param", 10),
                (0, "Pulse", "param", 100),
            ]
            ref = _reference_execute_cme(mod, "KPOL-CME-1", triggers)
            assert bin_path.read_bytes() == ref["image"]
            rtl_ops = [("trig", cid, pval) for cid, _, _, pval in triggers]
            rtl = _run_axi_rtl_trace(vvp_cfgp, scratch, ref["image"], rtl_ops, f"cme1_{name}")
            assert rtl["slots"] == ref["slots"]
            assert rtl["summary"] == ref["summary"]

        # 4. Deterministic B3-* rejection before file emission
        b3_negative_cases = [
            (
                "b3_syntax.kpol",
                "Problem P { Invariants { I: S >= 0; } } Solution P { state S: Int32 = 0 ",
                "B3-SYNTAX",
            ),
            (
                "b3_type.kpol",
                """
                Problem P { Invariants { I: S >= 0; } }
                Solution P {
                    state S: Bool = true;
                    event E(x: Int32);
                    rule R on E when true { set S := true; }
                }
                """,
                "B3-TYPE",
            ),
            (
                "b3_guard_range.kpol",
                """
                Problem P { Invariants { I: S >= 0; } }
                Solution P {
                    state S: Int32 = 0;
                    event E(x: Int32);
                    rule R on E when x >= 1 and x <= 10 { set S := S + 1; }
                }
                """,
                "B3-GUARD",
            ),
            (
                "b3_action_add5.kpol",
                """
                Problem P { Invariants { I: S >= 0; } }
                Solution P {
                    state S: Int32 = 0;
                    event E(x: Int32);
                    rule R on E when x > 0 { set S := S + 5; }
                }
                """,
                "B3-ACTION",
            ),
            (
                "b3_proof_fail.kpol",
                """
                Problem P { Invariants { I: S >= 0; } }
                Solution P {
                    state S: Int32 = 0;
                    event E(x: Int32);
                    rule R on E when x > 0 { set S := S + 1; }
                }
                Proof P {
                    scenario Wrong {
                        step E(x = 5);
                        expect S == 99;
                    }
                }
                """,
                "B3-PROOF",
            ),
        ]
        for fname, bad_text, expected_code in b3_negative_cases:
            bad_src = scratch / fname
            bad_out = scratch / f"{fname}.bin"
            bad_src.write_text(bad_text, encoding="utf-8")
            res = subprocess.run(
                [
                    sys.executable,
                    str(COMPILE_CLI),
                    "--profile",
                    "KPOL-CME-1",
                    str(bad_src),
                    str(bad_out),
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            assert res.returncode != 0
            assert expected_code in res.stderr
            assert not bad_out.exists(), f"Output file {bad_out} must not exist on {expected_code}"


@pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Requires iverilog and vvp for RTL simulation",
)
def test_s5_kpol_cme2_cascade_rtl_simulation_cfg_p_and_cfg_p_ha_equivalence():
    """
    Contour 2 (KPOL-CME-2, [rtl_simulation]):
    Multi-concept 4-stage acyclic cascade compilation into 1024-byte CME-RAW-1,
    bit-exact equivalence between Interpreter, single-bank kpol_bram_pipeline_axi.sv (CFG-P),
    and dual-bank kpol_bram_pipeline_axi_ha.sv (CFG-P-HA, including live shadow-bank swap),
    plus deterministic rejection of CME2-OPERAND-COLLISION and CME2-CASCADE.
    """
    with _workspace_scratch_dir("s5_cme2") as scratch:
        env = _subproc_env(scratch)
        vvp_cfgp = _build_axi_rtl_sim(scratch, ha_mode=False)
        vvp_cfgp_ha = _build_axi_rtl_sim(scratch, ha_mode=True)

        # 1. 4-stage acyclic cascade (C0 -> C1 -> C2 -> C3) + Chain4 into CID 0
        cme2_programs = [
            (
                "cascade4",
                CME2_CASCADE_4STAGE_SOURCE,
                [
                    (0, "E0", "p0", 5),     # rejected at C0 guard (p0 < 10)
                    (0, "E0", "p0", 25),    # full 4-hop cascade C0->C1->C2->C3 (4 commits)
                    (0, "E0", "p0", 1500),  # rejected at C0 guard (p0 > 1000)
                    (0, "E0", "p0", 100),   # full 4-hop cascade (C2 reaches 0)
                    (0, "E0", "p0", 50),    # mid-cascade invariant reject at C2 (0 - 1 < 0)
                ],
            ),
            (
                "chain_cid0",
                CME2_CHAIN_TO_CID0_SOURCE,
                [
                    (3, "EvIngest", "x", 1),
                    (3, "EvIngest", "x", 2),
                ],
            ),
        ]

        for tag, src_text, triggers in cme2_programs:
            src_path = scratch / f"{tag}.kpol"
            bin_path = scratch / f"{tag}.bin"
            src_path.write_text(src_text, encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(COMPILE_CLI),
                    "--profile",
                    "KPOL-CME-2",
                    str(src_path),
                    str(bin_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            mod = parse_module(src_text)
            ref = _reference_execute_cme(mod, "KPOL-CME-2", triggers)
            assert bin_path.read_bytes() == ref["image"]
            assert len(ref["image"]) == 1024

            rtl_ops = [("trig", cid, pval) for cid, _, _, pval in triggers]
            rtl_single = _run_axi_rtl_trace(vvp_cfgp, scratch, ref["image"], rtl_ops, f"{tag}_single")
            rtl_dual_ha = _run_axi_rtl_trace(vvp_cfgp_ha, scratch, ref["image"], rtl_ops, f"{tag}_ha")

            assert rtl_single["slots"] == ref["slots"]
            assert rtl_single["summary"] == ref["summary"]
            assert rtl_dual_ha["slots"] == ref["slots"]
            assert rtl_dual_ha["summary"] == ref["summary"]
            assert rtl_dual_ha["ha_telem"]["seq_mon"] == 8  # 0 anomalies, 8 cycles/event

        # 2. Live shadow-bank hot update on kpol_bram_pipeline_axi_ha.sv (0x030..0x038)
        # Start with Cascade4Stage (C0 requires p0 in [10, 1000]), then hot-swap C0 W1..W2
        # in shadow bank to accept any p0 >= 0 (W1 = 0, W2 = LT inverted 0x01001b04) and swap!
        mod_c4 = parse_module(CME2_CASCADE_4STAGE_SOURCE)
        img_c4 = compile_concept_microcode_bram_image(mod_c4, profile="KPOL-CME-2")
        ha_hot_ops = [
            ("trig", 0, 5),  # rejected under initial rule [10, 1000]
            # Hot-inject new rule for CID 0 (word 1 = 0, word 2 = 0x01001b04: INC + SUBSCRIBER_EN + INVERT + LT)
            ("shadow_write", 1, 0),
            ("shadow_write_and_swap", 2, 0x01001B04),
            ("trig", 0, 5),  # now accepted under hot-swapped rule (p0=5 >= 0) -> 4-stage cascade!
        ]
        rtl_ha_hot = _run_axi_rtl_trace(vvp_cfgp_ha, scratch, img_c4, ha_hot_ops, "c4_hot_swap")
        assert rtl_ha_hot["ha_telem"]["swap_count"] == 1
        assert (rtl_ha_hot["ha_telem"]["swap_stat"] & 0xF) == 1  # active_bank == 1, 0 collisions
        assert rtl_ha_hot["ha_telem"]["seq_mon"] == 8  # 0 stall/anomaly cycles
        assert rtl_ha_hot["summary"]["commits"] == 4
        assert rtl_ha_hot["summary"]["rejects"] == 1
        assert [rtl_ha_hot["slots"][i][0] for i in range(4)] == [11, 1, 1, 1]

        # 3. Deterministic CME2-* fail-closed rejections before file emission
        cme2_negative_cases = [
            (
                "cme2_collision.kpol",
                """
                Problem Coll { Invariants { I0: S0 >= 0; } }
                Solution Coll {
                    state S0: Int32 = 0;
                    event E0(x: Int32);
                    rule R0 on E0 when x > 10 { set S0 := S0 + 5; }
                }
                """,
                "CME2-OPERAND-COLLISION",
            ),
            (
                "cme2_cycle_2node.kpol",
                """
                Problem Cyc2 { Invariants { I0: A >= 0; I1: B >= 0; I2: T >= 0; } }
                Solution Cyc2 {
                    state A: Int32 = 0;
                    state B: Int32 = 0;
                    state T: Int32 = 0;
                    event E0(x: Int32);
                    rule RT on E0 when true { set T := T + 1; }
                    rule RA on change(B) when B > 0 { set A := A + 1; }
                    rule RB on change(A) when A > 0 { set B := B + 1; }
                }
                """,
                "CME2-CASCADE",
            ),
            (
                "cme2_self_loop.kpol",
                """
                Problem CycSelf { Invariants { I0: A >= 0; I1: T >= 0; } }
                Solution CycSelf {
                    state A: Int32 = 0;
                    state T: Int32 = 0;
                    event E0(x: Int32);
                    rule RT on E0 when true { set T := T + 1; }
                    rule RA on change(A) when A > 0 { set A := A + 1; }
                }
                """,
                "CME2-CASCADE",
            ),
            (
                "cme2_fanout2.kpol",
                """
                Problem Fan2 { Invariants { I0: A >= 0; I1: B >= 0; I2: C >= 0; } }
                Solution Fan2 {
                    state A: Int32 = 0;
                    state B: Int32 = 0;
                    state C: Int32 = 0;
                    event E0(x: Int32);
                    rule RA on E0 when true { set A := A + 1; }
                    rule RB on change(A) when A > 0 { set B := B + 1; }
                    rule RC on change(A) when A > 0 { set C := C + 1; }
                }
                """,
                "CME2-CASCADE",
            ),
        ]
        for fname, bad_text, expected_code in cme2_negative_cases:
            bad_src = scratch / fname
            bad_out = scratch / f"{fname}.bin"
            bad_src.write_text(bad_text, encoding="utf-8")
            res = subprocess.run(
                [
                    sys.executable,
                    str(COMPILE_CLI),
                    "--profile",
                    "KPOL-CME-2",
                    str(bad_src),
                    str(bad_out),
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            assert res.returncode != 0
            assert expected_code in res.stderr
            assert not bad_out.exists(), f"Output file {bad_out} must not exist on {expected_code}"


def test_s5_kpol_auth_cli_dogo_vm_and_uncertainty_gates():
    """
    Contour 3 (KPOL-AUTH, [software_vm] + [negative_control]):
    CLI compilation of supported subset (`Concept` + `•` + `OnPositive` + `OnAbort`)
    into 1024-byte CME-RAW-1 and 32-bit Do/Go bytecode, execution on ReferenceDoGoVM,
    rejection of self-loops/cycles (`KPOL-LOWER-CYCLE` — precondition of formal lemma P2),
    and deterministic fail-closed rejection of all 12 uncertainty gates `KPOL-AUTH-U01..U12`.
    """
    with _workspace_scratch_dir("s5_auth") as scratch:
        env = _subproc_env(scratch)

        # 1. Compile THERMAL_GRAPH_SOURCE and AUTH_CASCADE_4STAGE_SOURCE via CLI
        for name, src_text in (
            ("thermal", THERMAL_GRAPH_SOURCE),
            ("cascade4_auth", AUTH_CASCADE_4STAGE_SOURCE),
        ):
            src_file = scratch / f"{name}.kpol"
            bram_file = scratch / f"{name}.bram.bin"
            dogo_json = scratch / f"{name}.dogo.json"
            dogo_bin = scratch / f"{name}.dogo.bin"
            src_file.write_text(src_text, encoding="utf-8")

            res = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "kpol_auth",
                    str(src_file),
                    "--check",
                    "--emit-bram",
                    str(bram_file),
                    "--emit-dogo",
                    str(dogo_json),
                ],
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            assert "OK:" in res.stdout
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "kpol_auth",
                    str(src_file),
                    "--emit-dogo",
                    str(dogo_bin),
                ],
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )

            artifact = ka.lower_document(src_text)
            assert bram_file.read_bytes() == artifact.bram_image
            assert len(artifact.bram_image) == 1024
            payload = json.loads(dogo_json.read_text(encoding="utf-8"))
            assert payload["code_o"] == list(artifact.code_o)
            assert dogo_bin.read_bytes() == b"".join(
                struct.pack("<I", w) for w in artifact.code_o
            )

        # 2. Execute lowered programs on ReferenceDoGoVM
        thermal_art = ka.lower_document(THERMAL_GRAPH_SOURCE)
        vm_th = ReferenceDoGoVM(thermal_art)
        vm_th.trigger_external(0, 25)
        assert vm_th.val_cur == [25, 50, 50, 0]
        assert vm_th.big_dot_ok[1] == 0
        vm_th.trigger_external(0, 45)
        assert vm_th.val_cur == [45, 50, 100, 1]
        assert vm_th.big_dot_ok[1] == 1

        c4_art = ka.lower_document(AUTH_CASCADE_4STAGE_SOURCE)
        vm_c4 = ReferenceDoGoVM(c4_art)
        vm_c4.trigger_external(0, 30)  # Filter = (30-10)*4 = 80 > 0 -> Actuator = 100
        assert vm_c4.val_cur == [30, 80, 100, 0]
        assert vm_c4.big_dot_ok[1] == 0
        vm_c4.trigger_external(0, 200)  # Filter = 760 > Upper=500 -> OnAbort -> FaultFlag = 1
        assert vm_c4.val_cur == [200, 80, 100, 1]
        assert vm_c4.big_dot_ok[1] == 1

        # 3. Reject self-loops, 2-node cycles, and rank violations (dst_cid <= src_cid) with KPOL-LOWER-CYCLE
        cycle_cases = [
            "Concept(C0, 1)\nC0 • Assign(C0, C0 + 1)\n",
            "Concept(A, 0)\nConcept(B, 0)\nA • Assign(B, A + 1)\nB • Assign(A, B + 1)\n",
            "Concept(A, 0)\nConcept(B, 0)\nB • Assign(A, B + 1)\n",
        ]
        for idx, cyc_src in enumerate(cycle_cases):
            c_in = scratch / f"cyc_{idx}.kpol"
            c_bram = scratch / f"cyc_{idx}.bram.bin"
            c_in.write_text(cyc_src, encoding="utf-8")
            res_cyc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "kpol_auth",
                    str(c_in),
                    "--emit-bram",
                    str(c_bram),
                ],
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
            )
            assert res_cyc.returncode == 3
            assert "KPOL-LOWER-CYCLE" in res_cyc.stderr
            assert not c_bram.exists()

        # 4. All 12 uncertainty gates KPOL-AUTH-U01..U12 rejected fail-closed
        expected_u_codes = {f"KPOL-AUTH-U{i:02d}" for i in range(1, 13)}
        assert set(ka.UNCERTAINTY_REGISTRY.keys()) == expected_u_codes
        observed_u_codes: set[str] = set()
        for ex in ka.AUTHOR_CORPUS:
            if not ex.in_source_scope:
                with pytest.raises(ka.KpolAuthError) as exc_info:
                    ka.parse_kpol_auth(ex.source_text)
                code = exc_info.value.diagnostic.code
                assert code in ex.expected_diagnostics
                observed_u_codes.add(code)
        assert observed_u_codes == expected_u_codes


@pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Requires iverilog and vvp for RTL simulation",
)
def test_s5_negative_and_mutant_controls_hmac_rtl_vm_and_cycles():
    """
    Part 4 (Negative & Mutant Controls per AGENTS.md §4.1, [mutant_control]):
    - M1: Byte/bit corruption in BRAM image / HMAC tag caught by `verify_bram_signature`;
    - M2: Opcode (`INC -> DEC`) and threshold (`W1` / `guard_flags`) mutations in BRAM
          image caught by `Interpreter <-> RTL` equivalence (`CFG-P` and `CFG-P-HA`);
    - M3: `Do/Go` bytecode mutations (`ADD -> SUB`, missing `EXIT`) caught by `ReferenceDoGoVM`;
    - M4: Weakened `_validate_bram_acyclic` mutants caught by cycle/self-loop tests;
    - M5: Weakened `emit_uncertainty` mutant caught by `U01..U12` gate tests.
    """
    with _workspace_scratch_dir("s5_mutants") as scratch:
        vvp_cfgp = _build_axi_rtl_sim(scratch, ha_mode=False)
        vvp_cfgp_ha = _build_axi_rtl_sim(scratch, ha_mode=True)

        # --- Mutant M1: Secure Boot HMAC byte corruption & replay ---
        mod_c4 = parse_module(CME2_CASCADE_4STAGE_SOURCE)
        raw_c4 = compile_concept_microcode_bram_image(mod_c4, profile="KPOL-CME-2")
        key = b"S5-MUTANT-TEST-HMAC-SECRET-KEY32"
        seen: set[bytes] = set()
        signed = compile_signed_bram_image(raw_c4, key, key_id=3)

        # Corrupt bytes in header (nonce offset 20), HMAC tag (offset 40), and BRAM payload (offset 64, 512, 1087)
        for corrupt_offset in (20, 40, 64, 512, 1087):
            tampered = bytearray(signed)
            tampered[corrupt_offset] ^= 0x01
            ok, reason = verify_bram_signature(bytes(tampered), key, seen_nonces=seen)
            assert ok is False
            assert "mismatch" in reason
            assert len(seen) == 0, "Pre-auth tampering must not poison seen_nonces"

        # Valid signature succeeds once, replay with same nonce is rejected
        ok1, _ = verify_bram_signature(signed, key, seen_nonces=seen)
        assert ok1 is True
        ok_replay, reason_replay = verify_bram_signature(signed, key, seen_nonces=seen)
        assert ok_replay is False
        assert "Replay" in reason_replay

        # --- Mutant M2: BRAM opcode & threshold mutations caught by Interpreter <-> RTL ---
        triggers = [(0, "E0", "p0", 25)]
        ref = _reference_execute_cme(mod_c4, "KPOL-CME-2", triggers)
        rtl_ops = [("trig", 0, 25)]

        # M2a: Mutate C0 action_opcode in W2[31:24] from INC (0x01) to DEC (0x02)
        mut_opcode_img = bytearray(raw_c4)
        assert mut_opcode_img[11] == 0x01  # CID 0, W2 byte 3 = action_opcode INC
        mut_opcode_img[11] = 0x02          # Mutate to DEC (10 - 1 = 9 -> C1 guard C0 > 10 rejects!)
        for vvp in (vvp_cfgp, vvp_cfgp_ha):
            rtl_m2a = _run_axi_rtl_trace(vvp, scratch, bytes(mut_opcode_img), rtl_ops, "m2a_opc")
            assert rtl_m2a["slots"] != ref["slots"], "Mutant M2a (INC->DEC) must diverge from Interpreter"
            assert [ref["slots"][i][0] for i in range(4)] == [11, 1, 1, 1]
            assert [rtl_m2a["slots"][i][0] for i in range(4)] == [9, 0, 2, 0]
            assert rtl_m2a["summary"]["commits"] == 1 and rtl_m2a["summary"]["rejects"] == 1

        # M2b: Mutate C1 threshold in W1 (offset 16 + 4 = 20) from GT 10 to GT 50
        mut_thresh_img = bytearray(raw_c4)
        assert struct.unpack_from("<i", mut_thresh_img, 20)[0] == 10
        struct.pack_into("<i", mut_thresh_img, 20, 50)
        for vvp in (vvp_cfgp, vvp_cfgp_ha):
            rtl_m2b = _run_axi_rtl_trace(vvp, scratch, bytes(mut_thresh_img), rtl_ops, "m2b_thr")
            assert rtl_m2b["slots"] != ref["slots"], "Mutant M2b (threshold 10->50) must diverge from Interpreter"
            assert [rtl_m2b["slots"][i][0] for i in range(4)] == [11, 0, 2, 0]
            assert rtl_m2b["summary"]["commits"] == 1 and rtl_m2b["summary"]["rejects"] == 1
            assert ref["summary"]["commits"] == 4 and ref["summary"]["rejects"] == 0

        # --- Mutant M3: Do/Go bytecode mutations caught by ReferenceDoGoVM ---
        auth_art = ka.lower_document(THERMAL_GRAPH_SOURCE)
        add_word = lowering_mod.km_pack_instr(lowering_mod.KM_OPC_DO, lowering_mod.KM_DO_ADD, 0, 0)
        sub_word = lowering_mod.km_pack_instr(lowering_mod.KM_OPC_DO, lowering_mod.KM_DO_SUB, 0, 0)
        corrupted_code = list(auth_art.code_o)
        corrupted_code[corrupted_code.index(add_word)] = sub_word
        vm_m3a = ReferenceDoGoVM(replace(auth_art, code_o=tuple(corrupted_code)))
        vm_m3a.trigger_external(0, 25)
        # With ADD->SUB: 25 - ((25 - 20) * 5) = 0 < Lower=10 -> Heater aborts (retains 10),
        # sets big_dot_ok[1]=1, and triggers OnAbort(Heater) -> Alarm=1, Fan=100
        assert vm_m3a.val_cur != [25, 50, 50, 0], "Mutant M3a (ADD->SUB) must diverge on ReferenceDoGoVM"
        assert vm_m3a.val_cur == [25, 10, 100, 1]
        assert vm_m3a.big_dot_ok == [0, 1, 0, 0]

        exit_word = lowering_mod.km_pack_instr(lowering_mod.KM_OPC_EXIT, 0, 0, 0)
        no_exit_code = list(auth_art.code_o)
        no_exit_code[no_exit_code.index(exit_word)] = lowering_mod.km_pack_instr(
            lowering_mod.KM_OPC_NOP, 0, 0, 0
        )
        vm_m3b = ReferenceDoGoVM(replace(auth_art, code_o=tuple(no_exit_code)))
        with pytest.raises(AssertionError, match="Unexpected opcode 0x0|missing KM_OPC_EXIT"):
            vm_m3b.trigger_external(0, 25)

        # --- Mutant M4: Partial / weakened cycle validator mutants in KPOL-AUTH ---
        self_loop_ast = ka.parse_kpol_auth("Concept(C0, 1)\nC0 • Assign(C0, C0 + 1)")
        two_node_cycle_ast = ka.parse_kpol_auth(
            "Concept(A, 0)\nConcept(B, 0)\nA • Assign(B, A + 1)\nB • Assign(A, B + 1)"
        )

        # M4a: Weakened validator checks only distinct 2-node cycles (u != v) and misses self-loop u == v
        def _defective_no_self_loop_check(edges):
            edge_set = set(edges)
            for u, v in edges:
                if u != v and (v, u) in edge_set:
                    raise ka.KpolAuthLoweringError("KPOL-LOWER-CYCLE", "2-node cycle only")

        with mock.patch.object(lowering_mod, "_validate_bram_acyclic", _defective_no_self_loop_check):
            # Still catches 2-node cycle A <-> B, but lets self-loop C0 -> C0 slip through
            with pytest.raises(ka.KpolAuthLoweringError) as ctx_2node_ok:
                ka.lower_document(two_node_cycle_ast)
            assert ctx_2node_ok.value.code == "KPOL-LOWER-CYCLE"
            slipped_self = ka.lower_document(self_loop_ast)
            assert struct.unpack("<4I", slipped_self.bram_image[0:16])[3] == 0

        # M4b: Weakened validator checks only self-loops (u == v) and misses 2-node cycle A <-> B
        def _defective_self_loop_only_check(edges):
            for u, v in edges:
                if u == v:
                    raise ka.KpolAuthLoweringError("KPOL-LOWER-CYCLE", "self-loop only")

        with mock.patch.object(lowering_mod, "_validate_bram_acyclic", _defective_self_loop_only_check):
            with pytest.raises(ka.KpolAuthLoweringError) as ctx_self_ok:
                ka.lower_document(self_loop_ast)
            assert ctx_self_ok.value.code == "KPOL-LOWER-CYCLE"
            slipped_2node = ka.lower_document(two_node_cycle_ast)
            assert struct.unpack("<4I", slipped_2node.bram_image[0:16])[3] == 1
            assert struct.unpack("<4I", slipped_2node.bram_image[16:32])[3] == 0

        for cyc_ast in (self_loop_ast, two_node_cycle_ast):
            with pytest.raises(ka.KpolAuthLoweringError) as ctx_real:
                ka.lower_document(cyc_ast)
            assert ctx_real.value.code == "KPOL-LOWER-CYCLE"

        # --- Mutant M5: Selective uncertainty policy weakening (record-diagnostic) vs fail-closed ---
        uninit_expr_src = "Concept(A, 1)\nConcept(B, 2)\nA • Assign(B, _ + A)"
        # Default fail-closed configuration blocks U10 in frontend parser
        with pytest.raises(ka.KpolAuthError) as ctx_u10_default:
            ka.parse_kpol_auth(uninit_expr_src)
        assert ctx_u10_default.value.diagnostic.code == "KPOL-AUTH-U10"

        # Weakening only U10 policy in AuthFrontendConfig allows parse_kpol_auth to succeed with
        # a recorded diagnostic while keeping U01..U09, U11..U12 fail-closed:
        weak_cfg = ka.AuthFrontendConfig(policies={"KPOL-AUTH-U10": "record-diagnostic"})
        with pytest.raises(ka.KpolAuthError) as ctx_u05_still_closed:
            ka.parse_kpol_auth("#legacy_comment", config=weak_cfg)
        assert ctx_u05_still_closed.value.diagnostic.code == "KPOL-AUTH-U05"

        prog_u10_recorded = ka.parse_kpol_auth(uninit_expr_src, config=weak_cfg)
        assert [d.code for d in prog_u10_recorded.diagnostics] == ["KPOL-AUTH-U10"]
        # Second-stage defense: lower_kpol_auth blocks recorded diagnostics with KPOL-LOWER-UNCERTAINTY
        with pytest.raises(ka.KpolAuthLoweringError) as ctx_lower_u10:
            ka.lower_kpol_auth(prog_u10_recorded)
        assert ctx_lower_u10.value.code == "KPOL-LOWER-UNCERTAINTY"
        # And if the diagnostics list is stripped, _emit_expr still rejects UninitCST:
        with pytest.raises(ka.KpolAuthLoweringError) as ctx_lower_cst:
            ka.lower_kpol_auth(replace(prog_u10_recorded, diagnostics=()))
        assert ctx_lower_cst.value.code == "KPOL-LOWER-UNSUPPORTED-CST"


def generate_acceptance_summary() -> dict:
    """Compute deterministic summary metrics and artifact hashes for S5 acceptance report."""
    inc_src = (HW_DIR / "tests" / "kpol_bram_pipeline_increase.kpol").read_text(encoding="utf-8")
    dec_src = (HW_DIR / "tests" / "kpol_bram_pipeline_decrease.kpol").read_text(encoding="utf-8")
    img_inc = compile_concept_microcode_bram_image(parse_module(inc_src), profile="KPOL-CME-1")
    img_dec = compile_concept_microcode_bram_image(parse_module(dec_src), profile="KPOL-CME-1")
    img_c4 = compile_concept_microcode_bram_image(
        parse_module(CME2_CASCADE_4STAGE_SOURCE), profile="KPOL-CME-2"
    )
    img_cid0 = compile_concept_microcode_bram_image(
        parse_module(CME2_CHAIN_TO_CID0_SOURCE), profile="KPOL-CME-2"
    )
    auth_thermal = ka.lower_document(THERMAL_GRAPH_SOURCE)
    auth_c4 = ka.lower_document(AUTH_CASCADE_4STAGE_SOURCE)

    return {
        "issue": 8,
        "step": "S5",
        "date": "2026-11-17",
        "evidence_kind": "host_compiler_and_iverilog_rtl_simulation_not_physical_hil",
        "contours": {
            "KPOL-CME-1": {
                "profile": "KPOL-CME-1",
                "bram_bytes": 1024,
                "signed_container_bytes": 1088,
                "golden_cme1_sha256": hashlib.sha256(GOLDEN_CME1_BIN.read_bytes()).hexdigest(),
                "increase_bram_sha256": hashlib.sha256(img_inc).hexdigest(),
                "decrease_bram_sha256": hashlib.sha256(img_dec).hexdigest(),
                "rtl_targets_verified": ["kpol_bram_pipeline_axi.sv"],
                "negative_codes_verified": [
                    "B3-SYNTAX",
                    "B3-TYPE",
                    "B3-GUARD",
                    "B3-ACTION",
                    "B3-PROOF",
                ],
            },
            "KPOL-CME-2": {
                "profile": "KPOL-CME-2",
                "bram_bytes": 1024,
                "cascade4_bram_sha256": hashlib.sha256(img_c4).hexdigest(),
                "chain_cid0_bram_sha256": hashlib.sha256(img_cid0).hexdigest(),
                "rtl_targets_verified": [
                    "kpol_bram_pipeline_axi.sv",
                    "kpol_bram_pipeline_axi_ha.sv",
                ],
                "negative_codes_verified": [
                    "CME2-OPERAND-COLLISION",
                    "CME2-CASCADE",
                ],
            },
            "KPOL-AUTH": {
                "subset_spec": "Engineering/specifications/kpol/kpol-auth-subset.md",
                "bram_bytes": 1024,
                "thermal_bram_sha256": hashlib.sha256(auth_thermal.bram_image).hexdigest(),
                "thermal_dogo_words": len(auth_thermal.code_o),
                "cascade4_auth_bram_sha256": hashlib.sha256(auth_c4.bram_image).hexdigest(),
                "cascade4_auth_dogo_words": len(auth_c4.code_o),
                "cycle_rejection_code": "KPOL-LOWER-CYCLE",
                "uncertainty_gates_verified": [f"KPOL-AUTH-U{i:02d}" for i in range(1, 13)],
                "open_boundary_issue": 186,
            },
        },
        "mutant_controls": [
            "M1_secure_boot_hmac_byte_tamper_and_replay",
            "M2a_bram_action_opcode_inc_to_dec_rtl_divergence",
            "M2b_bram_threshold_w1_10_to_50_rtl_divergence",
            "M3a_dogo_opcode_add_to_sub_vm_exact_abort_vector",
            "M3b_dogo_missing_exit_opcode_vm_abort",
            "M4a_bram_cycle_validator_missing_self_loop_caught",
            "M4b_bram_cycle_validator_missing_2node_cycle_caught",
            "M5_uncertainty_policy_record_diagnostic_and_lowering_gate",
        ],
    }


def test_s5_recorded_acceptance_artifacts_and_provenance():
    """Verify recorded raw summary JSON and run log provenance headers (#179, AGENTS.md §4.4)."""
    assert SUMMARY_JSON_PATH.is_file(), f"Missing {SUMMARY_JSON_PATH}"
    assert RUN_LOG_PATH.is_file(), f"Missing {RUN_LOG_PATH}"

    recorded = json.loads(SUMMARY_JSON_PATH.read_text(encoding="utf-8"))
    expected = generate_acceptance_summary()
    assert recorded == expected

    log_lines = RUN_LOG_PATH.read_text(encoding="utf-8").splitlines()
    assert len(log_lines) >= 5
    assert log_lines[0].startswith("# cmd: "), "Line 1 of raw log must start with '# cmd: '"
    assert re.match(
        r"^# timestamp: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$",
        log_lines[1],
    ), f"Line 2 must be ISO 8601 timestamp with timezone, got: {log_lines[1]!r}"
    for idx, line in enumerate(log_lines, start=1):
        assert line == line.rstrip(), f"Trailing whitespace on line {idx} of {RUN_LOG_PATH}"


def _cli_main() -> int:
    parser = argparse.ArgumentParser(description="Generate S5 compiler acceptance summary JSON.")
    parser.add_argument("--emit-summary", type=Path, required=True)
    args = parser.parse_args()
    summary = generate_acceptance_summary()
    args.emit_summary.parent.mkdir(parents=True, exist_ok=True)
    args.emit_summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
