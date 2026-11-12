#!/usr/bin/env python3
"""
Unit tests for KuzminMachineDirectMMIO (driver without .hwh)
Verifies:
1. MockMMIO register read/write and address boundaries.
2. Kernel ID reading (0x4B504F4C / 'KPOL').
3. Valid commit branch.
4. Input rejection branch (assumption not met).
5. Invariant rejection branch (candidate breaks invariant).
6. Hazard branch (fail-safe abort on hazard observation).
7. Unknown hazard branch (fail-closed when hazard unknown).
8. State retention across rejections.
"""

import os
import sys
import pytest

# Тест на mock-MMIO: перевіряє логіку драйвера без плати (не HIL).
DEPLOY_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if DEPLOY_DIR not in sys.path:
    sys.path.insert(0, DEPLOY_DIR)

from kpol_direct_mmio_driver import (
    KuzminMachineDirectMMIO,
    MockMMIO,
    EXPECTED_IDENT,
    COND_CAND_KNOWN,
    COND_ASSUMP_KNOWN,
    COND_ASSUMP_TRUE,
    COND_INV_KNOWN,
    COND_INV_TRUE,
    COND_HAZARD_KNOWN,
    COND_HAZARD_TRUE
)


@pytest.fixture
def driver():
    return KuzminMachineDirectMMIO(mock=True)


def test_ident_register(driver):
    val, s = driver.read_ident()
    assert val == EXPECTED_IDENT
    assert s == "KPOL"


def test_initial_state_zero(driver):
    assert driver.read_state() == 0


def test_valid_commit(driver):
    cond = (COND_CAND_KNOWN | COND_ASSUMP_KNOWN | COND_ASSUMP_TRUE |
            COND_INV_KNOWN | COND_INV_TRUE | COND_HAZARD_KNOWN)
    res = driver.execute_transaction(candidate=0x12345678, conditions=cond)
    assert res["done"] is True
    assert res["committed"] is True
    assert res["rejected"] is False
    assert res["changed"] is True
    assert res["new_state"] == 0x12345678
    assert driver.read_state() == 0x12345678


def test_input_reject_assump_false(driver):
    # Set initial state
    cond_valid = (COND_CAND_KNOWN | COND_ASSUMP_KNOWN | COND_ASSUMP_TRUE |
                  COND_INV_KNOWN | COND_INV_TRUE | COND_HAZARD_KNOWN)
    driver.execute_transaction(candidate=0x1000, conditions=cond_valid)

    # Now attempt transaction with assump_true = 0
    cond_bad = (COND_CAND_KNOWN | COND_ASSUMP_KNOWN |
                COND_INV_KNOWN | COND_INV_TRUE | COND_HAZARD_KNOWN)
    res = driver.execute_transaction(candidate=0x9999, conditions=cond_bad)
    assert res["committed"] is False
    assert res["rejected"] is True
    assert res["rejected_input"] is True
    assert res["new_state"] == 0x1000  # State must remain unchanged
    assert driver.read_state() == 0x1000


def test_invariant_reject(driver):
    cond_bad_inv = (COND_CAND_KNOWN | COND_ASSUMP_KNOWN | COND_ASSUMP_TRUE |
                    COND_INV_KNOWN | COND_HAZARD_KNOWN)
    res = driver.execute_transaction(candidate=0xBEEF, conditions=cond_bad_inv)
    assert res["committed"] is False
    assert res["rejected"] is True
    assert res["rejected_inv"] is True


def test_hazard_abort(driver):
    cond_hazard = (COND_CAND_KNOWN | COND_ASSUMP_KNOWN | COND_ASSUMP_TRUE |
                   COND_INV_KNOWN | COND_INV_TRUE | COND_HAZARD_KNOWN | COND_HAZARD_TRUE)
    res = driver.execute_transaction(candidate=0xDEAD, conditions=cond_hazard)
    assert res["committed"] is False
    assert res["rejected"] is True
    assert res["hazard_observed"] is True


def test_unknown_hazard_abort(driver):
    # Hazard is unknown (COND_HAZARD_KNOWN not set)
    cond_unk = (COND_CAND_KNOWN | COND_ASSUMP_KNOWN | COND_ASSUMP_TRUE |
                COND_INV_KNOWN | COND_INV_TRUE)
    res = driver.execute_transaction(candidate=0x5555, conditions=cond_unk)
    assert res["committed"] is False
    assert res["rejected"] is True
    assert res["unknown_hazard"] is True


def test_full_validation_suite(driver):
    assert driver.run_validation_suite() is True
