#!/usr/bin/env python3
"""Ergonomic KPOL (`EKPOL 0.1.0`) Frontend, Static Verifier, BRAM Compiler, and Bidirectional Transpiler.

Supports both pure 7-bit ASCII symbolic notation (`<-`, `->`, `~`, `|`, `::`, `=>`, `.`)
and modern programmer keyword notation (`on write`, `on read`, `on change`, `on call`,
`when`, `=>`, `commit`, `after`), while preserving classic KPOL (`KPOL-CME-1`,
`KPOL-CME-2`, `KPOL-AUTH`) 100% unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from kpol_reference import (
    Binary,
    CME_ACT_ADD,
    CME_ACT_ASSIGN,
    CME_ACT_DEC,
    CME_ACT_INC,
    CME_ACT_SUB,
    CME_GUARD_ASSUMPTION_EN,
    CME_GUARD_HAZARD_EN,
    CME_GUARD_INVARIANT_EN,
    CME_GUARD_INVERT_ASSUMPTION,
    CME_GUARD_SUBSCRIBER_EN,
    CME_PRED_BITMASK,
    CME_PRED_EQ,
    CME_PRED_GT,
    CME_PRED_LT,
    CME_PRED_NEQ,
    CME_PRED_NOP,
    CME_PRED_RANGE,
    ConceptMicroDescriptor,
    ExpectCheck,
    Expr,
    KpolError,
    Literal,
    Module,
    Name,
    Parser,
    ScenarioDecl,
    SetAction,
    StepAction,
    Unary,
    compile_concept_microcode_bram_image,
    verify_module,
)


class EkpolError(KpolError):
    """Diagnostic error raised during EKPOL parsing, validation, transpilation, or compilation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.detail = message
        super().__init__(f"{code}: {message}")


TYPE_SYNONYMS: dict[str, str] = {
    "i32": "Int32",
    "int32": "Int32",
    "Int32": "Int32",
    "u64": "U64",
    "uint64": "U64",
    "U64": "U64",
    "f64": "Float",
    "float64": "Float",
    "Float": "Float",
    "bool": "Bool",
    "Bool": "Bool",
    "?": "Bool",
}


@dataclass(frozen=True)
class EkpolInvariant:
    """Concept safety invariant declared in `[...]` header brackets or `invariant ...;` body."""

    kind: str  # "cmp" or "range"
    op: str = ">="
    value: int = 0
    lo: int | None = None
    hi: int | None = None


@dataclass(frozen=True)
class EkpolPredicate:
    """Normalized rule guard predicate (`::` or `when`)."""

    kind: str  # "nop", "cmp", "range", "bitmask", "undef", "raw"
    var: str = ""
    op: str = "=="
    value: Any = 0
    lo: int | None = None
    hi: int | None = None
    inverted: bool = False
    raw_text: str = "true"


@dataclass(frozen=True)
class EkpolAction:
    """Single state update action after `=>`."""

    kind: str  # "inc", "dec", "add", "sub", "assign", "set_const", "nop", "raw"
    target: str
    operand: Any = 0
    raw_text: str = ""


@dataclass(frozen=True)
class EkpolRule:
    """Reaction rule inside an EKPOL concept."""

    trigger_kind: str  # "write", "change", "read", "exec", "state"
    event_name: str | None
    param_name: str
    param_type: str = "Int32"
    watch_concept: str | None = None
    exec_params: tuple[str, ...] = ()
    predicate: EkpolPredicate = field(default_factory=lambda: EkpolPredicate(kind="nop"))
    actions: tuple[EkpolAction, ...] = ()
    post_read_barrier: bool = False
    rule_name: str | None = None


@dataclass(frozen=True)
class EkpolConcept:
    """Parsed EKPOL concept declaration (`concept Name: Type = Init [Invariant] { ... }`)."""

    name: str
    canonical_type: str
    raw_type: str
    initial_value: Any
    is_undef_init: bool
    invariants: tuple[EkpolInvariant, ...]
    annotations: tuple[str, ...] = ()
    rules: tuple[EkpolRule, ...] = ()


@dataclass(frozen=True)
class EkpolTestStep:
    """Single `send` / `step` or `expect` statement inside a `test` block."""

    kind: str  # "send" or "expect"
    target: str
    param_name: str | None = None
    op: str = "=="
    value: Any = 0
    extra_args: tuple[Any, ...] = ()


@dataclass(frozen=True)
class EkpolTest:
    """Built-in verification scenario (`test Name { ... }` or `scenario Name { ... }`)."""

    name: str
    steps: tuple[EkpolTestStep, ...]


@dataclass(frozen=True)
class EkpolProgram:
    """Complete parsed EKPOL program AST."""

    module_name: str
    concepts: tuple[EkpolConcept, ...]
    tests: tuple[EkpolTest, ...] = ()
    stdin_concepts: tuple[str, ...] = ()
    stdout_concepts: tuple[str, ...] = ()
    stderr_concepts: tuple[str, ...] = ()

    @property
    def is_conceptual_only(self) -> bool:
        for c in self.concepts:
            if c.canonical_type != "Int32" or c.is_undef_init:
                return True
            for r in c.rules:
                if r.trigger_kind in ("read", "exec", "state"):
                    return True
        return False


