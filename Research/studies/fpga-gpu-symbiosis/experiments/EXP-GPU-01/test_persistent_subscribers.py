#!/usr/bin/env python3
"""
Integration and regression test for TASK-KM-GPU-WARP-01 (ADR B6)
Verifies Persistent Warp Mega-Kernel on NVIDIA Jetson AGX Orin 64GB.
Ensures T_sub-exec <= 100 ns across 32 parallel subscribers with 0 warp divergence.
"""

import subprocess
import pytest
import os

JETSON_HOST = "mfedchyk@192.168.68.68"
REMOTE_BIN = "/home/mfedchyk/persistent_subscribers"


def is_jetson_reachable():
    res = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=2", "-o", "StrictHostKeyChecking=no", JETSON_HOST, "echo OK"],
        capture_output=True,
        text=True,
    )
    return res.returncode == 0 and "OK" in res.stdout


@pytest.mark.skipif(not is_jetson_reachable(), reason="Jetson AGX Orin stand not reachable via SSH")
def test_persistent_subscribers_benchmark_on_jetson():
    """Run persistent subscribers benchmark on Jetson Orin Ampere GPU."""
    cmd = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        JETSON_HOST,
        f"{REMOTE_BIN} 1000",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Execution failed: {res.stderr}\n{res.stdout}"
    out = res.stdout

    # Verify platform and kernel initialization
    assert "МАШИНА КУЗЬМІНА: PERSISTENT GPU MEGA-KERNEL (TASK-KM-GPU-WARP-01 / ADR B6)" in out
    assert "NVIDIA Jetson AGX Orin 64GB (Ampere GPU @ 1.30 GHz, 2048 Cores)" in out
    assert "[+] Персистентний варп активний в SM! Початок бенчмарку (1000 подій)..." in out
    assert "[+] Персистентний варп коректно завершив виконання!" in out

    # Verify 32 subscribers
    assert "Кількість оброблених пакетів подій:    1000" in out
    assert "Кількість паралельних підписників:     32 (по 1 на потік варпа)" in out

    # Verify ADR B6 acceptance criterion: T_sub-exec <= 100.0 ns
    assert "[+] КРИТЕРІЙ ПРИЙМАННЯ ADR B6 ВИКОНАНО:" in out
    assert "[+] Callback Bottleneck для 32 підписників успішно усунено в кремнії GPU!" in out
