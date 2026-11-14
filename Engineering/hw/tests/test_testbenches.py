# -*- coding: utf-8 -*-
"""Запуск усіх RTL-тестбенчів hw/tb/ в Icarus Verilog.

Тест падає, якщо компіляція чи симуляція завершилися з помилкою, якщо
в журналі є ознаки провалу (ті самі, що в AV-07), або якщо немає
очікуваного рядка успіху. Перелік залежностей — явний: новий тестбенч
без запису в TESTBENCHES тест помітить (test_all_testbenches_registered).
"""
import shutil
import subprocess
from pathlib import Path

import pytest

HW = Path(__file__).resolve().parents[1]
CORE, IO = "rtl/core", "rtl/io"

# тестбенч -> (RTL-залежності, обов'язковий рядок успіху або None)
TESTBENCHES = {
    "kpol_txn_gate_v2_tb.sv": ([f"{CORE}/kpol_txn_gate_v2.sv"], None),
    "km_concept_bram_tb.sv": ([f"{CORE}/km_concept_bram.sv"], None),
    "km_concept_micro_engine_tb.sv": (
        [f"{CORE}/kpol_txn_gate_v2.sv", f"{CORE}/km_concept_micro_engine.sv"],
        "УСІ 10 ТЕСТОВИХ СЦЕНАРІЇВ УНІВЕРСАЛЬНОГО ЯДРА CME УСПІШНО ПРОЙДЕНО"),
    "km_autonomous_sequencer_tb.sv": (
        [f"{CORE}/kpol_txn_gate_v2.sv", f"{CORE}/km_concept_micro_engine.sv",
         f"{CORE}/km_concept_bram.sv", f"{CORE}/km_autonomous_sequencer.sv"],
        "АВТОНОМНЕ ВИКОНАННЯ, ЧЕРГА ТА НЕЗМІННЕ ЯДРО УСПІШНО ДОВЕДЕНО"),
    "km_io_trigger_engine_tb.sv": ([f"{IO}/km_io_trigger_engine.sv"], None),
}

FAIL_MARKERS = ("$fatal", "FATAL", "[FAIL]", "FAIL:", "mismatch", "ERROR")

needs_iverilog = pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Потрібні iverilog і vvp")


def test_all_testbenches_registered():
    on_disk = {p.name for p in (HW / "tb").glob("*_tb.sv")}
    assert on_disk == set(TESTBENCHES), f"не зареєстровано: {on_disk ^ set(TESTBENCHES)}"


# Відомі провали, що існували ще в drafts@a4738bc. strict=True: якщо тест
# почне проходити, позначку треба зняти разом із закриттям Issue.
KNOWN_FAILURES: dict[str, str] = {}


def _params():
    for tb in sorted(TESTBENCHES):
        marks = [pytest.mark.xfail(reason=KNOWN_FAILURES[tb], strict=True)] if tb in KNOWN_FAILURES else []
        yield pytest.param(tb, marks=marks, id=tb)


@needs_iverilog
@pytest.mark.parametrize("tb", _params())
def test_testbench(tb, tmp_path):
    deps, success = TESTBENCHES[tb]
    sim = tmp_path / "sim.vvp"
    comp = subprocess.run(
        ["iverilog", "-g2012", "-o", str(sim), *[str(HW / d) for d in deps], str(HW / "tb" / tb)],
        capture_output=True, text=True)
    assert comp.returncode == 0, comp.stderr
    run = subprocess.run(["vvp", "-n", str(sim)], capture_output=True, text=True, timeout=120)
    out = run.stdout + run.stderr
    assert run.returncode == 0, out[-3000:]
    bad = [m for m in FAIL_MARKERS if m in out]
    assert not bad, f"ознаки провалу {bad}:\n{out[-3000:]}"
    if success:
        assert success in out, out[-3000:]