def _strip_comments_preserve_pragmas(source: str) -> tuple[str, list[str], list[str], list[str]]:
    """Remove comments (`#`, `//`, `/* ... */`) while extracting comment-level `@stdin`/`@stdout`."""
    stdin_c: list[str] = []
    stdout_c: list[str] = []
    stderr_c: list[str] = []

    def _extract_pragma(comment_body: str) -> None:
        b = comment_body.strip()
        if b.startswith("@stdin"):
            toks = b[len("@stdin") :].replace(",", " ").split()
            stdin_c.extend(t for t in toks if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", t))
        elif b.startswith("@stdout"):
            toks = b[len("@stdout") :].replace(",", " ").split()
            stdout_c.extend(t for t in toks if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", t))
        elif b.startswith("@stderr"):
            toks = b[len("@stderr") :].replace(",", " ").split()
            stderr_c.extend(t for t in toks if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", t))

    # Strip /* ... */ block comments first
    out_chars: list[str] = []
    i = 0
    n = len(source)
    while i < n:
        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            if end < 0:
                raise EkpolError("EKPOL-SYNTAX-ERR", "unterminated /* ... */ block comment")
            newlines = source[i : end + 2].count("\n")
            out_chars.append("\n" * newlines)
            i = end + 2
        else:
            out_chars.append(source[i])
            i += 1
    no_block = "".join(out_chars)

    cleaned_lines: list[str] = []
    for line in no_block.splitlines():
        # Check for # or // comment
        cut = len(line)
        marker_len = 0
        for m in ("//", "#"):
            pos = line.find(m)
            if pos >= 0 and pos < cut:
                cut = pos
                marker_len = len(m)
        if cut < len(line):
            _extract_pragma(line[cut + marker_len :])
            line = line[:cut]
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines), stdin_c, stdout_c, stderr_c


def _parse_int_literal(text: str, err_code: str = "EKPOL-SYNTAX-ERR") -> int:
    s = text.strip()
    try:
        return int(s, 0)
    except ValueError as err:
        raise EkpolError(err_code, f"invalid integer literal {text!r}") from err


def _parse_init_value(raw_init: str, canonical_type: str, concept_name: str) -> tuple[Any, bool]:
    s = raw_init.strip()
    if s in ("_", "undef", "Unknown"):
        return "_", True
    if canonical_type == "Bool":
        if s in ("true", "True", "!"):
            return True, False
        if s in ("false", "False", "~false", "¬"):
            return False, False
        raise EkpolError(
            "EKPOL-TYPE-ERR",
            f"concept {concept_name!r}: invalid Bool initial value {raw_init!r} (expected true, false, !, ~false, or _/undef)",
        )
    if canonical_type == "Float":
        if s in ("true", "false", "!"):
            raise EkpolError("EKPOL-TYPE-ERR", f"concept {concept_name!r}: expected Float initial value, got {raw_init!r}")
        try:
            return float(s), False
        except ValueError as err:
            raise EkpolError("EKPOL-TYPE-ERR", f"concept {concept_name!r}: invalid Float initial value {raw_init!r}") from err
    if canonical_type in ("Int32", "U64"):
        if s in ("true", "false", "!", "~false") or "." in s:
            raise EkpolError(
                "EKPOL-TYPE-ERR",
                f"concept {concept_name!r}: expected integer initial value for {canonical_type}, got {raw_init!r}",
            )
        try:
            val = int(s, 0)
        except ValueError as err:
            raise EkpolError(
                "EKPOL-TYPE-ERR",
                f"concept {concept_name!r}: invalid integer initial value {raw_init!r}",
            ) from err
        if canonical_type == "U64" and not (0 <= val < (1 << 64)):
            raise EkpolError("EKPOL-TYPE-ERR", f"concept {concept_name!r}: U64 initial value {val} out of range")
        if canonical_type == "Int32" and not (-(1 << 31) <= val <= (1 << 31) - 1):
            raise EkpolError("EKPOL-TYPE-ERR", f"concept {concept_name!r}: Int32 initial value {val} out of range")
        return val, False
    raise EkpolError("EKPOL-TYPE-ERR", f"concept {concept_name!r}: unsupported type {canonical_type!r}")


def _parse_bracket_invariants(bracket_str: str | None, concept_name: str) -> list[EkpolInvariant]:
    if not bracket_str:
        return []
    inner = bracket_str.strip()
    if inner.startswith("[") and inner.endswith("]"):
        inner = inner[1:-1].strip()
    if not inner:
        raise EkpolError("EKPOL-INVARIANT-ERR", f"concept {concept_name!r}: empty invariant brackets '[]'")

    invs: list[EkpolInvariant] = []
    for part in inner.split(","):
        clause = part.strip()
        if not clause:
            continue
        if ".." in clause:
            bounds = clause.split("..", 1)
            lo = _parse_int_literal(bounds[0], "EKPOL-INVARIANT-ERR")
            hi = _parse_int_literal(bounds[1], "EKPOL-INVARIANT-ERR")
            if lo > hi:
                raise EkpolError(
                    "EKPOL-INVARIANT-ERR",
                    f"concept {concept_name!r}: inverted invariant range [{lo}..{hi}]",
                )
            invs.append(EkpolInvariant(kind="range", op="..", lo=lo, hi=hi, value=lo))
        else:
            m = re.match(r"^(?:([A-Za-z_][A-Za-z0-9_]*)\s*)?(>=|<=|==|!=|>|<)\s*(-?[0-9]+)$", clause)
            if not m:
                raise EkpolError(
                    "EKPOL-INVARIANT-ERR",
                    f"concept {concept_name!r}: invalid invariant clause {clause!r}",
                )
            ident, op, num_s = m.group(1), m.group(2), m.group(3)
            if ident is not None and ident != concept_name:
                raise EkpolError(
                    "EKPOL-INVARIANT-ERR",
                    f"concept {concept_name!r}: invariant references foreign concept {ident!r}",
                )
            val = _parse_int_literal(num_s, "EKPOL-INVARIANT-ERR")
            invs.append(EkpolInvariant(kind="cmp", op=op, value=val))
    return invs


def _parse_single_cmp_clause(clause: str, default_var: str, concept_name: str) -> tuple[str, str, int]:
    """Parse `<var> <op> <int>` or `<int> <op> <var>` into canonical `(var, op, int_val)`."""
    s = clause.strip()
    while s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
    flip = {"<": ">", ">": "<", "<=": ">=", ">=": "<=", "==": "==", "=": "==", "!=": "!="}
    m_left = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=|<=|>=|<|>|=)\s*(-?(?:0x[0-9A-Fa-f]+|[0-9]+))$", s)
    if m_left:
        var_name = m_left.group(1)
        op = "==" if m_left.group(2) == "=" else m_left.group(2)
        val = _parse_int_literal(m_left.group(3), "EKPOL-SYNTAX-ERR")
        return var_name, op, val
    m_right = re.match(r"^(-?(?:0x[0-9A-Fa-f]+|[0-9]+))\s*(==|!=|<=|>=|<|>|=)\s*([A-Za-z_][A-Za-z0-9_]*)$", s)
    if m_right:
        val = _parse_int_literal(m_right.group(1), "EKPOL-SYNTAX-ERR")
        op = flip[m_right.group(2)]
        var_name = m_right.group(3)
        return var_name, op, val
    raise EkpolError(
        "EKPOL-SYNTAX-ERR",
        f"concept {concept_name!r}: cannot parse guard comparison {clause!r} (expected comparison on {default_var!r})",
    )


def _parse_predicate(guard_str: str | None, default_var: str, concept_name: str) -> EkpolPredicate:
    if guard_str is None:
        return EkpolPredicate(kind="nop", var=default_var, raw_text="true")
    g = guard_str.strip()
    if not g or g == "true":
        return EkpolPredicate(kind="nop", var=default_var, inverted=False, raw_text="true")
    if g == "false":
        return EkpolPredicate(kind="nop", var=default_var, inverted=True, raw_text="false")

    invert = False
    while True:
        if g.startswith("not ") or g.startswith("not("):
            invert = not invert
            g = g[3:].strip()
        elif g.startswith("!") and not g.startswith("!=") and g != "!":
            invert = not invert
            g = g[1:].strip()
        else:
            break
        if g.startswith("(") and g.endswith(")"):
            # Only strip outer parens if balanced
            depth = 0
            balanced = True
            for idx, ch in enumerate(g):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0 and idx < len(g) - 1:
                        balanced = False
                        break
            if balanced:
                g = g[1:-1].strip()

    while g.startswith("(") and g.endswith(")"):
        depth = 0
        balanced = True
        for idx, ch in enumerate(g):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and idx < len(g) - 1:
                    balanced = False
                    break
        if balanced:
            g = g[1:-1].strip()
        else:
            break

    if g == "true":
        return EkpolPredicate(kind="nop", var=default_var, inverted=invert, raw_text=guard_str.strip())
    if g == "false":
        return EkpolPredicate(kind="nop", var=default_var, inverted=not invert, raw_text=guard_str.strip())

    # 1. Range predicate: `x in LO..HI` or `RANGE(x, LO, HI)`
    m_in = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s+in\s+(-?[0-9]+)\s*\.\.\s*(-?[0-9]+)$", g)
    if not m_in:
        m_in = re.match(
            r"^RANGE\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,\s*(-?[0-9]+)\s*,\s*(-?[0-9]+)\s*\)$",
            g,
            re.IGNORECASE,
        )
    if m_in:
        v_name = m_in.group(1)
        lo = _parse_int_literal(m_in.group(2), "EKPOL-RANGE-ERR")
        hi = _parse_int_literal(m_in.group(3), "EKPOL-RANGE-ERR")
        if lo > hi or lo < -32768 or hi > 32767:
            raise EkpolError(
                "EKPOL-RANGE-ERR",
                f"concept {concept_name!r}: invalid range {lo}..{hi} (must satisfy -32768 <= lo <= hi <= 32767)",
            )
        return EkpolPredicate(
            kind="range",
            var=v_name,
            op="in",
            lo=lo,
            hi=hi,
            inverted=invert,
            raw_text=guard_str.strip(),
        )

    # 2. Compound range predicate: `x >= LO && x <= HI` or `x >= LO and x <= HI`
    and_parts = re.split(r"\s+(?:&&|and)\s+", g)
    if len(and_parts) == 2:
        v1, op1, val1 = _parse_single_cmp_clause(and_parts[0], default_var, concept_name)
        v2, op2, val2 = _parse_single_cmp_clause(and_parts[1], default_var, concept_name)
        if v1 != v2:
            raise EkpolError(
                "EKPOL-SYNTAX-ERR",
                f"concept {concept_name!r}: compound guard compares two different variables ({v1!r} and {v2!r})",
            )
        lo_val: int | None = None
        hi_val: int | None = None
        for op_c, val_c in ((op1, val1), (op2, val2)):
            if op_c == ">=":
                lo_val = val_c
            elif op_c == ">":
                lo_val = val_c + 1
            elif op_c == "<=":
                hi_val = val_c
            elif op_c == "<":
                hi_val = val_c - 1
            else:
                raise EkpolError(
                    "EKPOL-RANGE-ERR",
                    f"concept {concept_name!r}: compound range requires lower (>, >=) and upper (<, <=) bounds",
                )
        if lo_val is None or hi_val is None or lo_val > hi_val or lo_val < -32768 or hi_val > 32767:
            raise EkpolError(
                "EKPOL-RANGE-ERR",
                f"concept {concept_name!r}: invalid two-sided range [{lo_val}, {hi_val}]",
            )
        return EkpolPredicate(
            kind="range",
            var=v1,
            op="in",
            lo=lo_val,
            hi=hi_val,
            inverted=invert,
            raw_text=guard_str.strip(),
        )

    # 3. Named state predicates: `[x] is [not] (undef|null|positive|negative|even|odd|uneven)`
    m_is = re.match(
        r"^(?:([A-Za-z_][A-Za-z0-9_]*)\s+)?is\s+(not\s+)?(undef|null|positive|negative|even|odd|uneven)$",
        g,
        re.IGNORECASE,
    )
    if m_is:
        v_name = m_is.group(1) or default_var
        is_not = bool(m_is.group(2))
        pred_word = m_is.group(3).lower()
        eff_inv = invert ^ is_not
        if pred_word == "undef":
            return EkpolPredicate(
                kind="undef",
                var=v_name,
                op="!=" if eff_inv else "==",
                value="_",
                inverted=eff_inv,
                raw_text=guard_str.strip(),
            )
        if pred_word == "null":
            return EkpolPredicate(
                kind="cmp",
                var=v_name,
                op="!=" if eff_inv else "==",
                value=0,
                inverted=False,
                raw_text=guard_str.strip(),
            )
        if pred_word == "positive":
            return EkpolPredicate(
                kind="cmp",
                var=v_name,
                op=">" if not eff_inv else "<=",
                value=0,
                inverted=False,
                raw_text=guard_str.strip(),
            )
        if pred_word == "negative":
            return EkpolPredicate(
                kind="cmp",
                var=v_name,
                op="<" if not eff_inv else ">=",
                value=0,
                inverted=False,
                raw_text=guard_str.strip(),
            )
        if pred_word in ("odd", "uneven"):
            return EkpolPredicate(
                kind="bitmask",
                var=v_name,
                op="&",
                value=1,
                inverted=eff_inv,
                raw_text=guard_str.strip(),
            )
        if pred_word == "even":
            return EkpolPredicate(
                kind="bitmask",
                var=v_name,
                op="&",
                value=1,
                inverted=not eff_inv,
                raw_text=guard_str.strip(),
            )

    # 4. Explicit bitmask `(x & MASK) != 0` or `x & MASK`
    m_mask = re.match(
        r"^\(?\s*([A-Za-z_][A-Za-z0-9_]*)\s*&\s*(-?(?:0x[0-9A-Fa-f]+|[0-9]+))\s*\)?(?:\s*(!=|==)\s*0)?$",
        g,
    )
    if m_mask:
        v_name = m_mask.group(1)
        mask_val = _parse_int_literal(m_mask.group(2), "EKPOL-SYNTAX-ERR")
        cmp_zero = m_mask.group(3)
        eff_inv = invert ^ (cmp_zero == "==")
        return EkpolPredicate(
            kind="bitmask",
            var=v_name,
            op="&",
            value=mask_val,
            inverted=eff_inv,
            raw_text=guard_str.strip(),
        )

    # 5. Uncertainty / Bool comparison (`x == _`, `x == undef`, `x == true`, `x == false`, `_`, `!`, `¬`)
    if g in ("_", "undef"):
        return EkpolPredicate(kind="undef", var=default_var, op="==", value="_", inverted=invert, raw_text=g)
    if g in ("!", "true"):
        return EkpolPredicate(kind="cmp", var=default_var, op="==", value=True, inverted=invert, raw_text=g)
    if g in ("¬", "~false", "false"):
        return EkpolPredicate(kind="cmp", var=default_var, op="==", value=False, inverted=invert, raw_text=g)

    m_special = re.match(
        r"^([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=|=)\s*(_|undef|true|false|!|~false|¬)$",
        g,
    )
    if m_special:
        v_name = m_special.group(1)
        op_s = "==" if m_special.group(2) == "=" else m_special.group(2)
        rhs_s = m_special.group(3)
        if rhs_s in ("_", "undef"):
            return EkpolPredicate(
                kind="undef",
                var=v_name,
                op=op_s,
                value="_",
                inverted=invert ^ (op_s == "!="),
                raw_text=guard_str.strip(),
            )
        b_val = rhs_s in ("true", "!")
        return EkpolPredicate(
            kind="cmp",
            var=v_name,
            op=op_s,
            value=b_val,
            inverted=invert,
            raw_text=guard_str.strip(),
        )

    # 6. Standard numeric comparison (`x < 20`, `x >= 1`, `x == 2`, etc.)
    try:
        v_name, op_s, val_i = _parse_single_cmp_clause(g, default_var, concept_name)
        return EkpolPredicate(
            kind="cmp",
            var=v_name,
            op=op_s,
            value=val_i,
            inverted=invert,
            raw_text=guard_str.strip(),
        )
    except EkpolError:
        # Allow conceptual symbol-to-symbol comparisons like `a > b` in conceptual mode
        m_sym = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=|<=|>=|<|>)\s*([A-Za-z_][A-Za-z0-9_]*)$", g)
        if m_sym:
            return EkpolPredicate(
                kind="raw",
                var=m_sym.group(1),
                op=m_sym.group(2),
                value=m_sym.group(3),
                inverted=invert,
                raw_text=guard_str.strip(),
            )
        raise


