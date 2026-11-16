#!/usr/bin/env python3
"""
Unit and regression test for C99 MCU Runtime + FPGA Coprocessor Bridge
Verifies Proposal 3 (Hybrid Co-Design: ARM Cortex-A9 / MCU + FPGA Invariant Guard).
"""

import subprocess
import os
import pytest

C_SOURCE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "km_mcu_fpga_bridge.c"))
BIN_PATH = "/tmp/km_mcu_fpga_bridge_test_bin"


@pytest.fixture(scope="module")
def compiled_binary():
    assert os.path.isfile(C_SOURCE), f"C source not found: {C_SOURCE}"
    compile_cmd = [
        "gcc",
        "-O2",
        "-Wall",
        "-Wextra",
        C_SOURCE,
        "-o",
        BIN_PATH,
    ]
    res = subprocess.run(compile_cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Compilation failed: {res.stderr}"
    assert os.path.isfile(BIN_PATH)
    yield BIN_PATH
    if os.path.exists(BIN_PATH):
        try:
            os.remove(BIN_PATH)
        except OSError:
            pass


def test_mcu_fpga_bridge_mock_execution(compiled_binary):
    """Verify hybrid MCU+FPGA bridge execution in mock mode."""
    res = subprocess.run(
        [compiled_binary, "--mock"], capture_output=True, text=True
    )
    assert res.returncode == 0, f"Execution failed: {res.stderr}"
    out = res.stdout

    assert "[FPGA Bridge] Ініціалізація в режимі ПРОГРАМНОГО МОКУ" in out
    assert "СЦЕНАРІЙ 1: Номінальне керування актуатором" in out
    assert (
        "[FPGA COP-GUARD] КОМІТ ПІДТВЕРДЖЕНО КРЕМНІЄМ: стан концепту 1 оновлено на 50"
        in out
    )

    assert "СЦЕНАРІЙ 2: Аварійний збій у софті" in out
    assert (
        "[FPGA COP-GUARD] ВІДХИЛЕНО КРЕМНІЄМ! Запис 150 у концепт 1 заблоковано"
        in out
    )
    assert (
        "[+] Апаратний Fail-Closed захист: КРЕМНІЙ ЗАПОБІГ АВАРІЇ ПЕРЕГРІВУ!"
        in out
    )

    assert "СЦЕНАРІЙ 3: Аварійний збій у софті" in out
    assert (
        "[FPGA COP-GUARD] ВІДХИЛЕНО КРЕМНІЄМ! Запис -20 у концепт 1 заблоковано"
        in out
    )

    assert "СЦЕНАРІЙ 4: Повернення до штатного режиму" in out
    assert (
        "[FPGA COP-GUARD] КОМІТ ПІДТВЕРДЖЕНО КРЕМНІЄМ: стан концепту 1 оновлено на 75"
        in out
    )
    assert (
        "РЕЗУЛЬТАТ: ГІБРИДНИЙ КО-ДИЗАЙН ПРОЦЕСОР+FPGA ПОВНІСТЮ ДОВЕДЕНО НА ПРАКТИЦІ!"
        in out
    )


def test_km_mcu_reactive_cascade_and_fail_closed(compiled_binary):
    """
    Verify TASK-KM-MCU-SUB-01:
    Reactive subscription dispatching, Do/Go bytecode execution, Big Dot semantics,
    and fail-closed emergency protection cascade.
    """
    res = subprocess.run(
        [compiled_binary, "--mock"], capture_output=True, text=True
    )
    assert res.returncode == 0, f"Execution failed: {res.stderr}"
    out = res.stdout

    # 1. Graph and bytecode loading verification
    assert "[+] Граф з 4 концептів, 3 підписок та 14 інструкцій Do/Go успішно завантажено!" in out

    # 2. Scenario 1: Nominal Closed-Loop Cascade C0 -> S0 -> C1 -> S1 -> C2
    assert ">>> [EXTERNAL INPUT] Подія середовища: запис C0 = 25 <<<" in out
    assert "[KM-EXEC S0] Запуск колбеку (Власник C0, фаза=1, PC=0..7)" in out
    assert "[KM-EXEC S1] Запуск колбеку (Власник C1, фаза=1, PC=8..9)" in out
    assert "C1 (HeaterPower):      50 Вт (Очікується 50 Вт)" in out
    assert "C2 (FanSpeed):         50 % (Очікується 50 %)" in out
    assert "C3 (Alarm):            0 (Очікується 0)" in out
    assert "[+] Номінальний режим: ВЕРИФІКОВАНО (Каскад S0 -> C1 -> S1 -> C2 спрацював автономно)" in out

    # 3. Scenario 2: Overheat Anomaly S0 -> C1 (Reject) -> S2 (Abort Watchdog)
    assert ">>> [EXTERNAL INPUT] Подія середовища: запис C0 = 45 <<<" in out
    assert "[KM-EXEC S2] Запуск колбеку (Власник C1, фаза=4, PC=10..13)" in out
    assert "C1 (HeaterPower):      50 Вт (Має лишитися 50 Вт!)" in out
    assert "C2 (FanSpeed):         100 % (Очікується 100 % аварійного охолодження)" in out
    assert "C3 (Alarm):            1 (Очікується 1 - Тривога!)" in out

    # 4. Scenario 3: Underflow Anomaly S0 -> C1 (Reject -20) -> S2
    assert ">>> [EXTERNAL INPUT] Подія середовища: запис C0 = 11 <<<" in out
    assert "C1 (HeaterPower):      50 Вт (Має лишитися 50 Вт!)" in out
    assert "C2 (FanSpeed):         100 % (Очікується 100 %)" in out
    assert "C3 (Alarm):            1 (Очікується 1)" in out

    # 5. Scenario 4: Recovery back to nominal operation
    assert ">>> [EXTERNAL INPUT] Подія середовища: запис C0 = 30 <<<" in out
    assert "C1 (HeaterPower):      75 Вт (Очікується 75 Вт)" in out
    assert "C2 (FanSpeed):         75 % (Очікується 75 %)" in out
    assert "C3 (Alarm):            0 (Очікується 0)" in out
    assert "[+] Штатне функціонування відновлено! (C1=75 Вт, C2=75%, C3=0)" in out

    # 6. Step count verification
    assert "Виконано всього кроків інструкцій: 44" in out
