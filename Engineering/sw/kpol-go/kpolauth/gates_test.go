package kpolauth

import (
	"strings"
	"testing"
)

// gateCase is one uncertainty gate with a triggering sample and a near miss.
type gateCase struct {
	code     string
	trigger  string
	positive string // accepted without any diagnostic
}

var gateCases = []gateCase{
	{"KPOL-AUTH-U01", `Collection(A, B)[Min=1, Max=2, Logic=AND]`, `Collection(A, B)[Min=1, Max=2]`},
	{"KPOL-AUTH-U02", `Array(A, B)[Min=Byte(1), Max=2]`, `Array(A, B)[Min=1, Max=2]`},
	{"KPOL-AUTH-U03", `Static(OpenBracket, A, CloseBracked)`, `Static(OpenBracket, A, CloseBracket)`},
	{"KPOL-AUTH-U04", `Static(@runtime, OpenBracket, A, CloseBracket)`, `Static(@x, OpenBracket, A, CloseBracket)`},
	{"KPOL-AUTH-U05", `#legacy`, `legacy`},
	{"KPOL-AUTH-U06", `"text \" quote"`, `«text " quote»`},
	{"KPOL-AUTH-U07", `Name("Абвгдеєжз")`, `Name("Абвгдеєж")`},
	{"KPOL-AUTH-U08", `Flag := (A • B)`, `Flag := (A + B)`},
	{"KPOL-AUTH-U09", `A • busy(A)`, `A • buzy(A)`},
	{"KPOL-AUTH-U10", `C := _ + B`, `C := _`},
	{"KPOL-AUTH-U11", `Def(1, 0, 0, 0, 0, 0, 0, 1)`, `Def(1, 0, 0, 0, 0, 0, 0)`},
	{"KPOL-AUTH-U12", `Property(DefBit=1, Value=_)`, `Property(DefBit=1, Value=0)`},
}

func TestRegistryCoversU01toU12(t *testing.T) {
	reg := UncertaintyRegistry()
	if len(reg) != 12 {
		t.Fatalf("registry has %d points", len(reg))
	}
	for i, p := range reg {
		if want := "KPOL-AUTH-U" + string(rune('0'+(i+1)/10)) + string(rune('0'+(i+1)%10)); p.Code != want {
			t.Errorf("registry[%d] = %s, want %s", i, p.Code, want)
		}
		if p.DefaultPolicy != string(FailClosed) || p.RFC == "" || p.Topic == "" || p.SourceStatus == "" {
			t.Errorf("%s: incomplete entry %+v", p.Code, p)
		}
	}
	if len(gateCases) != 12 {
		t.Fatal("every gate needs a test case")
	}
	reg[0].Code = "mutated"
	if UncertaintyRegistry()[0].Code != "KPOL-AUTH-U01" {
		t.Error("UncertaintyRegistry must return a copy")
	}
}

// TestGatesFailClosedAndPositiveControls: every gate stops by default and a
// minimal fix removes the diagnostic.
func TestGatesFailClosedAndPositiveControls(t *testing.T) {
	for _, g := range gateCases {
		t.Run(g.code, func(t *testing.T) {
			_, err := Parse(g.trigger, DefaultConfig())
			var e *Error
			if firstCode(err) != g.code {
				t.Fatalf("trigger %q: code %q, want %s", g.trigger, firstCode(err), g.code)
			}
			e = err.(*Error)
			if e.Diagnostic == nil || e.Diagnostic.Severity != "error" || e.Diagnostic.UncertaintyCode != g.code ||
				e.Diagnostic.SourceRef == "" || e.Span == nil {
				t.Errorf("diagnostic %+v", e.Diagnostic)
			}
			prog, err := Parse(g.positive, DefaultConfig())
			if err != nil || len(prog.Diagnostics) != 0 {
				t.Errorf("positive control %q: err=%v diagnostics=%v", g.positive, err, prog)
			}
		})
	}
}

// TestGatesRecordDiagnostic: under record-diagnostic each gate adds exactly one
// warning and parsing continues; the lowering then refuses the program.
func TestGatesRecordDiagnostic(t *testing.T) {
	for _, g := range gateCases {
		t.Run(g.code, func(t *testing.T) {
			cfg := DefaultConfig()
			cfg.Policies = map[string]Policy{g.code: RecordDiagnostic}
			prog, err := Parse(g.trigger, cfg)
			if err != nil {
				t.Fatalf("record-diagnostic must continue: %v", err)
			}
			var found int
			for _, d := range prog.Diagnostics {
				if d.Code == g.code {
					found++
					if d.Severity != "warning" || d.UncertaintyCode != g.code {
						t.Errorf("diagnostic %+v", d)
					}
				}
			}
			if found != 1 {
				t.Errorf("%d diagnostics with code %s, want 1", found, g.code)
			}
			if _, err := Lower(prog); firstCode(err) != "KPOL-LOWER-UNCERTAINTY" {
				t.Errorf("Lower: %v, want KPOL-LOWER-UNCERTAINTY", err)
			}
		})
	}
}