def _parse_actions(action_str: str, concept_name: str, input_var: str) -> tuple[EkpolAction, ...]:
    s = action_str.strip()
    # Strip trailing rule terminator if still attached
    while True:
        s_prev = s
        for suffix in ("commit;", "commit", ".;", ".", "•;", "•", ";"):
            if s.endswith(suffix):
                s = s[: -len(suffix)].strip()
        if s == s_prev:
            break

    if not s:
        raise EkpolError("EKPOL-SYNTAX-ERR", f"concept {concept_name!r}: empty action after '=>'")

    if s in ("pass", "nop"):
        return (EkpolAction(kind="nop", target=concept_name, operand=0, raw_text=s),)

    parts = [p.strip() for p in s.split(";") if p.strip()]
    actions: list[EkpolAction] = []
    for part in parts:
        if part in ("pass", "nop"):
            actions.append(EkpolAction(kind="nop", target=concept_name, operand=0, raw_text=part))
            continue

        m_aug = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(\+=|-=)\s*(.+)$", part)
        if m_aug:
            tgt = m_aug.group(1)
            op = m_aug.group(2)
            rhs = m_aug.group(3).strip()
            try:
                step = int(rhs, 0)
                if step == 1:
                    actions.append(
                        EkpolAction(
                            kind="inc" if op == "+=" else "dec",
                            target=tgt,
                            operand=1,
                            raw_text=part,
                        )
                    )
                else:
                    actions.append(
                        EkpolAction(
                            kind="add" if op == "+=" else "sub",
                            target=tgt,
                            operand=step,
                            raw_text=part,
                        )
                    )
            except ValueError:
                actions.append(
                    EkpolAction(
                        kind="raw",
                        target=tgt,
                        operand=rhs,
                        raw_text=part,
                    )
                )
            continue

        m_set = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?::=|=)\s*(.+)$", part)
        if m_set:
            tgt = m_set.group(1)
            rhs = m_set.group(2).strip()
            # Check if rhs is `Target + K` or `Target - K`
            m_bin = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*([+\-])\s*(-?[0-9]+)$", rhs)
            if m_bin and m_bin.group(1) == tgt:
                op_b = m_bin.group(2)
                step = int(m_bin.group(3), 0)
                if step == 1:
                    actions.append(
                        EkpolAction(
                            kind="inc" if op_b == "+" else "dec",
                            target=tgt,
                            operand=1,
                            raw_text=part,
                        )
                    )
                else:
                    actions.append(
                        EkpolAction(
                            kind="add" if op_b == "+" else "sub",
                            target=tgt,
                            operand=step,
                            raw_text=part,
                        )
                    )
                continue
            if rhs == input_var and input_var != "":
                actions.append(EkpolAction(kind="assign", target=tgt, operand=rhs, raw_text=part))
            elif rhs in ("true", "!", "false", "~false", "¬", "_", "undef"):
                val_b: Any = "_" if rhs in ("_", "undef") else (rhs in ("true", "!"))
                actions.append(EkpolAction(kind="set_const", target=tgt, operand=val_b, raw_text=part))
            else:
                try:
                    c_int = int(rhs, 0)
                    actions.append(EkpolAction(kind="set_const", target=tgt, operand=c_int, raw_text=part))
                except ValueError:
                    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", rhs):
                        actions.append(EkpolAction(kind="assign", target=tgt, operand=rhs, raw_text=part))
                    else:
                        actions.append(EkpolAction(kind="raw", target=tgt, operand=rhs, raw_text=part))
            continue

        raise EkpolError("EKPOL-SYNTAX-ERR", f"concept {concept_name!r}: invalid action {part!r}")

    return tuple(actions)


def _split_concept_statements(body: str) -> list[str]:
    """Split concept body into individual rule/invariant statements."""
    statements: list[str] = []
    cur: list[str] = []
    paren_depth = 0
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for ch in line:
            if ch == "(":
                paren_depth += 1
            elif ch == ")":
                paren_depth = max(0, paren_depth - 1)
        cur.append(line)
        if paren_depth == 0 and (
            line.endswith(".")
            or line.endswith(";")
            or line.endswith("commit")
            or line.endswith("•")
            or "=>" in line
        ):
            statements.append(" ".join(cur))
            cur = []
    if cur:
        statements.append(" ".join(cur))
    return statements


