#!/usr/bin/env python3
"""Generate testdata/ekpol_golden.json.gz: the differential oracle for the Go `ekpol` package.

The Python reference (Engineering/sw/kpol-ref/ekpol_frontend.py) is run over

* the EKPOL corpus: every `.ekpol` file of the repository and every ```ekpol block of the
  guides (the four Annex A vectors of the formal specification are among them),
* the KPOL corpus: every `.kpol` file and ```kpol block, for KPOL -> EKPOL,
* >= 300 systematic mutations (token deletion / duplication / replacement / swap,
  number and operator tweaks, truncation) of both corpora,
* a template grid of positive and negative programs covering every diagnostic class,

and records for each input whether it is accepted, the diagnostic code and text, the
parsed program, the SHA-256 of the BRAM image, the KPOL translation, both EKPOL
renderings and the EKPOL -> KPOL -> EKPOL -> KPOL -> image round trip.

Usage: python3 gen_ekpol_golden.py            (writes ekpol_golden.json.gz next to this file)
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import goldenio  # noqa: E402
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "Engineering" / "sw" / "kpol-ref"))

import ekpol_frontend as ef  # noqa: E402
import kpol_reference as kr  # noqa: E402

OUT = HERE / "ekpol_golden.json.gz"
SEED = 278


# ---------------------------------------------------------------- result capture
def call(fn, *args, **kwargs):
    """Run fn and describe the outcome without Python-specific detail."""
    try:
        return {"ok": True, "value": fn(*args, **kwargs)}
    except ef.EkpolError as err:
        return {"ok": False, "code": err.code, "message": err.detail}
    except kr.KpolError as err:
        return {"ok": False, "kpol_error": str(err)}
    except Exception as err:  # unhandled exception in the reference
        return {"ok": False, "crash": type(err).__name__, "message": str(err)}


def failure(res):
    return {k: v for k, v in res.items() if k != "value"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- program dump
def rv(value):
    return repr(value)


def dump_pred(p):
    return {
        "kind": p.kind, "var": p.var, "op": p.op, "value": rv(p.value),
        "lo": None if p.lo is None else str(p.lo), "hi": None if p.hi is None else str(p.hi),
        "inverted": p.inverted, "raw": p.raw_text,
    }


def dump_rule(r):
    return {
        "trigger": r.trigger_kind, "event": r.event_name, "param": r.param_name,
        "param_type": r.param_type, "watch": r.watch_concept, "exec": list(r.exec_params),
        "pred": dump_pred(r.predicate),
        "actions": [{"kind": a.kind, "target": a.target, "operand": rv(a.operand), "raw": a.raw_text} for a in r.actions],
        "post_read": r.post_read_barrier, "rule_name": r.rule_name,
    }


def dump_concept(c):
    return {
        "name": c.name, "type": c.canonical_type, "raw_type": c.raw_type, "init": rv(c.initial_value),
        "undef": c.is_undef_init,
        "invariants": [
            {"kind": i.kind, "op": i.op, "value": str(i.value), "lo": None if i.lo is None else str(i.lo),
             "hi": None if i.hi is None else str(i.hi)} for i in c.invariants
        ],
        "annotations": list(c.annotations),
        "rules": [dump_rule(r) for r in c.rules],
    }


def dump_step(s):
    return {
        "kind": s.kind, "target": s.target, "param": s.param_name, "op": s.op, "value": rv(s.value),
        "extra": [rv(x) for x in s.extra_args],
    }


def dump_prog(p):
    return {
        "module": p.module_name, "stdin": list(p.stdin_concepts), "stdout": list(p.stdout_concepts),
        "stderr": list(p.stderr_concepts), "conceptual_only": p.is_conceptual_only,
        "concepts": [dump_concept(c) for c in p.concepts],
        "tests": [{"name": t.name, "steps": [dump_step(s) for s in t.steps]} for t in p.tests],
    }


# ---------------------------------------------------------------- per-case oracle
def ekpol_case(src: str) -> dict:
    case: dict = {"kind": "ekpol", "src": src}
    parsed = call(ef.parse_ekpol, src)
    if not parsed["ok"]:
        case["parse"] = failure(parsed)
        return case
    prog = parsed["value"]
    case["parse"] = {"ok": True, "program": dump_prog(prog)}
    custom = call(ef.parse_ekpol, src, "MyMod")
    case["parse_custom_module"] = custom["value"].module_name if custom["ok"] else None

    val = call(ef.validate_ekpol_for_bram64, prog)
    if val["ok"]:
        packed = b"".join(d.pack() for d in val["value"])
        case["validate"] = {"ok": True, "sha256": sha(packed)}
    else:
        case["validate"] = failure(val)

    img = call(ef.compile_ekpol_to_bram_image, src)
    case["image"] = {"ok": True, "sha256": sha(img["value"]), "len": len(img["value"])} if img["ok"] else failure(img)

    k1 = call(ef.transpile_ekpol_to_kpol, src)
    case["to_kpol"] = {"ok": True, "text": k1["value"]} if k1["ok"] else failure(k1)

    k1s = call(ef.transpile_ekpol_to_kpol, src, synthesize_proof_if_needed=True)
    if k1["ok"] and k1s["ok"] and k1["value"] == k1s["value"]:
        case["to_kpol_synth"] = {"same": True}
    else:
        case["to_kpol_synth"] = {"ok": True, "text": k1s["value"]} if k1s["ok"] else failure(k1s)

    if k1["ok"] and img["ok"]:
        case["roundtrip"] = {style: roundtrip(k1["value"], style) for style in ("symbolic", "keyword")}
    return case


def roundtrip(kpol_text: str, style: str) -> dict:
    """KPOL -> EKPOL(style) -> image, and -> KPOL again -> image."""
    out: dict = {}
    e1 = call(ef.transpile_kpol_to_ekpol, kpol_text, style)
    if not e1["ok"]:
        return {"stage": "to_ekpol", **failure(e1)}
    text = e1["value"]
    out["ascii"] = all(ord(ch) < 128 for ch in text)
    out["ekpol_sha256"] = sha(text.encode())
    img = call(ef.compile_ekpol_to_bram_image, text)
    if not img["ok"]:
        return {"stage": "image", **out, **failure(img)}
    out["image_sha256"] = sha(img["value"])
    k2 = call(ef.transpile_ekpol_to_kpol, text)
    if not k2["ok"]:
        return {"stage": "to_kpol", **out, **failure(k2)}
    out["kpol2_sha256"] = sha(k2["value"].encode())
    out["stage"] = "ok"
    return out


def kpol_case(src: str) -> dict:
    case: dict = {"kind": "kpol", "src": src}
    for style in ("symbolic", "keyword"):
        res = call(ef.transpile_kpol_to_ekpol, src, style)
        case["to_ekpol_" + style] = {"ok": True, "text": res["value"]} if res["ok"] else failure(res)
    if case["to_ekpol_symbolic"]["ok"]:
        case["roundtrip"] = {style: kpol_roundtrip(src, style) for style in ("symbolic", "keyword")}
    return case


def kpol_roundtrip(src: str, style: str) -> dict:
    """Original KPOL -> EKPOL -> image, to compare with the profile image of the original."""
    e1 = call(ef.transpile_kpol_to_ekpol, src, style)
    text = e1["value"]
    img = call(ef.compile_ekpol_to_bram_image, text)
    out = {"ascii": all(ord(ch) < 128 for ch in text)}
    if not img["ok"]:
        return {**out, "stage": "image", **failure(img)}
    out["stage"] = "ok"
    out["image_sha256"] = sha(img["value"])
    return out


# ---------------------------------------------------------------- corpora
def repo_files(suffix: str):
    skipped = {".git", "node_modules", "__pycache__", ".pytest_cache", "scratch_work"}
    port = REPO / "Engineering" / "sw" / "kpol-go"  # the Go port itself holds generated and scratch material
    for root, dirs, files in os.walk(REPO):
        dirs[:] = sorted(d for d in dirs if d not in skipped and Path(root, d) != port)
        for name in sorted(files):
            if name.endswith(suffix):
                yield Path(root) / name


MARKDOWN_DIRS = [
    REPO / "Engineering" / "guides",
    REPO / "Engineering" / "specifications" / "kpol",
    REPO / "Engineering" / "sw" / "kpol-ref" / "tests" / "fixtures",
]


def fenced_blocks(lang: str):
    pattern = re.compile(rf"^```{lang}\n(.*?)^```", re.M | re.S)
    for directory in MARKDOWN_DIRS:
        for md in sorted(directory.glob("*.md")):
            for idx, block in enumerate(pattern.findall(md.read_text(encoding="utf-8"))):
                yield f"{md.name}#{lang}{idx}", block


def corpus(suffix: str, lang: str):
    items: dict[str, str] = {}
    for path in sorted(repo_files(suffix)):
        items[str(path.relative_to(REPO))] = path.read_text(encoding="utf-8")
    for name, block in fenced_blocks(lang):
        items[name] = block
    return items


# ---------------------------------------------------------------- mutations
TOKEN = re.compile(
    r"\s+|[A-Za-z_][A-Za-z0-9_]*|0[xX][0-9A-Fa-f]+|[0-9]+(?:\.[0-9]+)?|\.\.|=>|<-|->|::|<=|>=|==|!=|\+=|-=|:=|&&|[^\sA-Za-z0-9_]"
)
EK_VOCAB = [
    "=>", "<-", "->", "~", "|", "::", ".", ";", "commit", "when", "on", "after", "read", "write", "change", "call",
    "exec", "not", "!", "(", ")", "{", "}", "[", "]", ",", ":", "==", "!=", "<", ">", "<=", ">=", "=", "+=", "-=",
    "in", "is", "undef", "null", "positive", "negative", "even", "odd", "&&", "and", "or", "&", "..", "true", "false",
    "_", "0", "1", "2", "-1", "10", "50", "0x10", "010", "1_0", "2147483648", "4294967296", "65536", "-32769",
    "concept", "test", "scenario", "send", "step", "expect", "invariant", "module", "@stdin", "@stdout", "@stderr",
    "i32", "u64", "f64", "bool", "Int32", "RANGE", "pass", "nop", "//", "#", "/*", "*/", "param", "Counter", "x",
]
KP_VOCAB = [
    "Problem", "Solution", "Proof", "Invariants", "event", "state", "rule", "on", "change", "when", "set", "scenario",
    "step", "expect", "assert", "{", "}", "(", ")", ";", ":", ":=", "=", "==", "!=", "<", ">", "<=", ">=", "+", "-", "*",
    "and", "or", "not", "true", "false", "Unknown", "Int32", "Bool", "0", "1", "2", "-1", "10", "2147483648", "2.5",
    "Counter", "param", "x", "Hazards", "Assumptions", "covers", "reject", "•", "(*)", "#", "//", "/*",
]
FLIPS = {
    "<": ">", ">": "<", "<=": ">=", ">=": "<=", "==": "!=", "!=": "==", "+=": "-=", "-=": "+=", "+": "-", "-": "+",
    "and": "or", "or": "and", "&&": "and", "true": "false", "false": "true", "<-": "->", "->": "<-", "::": "when",
    "commit": ".", ".": "commit", "i32": "u64", "in": "is",
}


def mutate(src: str, rng: random.Random, vocab: list[str]) -> str:
    toks = TOKEN.findall(src)
    idxs = [i for i, t in enumerate(toks) if not t.isspace()]
    if not idxs:
        return src
    i = rng.choice(idxs)
    t = toks[i]
    op = rng.choice(["delete", "dup", "replace", "swap", "flip", "number", "truncate", "insert", "dropline"])
    if op == "delete":
        del toks[i]
    elif op == "dup":
        toks.insert(i, t)
    elif op == "replace":
        toks[i] = rng.choice(vocab)
    elif op == "insert":
        toks.insert(i, rng.choice(vocab) + " ")
    elif op == "swap":
        j = next((j for j in range(i + 1, len(toks)) if not toks[j].isspace()), None)
        if j is not None:
            toks[i], toks[j] = toks[j], toks[i]
    elif op == "flip":
        toks[i] = FLIPS.get(t, rng.choice(vocab))
    elif op == "number":
        if re.fullmatch(r"-?[0-9]+", t):
            toks[i] = str(rng.choice([int(t) + 1, int(t) - 1, -int(t), 0, 2**31, 2**32 + 1, 65536, 32768, f"0{t}", f"{t}_0"]))
        else:
            toks[i] = rng.choice(["0", "1", "100", "-5", "0x1F", "007", "1.5", "2147483647"])
    elif op == "truncate":
        return "".join(toks[:i])
    elif op == "dropline":
        lines = "".join(toks).split("\n")
        if len(lines) > 1:
            del lines[rng.randrange(len(lines))]
        return "\n".join(lines)
    return "".join(toks)


def mutations(bases: dict[str, str], per_base: int, vocab: list[str], rng: random.Random):
    seen = set(bases.values())
    out: dict[str, str] = {}
    for name, src in sorted(bases.items()):
        made, attempts = 0, 0
        n = per_base if len(src) > 400 else per_base // 2
        while made < n and attempts < n * 6:
            attempts += 1
            m = mutate(src, rng, vocab)
            if rng.random() < 0.12:  # compound mutations
                m = mutate(m, rng, vocab)
            if m in seen:
                continue
            seen.add(m)
            out[f"mut:{name}:{made}"] = m
            made += 1
    return out


EXOTIC = [
    " ", "\t", "\r", "\r\n", "\x0b", "\x0c", "\x1c", "\x1f", "\x85", "\xa0", "\u1680", "\u2003", "\u2028", "\u2029", "\u3000",
    "\u200b", "\ufeff", "•", "¬", "←", "→", "é", "п", "٣", "０", "ſ", "\u212a", "ı", "\x00", "'", '"', "\\", "{", "}", "(", ")",
    "\n", "\n\n", ";", ",", ".", "_", "?", "@",
]


def charfuzz(bases: dict[str, str], per_base: int, rng: random.Random):
    """Single-character edits with whitespace, Unicode and quoting oddities."""
    seen = set(bases.values())
    out: dict[str, str] = {}
    for name, src in sorted(bases.items()):
        for k in range(per_base):
            pos = rng.randrange(len(src) + 1)
            ch = rng.choice(EXOTIC)
            kind = rng.choice(["insert", "replace", "delete"])
            if kind == "insert":
                m = src[:pos] + ch + src[pos:]
            elif kind == "replace" and pos < len(src):
                m = src[:pos] + ch + src[pos + 1:]
            elif pos < len(src):
                m = src[:pos] + src[pos + 1:]
            else:
                continue
            if m in seen:
                continue
            seen.add(m)
            out[f"fuzz:{name}:{k}"] = m
    return out


# ---------------------------------------------------------------- template grid
GUARDS = [
    None, "true", "false", "param < 20", "param > 5", "param == 7", "param != 7", "param >= 3", "param <= 9",
    "20 > param", "5 <= param", "param = 4", "param in 0..100", "param in 5..1", "param in 0..70000", "param in -40000..5",
    "RANGE(param, -5, 5)", "range(param, 1, 9)", "param >= 1 && param <= 10", "param > 0 and param < 10",
    "param >= 10 and param <= 1", "param > 0 and param > 5", "param >= 1 and param <= 2 and param != 5",
    "param > 3 && other < 5", "not (param < 5)", "not(param == 3)", "!(param == 2)", "!param == 2", "not not (param < 5)",
    "!(not (param < 5))", "((param < 5))", "(param) < 5", "param is positive", "param is not positive", "param is negative",
    "param is not null", "param is null", "param is even", "param is odd", "param is uneven", "param is not even",
    "IS ODD", "x is odd", "param is undef", "param is not undef", "(param & 4) != 0", "(param & 4) == 0", "param & 8",
    "param & 0x10", "(param & 0xFF)", "param & -1", "param == _", "param != undef", "param == true", "param = false",
    "param == !", "_", "undef", "!", "¬", "other < 5", "a > b", "param < 0x10", "param == 010", "param < 4294967297",
    "param == -5", "param < 2147483648", "param <= -2147483649", "param", "param + 1 < 5", "param < y", "param <",
    "when", "param > 1 or param < 0",
    "(param >= 1) && (param <= 5)", "(param > 0) and (param < 9)", "not (param < 1) && (param < 5)",
    "!(param > 1) and (param > 0)", "((param < 5)) && ((param > 1))", "(param < 5) (", "(param < 5) )(", "not ((param < 5) and (param > 1))",
    "(not (param < 5))", "not(not(param < 5))", "(param < 5) == true", "param < 5 and param",
]
ACTIONS = [
    "Counter += 1", "Counter -= 1", "Counter += 5", "Counter -= 5", "Counter = param", "Counter := param",
    "Counter = Counter + 1", "Counter = Counter - 3", "Counter = Counter + 010", "Counter = 5", "Counter = 0x10", "Counter += 0",
    "Counter += -1", "Counter += param", "pass", "nop", "Counter += 1; Counter -= 1", "Other += 1", "Counter = true",
    "Counter = _", "Counter *= 2", "Counter += 0x10", "Counter -= 4294967297", "Counter += 2147483648", "Counter = other",
    "Counter += 1_0", "Counter -= 0b11", "Counter += ٣", "Counter = ٣", "Counter += 0x٣", "Counter -= １２", "Counter = 0_0",
    "Counter += 1__0", "Counter += _1", "Counter += 1_", "Counter += 0x_1f", "Counter += -0", "Counter += 00", "Counter += 0 ", "Counter = Counter - -2", "Counter", "", "Counter + 1", "Counter = 1 + 2",
]
TRIGGERS = [
    "<- Pulse(param) :: {g} => {a} .",
    "on Pulse(param) when {g} => {a} commit;",
    "<- (param) :: {g} => {a} .",
    "<- param :: {g} => {a} ;",
    "<- Pulse(param: i32) :: {g} => {a} commit",
    "on write(param) when {g} => {a} .;",
    "on input(param: u64) when {g} => {a} commit;",
    "<- :: {g} => {a} .",
    "<- when {g} => {a} .",
    "on Pulse when {g} => {a} .",
    "<- Pulse(param) :: {g} => {a} •",
    "<- Pulse(param) :: {g} => {a} •;",
    "<- Pulse(param) :: {g} => {a} .;",
    "<- Pulse(param) :: {g} => {a} commit;",
    "<- Pulse(param) :: {g} => {a} ; ;",
    "<- Pulse(param) :: {g} => {a} commit ;",
    "<- Pulse(param) :: {g} => {a} . .",
]
NO_GUARD_TRIGGERS = [
    "<- Pulse(param) => {a} .",
    "on Pulse(param) => {a} commit;",
    "<- param => {a} .",
    "on write => {a} .",
    "on Pulse(param) => {a}",
    "<- Pulse(param) => {a}",
]


def single_concept(rule_lines: str, init: str = "10", typ: str = "i32", inv: str = " [>= 0]", tests: str = "",
                   module: str = "module G;\n") -> str:
    return f"{module}@stdin\n@stdout\nconcept Counter: {typ} = {init}{inv} {{\n    {rule_lines}\n}}\n{tests}"


TEST_OK = "\ntest T {\n    send Counter(5);\n    expect Counter >= 0;\n}\n"


def grid(rng: random.Random) -> dict[str, str]:
    out: dict[str, str] = {}
    combos = list(itertools.product(GUARDS, ACTIONS))
    rng.shuffle(combos)
    for idx, (g, a) in enumerate(combos[:300]):
        trig = TRIGGERS[idx % len(TRIGGERS)] if g is not None else NO_GUARD_TRIGGERS[idx % len(NO_GUARD_TRIGGERS)]
        rule = trig.format(g=g, a=a)
        tests = TEST_OK if idx % 3 == 0 else ""
        out[f"grid:single:{idx}"] = single_concept(rule, tests=tests)
    # every guard with a plain increment, with and without a test (CME-1 / CME-2 paths)
    for idx, g in enumerate(GUARDS):
        for t_idx, tests in enumerate(("", TEST_OK)):
            rule = (TRIGGERS[idx % len(TRIGGERS)] if g is not None else NO_GUARD_TRIGGERS[0]).format(g=g, a="Counter += 1")
            out[f"grid:guard:{idx}:{t_idx}"] = single_concept(rule, tests=tests)
    # every action under a trivial guard
    for idx, a in enumerate(ACTIONS):
        for t_idx, tests in enumerate(("", TEST_OK)):
            out[f"grid:action:{idx}:{t_idx}"] = single_concept(f"<- Pulse(param) :: param < 50 => {a} .", tests=tests)
    return out


HEADERS = {
    "types": ["i32", "int32", "Int32", "u64", "uint64", "U64", "f64", "float64", "Float", "bool", "Bool", "?", "i64", "I32", ""],
    "inits": ["0", "1", "-1", "10", "2147483647", "2147483648", "-2147483648", "-2147483649", "0x10", "0X10", "010", "00",
              "1_000", "+5", "0b11", "0o7", "true", "false", "True", "!", "~false", "_", "undef", "Unknown", "1.5", "1e3", "inf",
              "nan", "5.", ".5", "abc", "٣", "0x٣", "１２", "1_٣", "\u3000 5", "5\x1c", "1 0", "0b", "0x", "0xg", "-0", "- 5", "+-5", "1e400", "1_0.5", ".5e1", "1.e2", "nan", "-inf", "infinity", "18446744073709551615", "18446744073709551616", ""],
    "invs": ["", " [>= 0]", " [> -1]", " [> -2]", " [>= 1]", " [>= -1]", " [0..100]", " [-5..5]", " [5..1]", " [<= 200]",
             " [Counter >= 0]", " [Other >= 0]", " [>= 0, <= 9]", " [>= 0,]", " []", " [ ]", " [,]", " [x]", " [>= 010]",
             " [0x1..0x9]", " [== 0]", " [!= 3]", " [>=0]", " [ >= 0 ]", " [\n>= 0\n]", " [>= 0] [>= 1]"],
}


def header_grid(rng: random.Random) -> dict[str, str]:
    out: dict[str, str] = {}
    rule = "<- Pulse(param) :: param < 20 => Counter += 1 ."
    for typ in HEADERS["types"]:
        for init in rng.sample(HEADERS["inits"], 9):
            out[f"grid:header:{typ}:{init}"] = single_concept(rule, init=init, typ=typ)
    for inv in HEADERS["invs"]:
        out[f"grid:inv:{inv!r}"] = single_concept(rule, inv=inv)
        out[f"grid:invbody:{inv!r}"] = single_concept(rule, inv="").replace(
            "    <- Pulse", f"    invariant{inv.replace('[', ' ').replace(']', ';')}\n    <- Pulse")
    for body in ["invariant >= 0;", "invariant: >= 0;", "invariant NonNeg: >= 0;", "invariant Counter >= 0.", "invariant;",
                 "invariant >= 0, <= 5;", "invariant 0..9;", "invariant", "@stdin;", "@stderr", "@stdout",
                 "invariant Foo >= 0;", "invariant 3..1;"]:
        out[f"grid:body:{body}"] = single_concept(f"{body}\n    <- Pulse(param) => Counter += 1 .", inv="")
    return out


MULTI = {
    "chain4": """module Chain;
