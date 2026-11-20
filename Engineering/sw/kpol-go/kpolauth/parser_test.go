package kpolauth

import (
	"fmt"
	"strings"
	"testing"
)

// shape renders a compact structural view of a CST for assertions.
func shape(n Node) string {
	switch n := n.(type) {
	case *Identifier:
		return n.Token.Value
	case *Literal:
		return fmt.Sprintf("%s(%s)", n.Token.Kind, n.Token.Value)
	case *Uninit:
		return "_"
	case *Param:
		return "@" + shape(n.Target)
	case *BracketGroup:
		parts := make([]string, len(n.Elements))
		for i, e := range n.Elements {
			parts[i] = shape(e)
		}
		return n.OpenToken.Value + strings.Join(parts, " ") + n.CloseToken.Value
	case *Construct:
		return n.Name.Token.Value + shape(n.Group)
	case *GroupBounds:
		return fmt.Sprintf("<%s %s|%s..%s>", shape(n.Target), shape(n.Group), n.MinEffective, n.MaxEffective)
	case *DefLayout:
		return fmt.Sprintf("Def%v", n.Bits)
	case *SubscriptionSeq:
		return fmt.Sprintf("(%s • %s)", shape(n.Left), shape(n.Right))
	case *Assignment:
		return fmt.Sprintf("(%s := %s)", shape(n.Target), shape(n.Value))
	case *BinaryExpr:
		return fmt.Sprintf("(%s %s %s)", shape(n.Left), n.OpToken.Value, shape(n.Right))
	}
	return "?"
}

func shapes(t *testing.T, src string) string {
	t.Helper()
	p := mustParse(t, src)
	parts := make([]string, len(p.Items))
	for i, n := range p.Items {
		parts[i] = shape(n)
	}
	return strings.Join(parts, " ; ")
}

func TestParseGrammarRules(t *testing.T) {
	cases := []struct{ src, want string }{
		// KPA-SYN-2: greedy constructs and bounds, adjacency gives separate statements
		{`A (B)`, `A(B)`},
		{"A\n{B}", `A{B}`},
		{`A [i]`, `<A [i]|1..1>`},
		{`A B`, `A ; B`},
		{`A B(C) D`, `A ; B(C) ; D`},
		{`A [1][2]`, `<<A [INT(1)]|1..1> [INT(2)]|1..1>`},
		// KPA-SYN-3: one precedence level, left associative
		{`A + B * C`, `((A + B) * C)`},
		{`A = B : C < D`, `(((A = B) : C) < D)`},
		{`A - 1 - 2`, `((A - INT(1)) - INT(2))`},
		// KPA-SYN-4: := right associative, • left associative, := after • starts a statement
		{`A := B := C`, `(A := (B := C))`},
		{`A • B • C`, `((A • B) • C)`},
		{`A • B + C`, `(A • (B + C))`},
		{`(A • B) := C`, `(((A • B)) := C)`},
		// KPA-SYN-1 primaries
		{`@x`, `@x`},
		{`@@x`, `@@x`},
		{`@F(1)`, `@F(INT(1))`},
		{`! ¬ _ "t" 7`, `BOOL_BANG(!) ; BOOL_NOT_SIGN(¬) ; _ ; TEXT(t) ; INT(7)`},
		{`{}`, `{}`},
		{`()`, `()`},
		{`[]`, `[]`},
		{`F()`, `F()`},
		{``, ``},
		// KPA-SYN-7: optional commas
		{`(a, b,)`, `(a b)`},
		{`{a b, c}`, `{a b c}`},
		{`(a • b, c := d)`, `((a • b) (c := d))`},
		// groups nest, bounds attach to groups and constructs
		{`{(A, B), [C, D]}`, `{(A B) [C D]}`},
		{`Collection(A)[Min=1, Max=3]`, `<Collection(A) [(Min = INT(1)) (Max = INT(3))]|1..4>`},
		{`Def{1, 0, 1, 0, 0, 0, 0}`, `Def[1 0 1 0 0 0 0]`},
		{`Def(1, x, 1, 0, 0, 0, 0)`, `Def[1 1 0 0 0 0]`},   // D-A5: non-integer elements drop out of bits
		{`Def(5, 0, 0, 0, 0, 0, 2)`, `Def[5 0 0 0 0 0 2]`}, // D-A5: not limited to 0/1
	}
	for _, c := range cases {
		if got := shapes(t, c.src); got != c.want {
			t.Errorf("%q\n got %s\nwant %s", c.src, got, c.want)
		}
	}
}