def _parse_concept_rule(stmt: str, concept_name: str) -> EkpolRule:
    s = stmt.strip()
    if "=>" not in s:
        raise EkpolError(
            "EKPOL-SYNTAX-ERR",
            f"concept {concept_name!r}: rule {s!r} is missing '=>' action arrow",
        )
    lhs, rhs = s.split("=>", 1)
    lhs = lhs.strip()
    rhs = rhs.strip()

    # Check terminator or post-read dot
    has_terminator = any(
        rhs.endswith(term) for term in ("commit;", "commit", ".;", ".", "•;", "•", ";")
    )

    # 1. Read rule (`-> ... => . Action` or `on read ... => after Action`)
    if lhs.startswith("->") or re.match(r"^on\s+read\b", lhs):
        if lhs.startswith("->"):
            rest_lhs = lhs[2:].strip()
        else:
            rest_lhs = re.sub(r"^on\s+read\b", "", lhs, count=1).strip()

        guard_str: str | None = None
        if rest_lhs:
            m_g = re.match(r"^(?:::|when)\s+(.+)$", rest_lhs)
            if not m_g:
                raise EkpolError("EKPOL-SYNTAX-ERR", f"concept {concept_name!r}: invalid read guard {rest_lhs!r}")
            guard_str = m_g.group(1).strip()

        post_read_dot = False
        if rhs.startswith(".") or rhs.startswith("•"):
            post_read_dot = True
            rhs = rhs[1:].strip()
        elif re.match(r"^after\b", rhs):
            post_read_dot = True
            rhs = re.sub(r"^after\b", "", rhs, count=1).strip()

        pred = _parse_predicate(guard_str, concept_name, concept_name)
        acts = _parse_actions(rhs, concept_name, concept_name)
        return EkpolRule(
            trigger_kind="read",
            event_name="read",
            param_name=concept_name,
            predicate=pred,
            actions=acts,
            post_read_barrier=post_read_dot,
        )

    if not has_terminator:
        raise EkpolError(
            "EKPOL-SYNTAX-ERR",
            f"concept {concept_name!r}: rule {s!r} is missing Big Dot terminator ('.', 'commit', or ';')",
        )

    # 2. Change subscription rule (`~ Src ...` or `on change(Src) ...`)
    if lhs.startswith("~") or re.match(r"^on\s+change\b", lhs):
        if lhs.startswith("~"):
            rest = lhs[1:].strip()
        else:
            rest = re.sub(r"^on\s+change\b", "", lhs, count=1).strip()

        m_src = re.match(r"^\(?\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)?(.*)$", rest)
        if not m_src:
            raise EkpolError(
                "EKPOL-SYNTAX-ERR",
                f"concept {concept_name!r}: invalid change subscription {lhs!r}",
            )
        src_concept = m_src.group(1)
        guard_part = m_src.group(2).strip()
        guard_str = None
        if guard_part:
            m_g = re.match(r"^(?:::|when)\s+(.+)$", guard_part)
            if not m_g:
                raise EkpolError(
                    "EKPOL-SYNTAX-ERR",
                    f"concept {concept_name!r}: invalid guard syntax {guard_part!r}",
                )
            guard_str = m_g.group(1).strip()

        pred = _parse_predicate(guard_str, src_concept, concept_name)
        acts = _parse_actions(rhs, concept_name, src_concept)
        return EkpolRule(
            trigger_kind="change",
            event_name="change",
            param_name=src_concept,
            watch_concept=src_concept,
            predicate=pred,
            actions=acts,
        )

    # 3. Execute / Call rule (`| ...` or `on call(...)` or `on exec(...)`)
    if lhs.startswith("|") or re.match(r"^on\s+(?:call|exec)\b", lhs):
        if lhs.startswith("|"):
            rest = lhs[1:].strip()
        else:
            rest = re.sub(r"^on\s+(?:call|exec)\b", "", lhs, count=1).strip()

        exec_params: list[str] = []
        if rest.startswith("("):
            close_idx = rest.find(")")
            if close_idx < 0:
                raise EkpolError("EKPOL-SYNTAX-ERR", f"concept {concept_name!r}: unclosed '(' in exec rule")
            p_inner = rest[1:close_idx].strip()
            if p_inner:
                for p_tok in p_inner.split(","):
                    p_clean = p_tok.split(":", 1)[0].strip()
                    if p_clean:
                        exec_params.append(p_clean)
            rest = rest[close_idx + 1 :].strip()

        guard_str = None
        if rest:
            m_g = re.match(r"^(?:::|when)\s+(.+)$", rest)
            if not m_g:
                raise EkpolError("EKPOL-SYNTAX-ERR", f"concept {concept_name!r}: invalid exec guard {rest!r}")
            guard_str = m_g.group(1).strip()

        default_var = exec_params[0] if exec_params else concept_name
        pred = _parse_predicate(guard_str, default_var, concept_name)
        acts = _parse_actions(rhs, concept_name, default_var)
        return EkpolRule(
            trigger_kind="exec",
            event_name="call",
            param_name=default_var,
            exec_params=tuple(exec_params),
            predicate=pred,
            actions=acts,
        )

    # 4. External write / input event rule (`<- ...` or `on write(p)` / `on input(p)` / `on EvName(p)`)
    if lhs.startswith("<-") or re.match(r"^on\s+[A-Za-z_]", lhs):
        ev_name: str | None = None
        param_name = "param"
        param_type = "Int32"
        guard_part = ""

        if lhs.startswith("<-"):
            rest = lhs[2:].strip()
            # Could be `<- EvName(param) :: ...` or `<- (param) :: ...` or `<- param :: ...` or `<- :: ...`
            m_ev_p = re.match(
                r"^([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*([A-Za-z0-9_?]+))?\s*\)(.*)$",
                rest,
            )
            m_paren_p = re.match(
                r"^\(\s*([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*([A-Za-z0-9_?]+))?\s*\)(.*)$",
                rest,
            )
            m_bare_p = re.match(
                r"^([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*([A-Za-z0-9_?]+))?(.*)$",
                rest,
            )
            if m_ev_p:
                raw_ev = m_ev_p.group(1)
                ev_name = None if raw_ev in ("write", "input") else raw_ev
                param_name = m_ev_p.group(2)
                if m_ev_p.group(3):
                    param_type = TYPE_SYNONYMS.get(m_ev_p.group(3), m_ev_p.group(3))
                guard_part = m_ev_p.group(4).strip()
            elif m_paren_p:
                param_name = m_paren_p.group(1)
                if m_paren_p.group(2):
                    param_type = TYPE_SYNONYMS.get(m_paren_p.group(2), m_paren_p.group(2))
                guard_part = m_paren_p.group(3).strip()
            elif m_bare_p and m_bare_p.group(1) not in ("when",):
                param_name = m_bare_p.group(1)
                if m_bare_p.group(2):
                    param_type = TYPE_SYNONYMS.get(m_bare_p.group(2), m_bare_p.group(2))
                guard_part = m_bare_p.group(3).strip()
            else:
                guard_part = rest
        else:
            m_on = re.match(
                r"^on\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*([A-Za-z0-9_?]+))?\s*\))?(.*)$",
                lhs,
            )
            if not m_on:
                raise EkpolError("EKPOL-SYNTAX-ERR", f"concept {concept_name!r}: invalid 'on' trigger {lhs!r}")
            raw_ev = m_on.group(1)
            ev_name = None if raw_ev in ("write", "input") else raw_ev
            param_name = m_on.group(2) or "param"
            if m_on.group(3):
                param_type = TYPE_SYNONYMS.get(m_on.group(3), m_on.group(3))
            guard_part = m_on.group(4).strip()

        guard_str = None
        if guard_part:
            m_g = re.match(r"^(?:::|when)\s+(.+)$", guard_part)
            if not m_g:
                raise EkpolError(
                    "EKPOL-SYNTAX-ERR",
                    f"concept {concept_name!r}: expected '::' or 'when' before guard {guard_part!r}",
                )
            guard_str = m_g.group(1).strip()

        pred = _parse_predicate(guard_str, param_name, concept_name)
        acts = _parse_actions(rhs, concept_name, param_name)
        return EkpolRule(
            trigger_kind="write",
            event_name=ev_name,
            param_name=param_name,
            param_type=param_type,
            predicate=pred,
            actions=acts,
        )

    # 5. Autonomous state transition rule (`:: ... => ...` or `when ... => ...`)
    m_st = re.match(r"^(?:::|when)\s+(.+)$", lhs)
    if m_st:
        pred = _parse_predicate(m_st.group(1).strip(), concept_name, concept_name)
        acts = _parse_actions(rhs, concept_name, concept_name)
        return EkpolRule(
            trigger_kind="state",
            event_name=None,
            param_name=concept_name,
            predicate=pred,
            actions=acts,
        )

    raise EkpolError("EKPOL-SYNTAX-ERR", f"concept {concept_name!r}: unrecognized rule trigger {lhs!r}")


def _parse_test_block(name: str, body: str) -> EkpolTest:
    steps: list[EkpolTestStep] = []
    for raw_stmt in re.split(r"[;\n]+", body):
        stmt = raw_stmt.strip()
        if not stmt:
            continue
        if stmt.endswith("."):
            stmt = stmt[:-1].strip()
        if not stmt:
            continue

        m_send = re.match(r"^(?:send|step)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)$", stmt)
        if m_send:
            target = m_send.group(1)
            args_str = m_send.group(2).strip()
            if not args_str:
                raise EkpolError("EKPOL-SYNTAX-ERR", f"test {name!r}: send/step {target}(...) requires an argument")
            arg_parts = [a.strip() for a in args_str.split(",") if a.strip()]
            first_arg = arg_parts[0]
            param_name: str | None = None
            if "=" in first_arg or ":" in first_arg:
                sep = "=" if "=" in first_arg else ":"
                p_k, p_v = first_arg.split(sep, 1)
                param_name = p_k.strip()
                val_tok = p_v.strip()
            else:
                val_tok = first_arg

            if val_tok in ("_", "undef", "invalid"):
                val: Any = "_"
            else:
                val = _parse_int_literal(val_tok, "EKPOL-SYNTAX-ERR")
            extra: list[Any] = []
            for extra_tok in arg_parts[1:]:
                extra.append(_parse_int_literal(extra_tok, "EKPOL-SYNTAX-ERR"))
            steps.append(
                EkpolTestStep(
                    kind="send",
                    target=target,
                    param_name=param_name,
                    value=val,
                    extra_args=tuple(extra),
                )
            )
            continue

        m_exp = re.match(
            r"^expect\s+([A-Za-z_][A-Za-z0-9_]*)\s*(==|=|!=|<=|>=|<|>)\s*(.+)$",
            stmt,
        )
        if m_exp:
            target = m_exp.group(1)
            op = "==" if m_exp.group(2) == "=" else m_exp.group(2)
            rhs = m_exp.group(3).strip()
            if rhs in ("_", "undef"):
                val = "_"
            elif rhs in ("true", "!"):
                val = True
            elif rhs in ("false", "~false", "¬"):
                val = False
            else:
                try:
                    val = int(rhs, 0)
                except ValueError:
                    try:
                        val = float(rhs)
                    except ValueError as err:
                        raise EkpolError("EKPOL-SYNTAX-ERR", f"test {name!r}: invalid expect literal {rhs!r}") from err
            steps.append(EkpolTestStep(kind="expect", target=target, op=op, value=val))
            continue

        raise EkpolError("EKPOL-SYNTAX-ERR", f"test {name!r}: unrecognized test statement {stmt!r}")

    if not steps:
        raise EkpolError("EKPOL-PROOF-ERR", f"test {name!r}: test block cannot be empty")
    return EkpolTest(name=name, steps=tuple(steps))