concept A: i32 = 0 [>= 0] {
    <- EvA(p) :: p < 100 => A += 1 .
}
concept B: i32 = 0 [>= 0] {
    ~ A :: A >= 1 => B += 1 .
}
concept C: i32 = 5 [>= 0] {
    ~ B :: B > 0 => C -= 1 .
}
""",
    "keyword": """module KeywordChain;
concept A: int32 = 3 [>= 0] {
    on EvA(p) when p in 0..9 => A += 2 commit;
}
concept B: int32 = 0 [>= 0] {
    on change(A) when A >= 5 => B = A commit;
}
test T {
    send A(4);
    expect A == 5;
    expect B == 5;
    send EvA(20);
    expect A == 5;
}
""",
    "cycle": "concept C0: i32 = 0 [>= 0] { ~ C1 :: C1 >= 1 => C0 += 1 . }\nconcept C1: i32 = 0 [>= 0] { ~ C0 :: C0 >= 1 => C1 += 1 . }\n",
    "self": "concept C0: i32 = 0 [>= 0] { ~ C0 :: C0 >= 1 => C0 += 1 . }\n",
    "undeclared": "concept C0: i32 = 0 [>= 0] { ~ Nope :: Nope >= 1 => C0 += 1 . }\n",
    "fanout": """concept A: i32 = 0 [>= 0] { <- E(p) => A += 1 . }
