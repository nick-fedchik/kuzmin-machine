package kpolauth

import (
	"fmt"
	"unicode/utf8"
)

// TokenKind is the kind of a lexical token (KPA-LEX-4 table).
type TokenKind string

// Token kinds.
const (
	TokLBrace          TokenKind = "LBRACE"
	TokRBrace          TokenKind = "RBRACE"
	TokLParen          TokenKind = "LPAREN"
	TokRParen          TokenKind = "RPAREN"
	TokLBracket        TokenKind = "LBRACKET"
	TokRBracket        TokenKind = "RBRACKET"
	TokComma           TokenKind = "COMMA"
	TokAt              TokenKind = "AT"
	TokPlus            TokenKind = "PLUS"
	TokMinus           TokenKind = "MINUS"
	TokStar            TokenKind = "STAR"
	TokSlash           TokenKind = "SLASH"
	TokEq              TokenKind = "EQ"
	TokLt              TokenKind = "LT"
	TokGt              TokenKind = "GT"
	TokBoolBang        TokenKind = "BOOL_BANG"
	TokBoolNotSign     TokenKind = "BOOL_NOT_SIGN"
	TokSubscriptionSeq TokenKind = "SUBSCRIPTION_SEQ"
	TokAssign          TokenKind = "ASSIGN"
	TokColon           TokenKind = "COLON"
	TokText            TokenKind = "TEXT"
	TokInt             TokenKind = "INT"
	TokUninit          TokenKind = "UNINIT"
	TokIdent           TokenKind = "IDENT"
	TokHashLegacy      TokenKind = "HASH_LEGACY"
)

// Token is a lexical token that keeps the exact source text and its span. For
// TEXT the Value is the content without delimiters.
type Token struct {
	Kind  TokenKind
	Value string
	Span  Span
}

func openBracketKind(r rune) (TokenKind, bool) {
	switch r {
	case '{':
		return TokLBrace, true
	case '(':
		return TokLParen, true
	case '[':
		return TokLBracket, true
	}
	return "", false
}

func closeBracketKind(r rune) (TokenKind, bool) {
	switch r {
	case '}':
		return TokRBrace, true
	case ')':
		return TokRParen, true
	case ']':
		return TokRBracket, true
	}
	return "", false
}

// closingBracket returns the closing bracket that pairs with an opening one.
func closingBracket(open rune) rune {
	switch open {
	case '{':
		return '}'
	case '(':
		return ')'
	}
	return ']'
}

func singleCharKind(r rune) (TokenKind, bool) {
	switch r {
	case ',':
		return TokComma, true
	case '@':
		return TokAt, true
	case '+':
		return TokPlus, true
	case '-':
		return TokMinus, true
	case '*':
		return TokStar, true
	case '/':
		return TokSlash, true
	case '=':
		return TokEq, true
	case '<':
		return TokLt, true
	case '>':
		return TokGt, true
	case '!':
		return TokBoolBang, true
	case '¬':
		return TokBoolNotSign, true
	case '•':
		return TokSubscriptionSeq, true
	}
	return "", false
}

// textCloser returns the closing delimiter of a text opened by r.
func textCloser(r rune) (rune, bool) {
	switch r {
	case '"':
		return '"', true
	case '«':
		return '»', true
	}
	return 0, false
}

// Tokenize splits KPOL-AUTH source text into tokens (KPA-LEX-1..8). The U05 and
// U06 gates fire here; under the record-diagnostic policy their diagnostics are
// available from TokenizeWithDiagnostics. Invalid UTF-8 bytes are read as
// U+FFFD, which the lexer rejects outside text.
func Tokenize(src string, cfg Config) ([]Token, error) {
	toks, _, err := TokenizeWithDiagnostics(src, cfg)
	return toks, err
}

// TokenizeWithDiagnostics is Tokenize that also returns the diagnostics
// recorded under the record-diagnostic policy (the second result of tokenize in
// the reference).
func TokenizeWithDiagnostics(src string, cfg Config) (toks []Token, diags []Diagnostic, err error) {
	if err := cfg.Validate(); err != nil {
		return nil, nil, err
	}
	f := &frontend{cfg: cfg}
	toks, err = tokenize(f, src)
	if err != nil {
		return nil, nil, err
	}
	return toks, f.diags, nil
}

func tokenize(f *frontend, src string) (toks []Token, err error) {
	defer recoverBailout(&err)
	l := &lexer{f: f, src: []rune(src), line: 1, col: 1}
	return l.run(), nil
}

type lexer struct {
	f       *frontend
	src     []rune
	i       int
	line    int
	col     int
	bytePos int
}

