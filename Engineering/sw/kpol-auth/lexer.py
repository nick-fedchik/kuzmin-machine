"""Lexer for the KPOL-AUTH native dialect with paired brackets and delimiters."""

from __future__ import annotations

from dataclasses import dataclass

from .uncertainty import (
    AuthFrontendConfig,
    Diagnostic,
    KpolAuthError,
    Span,
    emit_uncertainty,
)


@dataclass(frozen=True)
class Token:
    """Lexical token preserving exact source text and span."""

    kind: str
    value: str
    span: Span


OPEN_BRACKETS = {
    "{": "LBRACE",
    "(": "LPAREN",
    "[": "LBRACKET",
}

CLOSE_BRACKETS = {
    "}": "RBRACE",
    ")": "RPAREN",
    "]": "RBRACKET",
}

BRACKET_PAIRS = {
    "{": "}",
    "(": ")",
    "[": "]",
}

SINGLE_CHAR_TOKENS = {
    ",": "COMMA",
    "@": "AT",
    "+": "PLUS",
    "-": "MINUS",
    "*": "STAR",
    "/": "SLASH",
    "=": "EQ",
    "<": "LT",
    ">": "GT",
    "!": "BOOL_BANG",
    "¬": "BOOL_NOT_SIGN",
    "•": "SUBSCRIPTION_SEQ",
}

TEXT_DELIMITERS = {
    '"': '"',
    "«": "»",
}


def tokenize(
    source: str,
    config: AuthFrontendConfig | None = None,
) -> tuple[list[Token], list[Diagnostic]]:
    """Tokenize KPOL-AUTH source text into paired brackets, delimiters, and atoms."""
    cfg = config or AuthFrontendConfig()
    tokens: list[Token] = []
    diagnostics: list[Diagnostic] = []

    i = 0
    n = len(source)
    line = 1
    col = 1

    def advance(count: int = 1) -> None:
        nonlocal i, line, col
        for _ in range(count):
            ch = source[i]
            i += 1
            if ch == "\n":
                line += 1
                col = 1
            else:
                col += 1

    while i < n:
        ch = source[i]

        if ch in (" ", "\t", "\r", "\n"):
            advance()
            continue

        start_line, start_col, start_off = line, col, i

        if ch == "#":
            span = Span(start_line, start_col, start_off, 1)
            emit_uncertainty(
                "KPOL-AUTH-U05",
                "Символ '#' звільнено автором (RFC-011/RFC-016), але нова пара роздільників ще не визначена.",
                cfg,
                span=span,
                diagnostics=diagnostics,
            )
            advance()
            tokens.append(Token("HASH_LEGACY", "#", span))
            continue

        if ch in TEXT_DELIMITERS:
            close_delim = TEXT_DELIMITERS[ch]
            advance()
            buf: list[str] = []
            closed = False
            while i < n:
                cur = source[i]
                if cur == "\\":
                    err_span = Span(line, col, i, 1)
                    emit_uncertainty(
                        "KPOL-AUTH-U06",
                        "Екранування закривального знака всередині Text/Help не визначено автором (RFC-016 п. 2).",
                        cfg,
                        span=err_span,
                        diagnostics=diagnostics,
                    )
                    advance()
                    if i < n:
                        buf.append(source[i])
                        advance()
                    continue
                if cur == close_delim:
                    advance()
                    closed = True
                    break
                buf.append(cur)
                advance()
            span = Span(start_line, start_col, start_off, i - start_off)
            if not closed:
                diag = Diagnostic(
                    code="KPOL-AUTH-SYNTAX-01",
                    severity="error",
                    message=f"Незакритий текстовий роздільник '{ch}' (очікувався '{close_delim}').",
                    span=span,
                )
                diagnostics.append(diag)
                raise KpolAuthError(diag)
            tokens.append(Token("TEXT", "".join(buf), span))
            continue

        if ch == ":" and i + 1 < n and source[i + 1] == "=":
            advance(2)
            tokens.append(
                Token("ASSIGN", ":=", Span(start_line, start_col, start_off, 2))
            )
            continue

        if ch == ":":
            advance()
            tokens.append(
                Token("COLON", ":", Span(start_line, start_col, start_off, 1))
            )
            continue

        if ch in OPEN_BRACKETS:
            advance()
            tokens.append(
                Token(
                    OPEN_BRACKETS[ch],
                    ch,
                    Span(start_line, start_col, start_off, 1),
                )
            )
            continue

        if ch in CLOSE_BRACKETS:
            advance()
            tokens.append(
                Token(
                    CLOSE_BRACKETS[ch],
                    ch,
                    Span(start_line, start_col, start_off, 1),
                )
            )
            continue

        if ch in SINGLE_CHAR_TOKENS:
            advance()
            tokens.append(
                Token(
                    SINGLE_CHAR_TOKENS[ch],
                    ch,
                    Span(start_line, start_col, start_off, 1),
                )
            )
            continue

        if ch.isdigit():
            while i < n and source[i].isdigit():
                advance()
            val = source[start_off:i]
            tokens.append(
                Token("INT", val, Span(start_line, start_col, start_off, len(val)))
            )
            continue

        if ch == "_" and (i + 1 == n or not (source[i + 1].isalnum() or source[i + 1] == "_")):
            advance()
            tokens.append(
                Token("UNINIT", "_", Span(start_line, start_col, start_off, 1))
            )
            continue

        if ch.isalpha() or ch == "_":
            while i < n and (source[i].isalnum() or source[i] == "_"):
                advance()
            val = source[start_off:i]
            tokens.append(
                Token("IDENT", val, Span(start_line, start_col, start_off, len(val)))
            )
            continue

        advance()
        diag = Diagnostic(
            code="KPOL-AUTH-LEX-01",
            severity="error",
            message=f"Несподіваний символ '{ch}' у потоці KPOL-AUTH.",
            span=Span(start_line, start_col, start_off, 1),
        )
        diagnostics.append(diag)
        raise KpolAuthError(diag)

    return tokens, diagnostics