concept B: i32 = 0 [>= 0] { ~ A :: A >= 1 => B += 1 . }
concept C: i32 = 0 [>= 0] { ~ A :: A >= 1 => C += 1 . }
""",
    "active_init": """concept A: i32 = 3 [>= 0] { <- E(p) => A += 1 . }
concept B: i32 = 0 [>= 0] { ~ A :: A >= 1 => B += 1 . }
""",
    "assign_publisher": """concept A: i32 = 0 [>= 0] { <- E(p) => A = p . }
concept B: i32 = 0 [>= 0] { ~ A :: A >= 1 => B += 1 . }
""",
    "collision": """concept God: i32 = 0 [>= 0] {
    <- Ev(p) :: p in 0..100 => God += 5 .
}
""",
    "collision_cmp": "concept God: i32 = 0 [>= 0] { <- Ev(p) :: p < 100 => God -= 3 . }\n",
    "wrong_var": "concept A: i32 = 0 [>= 0] { <- E(p) :: q < 5 => A += 1 . }\n",
    "two_rules": "concept A: i32 = 0 [>= 0] {\n    <- E(p) => A += 1 .\n    <- F(p) => A += 2 .\n}\n",
    "no_rules": "concept A: i32 = 0 [>= 0] {\n}\n",
    "two_actions": "concept A: i32 = 0 [>= 0] { <- E(p) => A += 1; A += 2 . }\n",
    "foreign_target": "concept A: i32 = 0 [>= 0] { <- E(p) => B += 1 . }\nconcept B: i32 = 0 [>= 0] { <- F(q) => B += 1 . }\n",
    "dup_concept": "concept A: i32 = 0 [>= 0] { <- E(p) => A += 1 . }\nconcept A: i32 = 0 [>= 0] { <- F(p) => A += 1 . }\n",
    "dup_event": "concept A: i32 = 0 [>= 0] { <- E(p) => A += 1 . }\nconcept B: i32 = 0 [>= 0] { <- E(p) => B += 1 . }\n",
    "derived_clash": "concept A_B: i32 = 0 [>= 0] { <- (p) => A_B += 1 . }\nconcept AB: i32 = 0 [>= 0] { <- (p) => AB += 1 . }\ntest T { send AB(1); expect AB == 1; }\n",
    "derived_clash_notest": "concept A_B: i32 = 0 [>= 0] { <- (p) => A_B += 1 . }\nconcept AB: i32 = 0 [>= 0] { <- (p) => AB += 1 . }\n",
    "param_shadow": "concept A: i32 = 0 [>= 0] { <- E(A) => A += 1 . }\n",
    "event_is_state": "concept A: i32 = 0 [>= 0] { <- A(p) => A += 1 . }\n",
    "reserved_names": "concept state: i32 = 0 [>= 0] { <- event(p) => state += 1 . }\n",
    "reserved_module": "module Problem;\nconcept A: i32 = 0 [>= 0] { <- E(p) => A += 1 . }\n",
    "counter_dec": "concept Counter: i32 = 10 [>= 0] { <- (p) :: p < 20 => Counter -= 1 . }\n",
    "counter_dec1": "concept Counter: i32 = 1 [>= 0] { <- (p) :: p < 20 => Counter -= 1 . }\n",
    "counter_inc": "concept Counter: i32 = 1 [>= 0] { <- (p) :: p < 20 => Counter += 1 . }\n",
    "counter_other": "concept Counter: i32 = 1 [>= 0] { <- (p) :: p < 20 => Counter += 2 . }\n",
    "c_names": "concept C0: i32 = 10 [>= 0] { <- (p) :: p < 50 => C0 += 1 . }\nconcept C1: i32 = 0 [>= 0] { ~ C0 :: C0 > 10 => C1 += 1 . }\n",
    "bitmask_multi": """concept A: i32 = 0 [>= 0] { <- E(p) :: p is odd => A += 1 . }