// TestGateConditionBoundaries pins the exact trigger conditions of KPA-CTX-2,
// including the known blind spots D-A4 and D-A6.
func TestGateConditionBoundaries(t *testing.T) {
	cases := []struct {
		src  string
		code string
	}{
		// U01
		{`A[Op=x]`, "KPOL-AUTH-U01"},
		{`A[Logic=1]`, "KPOL-AUTH-U01"},
		{`A[Other=1]`, ""}, // D-A4: unknown keys are ignored
		// U02
		{`A[Max=Byte]`, "KPOL-AUTH-U02"},
		{`A[Min=_]`, "KPOL-AUTH-U02"},
		{`A[Min=1, Max=15, Count=16]`, ""},
		{`A[Min=1, Max=15, Count=17]`, "KPOL-AUTH-U02"},
		{`A[Count=1]`, ""},
		{`A[Count=2]`, "KPOL-AUTH-U02"},
		{`A[Count=0]`, "KPOL-AUTH-U02"},
		{`A[Count=2, Max=5]`, "KPOL-AUTH-U02"}, // Count only sees Min/Max written to its left
		{`A[Max=5, Count=2]`, ""},
		{`A[Min=3, Count=2]`, "KPOL-AUTH-U02"},
		{`A[Count=Byte(1)]`, ""}, // non-INT Count is not checked
		{`A[Min=5, Max=1]`, ""},  // D-A4: empty interval without diagnostic
		// U03/U04
		{`CloseBracked`, "KPOL-AUTH-U03"},
		{`closebracked`, ""},
		{`@runtime`, "KPOL-AUTH-U04"},
		{`@runtime(1)`, ""},
		{`@@runtime`, "KPOL-AUTH-U04"},
		{`@Runtime`, ""},
		// U05/U06
		{`A # B`, "KPOL-AUTH-U05"},
		{`"a\\"`, "KPOL-AUTH-U06"},
		{`«a\»`, "KPOL-AUTH-U06"},
		// U07: only Name(x) with exactly one literal
		{`Name("0123456789abcdef")`, ""},
		{`Name("0123456789abcdefg")`, "KPOL-AUTH-U07"},
		{`Name(12345678901234567)`, "KPOL-AUTH-U07"},
		{`Name("0123456789abcdefg", 1)`, ""},
		{`Name(Abcdefghijklmnopqrstuvwxyz)`, ""},
		{`Name{"0123456789abcdefg"}`, "KPOL-AUTH-U07"},
		{`name("0123456789abcdefg")`, ""},
		{`Name("")`, ""},
		// U08: • in the right part, also through groups; not through constructs (D-A6)
		{`A := B • C`, "KPOL-AUTH-U08"},
		{`A := {B, (C • D)}`, "KPOL-AUTH-U08"},
		{`A := F(B • C)`, ""},
		{`A := B := (C • D)`, "KPOL-AUTH-U08"},
		{`(A • B) := C`, ""},
		// U09: right link only; case-insensitive; not inside binary expressions (D-A6)
		{`A • busy`, "KPOL-AUTH-U09"},
		{`A • BUSY`, "KPOL-AUTH-U09"},
		{`A • Busy(B)`, "KPOL-AUTH-U09"},
		{`A • F(busy)`, "KPOL-AUTH-U09"},
		{`A • (B, {busy})`, "KPOL-AUTH-U09"},
		{`A • B • busy`, "KPOL-AUTH-U09"},
		{`busy • A`, ""},
		{`A • busy + 1`, ""},
		{`A • F(1 + busy)`, ""},
		{`A • buſy`, ""},
		// U10: immediate arithmetic operand; not inside parentheses (D-A6)
		{`_ + 1`, "KPOL-AUTH-U10"},
		{`1 - _`, "KPOL-AUTH-U10"},
		{`_ * _`, "KPOL-AUTH-U10"},
		{`A / _`, "KPOL-AUTH-U10"},
		{`_ = 1`, ""},
		{`_ < 1`, ""},
		{`_ : 1`, ""},
		{`(_) + 1`, ""},
		{`1 + 2 + _`, "KPOL-AUTH-U10"},
		{`_ + 1 + 2`, "KPOL-AUTH-U10"},
		// U11
		{`Child(1)`, "KPOL-AUTH-U11"},
		{`Def(1, 0, 0, 0, 0, 0, 0, 0)`, "KPOL-AUTH-U11"},
		{`Def{1, 0, 0, 0, 0, 0, 0, 0}`, "KPOL-AUTH-U11"},
		// U12
		{`Property(Value=_, DefBit=1)`, "KPOL-AUTH-U12"},
		{`Property(DefBit=1)`, ""},
		{`Property(Value=_)`, ""},
		{`Prop(DefBit=1, Value=_)`, ""},
	}
	for _, c := range cases {
		_, err := Parse(c.src, DefaultConfig())
		if got := firstCode(err); got != c.code {
			t.Errorf("%q: code %q, want %q (%v)", c.src, got, c.code, err)
		}
	}
}

