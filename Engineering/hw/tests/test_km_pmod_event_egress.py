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