concept B: i32 = 0 [>= 0] { ~ A :: A >= 1 => B += 1 . }
test T { send A(3); expect A == 1; }
""",
    "read_rule": "concept A: i32 = 0 [>= 0] {\n    <- (p) => A += p .\n    -> => . A = 0\n}\n",
    "read_after": "concept A: u64 = 0 [>= 0] {\n    on read => after A = 0;\n}\n",
    "read_guard": "concept A: i32 = 0 [>= 0] {\n    -> :: A > 0 => A = 0\n    on read when A > 1 => . A = 1\n}\n",
    "exec": "concept A: i32 = 0 [>= 0] {\n    | (a, b: i32) :: a == b => A = a .\n    on call(x) when x > 1 => A = x commit;\n    on exec => A = 1 ;\n}\n",
    "state_rule": "concept A: bool = _ {\n    when A is undef => A = true commit;\n    :: A == true => A = false .\n}\n",
    "multi_line_rule": "concept A: i32 = 0 [>= 0] {\n    <- E(p)\n        :: p < 5\n        => A += 1 .\n}\n",
    "rule_on_one_line": "concept A: i32 = 0 [>= 0] { <- E(p) => A += 1 . <- F(p) => A += 2 . }\n",
    "paren_split": "concept A: i32 = 0 [>= 0] {\n    <- E(p) :: (p < 5\n    ) => A += 1 .\n}\n",
    "annotations": "@stdout\n@stdout\n@stderr\nconcept A: i32 = 0 [>= 0] { <- E(p) => A += 1 . }\n@stdin\nconcept B: i32 = 0 [>= 0] { <- F(p) => B += 1 . }\n@stdin\n",
    "dangling": "@stdin\ntest T { send A(1); }\nconcept A: i32 = 0 [>= 0] { <- E(p) => A += 1 . }\n",
    "pragma_comments": "// @stdin A, B\n# @stdout A\n# @stderr B, C\n/* @stdin Z */\nconcept A: i32 = 0 [>= 0] { <- E(p) => A += 1 . } // tail\nconcept B: i32 = 0 [>= 0] { <- F(p) => B += 1 . } # tail\n",
    "pragma_weird": "# @stdin A;B c-d 1x\n# @stdinX Y\n#@stdout\nconcept A: i32 = 0 [>= 0] { <- E(p) => A += 1 . }\n",
    "block_unterminated": "/* never closed\nconcept A: i32 = 0 [>= 0] { <- E(p) => A += 1 . }\n",
    "empty": "   \n  // nothing\n",
    "only_module": "module M;\n",
    "module_brace": "module M {\nconcept A: i32 = 0 [>= 0] { <- E(p) => A += 1 . }\n}\n",
    "module_brace_trailing": "module M {\nconcept A: i32 = 0 [>= 0] { <- E(p) => A += 1 . }\n} extra\n",
    "module_default_name": "module EkpolModule;\nconcept Counter: i32 = 10 [>= 0] { <- (p) => Counter -= 1 . }\n",
    "unclosed_concept": "concept A: i32 = 0 [>= 0] { <- E(p) => A += 1 .\n",
    "unclosed_test": "concept A: i32 = 0 [>= 0] { <- E(p) => A += 1 . }\ntest T { send A(1);\n",
    "garbage": "concept A: i32 = 0 [>= 0] { <- E(p) => A += 1 . }\nfoo bar\n",
    "multi_line_init": "concept A: i32 =\n 0 [>= 0] { <- E(p) => A += 1 . }\n",
    "unicode_alias": "concept A: ? = ¬ { when A == ¬ => A = ! • }\n",
    "unicode_text": "concept A: i32 = 0 [>= 0] { <- E(п) => A += 1 . }\n",
    "weird_ws": "concept\tA:\ti32\t=\t0\t[>= 0]\t{\r\n\t<-\tE(p)\t=>\tA\t+=\t1\t.\r\n}\r\n",
}

TEST_VARIANTS = [
    "send A(1); expect A == 1;",
    "send A(1)\nexpect A == 1",
    "step A(p = 1); expect A == 1;",
    "step A(p: 1); expect A = 1;",
    "send E(1); expect A == 1;",
    "send E(p = 3); expect A == 1; expect A != 2; expect A < 5; expect A > 0; expect A <= 1; expect A >= 1;",
    "send A(1); expect A == 2;",
    "send A(1); expect A == 1.0;",
    "send A(1); expect A == 1.5;",
    "send A(1); expect A == true;",
    "send A(1); expect A == _;",
    "send A(_); expect A == 0;",
    "send A(undef); expect A == 0;",
    "send A(invalid); expect A == 0;",
    "send A(1, 2, 3); expect A == 1;",
    "send A(0x1); expect A == 0x1;",
    "send A(-1); expect A == 0;",
    "send A(); expect A == 0;",
    "send A(,); expect A == 0;",
    "send A(= 5); expect A == 0;",
    "send A(x = ); expect A == 0;",
    "send Z(1); expect A == 0;",
    "expect A == 0;",
    "expect Z == 0;",
    "send A(1)",
    "",
    ";",
    ".",
    "send A(1). expect A == 1.",
    "bogus statement;",
    "expect A ~ 1;",
    "send A(010); expect A == 0;",
    "send A(1); expect A == 010;",
    "send A(1); expect A == 1e3;",
    "send A(1); expect A == nan;",
    "send A(1); expect A == inf;",
    "send A(1); expect A == 0.5;",
    "send A(1); expect A == 1e16;",
    "send A(1); expect A == 1e-5;",
    "send A(99999999999); expect A == 0;",
    "send A(1); expect A == 99999999999;",
    "send A(٣); expect A == ٣;",
    "send A(1); expect A == ٣.٥;",
    "send A(1); expect A == １e3;",
    "send A(1); expect A == 1_0;",
    "send A(1); expect A == 1_0.5;",
    "send A(1); expect A == -0.0;",
    "send A(1); expect A == 1e400;",
    "send A(1); expect A == -inf;",
    "send A(1); expect A == Infinity;",
    "send A(1); expect A == 0x1p3;",
    "send A(1); expect A == 123456789012345678.5;",
    "send A(1); expect A == 0.1;",
    "send A(1); expect A == 100000000000000000000.0;",
    "send A(1); expect A == 1.5e300;",
    "send A(\u3000 1 \u3000); expect A == 1;",
    "send A(1); expect A == -1;",
    "send A(1); expect A == !;",
    "send A(1); expect A == false;",
    "step E(1); step E(2); expect A == 3;",
    "send E(1); expect B == 0;",
]


def test_grid() -> dict[str, str]:
    out: dict[str, str] = {}
    for idx, body in enumerate(TEST_VARIANTS):
        out[f"grid:test:{idx}"] = (
            "module TG;\nconcept A: i32 = 0 [>= 0] {\n    <- E(p) :: p < 50 => A += 1 .\n}\n"
            f"test T {{\n    {body}\n}}\n"
        )
        out[f"grid:test2:{idx}"] = (
            "module TG;\nconcept A: i32 = 0 [>= 0] {\n    <- E(p) :: p < 50 => A += 1 .\n}\n"
            "concept B: i32 = 0 [>= 0] {\n    ~ A :: A >= 2 => B += 1 .\n}\n"
            f"scenario T {{\n    {body}\n}}\n"
        )
    return out


def structure_grid() -> dict[str, str]:
    return {f"grid:multi:{k}": v for k, v in MULTI.items()}


# ---------------------------------------------------------------- KPOL template grid (for KPOL -> EKPOL)
KPOL_SKELETON = """Problem M {{
    Invariants {{
        NonNeg: A >= 0;
    }}
}}

