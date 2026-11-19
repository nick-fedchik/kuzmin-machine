"""Keep the formal KPOL/EKPOL specifications consistent with the reference implementations.

Each check fails if a normative statement in `Engineering/guides/*-formal-specification.md`
drifts from `kpol_reference.py` / `ekpol_frontend.py`.
"""

from __future__ import annotations

import hashlib
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

GUIDES = REPO_ROOT / "Engineering" / "guides"
EXAMPLES = REPO_ROOT / "Engineering" / "sw" / "vmk-go" / "examples"
KPOL_SPEC = (GUIDES / "kpol-formal-specification.md").read_text(encoding="utf-8")
EKPOL_SPEC = (GUIDES / "ekpol-formal-specification.md").read_text(encoding="utf-8")

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