func TestParseSyntaxErrors(t *testing.T) {
	cases := []struct{ src, code, msg string }{
		{`• Flag`, "KPOL-AUTH-SYNTAX-03", "У діалекті KPOL-AUTH символ '•' позначає подію/послідовність підписки (A • B), а не унарний 'not'."},
		{`A •`, "KPOL-AUTH-SYNTAX-01", "Несподіваний кінець файлу."},
		{`A +`, "KPOL-AUTH-SYNTAX-01", "Несподіваний кінець файлу."},
		{`A := `, "KPOL-AUTH-SYNTAX-01", "Несподіваний кінець файлу."},
		{`@`, "KPOL-AUTH-SYNTAX-01", "Несподіваний кінець файлу."},
		{`A • B := C`, "KPOL-AUTH-SYNTAX-01", "Несподіваний токен ASSIGN (':=')."},
		{`,`, "KPOL-AUTH-SYNTAX-01", "Несподіваний токен COMMA (',')."},
		{`(, a)`, "KPOL-AUTH-SYNTAX-01", "Несподіваний токен COMMA (',')."},
		{`(a,, b)`, "KPOL-AUTH-SYNTAX-01", "Несподіваний токен COMMA (',')."},
		{`A, B`, "KPOL-AUTH-SYNTAX-01", "Несподіваний токен COMMA (',')."},
		{`Lower=-1`, "KPOL-AUTH-SYNTAX-01", "Несподіваний токен MINUS ('-')."},
		{`Concept(A, -5)`, "KPOL-AUTH-SYNTAX-01", "Несподіваний токен MINUS ('-')."},
		{`A := := B`, "KPOL-AUTH-SYNTAX-01", "Несподіваний токен ASSIGN (':=')."},
		{`{ A )`, "KPOL-AUTH-SYNTAX-02", "Закривальна дужка ')' не відповідає відкривальній '{' (RFC-011)."},
		{`( A ]`, "KPOL-AUTH-SYNTAX-02", "Закривальна дужка ']' не відповідає відкривальній '(' (RFC-011)."},
		{`( A`, "KPOL-AUTH-SYNTAX-02", "Незакрита дужка '(' (очікувалась ')')."},
		{`[ A [`, "KPOL-AUTH-SYNTAX-02", "Незакрита дужка '[' (очікувалась ']')."},
		{`A ]`, "KPOL-AUTH-SYNTAX-02", "Зайва закривальна дужка ']' без відповідної відкривальної."},
		{`(A + )`, "KPOL-AUTH-SYNTAX-02", "Зайва закривальна дужка ')' без відповідної відкривальної."},
		{`Def(1, 0, 1)`, "KPOL-AUTH-SYNTAX-04", "Непідтримувана ширина Def(3 бітів): підтверджено лише 7-бітний запис (8-бітний із Child підпадає під KPOL-AUTH-U11)."},
		{`Def()`, "KPOL-AUTH-SYNTAX-04", "Непідтримувана ширина Def(0 бітів): підтверджено лише 7-бітний запис (8-бітний із Child підпадає під KPOL-AUTH-U11)."},
		{`Def(1, 0, 0, 0, 0, 0, 0, 0, 1)`, "KPOL-AUTH-SYNTAX-04", "Непідтримувана ширина Def(9 бітів): підтверджено лише 7-бітний запис (8-бітний із Child підпадає під KPOL-AUTH-U11)."},
	}
	for _, c := range cases {
		_, err := Parse(c.src, DefaultConfig())
		e, ok := err.(*Error)
		if !ok || e.Code != c.code || e.Msg != c.msg {
			t.Errorf("%q: %v\nwant %s: %s", c.src, err, c.code, c.msg)
		}
	}
	// SYNTAX-01 at the end of text carries no span, the others locate the token.
	_, err := Parse(`A •`, DefaultConfig())
	if err.(*Error).Span != nil {
		t.Error("end-of-file error must not have a span")
	}
	_, err = Parse("A\n  ]", DefaultConfig())
	if s := err.(*Error).Span; s == nil || s.Line != 2 || s.Column != 3 {
		t.Errorf("span %+v", s)
	}
}

