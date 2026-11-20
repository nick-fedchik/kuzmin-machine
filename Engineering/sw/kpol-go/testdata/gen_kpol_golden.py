#!/usr/bin/env python3
"""Generate testdata/kpol_golden.json.gz for the Go port of the KPOL front end.

The reference implementation Engineering/sw/kpol-ref/kpol_reference.py is run on
a corpus and the observable results are recorded:

* repository .kpol files, ```kpol fences of the Markdown documents and the KPOL
  program strings found in the Python tests;
* hand-written lexical, syntactic, static and dynamic corner cases;
* a type-compatibility matrix and >= 300 systematic mutations of base programs
  (token deletion / duplication / swap / replacement, number and operator
  changes, stray characters);
* expression-level value matrices (numeric tower: bool, int, Decimal, float,
  Unknown), normalisation cases and randomised Decimal arithmetic.

Everything is deterministic (fixed seeds, sorted inputs).

Usage (from Engineering/sw/kpol-go):  python3 testdata/gen_kpol_golden.py
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import random
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import goldenio  # noqa: E402
REPO = HERE.parents[3]
REF_DIR = REPO / "Engineering" / "sw" / "kpol-ref"
OUT = HERE / "kpol_golden.json.gz"

sys.path.insert(0, str(REF_DIR))
sys.setrecursionlimit(3000)
import kpol_reference as kr  # noqa: E402

SEED = 20261120


# --------------------------------------------------------------------------
# Encoding helpers
# --------------------------------------------------------------------------

def enc(v) -> str:
    """Tagged text for a runtime value: b:, i:, d:, f:, u."""
    if v is kr.UNKNOWN:
        return "u"
    if isinstance(v, bool):
        return "b:" + ("true" if v else "false")
    if isinstance(v, int):
        if v.bit_length() > 12000:
            return "i:" + hex(v)  # str(int) is limited to 4300 digits
        return "i:" + str(v)
    if isinstance(v, Decimal):
        return "d:" + str(v)
    if isinstance(v, float):
        return "f:" + repr(v)
    raise TypeError(f"cannot encode {v!r}")


def exc_info(e: BaseException) -> dict:
    if isinstance(e, kr.KpolError):
        return {"kind": "kpol", "text": str(e)}
    return {"kind": "crash", "text": f"{type(e).__name__}"}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def enc_state(state: dict) -> list:
    return [[k, enc(v)] for k, v in state.items()]


# --------------------------------------------------------------------------
# AST dump (must match dumpModule in kpol/golden_test.go)
# --------------------------------------------------------------------------

def dump_expr(e) -> str:
    if isinstance(e, kr.Literal):
        v = e.value
        if v is kr.UNKNOWN:
            return "(lit unk)"
        if isinstance(v, bool):
            return "(lit bool " + ("true" if v else "false") + ")"
        if isinstance(v, int):
            return f"(lit int {v})"
        if isinstance(v, Decimal):
            return f"(lit dec {v})"
        raise TypeError(v)
    if isinstance(e, kr.Name):
        return f"(name {e.value})"
    if isinstance(e, kr.Unary):
        return f"(un {e.operator} {dump_expr(e.operand)})"
    if isinstance(e, kr.Binary):
        return f"(bin {e.operator} {dump_expr(e.left)} {dump_expr(e.right)})"
    if isinstance(e, kr.Call):
        return f"(call {e.name} " + " ".join(dump_expr(a) for a in e.arguments) + ")"
    raise TypeError(e)


def dump_type(t: kr.TypeRef) -> str:
    return t.name + (f"<{t.unit}>" if t.unit else "")


def dump_module(m: kr.Module) -> str:
    out = [f"module {m.name} aliases={int(m.phase_aliases_used)} proof={int(m.proof_present)}"]
    for r in m.requirements:
        out.append(f"req {r.kind} {r.name} on={r.event or '-'} to={r.target or '-'} {dump_expr(r.expression)}")
    for e in m.events:
        out.append("event " + e.name + "(" + ",".join(f"{n}:{dump_type(t)}" for n, t in e.parameters) + ")")
    for s in m.states:
        out.append(f"state {s.name} {dump_type(s.type_ref)} {dump_expr(s.initial)}")
    for r in m.rules:
        on = "change(" + ",".join(r.watch) + ")" if r.event == "change" else r.event
        out.append(f"rule {r.name} on={on} reject={int(r.reject)} covers={r.covers or '-'} when {dump_expr(r.guard)}")
        for a in r.actions:
            out.append(f"  set {a.name} {dump_expr(a.expression)}")
    for p in m.proofs:
        if isinstance(p, kr.AssertPropertyDecl):
            out.append(f"assert {p.name} on={p.event} when {dump_expr(p.guard)} expect {dump_expr(p.expectation)}")
        else:
            out.append(f"scenario {p.name}")
            for s in p.steps:
                if isinstance(s, kr.StepAction):
                    out.append(f"  step {s.event_name} " + " ".join(f"{n}={dump_expr(v)}" for n, v in s.arguments))
                else:
                    out.append(f"  expect {dump_expr(s.expression)}")
    return "\n".join(out)


# --------------------------------------------------------------------------
# Running the reference on one source
# --------------------------------------------------------------------------

def token_digest(source: str) -> dict:
    try:
        toks = kr.tokenize(source)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": exc_info(e)}
    text = "\n".join(f"{t.kind}\t{t.value}\t{t.line}\t{t.column}" for t in toks)
    return {"ok": True, "n": len(toks), "sha": sha(text)}


def literals_of(module: kr.Module) -> list:
    found: list = []

    def walk(e):
        if isinstance(e, kr.Literal):
            if isinstance(e.value, (int, Decimal)) and not isinstance(e.value, bool):
                found.append(e.value)
        elif isinstance(e, kr.Unary):
            walk(e.operand)
        elif isinstance(e, kr.Binary):
            walk(e.left)
            walk(e.right)
        elif isinstance(e, kr.Call):
            for a in e.arguments:
                walk(a)

    for r in module.requirements:
        walk(r.expression)
    for s in module.states:
        walk(s.initial)
    for r in module.rules:
        walk(r.guard)
        for a in r.actions:
            walk(a.expression)
    for p in module.proofs:
        if isinstance(p, kr.AssertPropertyDecl):
            walk(p.guard)
            walk(p.expectation)
        else:
            for s in p.steps:
                if isinstance(s, kr.StepAction):
                    for _, v in s.arguments:
                        walk(v)
                else:
                    walk(s.expression)
    return found


def candidate_values(type_ref: kr.TypeRef, lits: list, rng: random.Random):
    ints = {0, 1, -1, 2, 5, 10}
    for lit in lits:
        try:
            base = int(lit)
        except Exception:  # noqa: BLE001
            continue
        if abs(base) < 10**12:
            ints.update({base - 1, base, base + 1})
    ints = sorted(ints)
    name = type_ref.name
    if name == "Bool":
        return [True, False, True, False, kr.UNKNOWN], [True, False]
    if name == "Int32":
        main = [i for i in ints if -(2**31) <= i < 2**31]
        return main + [2**31 - 1, -(2**31), 2**31, True, kr.UNKNOWN], main
    if name == "U32":
        main = [i for i in ints if 0 <= i < 2**32]
        return main + [2**32 - 1, 2**32, -1, kr.UNKNOWN], main
    if name == "U64":
        main = [i for i in ints if 0 <= i < 2**64]
        return main + [2**64 - 1, 2**64, -1, kr.UNKNOWN], main
    if name == "Float":
        main = [Decimal(i) for i in ints] + [Decimal("0.5"), Decimal("100.25"), Decimal("-2.5")]
        for lit in lits:
            if isinstance(lit, Decimal):
                main += [lit, lit + Decimal("0.5")]
        return main + [3, 2.5, True, kr.UNKNOWN], main
    if name == "Pin":
        return [0, 1, True, False, 1, 0, 2, kr.UNKNOWN], [0, 1, True, False]
    return [kr.UNKNOWN], [kr.UNKNOWN]


def make_runs(module: kr.Module, rng: random.Random, n_random: int) -> list:
    """Build run scripts (options + batches of events) for a module."""
    lits = literals_of(module)
    events = list(module.events)
    states = {s.name: s.type_ref for s in module.states}
    scripts: list[dict] = []

    def payload_for(event, wide: bool) -> dict:
        payload = {}
        for pname, ptype in event.parameters:
            full, main = candidate_values(ptype, lits, rng)
            pool = full if wide else main
            payload[pname] = rng.choice(pool)
        return payload

    def ev(event, wide=False):
        return {"name": event.name, "payload": payload_for(event, wide)}

    scripts.append({"opts": {}, "batches": [[]]})
    if events:
        scripts.append({"opts": {}, "batches": [[ev(e) for e in events]]})
    for k in range(n_random):
        if not events:
            break
        opts: dict = {}
        if k % 3 == 1:
            opts["fail_closed"] = False
        if k % 4 == 2 and states:
            name = rng.choice(sorted(states))
            full, main = candidate_values(states[name], lits, rng)
            opts["overrides"] = {name: rng.choice(full)}
        if k % 5 == 3:
            opts["max_events"] = rng.choice([3, 6, 40])
        batches = []
        for _ in range(rng.choice([1, 1, 2])):
            n = rng.randint(1, 7)
            batches.append([ev(rng.choice(events), wide=rng.random() < 0.3) for _ in range(n)])
        scripts.append({"opts": opts, "batches": batches})
    if events:
        e0 = events[0]
        scripts.append({"opts": {}, "batches": [[{"name": "NoSuchEvent", "payload": {}}]]})
        if e0.parameters:
            scripts.append({"opts": {}, "batches": [[{"name": e0.name, "payload": {}}]]})
        scripts.append({"opts": {}, "batches": [[{"name": "change", "payload": {}}]]})
    return scripts


def run_script(module: kr.Module, script: dict) -> dict:
    opts = script.get("opts", {})
    out: dict = {"opts": {}, "batches": []}
    if "fail_closed" in opts:
        out["opts"]["fail_closed"] = opts["fail_closed"]
    if "overrides" in opts:
        out["opts"]["overrides"] = {k: enc(v) for k, v in opts["overrides"].items()}
    if "max_events" in opts:
        out["opts"]["max_events"] = opts["max_events"]
    try:
        interp = kr.Interpreter(
            module,
            initial=dict(opts["overrides"]) if "overrides" in opts else None,
            fail_closed_hazards=opts.get("fail_closed", True),
        )
    except Exception as e:  # noqa: BLE001
        out["init_error"] = exc_info(e)
        return out
    out["init_state"] = enc_state(interp.state)
    max_events = opts.get("max_events", 10000)
    for batch in script["batches"]:
        entry: dict = {"events": [{"name": b["name"], "payload": {k: enc(v) for k, v in b["payload"].items()}} for b in batch]}
        try:
            res = interp.run([kr.EventInput(b["name"], dict(b["payload"])) for b in batch], max_events=max_events)
            entry["result"] = {
                "state": enc_state(res.state),
                "hazards": res.hazards,
                "alerts": res.alerts,
                "rejected": res.rejected,
                "diagnostics": res.diagnostics,
                "goal_failures": res.goal_failures,
                "steps": res.steps,
            }
        except Exception as e:  # noqa: BLE001
            entry["error"] = exc_info(e)
            entry["state_after"] = enc_state(interp.state)
            out["batches"].append(entry)
            break
        out["batches"].append(entry)
    return out


def verify_result(module: kr.Module, fail_closed: bool) -> dict:
    try:
        rep = kr.verify_module(module, fail_closed_hazards=fail_closed)
    except Exception as e:  # noqa: BLE001
        return {"error": exc_info(e)}
    return {
        "total": rep.total_checks,
        "passed": rep.passed_checks,
        "failures": [[f.scenario_or_assert, f.message] for f in rep.failures],
    }


def make_case(cid: str, group: str, source: str, rng: random.Random, light: bool = False,
              n_random: int = 4, scripts: list | None = None) -> dict:
    case: dict = {"id": cid, "group": group, "source": source, "tokens": token_digest(source)}
    try:
        module = kr.Parser(source).parse()
    except Exception as e:  # noqa: BLE001
        case["syntax"] = {"ok": False, "error": exc_info(e)}
        case["parse"] = {"ok": False, "error": exc_info(e)}
        return case
    dump = dump_module(module)
    case["syntax"] = {"ok": True, "ast_sha": sha(dump)}
    if len(dump) <= 1500:
        case["syntax"]["ast"] = dump
    try:
        kr.check_module(module)
    except Exception as e:  # noqa: BLE001
        case["parse"] = {"ok": False, "error": exc_info(e)}
        return case
    case["parse"] = {"ok": True}
    if light:
        return case
    case["verify"] = verify_result(module, True)
    case["verify_open"] = verify_result(module, False)
    runs = make_runs(module, rng, n_random)
    if scripts:
        runs = scripts + runs
    case["runs"] = [run_script(module, s) for s in runs]
    return case


# --------------------------------------------------------------------------
# Corpus collection
# --------------------------------------------------------------------------

GO_PORT_DIR = REPO / "Engineering" / "sw" / "kpol-go"


def corpus_files(root: Path, pattern: str):
    """Sorted files under root matching pattern, excluding the Go port's own tree."""
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
        for path in corpus_files(root, "test_*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    s = node.value
                    if "Problem" in s and "Solution" in s and "{" in s and len(s) < 20000:
                        found.setdefault(s, f"{path.relative_to(REPO)}:{node.lineno}")
    return [(loc, src) for src, loc in sorted(found.items(), key=lambda kv: (kv[1], kv[0]))]


def collect_corpus() -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add(cid, group, src, dedupe=True):
        if dedupe and src in seen:
            return
        seen.add(src)
        out.append((cid, group, src))

    # every repository file is its own case, even when its text repeats
    for path in corpus_files(REPO / "Engineering", "*.kpol"):
        add(f"file:{path.relative_to(REPO)}", "corpus", path.read_text(encoding="utf-8"), dedupe=False)
    md_files = list(corpus_files(REPO / "Engineering", "*.md"))
    for path in md_files:
        for i, block in enumerate(md_blocks(path)):
            add(f"md:{path.relative_to(REPO)}#{i}", "guide", block)
    for loc, src in python_test_sources():
        add(f"pytest:{loc}", "pytest", src)
    return out


# --------------------------------------------------------------------------
# Mutations
# --------------------------------------------------------------------------

ALIAS_LEN = {"ALIAS_PHASE": None, "ALIAS_WRITE": None, "ALIAS_READ": None}


def token_spans(source: str):
    toks = kr.tokenize(source)[:-1]
    starts = [0]
    for i, ch in enumerate(source):
        if ch == "\n":
            starts.append(i + 1)
    spans = []
    for t in toks:
        off = starts[t.line - 1] + t.column - 1
        if t.kind.startswith("ALIAS"):
            for a in ("(*)", "<-", "->", "←", "→", "•"):
                if source.startswith(a, off):
                    length = len(a)
                    break
        else:
            length = len(t.value)
        spans.append((t, off, off + length))
    return spans


BIN_OPS = ["+", "-", "*", "/", "==", "!=", "<", "<=", ">", ">=", "and", "or"]
NUM_REPL = ["0", "1", "2", "7", "100", "2147483647", "2147483648", "4294967296", "18446744073709551616",
            "1.5", "2.0", "0.0", "007", "0.25", "99999999999999999999"]
STRAY = ["!", "@", '"', "'", ".", "[", "|", "&", "²", "é", "\u00a0", "#", "/*", "$", "~", "`", "\\"]
KEYWORDS = sorted(kr.Parser._reserved)
PUNCT_SWAP = ["{", "}", "(", ")", ":", ",", ";", "=", ":=", "<", ">"]
VOCAB = KEYWORDS + BIN_OPS + PUNCT_SWAP + ["x", "0", "1", "1.5", "Unknown", "•", "(*)", "<-", "->"]


def mutate(source: str, rng: random.Random, kind: str) -> str | None:
    spans = token_spans(source)
    if not spans:
        return None
    ids = sorted({t.value for t, _, _ in spans if t.kind == "ID" and t.value not in kr.Parser._reserved})

    def pick(pred):
        cand = [s for s in spans if pred(s[0])]
        return rng.choice(cand) if cand else None

    def splice(a, b, text):
        return source[:a] + text + source[b:]

    if kind == "del":
        t, a, b = rng.choice(spans)
        return splice(a, b, "")
    if kind == "dup":
        t, a, b = rng.choice(spans)
        return splice(a, b, source[a:b] + " " + source[a:b])
    if kind == "swap":
        if len(spans) < 2:
            return None
        i = rng.randrange(len(spans) - 1)
        (_, a1, b1), (_, a2, b2) = spans[i], spans[i + 1]
        return source[:a1] + source[a2:b2] + source[b1:a2] + source[a1:b1] + source[b2:]
    if kind == "num":
        s = pick(lambda t: t.kind == "NUMBER")
        if not s:
            return None
        return splice(s[1], s[2], rng.choice(NUM_REPL))
    if kind == "op":
        s = pick(lambda t: t.value in BIN_OPS)
        if not s:
            return None
        return splice(s[1], s[2], rng.choice([o for o in BIN_OPS if o != s[0].value]))
    if kind == "id":
        s = pick(lambda t: t.kind == "ID" and t.value not in kr.Parser._reserved)
        if not s:
            return None
        return splice(s[1], s[2], rng.choice(ids + KEYWORDS))
    if kind == "punct":
        s = pick(lambda t: t.kind == "PUNCT" or t.value in ("<", ">", ":="))
        if not s:
            return None
        return splice(s[1], s[2], rng.choice(PUNCT_SWAP))
    if kind == "ins":
        t, a, b = rng.choice(spans)
        return splice(a, a, rng.choice(VOCAB) + " ")
    if kind == "char":
        pos = rng.randrange(len(source))
        if rng.random() < 0.5:
            return source[:pos] + source[pos + 1:]
        return source[:pos] + rng.choice(STRAY) + source[pos:]
    if kind == "kw":
        s = pick(lambda t: t.value in kr.Parser._reserved)
        if not s:
            return None
        return splice(s[1], s[2], rng.choice(KEYWORDS))
    raise ValueError(kind)


MUTATION_KINDS = [("del", 6), ("dup", 4), ("swap", 4), ("num", 7), ("op", 7), ("id", 6),
                  ("punct", 4), ("ins", 4), ("char", 4), ("kw", 4)]


# --------------------------------------------------------------------------
# Hand-written cases
# --------------------------------------------------------------------------

def M(problem: str = "", states: str = "", events: str = "", rules: str = "", proof: str = "",
      name: str = "M") -> str:
    parts = [f"Problem {name} {{ {problem} }}", f"Solution {name} {{"]
    for blk in (events, states, rules):
        if blk:
            parts.append(blk)
    parts.append("}")
    if proof:
        parts.append(f"Proof {name} {{ {proof} }}")
    return "\n".join(parts)


LEX_CASES = [
    "", " ", "\n", "a<-1", "x->y", "a < -1", "(*)x", "f((*)x)", "•x", "←", "→", "1.", "1.5", "1.5.2",
    "007", "007.50", "0.0", "1..2", "1.a", "1.\n", "/* c */x", "/* unterminated", "/*/", "/**/", "/***/ y",
    "x//y\nz", "x#y\nz", "# only comment", "// only", "a!=b", "a!b", "!", "a=b", "a:=b", "a==b", "a<=b",
    "a>=b", "a<b>c", "@", '"', "'", ".5", "a.b", "змінна", "x²", "²", "٣٤", "٣.٥", "①", "\u00a0x",
    "x\r\ny", "a\x0bb", "\x1cx", "\u2028x", "\tx\n  y", "_x", "x_1", "1x", "Problem", "-5", "a-5",
    "a - -5", "}{)(;,:", "\U0001f4a9", "\x00", "\x7f", "é", "ǅ", "ǆ", "a\u200bb", "(*", "(*))", "<-->",
    "a<--1", "==", "===", "!==", ":= =", ": =", "ab\ncd\n\n  ef", "/* a\nb */ x", "x /* a\nb */ y // z\n w",
    "\u0660\u0661.\u0662", "9" * 30, "x" * 50, "1 2 3", "Float<V>", "• •", "(*)(*)", "a\u2029b", "\x85", "é1", "_",
    "__init__", "a\u00b7b", "Ⅷ", "½", "x\u0301", "٣x",
]

def lex_sweep_codepoints() -> list[int]:
    cps = list(range(0, 128))
    cps += [0x85, 0xA0, 0xAA, 0xB2, 0xB5, 0xB7, 0xBD, 0xC0, 0xD7, 0xE9, 0x1C5, 0x2B0, 0x300, 0x660, 0x6F0, 0x966, 0x1680,
            0x2000, 0x200A, 0x200B, 0x2028, 0x2029, 0x202F, 0x205F, 0x2160, 0x2460, 0x2776, 0x3000, 0x3007, 0x4E00,
            0xFF10, 0xFF21, 0xFFFD, 0x1D7CE, 0x1F4A9, 0x10FFFF, 0xE000, 0x2190, 0x2192, 0x2022, 0x2192]
    cps += list(range(0x100, 0x3000, 211))
    cps += list(range(0x3000, 0x20000, 997))
    return sorted(cp for cp in set(cps) if not 0xD800 <= cp <= 0xDFFF)  # lone surrogates are not valid UTF-8


TYPE_NAMES = ["Bool", "Int32", "U32", "U64", "Float<V>", "Float<A>", "Float<W>", "Float<s>", "Float<J>",
              "Float<degC>", "Pin", "Pin<a>", "Pin<b>"]
TYPE_INIT = {"Bool": "true", "Int32": "1", "U32": "1", "U64": "1", "Pin": "1"}


def type_init(t: str) -> str:
    if t.startswith("Float"):
        return "1.5"
    if t.startswith("Pin"):
        return "1"
    return TYPE_INIT[t]


def type_matrix() -> list[tuple[str, str]]:
    out = []
    for t1 in TYPE_NAMES:
        for t2 in TYPE_NAMES:
            for op in ["+", "-", "*", "/", "==", "<", "and"]:
                if op in "+-*/":
                    goal = f"(a {op} b) == (a {op} b)"
                else:
                    goal = f"a {op} b"
                src = M(problem=f"Goals {{ G: {goal}; }}",
                        states=f"state a: {t1} = {type_init(t1)};\n state b: {t2} = {type_init(t2)};")
                out.append((f"matrix:{t1}{op}{t2}", src))
    return out


def init_cases() -> list[tuple[str, str]]:
    out = []
    inits = [
        ("Int32", "2147483647"), ("Int32", "2147483648"), ("Int32", "-2147483648"), ("Int32", "-2147483649"),
        ("Int32", "2.0"), ("Int32", "1.5"), ("Int32", "1 + 1"), ("Int32", "-(3)"), ("Int32", "7 * 7"),
        ("Int32", "3 - 5"), ("Int32", "2 / 1"), ("Int32", "true"), ("Int32", "Unknown"), ("Int32", "gcd(12, 18)"),
        ("Int32", "0.0 + 2"), ("Int32", "2147483647 + 1"), ("Int32", "- -5"), ("Int32", "--5"),
        ("U32", "-1"), ("U32", "4294967295"), ("U32", "4294967296"), ("U32", "3 - 5"), ("U32", "5 - 3"),
        ("U64", "18446744073709551615"), ("U64", "18446744073709551616"), ("U64", "gcd(48, 18)"),
        ("U64", "gcd(-4, 6)"), ("U64", "gcd(true, 2)"), ("U64", "gcd(1.5, 2)"),
        ("Pin", "0"), ("Pin", "1"), ("Pin", "2"), ("Pin", "true"), ("Pin", "1.0"), ("Pin", "0.5"), ("Pin", "-1"),
        ("Pin", "1 - 1"), ("Pin", "3 - 2"), ("Pin", "1 + 1"), ("Pin", "false"),
        ("Float<V>", "1"), ("Float<V>", "1/3"), ("Float<V>", "10 / 4"), ("Float<V>", "0.1 + 0.2"),
        ("Float<V>", "Unknown"), ("Float<V>", "true"), ("Float<V>", "2.50"), ("Float<V>", "0.000001"),
        ("Float<V>", "0.0000001"), ("Float<V>", "1000000000000000000000000000000 * 1000000000"),
        ("Float<V>", "1/0"), ("Float<V>", "1.0/3.0"), ("Float<V>", "- 0.0"), ("Float<V>", "0 * -1.0"),
        ("Float<V>", "12345678901234567890123456789.5 + 1"), ("Float<V>", "7 / 2 * 3"),
        ("Float<degC>", "20.5"), ("Float<degC>", "20.5 + 1"),
        ("Bool", "1"), ("Bool", "true"), ("Bool", "not false"), ("Bool", "Unknown"), ("Bool", "1 == 1"),
        ("Bool", "Unknown == Unknown"), ("Bool", "• false"), ("Bool", "(*) true"), ("Bool", "true and Unknown"),
        ("Bool", "false and (1 / 0 == 1)"), ("Bool", "true or (1 / 0 == 1)"), ("Bool", "true and (1 / 0 == 1)"),
        ("Bool", "false or (1 / 0 == 1)"), ("Bool", "not Unknown"), ("Bool", "1 < Unknown"),
        ("Bool", "Unknown < 5"), ("Bool", "Unknown != 5"), ("Bool", "Unknown != Unknown"),
    ]
    for i, (t, e) in enumerate(inits):
        out.append((f"init:{t}={e}", M(states=f"state x: {t} = {e};")))
    return out


def static_cases() -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []

    def add(cid, src):
        cases.append((f"static:{cid}", src))

    ev_b = "event E(p: Int32);"
    add("dup-event", M(events="event E(); event E();"))
    add("dup-state", M(states="state x: Int32 = 0; state x: Int32 = 1;"))
    add("dup-rule", M(events="event E();", rules="rule R on E { } rule R on E { }"))
    add("event-change", M(events="event change();"))
    add("param-dup", M(events="event E(a: Int32, a: Int32);"))
    add("param-state-collision", M(states="state a: Int32 = 0;", events="event E(a: Int32);"))
    add("init-forward-ref", M(states="state a: Int32 = b; state b: Int32 = 0;"))
    add("init-self-ref", M(states="state a: Int32 = a;"))
    add("init-back-ref", M(states="state a: Int32 = 1; state b: Int32 = a + 1;"))
    add("init-mismatch", M(states="state a: Bool = 1;"))
    add("req-dup-same-kind", M(problem="Invariants { A: true; A: true; }"))
    add("req-dup-diff-kind", M(problem="Invariants { A: true; } Goals { A: true; }"))
    add("req-unknown-event", M(problem="Assumptions { A on Nope: true; }"))
    add("invariant-with-on", M(problem="Invariants { A on E: true; }", events="event E();"))
    add("goal-with-on", M(problem="Goals { A on E: true; }", events="event E();"))
    add("hazard-no-on", M(problem="Hazards { H to f: true; }", states="state f: Bool = false;"))
    add("alert-no-on", M(problem="Alerts { A: true; }"))
    add("alert-with-to", M(problem="Alerts { A on E to f: true; }", states="state f: Bool = false;", events="event E();"))
    add("assumption-with-to", M(problem="Assumptions { A on E to f: true; }", states="state f: Bool = false;", events="event E();"))
    add("hazard-no-target", M(problem="Hazards { H on E: true; }", events="event E();"))
    add("hazard-target-undeclared", M(problem="Hazards { H on E to g: true; }", events="event E();"))
    add("hazard-target-nonbool", M(problem="Hazards { H on E to g: true; }", states="state g: Int32 = 0;", events="event E();"))
    add("req-not-bool", M(problem="Invariants { A: 1 + 1; }"))
    add("req-unknown-literal", M(problem="Invariants { A: Unknown; }"))
    add("req-unknown-name", M(problem="Invariants { A: zz == 1; }"))
    add("req-keyword-name", M(problem="Invariants { A: Problem == 1; }"))
    add("req-gcd-name", M(problem="Invariants { A: gcd == 1; }"))
    add("req-param-out-of-scope", M(problem="Invariants { A: p == 1; }", events="event E(p: Int32);"))
    add("req-param-in-scope", M(problem="Alerts { A on E: p == 1; }", events="event E(p: Int32);"))
    add("rule-unknown-event", M(rules="rule R on Nope { }"))
    add("rule-reject-ok", M(events="event E();", rules="rule R on reject E { }"))
    add("rule-change-reject", M(states="state x: Int32 = 0;", rules="rule R on reject change(x) { }"))
    add("rule-change-unknown-state", M(rules="rule R on change(nope) { }"))
    add("rule-change-dup-watch", M(states="state x: Int32 = 0;", rules="rule R on change(x, x) { set x := 1; }"))
    add("rule-change-order", M(states="state x: Int32 = 0; state y: Int32 = 0;",
                              rules="rule R on change(x, y) { } rule S on change(y, x) { }"))
    add("rule-change-ctx-param", M(states="state x: Int32 = 0;", rules="rule R on change(x) when p == 1 { }"))
    add("rule-guard-nonbool", M(events="event E();", rules="rule R on E when 1 { }"))
    add("rule-guard-unknown", M(events="event E();", rules="rule R on E when Unknown { }"))
    add("rule-write-undeclared", M(events="event E();", rules="rule R on E { set q := 1; }"))
    add("rule-write-mismatch", M(states="state x: Int32 = 0;", events="event E();", rules="rule R on E { set x := true; }"))
    add("rule-write-range", M(states="state x: Int32 = 0;", events="event E();", rules="rule R on E { set x := 2147483648; }"))
    add("rule-write-multi", M(states="state x: Int32 = 0;", events="event E();", rules="rule R on E { set x := 1; set x := 2; }"))
    add("rule-write-param", M(states="state x: Int32 = 0;", events="event E(p: Int32);", rules="rule R on E { set x := p; }"))
    add("rule-write-param-u32", M(states="state x: Int32 = 0;", events="event E(p: U32);", rules="rule R on E { set x := p; }"))
    haz_p = "Hazards { H on E to t: p > 10; }"
    haz_s = "state t: Bool = false;"
    add("covers-ok", M(problem=haz_p, states=haz_s, events="event E(p: Int32);",
                       rules="rule R on reject E when p > 10 covers H { set t := true; }"))
    add("covers-not-reject-ok", M(problem=haz_p, states=haz_s, events="event E(p: Int32);",
                                  rules="rule R on E when p > 10 covers H { set t := true; }"))
    add("covers-swapped-guard", M(problem=haz_p, states=haz_s, events="event E(p: Int32);",
                                  rules="rule R on reject E when 10 < p covers H { set t := true; }"))
    add("covers-parens", M(problem=haz_p, states=haz_s, events="event E(p: Int32);",
                           rules="rule R on reject E when (p > 10) covers H { set t := true; }"))
    add("covers-number-forms", M(problem="Hazards { H on E to t: p == 1; }", states=haz_s + " ",
                                 events="event E(p: Pin);",
                                 rules="rule R on reject E when p == 1.0 covers H { set t := true; }"))
    add("covers-bool-vs-int", M(problem="Hazards { H on E to t: p == 1; }", states=haz_s,
                                events="event E(p: Pin);",
                                rules="rule R on reject E when p == true covers H { set t := true; }"))
    add("covers-wrong-event", M(problem=haz_p, states=haz_s, events="event E(p: Int32); event F(p: Int32);",
                                rules="rule R on reject F when p > 10 covers H { set t := true; }"))
    add("covers-unknown", M(problem=haz_p, states=haz_s, events="event E(p: Int32);",
                            rules="rule R on reject E when p > 10 covers Z { set t := true; }"))
    add("covers-no-true-write", M(problem=haz_p, states=haz_s, events="event E(p: Int32);",
                                  rules="rule R on reject E when p > 10 covers H { set t := false; }"))
    add("covers-write-int-literal", M(problem="Hazards { H on E to t: p > 10; }", states="state t: Bool = false;",
                                      events="event E(p: Int32);",
                                      rules="rule R on reject E when p > 10 covers H { set t := not false; }"))
    add("covers-change-rule", M(problem=haz_p, states=haz_s + " state w: Int32 = 0;", events="event E(p: Int32);",
                                rules="rule R on change(w) when p > 10 covers H { set t := true; }"))
    add("hazard-uncovered", M(problem=haz_p, states=haz_s, events="event E(p: Int32);"))
    add("hazards-uncovered-sorted", M(problem="Hazards { Zed on E to t: true; Alpha on E to t: true; Mid on E to t: true; }",
                                      states=haz_s, events="event E();"))
    add("assert-unknown-event", M(proof="assert A on Nope expect true;"))
    add("assert-guard-nonbool", M(events="event E();", proof="assert A on E when 1 expect true;"))
    add("assert-expect-nonbool", M(events="event E();", proof="assert A on E expect 1;"))
    add("assert-param-scope", M(events="event E(p: Int32);", proof="assert A on E when p == 1 expect p == 1;"))
    add("assert-block", M(events="event E();", proof="assert A on E { expect true; }"))
    add("assert-block-when", M(events="event E();", proof="assert A on E { when true expect true; }"))
    add("assert-unclosed-block", M(events="event E();", proof="assert A on E { expect true;"))
    add("step-unknown-event", M(proof="scenario S { step Nope(); }"))
    add("step-missing-arg", M(events="event E(p: Int32);", proof="scenario S { step E(); }"))
    add("step-extra-arg", M(events="event E();", proof="scenario S { step E(q: 1); }"))
    add("step-wrong-type", M(events="event E(p: Int32);", proof="scenario S { step E(p: true); }"))
    add("step-dup-arg", M(events="event E(p: Int32);", states="state x: Int32 = 0;",
                          rules="rule R on E { set x := p; }",
                          proof="scenario S { step E(p: 1, p: 2); expect x == 2; }"))
    add("step-dup-arg-bad", M(events="event E(p: Int32);", proof="scenario S { step E(p: true, p: 1); }"))
    add("step-eq-style", M(events="event E(p: Int32);", states="state x: Int32 = 0;",
                           rules="rule R on E { set x := p; }", proof="scenario S { step E(p = 3); expect x == 3; }"))
    add("step-arg-uses-state", M(events="event E(p: Int32);", states="state x: Int32 = 4;",
                                 rules="rule R on E { set x := p; }",
                                 proof="scenario S { step E(p: x + 1); expect x == 5; }"))
    add("step-arg-uses-param", M(events="event E(p: Int32);", proof="scenario S { step E(p: p); }"))
    add("step-unknown", M(events="event E(p: Int32);", states="state x: Int32 = 0;",
                          rules="rule R on E { set x := p; }",
                          proof="scenario S { step E(p: Unknown); expect x == 0; }"))
    add("expect-nonbool", M(proof="scenario S { expect 1; }"))
    add("expect-unknown", M(proof="scenario S { expect Unknown; }"))
    add("expect-param", M(events="event E(p: Int32);", proof="scenario S { expect p == 1; }"))
    add("empty-proof", M(proof=""))
    add("empty-proof-block", "Problem M { }\nSolution M { }\nProof M { }")
    add("empty-scenario", "Problem M { }\nSolution M { }\nProof M { scenario S { } }")
    add("vacuous-assert", M(events="event E();", proof="assert A on E when false expect true;\n scenario S { step E(); }"))
    add("assert-never-stepped", M(events="event E(); event F();", proof="assert A on E expect true;\n scenario S { step F(); }"))
    add("scenario-only-expect", M(states="state x: Int32 = 0;", proof="scenario S { expect x == 0; expect x == 1; }"))
    add("name-mismatch-solution", "Problem A { }\nSolution B { }")
    add("name-mismatch-proof", "Problem A { }\nSolution A { }\nProof B { }")
    add("trailing-text", "Problem A { }\nSolution A { }\nProof A { }\nextra")
    add("trailing-solution", "Problem A { }\nSolution A { }\nextra")
    add("dup-section", "Problem A { Invariants { } Invariants { } }\nSolution A { }")
    add("unknown-section", "Problem A { Rules { } }\nSolution A { }")
    add("section-not-id", "Problem A { 1 }\nSolution A { }")
    add("section-eof", "Problem A {")
    add("keyword-as-name", "Problem rule { }\nSolution rule { }")
    add("keyword-as-state", M(states="state set: Int32 = 0;"))
    add("module-keyword", "module A { }")
    add("import-line", "import X;\nProblem A { }\nSolution A { }")
    add("unknown-type", M(states="state x: Int64 = 0;"))
    add("void-type", M(states="state x: Void = 0;"))
    add("float-bad-unit", M(states="state x: Float<kg> = 0;"))
    add("float-no-unit", M(states="state x: Float = 0;"))
    add("float-reserved-unit", M(states="state x: Float<on> = 0;"))
    add("pin-params", M(states="state x: Pin<a, b, c> = 0;"))
    add("pin-empty-params", M(states="state x: Pin<> = 0;"))
    add("pin-unclosed", M(states="state x: Pin<a = 0;"))
    add("pin-compat-same", M(states="state x: Pin<a> = 0; state y: Pin<a> = 0;", problem="Invariants { I: x == y; }"))
    add("pin-compat-diff", M(states="state x: Pin<a> = 0; state y: Pin<b> = 0;", problem="Invariants { I: x == y; }"))
    add("pin-vs-plain", M(states="state x: Pin<a> = 0; state y: Pin = 0;", problem="Invariants { I: x == y; }"))
    add("pin-vs-bool", M(states="state x: Pin = 0; state y: Bool = true;", problem="Invariants { I: x == y; }"))
    add("pin-vs-int", M(states="state x: Pin = 0; state y: Int32 = 0;", problem="Invariants { I: x == y; }"))
    add("pin-lt", M(states="state x: Pin = 0;", problem="Invariants { I: x < 1; }"))
    add("pin-arith", M(states="state x: Pin = 0;", problem="Invariants { I: x + 1 == 1; }"))
    add("not-numeric", M(states="state x: Int32 = 0;", problem="Invariants { I: not x; }"))
    add("not-eq-precedence", M(states="state x: Int32 = 0;", problem="Invariants { I: not x == 1; }"))
    add("not-eq-parens", M(states="state x: Int32 = 0;", problem="Invariants { I: not (x == 1); }"))
    add("chain-compare", M(states="state x: Int32 = 0;", problem="Invariants { I: 1 < x < 3; }"))
    add("neg-bool", M(states="state b: Bool = true;", problem="Invariants { I: -b == 1; }"))
    add("and-numeric", M(states="state x: Int32 = 0;", problem="Invariants { I: x and true; }"))
    add("or-unknown", M(problem="Invariants { I: Unknown or true; }"))
    add("int-plus-float", M(states="state x: Int32 = 0; state f: Float<V> = 0;", problem="Invariants { I: x + f == 0; }"))
    add("float-plus-lit", M(states="state f: Float<V> = 0;", problem="Invariants { I: f + 1 == 1; }"))
    add("float-v-plus-a", M(states="state f: Float<V> = 0; state g: Float<A> = 0;", problem="Invariants { I: f + g == 0; }"))
    add("float-v-times-a", M(states="state f: Float<V> = 1; state g: Float<A> = 1; state w: Float<W> = 1;",
                             problem="Invariants { I: f * g == w; }"))
    add("float-w-times-s", M(states="state f: Float<W> = 1; state g: Float<s> = 1; state w: Float<J> = 1;",
                             problem="Invariants { I: f * g == w; }"))
    add("float-v-times-v", M(states="state f: Float<V> = 1; state g: Float<V> = 1;", problem="Invariants { I: f * g == f; }"))
    add("float-div-same", M(states="state f: Float<V> = 1; state g: Float<V> = 1;", problem="Invariants { I: f / g == 1; }"))
    add("float-div-diff", M(states="state f: Float<V> = 1; state g: Float<A> = 1;", problem="Invariants { I: f / g == 1; }"))
    add("int-div-int", M(states="state a: Int32 = 1; state b: Int32 = 1;", problem="Invariants { I: a / b == 1; }"))
    add("int-div-lit", M(states="state a: Int32 = 4;", problem="Invariants { I: a / 2 == 2; }"))
    add("lit-div-lit", M(problem="Invariants { I: 4 / 2 == 2; }"))
    add("degc-plus", M(states="state t: Float<degC> = 1;", problem="Invariants { I: t + 1 == 1; }"))
    add("degc-neg", M(states="state t: Float<degC> = 1;", problem="Invariants { I: -t == 1; }"))
    add("degc-div", M(states="state t: Float<degC> = 1;", problem="Invariants { I: t / 2 == 1; }"))
    add("degc-cmp", M(states="state t: Float<degC> = 1;", problem="Invariants { I: t < 100; }"))
    add("gcd-ok", M(states="state a: U64 = 12; state b: U64 = 18;", problem="Invariants { I: gcd(a, b) == 6; }"))
    add("gcd-int32", M(states="state a: Int32 = 12; state b: U64 = 18;", problem="Invariants { I: gcd(a, b) == 6; }"))
    add("gcd-literal-neg", M(problem="Invariants { I: gcd(-1, 2) == 1; }"))
    add("gcd-not-call", M(problem="Invariants { I: gcd + 1 == 1; }"))
    add("gcd-arity", M(problem="Invariants { I: gcd(1) == 1; }"))
    add("gcd-arity3", M(problem="Invariants { I: gcd(1, 2, 3) == 1; }"))
    add("gcd-bool", M(states="state b: Bool = true;", problem="Invariants { I: gcd(b, 2) == 1; }"))
    add("gcd-float", M(states="state f: Float<V> = 1;", problem="Invariants { I: gcd(f, 2) == 1; }"))
    add("unit-lit-compare", M(states="state f: Float<V> = 1;", problem="Invariants { I: f == 1; }"))
    add("unit-compare-diff", M(states="state f: Float<V> = 1; state g: Float<A> = 1;", problem="Invariants { I: f == g; }"))
    add("int-compare-range", M(states="state x: Int32 = 0;", problem="Invariants { I: x == 4294967296; }"))
    add("u32-compare-neg", M(states="state x: U32 = 0;", problem="Invariants { I: x == -1; }"))
    add("u32-add-neg", M(states="state x: U32 = 0;", problem="Invariants { I: x + -1 == 0; }"))
    add("int32-add-float-lit", M(states="state x: Int32 = 0;", problem="Invariants { I: x + 1.5 == 0; }"))
    add("int32-add-float-int-lit", M(states="state x: Int32 = 0;", problem="Invariants { I: x + 2.0 == 2; }"))
    add("int32-plus-u32", M(states="state x: Int32 = 0; state y: U32 = 0;", problem="Invariants { I: x + y == 0; }"))
    add("int32-mul-float", M(states="state x: Int32 = 2; state f: Float<V> = 1;", problem="Invariants { I: x * f == f; }"))
    add("number-mul-float", M(states="state f: Float<V> = 1;", problem="Invariants { I: 2 * f == f; }"))
    add("float-mul-number", M(states="state f: Float<V> = 1;", problem="Invariants { I: f * 2 == f; }"))
    add("float-div-number", M(states="state f: Float<V> = 1;", problem="Invariants { I: f / 2 == f; }"))
    add("number-div-float", M(states="state f: Float<V> = 1;", problem="Invariants { I: 2 / f == f; }"))
    add("bool-eq-bool", M(states="state a: Bool = true; state b: Bool = false;", problem="Invariants { I: a == b; }"))
    add("bool-lt-bool", M(states="state a: Bool = true; state b: Bool = false;", problem="Invariants { I: a < b; }"))
    add("bool-eq-num", M(states="state a: Bool = true;", problem="Invariants { I: a == 1; }"))
    add("unknown-lt", M(states="state a: Int32 = 1;", problem="Invariants { I: a < Unknown; }"))
    add("unknown-eq-unknown", M(problem="Invariants { I: Unknown == Unknown; }"))
    add("phase-alias-not", M(states="state a: Bool = true;", problem="Invariants { I: • a; }"))
    add("phase-alias-star", M(states="state a: Bool = true;", problem="Invariants { I: (*) a; }"))
    add("phase-alias-nested", M(states="state a: Bool = true;", problem="Invariants { I: (*)(*)a; }"))
    add("phase-alias-binary", M(states="state a: Bool = true;", problem="Invariants { I: a • a; }"))
    add("arrow-alias", M(states="state a: Bool = true;", problem="Invariants { I: a -> a; }"))
    add("left-arrow", M(states="state a: Int32 = 0;", problem="Invariants { I: a<-1 == 0; }"))
    add("unary-mul", M(states="state a: Int32 = 2; state b: Int32 = 3;", problem="Invariants { I: -a * b == -(a * b); J: - a - b < 0; }"))
    add("not-eq-mix", M(states="state a: Bool = true; state b: Bool = true;", problem="Invariants { I: not a == not b; J: not a and b or a; }"))
    add("neg-compare-space", M(states="state a: Int32 = 0;", problem="Invariants { I: a < -1; }"))
    add("deep-parens", M(problem="Invariants { I: " + "(" * 200 + "true" + ")" * 200 + "; }"))
    add("deep-neg", M(states="state a: Int32 = 0;", problem="Invariants { I: " + "-" * 100 + "a == 0; }"))
    add("long-chain", M(states="state a: Int32 = 0;", problem="Invariants { I: " + " + ".join(["a"] * 150) + " == 0; }"))
    add("many-and", M(problem="Invariants { I: " + " and ".join(["true"] * 120) + "; }"))
    add("comments", "# header\nProblem /* x */ M // y\n{ }\nSolution M { /* a\n b */ }\n/* tail */")
    add("crlf", "Problem M {\r\n}\r\nSolution M {\r\n}\r\n")
    add("tabs", "Problem\tM\t{\t}\nSolution\tM\t{\t}")
    add("unicode-ident", M(states="state змінна: Int32 = 0;", problem="Invariants { I: змінна >= 0; }"))
    add("unicode-digit-lit", M(states="state x: Int32 = ٣;"))
    add("unicode-digit-dec", M(states="state x: Float<V> = ٣.٥;"))
    add("superscript-lit", M(states="state x: Int32 = ²;"))
    add("superscript-dec", M(states="state x: Float<V> = ².5;"))
    add("circled-lit", M(states="state x: Int32 = ①;"))
    add("huge-int", M(states="state x: U64 = " + "9" * 30 + ";"))
    add("leading-zeros", M(states="state x: Int32 = 007; state y: Float<V> = 007.50;"))
    add("event-no-params-trailing-comma", M(events="event E(a: Int32,);"))
    add("event-missing-semicolon", M(events="event E()"))
    add("event-missing-type", M(events="event E(a);"))
    add("state-missing-init", M(states="state a: Int32;"))
    add("state-colon-eq", M(states="state a: Int32 := 0;"))
    add("rule-no-on", M(rules="rule R E { }"))
    add("rule-set-colon", M(states="state a: Int32 = 0;", events="event E();", rules="rule R on E { set a = 1; }"))
    add("rule-covers-before-when", M(problem="Hazards { H on E to t: true; }", states="state t: Bool = false;",
                                     events="event E();", rules="rule R on reject E covers H when true { set t := true; }"))
    add("rule-when-twice", M(events="event E();", rules="rule R on E when true when true { }"))
    add("rule-reject-order", M(events="event E();", rules="rule R on E reject { }"))
    add("req-to-before-on", M(problem="Hazards { H to t on E: true; }", states="state t: Bool = false;", events="event E();"))
    add("req-missing-colon", M(problem="Invariants { I true; }"))
    add("req-missing-semi", M(problem="Invariants { I: true }"))
    add("req-empty-section", M(problem="Invariants { } Alerts { } Goals { } Assumptions { } Hazards { }"))
    add("all-sections", M(problem="Assumptions { A: true; } Invariants { I: true; } Hazards { } Alerts { } Goals { G: true; }"))
    add("scenario-bad-item", M(proof="scenario S { set x := 1; }"))
    add("proof-bad-item", M(proof="rule R on E { }"))
    add("step-bad-sep", M(events="event E(p: Int32);", proof="scenario S { step E(p 1); }"))
    add("step-missing-comma", M(events="event E(a: Int32, b: Int32);", proof="scenario S { step E(a: 1 b: 2); }"))
    add("step-trailing-comma", M(events="event E(a: Int32);", proof="scenario S { step E(a: 1,); }"))
    add("expression-missing", M(problem="Invariants { I: ; }"))
    add("expression-eof", "Problem M { Invariants { I: ")
    add("paren-unclosed", M(problem="Invariants { I: (true; }"))
    add("gcd-no-paren", M(problem="Invariants { I: gcd == 1; }"))
    add("gcd-missing-comma", M(problem="Invariants { I: gcd(1 2) == 1; }"))
    add("true-call", M(problem="Invariants { I: true(); }"))
    return cases


def dyn_cases() -> list[tuple[str, str, list]]:
    """(id, source, scripts) with explicit event scripts."""
    out: list = []

    def add(cid, src, scripts):
        out.append((f"dyn:{cid}", src, scripts))

    def S(*batches, **opts):
        return {"opts": opts, "batches": [list(b) for b in batches]}

    def E(name, **payload):
        return {"name": name, "payload": payload}

    U = kr.UNKNOWN
    add("short-circuit", M(states="state x: Int32 = 0; state ok: Bool = false;",
                           events="event E(d: Int32);",
                           rules="rule R on E when d != 0 and x / 0 > 1 { set ok := true; }\n"
                                 "rule S on E when d == 0 or x / 0 > 100 { set x := 1; }"),
        [S([E("E", d=0)]), S([E("E", d=2)]), S([E("E", d=U)]), S([E("E", d=1)])])
    add("division-error", M(states="state x: Int32 = 0;", events="event E(d: Int32);",
                            rules="rule R on E when d > 0 and 10 / 0 > 1 { set x := 1; }"),
        [S([E("E", d=0)]), S([E("E", d=5)])])
    add("float-division-store", M(states="state x: Int32 = 0; state f: Float<V> = 0;",
                                  events="event E(a: Int32);",
                                  rules="rule R1 on E when a == 1 { set f := 1 / 3; }\n"
                                        "rule R2 on E when a == 2 { set f := 7 / 2; }\n"
                                        "rule R3 on E when a == 3 { set x := a / 3; }\n"
                                        "rule R4 on E when a == 4 { set f := 0 / -5; }\n"
                                        "rule R5 on E when a == 5 { set f := 10000000000000000 / 3; }\n"
                                        "rule R6 on E when a == 6 { set f := 1 / 0; }\n"
                                        "rule R7 on E when a == 7 { set f := 1 / 7 * 7; }\n"
                                        "rule R8 on E when a == 8 { set x := a / 2; }"),
        [S([E("E", a=k)]) for k in range(0, 10)])
    add("decimal-arith", M(states="state f: Float<V> = 1.0; state g: Float<A> = 3; state w: Float<W> = 0;",
                           events="event E(k: Float<V>);",
                           rules="rule R on E { set f := f + k; set w := f * g; }\n"
                                 "rule S on E when k > 0.5 { set g := g / 3; }"),
        [S([E("E", k=Decimal("0.1"))] * 3), S([E("E", k=Decimal("1E+2"))]), S([E("E", k=3)]),
         S([E("E", k=2.5)]), S([E("E", k=True)]), S([E("E", k=U)]), S([E("E", k=Decimal("0.5"))] * 5)])
    add("decimal-precision", M(states="state f: Float<V> = 1; state h: Float<V> = 0;",
                               events="event E();",
                               rules="rule R on E { set f := f / 3; set h := f * 3 + h; }"),
        [S([E("E")] * 6)])
    add("conflicting-writes", M(states="state x: Int32 = 0; state y: Int32 = 0;", events="event E(p: Int32);",
                                rules="rule A on E { set x := 1; set y := p; }\n"
                                      "rule B on E when p > 0 { set x := 2; }"),
        [S([E("E", p=0)]), S([E("E", p=5)])])
    add("conflicting-writes-equal", M(states="state x: Int32 = 0;", events="event E();",
                                      rules="rule A on E { set x := 1; }\nrule B on E { set x := 1; }"),
        [S([E("E")])])
    add("conflicting-decimal-repr", M(states="state f: Float<V> = 0;", events="event E();",
                                      rules="rule A on E { set f := 1.0; }\nrule B on E { set f := 1.00; }"),
        [S([E("E")])])
    add("same-rule-conflict", M(states="state x: Int32 = 0;", events="event E();",
                                rules="rule A on E { set x := 1; set x := 2; }"),
        [S([E("E")])])
    add("invariant-violation", M(problem="Invariants { Cap: x <= 3; }", states="state x: Int32 = 0;",
                                 events="event E();", rules="rule R on E { set x := x + 2; }"),
        [S([E("E")] * 3)])
    add("simultaneous-writes", M(states="state a: Int32 = 1; state b: Int32 = 2;", events="event Swap();",
                                 rules="rule R on Swap { set a := b; set b := a; }"),
        [S([E("Swap")] * 3)])
    add("int32-overflow", M(states="state x: Int32 = 2147483646;", events="event E();",
                            rules="rule R on E { set x := x + 1; }"),
        [S([E("E")]), S([E("E")])])
    add("u32-underflow", M(states="state x: U32 = 1;", events="event E();", rules="rule R on E { set x := x - 1; }"),
        [S([E("E")]), S([E("E")])])
    add("u64-mul", M(states="state x: U64 = 4294967296;", events="event E();", rules="rule R on E { set x := x * x; }"),
        [S([E("E")])])
    add("pin-writes", M(states="state p: Pin = 0; state n: Int32 = 0;", events="event E(v: Int32);",
                        rules="rule R on E { set p := v; }\nrule S on E when v == 5 { set n := 1; }"),
        [S([E("E", v=1)]), S([E("E", v=0)]), S([E("E", v=2)]), S([E("E", v=-1)])])
    add("pin-bool-write", M(states="state p: Pin = 0;", events="event E(b: Bool);",
                            rules="rule R on E { set p := b; }"),
        [S([E("E", b=True)]), S([E("E", b=False)]), S([E("E", b=U)])])
    add("pin-payload", M(states="state p: Pin = 0;", events="event E(q: Pin);",
                         rules="rule R on E { set p := q; }"),
        [S([E("E", q=True)]), S([E("E", q=1)]), S([E("E", q=2)]), S([E("E", q=Decimal("1"))])])
    add("unknown-guard", M(states="state x: Int32 = 0;", events="event E(p: Int32);",
                           rules="rule R on E when p > 0 { set x := 1; }"),
        [S([E("E", p=U)]), S([E("E", p=1)])])
    add("unknown-write", M(states="state x: Int32 = 0;", events="event E(p: Int32);",
                           rules="rule R on E { set x := p; }"),
        [S([E("E", p=U)]), S([E("E", p=4)])])
    add("unknown-eq", M(states="state ok: Bool = false;", events="event E(p: Int32, q: Int32);",
                        rules="rule R on E when p == q { set ok := true; }\nrule S on E when p != q { set ok := false; }"),
        [S([E("E", p=U, q=U)]), S([E("E", p=U, q=1)]), S([E("E", p=1, q=1)])])
    add("unknown-kleene", M(states="state a: Bool = false; state b: Bool = false; state c: Bool = false;",
                            events="event E(p: Bool, q: Bool);",
                            rules="rule A on E when p and q { set a := true; }\n"
                                  "rule B on E when p or q { set b := true; }\n"
                                  "rule C on E when not p { set c := true; }"),
        [S([E("E", p=U, q=False)]), S([E("E", p=U, q=True)]), S([E("E", p=False, q=U)]),
         S([E("E", p=True, q=U)]), S([E("E", p=U, q=U)])])
    add("gcd-runtime", M(states="state g: U64 = 0;", events="event E(a: U64, b: U64);",
                         rules="rule R on E { set g := gcd(a, b); }"),
        [S([E("E", a=12, b=18)]), S([E("E", a=0, b=0)]), S([E("E", a=U, b=3)]), S([E("E", a=2**63, b=2**62)])])
    add("assumption-reject", M(problem="Assumptions { Range on E: p >= 0; }", states="state x: Int32 = 0; state bad: Bool = false;",
                               events="event E(p: Int32);",
                               rules="rule Ok on E { set x := p; }\nrule Rej on reject E { set bad := true; }"),
        [S([E("E", p=5)]), S([E("E", p=-1)]), S([E("E", p=U)])])
    add("assumption-two", M(problem="Assumptions { A1 on E: p >= 0; A2 on E: x / 0 > 0; }",
                            states="state x: Int32 = 0;", events="event E(p: Int32);",
                            rules="rule Ok on E { set x := p; }"),
        [S([E("E", p=-1)]), S([E("E", p=0)]), S([E("E", p=2)])])
    haz = M(problem="Hazards { Over on E to trip: p > 10; } Alerts { Warn on E: p > 5; Maybe on E: q > 0; } Invariants { I: x >= 0; }",
            states="state trip: Bool = false; state x: Int32 = 0;",
            events="event E(p: Int32, q: Int32); event F(p: Int32);",
            rules="rule Cover on reject E when p > 10 covers Over { set trip := true; }\n"
                  "rule Go on E { set x := x + 1; }\n"
                  "rule Rej on reject E { set x := x + 100; }\n"
                  "rule GoF on F { set x := p; }")
    add("hazard-alert", haz,
        [S([E("E", p=1, q=1)]), S([E("E", p=7, q=1)]), S([E("E", p=11, q=1)]), S([E("E", p=11, q=U)]),
         S([E("E", p=U, q=1)]), S([E("E", p=U, q=U)]), S([E("E", p=11, q=1), E("F", p=-5)]),
         S([E("E", p=11, q=1), E("E", p=1, q=1), E("F", p=-5)]), S([E("F", p=-5), E("E", p=11, q=1)]),
         S([E("E", p=11, q=1)], fail_closed=False), S([E("E", p=U, q=1)], fail_closed=False)])
    add("hazard-latch-d-k4", M(problem="Hazards { H on A to t: p > 10; } Assumptions { Pos on B: q > 0; }",
                               states="state t: Bool = false; state s: Int32 = 0;",
                               events="event A(p: Int32); event B(q: Int32);",
                               rules="rule HA on reject A when p > 10 covers H { set t := true; }\n"
                                     "rule OkB on B { set s := q; }\nrule RejB on reject B { set s := 0 - 1; }"),
        [S([E("A", p=11), E("B", q=-1)]), S([E("A", p=11)], [E("B", q=-1)])])
    add("hazard-latch-skip-explicit", M(problem="Hazards { H on A to t: p > 10; }",
                                        states="state t: Bool = false;", events="event A(p: Int32);",
                                        rules="rule HA on A when p > 10 covers H { set t := true; }\n"
                                              "rule Clr on reject A { set t := false; }"),
        [S([E("A", p=11)]), S([E("A", p=3)])])
    add("hazard-no-latch-write", M(problem="Hazards { H on A to t: p > 10; }",
                                   states="state t: Bool = false;",
                                   events="event A(p: Int32);",
                                   rules="rule HA on reject A when p > 10 covers H { set t := true; }"),
        [S([E("A", p=11)]), S([E("A", p=3)])])
    add("hazard-unknown-fail-open", M(problem="Hazards { H on A to t: p > 10; }",
                                      states="state t: Bool = false; state s: Int32 = 0;",
                                      events="event A(p: Int32);",
                                      rules="rule HA on reject A when p > 10 covers H { set t := true; }\n"
                                            "rule Go on A { set s := 1; }"),
        [S([E("A", p=U)]), S([E("A", p=U)], fail_closed=False), S([E("A", p=50)], fail_closed=False)])
    add("alert-phase-a-d-k7", M(problem="Assumptions { P on E: p > 0; } Alerts { Al on E: q > 0; }",
                                states="state s: Int32 = 0;", events="event E(p: Int32, q: Int32);",
                                rules="rule R on E { set s := p; }"),
        [S([E("E", p=0, q=U)]), S([E("E", p=1, q=U)]), S([E("E", p=0, q=1)])])
    add("cascade", M(problem="Invariants { I: a >= 0; }",
                     states="state a: Int32 = 0; state b: Int32 = 0; state c: Int32 = 0;",
                     events="event Inc();",
                     rules="rule R0 on Inc { set a := a + 1; }\n"
                           "rule R1 on change(a) { set b := a * 2; }\n"
                           "rule R2 on change(b) { set c := b + 1; }\n"
                           "rule R3 on change(a, b) when c > 100 { set a := 0; }"),
        [S([E("Inc")] * 3), S([E("Inc")], [E("Inc")])])
    add("cascade-initial", M(states="state a: Int32 = 1; state b: Int32 = 0;", events="event E();",
                             rules="rule R1 on change(a) { set b := a + 10; }"),
        [S([]), S([], [E("E")]), S([E("E")])])
    add("cascade-order", M(states="state a: Int32 = 0; state b: Int32 = 0; state log: Int32 = 0;", events="event E();",
                           rules="rule T on E { set a := 1; set b := 1; }\n"
                                 "rule WAB on change(a, b) { set log := log * 10 + 1; }\n"
                                 "rule WBA on change(b, a) { set log := log * 10 + 2; }\n"
                                 "rule WAB2 on change(a, b) { set log := log * 10 + 3; }\n"
                                 "rule WA on change(a) { set log := log + 100; }"),
        [S([E("E")])])
    add("cascade-no-change", M(states="state a: Int32 = 0; state n: Int32 = 0;", events="event E();",
                               rules="rule T on E { set a := 0; }\nrule W on change(a) { set n := n + 1; }"),
        [S([E("E")] * 2)])
    add("cascade-dup-watch", M(states="state a: Int32 = 0; state n: Int32 = 0;", events="event E();",
                               rules="rule T on E { set a := a + 1; }\nrule W on change(a, a) { set n := n + 1; }\n"
                                     "rule X on change(a, a) { set n := n + 1; }"),
        [S([E("E")])])
    add("cascade-loop", M(states="state a: Int32 = 0; state b: Int32 = 0;", events="event E();",
                          rules="rule T on E { set a := a + 1; }\nrule A on change(a) { set b := b + 1; }\n"
                                "rule B on change(b) { set a := a + 1; }"),
        [S([E("E")], max_events=50), S([E("E")], max_events=5), S([E("E")], max_events=1)])
    add("cascade-toggle", M(states="state a: Bool = false;", events="event E();",
                            rules="rule T on E { set a := true; }\nrule A on change(a) { set a := not a; }"),
        [S([E("E")], max_events=10)])
    add("cascade-invariant-abort", M(problem="Invariants { I: b < 5; }",
                                     states="state a: Int32 = 0; state b: Int32 = 0;", events="event E();",
                                     rules="rule T on E { set a := a + 1; }\nrule W on change(a) { set b := a * 3; }"),
        [S([E("E")] * 3)])
    add("init-assumption-false", M(problem="Assumptions { A: x > 0; }", states="state x: Int32 = 0;"), [S([])])
    add("init-invariant-false", M(problem="Invariants { I: x > 0; }", states="state x: Int32 = 0;"), [S([])])
    add("init-event-assumption-ignored", M(problem="Assumptions { A on E: x > 0; }", states="state x: Int32 = 0;",
                                           events="event E();"), [S([E("E")])])
    add("init-goal-ignored", M(problem="Goals { G: x > 0; }", states="state x: Int32 = 0;"), [S([])])
    add("init-unknown-store", M(states="state x: Int32 = Unknown;"), [S([])])
    add("init-int32-decimal", M(states="state x: Int32 = 2.0;"), [S([])])
    add("init-division", M(states="state x: Int32 = 4 / 2;"), [S([])])
    add("init-divzero", M(states="state x: Int32 = 1 / 0;"), [S([])])
    add("init-override", M(states="state x: Int32 = 0; state y: Int32 = x + 1;"),
        [S([], overrides={"x": 5}), S([], overrides={"y": 9}), S([], overrides={"q": 1}),
         S([], overrides={"x": U}), S([], overrides={"x": 2**31}), S([], overrides={"x": True}),
         S([], overrides={"x": 1, "y": 2})])
    add("init-override-eval-order", M(states="state x: Int32 = 1 / 0;"), [S([], overrides={"x": 5})])
    add("init-override-bad-q-and-r", M(states="state x: Int32 = 0;"), [S([], overrides={"r": 1, "q": 2})])
    add("override-contract", M(problem="Invariants { I: x >= 0; }", states="state x: Int32 = 0;"),
        [S([], overrides={"x": -1})])
    add("goal-failures", M(problem="Goals { G1: x > 0; G2: x > 5; G3: Unknown == Unknown; }", states="state x: Int32 = 0;",
                           events="event E(p: Int32);", rules="rule R on E { set x := p; }"),
        [S([E("E", p=3)]), S([E("E", p=7)]), S([])])
    add("goal-unknown", M(problem="Goals { G1: x < y; }", states="state x: Int32 = 0; state y: Int32 = 1;"), [S([])])
    add("payload-mismatch", M(events="event E(a: Int32, b: Bool);", states="state x: Int32 = 0;",
                              rules="rule R on E { set x := a; }"),
        [S([E("E", a=1)]), S([E("E", a=1, b=True, c=1)]), S([E("E", a=1, b=1)]), S([E("E", a=True, b=True)]),
         S([E("E", a=2**31, b=True)])])
    add("payload-float-kinds", M(events="event E(f: Float<V>);", states="state x: Float<V> = 0;",
                                 rules="rule R on E { set x := f; }"),
        [S([E("E", f=1)]), S([E("E", f=1.5)]), S([E("E", f=1e16)]), S([E("E", f=1e-7)]), S([E("E", f=float("inf"))]),
         S([E("E", f=float("nan"))]), S([E("E", f=Decimal("1E+3"))]), S([E("E", f=Decimal("0.10"))]),
         S([E("E", f=10**5000)]), S([E("E", f=-0.0)])])
    add("steps-count", M(states="state a: Int32 = 0;", events="event E();", rules="rule T on E { set a := a + 1; }"),
        [S([E("E")] * 7)])
    add("rejected-order", M(problem="Assumptions { A on E: p > 0; } Hazards { H1 on E to t: p > 10; H2 on E to t: p > 5; }",
                            states="state t: Bool = false;", events="event E(p: Int32);",
                            rules="rule C1 on reject E when p > 10 covers H1 { set t := true; }\n"
                                  "rule C2 on reject E when p > 5 covers H2 { set t := true; }"),
        [S([E("E", p=11)]), S([E("E", p=6)]), S([E("E", p=0)]), S([E("E", p=U)])])
    add("float-int-mix", M(states="state f: Float<V> = 1.5; state g: Float<V> = 0;", events="event E(i: Int32);",
                           rules="rule R on E { set g := f * 3; }\n"
                                 "rule S on E when i < 0 { set f := f / 2; }\n"
                                 "rule Z on E when i == 0 { set f := f / 0; }"),
        [S([E("E", i=3)]), S([E("E", i=-2)]), S([E("E", i=0)])])
    add("verify-failures", M(problem="Invariants { I: x >= 0; }", states="state x: Int32 = 0; state f: Float<V> = 1.50;",
                             events="event E(p: Int32);", rules="rule R on E when p > 0 { set x := p; set f := f * 2; }",
                             proof="assert Pos on E when p > 0 expect x == p;\n"
                                   "assert Never on E when p > 1000 expect x == 0;\n"
                                   "assert Bad on E when p > 0 expect x == 0;\n"
                                   "scenario S1 { step E(p: 3); expect x == 3; expect x == 4; step E(p: -1); expect f == 3; }\n"
                                   "scenario S2 { step E(p: 2); expect f == 6.00; }"), [])
    add("verify-decimal-repr", M(states="state f: Float<V> = 0.10; state p: Pin = 1; state b: Bool = true;",
                                 events="event E();", rules="rule R on E { set f := f * 3; }",
                                 proof="scenario S { step E(); expect f == 99; }"), [])
    add("verify-vacuous-proof", "Problem M { }\nSolution M { }\nProof M { scenario S { } }", [])
    add("verify-runtime-error", M(states="state f: Float<V> = 1;", events="event E();",
                                  rules="rule R on E { set f := f / 0; }",
                                  proof="scenario S { step E(); expect f == 1; }"), [])
    add("verify-step-eval-error", M(states="state x: Int32 = 0;", events="event E(p: Int32);",
                                    rules="rule R on E { set x := p; }",
                                    proof="scenario S { step E(p: 1 / 0); }"), [])
    add("verify-init-error", M(problem="Invariants { I: x > 0; }", states="state x: Int32 = 0;",
                               proof="scenario S { expect true; }"), [])
    add("verify-float-arg", M(states="state x: Int32 = 0; state y: Pin = 0;", events="event E(p: Int32, q: Pin);",
                              rules="rule R on E { set x := p; set y := q; }",
                              proof="scenario S { step E(p: 4 / 2, q: 1); expect x == 2; }"), [])
    add("verify-raw-payload", M(states="state f: Float<V> = 0; state y: Pin = 0;", events="event E(q: Pin, g: Float<V>);",
                                rules="rule R on E { set y := q; set f := g; }",
                                proof="assert A on E when q == true expect y == 1 and g == 2;\n"
                                      "scenario S { step E(q: true, g: 2); expect f == 2; expect y == 1; }"), [])
    add("verify-cascade", M(states="state a: Int32 = 0; state b: Int32 = 0;", events="event E();",
                            rules="rule T on E { set a := a + 1; }\nrule W on change(a) { set b := a * 2; }",
                            proof="scenario S { expect b == 0; step E(); expect b == 2; step E(); expect b == 4; }"), [])
    add("verify-hazard", M(problem="Hazards { H on E to t: p > 10; }", states="state t: Bool = false; state s: Int32 = 0;",
                           events="event E(p: Int32);",
                           rules="rule C on reject E when p > 10 covers H { set t := true; }\nrule G on E { set s := p; }",
                           proof="assert A on E when p > 10 expect t;\n"
                                 "scenario S { step E(p: 3); expect not t and s == 3; step E(p: 11); expect t and s == 3; }"), [])
    return out


def triad_cases() -> list[dict]:
    cases = []

    def add(cid, p, s, q):
        entry: dict = {"id": cid, "problem": p, "solution": s, "proof": q}
        try:
            m = kr.parse_triad_files(p, s, q)
        except Exception as e:  # noqa: BLE001
            entry["error"] = exc_info(e)
        else:
            entry["ok"] = {"ast": dump_module(m), "problem_hash": m.problem_hash,
                           "solution_hash": m.solution_hash, "proof_hash": m.proof_hash,
                           "proof_present": m.proof_present, "aliases": m.phase_aliases_used}
        cases.append(entry)

    add("sensor", """
        namespace Avionics::Sensors;

        Problem SensorNode {
            Invariants {
                ValidReading: Value >= 0;
            }
        }
        """, """
        namespace Avionics::Sensors;
        import Avionics::Sensors::SensorNode;

        Solution SensorNode {
            event Read(Raw: Int32);
            state Value: Int32 = 0;
            rule on_read on Read when Raw >= 0 {
                set Value := Raw;
            }
        }
        """, """
        namespace Avionics::Sensors;
        import Avionics::Sensors::SensorNode;

        Proof SensorNode {
            scenario S1 {
                step Read(Raw: 10);
                expect Value == 10;
            }
        }
        """)
    p = "Problem P { Invariants { I: X >= 0; } }"
    s = "Solution P { state X: Int32 = 0; }"
    add("empty-proof", p, s, "Proof P {}")
    add("blank-proof", p, s, "")
    add("ws-proof", p, s, " \n\t ")
    add("none-like-problem", "", s, "Proof P { scenario S1 { expect X == 0; } }")
    add("blank-problem", "  \n", s, "Proof P { scenario S1 { expect X == 0; } }")
    add("blank-solution", p, "\u2003", "Proof P { scenario S1 { expect X == 0; } }")
    add("valid", p, s, "Proof P { scenario S1 { expect X == 0; } }")
    add("aliases-dropped", "Problem P { Invariants { I: • (X < 0); } }", s, "Proof P { scenario S1 { expect X == 0; } }")
    add("import-inside", p, "import Foo;\n" + s, "namespace N;\nProof P { scenario S1 { expect X == 0; } }")
    add("import-indented", p, "   import Foo;\r\n" + s, "\timport x;\nProof P { scenario S1 { expect X == 0; } }")
    add("import-no-space", p, "import;\n" + s, "Proof P { scenario S1 { expect X == 0; } }")
    add("line-numbers", "Problem P { Invariants { I: X >= 0; } }\n\n", "Solution P { state X: Int32 = 0; rule }", "Proof P { }")
    add("mismatch", "Problem A { }", "Solution B { }", "Proof A { scenario S { expect true; } }")
    add("static-error", "Problem P { Invariants { I: Y >= 0; } }", s, "Proof P { scenario S1 { expect X == 0; } }")
    add("assert-only", p, "Solution P { state X: Int32 = 0; event E(); }", "Proof P { assert A on E expect true; }")
    add("crlf", p + "\r\n", s + "\r\n", "Proof P {\r\n scenario S1 {\r\n expect X == 0;\r\n }\r\n}\r\n")
    add("form-feed", p, s + "\x0c", "Proof P { scenario S1 { expect X == 0; } }")
    add("unicode-ls", p, s + "\u2028import x;\u2028", "Proof P { scenario S1 { expect X == 0; } }")
    add("proof-with-hash", p, s, "Proof P { scenario S1 { expect X == 0; } } # \u00e9")
    return cases


# --------------------------------------------------------------------------
# Value matrices
# --------------------------------------------------------------------------

EVAL_VALUES = [
    True, False, 0, 1, -1, 5, 7, 2**40, -(2**70), 2**70,
    Decimal("0"), Decimal("-0.0"), Decimal("1.5"), Decimal("2.50"), Decimal("-3"), Decimal("1E+3"),
    Decimal("0.1"), Decimal("12345678901234567890123456789.5"), Decimal("0.0000001"),
    2.5, 0.1, -0.0, 1e16, 1e-7, 1e300, 1e-5, 0.0001, 1e15, 12345678901234567.0, 123456.789, float("inf"), float("nan"), kr.UNKNOWN,
]


def eval_binary(op: str, a, b):
    expr = kr.Binary(op, kr.Name("a"), kr.Name("b"))
    try:
        return "ok", kr._eval(expr, {"a": a, "b": b})
    except Exception as e:  # noqa: BLE001
        return "err", e


def result_text(kind, v) -> str:
    if kind == "ok":
        return enc(v)
    info = exc_info(v)
    return "!" + info["kind"] + ":" + info["text"]


def rand_decimal(rng: random.Random) -> Decimal:
    ndig = rng.choice([1, 1, 2, 3, 5, 10, 20, 27, 28, 29, 30, 40])
    digits = "".join(rng.choice("0123456789") for _ in range(ndig)).lstrip("0") or rng.choice(["0", "0", "5"])
    exp = rng.choice([0, 0, 0, -1, -2, -5, -10, -28, -30, 1, 2, 5, 10, 28, 30, 100, -100, 1000, -1000])
    sign = rng.choice(["", "", "-"])
    return Decimal(f"{sign}{digits}E{exp}") if rng.random() < 0.5 else Decimal(f"{sign}{digits}") * Decimal(1)


def eval_cases(rng: random.Random) -> list:
    rows = []
    ops = ["+", "-", "*", "/", "==", "!=", "<", "<=", ">", ">=", "and", "or"]
    for op in ops:
        for a in EVAL_VALUES:
            for b in EVAL_VALUES:
                kind, v = eval_binary(op, a, b)
                rows.append([op, enc(a), enc(b), result_text(kind, v)])
    edge = [Decimal(x) for x in ("1E+100", "1", "1E-100", "9" * 28, "9" * 28 + "5", "0", "0.00", "-0.00", "5", "1E+50",
                                "1.5E-7", "123456789012345678901234567890", "5E-29", "4.9999999999999999999999999999",
                                "7", "3", "1E+27", "1E+28", "1E-27", "99999999999999999999999999995", "-1E+100",
                                "2.5", "0.5", "1E+999972", "9999999999999999999999999999E+999972", "1E-999999",
                                "1E-1000030", "3E-1000026", "1E+999999")]
    for op in ["+", "-", "*", "/", "<", "=="]:
        for a in edge:
            for b in edge + [7, -3, True, 10**30]:
                if op == "/" and b == 0:
                    continue
                kind, v = eval_binary(op, a, b)
                rows.append([op, enc(a), enc(b), result_text(kind, v)])
    for _ in range(3000):
        op = rng.choice(["+", "-", "*", "/", "==", "<"])
        pool = [rand_decimal, rand_decimal, rand_decimal, lambda r: r.randint(-10**8, 10**8) * rng.choice([1, 10**20]),
                lambda r: r.choice([True, False])]
        a = rng.choice(pool)(rng)
        b = rng.choice(pool)(rng)
        kind, v = eval_binary(op, a, b)
        rows.append([op, enc(a), enc(b), result_text(kind, v)])
    for _ in range(600):
        op = rng.choice(["+", "-", "*", "/"])
        a = rand_decimal(rng)
        b = rand_decimal(rng)
        if op == "/" and b == 0:
            continue
        a = a * rng.choice([Decimal(1), Decimal("9999999999999999999999999999")])
        kind, v = eval_binary(op, a, b)
        rows.append([op, enc(a), enc(b), result_text(kind, v)])
    return rows


def unary_cases() -> list:
    rows = []
    for op in ("not", "-"):
        for v in EVAL_VALUES:
            try:
                r = kr._eval(kr.Unary(op, kr.Name("a")), {"a": v})
                rows.append([op, enc(v), enc(r)])
            except Exception as e:  # noqa: BLE001
                info = exc_info(e)
                rows.append([op, enc(v), "!" + info["kind"] + ":" + info["text"]])
    gcd_vals = [0, 1, -1, 12, 18, -12, 2**64, 2**70, True, False, Decimal("12.9"), Decimal("-12.9"), Decimal("1E+3"),
                2.9, -2.9, 1e20, float("inf"), float("nan"), kr.UNKNOWN]
    for a in gcd_vals:
        for b in gcd_vals:
            try:
                r = kr._eval(kr.Call("gcd", (kr.Name("a"), kr.Name("b"))), {"a": a, "b": b})
                rows.append(["gcd", enc(a), enc(b), enc(r)])
            except Exception as e:  # noqa: BLE001
                info = exc_info(e)
                rows.append(["gcd", enc(a), enc(b), "!" + info["kind"] + ":" + info["text"]])
    return rows


def norm_cases() -> list:
    rows = []
    types = [kr.TypeRef("Bool"), kr.TypeRef("Int32"), kr.TypeRef("U32"), kr.TypeRef("U64"), kr.TypeRef("Float", "V"),
             kr.TypeRef("Pin"), kr.TypeRef("Pin", "a,b"), kr.TypeRef("Weird")]
    vals = EVAL_VALUES + [2**31, 2**31 - 1, -(2**31), -(2**31) - 1, 2**32, 2**32 - 1, 2**64, 2**64 - 1, 10**5000,
                          Decimal("1"), Decimal("0.5")]
    for t in types:
        for v in vals:
            for allow in (False, True):
                try:
                    r = kr._normalize(v, t, allow)
                    out = enc(r)
                except Exception as e:  # noqa: BLE001
                    info = exc_info(e)
                    out = "!" + info["kind"] + ":" + info["text"]
                rows.append([t.name, enc(v), allow, out])
    return rows


def expr_cases() -> list:
    """Expression strings evaluated with a fixed environment (parser + evaluator)."""
    env = {"a": 7, "b": -3, "t": True, "f": False, "u": kr.UNKNOWN, "d": Decimal("2.50"), "z": 0, "x": 2.5}
    exprs = [
        "1 + 2 * 3", "(1 + 2) * 3", "1 - 2 - 3", "2 * 3 / 4", "8 / 4 / 2", "-a", "- -a", "--a", "-a * b", "- a / b", "-d * 2", "- 2 * 3 / 4", "not t == f", "not t and u", "-a - b", "- 2 - 3", "not t", "not f", "not u",
        "not not t", "t and f", "t and u", "f and u", "u and f", "u and t", "u and u", "t or f", "f or u", "u or t", "t or u",
        "u or u", "f or f", "a == 7", "a != 7", "a < b", "a <= 7", "a > b", "a >= 8", "u == u", "u != u", "u == 5", "u != 5",
        "u < 5", "5 > u", "u + 1", "-u", "gcd(12, 18)", "gcd(u, 3)", "gcd(a, b)", "gcd(0, 0)", "1 / 0 == 1", "f and 1 / 0 == 1",
        "t or 1 / 0 == 1", "t and 1 / 0 == 1", "f or 1 / 0 == 1", "a / z", "a / b", "d + 1", "d * d", "d / 3", "d - d",
        "d == 2.5", "d == 2.50", "x + 1", "x * 2", "d + x", "1 / 3", "-0.0", "0 * -1.0", "2.5 * 2", "007 + 1", "1.0 == 1",
        "t == 1", "t + t", "-t", "a < b == f", "a - b * 2", "not a", "not 0", "not d", "not x", "gcd(7.9, 3)", "q", "gcd(1, 2, 3)",
        "gcd", "true", "false", "Unknown", "t and (f or u)", "(u or t) and (u and f)", "a + 0.5", "d / d", "d / 0.00",
        "0.1 + 0.2", "0.1 * 3", "1 / 7 * 7", "100000000000000000000 * 100000000000000000000",
        "9999999999999999999999999999 + 1", "99999999999999999999999999999 + 1.0", "1.000000000000000000000000000001 + 0",
    ]
    rows = []
    for text in exprs:
        try:
            parser = kr.Parser(text)
            e = parser.expression()
            if parser.token.kind != "EOF":
                raise kr.KpolError("trailing")
            r = kr._eval(e, env)
            rows.append([text, "ok:" + enc(r)])
        except Exception as e:  # noqa: BLE001
            info = exc_info(e)
            rows.append([text, "!" + info["kind"] + ":" + info["text"]])
    return rows, {k: enc(v) for k, v in env.items()}


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    rng = random.Random(SEED)
    cases: list[dict] = []
    ids: set[str] = set()

    def push(case: dict) -> None:
        assert case["id"] not in ids, case["id"]
        ids.add(case["id"])
        cases.append(case)

    corpus = collect_corpus()
    for cid, group, src in corpus:
        push(make_case(cid, group, src, rng))

    for i, src in enumerate(LEX_CASES):
        case = make_case(f"lex:{i}", "lex", src, rng, light=True)
        try:
            toks = kr.tokenize(src)
            case["tokens"]["list"] = [[t.kind, t.value, t.line, t.column] for t in toks]
        except Exception:  # noqa: BLE001
            pass
        push(case)

    for cp in lex_sweep_codepoints():
        for tmpl, tag in (("{c}", "alone"), ("x{c}y", "inner"), ("{c}1", "lead")):
            src = tmpl.format(c=chr(cp))
            case = make_case(f"lexsweep:{tag}:U+{cp:04X}", "lex", src, rng, light=True)
            push(case)

    for cid, src in static_cases() + init_cases():
        push(make_case(cid if cid.startswith(("static:", "init:")) else cid, "corner", src, rng))

    for cid, src, scripts in dyn_cases():
        push(make_case(cid, "dynamic", src, rng, scripts=scripts))

    for cid, src in type_matrix():
        push(make_case(cid, "matrix", src, rng, light=True))

    # Mutations of base programs
    bases = [(cid, src) for cid, group, src in corpus
             if group in ("corpus", "guide") and 200 < len(src) < 3500 and kr_parses(src)]
    pyt = [(cid, src) for cid, group, src in corpus if group == "pytest" and 300 < len(src) < 1800 and kr_parses(src)]
    uniq: dict[str, str] = {}
    for bid, src in bases:
        uniq.setdefault(src, bid)
    bases = [(bid, src) for src, bid in uniq.items()][:14] + pyt[:6]
    seen_sources = {c["source"] for c in cases}
    mutants = 0
    mrng = random.Random(SEED + 1)
    for bi, (bid, src) in enumerate(bases):
        made = 0
        for kind, count in MUTATION_KINDS:
            for k in range(count):
                for _ in range(20):
                    mutated = mutate(src, mrng, kind)
                    if mutated is not None and mutated not in seen_sources and mutated != src:
                        break
                else:
                    continue
                seen_sources.add(mutated)
                push(make_case(f"mut:{bi}:{kind}:{k}", "mutation", mutated, rng, n_random=2))
                made += 1
                mutants += 1
    triads = triad_cases()
    ex_rows, ex_env = expr_cases()

    data = {
        "meta": {
            "generator": "Engineering/sw/kpol-go/testdata/gen_kpol_golden.py",
            "reference": "Engineering/sw/kpol-ref/kpol_reference.py",
            "reference_sha256": hashlib.sha256((REF_DIR / "kpol_reference.py").read_bytes()).hexdigest(),
            "python": sys.version.split()[0],
            "seed": SEED,
            "mutants": mutants,
        },
        "cases": cases,
        "triads": triads,
        "eval": eval_cases(random.Random(SEED + 2)),
        "unary": unary_cases(),
        "norm": norm_cases(),
        "expr": {"env": ex_env, "rows": ex_rows},
    }
    text = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
    goldenio.write_gz_text(OUT, text + "\n")
    groups: dict[str, int] = {}
    for c in cases:
        groups[c["group"]] = groups.get(c["group"], 0) + 1
    print(f"wrote {OUT} ({len(text) / 1e6:.2f} MB)")
    print("cases:", len(cases), groups, "mutants:", mutants)
    print("accepted:", sum(1 for c in cases if c["parse"]["ok"]), "triads:", len(triads),
          "eval:", len(data["eval"]), "norm:", len(data["norm"]))
    return 0


def kr_parses(src: str) -> bool:
    try:
        kr.parse_module(src)
        return True
    except Exception:  # noqa: BLE001
        return False


if __name__ == "__main__":
    raise SystemExit(main())
