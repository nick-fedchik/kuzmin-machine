"""Reproduction of Q3-DEF-01 and Q3-DEF-04 (#216, report 0.1.1).

Prints the raw observations; asserts nothing. Run from the repository root.
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DATA_DIR))
sys.path.insert(0, str(DATA_DIR / "tests"))

from kpol_reference import (  # noqa: E402
    EventInput,
    Interpreter,
    KpolError,
    Parser,
    compile_concept_microcode_bram_image,
)
from test_q3_acceptance import GOLDEN_TASK2  # noqa: E402

LITERAL = GOLDEN_TASK2.replace("on Ev when", "on Ev(p) when")
assert LITERAL != GOLDEN_TASK2

print("== Q3-DEF-01: literal 'rule R on Ev(p) when G' from kpol-cme2-profile.md section 2 item 4")
for label, source in (("golden (rule R on Ev when ...)", GOLDEN_TASK2), ("literal (rule R on Ev(p) when ...)", LITERAL)):
    try:
        module = Parser(source).parse()
        compile_concept_microcode_bram_image(module, profile="KPOL-CME-2")
        print(f"{label}: parsed and compiled")
    except KpolError as exc:
        print(f"{label}: KpolError: {exc}")

print("== Q3-DEF-04: Interpreter.run() on an invariant violation (golden task 2, S=1 -> 0 -> reject)")
module = Parser(GOLDEN_TASK2).parse()
interp = Interpreter(module)
event = module.events[0]
param = event.parameters[0][0]
interp.run([EventInput(event.name, {param: 50})])
result = interp.run([EventInput(event.name, {param: 50})])
print(f"state={dict(interp.state)}")
print(f"rejected={result.rejected!r}")
print(f"diagnostics={result.diagnostics!r}")
