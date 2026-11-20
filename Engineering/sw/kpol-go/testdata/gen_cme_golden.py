#!/usr/bin/env python3
"""Generate testdata/cme_golden.json.gz for the CME-RAW-1 profile compilers of the Go port.

The reference implementation Engineering/sw/kpol-ref/kpol_reference.py is run
through compile_concept_microcode_bram_image(module, cascade_map, acl_table,
profile=...) and the observable result of each case is recorded: the error
(code and text, or the kind "crash" for an unhandled Python exception), or the
SHA-256 of the 1024-byte image, every non-zero 16-byte slot, and the slots as
decoded by the reference disassemble_concept_microcode. The modules are built
with Parser(source).parse() (as compile_kpol_bram_image.py does), so the static
gate of each profile is exercised too.

Corpus:

* every .kpol file of the repository and every ```kpol block of the Markdown
  documents, and the KPOL program strings found in the Python tests, under both
  profiles (programs the reference parser rejects are dropped: the front end has
  its own golden file);
* hand-written positive and negative cases for every condition KPOL-P1-1..10
  and KPOL-P2-1..18, and lowering matrices for KPOL-P1-11 and KPOL-P2-19; the
  intent of each is asserted while generating;
* systematic mutations of valid profile programs (thresholds, operands,
  comparison operators, types, state counts, action steps, declaration order,
  `on change` links, range bounds, presence of Proof/Hazard/Assumption);
* differential cases for acl_table and cascade_map, direct
  check_module_security_acl cases, and unsupported profile names.

Everything is deterministic (fixed seed, sorted inputs).

Usage (from Engineering/sw/kpol-go):  python3 testdata/gen_cme_golden.py
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import goldenio  # noqa: E402
REPO = HERE.parents[3]
REF_DIR = REPO / "Engineering" / "sw" / "kpol-ref"
GO_PORT_DIR = REPO / "Engineering" / "sw" / "kpol-go"
OUT = HERE / "cme_golden.json.gz"

sys.path.insert(0, str(REF_DIR))
sys.setrecursionlimit(3000)
import kpol_reference as kr  # noqa: E402

SEED = 20261121
CME1, CME2 = "KPOL-CME-1", "KPOL-CME-2"
MIN_MUTANTS = 500
MUTANTS_PER_BASE_KIND = 3


# --------------------------------------------------------------------------
# Running the reference
# --------------------------------------------------------------------------

def run_compile(module, profile, acl=None, cascade=None) -> dict:
    cascade_arg = None
    if cascade is not None:
        cascade_arg = {(int(k) if k.isdigit() else k): (int(v) if str(v).isdigit() else v) for k, v in cascade.items()}
    try:
        image = kr.compile_concept_microcode_bram_image(
            module, cascade_map=cascade_arg, acl_table=acl, profile=profile)
    except kr.KpolError as error:
        return {"ok": False, "kind": "kpol", "text": str(error)}
    except Exception as error:  # an unhandled crash of the reference
        return {"ok": False, "kind": "crash", "text": type(error).__name__}
    assert len(image) == 1024
    slots, dis = [], []
    decoded = kr.disassemble_concept_microcode(image)
    for cid in range(64):
        raw = image[cid * 16:cid * 16 + 16]
        if any(raw):
            d = decoded[cid]
            slots.append(f"{cid}:{raw.hex()}")
            dis.append([cid, d.current_state, d.operand_val, d.pred_opcode, d.guard_flags,
                        d.hazard_limit, d.action_opcode, d.subscriber_cid])
    return {"ok": True, "sha": hashlib.sha256(image).hexdigest(), "slots": slots, "dis": dis}


def run_profile_name(profile) -> dict:
    """The profile dispatch alone: a module that never reaches the profile body."""
    module = kr.Parser(BASE1).parse()
    return run_compile(module, profile)


class Corpus:
    """Cases with the source text stored once."""

    def __init__(self) -> None:
        self.sources: list[str] = []
        self._index: dict[str, int] = {}
        self.cases: list[dict] = []
        self.ids: set[str] = set()
        self.problems: list[str] = []

    def src(self, text: str) -> int:
        if text not in self._index:
            self._index[text] = len(self.sources)
            self.sources.append(text)
        return self._index[text]

    def add(self, cid: str, group: str, source: str, profile: str, *, acl=None, cascade=None,
            rule: str | None = None, pol: str | None = None, expect: str | None = None,
            strip_alias_flag: bool = False) -> dict | None:
        """Run the reference on `source`; returns None if its parser rejects the source."""
        try:
            module = kr.Parser(source).parse()
        except kr.KpolError as error:
            if pol is not None:
                self.problems.append(f"{cid}: hand-written source does not parse: {error}")
            return None
        except Exception:
            return None
        if strip_alias_flag:
            module = dataclasses.replace(module, phase_aliases_used=False)
        result = run_compile(module, profile, acl, cascade)
        # the declared intent of a hand-written case must hold for the reference
        if pol == "pos" and not result["ok"]:
            self.problems.append(f"{cid}: expected acceptance, got {result}")
        if pol == "neg" and (result["ok"] or not result["text"].startswith(expect or "")):
            self.problems.append(f"{cid}: expected {expect!r}, got {result}")
        if pol == "crash":
            if result.get("kind") != "crash":
                self.problems.append(f"{cid}: expected a reference crash, got {result}")
            pol = "neg"
        assert cid not in self.ids, cid
        self.ids.add(cid)
        case = {"id": cid, "group": group, "src": self.src(source), "profile": profile,
                "acl": acl, "cascade": cascade, "result": result}
        if rule is not None:
            case["rule"] = rule
            case["pol"] = pol
        if strip_alias_flag:
            case["strip_alias_flag"] = True
        self.cases.append(case)
        return case


# --------------------------------------------------------------------------
# Program templates
# --------------------------------------------------------------------------

def mod(name="M", inv=("NonNeg: S >= 0;",), problem_extra="", sol="", proof=None) -> str:
    inv_block = ("Invariants { " + " ".join(inv) + " }") if inv else ""
    text = f"Problem {name} {{ {problem_extra} {inv_block} }}\nSolution {name} {{\n{sol}\n}}\n"
    if proof is not None:
        text += f"Proof {name} {{ {proof} }}\n"
    return text


def p1(guard="P < 20", action="S + 1", initial="10", rule="Step", proof=None, inv=("NonNeg: S >= 0;",),
       problem_extra="", extra_decl="", state_type="Int32", param_type="Int32", on="on E", param="P") -> str:
    sol = (f"state S: {state_type} = {initial};\n{extra_decl}event E({param}: {param_type});\n"
           f"rule {rule} {on} when {guard} {{ set S := {action}; }}")
    return mod(inv=inv, problem_extra=problem_extra, sol=sol, proof=proof)


P1_PROOF = "scenario Trace { step E(P = 5); expect S == 11; step E(P: 25); expect S == 11; }"
BASE1 = p1(proof=P1_PROOF)


def p2(states=(("A", "0"), ("B", "0")), events=(("E", "x"),), rules=None, proof="default", inv="default",
       problem_extra="", name="M") -> str:
    """A KPOL-CME-2 program. Defaults: A is driven by E, B follows A through `on change(A)`."""
    if rules is None:
        rules = ["rule RA on E when x < 50 { set A := A + 1; }",
                 "rule RB on change(A) when A > 0 { set B := B + 1; }"]
    if inv == "default":
        inv = tuple(f"I{n}: {n} >= 0;" for n, _ in states)
    sol = "\n".join(f"state {n}: Int32 = {v};" for n, v in states) + "\n"
    sol += "\n".join(f"event {n}({p}: Int32);" for n, p in events) + "\n" + "\n".join(rules)
    if proof == "default":
        proof = ("scenario T { step E(x = 1); expect A == 1; expect B == 1; "
                 "step E(x = 100); expect A == 1; expect B == 1; }")
    return mod(name=name, inv=inv, problem_extra=problem_extra, sol=sol, proof=proof)


BASE2 = p2()


def chain(n: int, tail_guard="true") -> str:
    """A cascade chain C0 <- E, C1 <- change(C0), ... of n states."""
    states = tuple((f"C{i}", "0") for i in range(n))
    rules = ["rule R0 on E when x < 50 { set C0 := C0 + 1; }"]
    for i in range(1, n):
        rules.append(f"rule R{i} on change(C{i - 1}) when C{i - 1} > 0 {{ set C{i} := C{i} + 1; }}")
    steps = "step E(x = 1); " + " ".join(f"expect C{i} == 1;" for i in range(n))
    return p2(states=states, rules=rules, proof=f"scenario T {{ {steps} }}")


def many_states(n: int) -> str:
    """n independent states, each with its own event."""
    states = tuple((f"S{i}", str(i)) for i in range(n))
    events = tuple((f"E{i}", f"p{i}") for i in range(n))
    rules = [f"rule R{i} on E{i} {{ set S{i} := S{i} + 1; }}" for i in range(n)]
    return p2(states=states, events=events, rules=rules,
              proof="scenario T { step E0(p0 = 1); expect S0 == 1; }")


# --------------------------------------------------------------------------
# Hand-written cases
# --------------------------------------------------------------------------

def hand_cases(c: Corpus) -> None:
    n = [0]

    def case(rule, pol, profile, source, expect=None, **kw):
        n[0] += 1
        cid = f"hand:{rule}:{pol}:{n[0]:03d}"
        c.add(cid, "hand", source, profile, rule=rule, pol=pol, expect=expect, **kw)

    # ---- KPOL-CME-1 ---------------------------------------------------------
    case("P1-1", "pos", CME1, BASE1)
    case("P1-1", "neg", CME1, p1(initial="true"), "B3-TYPE")
    case("P1-1", "neg", CME1, p1(guard="P"), "B3-TYPE")
    case("P1-1", "neg", CME1, p1(action="Q"), "B3-TYPE")
    case("P1-1", "neg", CME1, p1(proof="scenario T { step E(P = 1); expect S == 99999999999 + true; }"), "B3-TYPE")

    case("P1-2", "pos", CME1, BASE1, cascade=None)
    for cm in ({}, {"S": "T"}, {"S": "1"}, {"0": "1"}):
        case("P1-2", "neg", CME1, BASE1, "B3-SHAPE", cascade=cm)

    case("P1-3", "pos", CME1, p1())
    case("P1-3", "neg", CME1, p1(extra_decl="state T: Int32 = 1;\n"), "B3-SHAPE")
    case("P1-3", "neg", CME1, p1(extra_decl="event F();\n"), "B3-SHAPE")
    case("P1-3", "neg", CME1, p1().replace("rule Step", "rule Other on E { set S := S - 1; } rule Step"), "B3-SHAPE")
    case("P1-3", "neg", CME1, p1(state_type="Bool", initial="false", action="true", inv=("NonNeg: S == false;",)), "B3-")
    case("P1-3", "neg", CME1, p1(state_type="U32"), "B3-")
    case("P1-3", "neg", CME1, p1(param_type="Bool", guard="true"), "B3-SHAPE")
    case("P1-3", "neg", CME1, p1(param_type="U64", guard="true"), "B3-SHAPE")
    case("P1-3", "neg", CME1, p1().replace("(P: Int32)", "(P: Int32, Q: Int32)"), "B3-SHAPE")
    case("P1-3", "neg", CME1, p1().replace("(P: Int32)", "()").replace("P < 20", "true"), "B3-SHAPE")

    for init, ok in (("0", True), ("10", True), ("2147483647", True), ("-0", True), ("-1", False),
                     ("2147483648", False), ("5 + 5", False), ("Unknown", False), ("--1", False),
                     ("-(1)", False), ("1.0", False), ("-2147483648", False)):
        if ok:
            case("P1-4", "pos", CME1, p1(initial=init))
        else:
            case("P1-4", "neg", CME1, p1(initial=init), "B3-")

    case("P1-5", "pos", CME1, p1(rule="Whatever"))
    case("P1-5", "neg", CME1, p1(on="on change(S)", guard="true"), "B3-SHAPE")
    case("P1-5", "neg", CME1, p1(on="on reject E"), "B3-SHAPE")
    case("P1-5", "neg", CME1, p1().replace("rule Step on E when P < 20", "rule Step on E when P < 20 covers H"), "B3-")
    case("P1-5", "neg", CME1, p1(extra_decl="state T: Int32 = 1;\n").replace("set S := S + 1;", "set T := T + 1;"), "B3-SHAPE")
    case("P1-5", "neg", CME1, p1().replace("set S := S + 1;", "set S := S + 1; set S := S + 1;"), "B3-SHAPE")
    case("P1-5", "neg", CME1, p1().replace("set S := S + 1;", ""), "B3-SHAPE")

    case("P1-6", "pos", CME1, p1())
    case("P1-6", "pos", CME1, p1(inv=("NonNeg: S >= 0.0;",)))
    case("P1-6", "neg", CME1, p1(inv=("NonNeg: S >= false;",)), "B3-TYPE")
    case("P1-6", "neg", CME1, p1(inv=("NonNeg: 0 <= S;",)), "B3-INVARIANT")
    case("P1-6", "neg", CME1, p1(inv=("NonNeg: S > 0;",)), "B3-INVARIANT")
    case("P1-6", "neg", CME1, p1(inv=("NonNeg: S >= 1;",)), "B3-INVARIANT")
    case("P1-6", "neg", CME1, p1(inv=()), "B3-INVARIANT")
    case("P1-6", "neg", CME1, p1(inv=("A: S >= 0;", "B: S >= 0;")), "B3-INVARIANT")
    case("P1-6", "neg", CME1, p1(problem_extra="Goals { G: S > 0; }"), "B3-INVARIANT")
    case("P1-6", "neg", CME1, p1(problem_extra="Assumptions { A: S >= 0; }", inv=()), "B3-INVARIANT")
    case("P1-6", "neg", CME1, p1(inv=("NonNeg: S + 0 >= 0;",)), "B3-INVARIANT")

    case("P1-7", "pos", CME1, p1(action="S - 1"))
    for act in ("S + 2", "S - 2", "1 + S", "S * 1", "42", "P", "S + 0", "S + 1 + 0", "S + P", "S - -1", "1 - S"):
        case("P1-7", "neg", CME1, p1(action=act), "B3-")
    case("P1-7", "neg", CME1, p1(action="S + 1.0"), "B3-ACTION")

    for guard, ok in (("true", True), ("P < 0", True), ("P > -5", True), ("P == 2147483647", True),
                      ("P != -2147483648", True), ("P < 2147483648", False), ("P < -2147483649", False),
                      ("false", False), ("S < 20", False), ("20 > P", False), ("P >= 5", False),
                      ("P <= 5", False), ("P < 10 + 10", False), ("P < 20 and P > 0", False),
                      ("not (P < 20)", False), ("not true", False), ("P < Unknown", False), ("P == P", False)):
        if ok:
            case("P1-8", "pos", CME1, p1(guard=guard))
        else:
            case("P1-8", "neg", CME1, p1(guard=guard), "B3-")

    case("P1-9", "pos", CME1, p1(proof=P1_PROOF))
    case("P1-9", "pos", CME1, p1(proof="scenario A { step E(P = 1); expect S == 11; } scenario B { step E(P = 2); expect S == 11; }"))
    case("P1-9", "pos", CME1, p1(), cascade=None)
    for proof in ("", "scenario Empty {}", "scenario NoExpect { step E(P = 5); }",
                  "scenario Before { expect S == 10; step E(P = 5); }",
                  "assert A on E expect S >= 0;",
                  P1_PROOF.replace("S == 11", "S == 12"),
                  P1_PROOF.replace("P = 5", "P = Unknown"),
                  P1_PROOF.replace("S == 11", "S >= 0"),
                  P1_PROOF.replace("S == 11", "S == 10 + 1"),
                  "scenario NoStep { expect S == 10; }",
                  "scenario W { step E(Q = 5); expect S == 11; }",
                  "scenario W { step E(P = 5, P = 6); expect S == 11; }",
                  "scenario W { step E(P = 5 + 1); expect S == 11; }",
                  "scenario W { step E(P = 5); expect 11 == S; }",
                  "scenario W { step E(P = 5); expect S == 11; expect S == 11; } assert A on E expect true;",
                  "scenario W { step E(P = 2147483648); expect S == 11; }",
                  "scenario W { step E(P = 5); expect S == 2147483648; }",
                  "scenario W { step E(P = 5); expect S == -(1); }"):
        case("P1-9", "neg", CME1, p1(proof=proof), "B3-")
    case("P1-9", "neg", CME1, p1(proof=P1_PROOF.replace("expect S == 11; step", "expect S == 11; expect S == 99; step")), "B3-PROOF")

    case("P1-10", "pos", CME1, BASE1, acl={"S": 3})
    case("P1-10", "pos", CME1, BASE1, acl={"Other": 0})
    case("P1-10", "pos", CME1, BASE1, acl={})
    case("P1-10", "neg", CME1, BASE1, "B3-ACL", acl={"S": 1})
    case("P1-10", "neg", CME1, BASE1, "B3-ACL", acl={"S": 0})
    case("P1-10", "neg", CME1, p1(proof=P1_PROOF.replace("S == 11", "S == 12")), "B3-PROOF", acl={"S": 0})

    # ---- KPOL-CME-1 lowering (KPOL-P1-11) ---------------------------------------
    for guard in ("true", "P < 20", "P > 20", "P == 20", "P != 20", "P < -1", "P > -2147483648", "P == 2147483647"):
        for action in ("S + 1", "S - 1"):
            for init in ("0", "10", "2147483647"):
                case("P1-11", "pos", CME1, p1(guard=guard, action=action, initial=init))

    # ---- KPOL-CME-2 ---------------------------------------------------------
    case("P2-1", "pos", CME2, BASE2)
    case("P2-1", "neg", CME2, p2(states=(("A", "true"), ("B", "0"))), "CME2-TYPE")
    case("P2-1", "neg", CME2, p2(rules=["rule RA on E when x < 50 { set A := A + 1; }",
                                        "rule RB on change(A) when A > 0 { set B := Q; }"]), "CME2-TYPE")

    case("P2-2", "pos", CME2, BASE2, cascade=None)
    for cm in ({}, {"A": "B"}, {"0": "1"}):
        case("P2-2", "neg", CME2, BASE2, "CME2-CASCADE", cascade=cm)

    alias2 = p2(rules=["rule RA on E when • (x >= 50) { set A := A + 1; }",
                       "rule RB on change(A) when A > 0 { set B := B + 1; }"],
                proof="scenario T { step E(x = 1); expect A == 1; expect B == 1; }")
    case("P2-3", "pos", CME2, p2(rules=["rule RA on E when not (x >= 50) { set A := A + 1; }",
                                        "rule RB on change(A) when A > 0 { set B := B + 1; }"],
                                  proof="scenario T { step E(x = 1); expect A == 1; expect B == 1; }"))
    case("P2-3", "neg", CME2, alias2, "CME2-GUARD")
    case("P2-3", "neg", CME2, alias2.replace("•", "(*)"), "CME2-GUARD")
    case("P2-3", "pos", CME2, alias2, strip_alias_flag=True)  # a linked triad does not carry the alias flag

    case("P2-4", "pos", CME2, BASE2)
    case("P2-4", "neg", CME2, p2(problem_extra="Hazards { H on E to Flag: x > 100; }",
                                 states=(("A", "0"), ("B", "0"), ("Flag", "0")),
                                 ).replace("state Flag: Int32 = 0;", "state Flag: Bool = false;"), "CME2-")
    case("P2-4", "neg", CME2, p2(problem_extra="Assumptions { Ok: A >= 0; }"), "CME2-GUARD")
    case("P2-4", "neg", CME2, p2(problem_extra="Goals { G: A >= 0; }"), "CME2-INVARIANT")
    case("P2-4", "neg", CME2, p2(problem_extra="Alerts { Al on E: x > 100; }"), "CME2-INVARIANT")

    for n_states, ok in ((1, True), (2, True), (7, True), (64, True), (65, False)):
        text = many_states(n_states)
        if ok:
            case("P2-5", "pos", CME2, text)
        else:
            case("P2-5", "neg", CME2, text, "CME2-SHAPE")
    case("P2-5", "neg", CME2, mod(inv=(), sol="event E(x: Int32);"), "CME2-SHAPE")
    for init, ok in (("0", True), ("2147483647", True), ("-0", True), ("-1", False), ("2147483648", False),
                     ("1 + 1", False), ("Unknown", False), ("1.0", False)):
        text = p2(states=(("A", init),), rules=["rule RA on E when x < 50 { set A := A + 1; }"],
                  proof="scenario T { step E(x = 100); expect A >= 0; }")
        if ok:
            case("P2-5", "pos", CME2, text)
        else:
            case("P2-5", "neg", CME2, text, "CME2-")
    case("P2-5", "neg", CME2, p2(states=(("A", "0"), ("B", "0"))).replace("state B: Int32 = 0;", "state B: U32 = 0;"), "CME2-TYPE")
    case("P2-5", "neg", CME2, p2(states=(("A", "0"), ("B", "0"))).replace("state B: Int32 = 0;", "state B: Float<V> = 0.0;"), "CME2-")
    case("P2-5", "neg", CME2, p2(states=(("A", "0"), ("B", "0"))).replace("state B: Int32 = 0;", "state B: Pin<In> = 0;"), "CME2-")

    case("P2-6", "pos", CME2, p2(states=(("A", "0"), ("B", "0")), events=(("E", "x"),)))
    nostep = p2(proof="scenario T { expect A == 0; }")
    case("P2-6", "neg", CME2, nostep.replace("event E(x: Int32);", "event E(x: Int32, y: Int32);"), "CME2-SHAPE")
    case("P2-6", "neg", CME2, nostep.replace("event E(x: Int32);", "event E();").replace("x < 50", "true"), "CME2-SHAPE")
    case("P2-6", "neg", CME2, BASE2.replace("event E(x: Int32);", "event E(x: Bool);").replace("x < 50", "true"), "CME2-TYPE")
    case("P2-6", "neg", CME2, BASE2.replace("event E(x: Int32);", "event E(x: U32);"), "CME2-TYPE")
    case("P2-6", "neg", CME2, p2(events=(("E", "A"),)).replace("x < 50", "A < 50"), "CME2-")

    case("P2-7", "pos", CME2, BASE2)
    case("P2-7", "neg", CME2, BASE2.replace("on E when x < 50", "on reject E when x < 50"), "CME2-SHAPE")
    case("P2-7", "neg", CME2, BASE2.replace("set A := A + 1;", "set A := A + 1; set B := B + 1;"), "CME2-SHAPE")
    case("P2-7", "neg", CME2, BASE2.replace("set A := A + 1;", ""), "CME2-SHAPE")
    case("P2-7", "neg", CME2, BASE2.replace("rule RB on change(A) when A > 0 { set B := B + 1; }",
                                              "rule RB on change(A) when A > 0 { set A := A + 1; }"), "CME2-")
    case("P2-7", "neg", CME2, BASE2.replace("rule RB on change(A) when A > 0 { set B := B + 1; }", ""), "CME2-SHAPE")
    case("P2-7", "neg", CME2, BASE2.replace("}\n}\nProof", "}\nrule RC on change(A) when A > 100 { set B := B + 2; }\n}\nProof"), "CME2-SHAPE")
    case("P2-7", "neg", CME2, BASE2.replace("rule RB on change(A) when A > 0 { set B := B + 1; }",
                                              "rule RB on change(A) when A > 0 covers H { set B := B + 1; }"), "CME2-")

    case("P2-8", "pos", CME2, BASE2)
    case("P2-8", "neg", CME2, p2(states=(("A", "0"), ("B", "0"), ("C", "0")),
                                 rules=["rule RA on E when x < 50 { set A := A + 1; }",
                                        "rule RB on change(A, C) when A > 0 { set B := B + 1; }",
                                        "rule RC on E2 { set C := C + 1; }"],
                                 events=(("E", "x"), ("E2", "y")),
                                 proof="scenario T { step E(x = 1); expect A == 1; }"), "CME2-SHAPE")
    case("P2-8", "neg", CME2, BASE2.replace("event E(x: Int32);", "event E(x: Int32);\nevent F(y: Int32);"), "CME2-SHAPE")
    case("P2-8", "neg", CME2, p2(states=(("A", "0"), ("B", "0")),
                                 rules=["rule RA on E when x < 50 { set A := A + 1; }",
                                        "rule RB on E when x > 50 { set B := B + 1; }"],
                                 proof="scenario T { step E(x = 1); expect A == 1; }"), "CME2-SHAPE")
    case("P2-8", "neg", CME2, BASE2.replace("on change(A) when A > 0", "on change(A, A) when A > 0"), "CME2-SHAPE")

    case("P2-9", "pos", CME2, BASE2.replace("IA: A >= 0;", "IA: 0 <= A;"))
    case("P2-9", "pos", CME2, BASE2.replace("IA: A >= 0; IB: B >= 0;", "IB: 0 <= B; IA: A >= 0;"))
    case("P2-9", "neg", CME2, p2(inv=("IA: A >= 0;",)), "CME2-INVARIANT")
    case("P2-9", "neg", CME2, p2(inv=("IA: A >= 0;", "IB: B >= 0;", "IC: A >= 0;")), "CME2-INVARIANT")
    case("P2-9", "neg", CME2, p2(inv=("IA: A >= 0;", "IB: B > 0;")), "CME2-INVARIANT")
    case("P2-9", "neg", CME2, p2(inv=("IA: A >= 0;", "IB: B >= 1;")), "CME2-INVARIANT")
    case("P2-9", "neg", CME2, p2(inv=("IA: A >= 0;", "IB: B >= 0.0;")), "CME2-INVARIANT")
    case("P2-9", "neg", CME2, p2(inv=("IA: A >= 0;", "IB: B >= false;")), "CME2-")
    case("P2-9", "neg", CME2, p2(inv=("IA: A >= 0;", "IB: 0.0 <= B;")), "CME2-INVARIANT")
    case("P2-9", "neg", CME2, p2(inv=("IA: A >= 0;", "IB: B >= 0 and true;")), "CME2-INVARIANT")
    case("P2-9", "neg", CME2, p2(inv=("IA: A >= 0;", "IB: A <= 0;")), "CME2-INVARIANT")

    case("P2-10", "pos", CME2, chain(4))
    case("P2-10", "pos", CME2, chain(64))
    case("P2-10", "neg", CME2, p2(rules=["rule RA on change(A) when A > 100 { set A := A + 1; }",
                                         "rule RB on E when x < 50 { set B := B + 1; }"],
                                  proof="scenario T { step E(x = 1); expect B == 1; }"), "CME2-CASCADE")
    case("P2-10", "neg", CME2, p2(states=(("A", "0"), ("B", "0"), ("C", "0")),
                                  rules=["rule RA on E when x < 50 { set A := A + 1; }",
                                         "rule RB on change(A) when A > 0 { set B := B + 1; }",
                                         "rule RC on change(A) when A > 0 { set C := C + 1; }"],
                                  proof="scenario T { step E(x = 1); expect A == 1; }"), "CME2-CASCADE")
    case("P2-10", "neg", CME2, p2(rules=["rule RA on change(B) when B > 100 { set A := A + 1; }",
                                         "rule RB on change(A) when A > 100 { set B := B + 1; }"],
                                  events=(), proof="scenario T { expect A == 0; }"), "CME2-")
    case("P2-10", "neg", CME2, p2(states=(("A", "0"), ("B", "0"), ("C", "0")), events=(("E", "x"),),
                                  rules=["rule RA on change(C) when C > 100 { set A := A + 1; }",
                                         "rule RB on change(A) when A > 100 { set B := B + 1; }",
                                         "rule RC on change(B) when B > 100 { set C := C + 1; }"],
                                  proof="scenario T { expect A == 0; }"), "CME2-")
    case("P2-10", "neg", CME2, p2(states=(("A", "0"), ("B", "0"), ("C", "0")), events=(("E", "x"),),
                                  rules=["rule RA on E when x < 50 { set A := A + 1; }",
                                         "rule RB on change(A) when A > 100 { set B := B + 1; }",
                                         "rule RC on change(C) when C > 100 { set C := C + 1; }"],
                                  proof="scenario T { step E(x = 1); expect A == 1; }"), "CME2-CASCADE")

    guard_ok = ["true", "false", "x < 5", "x > 5", "x == 5", "x != 5", "x >= 5", "x <= 5", "5 < x", "5 >= x",
                "not (x < 5)", "not not (x < 5)", "not true", "not false", "x >= -5 and x <= 5", "x > 0 and x < 100",
                "x <= 5 and x >= -5", "not (x >= 10 and x <= 20)", "x < 2147483647", "x > -2147483648",
                "5 == x", "5 != x", "-5 < x"]
    # guard forms are checked together with a Proof that is valid for any guard value
    for g in guard_ok:
        proof = "scenario T { step E(x = 7); expect A >= 0; step E(x = 100); expect A >= 0; step E(x = -3); expect A >= 0; }"
        case("P2-11", "pos", CME2, p2(states=(("A", "0"),), rules=[f"rule RA on E when {g} {{ set A := A + 1; }}"], proof=proof))
    for g, code in (("x < y", "CME2-TYPE"), ("x + 1 < 5", "CME2-GUARD"), ("x < 5 or x > 9", "CME2-GUARD"),
                    ("x", "CME2-"), ("A < 5", "CME2-GUARD"), ("x < 2147483648", "CME2-TYPE"),
                    ("x > -2147483649", "CME2-TYPE"), ("x < 1.5", "CME2-"), ("x < 5.0", "CME2-GUARD"),
                    ("x == x", "CME2-GUARD"), ("-x < 5", "CME2-GUARD"), ("not (x < 5) and x > 1", "CME2-GUARD"),
                    ("x > 1 and x < 5 and x < 9", "CME2-GUARD"), ("x == 1 and x < 5", "CME2-RANGE"),
                    ("x > 1 and x > 5", "CME2-RANGE"), ("x < 1 and x < 5", "CME2-RANGE"), ("x != 1 and x < 5", "CME2-RANGE"),
                    ("x > 1 and y < 5", "CME2-TYPE"), ("(x > 1) and (x < 5)", None), ("x > Unknown", "CME2-"),
                    ("Unknown", "CME2-")):
        proof = "scenario T { step E(x = 7); expect A >= 0; }"
        src = p2(states=(("A", "0"),), rules=[f"rule RA on E when {g} {{ set A := A + 1; }}"], proof=proof)
        if code is None:
            case("P2-11", "pos", CME2, src)
        else:
            case("P2-11", "neg", CME2, src, code)

    for g, ok in (("x >= -32768 and x <= 32767", True), ("x > -32769 and x < 32768", True),
                  ("x >= -32768 and x < 32768", True), ("x >= 5 and x <= 5", True), ("x > 4 and x < 6", True),
                  ("x >= 0 and x <= 0", True), ("x >= -1 and x <= -1", True), ("x > -32769 and x <= 32767", True),
                  ("x >= -32769 and x <= 5", False), ("x >= 0 and x <= 32768", False), ("x >= 6 and x <= 5", False),
                  ("x > 5 and x < 6", False), ("x > 5 and x < 7", True), ("x >= 100000 and x <= 200000", False),
                  ("x > 5 and x < -2147483648", False), ("x > -5 and x < -2147483648", False),
                  ("x > 32767 and x < 32768", False), ("x >= 32767 and x <= 32767", True),
                  ("x >= -32768 and x <= -32768", True), ("10 > x and 2 <= x", True), ("x <= 7 and 3 < x", True)):
        proof = "scenario T { step E(x = 7); expect A >= 0; }"
        src = p2(states=(("A", "0"),), rules=[f"rule RA on E when {g} {{ set A := A + 1; }}"], proof=proof)
        if ok:
            case("P2-12", "pos", CME2, src)
        else:
            case("P2-12", "neg", CME2, src, "CME2-RANGE")

    act_ok = ["A + 1", "A - 1", "A + 2", "A - 2", "1 + A", "7 + A", "A + 2147483647", "A - 2147483647", "x"]
    for a in act_ok:
        proof = "scenario T { step E(x = 7); expect A >= 0; }"
        case("P2-13", "pos", CME2, p2(states=(("A", "0"),), rules=[f"rule RA on E when true {{ set A := {a}; }}"], proof=proof))
    for a, code in (("5", "CME2-ACTION"), ("A + 0", "CME2-ACTION"), ("A - 0", "CME2-ACTION"), ("A + 2147483648", "CME2-"),
                    ("2 - A", "CME2-ACTION"), ("A * 2", "CME2-ACTION"), ("A + x", "CME2-ACTION"), ("A + A", "CME2-ACTION"),
                    ("x + 1", "CME2-ACTION"), ("A + -1", "CME2-ACTION"), ("A - -1", "CME2-ACTION"), ("0", "CME2-ACTION"),
                    ("B", "CME2-"), ("A / 1", "CME2-"), ("-A", "CME2-"), ("A + 1.0", "CME2-ACTION"),
                    ("A + 1 + 1", "CME2-ACTION"), ("x + A", "CME2-ACTION")):
        proof = "scenario T { step E(x = 7); expect A >= 0; }"
        case("P2-13", "neg", CME2, p2(states=(("A", "0"),), rules=[f"rule RA on E when true {{ set A := {a}; }}"], proof=proof), code)

    # a change rule may assign the watched value
    asg = p2(rules=["rule RA on E when x < 50 { set A := A + 1; }", "rule RB on change(A) when A > 0 { set B := A; }"],
             proof="scenario T { step E(x = 1); expect B == 1; }")
    case("P2-13", "pos", CME2, asg)
    case("P2-14", "pos", CME2, BASE2)
    case("P2-14", "pos", CME2, chain(3))
    case("P2-14", "neg", CME2, p2(rules=["rule RA on E when x < 50 { set A := x; }",
                                         "rule RB on change(A) when A > 0 { set B := B + 1; }"],
                                  proof="scenario T { step E(x = 1); expect A == 1; }"), "CME2-CASCADE")
    case("P2-14", "pos", CME2, p2(rules=["rule RA on E when true { set A := A + 3; }",
                                         "rule RB on change(A) when A > 0 { set B := B + 1; }"],
                                  proof="scenario T { step E(x = 1); expect A == 3; expect B == 1; }"))

    case("P2-15", "pos", CME2, BASE2)
    case("P2-15", "pos", CME2, p2(states=(("A", "0"), ("B", "0")),
                                  rules=["rule RA on E when x < 50 { set A := A + 1; }",
                                         "rule RB on change(A) when A == 7 { set B := B + 1; }"],
                                  proof="scenario T { step E(x = 1); expect A == 1; }"))
    for g in ("A >= 0", "A <= 0", "A == 0", "true", "not (A != 0)", "A >= 0 and A <= 5", "A != 3"):
        case("P2-15", "neg", CME2, p2(rules=["rule RA on E when x < 50 { set A := A + 1; }",
                                             f"rule RB on change(A) when {g} {{ set B := B + 1; }}"],
                                      proof="scenario T { step E(x = 1); expect A == 1; }"), "CME2-")
    case("P2-15", "pos", CME2, p2(states=(("A", "5"), ("B", "0")),
                                  rules=["rule RA on E when x < 50 { set A := A + 1; }",
                                         "rule RB on change(A) when A < 5 { set B := B + 1; }"],
                                  proof="scenario T { step E(x = 1); expect A == 6; }"))

    case("P2-16", "pos", CME2, p2(states=(("A", "0"),), rules=["rule RA on E when true { set A := A + 5; }"],
                                  proof="scenario T { step E(x = 1); expect A == 5; }"))
    case("P2-16", "pos", CME2, p2(states=(("A", "0"),), rules=["rule RA on E when x < 50 { set A := A + 1; }"],
                                  proof="scenario T { step E(x = 1); expect A == 1; }"))
    for g in ("x < 50", "x == 1", "x >= 0", "x > 0 and x < 99", "5 > x", "not (x == 3)"):
        for a in ("A + 5", "A - 5", "5 + A"):
            text = p2(states=(("A", "9"),), rules=[f"rule RA on E when {g} {{ set A := {a}; }}"],
                      proof="scenario T { step E(x = 1); expect A >= 0; }")
            case("P2-16", "neg", CME2, text, "CME2-OPERAND-COLLISION")
    for g in ("true", "false", "not true"):
        case("P2-16", "pos", CME2, p2(states=(("A", "9"),), rules=[f"rule RA on E when {g} {{ set A := A + 5; }}"],
                                      proof="scenario T { step E(x = 1); expect A >= 0; }"))

    proof_ok = "scenario T { step E(x = 1); expect A == 1; expect B == 1; step E(x = 100); expect A == 1; expect B == 1; }"
    case("P2-17", "pos", CME2, p2(proof=proof_ok))
    case("P2-17", "pos", CME2, p2(proof="assert Inc on E when x < 50 expect A >= 1; scenario T { step E(x = 1); expect A == 1; }"))
    case("P2-17", "neg", CME2, p2(proof=None), "CME2-PROOF")
    case("P2-17", "neg", CME2, p2(proof=""), "CME2-PROOF")
    case("P2-17", "neg", CME2, p2(proof=proof_ok.replace("expect B == 1; step", "expect B == 9; step")), "CME2-PROOF")
    case("P2-17", "pos", CME2, p2(proof="scenario T { expect A == 0; }"))
    case("P2-17", "neg", CME2, p2(proof="scenario T { step E(x = 1); }"), "CME2-PROOF")
    case("P2-17", "neg", CME2, p2(proof="scenario T { }"), "CME2-PROOF")
    case("P2-17", "neg", CME2, p2(proof="assert Never on E when x > 1000 expect A >= 1; scenario T { step E(x = 1); expect A == 1; }"), "CME2-PROOF")
    case("P2-17", "neg", CME2, p2(proof="scenario T { step E(x = 1); expect A == 2; }"), "CME2-PROOF")
    case("P2-17", "pos", CME2, p2(proof="scenario T { step E(x = Unknown); expect A == 0; }"))
    # the reference crashes (float + Decimal inside verify_module): the Go port returns a coded error
    case("P2-17", "crash", CME2, p2(proof="scenario T { step E(x = 5 / 2 + 1.0); expect A == 1; }"))
    case("P2-17", "neg", CME2, p2(proof="scenario T { step E(x = 2147483647 + 1); expect A == 1; }"), "CME2-")

    for acl, ok in (({"A": 3, "B": 3}, True), ({"A": 3}, True), ({"Z": 0}, True), ({}, True), ({"A": 2}, True),
                    ({"A": 0x82}, True), ({"A": 1}, False), ({"B": 0}, False), ({"A": 0, "B": 0}, False),
                    ({"A": 1, "B": 1}, False), ({"A": 0x80}, False), ({"B": -1}, True), ({"A": -2}, True)):
        if ok:
            case("P2-18", "pos", CME2, BASE2, acl=acl)
        else:
            case("P2-18", "neg", CME2, BASE2, "CME2-ACL", acl=acl)
    case("P2-18", "neg", CME2, p2(proof=None), "CME2-PROOF", acl={"A": 0})

    # ---- KPOL-CME-2 lowering (KPOL-P2-19) -----------------------------------------
    for op in ("==", "!=", "<", ">", ">=", "<="):
        for k in ("0", "1", "-1", "100", "2147483647", "-2147483648"):
            for wrap in ("{}", "not ({})", "not not ({})"):
                g = wrap.format(f"x {op} {k}")
                case("P2-19", "pos", CME2, p2(states=(("A", "3"),), rules=[f"rule RA on E when {g} {{ set A := A + 1; }}"],
                                               proof="scenario T { step E(x = 7); expect A >= 0; }"))
    for op in ("==", "!=", "<", ">", ">=", "<="):
        case("P2-19", "pos", CME2, p2(states=(("A", "3"),), rules=[f"rule RA on E when 42 {op} x {{ set A := A + 1; }}"],
                                       proof="scenario T { step E(x = 7); expect A >= 0; }"))
    for lo, hi in ((-32768, 32767), (0, 0), (-1, 1), (5, 20), (-100, -50), (32767, 32767), (-32768, -32768)):
        for wrap in ("{}", "not ({})"):
            g = wrap.format(f"x >= {lo} and x <= {hi}")
            case("P2-19", "pos", CME2, p2(states=(("A", "3"),), rules=[f"rule RA on E when {g} {{ set A := A + 1; }}"],
                                           proof="scenario T { step E(x = 7); expect A >= 0; }"))
    for a in ("x", "A + 1", "A - 1", "A + 2", "A - 2", "A + 2147483647", "3 + A"):
        for g in ("true", "false", "not true", "not false"):
            init = "0" if a == "A + 2147483647" else "3"
            case("P2-19", "pos", CME2, p2(states=(("A", init),), rules=[f"rule RA on E when {g} {{ set A := {a}; }}"],
                                           proof="scenario T { step E(x = 7); expect A >= 0; }"))
    # cascade wiring: publisher flag, subscriber CID, declaration order different from the cascade order
    case("P2-19", "pos", CME2, p2(states=(("B", "0"), ("A", "0")),
                                  rules=["rule RA on E when x < 50 { set A := A + 1; }",
                                         "rule RB on change(A) when A > 0 { set B := B + 1; }"],
                                  inv=("IA: A >= 0;", "IB: B >= 0;"),
                                  proof="scenario T { step E(x = 1); expect A == 1; expect B == 1; }"))
    case("P2-19", "pos", CME2, p2(states=(("A", "0"), ("B", "4"), ("C", "9")), events=(("E", "x"), ("F", "y")),
                                  rules=["rule RC on F when y > 0 { set C := C + 1; }",
                                         "rule RB on change(C) when C > 9 { set B := B - 1; }",
                                         "rule RA on E when x < 50 { set A := x; }"],
                                  proof="scenario T { step F(y = 1); expect C == 10; expect B == 3; step E(x = 6); expect A == 6; }"))
    case("P2-19", "pos", CME2, chain(5))
    case("P2-19", "pos", CME2, many_states(64))
    case("P2-19", "pos", CME2, many_states(30))

    # a Proof literal that cannot be an Int32 is a type error of the module, not a Proof failure
    case("P1-1", "neg", CME1, p1(proof="scenario T { step E(P = 2147483648); expect S == 11; }"), "B3-TYPE")


# --------------------------------------------------------------------------
# Differential ACL and cascade_map cases
# --------------------------------------------------------------------------

ACL_TABLES = [
    {}, {"S": 0}, {"S": 1}, {"S": 2}, {"S": 3}, {"S": 4}, {"S": 5}, {"S": 6}, {"S": 7}, {"S": 0x80}, {"S": 0xFF},
    {"S": -1}, {"S": -2}, {"S": 1024}, {"S": 2 ** 40}, {"Other": 0}, {"Other": 7}, {"S": 0, "Other": 3},
    {"S": 3, "Other": 0}, {"S": 0x7D}, {"S": 0x1F}, {"S": 0x82}, {"s": 0}, {"": 0}, {"S": 2 ** 62},
]


def acl_cases(c: Corpus) -> None:
    for i, acl in enumerate(ACL_TABLES):
        acl = dict(acl)
        c.add(f"acl:cme1:{i:02d}", "acl", BASE1, CME1, acl=acl)
        # the Proof gate comes before the ACL gate
        c.add(f"acl:cme1-badproof:{i:02d}", "acl", p1(proof=P1_PROOF.replace("S == 11", "S == 12")), CME1, acl=acl)
    two = [
        {}, {"A": 0}, {"B": 0}, {"A": 1}, {"B": 1}, {"A": 2, "B": 2}, {"A": 3, "B": 3}, {"A": 0x80, "B": 3},
        {"A": 3, "B": 0x80}, {"C": 0}, {"A": 0, "B": 0, "C": 0}, {"A": -1, "B": -1}, {"a": 0}, {"A": 4}, {"B": 5},
    ]
    for i, acl in enumerate(two):
        c.add(f"acl:cme2:{i:02d}", "acl", BASE2, CME2, acl=dict(acl))
        c.add(f"acl:cme2-chain:{i:02d}", "acl", chain(4), CME2, acl=dict(acl))
    for i, acl in enumerate(two[:6]):
        c.add(f"acl:cme2-noproof:{i:02d}", "acl", p2(proof=None), CME2, acl=dict(acl))


def cascade_cases(c: Corpus) -> None:
    maps = [{}, {"S": "T"}, {"S": "1"}, {"0": "1"}, {"A": "B"}, {"A": "0"}, {"": ""}, {"S": "MissingState"}, {"S": "64"}]
    programs = [
        ("cme1-ok", CME1, BASE1),
        ("cme1-shape", CME1, p1(extra_decl="state T: Int32 = 1;\n")),
        ("cme1-type", CME1, p1(initial="true")),
        ("cme1-badproof", CME1, p1(proof=P1_PROOF.replace("S == 11", "S == 12"))),
        ("cme2-ok", CME2, BASE2),
        ("cme2-alias", CME2, p2(rules=["rule RA on E when • (x >= 50) { set A := A + 1; }",
                                       "rule RB on change(A) when A > 0 { set B := B + 1; }"])),
        ("cme2-noproof", CME2, p2(proof=None)),
        ("cme2-type", CME2, p2(states=(("A", "true"), ("B", "0")))),
        ("cme1-as-cme2", CME2, BASE1),
    ]
    for pname, profile, src in programs:
        for i, cm in enumerate(maps):
            c.add(f"cascade:{pname}:{i}", "cascade", src, profile, cascade=dict(cm))
    for pname, profile, src in programs[:2] + programs[4:5]:
        c.add(f"cascade:{pname}:acl", "cascade", src, profile, cascade={}, acl={"S": 0, "A": 0})


def profile_name_cases(c: Corpus) -> None:
    names = ["", "unknown", "KPOL-CME-3", "kpol-cme-1", "KPOL-CME-1 ", " KPOL-CME-2", "KPOL-CME-0", "CME-RAW-1", "EKPOL",
             "it's", 'say "hi"', "both ' and \"", "back\\slash", "tab\there", "nl\nx", "é", "КПОЛ", "😀", "\x00", "\x7f",
             "\u00a0", "\u2028", "KPOL-CME-１"]
    for i, name in enumerate(names):
        result = run_profile_name(name)
        assert not result["ok"] and result["text"].startswith("B3-PROFILE: unsupported profile "), result
        cid = f"profile:{i:02d}"
        c.ids.add(cid)
        c.cases.append({"id": cid, "group": "profile", "src": c.src(BASE1), "profile": name, "acl": None,
                        "cascade": None, "result": result})


# --------------------------------------------------------------------------
# Direct check_module_security_acl cases
# --------------------------------------------------------------------------

PIN_MODULE = """Problem P { Invariants { I: S >= 0; } }
Solution P {
  state S: Int32 = 1;
  state Led: Pin<Out> = 0;
  state Mix: Pin<In,Out> = 1;
  state Inp: Pin<In> = 0;
  event E(x: Int32);
  rule R on E { set S := S + 1; set Led := 1; set Mix := 0; set Inp := 1; }
  rule Q on E when x > 3 { set Led := 0; set S := S + 2; }
}
"""
PIN_PLAIN = """Problem P { Invariants { I: S >= 0; } }
Solution P { state S: Int32 = 1; event E(x: Int32); rule R on E { set S := S + 1; } }
"""
PIN_FLOAT = """Problem P { Invariants { I: S >= 0; } }
Solution P {
  state S: Int32 = 1;
  state T: Float<V> = 1.5;
  event E(x: Int32);
  rule R on E { set S := S + 1; set T := T + 1.0; }
}
"""


def security_acl_cases() -> tuple[list[str], list[dict]]:
    sources: list[str] = []
    cases: list[dict] = []
    tables = [
        None, {}, {"Led": 0}, {"Led": 4}, {"Led": 2}, {"Led": 6}, {"Mix": 4}, {"Mix": 0}, {"Mix": 2}, {"S": 0},
        {"S": 1}, {"S": 2}, {"Led": 0, "Mix": 0, "S": 0}, {"Led": 4, "Mix": 4, "S": 3}, {"Inp": 0}, {"Inp": 2},
        {"Nope": 0}, {"Led": -1}, {"Led": 0x84}, {"Led": 1}, {"Led": 0x80}, {"Mix": 4, "Led": 0}, {"T": 0}, {"T": 1},
        {"S": 5}, {"Led": 3},
    ]
    for si, text in enumerate((PIN_MODULE, PIN_PLAIN, PIN_FLOAT)):
        sources.append(text)
        module = kr.Parser(text).parse()
        for ti, acl in enumerate(tables):
            cases.append({"id": f"secacl:{si}:{ti:02d}", "src": si, "acl": acl,
                          "violations": kr.check_module_security_acl(module, acl)})
    return sources, cases


# --------------------------------------------------------------------------
# Corpus from the repository
# --------------------------------------------------------------------------

def corpus_files(root: Path, pattern: str):
    for path in sorted(root.rglob(pattern)):
        if GO_PORT_DIR in path.parents:
            continue
        yield path


def md_blocks(path: Path, fence: str = "kpol") -> list[str]:
    blocks, cur = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        if cur is None and line.strip() == "```" + fence:
            cur = []
        elif cur is not None and line.strip() == "```":
            blocks.append("\n".join(cur))
            cur = None
        elif cur is not None:
            cur.append(line)
    return blocks


def python_test_sources() -> list[tuple[str, str]]:
    found: dict[str, str] = {}
    roots = [REPO / "Engineering" / "sw", REPO / "Engineering" / "hw", REPO / "Engineering" / "validation"]
    for root in roots:
        for path in corpus_files(root, "*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    s = node.value
                    if "Problem" in s and "Solution" in s and "{" in s and len(s) < 20000:
                        found.setdefault(s, f"{path.relative_to(REPO)}:{node.lineno}")
    return [(loc, src) for src, loc in sorted(found.items(), key=lambda kv: (kv[1], kv[0]))]


def repo_cases(c: Corpus) -> list[tuple[str, str, str]]:
    """Adds every repository program under both profiles; returns the programs for mutation."""
    programs: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add(cid: str, group: str, src: str, dedupe: bool) -> None:
        if dedupe and src in seen:
            return
        seen.add(src)
        programs.append((cid, group, src))

    for path in corpus_files(REPO / "Engineering", "*.kpol"):
        add(f"file:{path.relative_to(REPO)}", "file", path.read_text(encoding="utf-8"), dedupe=False)
    for path in corpus_files(REPO / "Engineering", "*.md"):
        for i, block in enumerate(md_blocks(path)):
            add(f"md:{path.relative_to(REPO)}#{i}", "guide", block, dedupe=True)
    for loc, src in python_test_sources():
        add(f"pytest:{loc}", "pytest", src, dedupe=True)
    for cid, group, src in programs:
        for profile in (CME1, CME2):
            c.add(f"{cid}@{profile}", group, src, profile)
    return programs


# --------------------------------------------------------------------------
# Mutations
# --------------------------------------------------------------------------

class Doc:
    """A source text with token spans and the structure the mutators need."""

    def __init__(self, source: str) -> None:
        self.source = source
        starts = [0]
        for i, ch in enumerate(source):
            if ch == "\n":
                starts.append(i + 1)
        self.toks = []
        for t in kr.tokenize(source)[:-1]:
            off = starts[t.line - 1] + t.column - 1
            if t.kind.startswith("ALIAS"):
                length = next(len(a) for a in ("(*)", "<-", "->", "←", "→", "•") if source.startswith(a, off))
            else:
                length = len(t.value)
            self.toks.append((t.kind, t.value, off, off + length))

    def find(self, value: str, start: int = 0) -> list[int]:
        return [i for i in range(start, len(self.toks)) if self.toks[i][1] == value]

    def span(self, a: int, b: int) -> tuple[int, int]:
        """Source offsets covering tokens a..b (inclusive)."""
        return self.toks[a][2], self.toks[b][3]

    def until(self, a: int, stop: str) -> int:
        i = a
        while self.toks[i][1] != stop:
            i += 1
        return i

    def block_end(self, open_idx: int) -> int:
        depth = 0
        for i in range(open_idx, len(self.toks)):
            if self.toks[i][1] == "{":
                depth += 1
            elif self.toks[i][1] == "}":
                depth -= 1
                if depth == 0:
                    return i
        raise ValueError("unbalanced")

    def decls(self, keyword: str) -> list[tuple[int, int]]:
        """Token index ranges of `state`/`event` declarations (to ';') or `rule` blocks (to '}')."""
        out = []
        for i in self.find(keyword):
            if keyword == "rule":
                j = self.block_end(self.until(i, "{"))
            else:
                j = self.until(i, ";")
            out.append((i, j))
        return out

    def replace(self, ranges: list[tuple[int, int, str]]) -> str:
        text = self.source
        for a, b, repl in sorted(ranges, key=lambda r: -r[0]):
            text = text[:a] + repl + text[b:]
        return text


BIN_CMP = ["==", "!=", "<", "<=", ">", ">="]
NUMS = ["0", "1", "2", "3", "4", "5", "9", "10", "15", "16", "20", "31", "32", "50", "100", "255", "256", "32767", "32768",
        "65535", "65536", "2147483646", "2147483647", "2147483648", "4294967295", "4294967296", "1.0", "1.5", "007"]
TYPES = ["U32", "U64", "Bool", "Float<V>", "Pin<In>", "Pin<Out>", "Int32"]
ACTION_FORMS = ["{p}", "5", "{s} + 2", "2 + {s}", "{s} - 3", "3 - {s}", "{s} * 2", "{s} + {p}", "{s} + 1", "{s} - 1",
                "{s} + 2147483647", "{s} + 2147483648", "{s} + 0", "-{s}", "{p} + 1"]
GUARD_FORMS = ["true", "false", "not true", "{p} < 5", "5 < {p}", "{p} >= 5", "{p} <= -5", "{p} >= -32768 and {p} <= 32767",
               "{p} > 0 and {p} < 10", "{p} >= 10 and {p} <= 5", "{p} > 5 and {p} > 6", "{p} == 3 and {p} < 9", "not ({p} == 3)",
               "{p} < 5 or {p} > 9", "{p} + 1 < 5", "{p} < 2147483648", "{p} >= 0.5", "• ({p} > 5)", "(*) ({p} > 5)"]
SECTION_ADDS = [
    "Hazards { H1 on <e> to <s>: <p> > 1000; }",
    "Assumptions { As1: <s> >= 0; }",
    "Alerts { Al1 on <e>: <p> > 100; }",
    "Goals { G1: <s> >= 0; }",
    "Invariants { Extra: <s> >= 0; }",
]
INV_FORMS = ["0 <= {s}", "{s} >= 0.0", "{s} > -1", "{s} >= 1", "{s} > 0", "{s} >= 0 and true", "{s} + 0 >= 0", "{s} <= 0", "-1 < {s}"]
STEP_ARGS = ["0", "1", "5", "50", "100", "-1", "2147483647", "2147483648", "Unknown", "1 + 1"]


def names(doc: Doc) -> dict:
    states = [doc.toks[i + 1][1] for i in doc.find("state")]
    events = [doc.toks[i + 1][1] for i in doc.find("event")]
    params = []
    for i in doc.find("event"):
        j = i + 3
        if doc.toks[j][0] == "ID":
            params.append(doc.toks[j][1])
    return {"states": states, "events": events, "params": params}


def mutate(source: str, kind: str, rng: random.Random) -> str | None:
    doc = Doc(source)
    nm = names(doc)
    toks = doc.toks

    def choose(seq):
        return rng.choice(list(seq)) if seq else None

    def idx_where(pred):
        return [i for i, t in enumerate(toks) if pred(i, t)]

    def sub(i, text):
        return doc.replace([(toks[i][2], toks[i][3], text)])

    if kind == "num":
        i = choose(idx_where(lambda i, t: t[0] == "NUMBER"))
        if i is None:
            return None
        v = rng.choice(NUMS)
        neg = "-" if rng.random() < 0.25 else ""
        return sub(i, neg + v)
    if kind == "cmp":
        i = choose(idx_where(lambda i, t: t[1] in BIN_CMP))
        if i is None:
            return None
        return sub(i, rng.choice([o for o in BIN_CMP if o != toks[i][1]]))
    if kind == "arith":
        i = choose(idx_where(lambda i, t: t[1] in ("+", "-") and i > 0))
        if i is None:
            return None
        return sub(i, rng.choice([o for o in ("+", "-", "*", "/") if o != toks[i][1]]))
    if kind == "logic":
        i = choose(idx_where(lambda i, t: t[1] in ("and", "or", "not")))
        if i is None:
            return None
        if toks[i][1] == "not":
            return sub(i, "")
        return sub(i, "or" if toks[i][1] == "and" else "and")
    if kind == "type":
        i = choose(idx_where(lambda i, t: t[1] == "Int32"))
        if i is None:
            return None
        return sub(i, rng.choice([t for t in TYPES if t != "Int32"]))
    if kind == "ident":
        pool = nm["states"] + nm["params"] + nm["events"]
        i = choose(idx_where(lambda i, t: t[0] == "ID" and t[1] in pool))
        if i is None or len(pool) < 2:
            return None
        return sub(i, rng.choice([n for n in pool if n != toks[i][1]]))
    if kind == "rejectcovers":
        ons = doc.find("on")
        if not ons:
            return None
        i = choose(ons)
        if rng.random() < 0.5:
            return sub(i, "on reject")
        j = doc.until(i, "{")
        return doc.replace([(toks[j][2], toks[j][2], "covers H1 ")])
    if kind in ("swapdecl", "deldecl", "dupdecl"):
        key = choose(["state", "event", "rule", "rule", "state"])
        ds = doc.decls(key)
        if not ds:
            return None
        if kind == "swapdecl":
            if len(ds) < 2:
                return None
            k = rng.randrange(len(ds) - 1)
            (a1, b1), (a2, b2) = ds[k], ds[k + 1]
            s1, e1 = doc.span(a1, b1)
            s2, e2 = doc.span(a2, b2)
            return doc.replace([(s1, e1, source[s2:e2]), (s2, e2, source[s1:e1])])
        a, b = choose(ds)
        s, e = doc.span(a, b)
        if kind == "deldecl":
            return doc.replace([(s, e, "")])
        text = source[s:e]
        old = toks[a + 1][1]
        new = old + "x"
        if key == "state" or key == "event":
            text = text.replace(f" {old}", f" {new}", 1).replace(f" {old}:", f" {new}:", 1)
            text = text.replace(f"{key} {old}", f"{key} {new}", 1)
        else:
            text = text.replace(f"rule {old}", f"rule {new}", 1)
        return doc.replace([(e, e, "\n" + text)])
    if kind == "delinv":
        secs = doc.find("Invariants")
        if not secs:
            return None
        o = doc.until(secs[0], "{")
        c = doc.block_end(o)
        items = []
        k = o + 1
        while k < c:
            e = doc.until(k, ";")
            items.append((k, e))
            k = e + 1
        if not items:
            return None
        a, b = choose(items)
        s, e = doc.span(a, b)
        return doc.replace([(s, e, "")])
    if kind == "invform":
        secs = doc.find("Invariants")
        if not secs or not nm["states"]:
            return None
        o = doc.until(secs[0], "{")
        c = doc.block_end(o)
        items = []
        k = o + 1
        while k < c:
            e = doc.until(k, ";")
            items.append((k, e))
            k = e + 1
        if not items:
            return None
        a, b = choose(items)
        s_name = choose(nm["states"])
        for t in range(a, b):
            if toks[t][0] == "ID" and toks[t][1] in nm["states"]:
                s_name = toks[t][1]
                break
        start = toks[a + 2][2]
        return doc.replace([(start, toks[b][2], rng.choice(INV_FORMS).format(s=s_name))])
    if kind == "watch":
        ch = doc.find("change")
        ch = [i for i in ch if i > 0 and toks[i - 1][1] == "on"]
        if not ch or len(nm["states"]) < 2:
            return None
        i = choose(ch)
        j = doc.until(i, ")")
        names_in = [toks[k][1] for k in range(i + 2, j) if toks[k][0] == "ID"]
        mode = rng.choice(["retarget", "add", "empty", "self"])
        if mode == "retarget":
            alt = [n for n in nm["states"] if n not in names_in]
            if not alt:
                return None
            text = rng.choice(alt)
        elif mode == "add":
            text = ", ".join(names_in + [rng.choice(nm["states"])])
        elif mode == "empty":
            text = ""
        else:
            # the rule's own target
            k = doc.until(i, "{")
            tgt = [toks[t + 1][1] for t in range(k, len(toks) - 1) if toks[t][1] == "set"]
            text = tgt[0] if tgt else names_in[0]
        return doc.replace([(toks[i + 2][2], toks[j][2], text)])
    if kind == "proof":
        pr = [i for i, t in enumerate(toks) if t[1] == "Proof" and i + 1 < len(toks) and toks[i + 2][1] == "{"]
        if not pr:
            # add a trivial passing-or-failing Proof
            ev = choose(nm["events"])
            p = nm["params"][nm["events"].index(ev)]
            s = choose(nm["states"])
            if not ev:
                return None
            return source + f"\nProof M {{ scenario Added {{ step {ev}({p} = 1); expect {s} >= 0; }} }}\n"
        i = choose(pr)
        o = i + 2
        c = doc.block_end(o)
        mode = rng.choice(["del", "empty", "stepdel", "expectdel", "stepdup", "expectedit", "stepargs", "scenarios"])
        s0, e0 = doc.span(i, c)
        if mode == "del":
            return doc.replace([(s0, e0, "")])
        if mode == "empty":
            return doc.replace([(toks[o][3], toks[c][2], " ")])
        items = []
        for k in range(o + 1, c):
            if toks[k][1] in ("step", "expect", "assert"):
                items.append((k, doc.until(k, ";")))
        if mode == "scenarios":
            return doc.replace([(toks[c][2], toks[c][2], "scenario Extra { }")])
        if not items:
            return None
        if mode == "stepdel":
            cand = [it for it in items if toks[it[0]][1] == "step"]
        elif mode == "expectdel":
            cand = [it for it in items if toks[it[0]][1] == "expect"]
        elif mode == "stepdup":
            cand = [it for it in items if toks[it[0]][1] in ("step", "expect")]
        elif mode == "expectedit":
            cand = [it for it in items if toks[it[0]][1] == "expect"]
        else:
            cand = [it for it in items if toks[it[0]][1] == "step"]
        if not cand:
            return None
        a, b = choose(cand)
        s, e = doc.span(a, b)
        if mode in ("stepdel", "expectdel"):
            return doc.replace([(s, e, "")])
        if mode == "stepdup":
            return doc.replace([(e, e, " " + source[s:e])])
        nums = [k for k in range(a, b) if toks[k][0] == "NUMBER"]
        if mode == "expectedit":
            if not nums:
                return None
            k = nums[-1]
            return sub(k, str(int(float(toks[k][1])) + rng.choice([-2, -1, 1, 2, 100])))
        # stepargs
        k = [k for k in range(a, b) if toks[k][1] in ("=", ":")]
        if not k:
            return None
        return doc.replace([(toks[k[0]][3], toks[b][2], " " + rng.choice(STEP_ARGS))])
    if kind == "section":
        pb = [i for i, t in enumerate(toks) if t[1] == "Problem"]
        if not pb or not nm["events"]:
            return None
        o = doc.until(pb[0], "{")
        ev = choose(nm["events"])
        p = nm["params"][nm["events"].index(ev)]
        s = choose(nm["states"])
        text = rng.choice(SECTION_ADDS).replace("<e>", ev).replace("<p>", p).replace("<s>", s)
        return doc.replace([(toks[o][3], toks[o][3], " " + text + " ")])
    if kind == "guard":
        rules = doc.decls("rule")
        if not rules:
            return None
        a, b = choose(rules)
        whens = [k for k in range(a, b) if toks[k][1] == "when"]
        if not whens:
            return None
        w = whens[0]
        o = doc.until(w, "{")
        # the guard variable: the event parameter, or the watched state
        if toks[a + 2][1] == "on" and toks[a + 3][1] == "change":
            var = toks[a + 5][1]
        else:
            ev = toks[a + 3][1]
            var = nm["params"][nm["events"].index(ev)] if ev in nm["events"] else (nm["params"] or ["x"])[0]
        return doc.replace([(toks[w + 1][2], toks[o][2], rng.choice(GUARD_FORMS).format(p=var) + " ")])
    if kind == "action":
        rules = doc.decls("rule")
        if not rules:
            return None
        a, b = choose(rules)
        sets = [k for k in range(a, b) if toks[k][1] == "set"]
        if not sets:
            return None
        k = choose(sets)
        e = doc.until(k, ";")
        target = toks[k + 1][1]
        if toks[a + 2][1] == "on" and toks[a + 3][1] == "change":
            var = toks[a + 5][1]
        else:
            ev = toks[a + 3][1]
            var = nm["params"][nm["events"].index(ev)] if ev in nm["events"] else (nm["params"] or ["x"])[0]
        return doc.replace([(toks[k + 3][2], toks[e][2], rng.choice(ACTION_FORMS).format(s=target, p=var))])
    if kind == "target":
        rules = doc.decls("rule")
        if not rules or len(nm["states"]) < 2:
            return None
        a, b = choose(rules)
        sets = [k for k in range(a, b) if toks[k][1] == "set"]
        if not sets:
            return None
        k = choose(sets)
        return sub(k + 1, rng.choice([n for n in nm["states"] if n != toks[k + 1][1]]))
    if kind == "initial":
        sts = doc.find("state")
        if not sts:
            return None
        i = choose(sts)
        e = doc.until(i, ";")
        eq = doc.until(i, "=")
        return doc.replace([(toks[eq + 1][2], toks[e][2], rng.choice(["0", "1", "-1", "5 + 5", "Unknown", "true", "2147483647",
                                                                         "2147483648", "-2147483648", "1.0", "-0"]))])
    if kind == "param":
        evs = doc.find("event")
        if not evs:
            return None
        i = choose(evs)
        e = doc.until(i, ";")
        o = doc.until(i, "(")
        mode = rng.choice(["add", "del", "type"])
        close = e - 1  # the ')' before ';'
        if mode == "add":
            return doc.replace([(toks[close][2], toks[close][2], ", extra: Int32")])
        if mode == "del":
            return doc.replace([(toks[o][3], toks[close][2], "")])
        if toks[close - 1][0] == "ID" and toks[close - 2][1] == ":":
            return doc.replace([(toks[close - 1][2], toks[close - 1][3], rng.choice(["Bool", "U32", "U64", "Float<V>"]))])
        return None
    raise ValueError(kind)


MUTATION_KINDS = ["num", "cmp", "arith", "logic", "type", "ident", "rejectcovers", "swapdecl", "deldecl", "dupdecl", "delinv",
                  "invform", "watch", "proof", "section", "guard", "action", "target", "initial", "param"]


def mutation_cases(c: Corpus, bases: list[tuple[str, str, str]], rng: random.Random) -> Counter:
    """Mutates each valid profile program; every mutant is run under both profiles."""
    stats: Counter = Counter()
    images: set[str] = set()
    seen: set[str] = {src for _, _, src in bases}
    count = 0
    for base_id, base_src, profile in bases:
        for kind in MUTATION_KINDS:
            made = 0
            attempts = 0
            while made < MUTANTS_PER_BASE_KIND and attempts < 12:
                attempts += 1
                try:
                    mutant = mutate(base_src, kind, rng)
                except (ValueError, IndexError, StopIteration):
                    mutant = None
                if mutant is None or mutant in seen:
                    continue
                try:
                    kr.Parser(mutant).parse()
                except Exception:
                    continue
                seen.add(mutant)
                made += 1
                count += 1
                stats["kind:" + kind] += 1
                for p in (profile, CME2 if profile == CME1 else CME1):
                    case = c.add(f"mut:{base_id}:{kind}:{made}@{p}", "mutation", mutant, p)
                    if case is not None:
                        stats["ok" if case["result"]["ok"] else case["result"]["text"].split(":")[0]] += 1
                        case["mutant"] = {"base": base_id, "kind": kind}
                        if case["result"]["ok"]:
                            images.add(case["result"]["sha"])
    stats["mutants"] = count
    stats["distinct_images"] = len(images)
    return stats


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    rng = random.Random(SEED)
    c = Corpus()
    repo_programs = repo_cases(c)
    hand_cases(c)
    acl_cases(c)
    cascade_cases(c)
    profile_name_cases(c)

    # valid profile programs: the base set of the mutations
    bases: list[tuple[str, str, str]] = []
    done: set[str] = set()
    for case in list(c.cases):
        if case["result"]["ok"] and case["group"] in ("file", "guide", "pytest", "hand") and not case.get("acl") \
                and case.get("cascade") is None and not case.get("strip_alias_flag"):
            key = c.sources[case["src"]]
            if key in done:
                continue
            done.add(key)
            bases.append((case["id"].split("@")[0], c.sources[case["src"]], case["profile"]))
    # keep the number of bases bounded: hand-written lowering matrices would dominate
    hand = [b for b in bases if b[0].startswith("hand:")]
    other = [b for b in bases if not b[0].startswith("hand:")]
    rng.shuffle(hand)
    multi = [b for b in hand if b[1].count("state ") >= 2]
    single = [b for b in hand if b[1].count("state ") < 2]
    bases = other + multi[:50] + single[:30]
    if c.problems:
        print("\n".join(c.problems))
        raise SystemExit(f"{len(c.problems)} hand-written cases do not behave as declared")
    stats = mutation_cases(c, bases, rng)
    assert stats["mutants"] >= MIN_MUTANTS, stats

    sources_acl, acl_direct = security_acl_cases()

    codes: Counter = Counter()
    for case in c.cases:
        r = case["result"]
        codes["ok" if r["ok"] else (r["text"].split(":")[0] if r["kind"] == "kpol" else "crash:" + r["text"])] += 1

    data = {
        "meta": {"seed": SEED, "cases": len(c.cases), "sources": len(c.sources), "mutants": stats["mutants"],
                 "mutation_kinds": {k[5:]: v for k, v in sorted(stats.items()) if k.startswith("kind:")},
                 "mutant_images": stats["distinct_images"],
                 "codes": dict(sorted(codes.items())), "reference": "Engineering/sw/kpol-ref/kpol_reference.py"},
        "sources": c.sources,
        "cases": c.cases,
        "acl_sources": sources_acl,
        "acl_direct": acl_direct,
    }
    goldenio.write_gz_text(OUT, json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"wrote {OUT.relative_to(REPO)}: {len(c.cases)} cases, {len(c.sources)} sources, {stats['mutants']} mutants")
    print("repository programs:", len(repo_programs))
    for k, v in sorted(codes.items()):
        print(f"  {v:6d}  {k}")
    print("mutation outcomes:", dict(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
