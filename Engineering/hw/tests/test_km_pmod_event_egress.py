# -*- coding: utf-8 -*-
"""Верифікація RTL-модуля km_pmod_event_egress.sv (Issue #230, передумова EXP-GPU-01).

УВАГА (чесне маркування за AGENTS.md §4.2):
Усі перевірки нижче виконуються в симуляції (iverilog/vvp), статичному
лінті (verilator) та логічному синтезі XC7 (yosys synth_xilinx).
Фізичний HIL-запуск на платах PYNQ-Z1 <-> Jetson J501 тут НЕ виконується.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HW = Path(__file__).resolve().parents[1]
RTL = HW / "rtl" / "io" / "km_pmod_event_egress.sv"
TB = HW / "tb" / "km_pmod_event_egress_tb.sv"
TOP_V = HW / "boards" / "pynq-z1" / "kpol_bram_pipeline_pynq_z1_egress_top.v"
TOP_TB = HW / "tests" / "kpol_bram_pipeline_pynq_z1_egress_top_tb.sv"
PIPELINE_SRCS = [
    HW / "rtl" / "core" / "kpol_txn_gate_v2.sv",
    HW / "rtl" / "core" / "km_concept_micro_engine.sv",
    HW / "rtl" / "core" / "km_concept_bram.sv",
    HW / "rtl" / "core" / "km_autonomous_sequencer.sv",
    HW / "rtl" / "bus" / "kpol_bram_pipeline_axi.sv",
]

XILINX_BLACKBOX_STUB = """\
`timescale 1ns / 1ps
/* verilator lint_off UNDRIVEN */
/* verilator lint_off UNUSEDSIGNAL */
(* blackbox *)
module BUFG (input wire I, output wire O);
endmodule

(* blackbox *)
module PS7 (
    output wire [3:0]  FCLKCLK,
    input  wire        MAXIGP0ACLK,
    output wire        MAXIGP0ARESETN,
    output wire [31:0] MAXIGP0ARADDR,
    output wire [11:0] MAXIGP0ARID,
    output wire        MAXIGP0ARVALID,
    input  wire        MAXIGP0ARREADY,
    output wire        MAXIGP0RREADY,
    input  wire [31:0] MAXIGP0RDATA,
    input  wire [11:0] MAXIGP0RID,
    input  wire        MAXIGP0RLAST,
    input  wire [1:0]  MAXIGP0RRESP,
    input  wire        MAXIGP0RVALID,
    output wire [31:0] MAXIGP0AWADDR,
    output wire [11:0] MAXIGP0AWID,
    output wire        MAXIGP0AWVALID,
    input  wire        MAXIGP0AWREADY,
    output wire [31:0] MAXIGP0WDATA,
    output wire [3:0]  MAXIGP0WSTRB,
    output wire [11:0] MAXIGP0WID,
    output wire        MAXIGP0WVALID,
    input  wire        MAXIGP0WREADY,
    output wire        MAXIGP0BREADY,
    input  wire [11:0] MAXIGP0BID,
    input  wire [1:0]  MAXIGP0BRESP,
    input  wire        MAXIGP0BVALID
);
endmodule
/* verilator lint_on UNUSEDSIGNAL */
/* verilator lint_on UNDRIVEN */
"""

needs_iverilog = pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Потрібні iverilog і vvp",
)
needs_verilator = pytest.mark.skipif(
    shutil.which("verilator") is None,
    reason="Потрібен verilator",
)
needs_yosys = pytest.mark.skipif(
    shutil.which("yosys") is None,
    reason="Потрібен yosys",
)


def _py_crc8(payload_56: int) -> int:
    """Незалежний еталонний розрахунок CRC-8 (поліном 0x07, init 0x00, MSB-first)."""
    crc = 0
    for bit in range(55, -1, -1):
        fb = ((crc >> 7) ^ ((payload_56 >> bit) & 1)) & 1
        crc = ((crc << 1) & 0xFF) ^ (0x07 if fb else 0x00)
    return crc


def _run_sim(rtl_path: Path, work_dir: Path) -> subprocess.CompletedProcess[str]:
    sim = work_dir / "sim.vvp"
    comp = subprocess.run(
        ["iverilog", "-g2012", "-o", str(sim), str(rtl_path), str(TB)],
        capture_output=True,
        text=True,
    )
    assert comp.returncode == 0, f"iverilog failed:\n{comp.stderr}"
    return subprocess.run(
        ["vvp", "-n", str(sim)],
        capture_output=True,
        text=True,
        timeout=60,
    )


@needs_iverilog
def test_km_pmod_event_egress_simulation_and_python_crc_oracle(tmp_path):
    run = _run_sim(RTL, tmp_path)
    out = run.stdout + run.stderr
    assert run.returncode == 0, out
    assert "ALL KM_PMOD_EVENT_EGRESS SIMULATION TESTS PASSED" in out

    # Незалежна звірка 64-бітних кадрів із симуляції проти еталонної Python-моделі
    # Перевіряємо перші 4 тести (Test 1, 3, 4 виводять frame=... у лог)
    expected_cases = [
        (5, 0xA55A, 0x12345678),
        (63, 0xFFFF, 0x80000001),
        (0, 0x0000, 0x00000000),
    ]
    frames = [int(m, 16) for m in re.findall(r"frame=([0-9a-fA-F]{16})", out)]
    assert len(frames) == len(expected_cases), out
    for got_frame, (cid, mask16, state) in zip(frames, expected_cases):
        payload = (0b01 << 54) | (cid << 48) | (mask16 << 32) | state
        exp_frame = (_py_crc8(payload) << 56) | payload
        assert got_frame == exp_frame, (
            f"Невідповідність кадра для cid={cid}: got=0x{got_frame:016x} exp=0x{exp_frame:016x}"
        )


@needs_verilator
def test_km_pmod_event_egress_verilator_lint():
    res = subprocess.run(
        [
            "verilator",
            "--lint-only",
            "-Wall",
            "--top-module",
            "km_pmod_event_egress",
            str(RTL),
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr


@needs_yosys
def test_km_pmod_event_egress_yosys_synth_xilinx():
    cmd = (
        f"read_verilog -sv {RTL}; "
        "hierarchy -check -top km_pmod_event_egress; "
        "synth_xilinx -top km_pmod_event_egress; "
        "check"
    )
    res = subprocess.run(
        ["yosys", "-Q", "-q", "-p", cmd],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr


@needs_iverilog
@pytest.mark.parametrize(
    "mutant_name,old_expr,new_expr",
    [
        (
            "corrupt_crc_poly",
            "crc = {crc[6:0], 1'b0} ^ (fb ? 8'h07 : 8'h00);",
            "crc = {crc[6:0], 1'b0} ^ (fb ? 8'h05 : 8'h00);",
        ),
        (
            "corrupt_spi_shift_bit",
            "shift_reg_q <= {shift_reg_q[62:0], 1'b0};",
            "shift_reg_q <= {shift_reg_q[61:0], 2'b00};",
        ),
        (
            "corrupt_par8_byte_shift",
            "shift_reg_q <= {shift_reg_q[55:0], 8'd0};",
            "shift_reg_q <= {shift_reg_q[54:0], 9'd0};",
        ),
        (
            "cs_high_in_end",
            "                S_SPI_END: begin\n                    spi_sck_o  <= 1'b0;\n                    spi_cs_n_o <= 1'b0;",
            "                S_SPI_END: begin\n                    spi_sck_o  <= 1'b0;\n                    spi_cs_n_o <= 1'b1;",
        ),
        (
            "par_valid_drop_end",
            "                S_PAR_END: begin\n                    par_clk_o   <= 1'b0;\n                    par_valid_o <= 1'b1;",
            "                S_PAR_END: begin\n                    par_clk_o   <= 1'b0;\n                    par_valid_o <= 1'b0;",
        ),
        (
            "broken_drop_count",
            "drop_count_o <= drop_count_o + 32'd1;",
            "drop_count_o <= drop_count_o;",
        ),
        (
            "missing_event_start",
            "event_start_o <= 1'b1;",
            "event_start_o <= 1'b0;",
        ),
        (
            "stuck_not_busy",
            "busy_o        <= 1'b1;",
            "busy_o        <= 1'b0;",
        ),
    ],
)
def test_km_pmod_event_egress_mutant_negative_control(
    tmp_path, mutant_name, old_expr, new_expr
):
    """Мутантний негативний контроль (AGENTS.md §4.1): зіпсований RTL має провалювати тестбенч."""
    src = RTL.read_text(encoding="utf-8")
    assert old_expr in src, f"Не знайдено цільовий рядок для мутанта {mutant_name}"
    mutant_rtl = tmp_path / f"mutant_{mutant_name}.sv"
    mutant_rtl.write_text(src.replace(old_expr, new_expr, 1), encoding="utf-8")

    run = _run_sim(mutant_rtl, tmp_path)
    out = run.stdout + run.stderr
    assert run.returncode != 0, (
        f"Мутант '{mutant_name}' несподівано пройшов симуляцію!\n{out}"
    )


@needs_iverilog
def test_pynq_z1_egress_top_e2e_simulation_and_crc_oracle(tmp_path):
    """Наскрізна симуляція (mock PS7/BUFG): Stimulus -> BRAM Commit -> PMOD JB Egress."""
    sim = tmp_path / "egress_top_sim.vvp"
    comp = subprocess.run(
        [
            "iverilog",
            "-g2012",
            "-s",
            "kpol_bram_pipeline_pynq_z1_egress_top_tb",
            "-o",
            str(sim),
            *[str(p) for p in PIPELINE_SRCS],
            str(RTL),
            str(TOP_V),
            str(TOP_TB),
        ],
        capture_output=True,
        text=True,
    )
    assert comp.returncode == 0, f"iverilog failed:\n{comp.stderr}"
    run = subprocess.run(
        ["vvp", "-n", str(sim)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = run.stdout + run.stderr
    assert run.returncode == 0, out
    assert "PASS: ALL PYNQ_Z1_EGRESS_TOP E2E TESTS PASSED" in out, out

    frames = [int(m, 16) for m in re.findall(r"frame=([0-9a-fA-F]{16})", out)]
    expected = [
        (2, 0x0000, 201),
        (2, 0x0000, 202),
    ]
    assert len(frames) == len(expected), out
    for got_frame, (cid, mask16, state) in zip(frames, expected):
        payload = (0b01 << 54) | (cid << 48) | (mask16 << 32) | state
        exp_frame = (_py_crc8(payload) << 56) | payload
        assert got_frame == exp_frame, (
            f"Невідповідність E2E кадра: got=0x{got_frame:016x} exp=0x{exp_frame:016x}"
        )


@needs_verilator
def test_pynq_z1_egress_top_verilator_lint(tmp_path):
    stub = tmp_path / "xilinx_bb.v"
    stub.write_text(XILINX_BLACKBOX_STUB, encoding="utf-8")
    res = subprocess.run(
        [
            "verilator",
            "--lint-only",
            "-Wall",
            "-Wno-DECLFILENAME",
            "-Wno-PINCONNECTEMPTY",
            "-Wno-UNUSEDSIGNAL",
            "-Wno-UNUSEDPARAM",
            "--top-module",
            "kpol_bram_pipeline_pynq_z1_egress_top",
            str(stub),
            *[str(p) for p in PIPELINE_SRCS],
            str(RTL),
            str(TOP_V),
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr


@needs_yosys
def test_pynq_z1_egress_top_yosys_synth_xilinx(tmp_path):
    stub = tmp_path / "xilinx_bb.v"
    stub.write_text(XILINX_BLACKBOX_STUB, encoding="utf-8")
    srcs = " ".join(str(p) for p in [*PIPELINE_SRCS, RTL, TOP_V, stub])
    cmd = (
        f"read_verilog -sv {srcs}; "
        "hierarchy -check -top kpol_bram_pipeline_pynq_z1_egress_top; "
        "synth_xilinx -top kpol_bram_pipeline_pynq_z1_egress_top; "
        "check"
    )
    res = subprocess.run(
        ["yosys", "-Q", "-q", "-p", cmd],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_egress_frame_crc8_bytewise_and_tag_mutants_on_crossboard_runs():
    """Розширений негативний контроль CRC-8 та тегу (F-8) по всіх 8 байтах кадрів із r1..r5."""
    import json
    import sys

    exp_dir = HW.parents[1] / "Research" / "studies" / "fpga-gpu-symbiosis" / "experiments" / "EXP-GPU-01"
    data_cb = HW.parents[1] / "Research" / "studies" / "fpga-gpu-symbiosis" / "data" / "exp-gpu-01-crossboard"
    if str(exp_dir) not in sys.path:
        sys.path.insert(0, str(exp_dir))
    import crossboard_frame as cbf

    run_files = sorted(data_cb.glob("crossboard_r*.json"))
    assert len(run_files) == 5
    for rf in run_files:
        rdata = json.loads(rf.read_text(encoding="utf-8"))
        frame64 = int(rdata["last_frame64_hex"], 16)
        raw8 = frame64.to_bytes(8, byteorder="big")
        unpacked = cbf.verify_and_unpack_egress_bytes(raw8)
        assert unpacked["tag"] == 0b01
        assert unpacked["cid"] == 3

        # Побайтова та побітова інверсія кожного з 8 байтів кадра
        for byte_idx in range(8):
            for bit_idx in range(8):
                corrupted = bytearray(raw8)
                corrupted[byte_idx] ^= 1 << bit_idx
                with pytest.raises(cbf.EgressFrameError):
                    cbf.verify_and_unpack_egress_bytes(bytes(corrupted))

        # Невалідні 2-бітні теги формату (0b00, 0b10, 0b11) із валідним перерахованим CRC-8
        for bad_tag in (0b00, 0b10, 0b11):
            bad_bytes = cbf.encode_egress_frame_bytes(
                cid=unpacked["cid"],
                mask16=unpacked["mask16"],
                state=unpacked["state"],
                tag=bad_tag,
            )
            with pytest.raises(cbf.EgressFrameError, match="Invalid frame tag"):
                cbf.verify_and_unpack_egress_bytes(bad_bytes)
