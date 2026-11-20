#!/usr/bin/env python3
"""Generate testdata/c99_golden.json.gz: reference results for the Go `c99` package.

The generator drives Engineering/sw/kpol-ref/c99_emitter.py (the oracle) with
the system `z3` CLI as the only solver backend (the z3-solver Python API is
disabled so that Z3 "witness" text is deterministic and identical to what the
Go port produces) over:

  * every image the reference compiler builds from the example corpus
    (vmk-go/examples, hw/tests, validation, fenced blocks of the guides);
  * systematically mutated valid images (opcodes, guard flags, operands,
    cascades, cycles, out-of-range subscribers, random mutations);
  * concept-name / module-name / shape edge cases;
  * C99 *source* mutants of the emitted text (certificate negative controls);
  * seeded event traces for ReferenceCmeSafetyEngine.

Run from anywhere:  python3 gen_c99_golden.py [OUT.json]
Requires /usr/bin/z3 (fail-closed, like the reference).
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
import struct
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import goldenio  # noqa: E402
REPO = HERE.parents[3]
ENG = REPO / "Engineering"
SW_REF = ENG / "sw" / "kpol-ref"
sys.path.insert(0, str(SW_REF))

import c99_emitter as ce  # noqa: E402
import ekpol_frontend as ef  # noqa: E402
import kpol_reference as kr  # noqa: E402

if shutil.which("z3") is None:
    sys.exit("z3 binary is required to generate the golden file")
# Force the CLI backend: deterministic witness text, same as the Go port.
ce.HAS_Z3_PYTHON = False
ce.z3 = None

SOLVER_PLACEHOLDER = "@SOLVER@"
FULL_TEXT_KINDS = ("corpus",)  # full C99/certificate text only for these kinds; others keep SHA-256
FULL_JSON_MUTANTS = {"m1-invariant-true", "m2-fault-gate-off", "m3-topo-reversed", "m4-gt-ge", "m4-table-row-sub"}

M = 0xFFFFFFFF


def sha256(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def pack_image(descs) -> bytes:
    img = bytearray(1024)
    for d in descs:
        img[d.cid * 16:(d.cid + 1) * 16] = d.pack()
    return bytes(img)


def slots_of(image: bytes):
    out = []
    for cid in range(64):
        w = struct.unpack_from("<IIII", image, cid * 16)
        if any(w):
            out.append([cid, *w])
    return out


def mk(cid, state=0, operand=0, pred=0, guard=0, hazard=0, act=0, sub=0):
    return kr.ConceptMicroDescriptor(
        cid=cid, name=f"Concept_{cid}", current_state=state & M, operand_val=operand & M,
        pred_opcode=pred, guard_flags=guard, hazard_limit=hazard, action_opcode=act,
        subscriber_cid=sub & M,
    )


def table(base: bytes):
    return list(kr.disassemble_concept_microcode(base))


def put(tab, cid, **kw):
    tab = list(tab)
    tab[cid] = replace(tab[cid], **kw)
    return tab


def exc_info(e: Exception) -> dict:
    return {"exc": type(e).__name__, "message": str(e)}


# --------------------------------------------------------------------------
# Running the reference
# --------------------------------------------------------------------------

def run_emit(src, names, module_name, allow_unverified=False):
    kw = {"module_name": module_name, "require_z3_verified": not allow_unverified}
    if names is not None:
        kw["concept_names"] = names
    try:
        text = ce.emit_c99_safety_module(src, **kw)
    except Exception as e:  # noqa: BLE001 - recorded verbatim
        return None, {"ok": False, **exc_info(e)}
    return text, {"ok": True, "c99_sha256": sha256(text), "c99_len": len(text)}


def run_cert(src, names, module_name, c99_source):
    kw = {"module_name": module_name, "c99_source": c99_source}
    if names is not None:
        kw["concept_names"] = names
    try:
        cert = ce.prove_c99_descriptor_safety_z3(src, **kw)
    except Exception as e:  # noqa: BLE001
        return None, {"ok": False, **exc_info(e)}
    assert cert["solver"].startswith("z3-cli"), cert["solver"]
    cert["solver"] = SOLVER_PLACEHOLDER
    text = json.dumps(cert, indent=2, ensure_ascii=False) + "\n"
    return text, {
        "ok": True,
        "json_sha256": sha256(text),
        "verdict": cert["verdict"],
        "passed": cert["passed"],
        "statuses": [cert["checks"][k]["status"] for k in sorted(cert["checks"])],
        "failures": cert["failures"],
    }


def parsed_summary(text):
    try:
        p = ce.parse_emitted_c99_source(text)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, **exc_info(e)}
    packed = b"".join(d.pack() for d in p.descriptors)
    return {
        "ok": True,
        "topo_order": p.topo_order, "topo_loop_reversed": p.topo_loop_reversed,
        "descriptors_sha256": sha256(packed), "has_fault_gate": p.has_fault_gate,
        "ops": [p.pred_eq_op, p.pred_neq_op, p.pred_gt_op, p.pred_lt_op, p.range_lo_op,
                p.range_hi_op, p.act_inc_op, p.act_dec_op, p.act_add_op, p.act_sub_op,
                p.sub_ovf_xor_op],
        "range_sext": p.range_sext, "inv_overflow": p.invariant_checks_overflow,
        "inv_nonneg": p.invariant_checks_nonneg, "commit_inv": p.commit_checks_invariant,
        "self_suppress": p.has_self_suppress,
    }


# --------------------------------------------------------------------------
# Corpus images (as compile_kpol_bram_image.py builds them)
# --------------------------------------------------------------------------

def compile_kpol(source: str, profile: str):
    module = kr.Parser(source).parse()
    image = kr.compile_concept_microcode_bram_image(module, profile=profile)
    return module.name, [st.name for st in module.states], image


def compile_ekpol(source: str, stem: str):
    prog = ef.parse_ekpol(source, default_module_name=stem)
    image = ef.compile_ekpol_to_bram_image(prog)
    return prog.module_name, [c.name for c in prog.concepts], image


def fenced_blocks(path: Path, lang: str):
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"^```" + lang + r"[ \t]*\n(.*?)^```[ \t]*$", re.S | re.M)
    return [m.group(1) for m in pattern.finditer(text)]


def corpus_cases():
    cases, skipped = [], []
    files = []
    for pattern in ("sw/vmk-go/examples/*.kpol", "sw/vmk-go/examples/*.ekpol", "hw/tests/*.kpol"):
        files += sorted(ENG.glob(pattern))
    for pattern in ("*.kpol", "*.ekpol"):
        files += sorted(p for p in (ENG / "validation").rglob(pattern))
    seen = set()
    for path in files:
        rel = path.relative_to(ENG).as_posix()
        src = path.read_text(encoding="utf-8")
        if path.suffix == ".ekpol":
            attempts = [("EKPOL", lambda s=src, st=path.stem: compile_ekpol(s, st))]
        else:
            attempts = [(p, lambda s=src, p=p: compile_kpol(s, p)) for p in ("KPOL-CME-1", "KPOL-CME-2")]
        for profile, fn in attempts:
            try:
                module_name, names, image = fn()
            except Exception as e:  # noqa: BLE001
                skipped.append({"source": rel, "profile": profile, "reason": f"{type(e).__name__}: {str(e)[:120]}"})
                continue
            key = (module_name, tuple(names), image)
            if key in seen:
                continue
            seen.add(key)
            cases.append({"id": f"corpus/{rel}#{profile}", "kind": "corpus", "source": rel,
                          "profile": profile, "image": image, "names": names, "module": module_name})
    for gpath in sorted((ENG / "guides").glob("*.md")):
        for lang in ("kpol", "ekpol"):
            for idx, block in enumerate(fenced_blocks(gpath, lang)):
                rel = f"guides/{gpath.name}[{lang}#{idx}]"
                if lang == "ekpol":
                    attempts = [("EKPOL", lambda s=block: compile_ekpol(s, "GuideModule"))]
                else:
                    attempts = [(p, lambda s=block, p=p: compile_kpol(s, p)) for p in ("KPOL-CME-1", "KPOL-CME-2")]
                for profile, fn in attempts:
                    try:
                        module_name, names, image = fn()
                    except Exception as e:  # noqa: BLE001
                        skipped.append({"source": rel, "profile": profile, "reason": f"{type(e).__name__}: {str(e)[:120]}"})
                        continue
                    key = (module_name, tuple(names), image)
                    if key in seen:
                        continue
                    seen.add(key)
                    cases.append({"id": f"corpus/{rel}#{profile}", "kind": "corpus", "source": rel,
                                  "profile": profile, "image": image, "names": names, "module": module_name})
    return cases, skipped


# --------------------------------------------------------------------------
# Systematic mutants
# --------------------------------------------------------------------------

INT_MIN, INT_MAX = -(1 << 31), (1 << 31) - 1


def mutation_cases(bms_image: bytes):
    bms = table(bms_image)
    out = []

    def add(cid, tab, names=None, module="MutantModule"):
        out.append({"id": cid, "kind": "mut", "image": pack_image(tab), "names": names, "module": module})

    # A. field sweeps
    for op in (0, 1, 2, 3, 4, 5, 6, 7, 8, 0x7F, 0xFF):
        add(f"mut/pred-op/{op:02x}", put(bms, 0, pred_opcode=op))
    for op in (0, 1, 2, 3, 4, 5, 6, 0x7F, 0xFF):
        add(f"mut/act-op/c2/{op:02x}", put(bms, 2, action_opcode=op))
    for op in (1, 2, 3, 4):
        add(f"mut/act-op/c0/{op:02x}", put(put(bms, 0, action_opcode=op), 0, operand_val=7))
    for g in range(0x20):
        add(f"mut/guard/c1/{g:02x}", put(bms, 1, guard_flags=g))
    for g in (0x20, 0x40, 0x80, 0xE0, 0xFF):
        add(f"mut/guard/c1/{g:02x}", put(bms, 1, guard_flags=g | 0x13))
    for hz in (0, 1, 100, 127, 128, 255):
        add(f"mut/hazard/c0/{hz:02x}", put(bms, 0, hazard_limit=hz, guard_flags=0x17))

    # B. operand sweeps
    operands = (0, 1, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, 0x80007FFF, 0x7FFF8000)
    for pred in range(1, 7):
        for operand in operands:
            add(f"mut/operand/p{pred}/{operand:08x}", put(put(bms, 0, pred_opcode=pred), 0, operand_val=operand))
    for act in (3, 4):
        for operand in (0, 1, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF):
            add(f"mut/act-operand/a{act}/{operand:08x}",
                put(put(put(bms, 2, action_opcode=act), 2, operand_val=operand), 2, current_state=INT_MAX & M))

    # C. topology
    add("mut/topo/cycle2", put(bms, 1, subscriber_cid=0))
    add("mut/topo/cycle4", put(bms, 3, subscriber_cid=0, guard_flags=0x1B))
    add("mut/topo/self-loop-c0", put(bms, 0, subscriber_cid=0, guard_flags=0x13))
    add("mut/topo/self-loop-c5", put(bms, 5, subscriber_cid=5, guard_flags=0x13, action_opcode=1))
    for sub in (64, 65, 100, 255, 256, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF):
        add(f"mut/topo/oor-sub/{sub:08x}", put(bms, 3, subscriber_cid=sub))
    add("mut/topo/fan-in", put(put(bms, 1, subscriber_cid=3), 2, current_state=2, subscriber_cid=3))
    add("mut/topo/edge-from-unconfigured", put(bms, 7, subscriber_cid=3))
    add("mut/topo/zero-edge-via-flag", put(bms, 8, guard_flags=0x10, subscriber_cid=0))
    add("mut/topo/empty-image", [mk(c) for c in range(64)])
    add("mut/topo/only-slot63", [mk(c) for c in range(63)] + [mk(63, guard=0x03, pred=0, act=1)])
    add("mut/topo/all-independent", [mk(c, guard=0x03, act=1) for c in range(64)])
    tmpl = dict(guard=0x13, act=1)
    add("mut/topo/chain64", [mk(c, sub=c + 1 if c < 63 else 0, **({**tmpl, "guard": 0x13} if c < 63 else {"guard": 0x03, "act": 1})) for c in range(64)])
    add("mut/topo/chain64-reversed", [mk(c, sub=c - 1 if c > 0 else 0, **({**tmpl} if c > 0 else {"guard": 0x03, "act": 1})) for c in range(64)])
    add("mut/topo/two-chains-merge", [
        mk(0, sub=2, **tmpl), mk(1, sub=2, **tmpl), mk(2, sub=5, **tmpl), mk(3, sub=4, **tmpl),
        mk(4, sub=5, **tmpl), mk(5, guard=0x03, act=1), *[mk(c) for c in range(6, 64)]])
    sparse = [mk(c) for c in range(64)]
    sparse[40], sparse[60], sparse[63] = mk(40, sub=60, **tmpl), mk(60, sub=63, **tmpl), mk(63, guard=0x03, act=1)
    add("mut/topo/sparse-high-chain", sparse)

    # D. initial states
    for st in (-1, INT_MIN, INT_MAX, 1, 0x12345678):
        add(f"mut/init/c1/{st & M:08x}", put(bms, 1, current_state=st & M))
    add("mut/init/negative-active-c0", put(bms, 0, current_state=INT_MIN & M))

    # E. seeded random mutations
    rng = random.Random(0x270)
    bases = [bms, table(pack_image([mk(0, state=5, guard=0x13, act=1, sub=1, pred=3, operand=2),
                                    mk(1, guard=0x1B, act=2, sub=2, pred=4, operand=100, state=3),
                                    mk(2, guard=0x0B, act=0, pred=5, operand=0x00640001),
                                    *[mk(c) for c in range(3, 64)]]))]
    pools = {
        "operand": [0, 1, 2, 5, 50, 100, 5000, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, 0x00640001, 0x7FFF8000],
        "state": [0, 1, 2, 10, INT_MAX, INT_MIN & M, 0xFFFFFFFF, 123456],
    }
    for i in range(120):
        tab = list(rng.choice(bases))
        for _ in range(rng.randint(1, 4)):
            cid = rng.choice([0, 0, 1, 1, 2, 2, 3, 4, 5, 9, 63])
            field = rng.choice(["pred_opcode", "action_opcode", "guard_flags", "hazard_limit",
                                "operand_val", "current_state", "subscriber_cid"])
            if field == "pred_opcode":
                val = rng.choice([0, 1, 2, 3, 4, 5, 6, 6, 7, 0xFF])
            elif field == "action_opcode":
                val = rng.choice([0, 1, 2, 3, 4, 4, 5, 0xFF])
            elif field == "guard_flags":
                val = rng.choice([0x03, 0x13, 0x1B, 0x0B, 0x17, 0x1F, 0x01, 0x02, 0x10, 0x00, rng.randrange(256)])
            elif field == "hazard_limit":
                val = rng.choice([0, 0, 1, 50, 255])
            elif field == "operand_val":
                val = rng.choice(pools["operand"])
            elif field == "current_state":
                val = rng.choice(pools["state"])
            elif rng.random() < 0.95:
                val = rng.choice([0, 1, 2, 3, cid + 1, cid + 2, 5, 9, 63, rng.randrange(64), rng.randrange(64)])
            else:
                val = rng.choice([64, 0xFFFFFFFF])
            tab[cid] = replace(tab[cid], **{field: val})
        add(f"mut/random/{i:03d}", tab, names=[f"Node{j}" for j in range(rng.randint(0, 6))])
    return out


def name_cases(bms_image: bytes):
    out = []
    names_pool = [
        "Cell Voltage", "  padded  ", "9lives", "", "   ", "a-b.c", "Temperatura_Ґ", "emoji😀x",
        "tab\tx", "nl\nx", "x" * 70, "_already", "A\u00a0B", "A\u2003B", "A\u180eB", "A\u200bB", "\x1fz\x1f",
        "ǅ", "ÀB", "Ⅷ", "٣٤", "end ",
    ]
    for i, nm in enumerate(names_pool):
        names = ["Alpha", nm, "Gamma", nm]
        out.append({"id": f"name/seq/{i:02d}", "kind": "name", "image": bms_image, "names": names,
                    "module": "BmsSafetyCascade"})
    out.append({"id": "name/none", "kind": "name", "image": bms_image, "names": None, "module": "BmsSafetyCascade"})
    out.append({"id": "name/too-many", "kind": "name", "image": bms_image,
                "names": [f"N{i}" for i in range(80)], "module": "M"})
    out.append({"id": "name/empty-entries", "kind": "name", "image": bms_image,
                "names": ["", "B", "", ""], "module": "M"})
    for i, mod in enumerate(["BmsSafetyCascade", "my module-1", "1abc", "  ", "модуль", "a\"b\\c", "x\ty", "км😀"]):
        out.append({"id": f"name/module/{i:02d}", "kind": "name", "image": bms_image, "names": None, "module": mod})
    out.append({"id": "name/map", "kind": "name", "image": bms_image, "name_map": {"0": "Zero", "2": "Two", "63": "Last", "99": "Ghost"},
                "names": None, "module": "MapModule"})
    return out


def shape_cases(bms_image: bytes):
    out = []
    for n in (0, 1, 1023, 1025):
        out.append({"id": f"shape/image-len/{n}", "kind": "shape", "image_len": n, "names": None, "module": "M"})
    tab = table(bms_image)

    def dl(ds):
        return [[d.cid, d.name, d.current_state, d.operand_val, d.pred_opcode, d.guard_flags,
                 d.hazard_limit, d.action_opcode, d.subscriber_cid] for d in ds]

    out.append({"id": "shape/seq/duplicate-cid", "kind": "shape", "desc_list": dl([tab[0], tab[0]]), "names": None, "module": "M"})
    out.append({"id": "shape/seq/cid-64", "kind": "shape", "desc_list": dl([replace(tab[0], cid=64)]), "names": None, "module": "M"})
    out.append({"id": "shape/seq/cid-negative", "kind": "shape", "desc_list": dl([replace(tab[0], cid=-1)]), "names": None, "module": "M"})
    out.append({"id": "shape/seq/over-64", "kind": "shape", "desc_list": dl(tab + [tab[0]]), "names": None, "module": "M"})
    out.append({"id": "shape/seq/sparse-bms", "kind": "shape", "desc_list": dl(tab[:4]), "names": ["A", "B", "C", "D"], "module": "Sparse"})
    out.append({"id": "shape/seq/empty", "kind": "shape", "desc_list": [], "names": None, "module": "Empty"})
    out.append({"id": "shape/seq/own-names", "kind": "shape",
                "desc_list": dl([replace(tab[0], name="own name!"), replace(tab[1], name="")]), "names": None, "module": "Own"})
    return out


def unverified_cases(bms_image: bytes):
    """require_z3_verified=False: emission proceeds although the table is unsafe."""
    tab = table(bms_image)
    variants = {
        "cycle2": put(tab, 1, subscriber_cid=0),
        "self-loop": put(tab, 0, subscriber_cid=0, guard_flags=0x13),
        "oor-subscriber": put(tab, 3, subscriber_cid=64),
        "invariant-disabled": put(tab, 2, guard_flags=tab[2].guard_flags & ~0x02),
        "bad-opcodes": put(put(tab, 0, pred_opcode=9), 2, action_opcode=9),
        "safe-table": tab,
    }
    return [{"id": f"unverified/{k}", "kind": "unverified", "image": pack_image(v), "names": None,
             "module": "Unverified", "allow_unverified": True} for k, v in variants.items()]


def descs_from_case(case):
    if "desc_list" in case:
        return [kr.ConceptMicroDescriptor(cid=c, name=n, current_state=s, operand_val=o, pred_opcode=p,
                                          guard_flags=g, hazard_limit=h, action_opcode=a, subscriber_cid=sub)
                for c, n, s, o, p, g, h, a, sub in case["desc_list"]]
    return None


def case_input(case):
    if "desc_list" in case:
        return descs_from_case(case)
    if "image_len" in case:
        return bytes(case["image_len"])
    return case["image"]


def evaluate(case, index):
    src = case_input(case)
    names = case.get("name_map") and {int(k): v for k, v in case["name_map"].items()} or case.get("names")
    module = case["module"]
    allow = case.get("allow_unverified", False)
    text, emit = run_emit(src, names, module, allow)
    cert_text, cert = run_cert(src, names, module, text)
    rec = {"id": case["id"], "kind": case["kind"], "module": module}
    if allow:
        rec["allow_unverified"] = True
    for key in ("source", "profile"):
        if key in case:
            rec[key] = case[key]
    if "name_map" in case:
        rec["name_map"] = case["name_map"]
    if case.get("names") is not None:
        rec["names"] = case["names"]
    if "desc_list" in case:
        rec["desc_list"] = case["desc_list"]
    elif "image_len" in case:
        rec["image_len"] = case["image_len"]
    else:
        rec["slots"] = slots_of(case["image"])
    if emit["ok"] and case["kind"] in FULL_TEXT_KINDS:
        emit["c99"] = text
    if cert["ok"] and case["kind"] in FULL_TEXT_KINDS:
        cert["json"] = cert_text
    rec["emit"], rec["cert"] = emit, cert
    return rec, text


# --------------------------------------------------------------------------
# C99 source mutants (certificate negative controls)
# --------------------------------------------------------------------------

def row_line(text: str, cid: int) -> str:
    m = re.search(r"^    \{[^\n]*\} /\* CID %02d: [^\n]* \*/$" % cid, text, re.M)
    if not m:
        m = re.search(r"^    \{[^\n]*\},? /\* CID %02d: [^\n]* \*/$" % cid, text, re.M)
    assert m, cid
    return m.group(0)


def source_mutants(text: str):
    """(id, old, new) replacement triples (each `old` occurs exactly once)."""
    inv = "invariant_true   = (!arith_overflow) && ((cand_u32 & 0x80000000u) == 0u);"
    muts = [
        ("m1-invariant-true", inv, "invariant_true   = true; (void)arith_overflow;"),
        ("m1-drop-overflow", inv, "invariant_true   = ((cand_u32 & 0x80000000u) == 0u);"),
        ("m1-drop-nonneg", inv, "invariant_true   = (!arith_overflow);"),
        ("m1-commit-drops-invariant", "invariant_known && invariant_true &&", "invariant_known &&"),
        ("m2-fault-gate-off", "if ((!ev_param_valid) || (!concept_valid)) {", "if (false && ((!ev_param_valid) || (!concept_valid))) {"),
        ("m2-fault-gate-param-only", "if ((!ev_param_valid) || (!concept_valid)) {", "if (!ev_param_valid) {"),
        ("m3-topo-reversed", "uint8_t cid = KM_SAFETY_TOPO_ORDER[topo_idx];",
         "uint8_t cid = KM_SAFETY_TOPO_ORDER[(KM_SAFETY_NUM_ACTIVE_TOPO - 1u) - topo_idx];"),
        ("m3-topo-swapped", "= {\n    0u, 1u, 2u, 3u\n};", "= {\n    1u, 0u, 2u, 3u\n};"),
        ("m3-topo-too-short", "= {\n    0u, 1u, 2u, 3u\n};", "= {\n    0u, 1u, 2u\n};"),
        ("m3-topo-duplicate", "= {\n    0u, 1u, 2u, 3u\n};", "= {\n    0u, 1u, 2u, 3u, 3u\n};"),
        ("m3-topo-hex", "= {\n    0u, 1u, 2u, 3u\n};", "= {\n    0x0u, 0x1u, 0x02u, 0X3u\n};"),
        ("m4-gt-ge", "case KM_CME_PRED_GT:\n            pred_raw = (ev_param > op_i32);",
         "case KM_CME_PRED_GT:\n            pred_raw = (ev_param >= op_i32);"),
        ("m4-gt-eq", "case KM_CME_PRED_GT:\n            pred_raw = (ev_param > op_i32);",
         "case KM_CME_PRED_GT:\n            pred_raw = (ev_param == op_i32);"),
        ("m4-lt-le", "case KM_CME_PRED_LT:\n            pred_raw = (ev_param < op_i32);",
         "case KM_CME_PRED_LT:\n            pred_raw = (ev_param <= op_i32);"),
        ("m4-lt-gt", "case KM_CME_PRED_LT:\n            pred_raw = (ev_param < op_i32);",
         "case KM_CME_PRED_LT:\n            pred_raw = (ev_param > op_i32);"),
        ("m4-eq-ne", "pred_raw = (param_u32 == d->operand);", "pred_raw = (param_u32 != d->operand);"),
        ("m4-neq-eq", "pred_raw = (param_u32 != d->operand);", "pred_raw = (param_u32 == d->operand);"),
        ("m4-range-lo-zext", "int32_t lo_i32 = km_u16_to_i32_sext((uint16_t)(d->operand & 0xFFFFu));",
         "int32_t lo_i32 = (int32_t)(uint16_t)(d->operand & 0xFFFFu);"),
        ("m4-range-hi-zext", "int32_t hi_i32 = km_u16_to_i32_sext((uint16_t)((d->operand >> 16) & 0xFFFFu));",
         "int32_t hi_i32 = (int32_t)(uint16_t)((d->operand >> 16) & 0xFFFFu);"),
        ("m4-range-lo-strict", "(ev_param >= lo_i32)", "(ev_param > lo_i32)"),
        ("m4-range-hi-strict", "(ev_param <= hi_i32)", "(ev_param < hi_i32)"),
        ("m4-inc-minus", "cand_u32       = cur_u32 + 1u;", "cand_u32       = cur_u32 - 1u;"),
        ("m4-dec-plus", "cand_u32       = cur_u32 - 1u;", "cand_u32       = cur_u32 + 1u;"),
        ("m4-add-minus", "cand_u32       = cur_u32 + d->operand;", "cand_u32       = cur_u32 - d->operand;"),
        ("m4-sub-plus", "cand_u32       = cur_u32 - d->operand;", "cand_u32       = cur_u32 + d->operand;"),
        ("m4-sub-overflow-eq", "arith_overflow = (((cur_u32 ^ d->operand) & 0x80000000u) != 0u) &&",
         "arith_overflow = (((cur_u32 ^ d->operand) & 0x80000000u) == 0u) &&"),
        ("m4-no-self-suppress", "if (target_cid != cid) {", "if (true) {"),
        ("m4-table-row-sub", row_line(text, 2), row_line(text, 2).replace("3u }", "0u }")),
        ("m4-table-row-guard", row_line(text, 1), row_line(text, 1).replace("0x1Bu", "0x19u")),
        ("m4-table-row-init-neg", row_line(text, 1), re.sub(r"\{ 0,", "{ -5,", row_line(text, 1), count=1)),
        ("m4-table-row-intmin", row_line(text, 1), re.sub(r"\{ 0,", "{ (-2147483647 - 1),", row_line(text, 1), count=1)),
        ("m4-table-row-unused-slot", row_line(text, 20), row_line(text, 20).replace("{ 0, 0x00000000u, 0x00u, 0x00u, 0x00u, 0x00u, 0u }", "{ 0, 0x00000000u, 0x00u, 0x00u, 0x00u, 0x00u, 7u }")),
        ("m4-table-row-hex-literals", row_line(text, 1), row_line(text, 1).replace("0x00000001u", "0x1").replace("0x04u", "4u")),
        ("m4-table-row-huge-init", row_line(text, 1), re.sub(r"\{ 0,", "{ 99999999999999999999,", row_line(text, 1), count=1)),
        ("p-no-topo-array", "static const uint8_t KM_SAFETY_TOPO_ORDER[", "static const uint8_t KM_SAFETY_TOPO_ORDERX["),
        ("p-loop-indexing", "uint8_t cid = KM_SAFETY_TOPO_ORDER[topo_idx];", "uint8_t cid = KM_SAFETY_TOPO_ORDER[topo_idx + 0u];"),
        ("p-no-desc-table", "KM_SAFETY_DESCRIPTORS[KM_SAFETY_NUM_CONCEPTS] = {", "KM_SAFETY_DESCRIPTORX[KM_SAFETY_NUM_CONCEPTS] = {"),
        ("p-63-rows", row_line(text, 63) + "\n};", "};"),
        ("p-65-rows", row_line(text, 63) + "\n};", row_line(text, 63) + ",\n    { 0, 0x00000000u, 0x00u, 0x00u, 0x00u, 0x00u, 0u }\n};"),
        ("p-leading-zero-topo", "= {\n    0u, 1u, 2u, 3u\n};", "= {\n    0u, 01u, 2u, 3u\n};"),
        ("p-leading-zero-row", row_line(text, 1), row_line(text, 1).replace("0x00000001u", "00123u")),
        ("p-no-pred-gt", "case KM_CME_PRED_GT:", "case KM_CME_PRED_GX:"),
        ("p-no-pred-eq", "case KM_CME_PRED_EQ:", "case KM_CME_PRED_EX:"),
        ("p-no-range", "pred_raw = (ev_param >= lo_i32) && (ev_param <= hi_i32);", "pred_raw = true;"),
        ("p-no-act-add", "case KM_CME_ACT_ADD:", "case KM_CME_ACT_ADX:"),
        ("p-no-act-sub-overflow", "arith_overflow = (((cur_u32 ^ d->operand) & 0x80000000u) != 0u) &&", "arith_overflow = (((cur_u32 ^ d->operand) & 0x80000000u) > 0u) &&"),
        ("p-one-invariant", "invariant_true   = (!arith_overflow) && ((cand_u32 & 0x80000000u) == 0u);", "invariant_x      = (!arith_overflow) && ((cand_u32 & 0x80000000u) == 0u);"),
        ("p-one-commit", "commit = action_valid &&", "commix = action_valid &&"),
        ("p-blank-source", None, " "),
    ]
    return muts


def apply_mut(text, old, new):
    if old is None:
        return new
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new, 1)


def cert_mutant_cases(bases):
    """bases: list of (tag, image, names, module); returns records."""
    out = []
    for tag, image, names, module in bases:
        text = ce.emit_c99_safety_module(image, module_name=module, concept_names=names)
        for mid, old, new in source_mutants(text):
            if old is not None and (text.count(old) != 1 or new == old):
                continue  # base-specific mutant that does not apply to this module
            mutated = apply_mut(text, old, new)
            cert_text, cert = run_cert(image, names, module, mutated)
            rec = {"id": f"cmut/{tag}/{mid}", "kind": "cmut", "base": tag, "slots": slots_of(image),
                   "module": module, "names": names, "old": old, "new": new,
                   "parse": parsed_summary(mutated), "cert": cert}
            if cert["ok"] and tag == "bms" and mid in FULL_JSON_MUTANTS:
                cert["json"] = cert_text
            out.append(rec)
    return out


# --------------------------------------------------------------------------
# Engine traces
# --------------------------------------------------------------------------

def gen_events(tab, rng, n=48):
    configured = [d.cid for d in tab if ce.is_descriptor_configured(d)] or [0]
    params = [0, 1, -1, 2, 5, 50, 100, 120, 150, 180, 250, 5000, INT_MAX, INT_MIN]
    for d in tab:
        if ce.is_descriptor_configured(d):
            op = ce._to_i32(d.operand_val)
            params += [op, op - 1 if op > INT_MIN else op, op + 1 if op < INT_MAX else op, d.hazard_limit,
                       d.hazard_limit + 1, ce._to_i16(d.operand_val & 0xFFFF), ce._to_i16((d.operand_val >> 16) & 0xFFFF)]
    events = []
    for _ in range(n):
        r = rng.random()
        cid = rng.choice(configured) if rng.random() < 0.8 else rng.choice([rng.randrange(64), 64, 99, -1, 255])
        if r < 0.82:
            events.append(["s", cid, rng.choice(params), rng.random() < 0.88])
        elif r < 0.91:
            events.append(["i", cid, 0, True])
        else:
            events.append(["r", cid, rng.choice([0, 1, 2, 7, -1, 100, INT_MAX]), True])
    return events


def run_engine(image, events):
    eng = ce.ReferenceCmeSafetyEngine(image)
    h = hashlib.sha256()
    results = []
    for op, cid, param, valid in events:
        if op == "s":
            r = eng.step_event(cid, param, valid)
            results.append([r.steps_executed, r.commits, r.rejects, int(r.fault_propagated), r.last_state, r.status])
        elif op == "i":
            eng.invalidate_concept(cid)
        else:
            eng.revalidate_concept(cid, param)
        h.update((",".join(map(str, eng.state)) + f"|{eng.valid_mask}|{eng.events_processed},{eng.commits},"
                  f"{eng.rejects},{eng.fault_propagations},{eng.last_committed_state}\n").encode())
    return results, h.hexdigest(), {
        "state": eng.state, "valid_mask": eng.valid_mask, "counters": [eng.events_processed, eng.commits, eng.rejects,
                                                                       eng.fault_propagations, eng.last_committed_state],
    }


def engine_cases(records_with_images):
    rng = random.Random(0xC99)
    out = []
    for rec, image in records_with_images:
        try:
            ce.ReferenceCmeSafetyEngine(image)
        except Exception:  # noqa: BLE001 - cyclic / invalid tables have no engine
            continue
        events = gen_events(table(image), rng)
        results, digest, final = run_engine(image, events)
        out.append({"id": rec["id"], "slots": slots_of(image), "events": events, "results": results,
                    "digest": digest, "final": final})
    return out


def pyspace_codepoints():
    return [cp for cp in range(0x110000) if chr(cp).isspace() and not 0xD800 <= cp < 0xE000]


def sanitize_vectors():
    samples = ["", " ", "abc", "a b", "9", "_9", "é", "ab\u00a0", "\x1fabc\x1c", "\u180eabc", "日本", "😀", "A-Z_a-z0-9",
               "\u2028x\u2029", "x\x85", "\v\fabc\r\n", "0x1", "Ünïcödé 9"]
    return [[s, ce._sanitize_c_ident(s, "FALLBACK")] for s in samples]


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "c99_golden.json.gz"
    bms_image = (ENG / "validation/kpol-cme/c99-emitter-270/bms_safety_cascade.bin").read_bytes()

    corpus, skipped = corpus_cases()
    cases = (corpus + mutation_cases(bms_image) + name_cases(bms_image) + shape_cases(bms_image)
             + unverified_cases(bms_image))
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate case ids"

    records, images = [], []
    for i, case in enumerate(cases):
        rec, _ = evaluate(case, i)
        records.append(rec)
        if "image" in case:
            images.append((rec, case["image"]))

    chain8 = pack_image([mk(c, sub=c + 1 if c < 7 else 0, guard=0x13 if c < 7 else 0x03, act=1, pred=0, state=c)
                         for c in range(8)] + [mk(c) for c in range(8, 64)])
    bases = [
        ("bms", bms_image, ["Cell_Delta_mV", "Module_Thermal_Guard", "Pack_Fault_Latch", "Contactor_Interlock"], "BmsSafetyCascade"),
        ("chain8", chain8, None, "Chain8"),
    ]
    cmuts = cert_mutant_cases(bases)

    # The sample emit cases reused as engine traces: corpus + every 3rd mutant.
    pick = [(r, img) for k, (r, img) in enumerate(images) if r["kind"] == "corpus" or k % 3 == 0]
    engines = engine_cases(pick)

    z3_version = subprocess.run(["z3", "--version"], capture_output=True, text=True, check=True).stdout.strip()
    meta = {
        "generator": "Engineering/sw/kpol-go/testdata/gen_c99_golden.py",
        "reference": "Engineering/sw/kpol-ref/c99_emitter.py",
        "z3_cli": z3_version,
        "solver_placeholder": SOLVER_PLACEHOLDER,
        "counts": {"emit_cases": len(records), "emit_ok": sum(r["emit"]["ok"] for r in records),
                   "cert_ok": sum(r["cert"]["ok"] for r in records), "cert_mutants": len(cmuts),
                   "engine_cases": len(engines), "corpus": len(corpus), "skipped_corpus": len(skipped)},
        "skipped": skipped,
    }
    doc = {"meta": meta, "pyspace": pyspace_codepoints(), "sanitize": sanitize_vectors()}

    def dump(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

    with goldenio.open_gz_text(out_path) as f:
        f.write("{\n")
        keys = ["meta", "pyspace", "sanitize"]
        for k in keys:
            f.write(f'"{k}":{dump(doc[k])},\n')
        for k, rows in (("emit_cases", records), ("cert_mutants", cmuts), ("engine_cases", engines)):
            f.write(f'"{k}":[\n')
            f.write(",\n".join(dump(r) for r in rows))
            f.write("\n]" + ("," if k != "engine_cases" else "") + "\n")
        f.write("}\n")
    print(json.dumps(meta["counts"]), file=sys.stderr)


if __name__ == "__main__":
    main()