func TestParseCSTDetails(t *testing.T) {
	// KPA-CST-2: composite spans run from the first to the last child.
	p := mustParse(t, "Static(OpenBracket, ItemA, CloseBracket)")
	c := p.Items[0].(*Construct)
	if !c.Group.HasStubBrackets || len(c.Group.CommaTokens) != 2 || c.Group.Kind != CollectionParen {
		t.Errorf("group %+v", c.Group)
	}
	if s := c.Span(); s.Offset != 0 || s.Length != 40 || s.ByteEnd != 40 {
		t.Errorf("construct span %+v", s)
	}
	if mustParse(t, `F(OpenBracket)`).Items[0].(*Construct).Group.HasStubBrackets != true {
		t.Error("OpenBracket must set hasStubBrackets")
	}
	if mustParse(t, `F({OpenBracket})`).Items[0].(*Construct).Group.HasStubBrackets {
		t.Error("only direct elements count for hasStubBrackets")
	}

	// KPA-CST-3/4: kinds and defaulted bounds; the last Min/Max wins; nested bounds.
	gb := mustParse(t, `{X}[Min=2, Min=3, Max=7][Count=1]`).Items[0].(*GroupBounds)
	inner := gb.Target.(*GroupBounds)
	if inner.Group.Kind != ArrayBracket || inner.Target.(*BracketGroup).Kind != CollectionBrace {
		t.Error("group kinds")
	}
	if inner.MinRaw.Int64() != 3 || inner.MaxRaw.Int64() != 7 || inner.MinEffective.Int64() != 3 || inner.MaxEffective.Int64() != 8 {
		t.Errorf("inner bounds %v %v %v %v", inner.MinRaw, inner.MaxRaw, inner.MinEffective, inner.MaxEffective)
	}
	if gb.MinRaw.Int64() != 1 || gb.MaxRaw.Int64() != 0 || gb.MinEffective.Int64() != 1 || gb.MaxEffective.Int64() != 1 {
		t.Errorf("outer bounds are evaluated on their own group: %v %v", gb.MinEffective, gb.MaxEffective)
	}
	if mustParse(t, `X[Min=1, Max=15]`).Items[0].(*GroupBounds).MaxEffective.Int64() != 16 {
		t.Error("RFC-009: Max=15 means 16")
	}
	big := mustParse(t, `X[Max=99999999999999999999]`).Items[0].(*GroupBounds)
	if big.MaxEffective.String() != "100000000000000000000" {
		t.Errorf("big bounds: %s", big.MaxEffective)
	}

	// KPA-CST-5: Def bits, unicode digits are decimal integers (D-A1).
	d := mustParse(t, `Def(٣, 0, 1, 0, 0, 0, 0)`).Items[0].(*DefLayout)
	if d.BitOrder != BitOrderLSBLeft || d.Bits[0].Int64() != 3 || d.Keyword.Token.Value != "Def" {
		t.Errorf("def layout %+v", d)
	}

	// Diagnostic spans: the parameter gate points at "@", U08 at the right part.
	_, err := Parse(`F(@runtime)`, DefaultConfig())
	if s := err.(*Error).Span; s.Offset != 2 || s.Length != 1 {
		t.Errorf("U04 span %+v", s)
	}
	_, err = Parse(`A := B • C`, DefaultConfig())
	if s := err.(*Error).Span; s.Offset != 5 || s.Length != 5 {
		t.Errorf("U08 span %+v", s)
	}
}

