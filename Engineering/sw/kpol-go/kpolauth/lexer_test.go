package kpolauth

import (
	"strings"
	"testing"
)

func TestTokenizeKindsAndValues(t *testing.T) {
	src := "{ } ( ) [ ] , @ + - * / = < > ! ¬ • := : \"txt\" «a\"b» 42 _ _x x_1 Ідент"
	toks, err := Tokenize(src, DefaultConfig())
	if err != nil {
		t.Fatal(err)
	}
	want := []struct {
		kind  TokenKind
		value string
	}{
		{TokLBrace, "{"}, {TokRBrace, "}"}, {TokLParen, "("}, {TokRParen, ")"}, {TokLBracket, "["},
		{TokRBracket, "]"}, {TokComma, ","}, {TokAt, "@"}, {TokPlus, "+"}, {TokMinus, "-"}, {TokStar, "*"},
		{TokSlash, "/"}, {TokEq, "="}, {TokLt, "<"}, {TokGt, ">"}, {TokBoolBang, "!"}, {TokBoolNotSign, "¬"},
		{TokSubscriptionSeq, "•"}, {TokAssign, ":="}, {TokColon, ":"}, {TokText, "txt"}, {TokText, `a"b`},
		{TokInt, "42"}, {TokUninit, "_"}, {TokIdent, "_x"}, {TokIdent, "x_1"}, {TokIdent, "Ідент"},
	}
	if len(toks) != len(want) {
		t.Fatalf("%d tokens, want %d: %v", len(toks), len(want), toks)
	}
	for i, w := range want {
		if toks[i].Kind != w.kind || toks[i].Value != w.value {
			t.Errorf("token %d = %s %q, want %s %q", i, toks[i].Kind, toks[i].Value, w.kind, w.value)
		}
	}
}

// TestTokenizeSpansUTF8 mirrors the frontend test of the reference: positions
// in code points and exact UTF-8 byte offsets (KPA-LEX-1).
func TestTokenizeSpansUTF8(t *testing.T) {
	src := "Температура • «Текст» ¬ Стан\nНаступний"
	toks, err := Tokenize(src, DefaultConfig())
	if err != nil {
		t.Fatal(err)
	}
	runes := []rune(src)
	for _, tok := range toks {
		byteSlice := src[tok.Span.ByteOffset:tok.Span.ByteEnd]
		runeSlice := string(runes[tok.Span.Offset : tok.Span.Offset+tok.Span.Length])
		if byteSlice != runeSlice {
			t.Errorf("%s: byte slice %q != rune slice %q", tok.Kind, byteSlice, runeSlice)
		}
		if tok.Kind == TokText {
			if byteSlice != "«"+tok.Value+"»" {
				t.Errorf("TEXT slice %q", byteSlice)
			}
		} else if byteSlice != tok.Value {
			t.Errorf("%s: slice %q != value %q", tok.Kind, byteSlice, tok.Value)
		}
	}
	check := func(i int, line, col, endLine, endCol, b0, b1 int) {
		t.Helper()
		s := toks[i].Span
		got := [6]int{s.Line, s.Column, s.EndLine, s.EndColumn, s.ByteOffset, s.ByteEnd}
		if got != [6]int{line, col, endLine, endCol, b0, b1} {
			t.Errorf("token %d (%q) span %+v", i, toks[i].Value, s)
		}
	}
	check(0, 1, 1, 1, 12, 0, 22)
	check(1, 1, 13, 1, 14, 23, 26)
	check(5, 2, 1, 2, 10, len(src)-len("Наступний"), len(src))

	_, err = Parse("Помилка #старий", DefaultConfig())
	e := err.(*Error)
	if e.Span == nil || e.Span.Line != 1 || e.Span.Column != 9 || "Помилка #старий"[e.Span.ByteOffset:e.Span.ByteEnd] != "#" {
		t.Errorf("U05 span %+v", e.Span)
	}
}

func TestTokenizeLexicalRules(t *testing.T) {
	// KPA-LEX-2/8: only space, tab, CR, LF separate; everything else unknown is LEX-01.
	for _, ch := range []string{"\u00a0", "\u2003", "\ufeff", "'", "^", "¤", "←", "→", "|", "~", ";", ".", "?", "»", "$", "\u000b", "\u000c"} {
		_, err := Tokenize("A"+ch+"B", DefaultConfig())
		if firstCode(err) != "KPOL-AUTH-LEX-01" {
			t.Errorf("%U: code %q", []rune(ch)[0], firstCode(err))
		}
	}
	if _, err := Tokenize("A \t\r\n B", DefaultConfig()); err != nil {
		t.Errorf("whitespace: %v", err)
	}
	_, err := Tokenize("a ¤ b", DefaultConfig())
	if got := err.(*Error).Msg; got != "Несподіваний символ '¤' у потоці KPOL-AUTH." {
		t.Errorf("LEX-01 message %q", got)
	}

	// KPA-LEX-4: ":=" before ":", "_" alone versus identifier.
	toks, _ := Tokenize("a:=b:c::d _ _1 __ _a a_", DefaultConfig())
	var kinds []string
	for _, tok := range toks {
		kinds = append(kinds, string(tok.Kind)+":"+tok.Value)
	}
	want := "IDENT:a ASSIGN::= IDENT:b COLON:: IDENT:c COLON:: COLON:: IDENT:d UNINIT:_ IDENT:_1 IDENT:__ IDENT:_a IDENT:a_"
	if strings.Join(kinds, " ") != want {
		t.Errorf("kinds\n got %s\nwant %s", strings.Join(kinds, " "), want)
	}

	// D-A1 / KPA-LEX-6: str.isdigit classes. "²" is an INT token, "A²" an identifier.
	toks, _ = Tokenize("² A² ٣٣ ①", DefaultConfig())
	if len(toks) != 4 || toks[0].Kind != TokInt || toks[1].Kind != TokIdent || toks[2].Kind != TokInt || toks[3].Kind != TokInt {
		t.Errorf("digit classes: %v", toks)
	}
}

