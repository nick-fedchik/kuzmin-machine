#!/usr/bin/env python3
"""Generate differential golden data for the Go package kpolauth.

The Python reference (Engineering/sw/kpol-auth, plus ReferenceDoGoVM from its
lowering tests) is run over a deterministic corpus and the observable results
are written to testdata/kpolauth_golden.json.gz:

* AUTHOR_CORPUS (EX-01..EX-18), the vectors of specification Annex A.2, the
  thermal graph of the lowering tests and every ```kpol-auth block of the
  programming guide;
* every *.kpol / *.ekpol file and every fenced kpol / ekpol / kpol-auth block of
  the guides and specifications (mostly negative frontend probes);
* systematic token- and character-level mutations of the valid programs
  (deletion, duplication, swap, replacement, insertion, truncation, CRLF);
* four frontend configurations per case (default, codepoints, record-all,
  record-all+codepoints), lowering, the CLI JSON/BRAM bytes and reference-VM
  traces.

With --go-data DIR the script also emits the generated Go sources
pyunicode_tables.go (Python str character classes) and refdata.go (uncertainty
registry and AUTHOR_CORPUS) into DIR (default: ../kpolauth).

Usage (from Engineering/sw/kpol-go):
    python3 testdata/gen_kpolauth_golden.py [--go-data kpolauth] [--out PATH]

The output is fully deterministic for a given Python/Unicode version.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import unicodedata

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import goldenio  # noqa: E402
GO_MODULE = HERE.parent
REPO = GO_MODULE.parents[2]
AUTH_DIR = REPO / "Engineering" / "sw" / "kpol-auth"
SPEC = REPO / "Engineering" / "specifications" / "kpol" / "kpol-auth-formal-specification.md"
GUIDES = REPO / "Engineering" / "guides"

STEP_LIMIT = 20000
INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1
MUTANTS_PER_SEED = 36
RANDOM_PROGRAMS = 500


def load_reference():
    if "kpol_auth" in sys.modules:
        return sys.modules["kpol_auth"]
    spec = importlib.util.spec_from_file_location(
        "kpol_auth",
        AUTH_DIR / "__init__.py",
        submodule_search_locations=[str(AUTH_DIR)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["kpol_auth"] = module
    spec.loader.exec_module(module)
    return module


ka = load_reference()
lowering_mod = sys.modules["kpol_auth.lowering"]


def load_vm_module():
    path = AUTH_DIR / "tests" / "test_kpol_auth_lowering.py"
    spec = importlib.util.spec_from_file_location("kpol_auth_lowering_tests", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["kpol_auth_lowering_tests"] = module
    spec.loader.exec_module(module)
    return module


vm_mod = load_vm_module()


class StepLimitExceeded(Exception):
    pass


class Int64Overflow(Exception):
    pass


class BoundedVM(vm_mod.ReferenceDoGoVM):
    """ReferenceDoGoVM with a step limit and int64 storage detection (Go parity)."""

    def __init__(self, artifact) -> None:
        super().__init__(artifact)
        self.steps = 0

    def trigger_external(self, cid: int, val: int) -> None:
        self.steps = 0
        super().trigger_external(cid, val)

    def _exec_sub(self, sub_idx: int) -> None:
        self.steps += 1
        if self.steps > STEP_LIMIT:
            raise StepLimitExceeded()
        super()._exec_sub(sub_idx)

    def write_concept(self, cid: int, new_val: int) -> None:
        super().write_concept(cid, new_val)
        if not INT64_MIN <= self.val_cur[cid] <= INT64_MAX:
            raise Int64Overflow()


# --------------------------------------------------------------------------
# Canonical forms shared with the Go test (hex-coded strings, S-expressions).
# --------------------------------------------------------------------------


def hx(text: str) -> str:
    return text.encode("utf-8").hex()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def span_s(sp) -> str:
    if sp is None:
        return "-"
    return (
        f"{sp.line},{sp.column},{sp.offset},{sp.length},"
        f"{sp.end_line},{sp.end_column},{sp.byte_offset},{sp.byte_end}"
    )


def span_list(sp):
    if sp is None:
        return None
    return [sp.line, sp.column, sp.offset, sp.length, sp.end_line, sp.end_column, sp.byte_offset, sp.byte_end]


def tok_s(t) -> str:
    return f"T({t.kind},{hx(t.value)},{span_s(t.span)})"


def node_s(n) -> str:
    name = type(n).__name__
    sp = span_s(n.span)
    if isinstance(n, (ka.IdentifierCST, ka.LiteralCST, ka.UninitCST)):
        return f"({name} {sp} {tok_s(n.token)})"
    if isinstance(n, ka.ParamCST):
        return f"({name} {sp} {tok_s(n.at_token)} {node_s(n.target)})"
    if isinstance(n, ka.BracketGroupCST):
        elems = " ".join(node_s(e) for e in n.elements)
        commas = " ".join(tok_s(c) for c in n.comma_tokens)
        return (
            f"({name} {sp} {tok_s(n.open_token)} {tok_s(n.close_token)} {n.kind} "
            f"{int(n.has_stub_brackets)} [{elems}] [{commas}])"
        )
    if isinstance(n, ka.CallOrConstructCST):
        assert n.bounds is None
        return f"({name} {sp} {node_s(n.name)} {node_s(n.group)})"
    if isinstance(n, ka.GroupBoundsCST):
        return (
            f"({name} {sp} {node_s(n.target)} {node_s(n.bracket_group)} "
            f"{n.min_raw} {n.max_raw} {n.min_effective} {n.max_effective})"
        )
    if isinstance(n, ka.DefLayoutCST):
        bits = ",".join(str(b) for b in n.bits)
        return f"({name} {sp} {node_s(n.keyword)} {node_s(n.group)} [{bits}] {n.bit_order})"
    if isinstance(n, ka.SubscriptionSeqCST):
        return f"({name} {sp} {node_s(n.left)} {tok_s(n.dot_token)} {node_s(n.right)})"
    if isinstance(n, (ka.AssignmentCST, ka.BinaryExprCST)):
        right = n.value if isinstance(n, ka.AssignmentCST) else n.right
        left = n.target if isinstance(n, ka.AssignmentCST) else n.left
        return f"({name} {sp} {node_s(left)} {tok_s(n.op_token)} {node_s(right)})"
    raise AssertionError(name)


def diag_s(d) -> str:
    return (
        f"D({d.code},{d.severity},{hx(d.message)},{span_s(d.span)},"
        f"{d.uncertainty_code or '-'},{hx(d.source_ref) if d.source_ref else '-'})"
    )


def parse_canon(src: str, cfg):
    """Return (canonical string, ProgramCST | None, result dict)."""
    try:
        prog = ka.parse_kpol_auth(src, cfg)
    except ka.KpolAuthError as exc:
        d = exc.diagnostic
        canon = f"E|{diag_s(d)}"
        res = {
            "ok": False,
            "code": d.code,
            "message": d.message,
            "span": span_list(d.span),
            "h": sha(canon),
        }
        return canon, None, res
    except Exception as exc:  # unhandled reference crash (documented deviations)
        return "X|" + type(exc).__name__, None, {"ok": False, "crash": type(exc).__name__}
    items = ";".join(node_s(i) for i in prog.items)
    diags = ";".join(diag_s(d) for d in prog.diagnostics)
    canon = f"K|{len(prog.items)}|{items}|{diags}"
    res = {
        "ok": True,
        "n": len(prog.items),
        "root": type(prog.items[0]).__name__ if prog.items else None,
        "dcodes": [d.code for d in prog.diagnostics],
        "h": sha(canon),
    }
    return canon, prog, res


def dogo_payload(art) -> str:
    payload = {
        "format": "kpol-auth-dogo-0.1.0",
        "concepts": [asdict(c) for c in art.concepts],
        "subscriptions": [asdict(s) for s in art.subscriptions],
        "code_o": list(art.code_o),
        "code_o_hex": [f"0x{w:08X}" for w in art.code_o],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def lower_canon(prog):
    try:
        art = ka.lower_kpol_auth(prog)
    except ka.KpolAuthLoweringError as exc:
        canon = f"E|{exc.code}|{hx(exc.message)}|{span_s(exc.span)}"
        return canon, None, {
            "ok": False,
            "code": exc.code,
            "message": exc.message,
            "span": span_list(exc.span),
            "h": sha(canon),
        }
    except Exception as exc:
        return "X|" + type(exc).__name__, None, {"ok": False, "crash": type(exc).__name__}
    doc = dogo_payload(art)
    canon = f"K|{sha(doc)}|{hashlib.sha256(art.bram_image).hexdigest()}"
    res = {
        "ok": True,
        "code_o": list(art.code_o),
        "bram_sha256": hashlib.sha256(art.bram_image).hexdigest(),
        "dogo_sha256": sha(doc),
        "dogo_bin_sha256": hashlib.sha256(b"".join(struct.pack("<I", w) for w in art.code_o)).hexdigest(),
        "concepts": len(art.concepts),
        "subscriptions": len(art.subscriptions),
        "h": sha(canon),
    }
    return canon, art, res


def vm_trace(art):
    n = len(art.concepts)
    seq_a = [(0, v) for v in (4, 4, 0, 6, -3, 100, 5, 2147483647)]
    seq_b = []
    for cid in range(min(n, 6)):
        seq_b.append((cid, 7))
        seq_b.append((cid, -2))
    seq_b.append((n - 1, 33))
    out = {}
    for label, seq in (("a", seq_a), ("b", seq_b)):
        machine = BoundedVM(art)
        steps = []
        for cid, val in seq:
            try:
                machine.trigger_external(cid, val)
            except StepLimitExceeded:
                steps.append([cid, val, "steps"])
                break
            except Int64Overflow:
                steps.append([cid, val, "overflow"])
                break
            except Exception as exc:
                steps.append([cid, val, "error:" + type(exc).__name__])
                break
            steps.append([cid, val, list(machine.val_cur), list(machine.big_dot_ok)])
        out[label] = steps
    return out


CFG_DEFAULT = ka.AuthFrontendConfig()
CFG_CP = ka.AuthFrontendConfig(name_length_unit="codepoints")
CFG_REC = ka.AuthFrontendConfig(policies={c: "record-diagnostic" for c in ka.UNCERTAINTY_REGISTRY})
CFG_REC_CP = ka.AuthFrontendConfig(
    policies={c: "record-diagnostic" for c in ka.UNCERTAINTY_REGISTRY},
    name_length_unit="codepoints",
)


def build_case(origin: str, src: str) -> dict:
    _, prog, front = parse_canon(src, CFG_DEFAULT)
    case = {"origin": origin, "src": src, "front": front}
    cp = parse_canon(src, CFG_CP)[2]
    rec_canon, rec_prog, rec = parse_canon(src, CFG_REC)
    reccp = parse_canon(src, CFG_REC_CP)[2]
    case["cp"] = {k: cp[k] for k in ("ok", "h", "crash", "code") if k in cp}
    case["rec"] = {k: rec[k] for k in ("ok", "h", "crash", "code", "dcodes") if k in rec}
    case["reccp"] = {k: reccp[k] for k in ("ok", "h", "crash", "code") if k in reccp}
    if rec_prog is not None:
        case["lower_rec"] = {k: v for k, v in lower_canon(rec_prog)[2].items() if k in ("ok", "h", "crash", "code")}
    if prog is not None:
        _, art, low = lower_canon(prog)
        case["lower"] = low
        if art is not None:
            case["vm"] = vm_trace(art)
    return case


# --------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------


def fenced_blocks(path: Path, langs):
    text = path.read_text(encoding="utf-8")
    for m in re.finditer(r"^```([A-Za-z0-9_-]*)[^\n]*\n(.*?)^```", text, re.S | re.M):
        if m.group(1) in langs:
            yield m.group(1), m.group(2)


def spec_a2_vectors():
    text = SPEC.read_text(encoding="utf-8")
    a2 = text[text.index("### A.2."):]
    rows = []
    for line in a2.splitlines():
        m = re.match(r"^\| `(?P<src>Concept.*?)` \| `(?P<code>[0-9A-F ]+)` \| `(?P<sha>[0-9a-f]{64})` \|$", line)
        if m:
            rows.append((m.group("src"), m.group("code"), m.group("sha")))
    assert len(rows) == 3, rows
    return rows


EXTRA_SEEDS = [
    "Concept(A, 0)\nConcept(B, 0)\nConcept(C, 0)\nA • Assign(B, A * 2 + 1)\nB • Assign(C, (B - 3) * (A + 1))",
    "Concept(Температура, 20)\nConcept(Нагрів, 0)\nТемпература • Assign(Нагрів, Температура * 2)",
    "Concept(X, 5, Lower=0, Upper=10)\nConcept(Y, 0)\nConcept(Z, 0)\nOnAbort(X) • {Assign(Y, 1), Assign(Z, Y + 2)}",
    "Concept(A, 1)\nConcept(B, 1)\nOnPositive(A) • Assign(B, A - 1)\nOnAbort(B) • Assign(A, B)",
    "Concept(A, 0)\nA := B := C\nA • B • C\n{A B}[Min=2][Max=3]",
    "Name(\"Name16CharsLong!!\") Property(DefBit=1, Value=0) Def{1, 1, 0, 1, 0, 0, 1}",
    "Concept(A, 0) Concept(B, 0) A • Assign(B, A + 1 * 2 - 3)\nB",
    "Concept(A, 3)\nConcept(B, 0)\nConcept(C, 0)\nConcept(D, 0)\nA • Assign(B, A * A)\n"
    "B • Assign(C, B - A)\nOnPositive(C) • Assign(D, C + 100)",
    "Concept(A, 2147483647)\nConcept(B, 0)\nConcept(C, 0)\nConcept(D, 0)\nConcept(E, 0)\n"
    "A • Assign(B, A * A)\nB • Assign(C, B * B)\nC • Assign(D, C * C)\nD • Assign(E, D * D)",
    "Concept(A, 5, Lower=10, Upper=20)\nOnAbort(A) • Assign(A, 1)",
    "Concept(A, 15, Lower=10, Upper=20)\nConcept(B, 0, Lower=0, Upper=5)\nConcept(C, 0)\n"
    "OnAbort(A) • Assign(B, 9)\nOnAbort(B) • {Assign(A, 1), Assign(C, B + 1)}",
    "Concept(A, 0, Lower=-1)",
    "Concept(S, 0)\nConcept(T, 0)\nConcept(U, 0)\nConcept(V, 0)\nS • Assign(T, S + 1)\n"
    "OnPositive(S) • Assign(U, S)\nOnAbort(S) • Assign(V, 1)\nT • Assign(U, T)",
]

# Seeds in the lowering subset get a larger share of the mutation budget.
LOWERING_ORIGINS = ("spec-a2:", "test:thermal", "guide:", "extra:")
LOWERING_CAP = 120


def edge_programs():
    """Boundary programs of the limits KPA-L-4 and KPA-L-10 (not mutated)."""
    def concepts(n):
        return "\n".join(f"Concept(C{i}, {i})" for i in range(n))

    def abort_lines(n, expr):
        return "\n".join(f"OnAbort(C0) • Assign(C1, {expr})" for _ in range(n))

    base = "Concept(C0, 0)\nConcept(C1, 0)\n"
    ones = " + ".join(["1"] * 5)
    return [
        ("edge:concepts-64", concepts(64)),
        ("edge:concepts-65", concepts(65)),
        ("edge:subs-128", base + abort_lines(128, "1")),
        ("edge:subs-129", base + abort_lines(129, "1")),
        ("edge:words-512", base + abort_lines(46, ones) + "\n" + abort_lines(2, "1")),
        ("edge:words-513", base + abort_lines(46, ones) + "\n" + abort_lines(1, "1 + 1 + 1")),
        ("edge:empty", ""),
        ("edge:blank", "  \n\t\n"),
        ("edge:fanout-oncePositive", "Concept(A, 0)\nConcept(B, 0)\nConcept(C, 0)\nA • Assign(B, 1)\nOnPositive(A) • Assign(C, 1)"),
        ("edge:cycle-3", "Concept(A, 0)\nConcept(B, 0)\nConcept(C, 0)\nA • Assign(B, 1)\nB • Assign(C, 1)\nC • Assign(A, 1)"),
        ("edge:rank-backwards", "Concept(A, 0)\nConcept(B, 0)\nB • Assign(A, 1)"),
        ("edge:abort-self", "Concept(A, 0)\nOnAbort(A) • Assign(A, 1)"),
        ("edge:empty-sub", "Concept(A, 0)\nA • {}"),
        ("edge:imm-negative", "Concept(A, 0)\nConcept(B, 0)\nA • Assign(B, 0 - 5 + A)"),
        ("edge:unicode-digit", "Concept(A, ٣)\nConcept(B, 0)\nA • Assign(B, ٣٣ + A)"),
        ("edge:isdigit-only", "Concept(A, ²)"),
        ("edge:int-bounds", "Concept(A, 2147483647)\nConcept(B, 2147483648)"),
        ("edge:imm-bounds", "Concept(A, 0)\nConcept(B, 0)\nA • Assign(B, 32767)\nB • Assign(A, 32768)"),
    ]


def collect_seeds():
    """Valid-ish programs used as mutation seeds, as (origin, text)."""
    seeds = []
    for ex in ka.AUTHOR_CORPUS:
        seeds.append((f"corpus:{ex.id}", ex.source_text))
    for i, (src, _, _) in enumerate(spec_a2_vectors(), 1):
        seeds.append((f"spec-a2:{i}", src))
    seeds.append(("test:thermal", vm_mod.THERMAL_GRAPH_SOURCE))
    guide = GUIDES / "kpol-auth-programming-guide.md"
    for i, (_, body) in enumerate(fenced_blocks(guide, {"kpol-auth"}), 1):
        seeds.append((f"guide:kpol-auth:{i}", body))
    for i, src in enumerate(EXTRA_SEEDS, 1):
        seeds.append((f"extra:{i}", src))
    return seeds


def collect_probes():
    """Non-mutated probes (files/blocks of the repository), as (origin, text)."""
    out = edge_programs()
    for pattern in ("*.kpol", "*.ekpol"):
        for p in sorted((REPO / "Engineering").rglob(pattern)):
            if GO_MODULE in p.parents:
                continue  # the Go module's own scratch and test data are not part of the corpus
            out.append((f"file:{p.relative_to(REPO).as_posix()}", p.read_text(encoding="utf-8")))
    for folder in (GUIDES, REPO / "Engineering" / "specifications" / "kpol"):
        for p in sorted(folder.glob("*.md")):
            for i, (lang, body) in enumerate(fenced_blocks(p, {"kpol", "ekpol", "kpol-auth"}), 1):
                out.append((f"block:{lang}:{p.relative_to(REPO).as_posix()}#{i}", body))
    return out


INT_REPL = ["0", "1", "2", "3", "5", "15", "16", "32767", "32768", "65535", "65536", "2147483647",
            "2147483648", "4294967296", "99999999999999999999", "007", "٣", "²", "①"]
IDENT_EXTRA = ["Concept", "Assign", "OnAbort", "OnPositive", "Lower", "Upper", "Def", "Name", "Child",
               "busy", "Busy", "runtime", "CloseBracked", "CloseBracket", "OpenBracket", "Property",
               "Value", "DefBit", "Min", "Max", "Count", "Logic", "Op", "Static", "_", "Ж", "A1", "_x"]
OP_REPL = ["+", "-", "*", "/", "=", "<", ">", ":", ":=", "•", ",", "!", "¬", "@", "_", "0"]
BRACKET_REPL = ["(", ")", "{", "}", "[", "]"]
TEXT_REPL = ['""', '"x"', "«x»", '"\\"', "«»", '"ПривітСвітДовгеІм"', '"0123456789abcdef"',
             '"0123456789abcdefg"', '"Абвгдеєж"', '"АбвгдеєжA"', '"unterminated', "«open"]
INSERTS = ["#", "\\", "'", "¤", "←", "→", "|", "~", ";", ".", "?", "\u00a0", "\u2003", "\ufeff", "«", "»",
           '"', "@", "@runtime", "busy", "Child", "_", "•", ",", ",,", "(", ")", "[Min=1]", "[Max=0]",
           "[Min=Byte(1)]", "[Logic=AND]", "[Count=7]", 'Name("x")', "Def(1)", "-1", "^", "$", "٣", "²"]


def mutants_of(seed: str):
    try:
        toks, _ = ka.tokenize(seed, CFG_REC)
    except Exception:
        toks = []
    idents = sorted({t.value for t in toks if t.kind == "IDENT"})
    out = []

    def add(op, text):
        if text != seed:
            out.append((op, text))

    for i, t in enumerate(toks):
        a, b = t.span.offset, t.span.offset + t.span.length
        add("delete", seed[:a] + seed[b:])
        add("duplicate", seed[:b] + " " + seed[a:b] + seed[b:])
        if i + 1 < len(toks):
            n = toks[i + 1]
            c, d = n.span.offset, n.span.offset + n.span.length
            add("swap", seed[:a] + seed[c:d] + seed[b:c] + seed[a:b] + seed[d:])
        add("truncate", seed[:a])
        for ins in INSERTS:
            add("insert", seed[:a] + ins + " " + seed[a:])
        if t.kind == "INT":
            for rep in INT_REPL:
                add("replace-int", seed[:a] + rep + seed[b:])
            if t.value.isascii():
                add("number-plus1", seed[:a] + str(int(t.value) + 1) + seed[b:])
                add("number-minus1", seed[:a] + str(max(int(t.value) - 1, 0)) + seed[b:])
        elif t.kind == "IDENT":
            for rep in idents + IDENT_EXTRA:
                add("replace-ident", seed[:a] + rep + seed[b:])
        elif t.kind == "TEXT":
            for rep in TEXT_REPL:
                add("replace-text", seed[:a] + rep + seed[b:])
        elif t.kind in ("LBRACE", "RBRACE", "LPAREN", "RPAREN", "LBRACKET", "RBRACKET"):
            for rep in BRACKET_REPL:
                add("replace-bracket", seed[:a] + rep + seed[b:])
        else:
            for rep in OP_REPL:
                add("replace-op", seed[:a] + rep + seed[b:])
    add("truncate", seed[: len(seed) // 2])
    add("crlf", seed.replace("\n", "\r\n"))
    add("cr", seed.replace("\n", "\r"))
    add("tabs", seed.replace(" ", "\t"))
    add("indent", "\n  " + seed.replace("\n", "\n  ") + "\n")
    add("append-newline", seed + "\n#")
    lines = seed.split("\n")
    for i in range(len(lines)):
        add("line-delete", "\n".join(lines[:i] + lines[i + 1 :]))
        add("line-duplicate", "\n".join(lines[: i + 1] + lines[i:]))
        if i + 1 < len(lines):
            add("line-swap", "\n".join(lines[:i] + [lines[i + 1], lines[i]] + lines[i + 2 :]))
    add("line-reverse", "\n".join(reversed(lines)))
    add("line-double", seed + "\n" + seed)
    return out


def select_mutants(seed: str, limit: int):
    groups = {}
    for op, text in mutants_of(seed):
        groups.setdefault(op, []).append(text)
    for op in groups:
        seen = set()
        uniq = []
        for text in sorted(groups[op], key=lambda t: hashlib.sha1(t.encode("utf-8")).hexdigest()):
            if text not in seen:
                seen.add(text)
                uniq.append(text)
        groups[op] = uniq
    picked = []
    seen_all = {seed}
    ops = sorted(groups)
    idx = 0
    while len(picked) < limit and any(groups[op] for op in ops):
        op = ops[idx % len(ops)]
        idx += 1
        while groups[op]:
            text = groups[op].pop(0)
            if text not in seen_all:
                seen_all.add(text)
                picked.append((op, text))
                break
    return picked


class XorShift:
    """Small deterministic PRNG, independent of the Python version."""

    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFFFFFFFFFF or 1

    def next(self) -> int:
        x = self.state
        x ^= (x << 13) & 0xFFFFFFFFFFFFFFFF
        x ^= x >> 7
        x ^= (x << 17) & 0xFFFFFFFFFFFFFFFF
        self.state = x
        return x

    def below(self, n: int) -> int:
        return (self.next() >> 11) % n

    def choice(self, items):
        return items[self.below(len(items))]


def random_programs(count: int):
    """Random programs of the L1 subset (mostly valid) for lowering and VM coverage."""
    rng = XorShift(0x4B504F4C)
    inits = [0, 0, 1, 2, 3, 5, 7, 10, 100, 32767, 65536, 2147483647]
    consts = [0, 1, 2, 3, 4, 5, 10, 100, 1000, 32767, 32767, 32768, 70000]
    small = consts[:9]
    out = []
    for i in range(count):
        n = 2 + rng.below(7)
        names = [f"C{k}" for k in range(n)]
        lines = []
        for k, name in enumerate(names):
            opts = ""
            if rng.below(4) == 0:
                lo = rng.choice([0, 1, 5])
                hi = lo + rng.choice([0, 3, 50, 1000])
                kind = rng.below(3)
                opts = ", Lower=%d" % lo if kind == 0 else ", Upper=%d" % hi if kind == 1 else ", Lower=%d, Upper=%d" % (lo, hi)
            lines.append(f"Concept({name}, {rng.choice(inits)}{opts})")

        def expr(depth):
            r = rng.below(10)
            if depth == 0 or r < 3:
                if rng.below(2):
                    return str(rng.choice(consts if rng.below(12) == 0 else small))
                return rng.choice(names)
            left, right = expr(depth - 1), expr(depth - 1)
            op = rng.choice(["+", "-", "*"])
            text = f"{left} {op} {right}"
            return f"({text})" if rng.below(3) == 0 else text

        for _ in range(rng.below(9)):
            kind = rng.below(5)
            src = rng.below(n)
            dst = rng.below(n)
            if kind < 3 and rng.below(10) < 8 and src + 1 < n:
                dst = src + 1 + rng.below(n - src - 1)
            trigger = names[src] if kind in (0, 1) else f"OnPositive({names[src]})" if kind == 2 else f"OnAbort({names[src]})"
            if kind == 4 and rng.below(2):
                body = ", ".join(f"Assign({names[rng.below(n)]}, {expr(2)})" for _ in range(1 + rng.below(3)))
                lines.append(f"{trigger} • {{{body}}}")
            else:
                lines.append(f"{trigger} • Assign({names[dst]}, {expr(rng.below(4))})")
        out.append((f"random:{i}", "\n".join(lines) + "\n"))
    return out


def build_cases(per_seed=MUTANTS_PER_SEED, per_lowering_seed=LOWERING_CAP, random_count=RANDOM_PROGRAMS):
    cases = []
    seen = set()

    def push(origin, src):
        if src in seen:
            return
        seen.add(src)
        cases.append(build_case(origin, src))

    for origin, src in collect_seeds():
        push(origin, src)
    for origin, src in collect_probes():
        push(origin, src)
    for origin, seed in collect_seeds():
        cap = per_lowering_seed if origin.startswith(LOWERING_ORIGINS) else per_seed
        for op, text in select_mutants(seed, cap):
            push(f"mutant:{op}:{origin}", text)
    for origin, src in random_programs(random_count):
        push(origin, src)
    for n, case in enumerate(cases):
        case["id"] = n
    return cases


# --------------------------------------------------------------------------
# CLI-level golden: DoGoJSON, binary and error text for a handful of programs
# --------------------------------------------------------------------------


def build_cli_cases(cases):
    out = []
    for case in cases:
        if "lower" not in case or not case["lower"]["ok"]:
            continue
        if case["origin"].startswith("mutant:") and case["id"] % 7:
            continue
        art = ka.lower_document(case["src"])
        out.append({
            "src": case["src"],
            "json": dogo_payload(art),
            "bin_hex": b"".join(struct.pack("<I", w) for w in art.code_o).hex(),
            "bram_sha256": hashlib.sha256(art.bram_image).hexdigest(),
        })
    return out


# --------------------------------------------------------------------------
# Generated Go sources
# --------------------------------------------------------------------------


def go_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def ranges(pred):
    out, start = [], None
    for cp in range(0x110000):
        ok = not 0xD800 <= cp <= 0xDFFF and pred(chr(cp))
        if ok and start is None:
            start = cp
        elif not ok and start is not None:
            out.append((start, cp - 1))
            start = None
    if start is not None:
        out.append((start, 0x10FFFF))
    return out


def emit_table(name, doc, items):
    lines = [f"// {doc}", f"var {name} = []runeRange{{"]
    row = []
    for lo, hi in items:
        row.append(f"{{0x{lo:04X}, 0x{hi:04X}}},")
        if len(row) == 4:
            lines.append("\t" + " ".join(row))
            row = []
    if row:
        lines.append("\t" + " ".join(row))
    lines.append("}")
    return "\n".join(lines)


def write_go_tables(path: Path):
    decimal = ranges(str.isdecimal)
    for lo, hi in decimal:
        for cp in range(lo, hi + 1):
            assert unicodedata.decimal(chr(cp)) == (cp - lo) % 10 and int(chr(cp)) == (cp - lo) % 10
    digit, numeric, alpha = ranges(str.isdigit), ranges(str.isnumeric), ranges(str.isalpha)
    for cp in range(0x110000):
        if not 0xD800 <= cp <= 0xDFFF:
            ch = chr(cp)
            assert ch.isalnum() == (ch.isalpha() or ch.isnumeric())
            assert not ch.isdecimal() or ch.isdigit()
            assert not ch.isdigit() or ch.isnumeric()
    parts = [
        "// Code generated by testdata/gen_kpolauth_golden.py; DO NOT EDIT.",
        "",
        "package kpolauth",
        "",
        f"// pyUnicodeVersion is the Unicode version of Python {sys.version.split()[0]} used to generate the tables.",
        f'const pyUnicodeVersion = "{unicodedata.unidata_version}"',
        "",
        "// runeRange is an inclusive range of code points.",
        "type runeRange struct{ lo, hi rune }",
        "",
        emit_table("pyAlphaTable", "pyAlphaTable lists the code points with str.isalpha() == True.", alpha),
        "",
        emit_table("pyDigitTable", "pyDigitTable lists the code points with str.isdigit() == True.", digit),
        "",
        emit_table("pyNumericTable", "pyNumericTable lists the code points with str.isnumeric() == True.", numeric),
        "",
        emit_table(
            "pyDecimalTable",
            "pyDecimalTable lists the code points with str.isdecimal() == True; "
            "each range is a sequence of complete 0..9 runs.",
            decimal,
        ),
        "",
    ]
    path.write_text("\n".join(parts), encoding="utf-8")


def write_go_refdata(path: Path):
    lines = [
        "// Code generated by testdata/gen_kpolauth_golden.py; DO NOT EDIT.",
        "",
        "package kpolauth",
        "",
        "// registryData is the uncertainty registry of uncertainty.py (KPOL-AUTH-U01..U12).",
        "var registryData = [...]UncertaintyPoint{",
    ]
    for code in sorted(ka.UNCERTAINTY_REGISTRY):
        p = ka.UNCERTAINTY_REGISTRY[code]
        lines.append(
            f"\t{{Code: {go_str(p.code)}, RFC: {go_str(p.rfc)}, Topic: {go_str(p.topic)}, "
            f"SourceStatus: {go_str(p.source_status)}, DefaultPolicy: {go_str(p.default_policy)}}},"
        )
    lines += ["}", "", "// corpusData is AUTHOR_CORPUS of corpus.py.", "var corpusData = [...]CorpusExample{"]
    for ex in ka.AUTHOR_CORPUS:
        refs = ", ".join(go_str(r) for r in ex.source_refs)
        diags = ", ".join(go_str(d) for d in ex.expected_diagnostics)
        kind = go_str(ex.expected_cst_kind) if ex.expected_cst_kind else '""'
        lines += [
            "\t{",
            f"\t\tID: {go_str(ex.id)},",
            f"\t\tTitle: {go_str(ex.title)},",
            f"\t\tSourceText: {go_str(ex.source_text)},",
            f"\t\tSourceRefs: []string{{{refs}}},",
            f"\t\tExpectedStatus: {go_str(ex.expected_status)},",
            f"\t\tExpectedCSTKind: {kind},",
            f"\t\tExpectedDiagnostics: []string{{{diags}}},",
            f"\t\tSourceBoundaryNote: {go_str(ex.source_boundary_note)},",
            f"\t\tInSourceScope: {'true' if ex.in_source_scope else 'false'},",
            f"\t\tShowToAuthor: {'true' if ex.show_to_author else 'false'},",
            "\t},",
        ]
    lines += ["}", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def gofmt(*paths: Path) -> None:
    """Format generated sources with gofmt (the generated files are gofmt-clean)."""
    import shutil
    import subprocess

    tool = shutil.which("gofmt")
    if tool is None:
        print("warning: gofmt not found; generated Go files are not formatted", file=sys.stderr)
        return
    subprocess.run([tool, "-w", *map(str, paths)], check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=HERE / "kpolauth_golden.json.gz")
    ap.add_argument("--go-data", type=Path, default=None, metavar="DIR",
                    help="also write pyunicode_tables.go and refdata.go into DIR")
    ap.add_argument("--no-golden", action="store_true", help="skip the JSON golden file")
    ap.add_argument("--mutants", type=int, default=MUTANTS_PER_SEED, help="mutants per ordinary seed")
    ap.add_argument("--random", type=int, default=RANDOM_PROGRAMS, help="random L1 programs")
    ap.add_argument("--lowering-mutants", type=int, default=LOWERING_CAP, help="mutants per lowering seed")
    args = ap.parse_args()

    if args.go_data is not None:
        args.go_data.mkdir(parents=True, exist_ok=True)
        write_go_tables(args.go_data / "pyunicode_tables.go")
        write_go_refdata(args.go_data / "refdata.go")
        gofmt(args.go_data / "pyunicode_tables.go", args.go_data / "refdata.go")
    if args.no_golden:
        return 0

    cases = build_cases(args.mutants, args.lowering_mutants, args.random)
    a2 = [
        {"src": src, "code_o": [int(w, 16) for w in code.split()], "bram_sha256": digest}
        for src, code, digest in spec_a2_vectors()
    ]
    for vec in a2:
        art = ka.lower_document(vec["src"])
        assert list(art.code_o) == vec["code_o"], vec["src"]
        assert hashlib.sha256(art.bram_image).hexdigest() == vec["bram_sha256"], vec["src"]
    doc = {
        "format": "kpolauth-golden-1",
        "python": sys.version.split()[0],
        "unicode": unicodedata.unidata_version,
        "step_limit": STEP_LIMIT,
        "cases": cases,
        "cli": build_cli_cases(cases),
        "spec_a2": a2,
    }
    goldenio.write_gz_text(args.out, json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
    kinds = {}
    for case in cases:
        key = case["origin"].split(":")[0]
        kinds[key] = kinds.get(key, 0) + 1
    ok = sum(1 for c in cases if c["front"]["ok"])
    lowered = sum(1 for c in cases if c.get("lower", {}).get("ok"))
    print(f"wrote {args.out} cases={len(cases)} {kinds} frontend-ok={ok} lowered={lowered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