func TestParseNonDecimalDigitIsAnError(t *testing.T) {
	// D-A1: the reference raises ValueError for isdigit-only characters in numbers.
	for _, src := range []string{`A[Min=²]`, `Def(²,0,0,0,0,0,0)`, `A[Count=①]`} {
		_, err := Parse(src, DefaultConfig())
		if e, ok := err.(*Error); !ok || e.Code != CodeNonDecimalDigit || e.Span == nil {
			t.Errorf("%q: %v", src, err)
		}
	}
	// Outside numbers the same characters are harmless.
	if _, err := Parse(`A[Other=²]`, DefaultConfig()); err != nil {
		t.Errorf("ignored value: %v", err)
	}
}

func TestParseNestingLimit(t *testing.T) {
	deep := func(n int) string { return strings.Repeat("(", n) + strings.Repeat(")", n) }
	if _, err := Parse(deep(MaxNesting-1), DefaultConfig()); err != nil {
		t.Errorf("depth %d: %v", MaxNesting-1, err)
	}
	for name, src := range map[string]string{
		"groups":  deep(MaxNesting + 5),
		"params":  strings.Repeat("@", MaxNesting+5) + "x",
		"assigns": strings.Repeat("a := ", MaxNesting+5) + "b",
	} {
		if _, err := Parse(src, DefaultConfig()); firstCode(err) != CodeNestingLimit {
			t.Errorf("%s: %v", name, err)
		}
	}
	// Long flat inputs are not limited.
	if _, err := Parse(strings.Repeat("a + ", 100000)+"a", DefaultConfig()); err != nil {
		t.Errorf("long expression: %v", err)
	}
}

// TestParseNeverPanics feeds mangled programs to the frontend and the lowering.
func TestParseNeverPanics(t *testing.T) {
	seeds := []string{
		"Concept(A, 0) Concept(B, 0) A • Assign(B, A + 1)",
		"Static(@runtime, OpenBracket, A, CloseBracket)[Min=1] Def(1,0,1,0,0,0,0) \"x\" «y»",
		"A := B := (C • D) + _ [Count=3] #\\ ¤",
	}
	cfgs := []Config{DefaultConfig(), RecordAllConfig()}
	for _, seed := range seeds {
		runes := []rune(seed)
		for i := 0; i <= len(runes); i++ {
			for _, cut := range []string{string(runes[:i]), string(runes[i:]), string(runes[:i]) + "€" + string(runes[i:])} {
				for _, cfg := range cfgs {
					if prog, err := Parse(cut, cfg); err == nil {
						_, _ = Lower(prog)
					}
				}
			}
		}
	}
}

func FuzzParse(f *testing.F) {
	f.Add("Concept(A, 0) Concept(B, 0) A • Assign(B, A + 1)")
	f.Add("A[Min=1, Max=15, Count=3] Def(1,0,1,0,0,0,0) Name(\"x\") @runtime")
	f.Add("«a» \"b\\\" # ¤ _ :=")
	f.Fuzz(func(t *testing.T, src string) {
		for _, cfg := range []Config{DefaultConfig(), RecordAllConfig()} {
			prog, err := Parse(src, cfg)
			if err != nil {
				if _, ok := err.(*Error); !ok {
					t.Fatalf("non-*Error %T", err)
				}
				continue
			}
			if art, err := Lower(prog); err == nil {
				m := NewMachine(art)
				if len(art.Concepts) > 0 {
					_ = m.TriggerExternal(0, 3)
				}
			}
		}
	})
}