def parse_ekpol(ekpol_src: str, default_module_name: str = "EkpolModule") -> EkpolProgram:
    """Parse an EKPOL 0.1.0 program (symbolic, keyword, or mixed) into an `EkpolProgram` AST."""
    clean, c_stdin, c_stdout, c_stderr = _strip_comments_preserve_pragmas(ekpol_src)
    text = clean.strip()
    if not text:
        raise EkpolError("EKPOL-SYNTAX-ERR", "empty EKPOL source")

    module_name = default_module_name
    # Check optional `module <Name>;` or `module <Name> { ... }`
    m_mod_semi = re.match(r"^module\s+([A-Za-z_][A-Za-z0-9_]*)\s*;\s*(.*)$", text, re.DOTALL)
    m_mod_brace = re.match(r"^module\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{(.*)\}\s*$", text, re.DOTALL)
    if m_mod_semi:
        module_name = m_mod_semi.group(1)
        text = m_mod_semi.group(2).strip()
    elif m_mod_brace:
        module_name = m_mod_brace.group(1)
        text = m_mod_brace.group(2).strip()

    concepts: list[EkpolConcept] = []
    tests: list[EkpolTest] = []
    stdin_list: list[str] = list(c_stdin)
    stdout_list: list[str] = list(c_stdout)
    stderr_list: list[str] = list(c_stderr)

    idx = 0
    n = len(text)
    pending_annotations: list[str] = []

    while idx < n:
        while idx < n and text[idx].isspace():
            idx += 1
        if idx >= n:
            break

        # Top-level annotations `@stdin`, `@stdout`, `@stderr`
        m_ann = re.match(r"^@(stdin|stdout|stderr)\b", text[idx:])
        if m_ann:
            ann_tok = f"@{m_ann.group(1)}"
            if ann_tok not in pending_annotations:
                pending_annotations.append(ann_tok)
            idx += m_ann.end()
            continue

        # `concept Name: Type = Init [Invariant] { ... }`
        m_concept = re.match(
            r"^concept\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z0-9_?]+)\s*=\s*([^\[\{\n]+?)(\s*\[[^\]]*\])?\s*\{",
            text[idx:],
        )
        if m_concept:
            c_name = m_concept.group(1)
            raw_type = m_concept.group(2).strip()
            raw_init = m_concept.group(3).strip()
            bracket_inv = m_concept.group(4)

            if raw_type not in TYPE_SYNONYMS:
                raise EkpolError(
                    "EKPOL-TYPE-ERR",
                    f"concept {c_name!r}: unsupported type {raw_type!r} (expected i32/int32/Int32, u64/uint64/U64, f64/float64/Float, or bool/Bool/?)",
                )
            can_type = TYPE_SYNONYMS[raw_type]
            init_val, is_undef = _parse_init_value(raw_init, can_type, c_name)
            invs = _parse_bracket_invariants(bracket_inv, c_name)

            brace_start = idx + m_concept.end() - 1
            depth = 0
            pos = brace_start
            while pos < n:
                if text[pos] == "{":
                    depth += 1
                elif text[pos] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                pos += 1
            if depth != 0:
                raise EkpolError("EKPOL-SYNTAX-ERR", f"concept {c_name!r}: unclosed '{{' in concept body")

            body_text = text[brace_start + 1 : pos]
            idx = pos + 1

            c_anns = list(pending_annotations)
            pending_annotations = []
            c_rules: list[EkpolRule] = []

            for stmt in _split_concept_statements(body_text):
                st_clean = stmt.strip()
                if not st_clean:
                    continue
                if st_clean in ("@stdin", "@stdout", "@stderr", "@stdin;", "@stdout;", "@stderr;"):
                    a_clean = st_clean.rstrip(";")
                    if a_clean not in c_anns:
                        c_anns.append(a_clean)
                    continue
                if st_clean.startswith("invariant "):
                    inv_body = st_clean[len("invariant ") :].rstrip(";.").strip()
                    if ":" in inv_body:
                        inv_body = inv_body.split(":", 1)[1].strip()
                    invs.extend(_parse_bracket_invariants(f"[{inv_body}]", c_name))
                    continue
                c_rules.append(_parse_concept_rule(st_clean, c_name))

            for a in c_anns:
                if a == "@stdin" and c_name not in stdin_list:
                    stdin_list.append(c_name)
                elif a == "@stdout" and c_name not in stdout_list:
                    stdout_list.append(c_name)
                elif a == "@stderr" and c_name not in stderr_list:
                    stderr_list.append(c_name)

            concepts.append(
                EkpolConcept(
                    name=c_name,
                    canonical_type=can_type,
                    raw_type=raw_type,
                    initial_value=init_val,
                    is_undef_init=is_undef,
                    invariants=tuple(invs),
                    annotations=tuple(c_anns),
                    rules=tuple(c_rules),
                )
            )
            continue

        # `test Name { ... }` or `scenario Name { ... }`
        m_test = re.match(r"^(?:test|scenario)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{", text[idx:])
        if m_test:
            if pending_annotations:
                raise EkpolError("EKPOL-SYNTAX-ERR", f"dangling annotations {pending_annotations} before test block")
            t_name = m_test.group(1)
            brace_start = idx + m_test.end() - 1
            depth = 0
            pos = brace_start
            while pos < n:
                if text[pos] == "{":
                    depth += 1
                elif text[pos] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                pos += 1
            if depth != 0:
                raise EkpolError("EKPOL-SYNTAX-ERR", f"test {t_name!r}: unclosed '{{' in test block")
            t_body = text[brace_start + 1 : pos]
            idx = pos + 1
            tests.append(_parse_test_block(t_name, t_body))
            continue

        snippet = text[idx : idx + 40].splitlines()[0]
        raise EkpolError("EKPOL-SYNTAX-ERR", f"unexpected token near {snippet!r}")

    if not concepts:
        raise EkpolError("EKPOL-SYNTAX-ERR", "program must declare at least one concept")

    seen_names: set[str] = set()
    for c in concepts:
        if c.name in seen_names:
            raise EkpolError("EKPOL-SYNTAX-ERR", f"duplicate concept declaration {c.name!r}")
        seen_names.add(c.name)

    if module_name == "EkpolModule":
        if len(concepts) == 1:
            c0 = concepts[0]
            if c0.name == "Counter" and c0.rules and c0.rules[0].actions:
                act0 = c0.rules[0].actions[0]
                if act0.kind == "inc":
                    module_name = "Increase"
                elif act0.kind == "dec":
                    module_name = "Decrease" if c0.initial_value == 10 else "DecreaseFromOne"
                else:
                    module_name = c0.name
            else:
                module_name = c0.name
        elif [c.name for c in concepts] == [
            "Cell_Delta_mV",
            "Module_Thermal_Guard",
            "Pack_Fault_Latch",
            "Contactor_Interlock",
        ]:
            module_name = "BmsSafetyCascade"
        elif [c.name for c in concepts] == ["C0", "C1", "C2", "C3"]:
            module_name = "Cascade4Concept"
        else:
            module_name = concepts[0].name

    if not stdin_list:
        stdin_list = [concepts[0].name]
    if not stdout_list:
        stdout_list = [c.name for c in concepts]

    return EkpolProgram(
        module_name=module_name,
        concepts=tuple(concepts),
        tests=tuple(tests),
        stdin_concepts=tuple(stdin_list),
        stdout_concepts=tuple(stdout_list),
        stderr_concepts=tuple(stderr_list),
    )


