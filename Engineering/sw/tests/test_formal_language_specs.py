"""Keep the formal KPOL/EKPOL/KPOL-AUTH specifications consistent with the reference implementations.

The checks cover the normative documents in Engineering/specifications/kpol.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import re
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SW_REF_DIR = REPO_ROOT / "Engineering" / "sw" / "kpol-ref"
if str(SW_REF_DIR) not in sys.path:
    sys.path.insert(0, str(SW_REF_DIR))

import ekpol_frontend as ef  # noqa: E402
import kpol_reference as kr  # noqa: E402

SPECS = REPO_ROOT / "Engineering" / "specifications" / "kpol"
EXAMPLES = REPO_ROOT / "Engineering" / "sw" / "vmk-go" / "examples"
KPOL_SPEC = (SPECS / "kpol-formal-specification.md").read_text(encoding="utf-8")
EKPOL_SPEC = (SPECS / "ekpol-formal-specification.md").read_text(encoding="utf-8")
KPOL_AUTH_SPEC = (SPECS / "kpol-auth-formal-specification.md").read_text(encoding="utf-8")

VECTOR_ROW = re.compile(r"\| \[`(?P<file>[a-z0-9_]+\.e?kpol)`\]\([^)]*\) \| `?(?P<profile>[A-Z0-9-]+)`? \| `(?P<sha>[0-9a-f]{64})`")


def _vectors(spec: str) -> list[tuple[str, str, str]]:
    rows = [(m["file"], m["profile"], m["sha"]) for m in VECTOR_ROW.finditer(spec)]
    assert len(rows) == 4, rows
    return rows


@pytest.mark.parametrize("name, profile, sha", _vectors(KPOL_SPEC))
def test_kpol_spec_annex_a_vectors_match_reference_compiler(name, profile, sha):
    module = kr.parse_module((EXAMPLES / name).read_text(encoding="utf-8"))
    image = kr.compile_concept_microcode_bram_image(module, profile=profile)
    assert hashlib.sha256(image).hexdigest() == sha


@pytest.mark.parametrize("name, profile, sha", _vectors(EKPOL_SPEC))
def test_ekpol_spec_annex_a_vectors_match_reference_compiler(name, profile, sha):
    assert profile == "B64"
    image = ef.compile_ekpol_to_bram_image((EXAMPLES / name).read_text(encoding="utf-8"))
    assert hashlib.sha256(image).hexdigest() == sha


def test_kpol_spec_reserved_words_match_parser():
    block = re.search(r"\*\*KPOL-LEX-5.*?```text\n(.*?)```", KPOL_SPEC, re.S)
    assert block, "KPOL-LEX-5 keyword block not found"
    assert set(block.group(1).split()) == kr.Parser._reserved


def test_kpol_spec_lexical_and_semantic_corner_cases():
    # KPOL-LEX-3: alias tokens are recognised before single-character operators.
    assert [t.kind for t in kr.tokenize("a<-1")][:3] == ["ID", "ALIAS_WRITE", "NUMBER"]
    # KPOL-SYN-5: unary binds tighter than comparison.
    src = ("Problem M { Invariants { I: x >= 0; } }\n"
           "Solution M { state x: Int32 = 0; event Ev(p: Int32); rule R on Ev when not p == 1 { set x := x + 1; } }")
    with pytest.raises(kr.KpolError, match="not requires Bool"):
        kr.parse_module(src)
    # KPOL-DYN-3: equality with Unknown is definitional, ordering is Unknown.
    unknown = kr.Literal(kr.UNKNOWN)
    assert kr._eval(kr.Binary("==", unknown, unknown), {}) is True
    assert kr._eval(kr.Binary("==", unknown, kr.Literal(5)), {}) is False
    assert kr._eval(kr.Binary("<", unknown, kr.Literal(5)), {}) is kr.UNKNOWN


def test_ekpol_spec_layout_and_b64_corner_cases():
    # EKPOL-SEG-2: "=>" closes the statement, so the action must stay on the same line.
    with pytest.raises(ef.EkpolError) as err:
        ef.parse_ekpol("concept C: i32 = 0 [>= 0] {\n on write(x) when x > 1 =>\n C += 1 commit;\n}")
    assert err.value.code == "EKPOL-SYNTAX-ERR"
    # EKPOL-SYN-5: whitespace is required after "::".
    with pytest.raises(ef.EkpolError):
        ef.parse_ekpol("concept C: i32 = 0 [>= 0] { <- x ::x > 1 => C += 1 . }")
    # D-E8: extra invariant clauses are accepted but not lowered into hazard_limit.
    image = ef.compile_ekpol_to_bram_image(
        "concept C: i32 = 0 [>= 0, <= 200] { on write(x) => C += 1 commit; }\n"
        "test T { send C(1); expect C == 1; }"
    )
    assert image[8:12] == bytes([0x00, 0x03, 0x00, 0x01])
    # EKPOL-B64-20: a single concept without a test is cross-checked against KPOL-CME-1.
    with pytest.raises(ef.EkpolError) as err:
        ef.compile_ekpol_to_bram_image("concept C: i32 = 0 [>= 0] { on write(x) when x >= 5 => C += 1 commit; }")
    assert err.value.code == "EKPOL-PROOF-ERR"


def _kpol_auth():
    if "kpol_auth" in sys.modules:
        return sys.modules["kpol_auth"]
    pkg = REPO_ROOT / "Engineering" / "sw" / "kpol-auth"
    spec = importlib.util.spec_from_file_location(
        "kpol_auth", pkg / "__init__.py", submodule_search_locations=[str(pkg)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["kpol_auth"] = module
    spec.loader.exec_module(module)
    return module


def _auth_verdict(source):
    ka = _kpol_auth()
    try:
        artifact = ka.lower_document(source)
    except ka.KpolAuthError as err:
        return err.diagnostic.code
    except ka.KpolAuthLoweringError as err:
        return err.code
    return artifact


def test_kpol_auth_spec_annex_a1_matches_author_corpus():
    ka = _kpol_auth()
    rows = re.findall(r"\| `(EX-\d\d)` \| `(.*?)` \| (прийнято|відхилено) \| (.*?) \|", KPOL_AUTH_SPEC)
    corpus = {ex.id: ex for ex in ka.AUTHOR_CORPUS}
    assert [r[0] for r in rows] == sorted(corpus)
    for ex_id, source, verdict, detail in rows:
        assert source == corpus[ex_id].source_text
        try:
            ka.parse_kpol_auth(source)
        except ka.KpolAuthError as err:
            assert verdict == "відхилено" and err.diagnostic.code in detail, ex_id
        else:
            assert verdict == "прийнято", ex_id


def test_kpol_auth_spec_annex_a2_lowering_vectors():
    rows = re.findall(r"\| `(Concept\(.*?)` \| `([0-9A-F ]+)` \| `([0-9a-f]{64})` \|", KPOL_AUTH_SPEC)
    assert len(rows) == 3
    for source, code, sha in rows:
        artifact = _auth_verdict(source)
        assert " ".join(f"{w:08X}" for w in artifact.code_o) == code
        assert hashlib.sha256(artifact.bram_image).hexdigest() == sha
    negatives = re.findall(r"`(Concept\([^`]*)` → `(KPOL-[A-Z0-9-]+)`", KPOL_AUTH_SPEC)
    assert len(negatives) == 4
    for source, code in negatives:
        assert _auth_verdict(source) == code


def test_kpol_auth_spec_syntax_and_lowering_corner_cases():
    ka = _kpol_auth()
    # KPA-SYN-3: one precedence level, left-associative.
    expr = ka.parse_kpol_auth("A + B * C").items[0]
    assert expr.op_token.value == "*" and expr.left.op_token.value == "+"
    # KPA-SYN-4: ":=" after a subscription chain starts a new statement.
    assert _auth_verdict("A • B := C") == "KPOL-AUTH-SYNTAX-01"
    # KPA-CST-4: effective bounds are [Min, Max + 1]; Count is checked against bounds seen before it.
    bounds = ka.parse_kpol_auth("A[Max=15, Count=5]").items[0]
    assert (bounds.min_effective, bounds.max_effective) == (1, 16)
    assert _auth_verdict("A[Count=5, Max=15]") == "KPOL-AUTH-U02"
    # KPA-LEX-8: author addressing signs have no linear notation.
    for sign in ("←", "→", "¤", "'", "|", "~"):
        assert _auth_verdict(sign) == "KPOL-AUTH-LEX-01"
    # KPA-L-15 / D-A9: the routing image never sets ASSUMPTION_EN (guard bit 0).
    image = _auth_verdict("Concept(A, 0, Lower=0) Concept(B, 0) A • Assign(B, 1)").bram_image
    assert all(image[16 * k + 9] & 0x01 == 0 for k in range(64))
