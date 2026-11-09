#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Диференційний тест для експерименту AV-03:
Порівнює програмну C-реалізацію kpol_txn_gate_decision з еталонною Python-моделлю.
Перевіряє:
1. Повний перебір 2^8 = 256 комбінацій керувальних сигналів.
2. 100,000 псевдовипадкових векторів із фіксованим seed (0x4B504F4C).
Критерій: 0 розбіжностей.
"""

import ctypes
import os
import random
import subprocess
from pathlib import Path
import pytest

BENCH_DIR = Path(__file__).resolve().parent
SO_PATH = BENCH_DIR / "libkpol_gate.so"


class KpolGateInput(ctypes.Structure):
    _fields_ = [
        ("event_valid", ctypes.c_uint8),
        ("candidate_known", ctypes.c_uint8),
        ("candidate_value", ctypes.c_uint32),
        ("assumption_known", ctypes.c_uint8),
        ("assumption_true", ctypes.c_uint8),
        ("invariant_known", ctypes.c_uint8),
        ("invariant_true", ctypes.c_uint8),
        ("hazard_known", ctypes.c_uint8),
        ("hazard_true", ctypes.c_uint8),
        ("state_current", ctypes.c_uint32),
    ]


class KpolGateOutput(ctypes.Structure):
    _fields_ = [
        ("state_next", ctypes.c_uint32),
        ("committed", ctypes.c_uint8),
        ("rejected", ctypes.c_uint8),
        ("rejected_input", ctypes.c_uint8),
        ("rejected_invariant", ctypes.c_uint8),
        ("changed", ctypes.c_uint8),
        ("hazard_observed", ctypes.c_uint8),
        ("unknown_hazard", ctypes.c_uint8),
    ]


def build_shared_lib():
    """Компілює kpol_gate.c у спільну бібліотеку для ctypes."""
    cmd = [
        "gcc", "-O3", "-fPIC", "-shared",
        str(BENCH_DIR / "kpol_gate.c"),
        "-o", str(SO_PATH)
    ]
    subprocess.check_call(cmd)


def python_reference_gate(
    event_valid: int,
    candidate_known: int,
    candidate_value: int,
    assumption_known: int,
    assumption_true: int,
    invariant_known: int,
    invariant_true: int,
    hazard_known: int,
    hazard_true: int,
    state_current: int,
) -> dict:
    """Еталонна функція рішення шлюзу транзакцій KPOL за специфікацією."""
    state_next = state_current
    committed = 0
    rejected = 0
    rejected_input = 0
    rejected_invariant = 0
    changed = 0
    hazard_observed = 0
    unknown_hazard = 0

    if event_valid:
        if not hazard_known:
            unknown_hazard = 1
        elif hazard_true:
            hazard_observed = 1

        input_ok = bool(candidate_known and assumption_known and assumption_true)
        invariant_ok = bool(invariant_known and invariant_true)

        if not input_ok:
            rejected = 1
            rejected_input = 1
        elif not invariant_ok:
            rejected = 1
            rejected_invariant = 1
        else:
            state_next = candidate_value & 0xFFFFFFFF
            committed = 1
            changed = 1 if (candidate_value != state_current) else 0

    return {
        "state_next": state_next,
        "committed": committed,
        "rejected": rejected,
        "rejected_input": rejected_input,
        "rejected_invariant": rejected_invariant,
        "changed": changed,
        "hazard_observed": hazard_observed,
        "unknown_hazard": unknown_hazard,
    }


@pytest.fixture(scope="module")
def gate_lib():
    if not SO_PATH.exists():
        build_shared_lib()
    lib = ctypes.CDLL(str(SO_PATH))
    lib.kpol_txn_gate_decision.argtypes = [
        ctypes.POINTER(KpolGateInput),
        ctypes.POINTER(KpolGateOutput),
    ]
    lib.kpol_txn_gate_decision.restype = None
    return lib


def test_exhaustive_control_combinations(gate_lib):
    """Повний перебір усіх 2^8 = 256 комбінацій булевих сигналів."""
    for mask in range(256):
        event_valid = (mask >> 0) & 1
        candidate_known = (mask >> 1) & 1
        assumption_known = (mask >> 2) & 1
        assumption_true = (mask >> 3) & 1
        invariant_known = (mask >> 4) & 1
        invariant_true = (mask >> 5) & 1
        hazard_known = (mask >> 6) & 1
        hazard_true = (mask >> 7) & 1

        state_curr = 0x12345678
        cand_val = 0xDEADBEEF

        c_in = KpolGateInput(
            event_valid=event_valid,
            candidate_known=candidate_known,
            candidate_value=cand_val,
            assumption_known=assumption_known,
            assumption_true=assumption_true,
            invariant_known=invariant_known,
            invariant_true=invariant_true,
            hazard_known=hazard_known,
            hazard_true=hazard_true,
            state_current=state_curr,
        )
        c_out = KpolGateOutput()
        gate_lib.kpol_txn_gate_decision(ctypes.byref(c_in), ctypes.byref(c_out))

        py_out = python_reference_gate(
            event_valid, candidate_known, cand_val,
            assumption_known, assumption_true,
            invariant_known, invariant_true,
            hazard_known, hazard_true,
            state_curr,
        )

        assert c_out.state_next == py_out["state_next"]
        assert c_out.committed == py_out["committed"]
        assert c_out.rejected == py_out["rejected"]
        assert c_out.rejected_input == py_out["rejected_input"]
        assert c_out.rejected_invariant == py_out["rejected_invariant"]
        assert c_out.changed == py_out["changed"]
        assert c_out.hazard_observed == py_out["hazard_observed"]
        assert c_out.unknown_hazard == py_out["unknown_hazard"]


def test_pseudorandom_fuzzing(gate_lib):
    """100,000 псевдовипадкових векторів із фіксованим seed."""
    rng = random.Random(0x4B504F4C)  # "KPOL"
    c_in = KpolGateInput()
    c_out = KpolGateOutput()

    for i in range(100_000):
        ev = rng.randint(0, 1)
        ck = rng.randint(0, 1)
        cv = rng.getrandbits(32)
        ak = rng.randint(0, 1)
        at = rng.randint(0, 1)
        ik = rng.randint(0, 1)
        it = rng.randint(0, 1)
        hk = rng.randint(0, 1)
        ht = rng.randint(0, 1)
        sc = rng.getrandbits(32)

        c_in.event_valid = ev
        c_in.candidate_known = ck
        c_in.candidate_value = cv
        c_in.assumption_known = ak
        c_in.assumption_true = at
        c_in.invariant_known = ik
        c_in.invariant_true = it
        c_in.hazard_known = hk
        c_in.hazard_true = ht
        c_in.state_current = sc

        gate_lib.kpol_txn_gate_decision(ctypes.byref(c_in), ctypes.byref(c_out))

        py_out = python_reference_gate(ev, ck, cv, ak, at, ik, it, hk, ht, sc)

        if (c_out.committed != py_out["committed"] or
            c_out.rejected != py_out["rejected"] or
            c_out.state_next != py_out["state_next"] or
            c_out.unknown_hazard != py_out["unknown_hazard"] or
            c_out.hazard_observed != py_out["hazard_observed"]):
            pytest.fail(f"Розбіжність на ітерації {i}: C={c_out} != Py={py_out}")


if __name__ == "__main__":
    build_shared_lib()
    pytest.main([__file__, "-v"])