func TestTokenizeText(t *testing.T) {
	// KPA-LEX-5: the other delimiter is an ordinary character; line breaks are kept.
	toks, err := Tokenize("\"a»b\" «c\"d» \"line\nbreak\"", DefaultConfig())
	if err != nil || len(toks) != 3 || toks[0].Value != "a»b" || toks[1].Value != `c"d` || toks[2].Value != "line\nbreak" {
		t.Fatalf("%v %v", toks, err)
	}
	if toks[2].Span.EndLine != 2 || toks[2].Span.EndColumn != 7 {
		t.Errorf("multi-line text span %+v", toks[2].Span)
	}
	_, err = Tokenize(`x "never closed`, DefaultConfig())
	if e := err.(*Error); e.Code != "KPOL-AUTH-SYNTAX-01" || e.Msg != "Незакритий текстовий роздільник '\"' (очікувався '\"')." {
		t.Errorf("unterminated: %v", err)
	}
	_, err = Tokenize(`«never closed`, DefaultConfig())
	if e := err.(*Error); e.Msg != "Незакритий текстовий роздільник '«' (очікувався '»')." {
		t.Errorf("unterminated «: %v", err)
	}
	// Record-diagnostic U06: the escaped character is kept, the backslash dropped.
	toks, diags, err := TokenizeWithDiagnostics(`"a\"b"`, RecordAllConfig())
	if err != nil || len(toks) != 1 || toks[0].Value != `a"b` || len(diags) != 1 || diags[0].Code != "KPOL-AUTH-U06" {
		t.Errorf("record U06: %v %v %v", toks, diags, err)
	}
	// A trailing backslash records U06 and then the text is unterminated.
	if _, err = Tokenize(`"a\`, RecordAllConfig()); firstCode(err) != "KPOL-AUTH-SYNTAX-01" {
		t.Errorf("trailing backslash: %v", err)
	}
	toks, diags, _ = TokenizeWithDiagnostics("# #", RecordAllConfig())
	if len(toks) != 2 || toks[0].Kind != TokHashLegacy || len(diags) != 2 || diags[0].Severity != "warning" {
		t.Errorf("record U05: %v %v", toks, diags)
	}
}

func TestTokenizeInvalidUTF8(t *testing.T) {
	// Invalid bytes are read as U+FFFD (3 bytes wide), so they are LEX-01 outside text.
	_, err := Tokenize("A \xff B", DefaultConfig())
	if firstCode(err) != "KPOL-AUTH-LEX-01" {
		t.Errorf("code %q", firstCode(err))
	}
	toks, err := Tokenize("«\xff»", DefaultConfig())
	if err != nil || toks[0].Value != "\uFFFD" {
		t.Errorf("text with invalid byte: %v %v", toks, err)
	}
}

func TestPyCharacterClasses(t *testing.T) {
	for _, c := range []struct {
		r                        rune
		alpha, digit, alnum, dec bool
	}{
		{'a', true, false, true, false},
		{'Ж', true, false, true, false},
		{'_', false, false, false, false},
		{'0', false, true, true, true},
		{'٣', false, true, true, true},
		{'²', false, true, true, false},
		{'①', false, true, true, false},
		{'½', false, false, true, false}, // isnumeric but not isdigit
		{'Ⅷ', false, false, true, false},
		{'\u00a0', false, false, false, false},
		{'•', false, false, false, false},
		{'¬', false, false, false, false},
	} {
		if pyIsAlpha(c.r) != c.alpha || pyIsDigit(c.r) != c.digit || pyIsAlnum(c.r) != c.alnum {
			t.Errorf("%q: alpha=%v digit=%v alnum=%v", c.r, pyIsAlpha(c.r), pyIsDigit(c.r), pyIsAlnum(c.r))
		}
		if _, ok := pyDecimalValue(c.r); ok != c.dec {
			t.Errorf("%q: decimal=%v", c.r, ok)
		}
	}
	if v, _ := pyDecimalValue('٣'); v != 3 {
		t.Errorf("value of ٣ = %d", v)
	}
	if v, _ := pyDecimalValue('𝟕'); v != 7 { // MATHEMATICAL DOUBLE-STRUCK DIGIT SEVEN
		t.Errorf("value of 𝟕 = %d", v)
	}
}
