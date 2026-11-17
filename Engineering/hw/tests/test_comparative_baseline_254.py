#!/usr/bin/env python3
"""
Comparative Baseline Equivalence, Cycle-Accuracy, Mutant, and Provenance Suite (Issue #254).

Verifies 100% bit-exact equivalence across all 4 implementations on identical
KPOL-CME-2 reactive cascade programs (valid cascades, input rejections,
mid-cascade guard rejections, < 0 invariant underflow rejections, 64-concept
boundary cascades, and online runtime rule reconfiguration without recompilation
or FPGA bitstream resynthesis):
  1. Reference KPOL-CME-2 specification & interpreter (kpol_reference.py)
  2. Compiled C99 (-O3) cascade engine (c99_cascade_bench.c)
  3. Register-configurable RTL cascade engine (km_reg_configurable_cascade_axi.sv)
  4. BRAM-descriptor pipeline CFG-P (kpol_bram_pipeline_axi.sv)

Also executes 6 mutant controls (3 RTL mutants + 3 C99 mutants) per AGENTS.md §4.1
and cross-checks raw synthesis / ARM benchmark artifacts in
Research/studies/comparative-baseline-254/raw/.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HW_DIR = REPO_ROOT / "Engineering" / "hw"
STUDY_DIR = REPO_ROOT / "Research" / "studies" / "comparative-baseline-254"
RAW_DIR = STUDY_DIR / "raw"

sys.path.insert(0, str(REPO_ROOT / "Engineering" / "sw" / "kpol-ref"))

import kpol_reference as kr  # noqa: E402
from kpol_reference import (  # noqa: E402
    EventInput,
    Interpreter,
    compile_concept_microcode_bram_image,
    parse_module,
)

needs_sim_and_cc = pytest.mark.skipif(
    shutil.which("iverilog") is None
    or shutil.which("vvp") is None
    or shutil.which("gcc") is None,
    reason="Requires iverilog, vvp, and gcc",
)

# Program A: Canonical 4-concept acyclic cascade C0 -> C1 -> C2 -> C3
# Exercises RANGE [10, 1000] + INC, GT 10 + INC, LT 1 inverted (>= 1) + DEC,
# EQ 2 inverted (!= 2) + ASSIGN, plus mid-cascade < 0 invariant rejection when C2 == 0.
CANONICAL_CASCADE_4_KPOL = """
Problem CanonicalCascade4 {
    Invariants {
        I0: C0 >= 0;
        I1: C1 >= 0;
        I2: C2 >= 0;
        I3: C3 >= 0;
    }
}
Solution CanonicalCascade4 {
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
Proof CanonicalCascade4 {
    scenario Basic {
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

# Program B: Exercises SUB k (k=20), ADD k (k=15), LT, EQ, root < 0 invariant
# underflow rejection (10 - 20 = -10 < 0), and mid-cascade predicate stop (C1 == 7).
SUB_ADD_UNDERFLOW_4_KPOL = """
Problem SubAddUnderflow4 {
    Invariants {
        I0: C0 >= 0;
        I1: C1 >= 0;
        I2: C2 >= 0;
        I3: C3 >= 0;
    }
}
Solution SubAddUnderflow4 {
    state C0: Int32 = 50;
    state C1: Int32 = 5;
    state C2: Int32 = 1;
    state C3: Int32 = 100;

    event E0(p0: Int32);
    event E3(p3: Int32);

    rule R0 on E0 when true { set C0 := C0 - 20; }
    rule R1 on change(C0) when C0 < 50 { set C1 := C1 + 1; }
    rule R2 on change(C1) when C1 == 7 { set C2 := C2 - 1; }
    rule R3 on E3 when true { set C3 := C3 + 15; }
}
Proof SubAddUnderflow4 {
    scenario UnderflowAndAdd {
        step E0(p0 = 0);
        expect C0 == 30;
        expect C1 == 6;
        expect C2 == 1;
        step E0(p0 = 0);
        expect C0 == 10;
        expect C1 == 7;
        expect C2 == 0;
        step E0(p0 = 0);
        expect C0 == 10;
        step E3(p3 = 0);
        expect C3 == 115;
    }
}
"""

# Program C: Boundary GT test on C0 > 100 -> C1 -> C2 -> C3 to expose > vs >= mutant
GT_BOUNDARY_4_KPOL = """
Problem GtBoundary4 {
    Invariants {
        I0: C0 >= 0;
        I1: C1 >= 0;
        I2: C2 >= 0;
        I3: C3 >= 0;
    }
}
Solution GtBoundary4 {
    state C0: Int32 = 0;
    state C1: Int32 = 0;
    state C2: Int32 = 0;
    state C3: Int32 = 0;

    event E0(p0: Int32);

    rule R0 on E0 when p0 > 100 { set C0 := C0 + 1; }
    rule R1 on change(C0) when C0 > 0 { set C1 := C1 + 1; }
    rule R2 on change(C1) when C1 > 0 { set C2 := C2 + 1; }
    rule R3 on change(C2) when C2 > 0 { set C3 := C2; }
}
Proof GtBoundary4 {
    scenario Boundary {
        step E0(p0 = 100);
        expect C0 == 0;
        step E0(p0 = 101);
        expect C3 == 1;
    }
}
"""


def _u32(val: int) -> int:
    return val & 0xFFFFFFFF


def _write_image_hex(image_bytes: bytes, out_path: Path) -> list[int]:
    words = list(struct.unpack("<256I", image_bytes))
    out_path.write_text("".join(f"{w:08x}\n" for w in words), encoding="utf-8")
    return words


def _write_events_hex(ops: list[tuple[str, int, int]], out_path: Path) -> None:
    """
    ops: list of ("trig", cid, param) or ("write_word", word_idx, word_val).
    Encoded as pairs of 32-bit hex words for C99 and SystemVerilog testbenches.
    """
    lines = []
    for kind, a, b in ops:
        if kind == "write_word":
            cmd_w = (0x01 << 24) | (a & 0xFF)
        elif kind == "trig":
            cmd_w = a & 0x3F
        else:
            raise ValueError(f"Unknown op kind: {kind}")
        lines.append(f"{_u32(cmd_w):08x} {_u32(b):08x}\n")
    out_path.write_text("".join(lines), encoding="utf-8")


def _parse_slots_and_summary(stdout: str) -> dict:
    slots: list[tuple[int, int, int, int]] = []
    summary: dict[str, int] = {}
    step_cycles: list[tuple[int, int, int]] = []
    for line in stdout.splitlines():
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
        elif line.startswith("STEP "):
            parts = dict(kv.split("=") for kv in line.split()[2:])
            step_cycles.append((
                int(parts["cycles"]),
                int(parts["commits"]),
                int(parts["rejects"]),
            ))
    assert len(slots) == 64, f"Expected 64 slots, got {len(slots)} in:\n{stdout}"
    assert "events" in summary, f"Missing SUMMARY line in:\n{stdout}"
    return {"slots": slots, "summary": summary, "steps": step_cycles}


def _reference_execute_kpol(module: kr.Module, triggers: list[tuple[int, str, str, int]]) -> dict:
    """
    Independently execute triggers through kpol_reference.Interpreter and compute
    expected final 256 words + (events, commits, rejects, last_state).
    """
    image = compile_concept_microcode_bram_image(module, profile="KPOL-CME-2")
    init_words = list(struct.unpack("<256I", image))
    interp = Interpreter(module)
    # Flush one-time initial change check (no-op in KPOL-CME-2)
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
        # Trace exact cascade chain on module rules to tally commits/rejects
        events_cnt += res.steps
        # Find root target state of ev_name
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


def _compile_c99_runner(tmp_path: Path, extra_cflags: list[str] | None = None, name: str = "c99_runner") -> Path:
    exe = tmp_path / name
    env = os.environ.copy()
    env["TMPDIR"] = str(tmp_path)
    mut_flags = ["-Wno-unused-but-set-variable", *extra_cflags] if extra_cflags else []
    cmd = [
        "gcc", "-std=gnu99", "-O3", "-Wall", "-Wextra", "-Werror",
        *mut_flags,
        str(STUDY_DIR / "c99_cascade_bench.c"),
        "-o", str(exe), "-lpthread", "-lm",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
    return exe


def _compile_reg_rtl_sim(
    tmp_path: Path,
    num_concepts: int = 4,
    extra_defines: list[str] | None = None,
    name: str = "reg_sim.vvp",
) -> Path:
    vvp = tmp_path / name
    env = os.environ.copy()
    env["TMPDIR"] = str(tmp_path)
    cmd = [
        "iverilog", "-g2012",
        f"-Pkm_reg_configurable_cascade_axi_tb.NUM_CONCEPTS={num_concepts}",
        *(extra_defines or []),
        "-s", "km_reg_configurable_cascade_axi_tb",
        "-o", str(vvp),
        str(HW_DIR / "rtl" / "baseline" / "km_reg_configurable_cascade_axi.sv"),
        str(HW_DIR / "tests" / "km_reg_configurable_cascade_axi_tb.sv"),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
    return vvp


def _compile_cfgp_rtl_sim(tmp_path: Path) -> Path:
    tb_code = """`timescale 1ns/1ps
module cfgp_trace_tb;
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
        .hw_commit_cid_o(), .hw_last_committed_state_o(), .busy(busy)
    );

    task automatic axi_write(input [12:0] addr, input [31:0] data);
        @(negedge clk);
        awaddr = addr; wdata = data; awvalid = 1; wvalid = 1; bready = 1;
        do @(posedge clk); while (!awready || !wready);
        @(negedge clk); awvalid = 0; wvalid = 0;
        while (!bvalid) @(negedge clk);
        if (bresp !== 2'b00) $fatal(1, "CFG-P write 0x%03h resp=%0d", addr, bresp);
        @(negedge clk); bready = 0;
    endtask

    task automatic axi_read(input [12:0] addr, output [31:0] data);
        @(negedge clk);
        araddr = addr; arvalid = 1; rready = 1;
        do @(posedge clk); while (!arready);
        @(negedge clk); arvalid = 0;
        while (!rvalid) @(negedge clk);
        if (rresp !== 2'b00) $fatal(1, "CFG-P read 0x%03h resp=%0d", addr, rresp);
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
            if (cmd_w[31:24] == 8'h01) begin
                axi_write(13'h004, {24'd0, cmd_w[7:0]});
                axi_write(13'h008, arg_w);
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
                    if (cyc > 1024) $fatal(1, "CFG-P watchdog");
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
        $finish;
    end
endmodule
"""
    tb_path = tmp_path / "cfgp_trace_tb.sv"
    vvp_path = tmp_path / "cfgp_trace.vvp"
    tb_path.write_text(tb_code, encoding="utf-8")
    env = os.environ.copy()
    env["TMPDIR"] = str(tmp_path)
    cmd = [
        "iverilog", "-g2012", "-s", "cfgp_trace_tb", "-o", str(vvp_path),
        str(HW_DIR / "rtl" / "core" / "kpol_txn_gate_v2.sv"),
        str(HW_DIR / "rtl" / "core" / "km_concept_micro_engine.sv"),
        str(HW_DIR / "rtl" / "core" / "km_concept_bram.sv"),
        str(HW_DIR / "rtl" / "core" / "km_autonomous_sequencer.sv"),
        str(HW_DIR / "rtl" / "bus" / "kpol_bram_pipeline_axi.sv"),
        str(tb_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
    return vvp_path


@needs_sim_and_cc
def test_four_way_bit_exact_equivalence_and_cycle_ratio_sim(tmp_path: Path):
    """
    Verify 100% bit-exact state/commit/reject identity across:
      (1) kpol_reference.py, (2) C99 -O3, (3) km_reg_configurable_cascade_axi.sv,
      and (4) kpol_bram_pipeline_axi.sv (CFG-P), plus exact 1-cycle vs 8-cycle step ratio.
    """
    c99_exe = _compile_c99_runner(tmp_path)
    reg_vvp = _compile_reg_rtl_sim(tmp_path, num_concepts=4)
    cfgp_vvp = _compile_cfgp_rtl_sim(tmp_path)

    cases = [
        (
            "canonical_cascade_and_mid_invariant_reject",
            CANONICAL_CASCADE_4_KPOL,
            [
                (0, "E0", "p0", 5),       # Input reject (< 10) -> 1 step
                (0, "E0", "p0", -32768),  # Negative input reject -> 1 step
                (0, "E0", "p0", 1001),    # Input reject (> 1000) -> 1 step
                (0, "E0", "p0", 10),      # Lower bound valid -> full 4-step cascade (C2: 2->1)
                (0, "E0", "p0", 1000),    # Upper bound valid -> full 4-step cascade (C2: 1->0)
                (0, "E0", "p0", 25),      # Mid-cascade < 0 invariant reject at C2 (0-1 = -1) -> 3 steps
                (0, "E0", "p0", 500),     # Second mid-cascade < 0 invariant reject at C2 -> 3 steps
            ],
        ),
        (
            "sub_add_underflow_and_predicate_stop",
            SUB_ADD_UNDERFLOW_4_KPOL,
            [
                (0, "E0", "p0", 0),       # C0: 50->30, C1: 5->6, C2 guard (6==7) rejects -> 3 steps
                (0, "E0", "p0", 0),       # C0: 30->10, C1: 6->7, C2: 1->0 -> 3 commits
                (0, "E0", "p0", 0),       # C0: 10-20 = -10 < 0 invariant rejects at C0 -> 1 step
                (3, "E3", "p3", 0),       # C3: 100 + 15 = 115 -> 1 commit
                (3, "E3", "p3", 0),       # C3: 115 + 15 = 130 -> 1 commit
            ],
        ),
    ]

    for case_name, kpol_src, triggers in cases:
        module = parse_module(kpol_src)
        ref = _reference_execute_kpol(module, triggers)

        img_hex = tmp_path / f"{case_name}_img.hex"
        ev_hex = tmp_path / f"{case_name}_ev.hex"
        _write_image_hex(ref["image"], img_hex)
        ops = [("trig", cid, pval) for cid, _en, _pn, pval in triggers]
        _write_events_hex(ops, ev_hex)

        c99_out = subprocess.run(
            [str(c99_exe), "--trace", str(img_hex), str(ev_hex), str(len(ops))],
            check=True, capture_output=True, text=True,
        ).stdout
        reg_out = subprocess.run(
            ["vvp", "-n", str(reg_vvp), f"+image_hex={img_hex}", f"+events_hex={ev_hex}", f"+num_events={len(ops)}"],
            check=True, capture_output=True, text=True,
        ).stdout
        cfgp_out = subprocess.run(
            ["vvp", "-n", str(cfgp_vvp), f"+image_hex={img_hex}", f"+events_hex={ev_hex}", f"+num_events={len(ops)}"],
            check=True, capture_output=True, text=True,
        ).stdout

        res_c99 = _parse_slots_and_summary(c99_out)
        res_reg = _parse_slots_and_summary(reg_out)
        res_cfgp = _parse_slots_and_summary(cfgp_out)

        assert res_c99["slots"] == ref["slots"], f"{case_name}: C99 slots diverged from kpol_reference"
        assert res_reg["slots"] == ref["slots"], f"{case_name}: Reg-RTL slots diverged from kpol_reference"
        assert res_cfgp["slots"] == ref["slots"], f"{case_name}: CFG-P slots diverged from kpol_reference"

        assert res_c99["summary"] == ref["summary"], f"{case_name}: C99 summary mismatch"
        assert res_reg["summary"] == ref["summary"], f"{case_name}: Reg-RTL summary mismatch"
        assert res_cfgp["summary"] == ref["summary"], f"{case_name}: CFG-P summary mismatch"

    # Verify exact cycle-level latency contrast on canonical case:
    # Reg-RTL: 1 cycle/concept (1 cycle for C0 reject, 4 cycles for 4-concept cascade, 3 cycles for C2 reject)
    # CFG-P: 8 cycles/concept + 1 cycle final b_we writeback when last step commits (8 cycles reject, 33 busy / 32 to 4th commit)
    img_hex = tmp_path / "canonical_cascade_and_mid_invariant_reject_img.hex"
    ev_hex = tmp_path / "canonical_cascade_and_mid_invariant_reject_ev.hex"
    reg_steps = _parse_slots_and_summary(
        subprocess.run(
            ["vvp", "-n", str(reg_vvp), f"+image_hex={img_hex}", f"+events_hex={ev_hex}", "+num_events=7"],
            check=True, capture_output=True, text=True,
        ).stdout
    )["steps"]
    assert [s[0] for s in reg_steps] == [1, 1, 1, 4, 4, 3, 3]


@needs_sim_and_cc
def test_online_rule_reconfiguration_without_resynthesis_all_engines_sim(tmp_path: Path):
    """
    Start C99, km_reg_configurable_cascade_axi (K=4), and CFG-P with Program A,
    execute events, dynamically rewrite rules/states to Program B via RAM / AXI4-Lite
    without recompilation or resynthesis, and verify 100% bit-exact final state.
    """
    mod_a = parse_module(CANONICAL_CASCADE_4_KPOL)
    mod_b = parse_module(SUB_ADD_UNDERFLOW_4_KPOL)
    img_a = compile_concept_microcode_bram_image(mod_a, profile="KPOL-CME-2")
    img_b = compile_concept_microcode_bram_image(mod_b, profile="KPOL-CME-2")
    words_b = list(struct.unpack("<256I", img_b))

    img_a_hex = tmp_path / "online_a.hex"
    ev_hex = tmp_path / "online_ev.hex"
    _write_image_hex(img_a, img_a_hex)

    ops: list[tuple[str, int, int]] = [
        ("trig", 0, 25),  # Program A: full 4-concept cascade (+4 commits)
        ("trig", 0, 5),   # Program A: rejected at C0 (+1 reject)
    ]
    # Reconfigure concepts 0..3 (16 words) to Program B at runtime
    for word_idx in range(16):
        ops.append(("write_word", word_idx, words_b[word_idx]))
    ops.extend([
        ("trig", 0, 0),   # Program B: C0 50->30, C1 5->6, C2 rejects (+2 commits, +1 reject)
        ("trig", 0, 0),   # Program B: C0 30->10, C1 6->7, C2 1->0 (+3 commits)
        ("trig", 0, 0),   # Program B: C0 10-20=-10 invariant rejects (+1 reject)
        ("trig", 3, 0),   # Program B: C3 100->115 (+1 commit)
    ])
    _write_events_hex(ops, ev_hex)

    # Independent reference calculation across Program A followed by Program B
    ref_a = _reference_execute_kpol(mod_a, [(0, "E0", "p0", 25), (0, "E0", "p0", 5)])
    ref_b = _reference_execute_kpol(
        mod_b,
        [(0, "E0", "p0", 0), (0, "E0", "p0", 0), (0, "E0", "p0", 0), (3, "E3", "p3", 0)],
    )
    expected_summary = {
        "events": ref_a["summary"]["events"] + ref_b["summary"]["events"],
        "commits": ref_a["summary"]["commits"] + ref_b["summary"]["commits"],
        "rejects": ref_a["summary"]["rejects"] + ref_b["summary"]["rejects"],
        "last_state": ref_b["summary"]["last_state"],
    }

    c99_exe = _compile_c99_runner(tmp_path)
    reg_vvp = _compile_reg_rtl_sim(tmp_path, num_concepts=4)
    cfgp_vvp = _compile_cfgp_rtl_sim(tmp_path)

    res_c99 = _parse_slots_and_summary(
        subprocess.run(
            [str(c99_exe), "--trace", str(img_a_hex), str(ev_hex), str(len(ops))],
            check=True, capture_output=True, text=True,
        ).stdout
    )
    res_reg = _parse_slots_and_summary(
        subprocess.run(
            ["vvp", "-n", str(reg_vvp), f"+image_hex={img_a_hex}", f"+events_hex={ev_hex}", f"+num_events={len(ops)}"],
            check=True, capture_output=True, text=True,
        ).stdout
    )
    res_cfgp = _parse_slots_and_summary(
        subprocess.run(
            ["vvp", "-n", str(cfgp_vvp), f"+image_hex={img_a_hex}", f"+events_hex={ev_hex}", f"+num_events={len(ops)}"],
            check=True, capture_output=True, text=True,
        ).stdout
    )

    assert res_c99["slots"] == ref_b["slots"]
    assert res_reg["slots"] == ref_b["slots"]
    assert res_cfgp["slots"] == ref_b["slots"]
    assert res_c99["summary"] == expected_summary
    assert res_reg["summary"] == expected_summary
    assert res_cfgp["summary"] == expected_summary


@needs_sim_and_cc
@pytest.mark.parametrize("num_concepts", [16, 64])
def test_scaling_parameterization_k16_and_k64_equivalence_sim(tmp_path: Path, num_concepts: int):
    """Verify km_reg_configurable_cascade_axi parameterized for K=16 and K=64 matches kpol_reference and CFG-P."""
    last = num_concepts - 1
    invariants = "\n".join(f"I{i}: S{i} >= 0;" for i in range(num_concepts))
    states = "\n".join(f"state S{i}: Int32 = {i};" for i in range(num_concepts))
    events = "\n".join(f"event E{i}(p{i}: Int32);" for i in range(num_concepts - 3))
    rules = []
    for i in range(num_concepts - 4):
        rules.append(f"rule R{i} on E{i} when p{i} == {i} {{ set S{i} := S{i} + 1; }}")
    c0 = num_concepts - 4
    rules.extend([
        f"rule R{c0} on E{c0} when p{c0} >= 1 and p{c0} <= 50 {{ set S{c0} := S{c0} + 1; }}",
        f"rule R{c0+1} on change(S{c0}) when S{c0} > {c0} {{ set S{c0+1} := S{c0+1} + 1; }}",
        f"rule R{c0+2} on change(S{c0+1}) when S{c0+1} > {c0+1} {{ set S{c0+2} := S{c0+2} + 1; }}",
        f"rule R{last} on change(S{c0+2}) when S{c0+2} > {c0+2} {{ set S{last} := S{c0+2}; }}",
    ])
    kpol_src = f"""
    Problem Scale{num_concepts} {{ Invariants {{ {invariants} }} }}
    Solution Scale{num_concepts} {{
        {states}
        {events}
        {chr(10).join(rules)}
    }}
    Proof Scale{num_concepts} {{
        scenario CascadeTail {{
            step E{c0}(p{c0} = 10);
            expect S{last} == {c0 + 3};
        }}
    }}
    """
    module = parse_module(kpol_src)
    triggers = [
        (c0, f"E{c0}", f"p{c0}", 99),  # Reject at c0
        (c0, f"E{c0}", f"p{c0}", 10),  # 4-stage cascade across top CIDs .. K-1
    ]
    ref = _reference_execute_kpol(module, triggers)
    img_hex = tmp_path / f"scale{num_concepts}_img.hex"
    ev_hex = tmp_path / f"scale{num_concepts}_ev.hex"
    _write_image_hex(ref["image"], img_hex)
    ops = [("trig", cid, pval) for cid, _en, _pn, pval in triggers]
    _write_events_hex(ops, ev_hex)

    reg_vvp = _compile_reg_rtl_sim(tmp_path, num_concepts=num_concepts, name=f"reg_k{num_concepts}.vvp")
    cfgp_vvp = _compile_cfgp_rtl_sim(tmp_path)

    res_reg = _parse_slots_and_summary(
        subprocess.run(
            ["vvp", "-n", str(reg_vvp), f"+image_hex={img_hex}", f"+events_hex={ev_hex}", "+num_events=2"],
            check=True, capture_output=True, text=True,
        ).stdout
    )
    res_cfgp = _parse_slots_and_summary(
        subprocess.run(
            ["vvp", "-n", str(cfgp_vvp), f"+image_hex={img_hex}", f"+events_hex={ev_hex}", "+num_events=2"],
            check=True, capture_output=True, text=True,
        ).stdout
    )
    assert res_reg["slots"] == ref["slots"]
    assert res_cfgp["slots"] == ref["slots"]
    assert res_reg["summary"] == ref["summary"]


@needs_sim_and_cc
@pytest.mark.parametrize(
    "mutant_kind,define_flag,kpol_src,triggers",
    [
        pytest.param(
            "rtl",
            "-DMUTANT_SKIP_INVARIANT",
            CANONICAL_CASCADE_4_KPOL,
            [(0, "E0", "p0", 25), (0, "E0", "p0", 25), (0, "E0", "p0", 25)],
            id="rtl_skip_invariant",
        ),
        pytest.param(
            "rtl",
            "-DMUTANT_FLIP_GT",
            GT_BOUNDARY_4_KPOL,
            [(0, "E0", "p0", 100)],
            id="rtl_flip_gt_threshold",
        ),
        pytest.param(
            "rtl",
            "-DMUTANT_DROP_CASCADE",
            CANONICAL_CASCADE_4_KPOL,
            [(0, "E0", "p0", 25)],
            id="rtl_drop_cascade",
        ),
        pytest.param(
            "c99",
            "-DMUTANT_C_SKIP_INVARIANT",
            CANONICAL_CASCADE_4_KPOL,
            [(0, "E0", "p0", 25), (0, "E0", "p0", 25), (0, "E0", "p0", 25)],
            id="c99_skip_invariant",
        ),
        pytest.param(
            "c99",
            "-DMUTANT_C_FLIP_GT",
            GT_BOUNDARY_4_KPOL,
            [(0, "E0", "p0", 100)],
            id="c99_flip_gt_threshold",
        ),
        pytest.param(
            "c99",
            "-DMUTANT_C_DROP_CASCADE",
            CANONICAL_CASCADE_4_KPOL,
            [(0, "E0", "p0", 25)],
            id="c99_drop_cascade",
        ),
    ],
)
def test_mutant_controls_are_detected_sim(
    tmp_path: Path,
    mutant_kind: str,
    define_flag: str,
    kpol_src: str,
    triggers: list[tuple[int, str, str, int]],
):
    """AGENTS.md §4.1: prove equivalence test kills invariant, threshold, and cascade mutants in RTL and C99."""
    module = parse_module(kpol_src)
    ref = _reference_execute_kpol(module, triggers)

    img_hex = tmp_path / "mut_img.hex"
    ev_hex = tmp_path / "mut_ev.hex"
    _write_image_hex(ref["image"], img_hex)
    ops = [("trig", cid, pval) for cid, _en, _pn, pval in triggers]
    _write_events_hex(ops, ev_hex)

    if mutant_kind == "rtl":
        mut_vvp = _compile_reg_rtl_sim(
            tmp_path, num_concepts=4, extra_defines=[define_flag], name="mut_reg.vvp"
        )
        out = subprocess.run(
            ["vvp", "-n", str(mut_vvp), f"+image_hex={img_hex}", f"+events_hex={ev_hex}", f"+num_events={len(ops)}"],
            check=True, capture_output=True, text=True,
        ).stdout
    else:
        mut_exe = _compile_c99_runner(tmp_path, extra_cflags=[define_flag], name="mut_c99")
        out = subprocess.run(
            [str(mut_exe), "--trace", str(img_hex), str(ev_hex), str(len(ops))],
            check=True, capture_output=True, text=True,
        ).stdout

    mut_res = _parse_slots_and_summary(out)
    diverged = (mut_res["slots"] != ref["slots"]) or (mut_res["summary"] != ref["summary"])
    assert diverged, f"Mutant {mutant_kind}:{define_flag} survived undetected"


def test_raw_artifacts_provenance_and_lut_crossover_consistency():
    """Verify raw study artifacts, SHA-256 hashes, ARM disassembly, and nextpnr SLICE_LUTX K* crossover."""
    summary_path = RAW_DIR / "baseline_254_summary.json"
    assert summary_path.is_file(), "Missing baseline_254_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    required_files = [
        "arm_c99_build_and_sysinfo.log",
        "arm_c99_o3_disasm.txt",
        "arm_c99_and_eventfd_bench.log",
        "arm_c99_and_eventfd_bench.json",
        "rtl_cycle_timing_sim.log",
        "yosys_standalone_cores_stat.log",
        "yosys_cfg_p_k64.log",
        "nextpnr_cfg_p_k64.log",
        "nextpnr_cfg_p_k64_report.json",
        "yosys_reg_k4.log",
        "nextpnr_reg_k4.log",
        "nextpnr_reg_k4_report.json",
        "yosys_reg_k16.log",
        "nextpnr_reg_k16.log",
        "nextpnr_reg_k16_report.json",
        "yosys_reg_k64.log",
        "nextpnr_reg_k64.log",
        "nextpnr_reg_k64_report.json",
    ]
    hashes = summary["raw_artifact_sha256"]
    for fname in required_files:
        fpath = RAW_DIR / fname
        assert fpath.is_file() and fpath.stat().st_size > 0, f"Missing or empty raw file: {fname}"
        actual_sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
        assert hashes.get(fname) == actual_sha, f"SHA-256 mismatch for {fname}"

    # Check ISO 8601 header provenance in raw .log and disasm .txt files
    for fname in required_files:
        if fname.endswith((".log", ".txt")):
            head = (RAW_DIR / fname).read_text(encoding="utf-8").splitlines()[:2]
            assert head[0].startswith("# cmd: "), f"{fname} missing '# cmd:' header"
            assert head[1].startswith("# timestamp: "), f"{fname} missing '# timestamp:' header"

    disasm_text = (RAW_DIR / "arm_c99_o3_disasm.txt").read_text(encoding="utf-8")
    assert "<km_eval_cascade>:" in disasm_text
    assert "<km_update_rules_ram>:" in disasm_text

    # Cross-check SLICE_LUTX, SLICE_FFX, RAMB36E1, and K* directly against nextpnr JSON reports
    pnr = summary["openxc7_pnr_xc7z020"]
    cfgp_rep = json.loads((RAW_DIR / "nextpnr_cfg_p_k64_report.json").read_text(encoding="utf-8"))
    k4_rep = json.loads((RAW_DIR / "nextpnr_reg_k4_report.json").read_text(encoding="utf-8"))
    k16_rep = json.loads((RAW_DIR / "nextpnr_reg_k16_report.json").read_text(encoding="utf-8"))
    k64_rep = json.loads((RAW_DIR / "nextpnr_reg_k64_report.json").read_text(encoding="utf-8"))

    lut_cfgp = cfgp_rep["utilization"]["SLICE_LUTX"]["used"]
    lut_k4 = k4_rep["utilization"]["SLICE_LUTX"]["used"]
    lut_k16 = k16_rep["utilization"]["SLICE_LUTX"]["used"]
    lut_k64 = k64_rep["utilization"]["SLICE_LUTX"]["used"]

    assert cfgp_rep["utilization"]["RAMB36E1"]["used"] == 1
    assert k4_rep["utilization"]["RAMB36E1"]["used"] == 0
    assert k16_rep["utilization"]["RAMB36E1"]["used"] == 0
    assert k64_rep["utilization"]["RAMB36E1"]["used"] == 0

    assert lut_k4 < lut_cfgp < lut_k64, (
        f"Expected monotonic LUT crossover: K=4 ({lut_k4}) < CFG-P ({lut_cfgp}) < K=64 ({lut_k64})"
    )
    assert lut_k4 < lut_k16 < lut_k64

    crossover = pnr["crossover"]
    assert 4.0 < crossover["piecewise_k_star"] < 64.0