Solution M {{
    state A: Int32 = {init};
    event E(p: Int32);
    rule R on E when {guard} {{
        set A := {action};
    }}
}}
{proof}"""
KPOL_GUARDS = [
    "true", "false", "p < 5", "5 < p", "p >= 1 and p <= 9", "p <= 9 and p >= 1", "p > 0 and p < 10", "9 >= p and 1 <= p",
    "not (p < 5)", "not (p >= 1 and p <= 9)", "not not (p == 2)", "p == q", "p == true", "p >= true", "p < -5", "-5 < p",
    "p < 2.5", "p != 0 and p != 1", "p >= 1 and p >= 2", "p >= 1 and q <= 9", "p + 1 < 5", "p < 5 or p > 9", "(p < 5)",
    "not p", "Unknown", "p == Unknown", "p >= 1 and (p <= 9 and p != 5)", "p >= 1 and p", "-p < 5", "p == -Unknown",
    "p < --5", "gcd(p, 2) == 1", "1 < p and p < 3", "p > 1.5 and p < 3.5", "p >= 007 and p <= 9", "not (not (p > 1) and p < 4)",
    "p >= 0 and p <= 0", "p = 5",
]
KPOL_ACTIONS = [
    "A + 1", "A - 1", "A + 5", "5 + A", "A - 5", "5 - A", "p", "3", "A", "A * 2", "A + 2.5", "A + true", "A + Unknown",
    "Unknown", "-A", "gcd(A, p)", "A + p", "(A + 1)", "A + 1 + 1", "1 + A + 1", "-3", "1.50", "true", "A - 0", "0 + A",
]
KPOL_PROOFS = [
    "",
    "\nProof M {\n    scenario S {\n        step E(p = 5);\n        expect A == 1;\n    }\n}\n",
    "\nProof M {\n    scenario S {\n        step E(p = -3);\n        expect A >= 0;\n        step E(p = 2);\n        expect 0 <= A;\n    }\n}\n",
    "\nProof M {\n    scenario S {\n        step E(p = 2.5);\n        step E(p = true);\n        step E(p = 007);\n        expect A == B;\n        expect A + 1 == 2;\n        expect not (A == 0);\n    }\n}\n",
    "\nProof M {\n    scenario S {\n        step E(p = -2.5);\n        step E(p = --3);\n        expect A != 7;\n    }\n}\n",
    "\nProof M {\n    scenario S {\n        step E(p = -Unknown);\n    }\n}\n",
    "\nProof M {\n    scenario S {\n        step E();\n        expect A == 0;\n    }\n}\n",
    "\nProof M {\n    scenario S {\n        step E(p = 1, q = 2);\n        expect A == 0;\n    }\n}\n",
    "\nProof M {\n    assert Stays on E when p > 0 expect A >= 0;\n    scenario S {\n        step E(p = 1);\n        expect A >= 0;\n    }\n    scenario T {\n        step F(p = 1);\n        expect A == 1.5;\n        expect A == true;\n        expect A == Unknown;\n    }\n}\n",
    "\nProof M {\n    scenario S {\n        step Nope(p = 1);\n        expect A == 1;\n    }\n}\n",
    "\nProof M {\n}\n",
]
KPOL_INITS = ["0", "10", "-1", "2.5", "true", "0x1", "007", "-3 + 4", "Unknown", "A", "2147483648"]

KPOL_MULTI = [
    """Problem M {
    Invariants {
        I_A: A >= 0;
        I_B: B >= 0;
    }
}
Solution M {
    state A: Int32 = 0;
    state B: Int32 = 0;
    event E(p: Int32);
    rule R1 on E when p < 5 { set A := A + 1; }
    rule R2 on change(A) when A >= 1 { set B := A; }
}
""",
    """Problem M { Invariants { I_A: A >= 0; } }