// TestGateOrder: lexical gates fire before syntax errors earlier in the text
// (KPA-CTX-3), and the first fired gate decides the verdict.
func TestGateOrder(t *testing.T) {
	cases := []struct{ src, code string }{
		{`) #`, "KPOL-AUTH-U05"},
		{`) ¤`, "KPOL-AUTH-LEX-01"},
		{`( "a\"`, "KPOL-AUTH-U06"},
		{`Child CloseBracked`, "KPOL-AUTH-U11"},
		{`CloseBracked Child`, "KPOL-AUTH-U03"},
		{`Child • busy`, "KPOL-AUTH-U11"},
		{`_ + 1 )`, "KPOL-AUTH-U10"},
		{`@runtime Child`, "KPOL-AUTH-U04"},
	}
	for _, c := range cases {
		_, err := Parse(c.src, DefaultConfig())
		if got := firstCode(err); got != c.code {
			t.Errorf("%q: code %q, want %q", c.src, got, c.code)
		}
	}
}

func TestU07NameLengthUnit(t *testing.T) {
	cyrillic8 := `Name("Абвгдеєж")`  // 8 code points, 16 bytes
	cyrillic9 := `Name("Абвгдеєжз")` // 9 code points, 18 bytes
	cp := DefaultConfig()
	cp.NameLengthUnit = Codepoints
	for _, c := range []struct {
		src  string
		cfg  Config
		code string
	}{
		{cyrillic8, DefaultConfig(), ""},
		{cyrillic9, DefaultConfig(), "KPOL-AUTH-U07"},
		{cyrillic9, cp, ""},
		{`Name("Абвгдеєжзиіїйклмн")`, cp, "KPOL-AUTH-U07"}, // 17 code points
		{cyrillic9, Config{}, "KPOL-AUTH-U07"},             // zero value is the default
	} {
		if _, err := Parse(c.src, c.cfg); firstCode(err) != c.code {
			t.Errorf("%q unit %q: code %q, want %q", c.src, c.cfg.NameLengthUnit, firstCode(err), c.code)
		}
	}
	_, err := Parse(cyrillic9, DefaultConfig())
	want := "Одиниця довжини Name (одиниця 'utf8_bytes': codepoints=9, utf8_bytes=18, межа 16) не визначена автором (RFC-016 п. 3)."
	if err == nil || err.(*Error).Msg != want {
		t.Errorf("message %v, want %q", err, want)
	}
}

func TestConfigValidation(t *testing.T) {
	bad := []struct {
		cfg Config
		msg string
	}{
		{Config{Policies: map[string]Policy{"KPOL-AUTH-U99": FailClosed}}, "Unknown uncertainty code: KPOL-AUTH-U99"},
		{Config{Policies: map[string]Policy{"KPOL-AUTH-U01": "silent-guess"}}, "Unsupported policy 'silent-guess' for KPOL-AUTH-U01"},
		{Config{NameLengthUnit: "tokens_guess"}, "Unsupported name_length_unit 'tokens_guess'"},
	}
	for _, b := range bad {
		for name, call := range map[string]func() error{
			"Validate": b.cfg.Validate,
			"Parse":    func() error { _, err := Parse("A", b.cfg); return err },
			"Tokenize": func() error { _, err := Tokenize("A", b.cfg); return err },
		} {
			err := call()
			if firstCode(err) != CodeConfig || !strings.HasSuffix(err.Error(), b.msg) {
				t.Errorf("%s(%+v) = %v, want %s", name, b.cfg, err, b.msg)
			}
		}
	}
	if err := (Config{}).Validate(); err != nil {
		t.Errorf("zero Config: %v", err)
	}
	if got := DefaultConfig().PolicyFor("KPOL-AUTH-U05"); got != FailClosed {
		t.Errorf("default policy %q", got)
	}
	all := RecordAllConfig()
	for _, p := range UncertaintyRegistry() {
		if all.PolicyFor(p.Code) != RecordDiagnostic {
			t.Errorf("RecordAllConfig: %s", p.Code)
		}
	}
}

// TestSyntaxErrorsIgnorePolicy: KPA-CTX-4.
func TestSyntaxErrorsIgnorePolicy(t *testing.T) {
	cfg := RecordAllConfig()
	for src, code := range map[string]string{
		"¤":          "KPOL-AUTH-LEX-01",
		"\u00a0A":    "KPOL-AUTH-LEX-01",
		`"open`:      "KPOL-AUTH-SYNTAX-01",
		`( A ]`:      "KPOL-AUTH-SYNTAX-02",
		`• A`:        "KPOL-AUTH-SYNTAX-03",
		`Def(1, 2)`:  "KPOL-AUTH-SYNTAX-04",
		`A • B := C`: "KPOL-AUTH-SYNTAX-01",
	} {
		if _, err := Parse(src, cfg); firstCode(err) != code {
			t.Errorf("%q: code %q, want %q", src, firstCode(err), code)
		}
	}
}