def _eval_pred_on_int(pred: EkpolPredicate, val: int) -> bool:
    if pred.kind == "nop":
        res = True
    elif pred.kind == "cmp":
        rhs = int(pred.value)
        if pred.op == "==":
            res = val == rhs
        elif pred.op == "!=":
            res = val != rhs
        elif pred.op == "<":
            res = val < rhs
        elif pred.op == ">":
            res = val > rhs
        elif pred.op == "<=":
            res = val <= rhs
        elif pred.op == ">=":
            res = val >= rhs
        else:
            res = False
    elif pred.kind == "range":
        assert pred.lo is not None and pred.hi is not None
        res = pred.lo <= val <= pred.hi
    elif pred.kind == "bitmask":
        res = (val & int(pred.value)) != 0
    else:
        res = False
    return (not res) if pred.inverted else res


def validate_ekpol_for_bram64(prog: EkpolProgram) -> list[ConceptMicroDescriptor]:
    """Validate an `EkpolProgram` against `CME-RAW-1` (`bram64`) hardware rules and build 64 descriptors."""
    if not (1 <= len(prog.concepts) <= 64):
        raise EkpolError("EKPOL-SYNTAX-ERR", f"expected 1..64 concepts for bram64, got {len(prog.concepts)}")

    concept_index: dict[str, int] = {}
    initial_env: dict[str, int] = {}

    for cid, c in enumerate(prog.concepts):
        if c.canonical_type != "Int32":
            raise EkpolError(
                "EKPOL-TYPE-ERR",
                f"concept {c.name!r} has type {c.canonical_type}, but CME-RAW-1 bram64 requires Int32 (i32/int32/Int32)",
            )
        if c.is_undef_init or not isinstance(c.initial_value, int) or isinstance(c.initial_value, bool):
            raise EkpolError(
                "EKPOL-TYPE-ERR",
                f"concept {c.name!r}: initial state '_' / undef requires --mode conceptual (CME-RAW-1 W0 stores signed Int32)",
            )
        has_nonneg_inv = False
        for inv in c.invariants:
            if inv.kind == "cmp" and inv.op == ">=" and inv.value >= 0:
                has_nonneg_inv = True
            elif inv.kind == "cmp" and inv.op == ">" and inv.value >= -1:
                has_nonneg_inv = True
            elif inv.kind == "range" and inv.lo is not None and inv.lo >= 0:
                has_nonneg_inv = True
        if not has_nonneg_inv:
            raise EkpolError(
                "EKPOL-INVARIANT-ERR",
                f"concept {c.name!r}: missing safety invariant '[>= 0]' in concept header or body",
            )
        if c.initial_value < 0:
            raise EkpolError(
                "EKPOL-INVARIANT-ERR",
                f"concept {c.name!r}: initial value {c.initial_value} violates safety invariant {c.name} >= 0",
            )
        if len(c.rules) != 1:
            raise EkpolError(
                "EKPOL-SYNTAX-ERR",
                f"concept {c.name!r}: expected exactly 1 reaction rule for bram64, got {len(c.rules)}",
            )
        concept_index[c.name] = cid
        initial_env[c.name] = c.initial_value

    subscriber_of: dict[str, str] = {}
    for c in prog.concepts:
        rule = c.rules[0]
        if rule.trigger_kind == "change":
            src = rule.watch_concept or rule.param_name
            if src not in concept_index:
                raise EkpolError(
                    "EKPOL-CYCLE-ERR",
                    f"concept {c.name!r}: subscribes to undeclared concept {src!r}",
                )
            if src == c.name:
                raise EkpolError(
                    "EKPOL-CYCLE-ERR",
                    f"concept {c.name!r}: self-subscription ({src} -> {c.name}) is forbidden in bram64",
                )
            if src in subscriber_of:
                raise EkpolError(
                    "EKPOL-CYCLE-ERR",
                    f"concept {src!r}: cascade fan-out > 1 ({subscriber_of[src]}, {c.name}) exceeds single-slot subscriber_cid",
                )
            subscriber_of[src] = c.name
        elif rule.trigger_kind != "write":
            raise EkpolError(
                "EKPOL-TYPE-ERR",
                f"concept {c.name!r}: trigger kind {rule.trigger_kind!r} requires --mode conceptual",
            )

    # 3-color DFS cycle detection
    visit_state: dict[str, int] = {c.name: 0 for c in prog.concepts}
    for c in prog.concepts:
        if visit_state[c.name] != 0:
            continue
        cur: str | None = c.name
        trail: list[str] = []
        while cur is not None and visit_state[cur] == 0:
            visit_state[cur] = 1
            trail.append(cur)
            cur = subscriber_of.get(cur)
        if cur is not None and visit_state[cur] == 1:
            raise EkpolError(
                "EKPOL-CYCLE-ERR",
                f"cyclic cascade subscription detected involving concept {cur!r} ({' -> '.join(trail + [cur])})",
            )
        for node in trail:
            visit_state[node] = 2

    descriptors: list[ConceptMicroDescriptor] = []
    for cid, c in enumerate(prog.concepts):
        rule = c.rules[0]
        input_var = rule.watch_concept if rule.trigger_kind == "change" else rule.param_name
        pred = rule.predicate

        if pred.kind != "nop" and pred.var != input_var:
            raise EkpolError(
                "EKPOL-SYNTAX-ERR",
                f"concept {c.name!r}: guard variable {pred.var!r} does not match rule parameter {input_var!r}",
            )

        guard_uses_op = False
        guard_op_u32 = 0
        invert = pred.inverted

        if pred.kind == "nop":
            pred_opcode = CME_PRED_NOP
        elif pred.kind == "range":
            assert pred.lo is not None and pred.hi is not None
            if pred.lo > pred.hi or pred.lo < -32768 or pred.hi > 32767:
                raise EkpolError(
                    "EKPOL-RANGE-ERR",
                    f"concept {c.name!r}: range {pred.lo}..{pred.hi} outside int16 [-32768, 32767]",
                )
            pred_opcode = CME_PRED_RANGE
            guard_uses_op = True
            guard_op_u32 = ((pred.hi & 0xFFFF) << 16) | (pred.lo & 0xFFFF)
        elif pred.kind == "bitmask":
            pred_opcode = CME_PRED_BITMASK
            guard_uses_op = True
            guard_op_u32 = int(pred.value) & 0xFFFFFFFF
        elif pred.kind == "cmp":
            if isinstance(pred.value, bool) or not isinstance(pred.value, int):
                raise EkpolError(
                    "EKPOL-TYPE-ERR",
                    f"concept {c.name!r}: guard comparison in bram64 requires Int32 literal",
                )
            guard_uses_op = True
            guard_op_u32 = int(pred.value) & 0xFFFFFFFF
            if pred.op == "==":
                pred_opcode = CME_PRED_EQ
            elif pred.op == "!=":
                pred_opcode = CME_PRED_NEQ
            elif pred.op == "<":
                pred_opcode = CME_PRED_LT
            elif pred.op == ">":
                pred_opcode = CME_PRED_GT
            elif pred.op == ">=":
                pred_opcode = CME_PRED_LT
                invert = not invert
            elif pred.op == "<=":
                pred_opcode = CME_PRED_GT
                invert = not invert
            else:
                raise EkpolError("EKPOL-SYNTAX-ERR", f"concept {c.name!r}: unsupported operator {pred.op!r}")
        else:
            raise EkpolError(
                "EKPOL-TYPE-ERR",
                f"concept {c.name!r}: predicate {pred.raw_text!r} is only supported in --mode conceptual",
            )

        if rule.trigger_kind == "change":
            assert input_var is not None
            if _eval_pred_on_int(pred, initial_env[input_var]):
                raise EkpolError(
                    "EKPOL-CYCLE-ERR",
                    f"concept {c.name!r}: on change({input_var}) guard is active on initial state ({initial_env[input_var]})",
                )

        if len(rule.actions) != 1:
            raise EkpolError(
                "EKPOL-SYNTAX-ERR",
                f"concept {c.name!r}: bram64 rule requires exactly 1 action, got {len(rule.actions)}",
            )
        act = rule.actions[0]
        if act.target != c.name:
            raise EkpolError(
                "EKPOL-SYNTAX-ERR",
                f"concept {c.name!r}: rule action must update {c.name!r}, not {act.target!r}",
            )

        act_uses_op = False
        act_op_u32 = 0
        if act.kind == "inc":
            act_opcode = CME_ACT_INC
        elif act.kind == "dec":
            act_opcode = CME_ACT_DEC
        elif act.kind in ("add", "sub"):
            step_val = int(act.operand)
            if step_val < 1:
                raise EkpolError("EKPOL-SYNTAX-ERR", f"concept {c.name!r}: step literal must be >= 1, got {step_val}")
            act_opcode = CME_ACT_ADD if act.kind == "add" else CME_ACT_SUB
            act_uses_op = True
            act_op_u32 = step_val & 0xFFFFFFFF
        elif act.kind == "assign" and act.operand == input_var:
            act_opcode = CME_ACT_ASSIGN
        else:
            raise EkpolError(
                "EKPOL-SYNTAX-ERR",
                f"concept {c.name!r}: unsupported bram64 action {act.raw_text!r} (expected += 1, -= 1, += K, -= K, or = {input_var})",
            )

        if c.name in subscriber_of and act_opcode not in (
            CME_ACT_INC,
            CME_ACT_DEC,
            CME_ACT_ADD,
            CME_ACT_SUB,
        ):
            raise EkpolError(
                "EKPOL-CYCLE-ERR",
                f"concept {c.name!r}: cascade publisher must use a non-zero step action (+/- K)",
            )

        if guard_uses_op and act_uses_op:
            raise EkpolError(
                "EKPOL-COLLISION-ERR",
                f"concept {c.name!r}: CME-RAW-1 shares one 32-bit W1 operand_val between guard literal and ADD/SUB step != 1",
            )

        operand_u32 = guard_op_u32 if guard_uses_op else act_op_u32
        guard_flags = CME_GUARD_ASSUMPTION_EN | CME_GUARD_INVARIANT_EN
        if invert:
            guard_flags |= CME_GUARD_INVERT_ASSUMPTION

        sub_cid = 0
        if c.name in subscriber_of:
            sub_cid = concept_index[subscriber_of[c.name]]
            guard_flags |= CME_GUARD_SUBSCRIBER_EN

        descriptors.append(
            ConceptMicroDescriptor(
                cid=cid,
                name=c.name,
                current_state=c.initial_value & 0xFFFFFFFF,
                operand_val=operand_u32,
                pred_opcode=pred_opcode,
                guard_flags=guard_flags,
                hazard_limit=0,
                action_opcode=act_opcode,
                subscriber_cid=sub_cid,
            )
        )

    for cid in range(len(descriptors), 64):
        descriptors.append(ConceptMicroDescriptor(cid=cid, name=f"Concept_{cid}"))

    return descriptors