Solution M {
    state A: Int32 = 0;
    state B: Int32 = 3;
    event E(p: Int32);
    event F(q: Int32);
    rule R1 on E when true { set A := 1 + A; }
    rule R2 on F when q in 3 { set B := B - 1; }
}
""",
    """Problem M { Invariants { I_A: A >= 0; } }
Solution M {
    state A: Int32 = 0;
    event E(p: Int32, q: Int32);
    rule R1 on E when p < q { set A := A + 1; set A := A + 2; }
}
""",
    """Problem M { Invariants { I_A: A >= 0; } }
Solution M {
    state A: Int32 = 0;
    state B: Int32 = 0;
    rule R2 on change(A, B) when A >= 1 { set B := A; }
}
""",
    """Problem M { Invariants { I_A: A >= 0; } }
Solution M {
    state A: Int32 = 0;
    event E(p: Int32);
    rule R1 on E when p < 5 { set A := A + 1; }
    rule R2 on reject E when p >= 5 { set A := 0; }
}
""",
    """Problem M { Hazards { H1 on E to A: p > 100; } Invariants { I_A: A >= 0; } }
Solution M {
    state A: Int32 = 0;
    event E(p: Int32);
    rule R1 on E when p < 5 covers C1 { set A := A + 1; }
}
""",
    """Problem M { Invariants { I_A: A >= 0; } }
