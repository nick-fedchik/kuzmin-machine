#!/usr/bin/env python3
"""
HIL regression test for TASK-KM-FPGA-BRAM-01.
Verifies endogenous subscriptions and cascading transitions across 4 concepts
in the CFG-P BRAM pipeline running on Digilent PYNQ-Z1 (XC7Z020 PL silicon).
"""
import subprocess
import pytest

PYNQ_HOST = "xilinx@192.168.68.69"
REMOTE_SCRIPT = "/home/xilinx/test_bram_cascade_live.py"


def is_pynq_reachable():
    cmd = [
        "sshpass", "-p", "xilinx",
        "ssh", "-o", "ConnectTimeout=2", "-o", "StrictHostKeyChecking=no",
        PYNQ_HOST, "echo OK"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.returncode == 0 and "OK" in res.stdout


@pytest.mark.skipif(not is_pynq_reachable(), reason="PYNQ-Z1 board not reachable via SSH")
def test_bram_cascade_execution_on_pynq_silicon():
    """Verify 4-concept endogenous subscription cascade in physical FPGA BRAM."""
    cmd = [
        "sshpass", "-p", "xilinx",
        "ssh", "-o", "StrictHostKeyChecking=no",
        PYNQ_HOST, f"echo xilinx | sudo -S python3 {REMOTE_SCRIPT}"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Execution failed: {res.stderr}\n{res.stdout}"
    out = res.stdout

    # 1. Header and chip identification
    assert "МАШИНА КУЗЬМІНА: ЕНДОГЕННІ ПІДПИСКИ В АПАРАТНОМУ BRAM-КОНВЕЄРІ (CFG-P)" in out
    assert "0x4B504D43 'KPMC'" in out
    assert "Верифікація пам'яті BRAM: 100% успішно (256 слів збігаються)" in out

    # 2. Scenario 1: Autonomous cascade execution across 4 concepts
    assert "СЦЕНАРІЙ 1: Подача валідного стимулу Stimulus(p = 10 < 50)" in out
    assert "C0 (Джерело):            11" in out
    assert "C1 (Підписник 1):        1" in out
    assert "C2 (Підписник 2):        1" in out
    assert "C3 (Листовий підписник): 1" in out
    assert "(+4, очікується +4 коміти для 4 концептів!)" in out
    assert "СЦЕНАРІЙ 1 УСПІХ: Повний апаратний каскад C0 -> C1 -> C2 -> C3 відпрацював у BRAM!" in out

    # 3. Scenario 2: Fail-Closed rejection of invalid stimulus
    assert "СЦЕНАРІЙ 2: Подача невалідного стимулу Stimulus(p = 100 >= 50)" in out
    assert "(Збільшився: +1, очікується +1)" in out
    assert "СЦЕНАРІЙ 2 УСПІХ: Невалідний стимул відхилено кремнієм, каскад заблоковано!" in out

    # 4. Final verification
    assert "РЕЗУЛЬТАТ: ЕНДОГЕННІ ПІДПИСКИ В АПАРАТНОМУ BRAM-КОНВЕЄРІ ВЕРИФІКОВАНО!" in out