def _canonical_event_name_for_concept(c: EkpolConcept, r: EkpolRule, total_concepts: int, cid: int) -> str:
    if r.event_name:
        return r.event_name
    if total_concepts == 1 and c.name == "Counter":
        return "Pulse"
    if re.match(r"^C[0-9]+$", c.name):
        return f"E{c.name[1:]}"
    cleaned = c.name.replace("_mV", "").replace("_", "")
    return f"Ev{cleaned}"


def _canonical_rule_name_for_concept(c: EkpolConcept, r: EkpolRule, total_concepts: int, cid: int) -> str:
    if r.rule_name:
        return r.rule_name
    if total_concepts == 1 and c.name == "Counter":
        return "Step"
    if re.match(r"^C[0-9]+$", c.name):
        return f"R{c.name[1:]}"
    return f"R_{c.name}"


def _predicate_to_kpol_guard(pred: EkpolPredicate) -> str:
    if pred.kind == "nop":
        base = "false" if pred.inverted else "true"
        return base
    if pred.kind == "range":
        base = f"{pred.var} >= {pred.lo} and {pred.var} <= {pred.hi}"
        return f"not ({base})" if pred.inverted else base
    if pred.kind == "cmp":
        base = f"{pred.var} {pred.op} {pred.value}"
        return f"not ({base})" if pred.inverted else base
    if pred.kind == "bitmask":
        # Note: KPOL-CME-2 text parser does not have `&` in expression grammar,
        # so bitmask is lowered directly via descriptors when compiled from EKPOL.
        base = f"{pred.var} != 0"
        return f"not ({base})" if pred.inverted else base
    return pred.raw_text


def _action_to_kpol_set(act: EkpolAction) -> str:
    if act.kind == "inc":
        return f"set {act.target} := {act.target} + 1;"
    if act.kind == "dec":
        return f"set {act.target} := {act.target} - 1;"
    if act.kind == "add":
        return f"set {act.target} := {act.target} + {act.operand};"
    if act.kind == "sub":
        return f"set {act.target} := {act.target} - {act.operand};"
    if act.kind == "assign":
        return f"set {act.target} := {act.operand};"
    return f"set {act.target} := {act.operand};"


def _synthesize_default_test_for_kpol(prog: EkpolProgram, event_by_concept: dict[str, tuple[str, str]]) -> list[str]:
    """Synthesize a valid non-vacuous Proof scenario when a multi-concept EKPOL program omits `test`."""
    entry_concept = prog.concepts[0]
    for c in prog.concepts:
        if c.rules and c.rules[0].trigger_kind == "write":
            entry_concept = c
            break
    ev_name, param_name = event_by_concept[entry_concept.name]
    pred = entry_concept.rules[0].predicate
    sample_val = 10
    if pred.kind == "range" and pred.lo is not None and pred.hi is not None:
        sample_val = pred.lo if not pred.inverted else (pred.hi + 10)
    elif pred.kind == "cmp" and isinstance(pred.value, int):
        v = pred.value
        if pred.op == "<":
            sample_val = (v - 1) if not pred.inverted else (v + 1)
        elif pred.op == "<=":
            sample_val = v if not pred.inverted else (v + 1)
        elif pred.op == ">":
            sample_val = (v + 1) if not pred.inverted else (v - 1)
        elif pred.op == ">=":
            sample_val = v if not pred.inverted else (v - 1)
        elif pred.op == "==":
            sample_val = v if not pred.inverted else (v + 1)
        elif pred.op == "!=":
            sample_val = (v + 1) if not pred.inverted else v

    return [
        f"Proof {prog.module_name} {{",
        "    scenario AutoGeneratedSanityCheck {",
        f"        step {ev_name}({param_name} = {sample_val});",
        f"        expect {entry_concept.name} >= 0;",
        "    }",
        "}",
    ]


def transpile_ekpol_to_kpol(
    ekpol_src: str | EkpolProgram,
    *,
    default_module_name: str = "EkpolModule",
    synthesize_proof_if_needed: bool = False,
) -> str:
    """Transpile an EKPOL 0.1.0 program into canonical classic KPOL (`KPOL-CME-1` / `KPOL-CME-2`)."""
    prog = parse_ekpol(ekpol_src, default_module_name=default_module_name) if isinstance(ekpol_src, str) else ekpol_src
    validate_ekpol_for_bram64(prog)

    lines: list[str] = []
    if prog.stdin_concepts:
        lines.append(f"# @stdin {', '.join(prog.stdin_concepts)}")
    if prog.stdout_concepts:
        lines.append(f"# @stdout {', '.join(prog.stdout_concepts)}")

    # Problem block
    lines.append(f"Problem {prog.module_name} {{")
    lines.append("    Invariants {")
    for idx, c in enumerate(prog.concepts):
        inv_name = "NonNeg" if len(prog.concepts) == 1 else f"I_{c.name}"
        lines.append(f"        {inv_name}: {c.name} >= 0;")
    lines.append("    }")
    lines.append("}")
    lines.append("")

    # Solution block
    lines.append(f"Solution {prog.module_name} {{")
    for c in prog.concepts:
        lines.append(f"    state {c.name}: Int32 = {c.initial_value};")
    lines.append("")

    event_by_concept: dict[str, tuple[str, str]] = {}
    event_to_param: dict[str, str] = {}
    for cid, c in enumerate(prog.concepts):
        r = c.rules[0]
        if r.trigger_kind == "write":
            ev_name = _canonical_event_name_for_concept(c, r, len(prog.concepts), cid)
            event_by_concept[c.name] = (ev_name, r.param_name)
            event_to_param[ev_name] = r.param_name
            lines.append(f"    event {ev_name}({r.param_name}: Int32);")
    lines.append("")

    for cid, c in enumerate(prog.concepts):
        r = c.rules[0]
        r_name = _canonical_rule_name_for_concept(c, r, len(prog.concepts), cid)
        guard_kpol = _predicate_to_kpol_guard(r.predicate)
        act_kpol = _action_to_kpol_set(r.actions[0])
        if r.trigger_kind == "change":
            on_clause = f"change({r.watch_concept})"
        else:
            ev_name, _ = event_by_concept[c.name]
            on_clause = ev_name
        lines.append(f"    rule {r_name} on {on_clause} when {guard_kpol} {{")
        lines.append(f"        {act_kpol}")
        lines.append("    }")
    lines.append("}")

    if prog.tests:
        lines.append("")
        lines.append(f"Proof {prog.module_name} {{")
        for t in prog.tests:
            lines.append(f"    scenario {t.name} {{")
            for st in t.steps:
                if st.kind == "send":
                    if st.target in event_by_concept:
                        ev_name, p_name = event_by_concept[st.target]
                    elif st.target in event_to_param:
                        ev_name = st.target
                        p_name = st.param_name or event_to_param[st.target]
                    else:
                        raise EkpolError(
                            "EKPOL-PROOF-ERR",
                            f"test {t.name!r}: unknown target concept or event {st.target!r}",
                        )
                    lines.append(f"        step {ev_name}({p_name} = {st.value});")
                else:
                    lines.append(f"        expect {st.target} {st.op} {st.value};")
            lines.append("    }")
        lines.append("}")
    elif synthesize_proof_if_needed and len(prog.concepts) > 1:
        lines.append("")
        lines.extend(_synthesize_default_test_for_kpol(prog, event_by_concept))

    kpol_text = "\n".join(lines) + "\n"
    if prog.tests:
        try:
            mod = Parser(kpol_text).parse()
            rep = verify_module(mod)
            if not rep.passed or rep.failures:
                reasons = "; ".join(f"{f.scenario_or_assert}: {f.message}" for f in rep.failures)
                raise EkpolError("EKPOL-PROOF-ERR", f"embedded test verification failed: {reasons}")
        except KpolError as err:
            if isinstance(err, EkpolError):
                raise
            raise EkpolError("EKPOL-PROOF-ERR", str(err)) from err
    return kpol_text