Solution M {
    state A: Int32 = 0;
    event E(p: Int32);
    rule R1 on E when p < 5 { set A := A + 1; }
    rule R3 on E when p > 7 { set A := A - 1; }
}
Proof M {
    scenario S { step E(p = 1); expect A == 1; step E(p = 9); expect A == 0; }
}
""",
    """# @stdin A
# @stdout A, B
# @stderr B
Problem M { Invariants { I_A: A >= 0; } }
Solution M {
    state A: Int32 = 0;
    state B: Int32 = 0;
    event E(p: Int32);
    rule R1 on E when p < 5 { set A := A + 1; }
    rule R2 on change(A) when A > 0 { set B := B + 1; }
}
""",
    """Problem M { Invariants { I_A: A >= 0; } }
Solution M {
    event E(p: Int32);
    rule R1 on E when p < 5 { set A := A + 1; }
}
""",
    """Problem M { Invariants { I_A: A >= 0; } }
Solution M {
    state A: Int32 = 0;
    state B: Int32 = 0;
    event E(p: Int32);
    rule R1 on E when p < 5 { set A := A + 1; }
    rule R2 on E when p < 5 { set A := A + 2; }
    rule R3 on change(A) when (*) A < 0 { set B := A; }
}
""",
]


def kpol_grid(rng: random.Random) -> dict[str, str]:
    out: dict[str, str] = {}
    combos = list(itertools.product(KPOL_GUARDS, KPOL_ACTIONS))
    rng.shuffle(combos)
    for idx, (g, a) in enumerate(combos[:260]):
        out[f"kgrid:single:{idx}"] = KPOL_SKELETON.format(
            init=rng.choice(KPOL_INITS) if idx % 4 == 0 else "0", guard=g, action=a, proof=rng.choice(KPOL_PROOFS))
    for idx, proof in enumerate(KPOL_PROOFS):
        for g in ("p < 5", "p >= 1 and p <= 9"):
            out[f"kgrid:proof:{idx}:{g}"] = KPOL_SKELETON.format(init="0", guard=g, action="A + 1", proof=proof)
    for idx, src in enumerate(KPOL_MULTI):
        out[f"kgrid:multi:{idx}"] = src
    return out


# ---------------------------------------------------------------- main
def main() -> None:
    rng = random.Random(SEED)
    ek_src = corpus(".ekpol", "ekpol")
    kp_src = corpus(".kpol", "kpol")

    ek_cases: dict[str, str] = {f"corpus:{k}": v for k, v in ek_src.items()}
    ek_cases.update(grid(rng))
    ek_cases.update(header_grid(rng))
    ek_cases.update(test_grid())
    ek_cases.update(structure_grid())
    ek_cases.update(mutations({k: v for k, v in ek_src.items()}, 30, EK_VOCAB, rng))
    # extra mutation pass over the structural templates (negative-control rich)
    ek_cases.update(mutations({f"tmpl:{k}": v for k, v in MULTI.items()}, 4, EK_VOCAB, rng))
    fuzz_bases = {k: v for k, v in ek_src.items() if len(v) < 1500}
    fuzz_bases.update({f"tmpl:{k}": v for k, v in MULTI.items()})
    ek_cases.update(charfuzz(fuzz_bases, 7, rng))

    # KPOL inputs: repo corpus, Python's own EKPOL -> KPOL output, and mutations of both
    kp_cases: dict[str, str] = {f"corpus:{k}": v for k, v in kp_src.items()}
    kp_cases.update(kpol_grid(rng))
    generated = {}
    for name, src in sorted(ek_cases.items()):
        res = call(ef.transpile_ekpol_to_kpol, src)
        if res["ok"] and res["value"] not in generated.values() and len(generated) < 150:
            generated[f"fromekpol:{name}"] = res["value"]
    kp_cases.update(generated)
    kp_cases.update(mutations({k: v for k, v in list(kp_src.items())}, 24, KP_VOCAB, rng))
    kp_cases.update(mutations(dict(itertools.islice(generated.items(), 40)), 3, KP_VOCAB, rng))
    kp_cases.update(charfuzz({k: v for k, v in kp_src.items() if len(v) < 2500}, 6, rng))

    cases = []
    for name, src in sorted(ek_cases.items()):
        c = ekpol_case(src)
        c["id"] = name
        cases.append(c)
    for name, src in sorted(kp_cases.items()):
        c = kpol_case(src)
        c["id"] = name
        cases.append(c)

    with goldenio.open_gz_text(OUT) as fh:
        fh.write('{"generator":"gen_ekpol_golden.py","seed":%d,"cases":[\n' % SEED)
        fh.write(",\n".join(json.dumps(c, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for c in cases))
        fh.write("\n]}\n")

    n_ek = sum(1 for c in cases if c["kind"] == "ekpol")
    n_mut = sum(1 for c in cases if c["id"].startswith("mut:"))
    ok_img = sum(1 for c in cases if c["kind"] == "ekpol" and c.get("image", {}).get("ok"))
    crashes = sum(1 for c in cases for v in c.values() if isinstance(v, dict) and "crash" in v)
    print(f"cases={len(cases)} ekpol={n_ek} kpol={len(cases) - n_ek} mutations={n_mut} accepted_images={ok_img} crashes={crashes}")


if __name__ == "__main__":
    main()