func (l *lexer) advance() {
	ch := l.src[l.i]
	l.i++
	l.bytePos += utf8.RuneLen(ch)
	if ch == '\n' {
		l.line++
		l.col = 1
	} else {
		l.col++
	}
}

// start is the position at which a token begins.
type start struct{ line, col, off, byteOff int }

func (l *lexer) here() start { return start{l.line, l.col, l.i, l.bytePos} }

func (l *lexer) spanFrom(s start) Span {
	return Span{
		Line:       s.line,
		Column:     s.col,
		Offset:     s.off,
		Length:     l.i - s.off,
		EndLine:    l.line,
		EndColumn:  l.col,
		ByteOffset: s.byteOff,
		ByteEnd:    l.bytePos,
	}
}

func (l *lexer) token(kind TokenKind, value string, s start) Token {
	return Token{Kind: kind, Value: value, Span: l.spanFrom(s)}
}

func (l *lexer) run() []Token {
	var toks []Token
	n := len(l.src)
	for l.i < n {
		ch := l.src[l.i]
		if ch == ' ' || ch == '\t' || ch == '\r' || ch == '\n' {
			l.advance()
			continue
		}
		s := l.here()

		if ch == '#' {
			l.advance()
			sp := l.spanFrom(s)
			l.f.emit("KPOL-AUTH-U05",
				"Символ '#' звільнено автором (RFC-011/RFC-016), але нова пара роздільників ще не визначена.",
				&sp)
			toks = append(toks, Token{Kind: TokHashLegacy, Value: "#", Span: sp})
			continue
		}

		if closeDelim, ok := textCloser(ch); ok {
			toks = append(toks, l.text(ch, closeDelim, s))
			continue
		}

		if ch == ':' && l.i+1 < n && l.src[l.i+1] == '=' {
			l.advance()
			l.advance()
			toks = append(toks, l.token(TokAssign, ":=", s))
			continue
		}
		if ch == ':' {
			l.advance()
			toks = append(toks, l.token(TokColon, ":", s))
			continue
		}

		if kind, ok := openBracketKind(ch); ok {
			l.advance()
			toks = append(toks, l.token(kind, string(ch), s))
			continue
		}
		if kind, ok := closeBracketKind(ch); ok {
			l.advance()
			toks = append(toks, l.token(kind, string(ch), s))
			continue
		}
		if kind, ok := singleCharKind(ch); ok {
			l.advance()
			toks = append(toks, l.token(kind, string(ch), s))
			continue
		}

		if pyIsDigit(ch) {
			for l.i < n && pyIsDigit(l.src[l.i]) {
				l.advance()
			}
			toks = append(toks, l.token(TokInt, string(l.src[s.off:l.i]), s))
			continue
		}

		if ch == '_' && (l.i+1 == n || !(pyIsAlnum(l.src[l.i+1]) || l.src[l.i+1] == '_')) {
			l.advance()
			toks = append(toks, l.token(TokUninit, "_", s))
			continue
		}

		if pyIsAlpha(ch) || ch == '_' {
			for l.i < n && (pyIsAlnum(l.src[l.i]) || l.src[l.i] == '_') {
				l.advance()
			}
			toks = append(toks, l.token(TokIdent, string(l.src[s.off:l.i]), s))
			continue
		}

		l.advance()
		sp := l.spanFrom(s)
		panic(l.f.syntaxError("KPOL-AUTH-LEX-01", fmt.Sprintf("Несподіваний символ '%c' у потоці KPOL-AUTH.", ch), &sp))
	}
	return toks
}

// text scans a text literal whose opening delimiter is at s.
func (l *lexer) text(open, closeDelim rune, s start) Token {
	n := len(l.src)
	l.advance()
	var buf []rune
	closed := false
	for l.i < n {
		cur := l.src[l.i]
		if cur == '\\' {
			errStart := l.here()
			l.advance()
			errSpan := l.spanFrom(errStart)
			l.f.emit("KPOL-AUTH-U06",
				"Екранування закривального знака всередині Text/Help не визначено автором (RFC-016 п. 2).",
				&errSpan)
			if l.i < n {
				buf = append(buf, l.src[l.i])
				l.advance()
			}
			continue
		}
		if cur == closeDelim {
			l.advance()
			closed = true
			break
		}
		buf = append(buf, cur)
		l.advance()
	}
	sp := l.spanFrom(s)
	if !closed {
		panic(l.f.syntaxError("KPOL-AUTH-SYNTAX-01",
			fmt.Sprintf("Незакритий текстовий роздільник '%c' (очікувався '%c').", open, closeDelim), &sp))
	}
	return Token{Kind: TokText, Value: string(buf), Span: sp}
}
