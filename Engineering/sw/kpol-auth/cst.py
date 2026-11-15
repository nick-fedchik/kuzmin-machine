"""Concrete Syntax Tree (CST) and parser for the KPOL-AUTH native dialect."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .lexer import BRACKET_PAIRS, Token, tokenize
from .uncertainty import (
    AuthFrontendConfig,
    Diagnostic,
    KpolAuthError,
    Span,
    emit_uncertainty,
)


@dataclass(frozen=True)
class CSTNode:
    """Base node for KPOL-AUTH CST."""

    span: Span


@dataclass(frozen=True)
class IdentifierCST(CSTNode):
    token: Token


@dataclass(frozen=True)
class LiteralCST(CSTNode):
    token: Token


@dataclass(frozen=True)
class UninitCST(CSTNode):
    token: Token


@dataclass(frozen=True)
class ParamCST(CSTNode):
    at_token: Token
    target: CSTNode


@dataclass(frozen=True)
class BracketGroupCST(CSTNode):
    open_token: Token
    close_token: Token
    kind: str  # "collection_brace" | "collection_paren" | "array_bracket"
    elements: tuple[CSTNode, ...]
    comma_tokens: tuple[Token, ...] = ()
    has_stub_brackets: bool = False


@dataclass(frozen=True)
class CallOrConstructCST(CSTNode):
    name: IdentifierCST
    group: BracketGroupCST
    bounds: GroupBoundsCST | None = None


@dataclass(frozen=True)
class GroupBoundsCST(CSTNode):
    target: CSTNode
    bracket_group: BracketGroupCST
    min_raw: int
    max_raw: int
    min_effective: int
    max_effective: int


@dataclass(frozen=True)
class DefLayoutCST(CSTNode):
    keyword: IdentifierCST
    group: BracketGroupCST
    bits: tuple[int, ...]
    bit_order: str  # "lsb_left_msb_right"


@dataclass(frozen=True)
class SubscriptionSeqCST(CSTNode):
    left: CSTNode
    dot_token: Token
    right: CSTNode


@dataclass(frozen=True)
class AssignmentCST(CSTNode):
    target: CSTNode
    op_token: Token
    value: CSTNode


@dataclass(frozen=True)
class BinaryExprCST(CSTNode):
    left: CSTNode
    op_token: Token
    right: CSTNode


@dataclass(frozen=True)
class ProgramCST:
    items: tuple[CSTNode, ...]
    diagnostics: tuple[Diagnostic, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


BRACKET_KIND = {
    "{": "collection_brace",
    "(": "collection_paren",
    "[": "array_bracket",
}


class _Parser:
    def __init__(
        self,
        tokens: list[Token],
        config: AuthFrontendConfig,
        diagnostics: list[Diagnostic],
    ) -> None:
        self.tokens = tokens
        self.config = config
        self.diagnostics = diagnostics
        self.pos = 0

    def peek(self, offset: int = 0) -> Token | None:
        idx = self.pos + offset
        return self.tokens[idx] if 0 <= idx < len(self.tokens) else None

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _syntax_error(self, code: str, message: str, span: Span | None) -> None:
        diag = Diagnostic(code=code, severity="error", message=message, span=span)
        self.diagnostics.append(diag)
        raise KpolAuthError(diag)

    def parse_program(self) -> ProgramCST:
        items: list[CSTNode] = []
        while self.peek() is not None:
            items.append(self.parse_statement())
        return ProgramCST(items=tuple(items), diagnostics=tuple(self.diagnostics))

    def parse_statement(self) -> CSTNode:
        node = self.parse_subscription_or_assign()
        return node

    def parse_subscription_or_assign(self) -> CSTNode:
        left = self.parse_expr()
        tok = self.peek()
        if tok is not None and tok.kind == "ASSIGN":
            op = self.advance()
            right = self.parse_subscription_or_assign()
            if self._contains_subscription_seq(right):
                emit_uncertainty(
                    "KPOL-AUTH-U08",
                    "Використання булевого значення '•' у присвоєнні не визначено автором (RFC-017 п. 2).",
                    self.config,
                    span=right.span,
                    diagnostics=self.diagnostics,
                )
            span = Span(
                left.span.line,
                left.span.column,
                left.span.offset,
                (right.span.offset + right.span.length) - left.span.offset,
            )
            return AssignmentCST(span=span, target=left, op_token=op, value=right)

        while tok is not None and tok.kind == "SUBSCRIPTION_SEQ":
            dot = self.advance()
            right = self.parse_expr()
            if self._contains_busy_probe(right):
                emit_uncertainty(
                    "KPOL-AUTH-U09",
                    "Стан busy між читанням і записом в 'A • B' не визначено автором (RFC-017 п. 1).",
                    self.config,
                    span=right.span,
                    diagnostics=self.diagnostics,
                )
            span = Span(
                left.span.line,
                left.span.column,
                left.span.offset,
                (right.span.offset + right.span.length) - left.span.offset,
            )
            left = SubscriptionSeqCST(span=span, left=left, dot_token=dot, right=right)
            tok = self.peek()

        return left

    def _contains_subscription_seq(self, node: CSTNode) -> bool:
        if isinstance(node, SubscriptionSeqCST):
            return True
        if isinstance(node, BracketGroupCST):
            return any(self._contains_subscription_seq(el) for el in node.elements)
        return False

    def _contains_busy_probe(self, node: CSTNode) -> bool:
        if isinstance(node, IdentifierCST):
            return node.token.value.lower() == "busy"
        if isinstance(node, CallOrConstructCST):
            return node.name.token.value.lower() == "busy" or any(
                self._contains_busy_probe(el) for el in node.group.elements
            )
        if isinstance(node, BracketGroupCST):
            return any(self._contains_busy_probe(el) for el in node.elements)
        return False

    def parse_expr(self) -> CSTNode:
        left = self.parse_postfix()
        while (tok := self.peek()) is not None and tok.kind in (
            "PLUS",
            "MINUS",
            "STAR",
            "SLASH",
            "EQ",
            "LT",
            "GT",
            "COLON",
        ):
            op = self.advance()
            right = self.parse_postfix()
            if op.kind in ("PLUS", "MINUS", "STAR", "SLASH") and (
                isinstance(left, UninitCST) or isinstance(right, UninitCST)
            ):
                emit_uncertainty(
                    "KPOL-AUTH-U10",
                    "Читання неініціалізованого стану '_' в арифметичному виразі не визначено автором (RFC-017 п. 3).",
                    self.config,
                    span=op.span,
                    diagnostics=self.diagnostics,
                )
            span = Span(
                left.span.line,
                left.span.column,
                left.span.offset,
                (right.span.offset + right.span.length) - left.span.offset,
            )
            left = BinaryExprCST(span=span, left=left, op_token=op, right=right)
        return left

    def parse_postfix(self) -> CSTNode:
        node = self.parse_primary()
        while (tok := self.peek()) is not None and tok.kind == "LBRACKET":
            bounds_group = self.parse_bracket_group()
            node = self._attach_bounds(node, bounds_group)
        return node

    def _attach_bounds(
        self, target: CSTNode, bounds_group: BracketGroupCST
    ) -> GroupBoundsCST:
        min_val: int | None = None
        max_val: int | None = None
        for el in bounds_group.elements:
            if not isinstance(el, BinaryExprCST) or el.op_token.kind != "EQ":
                continue
            if not isinstance(el.left, IdentifierCST):
                continue
            key = el.left.token.value
            if key in ("Logic", "Op"):
                emit_uncertainty(
                    "KPOL-AUTH-U01",
                    "Зв'язок семантики И/ИЛИ з межами Min/Max не визначено автором (RFC-009 п. 2).",
                    self.config,
                    span=el.span,
                    diagnostics=self.diagnostics,
                )
            elif key in ("Min", "Max"):
                if not isinstance(el.right, LiteralCST) or el.right.token.kind != "INT":
                    emit_uncertainty(
                        "KPOL-AUTH-U02",
                        f"Не-Token індекс для {key} не визначено автором (RFC-009 п. 3).",
                        self.config,
                        span=el.right.span,
                        diagnostics=self.diagnostics,
                    )
                else:
                    val = int(el.right.token.value)
                    if key == "Min":
                        min_val = val
                    else:
                        max_val = val
            elif key == "Count":
                if isinstance(el.right, LiteralCST) and el.right.token.kind == "INT":
                    cnt = int(el.right.token.value)
                    eff_min = min_val if min_val is not None else 1
                    eff_max = (max_val + 1) if max_val is not None else 1
                    if cnt < eff_min or cnt > eff_max:
                        emit_uncertainty(
                            "KPOL-AUTH-U02",
                            f"Вихід за межі Count={cnt} поза [{eff_min}, {eff_max}] не визначено автором (RFC-009 п. 3).",
                            self.config,
                            span=el.span,
                            diagnostics=self.diagnostics,
                        )

        eff_min = min_val if min_val is not None else 1
        eff_max = (max_val + 1) if max_val is not None else 1
        span = Span(
            target.span.line,
            target.span.column,
            target.span.offset,
            (bounds_group.span.offset + bounds_group.span.length) - target.span.offset,
        )
        return GroupBoundsCST(
            span=span,
            target=target,
            bracket_group=bounds_group,
            min_raw=eff_min,
            max_raw=max_val if max_val is not None else 0,
            min_effective=eff_min,
            max_effective=eff_max,
        )

    def parse_primary(self) -> CSTNode:
        tok = self.peek()
        if tok is None:
            self._syntax_error(
                "KPOL-AUTH-SYNTAX-01", "Несподіваний кінець файлу.", None
            )
            raise AssertionError("unreachable")

        if tok.kind == "SUBSCRIPTION_SEQ":
            self.advance()
            self._syntax_error(
                "KPOL-AUTH-SYNTAX-03",
                "У діалекті KPOL-AUTH символ '•' позначає подію/послідовність підписки (A • B), а не унарний 'not'.",
                tok.span,
            )

        if tok.kind == "AT":
            at_tok = self.advance()
            target = self.parse_primary()
            if (
                isinstance(target, IdentifierCST)
                and target.token.value == "runtime"
            ):
                emit_uncertainty(
                    "KPOL-AUTH-U04",
                    "Момент виконання OpenBracket/CloseBracket (рантайм vs транслятор) не визначено автором (RFC-015).",
                    self.config,
                    span=at_tok.span,
                    diagnostics=self.diagnostics,
                )
            span = Span(
                at_tok.span.line,
                at_tok.span.column,
                at_tok.span.offset,
                (target.span.offset + target.span.length) - at_tok.span.offset,
            )
            return ParamCST(span=span, at_token=at_tok, target=target)

        if tok.kind in ("LBRACE", "LPAREN", "LBRACKET"):
            return self.parse_bracket_group()

        if tok.kind in ("RBRACE", "RPAREN", "RBRACKET"):
            self._syntax_error(
                "KPOL-AUTH-SYNTAX-02",
                f"Зайва закривальна дужка '{tok.value}' без відповідної відкривальної.",
                tok.span,
            )

        if tok.kind == "IDENT":
            ident_tok = self.advance()
            if ident_tok.value == "CloseBracked":
                emit_uncertainty(
                    "KPOL-AUTH-U03",
                    "Написання 'CloseBracked' конфліктує з 'CloseBracket' (RFC-015).",
                    self.config,
                    span=ident_tok.span,
                    diagnostics=self.diagnostics,
                )
            if ident_tok.value == "Child":
                emit_uncertainty(
                    "KPOL-AUTH-U11",
                    "Роль елемента 'Child' («один лишний») у байті Def не визначена автором (RFC-018).",
                    self.config,
                    span=ident_tok.span,
                    diagnostics=self.diagnostics,
                )
            ident = IdentifierCST(span=ident_tok.span, token=ident_tok)
            if (nxt := self.peek()) is not None and nxt.kind in ("LPAREN", "LBRACE"):
                group = self.parse_bracket_group()
                return self._build_construct(ident, group)
            return ident

        if tok.kind in ("INT", "TEXT", "BOOL_BANG", "BOOL_NOT_SIGN", "HASH_LEGACY"):
            lit_tok = self.advance()
            return LiteralCST(span=lit_tok.span, token=lit_tok)

        if tok.kind == "UNINIT":
            u_tok = self.advance()
            return UninitCST(span=u_tok.span, token=u_tok)

        self._syntax_error(
            "KPOL-AUTH-SYNTAX-01",
            f"Несподіваний токен {tok.kind} ('{tok.value}').",
            tok.span,
        )
        raise AssertionError("unreachable")

    def _build_construct(
        self, ident: IdentifierCST, group: BracketGroupCST
    ) -> CSTNode:
        name = ident.token.value
        if name == "Def":
            if len(group.elements) == 8:
                emit_uncertainty(
                    "KPOL-AUTH-U11",
                    "8-бітний запис Def включає елемент Child, який Автор назвав «лишний» (RFC-018).",
                    self.config,
                    span=group.span,
                    diagnostics=self.diagnostics,
                )
            bits: list[int] = []
            for el in group.elements:
                if isinstance(el, LiteralCST) and el.token.kind == "INT":
                    bits.append(int(el.token.value))
            span = Span(
                ident.span.line,
                ident.span.column,
                ident.span.offset,
                (group.span.offset + group.span.length) - ident.span.offset,
            )
            return DefLayoutCST(
                span=span,
                keyword=ident,
                group=group,
                bits=tuple(bits),
                bit_order="lsb_left_msb_right",
            )

        if name == "Name":
            if len(group.elements) == 1 and isinstance(group.elements[0], LiteralCST):
                val = group.elements[0].token.value
                if not val.isascii() or len(val) > 16:
                    emit_uncertainty(
                        "KPOL-AUTH-U07",
                        "Одиниця довжини Name (букви vs байти vs 4-бітні Token, межа 16) не визначена автором (RFC-016 п. 3).",
                        self.config,
                        span=group.elements[0].span,
                        diagnostics=self.diagnostics,
                    )

        if name == "Property":
            has_def_bit = False
            has_uninit = False
            for el in group.elements:
                if (
                    isinstance(el, BinaryExprCST)
                    and el.op_token.kind == "EQ"
                    and isinstance(el.left, IdentifierCST)
                ):
                    if el.left.token.value == "DefBit":
                        has_def_bit = True
                    if el.left.token.value == "Value" and isinstance(
                        el.right, UninitCST
                    ):
                        has_uninit = True
            if has_def_bit and has_uninit:
                emit_uncertainty(
                    "KPOL-AUTH-U12",
                    "Розмежування Def[i]=0 та елемента зі станом '_' не визначено автором (RFC-018 / RFC-010 п. 3).",
                    self.config,
                    span=group.span,
                    diagnostics=self.diagnostics,
                )

        span = Span(
            ident.span.line,
            ident.span.column,
            ident.span.offset,
            (group.span.offset + group.span.length) - ident.span.offset,
        )
        return CallOrConstructCST(span=span, name=ident, group=group)

    def parse_bracket_group(self) -> BracketGroupCST:
        open_tok = self.advance()
        expected_close = BRACKET_PAIRS[open_tok.value]
        elements: list[CSTNode] = []
        commas: list[Token] = []

        while (tok := self.peek()) is not None:
            if tok.kind in ("RBRACE", "RPAREN", "RBRACKET"):
                if tok.value != expected_close:
                    self._syntax_error(
                        "KPOL-AUTH-SYNTAX-02",
                        f"Закривальна дужка '{tok.value}' не відповідає відкривальній '{open_tok.value}' (RFC-011).",
                        tok.span,
                    )
                close_tok = self.advance()
                has_stubs = any(
                    isinstance(el, IdentifierCST)
                    and el.token.value in ("OpenBracket", "CloseBracket")
                    for el in elements
                )
                span = Span(
                    open_tok.span.line,
                    open_tok.span.column,
                    open_tok.span.offset,
                    (close_tok.span.offset + close_tok.span.length)
                    - open_tok.span.offset,
                )
                return BracketGroupCST(
                    span=span,
                    open_token=open_tok,
                    close_token=close_tok,
                    kind=BRACKET_KIND[open_tok.value],
                    elements=tuple(elements),
                    comma_tokens=tuple(commas),
                    has_stub_brackets=has_stubs,
                )

            el = self.parse_statement()
            elements.append(el)
            if (nxt := self.peek()) is not None and nxt.kind == "COMMA":
                commas.append(self.advance())

        self._syntax_error(
            "KPOL-AUTH-SYNTAX-02",
            f"Незакрита дужка '{open_tok.value}' (очікувалась '{expected_close}').",
            open_tok.span,
        )
        raise AssertionError("unreachable")


def parse_kpol_auth(
    source: str,
    config: AuthFrontendConfig | None = None,
) -> ProgramCST:
    """Lex and parse KPOL-AUTH native source text into a CST."""
    cfg = config or AuthFrontendConfig()
    tokens, diagnostics = tokenize(source, cfg)
    parser = _Parser(tokens, cfg, diagnostics)
    return parser.parse_program()
