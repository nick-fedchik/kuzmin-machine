#!/usr/bin/env python3
"""
Unit and regression test for C99 MCU Runtime + FPGA Coprocessor Bridge
Verifies Proposal 3 (Hybrid Co-Design: ARM Cortex-A9 / MCU + FPGA Invariant Guard).
"""

import subprocess
import os
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
C_SOURCE = os.path.join(
    REPO_ROOT, "03-engineering-software", "km_mcu_fpga_bridge.c"
)
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
