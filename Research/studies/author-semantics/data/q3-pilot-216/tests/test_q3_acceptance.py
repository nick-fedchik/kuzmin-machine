"""Acceptance & negative-control tests for Q3 LLM pilot (#216)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parents[1]
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))

from tasks_and_tests import check_task1, check_task2, check_task3  # noqa: E402
from kpol_reference import KpolError  # noqa: E402

GOLDEN_TASK1 = """Problem T1 {
    Invariants { NonNeg: S >= 0; }
}
Solution T1 {
    state S: Int32 = 5;
    event Ev(p: Int32);
    rule R on Ev when p < 10 {
        set S := S + 1;
    }
}
Proof T1 {
    scenario Check {
        step Ev(p = 4);
        expect S == 6;
        step Ev(p = 10);
        expect S == 6;
    }
}
"""

GOLDEN_TASK2 = """Problem T2 {
    Invariants { NonNeg: S >= 0; }
}
Solution T2 {
    state S: Int32 = 1;
    event Ev(p: Int32);
    rule R on Ev when 0 <= p and p <= 100 {
        set S := S - 1;
    }
}
Proof T2 {
    scenario Check {
        step Ev(p = 50);
        expect S == 0;
        step Ev(p = 50);
        expect S == 0;
        step Ev(p = 101);
        expect S == 0;
    }
}
"""

GOLDEN_TASK3 = """Problem T3 {
    Invariants {
        NonNegA: A >= 0;
        NonNegB: B >= 0;
    }
}
Solution T3 {
    state A: Int32 = 0;
    state B: Int32 = 0;
    event Ev(p: Int32);
    rule R1 on Ev when p >= 10 {
        set A := A + 1;
    }
    rule R2 on change(A) when A >= 2 {
        set B := B + 1;
    }
}
Proof T3 {
    scenario Check {
        step Ev(p = 5);
        expect A == 0;
        expect B == 0;
        step Ev(p = 10);
        expect A == 1;
        expect B == 0;
        step Ev(p = 10);
        expect A == 2;
        expect B == 1;
    }
}
"""


def test_golden_solutions_pass_acceptance():
    assert check_task1(GOLDEN_TASK1)["profile"] == "KPOL-CME-1"
    assert check_task2(GOLDEN_TASK2)["profile"] == "KPOL-CME-2"
    assert check_task3(GOLDEN_TASK3)["profile"] == "KPOL-CME-2"


def test_negative_control_task1_rejects_wrong_guard_or_disallowed_op():
    # KPOL-CME-1 forbids <=
    bad_op = GOLDEN_TASK1.replace("p < 10", "p <= 10")
    with pytest.raises(KpolError, match="B3-GUARD"):
        check_task1(bad_op)

    # Wrong boundary (p < 9 fails step Ev(p=9) in acceptance)
    bad_bound = GOLDEN_TASK1.replace("p < 10", "p < 9")
    with pytest.raises(AssertionError):
        check_task1(bad_bound)


def test_negative_control_task2_rejects_wrong_range_or_missing_proof():
    # Wrong upper bound 99 instead of 100
    bad_range = GOLDEN_TASK2.replace("p <= 100", "p <= 99")
    with pytest.raises(AssertionError):
        check_task2(bad_range)

    # Missing Proof fails CME2-PROOF
    no_proof = GOLDEN_TASK2.split("Proof T2")[0]
    with pytest.raises(KpolError, match="CME2-PROOF"):
        check_task2(no_proof)


def test_negative_control_task3_rejects_operand_collision_and_start_active_cascade():
    # Operand collision: guard A >= 2 + action B + 2
    collision = GOLDEN_TASK3.replace("set B := B + 1;", "set B := B + 2;")
    with pytest.raises(KpolError, match="CME2-OPERAND-COLLISION"):
        check_task3(collision)

    # Cascade active on initial state A=0
    start_active = GOLDEN_TASK3.replace("when A >= 2", "when A >= 0")
    with pytest.raises(KpolError, match="CME2-CASCADE"):
        check_task3(start_active)


@pytest.mark.parametrize(
    "session_file",
    [
        "session-01-gemini-4-hydrogen.md",
        "session-02-claude-sonnet-5.5.md",
        "session-03-gpt-5.3-codex.md",
    ],
)
def test_pilot_sessions_acceptance(session_file: str):
    import re

    text = (DATA_DIR / "raw" / session_file).read_text(encoding="utf-8")
    blocks = re.findall(r"```kpol\n(.*?)```", text, flags=re.DOTALL)
    assert len(blocks) == 3, f"{session_file}: expected 3 kpol blocks, got {len(blocks)}"
    r1 = check_task1(blocks[0])
    r2 = check_task2(blocks[1])
    r3 = check_task3(blocks[2])
    assert r1["profile"] == "KPOL-CME-1"
    assert r2["profile"] == "KPOL-CME-2"
    assert r3["profile"] == "KPOL-CME-2"