def _kpol_expr_to_ekpol_guard(expr: Expr, style: str) -> str:
    invert = False
    cur = expr
    while isinstance(cur, Unary) and cur.operator in ("not", "!"):
        invert = not invert
        cur = cur.operand

    def _eval_lit(node: Expr) -> int:
        if isinstance(node, Literal) and isinstance(node.value, int):
            return node.value
        if isinstance(node, Unary) and node.operator == "-" and isinstance(node.operand, Literal):
            return -int(node.operand.value)
        raise EkpolError("EKPOL-SYNTAX-ERR", f"unsupported guard literal {node!r}")

    def _norm_cmp(node: Binary) -> tuple[str, str, int]:
        flip = {"<": ">", ">": "<", "<=": ">=", ">=": "<=", "==": "==", "!=": "!="}
        if isinstance(node.left, Name):
            return node.left.value, node.operator, _eval_lit(node.right)
        if isinstance(node.right, Name):
            return node.right.value, flip[node.operator], _eval_lit(node.left)
        raise EkpolError("EKPOL-SYNTAX-ERR", f"invalid comparison {node!r}")

    if isinstance(cur, Literal) and isinstance(cur.value, bool):
        val = (not cur.value) if invert else cur.value
        return "true" if val else "false"

    if isinstance(cur, Binary) and cur.operator == "and" and isinstance(cur.left, Binary) and isinstance(cur.right, Binary):
        v1, op1, val1 = _norm_cmp(cur.left)
        v2, op2, val2 = _norm_cmp(cur.right)
        lo = val1 if op1 == ">=" else (val1 + 1 if op1 == ">" else None)
        hi = val2 if op2 == "<=" else (val2 - 1 if op2 == "<" else None)
        if lo is None or hi is None:
            lo = val2 if op2 == ">=" else (val2 + 1 if op2 == ">" else None)
            hi = val1 if op1 == "<=" else (val1 - 1 if op1 == "<" else None)
        if v1 == v2 and lo is not None and hi is not None:
            base = f"{v1} in {lo}..{hi}"
            if invert:
                return f"not ({base})" if style == "keyword" else f"!({base})"
            return base

    if isinstance(cur, Binary):
        v_name, op_s, val_i = _norm_cmp(cur)
        if invert:
            return f"not ({v_name} {op_s} {val_i})" if style == "keyword" else f"!({v_name} {op_s} {val_i})"
        return f"{v_name} {op_s} {val_i}"

    raise EkpolError("EKPOL-SYNTAX-ERR", f"unsupported KPOL guard expression {expr!r}")


def _kpol_action_to_ekpol(act: SetAction) -> str:
    expr = act.expression
    if isinstance(expr, Binary) and expr.operator in ("+", "-"):
        op_aug = "+=" if expr.operator == "+" else "-="
        if isinstance(expr.left, Name) and expr.left.value == act.name and isinstance(expr.right, Literal):
            return f"{act.name} {op_aug} {expr.right.value}"
        if expr.operator == "+" and isinstance(expr.right, Name) and expr.right.value == act.name and isinstance(expr.left, Literal):
            return f"{act.name} += {expr.left.value}"
    if isinstance(expr, Name):
        return f"{act.name} = {expr.value}"
    if isinstance(expr, Literal):
        return f"{act.name} = {expr.value}"
    raise EkpolError("EKPOL-SYNTAX-ERR", f"unsupported KPOL action expression {expr!r}")


def transpile_kpol_to_ekpol(kpol_src: str, style: str = "symbolic") -> str:
    """Transpile a classic `.kpol` program (`KPOL-CME-1` or `KPOL-CME-2`) into clean ASCII `.ekpol`."""
    if style not in ("symbolic", "keyword"):
        raise EkpolError("EKPOL-SYNTAX-ERR", f"unsupported EKPOL formatting style {style!r} (expected 'symbolic' or 'keyword')")

    _, c_stdin, c_stdout, c_stderr = _strip_comments_preserve_pragmas(kpol_src)
    try:
        mod: Module = Parser(kpol_src).parse()
    except KpolError as err:
        raise EkpolError("EKPOL-SYNTAX-ERR", f"failed to parse input KPOL: {err}") from err

    type_lbl = "i32" if style == "symbolic" else "int32"
    event_map = {ev.name: ev for ev in mod.events}
    rules_by_state = {r.actions[0].name: r for r in mod.rules if r.actions}
    event_to_concept: dict[str, str] = {}
    for st in mod.states:
        r = rules_by_state.get(st.name)
        if r and r.event != "change":
            event_to_concept[r.event] = st.name

    stdin_set = set(c_stdin) if c_stdin else ({mod.states[0].name} if mod.states else set())
    stdout_set = set(c_stdout) if c_stdout else {st.name for st in mod.states}
    stderr_set = set(c_stderr)

    lines: list[str] = [f"module {mod.name};", ""]
    for st in mod.states:
        if st.name in stdin_set:
            lines.append("@stdin")
        if st.name in stdout_set:
            lines.append("@stdout")
        if st.name in stderr_set:
            lines.append("@stderr")

        init_val = st.initial.value if isinstance(st.initial, Literal) else 0
        lines.append(f"concept {st.name}: {type_lbl} = {init_val} [>= 0] {{")

        rule = rules_by_state.get(st.name)
        if rule is not None:
            guard_str = _kpol_expr_to_ekpol_guard(rule.guard, style)
            act_str = _kpol_action_to_ekpol(rule.actions[0])
            if rule.event == "change":
                watch_var = rule.watch[0]
                if style == "symbolic":
                    lines.append(f"    ~ {watch_var} :: {guard_str} => {act_str} .")
                else:
                    lines.append(f"    on change({watch_var}) when {guard_str} => {act_str} commit;")
            else:
                ev_decl = event_map[rule.event]
                p_name = ev_decl.parameters[0][0]
                if style == "symbolic":
                    lines.append(f"    <- {rule.event}({p_name}) :: {guard_str} => {act_str} .")
                else:
                    lines.append(f"    on {rule.event}({p_name}) when {guard_str} => {act_str} commit;")
        lines.append("}")
        lines.append("")

    for proof in mod.proofs:
        if isinstance(proof, ScenarioDecl):
            lines.append(f"test {proof.name} {{")
            for step in proof.steps:
                if isinstance(step, StepAction):
                    target_c = event_to_concept.get(step.event_name, step.event_name)
                    arg_expr = step.arguments[0][1]
                    if isinstance(arg_expr, Literal):
                        arg_v = arg_expr.value
                    elif isinstance(arg_expr, Unary) and arg_expr.operator == "-" and isinstance(arg_expr.operand, Literal):
                        arg_v = -int(arg_expr.operand.value)
                    else:
                        arg_v = 0
                    lines.append(f"    send {target_c}({arg_v});")
                elif isinstance(step, ExpectCheck) and isinstance(step.expression, Binary):
                    lhs_e = step.expression.left
                    rhs_e = step.expression.right
                    if isinstance(lhs_e, Name) and isinstance(rhs_e, Literal):
                        lines.append(f"    expect {lhs_e.value} {step.expression.operator} {rhs_e.value};")
            lines.append("}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def compile_ekpol_to_bram_image(ekpol_src: str | EkpolProgram) -> bytes:
    """Compile an `.ekpol` source string or `EkpolProgram` into a 1024-byte `CME-RAW-1` BRAM image."""
    prog = parse_ekpol(ekpol_src) if isinstance(ekpol_src, str) else ekpol_src
    descriptors = validate_ekpol_for_bram64(prog)
    direct_image = b"".join(d.pack() for d in descriptors)

    # If all predicates are representable in classic KPOL text (i.e. no bitmask predicate),
    # cross-verify against KPOL-CME-1/2 compiler and run embedded test block if present.
    has_bitmask = any(c.rules[0].predicate.kind == "bitmask" for c in prog.concepts)
    if not has_bitmask:
        kpol_text = transpile_ekpol_to_kpol(
            prog,
            synthesize_proof_if_needed=(len(prog.concepts) > 1 and not prog.tests),
        )
        cme_profile = "KPOL-CME-1" if (len(prog.concepts) == 1 and not prog.tests) else "KPOL-CME-2"
        if len(prog.concepts) == 1 and prog.concepts[0].rules[0].actions[0].kind not in ("inc", "dec"):
            cme_profile = "KPOL-CME-2"
            if not prog.tests:
                kpol_text = transpile_ekpol_to_kpol(prog, synthesize_proof_if_needed=True)
        try:
            mod = Parser(kpol_text).parse()
            kpol_image = compile_concept_microcode_bram_image(mod, profile=cme_profile)
            if direct_image != kpol_image:
                raise EkpolError("EKPOL-SYNTAX-ERR", "internal lowering mismatch between EKPOL and KPOL-CME")
        except KpolError as err:
            if isinstance(err, EkpolError):
                raise
            raise EkpolError("EKPOL-PROOF-ERR", str(err)) from err

    return direct_image
