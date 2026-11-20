package kpol

import (
	"errors"
	"os"
	"regexp"
	"sort"
	"strings"
	"testing"
)

// mod assembles a module text: problem items, then solution declarations in
// the order states, events, rules, and an optional Proof block.
func mod(parts ...string) string {
	get := func(i int) string {
		if i < len(parts) {
			return parts[i]
		}
		return ""
	}
	src := "Problem M { " + get(0) + " }\nSolution M { " + get(1) + " " + get(2) + " " + get(3) + " }\n"
	if p := get(4); p != "" {
		src += "Proof M { " + p + " }\n"
	}
	return src
}

func mustParse(t testing.TB, src string) *Module {
	t.Helper()
	m, err := Parse(src)
	if err != nil {
		t.Fatalf("Parse: %v\n%s", err, src)
	}
	return m
}

// ruleTable holds one verdict per normative rule (and per diagnostic class) of
// §§2–6 of the specification. An empty want means the source is accepted;
// "!crash" marks forms on which the Python reference dies with an unhandled
// exception (the port reports a coded error instead). All expectations are
// the reference's verdicts.
var ruleTable = []struct{ rule, name, src, want string }{
	{"LEX-1", "ascii-at", "@", "1:1: unexpected character '@'"},
	{"LEX-1", "unicode-ident", mod("Invariants { I: змінна >= 0; }", "state змінна: Int32 = 0;"), ""},
	{"LEX-1", "superscript-digit", mod("", "state x: Int32 = ²;"), "!crash"},
	{"LEX-2", "hash-comment", "# c\nProblem M {  }\nSolution M {    }\n", ""},
	{"LEX-2", "slash-comment", "// c\nProblem M {  }\nSolution M {    }\n", ""},
	{"LEX-2", "block-comment", "/* a\nb */Problem M {  }\nSolution M {    }\n", ""},
	{"LEX-2", "unterminated-block", "Problem M /* open", "1:11: unterminated block comment"},
	{"LEX-3", "left-arrow-glued", mod("Invariants { I: a<-1 == 0; }", "state a: Int32 = 0;"), "1:30: expected ';', got 'ALIAS_WRITE'"},
	{"LEX-3", "right-arrow", mod("Invariants { I: a->a; }", "state a: Bool = true;"), "1:30: expected ';', got 'ALIAS_READ'"},
	{"LEX-3", "left-arrow-spaced", mod("Invariants { I: a < -1; }", "state a: Int32 = 0;"), ""},
	{"LEX-3", "bang-alone", mod("Invariants { I: !a; }", "state a: Bool = true;"), "1:29: unexpected character '!'"},
	{"LEX-3", "dot-alone", mod("Invariants { I: a.b; }", "state a: Bool = true;"), "1:30: unexpected character '.'"},
	{"LEX-4", "malformed-number", mod("", "state x: Float<V> = 1.;"), "2:34: malformed numeric literal"},
	{"LEX-4", "leading-zeros", mod("", "state x: Int32 = 007;"), ""},
	{"LEX-4", "negative-literal", mod("", "state x: Int32 = -5;"), ""},
	{"LEX-5", "reserved-state-name", mod("", "state set: Int32 = 0;"), "2:20: reserved keyword 'set' cannot be an identifier"},
	{"LEX-5", "reserved-void", mod("", "state x: Void = 0;"), "2:28: unknown type 'Void'"},
	{"LEX-5", "not-reserved-module", "module M { }", "1:1: expected 'Problem', got 'module'"},
	{"LEX-6", "phase-alias-bullet", mod("Invariants { I: • a; }", "state a: Bool = true;"), ""},
	{"LEX-6", "phase-alias-star", mod("Invariants { I: (*) a; }", "state a: Bool = true;"), ""},
	{"SYN-1", "trailing-text", "Problem M {  }\nSolution M {    }\nx", "3:1: unexpected text after module"},
	{"SYN-2", "duplicate-section", "Problem M { Goals { } Goals { } }\nSolution M { }", "1:29: duplicate Problem section 'Goals'"},
	{"SYN-3", "solution-name", "Problem A { }\nSolution B { }", "2:12: Problem/Solution name mismatch: 'A' vs 'B'"},
	{"SYN-3", "proof-name", "Problem A { }\nSolution A { }\nProof B { }", "3:9: Problem/Proof name mismatch: 'A' vs 'B'"},
	{"SYN-4", "keyword-identifier", mod("", "", "event rule();"), "2:21: reserved keyword 'rule' cannot be an identifier"},
	{"SYN-4", "keyword-name-ref", mod("Invariants { I: event == 1; }"), "unresolved name 'event'"},
	{"SYN-5", "not-binds-tighter", mod("Invariants { I: not x == 1; }", "state x: Int32 = 0;"), "not requires Bool"},
	{"SYN-5", "not-parenthesised", mod("Invariants { I: not (x == 1); }", "state x: Int32 = 0;"), ""},
	{"SYN-6", "chained-comparison", mod("Invariants { I: 1 < x < 3; }", "state x: Int32 = 0;"), "incompatible comparison: KType(name='Bool', unit=None) < KType(name='Number', unit=None)"},
	{"SYN-7", "to-before-on", mod("Hazards { H to t on E: true; }", "state t: Bool = false;", "event E();"), "1:30: expected ':', got 'on'"},
	{"SYN-7", "covers-before-when", mod("Hazards { H on E to t: true; }", "state t: Bool = false;", "event E();", "rule R on E covers H when true { set t := true; }"), "2:69: expected '{', got 'when'"},
	{"SYN-7", "reject-change", mod("", "state x: Int32 = 0;", "", "rule R on reject change(x) { }"), "invalid change rule 'R'"},
	{"STA-1", "duplicate-event", mod("", "", "event E(); event E();"), "duplicate event declaration"},
	{"STA-1", "duplicate-state", mod("", "state x: Int32 = 0; state x: Int32 = 1;"), "duplicate state declaration"},
	{"STA-1", "duplicate-rule", mod("", "", "event E();", "rule R on E { } rule R on E { }"), "duplicate rule declaration"},
	{"STA-1", "same-requirement-name-two-kinds", mod("Invariants { A: true; } Goals { A: true; }"), ""},
	{"STA-1", "same-requirement-name-one-kind", mod("Invariants { A: true; A: true; }"), "duplicate requirement name within a contract kind"},
	{"STA-2", "parameter-state-clash", mod("", "state a: Int32 = 0;", "event E(a: Int32);"), "duplicate/colliding parameters in event 'E'"},
	{"STA-2", "duplicate-parameter", mod("", "", "event E(a: Int32, a: Int32);"), "duplicate/colliding parameters in event 'E'"},
	{"STA-3", "same-name-event-state-rule", mod("", "state E: Int32 = 0;", "event E();", "rule E on E { }"), ""},
	{"STA-4", "forward-reference", mod("", "state a: Int32 = b; state b: Int32 = 0;"), "unresolved name 'b'"},
	{"STA-4", "unresolved-in-requirement", mod("Invariants { I: z == 1; }"), "unresolved name 'z'"},
	{"STA-4", "event-param-outside-event", mod("Invariants { I: p == 1; }", "", "event E(p: Int32);"), "unresolved name 'p'"},
	{"STA-4", "keyword-as-name-ref-unresolved", mod("Invariants { I: gcd == 1; }"), "unresolved name 'gcd'"},
	{"STA-5", "int32-overflow-literal", mod("", "state x: Int32 = 2147483648;"), "initial value of 'x' has type KType(name='Number', unit=None), expected KType(name='Int32', unit=None)"},
	{"STA-5", "u32-negative-literal", mod("", "state x: U32 = -1;"), "initial value of 'x' has type KType(name='Number', unit=None), expected KType(name='U32', unit=None)"},
	{"STA-5", "pin-two", mod("", "state p: Pin = 2;"), "initial value of 'p' has type KType(name='Number', unit=None), expected KType(name='Pin', unit=None)"},
	{"STA-5", "pin-true", mod("", "state p: Pin = true;"), ""},
	{"STA-5", "int32-decimal-two-point-zero", mod("", "state x: Int32 = 2.0;"), ""},
	{"STA-5", "int32-folded-range", mod("", "state x: Int32 = 2147483647 + 1;"), "initial value of 'x' has type KType(name='Number', unit=None), expected KType(name='Int32', unit=None)"},
	{"STA-5", "float-from-int", mod("", "state f: Float<V> = 1;"), ""},
	{"STA-5", "bool-from-int", mod("", "state b: Bool = 1;"), "initial value of 'b' has type KType(name='Number', unit=None), expected KType(name='Bool', unit=None)"},
	{"STA-5", "unknown-initializer-static-ok", mod("", "state x: Int32 = Unknown;"), ""},
	{"STA-5", "pin-vs-pin-params", mod("Invariants { I: x == y; }", "state x: Pin<a> = 0; state y: Pin<b> = 0;"), "incompatible comparison: KType(name='Pin', unit='a') == KType(name='Pin', unit='b')"},
	{"STA-5", "pin-same-params", mod("Invariants { I: x == y; }", "state x: Pin<a> = 0; state y: Pin<a> = 0;"), ""},
	{"STA-5", "pin-vs-bool", mod("Invariants { I: x == y; }", "state x: Pin = 0; state y: Bool = true;"), ""},
	{"STA-5", "pin-ordering", mod("Invariants { I: x < 1; }", "state x: Pin = 0;"), "< requires numeric operands"},
	{"T-Not", "not-numeric", mod("Invariants { I: not x; }", "state x: Int32 = 0;"), "not requires Bool"},
	{"T-Logic", "and-numeric", mod("Invariants { I: x and true; }", "state x: Int32 = 0;"), "and requires Bool operands"},
	{"T-Neg", "neg-bool", mod("Invariants { I: -b == 1; }", "state b: Bool = true;"), "invalid unary operation '-'"},
	{"T-Rel", "compare-unit-mismatch", mod("Invariants { I: f == g; }", "state f: Float<V> = 1; state g: Float<A> = 1;"), "incompatible comparison: KType(name='Float', unit='V') == KType(name='Float', unit='A')"},
	{"T-Rel", "compare-unknown-literal", mod("Invariants { I: x < Unknown; }", "state x: Int32 = 0;"), ""},
	{"T-Rel", "compare-bool-bool-eq", mod("Invariants { I: a == b; }", "state a: Bool = true; state b: Bool = true;"), ""},
	{"T-Rel", "compare-bool-lt", mod("Invariants { I: a < b; }", "state a: Bool = true; state b: Bool = true;"), "< requires numeric operands"},
	{"T-Add", "int-plus-float-literal", mod("Invariants { I: x + 1.5 == 0; }", "state x: Int32 = 0;"), "+ has an invalid integer literal"},
	{"T-Add", "int-plus-integral-decimal", mod("Invariants { I: x + 2.0 == 2; }", "state x: Int32 = 0;"), ""},
	{"T-Add", "int32-plus-u32", mod("Invariants { I: x + y == 0; }", "state x: Int32 = 0; state y: U32 = 0;"), "+ has an invalid integer literal"},
	{"T-Add", "degc-plus", mod("Invariants { I: t + 1 == 1; }", "state t: Float<degC> = 1;"), "arithmetic on absolute degC values is unsupported"},
	{"T-Add", "units-mismatch", mod("Invariants { I: f + g == 0; }", "state f: Float<V> = 1; state g: Float<A> = 1;"), "incompatible numeric types: KType(name='Float', unit='V') and KType(name='Float', unit='A')"},
	{"T-Mul", "v-times-a-is-w", mod("Invariants { I: f * g == w; }", "state f: Float<V> = 1; state g: Float<A> = 1; state w: Float<W> = 1;"), ""},
	{"T-Mul", "w-times-s-is-j", mod("Invariants { I: f * g == w; }", "state f: Float<W> = 1; state g: Float<s> = 1; state w: Float<J> = 1;"), ""},
	{"T-Mul", "v-times-v", mod("Invariants { I: f * g == f; }", "state f: Float<V> = 1; state g: Float<V> = 1;"), "unsupported unit product: V*V"},
	{"T-Div", "int-div-int", mod("Invariants { I: a / b == 1; }", "state a: Int32 = 1; state b: Int32 = 1;"), "unsupported unit division: KType(name='Int32', unit=None)/KType(name='Int32', unit=None)"},
	{"T-Div", "int-div-literal", mod("Invariants { I: a / 2 == 2; }", "state a: Int32 = 4;"), ""},
	{"T-Div", "float-div-same-unit", mod("Invariants { I: f / g == 1; }", "state f: Float<V> = 1; state g: Float<V> = 1;"), ""},
	{"T-Div", "float-div-other-unit", mod("Invariants { I: f / g == 1; }", "state f: Float<V> = 1; state g: Float<A> = 1;"), "unsupported unit division: KType(name='Float', unit='V')/KType(name='Float', unit='A')"},
	{"T-Gcd", "gcd-u64", mod("Invariants { I: gcd(a, b) == 6; }", "state a: U64 = 12; state b: U64 = 18;"), ""},
	{"T-Gcd", "gcd-int32", mod("Invariants { I: gcd(a, b) == 6; }", "state a: Int32 = 12; state b: U64 = 18;"), "gcd arguments must be U64"},
	{"STA-7", "hazard-without-event", mod("Hazards { H to t: true; }", "state t: Bool = false;"), "Hazard 'H' must be scoped to an event"},
	{"STA-7", "hazard-without-target", mod("Hazards { H on E: true; }", "", "event E();"), "Hazard 'H' must declare a response target"},
	{"STA-7", "hazard-target-int", mod("Hazards { H on E to t: true; }", "state t: Int32 = 0;", "event E();"), "Hazard 'H' target must be a declared Bool state"},
	{"STA-7", "alert-with-target", mod("Alerts { A on E to t: true; }", "state t: Bool = false;", "event E();"), "only Hazard may declare a response target ('A')"},
	{"STA-7", "invariant-with-event", mod("Invariants { I on E: true; }", "", "event E();"), "Invariant 'I' must be a state-only predicate"},
	{"STA-7", "goal-with-event", mod("Goals { G on E: true; }", "", "event E();"), "Goal 'G' must be a state-only predicate"},
	{"STA-7", "assumption-with-target", mod("Assumptions { A on E to t: true; }", "state t: Bool = false;", "event E();"), "only Hazard may declare a response target ('A')"},
	{"STA-7", "requirement-unknown-event", mod("Assumptions { A on Nope: true; }"), "requirement 'A' references unknown event 'Nope'"},
	{"STA-7", "requirement-not-bool", mod("Invariants { I: 1 + 1; }"), "Invariant 'I' must have type Bool"},
	{"STA-7", "requirement-unknown-literal", mod("Invariants { I: Unknown; }"), "Invariant 'I' must have type Bool"},
	{"STA-8", "rule-unknown-event", mod("", "", "", "rule R on Nope { }"), "rule 'R' references unknown event 'Nope'"},
	{"STA-9", "change-unknown-state", mod("", "", "", "rule R on change(q) { }"), "change rule 'R' watches unknown state"},
	{"STA-9", "change-repeated-state-allowed", mod("", "state x: Int32 = 0;", "", "rule R on change(x, x) { }"), ""},
	{"STA-10", "guard-not-bool", mod("", "", "event E();", "rule R on E when 1 { }"), "guard of rule 'R' must have type Bool"},
	{"STA-10", "write-undeclared", mod("", "", "event E();", "rule R on E { set q := 1; }"), "rule 'R' writes undeclared state 'q'"},
	{"STA-10", "write-type-mismatch", mod("", "state x: Int32 = 0;", "event E();", "rule R on E { set x := true; }"), "assignment to 'x' has type KType(name='Bool', unit=None), expected KType(name='Int32', unit=None)"},
	{"STA-10", "several-writes-same-state-ok", mod("", "state x: Int32 = 0;", "event E();", "rule R on E { set x := 1; set x := 2; }"), ""},
	{"STA-11", "covers-ok", mod("Hazards { H on E to t: p > 10; }", "state t: Bool = false;", "event E(p: Int32);", "rule R on reject E when p > 10 covers H { set t := true; }"), ""},
	{"STA-11", "covers-not-reject-ok", mod("Hazards { H on E to t: p > 10; }", "state t: Bool = false;", "event E(p: Int32);", "rule R on E when p > 10 covers H { set t := true; }"), ""},
	{"STA-11", "covers-swapped-operands", mod("Hazards { H on E to t: p > 10; }", "state t: Bool = false;", "event E(p: Int32);", "rule R on reject E when 10 < p covers H { set t := true; }"), "rule 'R' does not exactly implement hazard guard"},
	{"STA-11", "covers-redundant-parens-equal", mod("Hazards { H on E to t: p > 10; }", "state t: Bool = false;", "event E(p: Int32);", "rule R on reject E when (p > 10) covers H { set t := true; }"), ""},
	{"STA-11", "covers-unknown-hazard", mod("Hazards { H on E to t: p > 10; }", "state t: Bool = false;", "event E(p: Int32);", "rule R on reject E when p > 10 covers Z { set t := true; }"), "rule 'R' covers unknown hazard 'Z'"},
	{"STA-11", "covers-wrong-event", mod("Hazards { H on E to t: p > 10; }", "state t: Bool = false;", "event E(p: Int32); event F(p: Int32);", "rule R on reject F when p > 10 covers H { set t := true; }"), "rule 'R' does not exactly implement hazard guard"},
	{"STA-11", "covers-target-false", mod("Hazards { H on E to t: p > 10; }", "state t: Bool = false;", "event E(p: Int32);", "rule R on reject E when p > 10 covers H { set t := false; }"), "hazard rule 'R' must set target 't' to true"},
	{"STA-12", "hazard-without-covers", mod("Hazards { Zed on E to t: true; Alpha on E to t: true; }", "state t: Bool = false;", "event E();"), "hazards without a covers rule: Alpha, Zed"},
	{"STA-13", "assert-unknown-event", mod("", "", "", "", "assert A on Nope expect true;"), "assert 'A' references unknown event 'Nope'"},
	{"STA-13", "assert-guard-not-bool", mod("", "", "event E();", "", "assert A on E when 1 expect true;"), "guard of assert 'A' must have type Bool"},
	{"STA-13", "step-missing-argument", mod("", "", "event E(p: Int32);", "", "scenario S { step E(); }"), "scenario 'S' step 'E' arguments do not match event parameters"},
	{"STA-13", "step-extra-argument", mod("", "", "event E();", "", "scenario S { step E(q: 1); }"), "scenario 'S' step 'E' arguments do not match event parameters"},
	{"STA-13", "step-argument-type", mod("", "", "event E(p: Int32);", "", "scenario S { step E(p: true); }"), "scenario 'S' argument 'p' type KType(name='Bool', unit=None) incompatible with KType(name='Int32', unit=None)"},
	{"STA-13", "step-duplicate-argument-d-k5", mod("", "", "event E(p: Int32);", "", "scenario S { step E(p: 1, p: 2); }"), ""},
	{"STA-13", "expect-not-bool", mod("", "", "", "", "scenario S { expect 1; }"), "scenario 'S' expect expression must have type Bool"},
	{"STA-13", "step-argument-sees-states-only", mod("", "", "event E(p: Int32);", "", "scenario S { step E(p: p); }"), "unresolved name 'p'"},
}

func TestRuleTable(t *testing.T) {
	rejected := map[string]bool{}
	for _, c := range ruleTable {
		t.Run(c.rule+"/"+c.name, func(t *testing.T) {
			_, err := Parse(c.src)
			switch {
			case c.want == "":
				if err != nil {
					t.Fatalf("want accepted, got %v", err)
				}
			case c.want == "!crash":
				var e *Error
				if !errors.As(err, &e) || e.Code == "" {
					t.Fatalf("want coded error for a reference crash, got %v", err)
				}
				rejected[c.rule] = true
			default:
				var e *Error
				if !errors.As(err, &e) {
					t.Fatalf("want error %q, got %v", c.want, err)
				}
				if e.Code != "" || e.Msg != c.want {
					t.Fatalf("error mismatch:\n got %q (code %q)\nwant %q", e.Msg, e.Code, c.want)
				}
				rejected[c.rule] = true
			}
		})
	}
	// Negative control: every rule family must be exercised by a rejecting case.
	for _, rule := range []string{"LEX-1", "LEX-2", "LEX-3", "LEX-4", "LEX-5", "SYN-1", "SYN-2", "SYN-3", "SYN-4", "SYN-5",
		"SYN-6", "SYN-7", "STA-1", "STA-2", "STA-4", "STA-5", "STA-7", "STA-8", "STA-9", "STA-10", "STA-11", "STA-12", "STA-13",
		"T-Not", "T-Logic", "T-Neg", "T-Rel", "T-Add", "T-Mul", "T-Div", "T-Gcd"} {
		if !rejected[rule] {
			t.Errorf("rule %s has no negative case", rule)
		}
	}
}

func TestPhaseAliasFlag(t *testing.T) {
	for _, alias := range []string{"•", "(*)"} {
		m := mustParse(t, mod("Invariants { I: "+alias+" a; }", "state a: Bool = true;"))
		if !m.PhaseAliasesUsed {
			t.Errorf("%q: PhaseAliasesUsed not set", alias)
		}
		u, ok := m.Requirements[0].Expression.(Unary)
		if !ok || u.Op != "not" {
			t.Errorf("%q: want unary not, got %#v", alias, m.Requirements[0].Expression)
		}
	}
	if m := mustParse(t, mod("Invariants { I: not a; }", "state a: Bool = true;")); m.PhaseAliasesUsed {
		t.Error("plain not must not set PhaseAliasesUsed")
	}
}

func TestTokenizeAliasOrder(t *testing.T) {
	toks, err := Tokenize("a<-1")
	if err != nil {
		t.Fatal(err)
	}
	var kinds []string
	for _, tk := range toks[:3] {
		kinds = append(kinds, tk.Kind)
	}
	if got := strings.Join(kinds, ","); got != "ID,ALIAS_WRITE,NUMBER" {
		t.Fatalf("a<-1 tokens = %s", got)
	}
	toks, _ = Tokenize("f((*)x)")
	var vals []string
	for _, tk := range toks {
		vals = append(vals, tk.Kind+":"+tk.Value)
	}
	if got := strings.Join(vals, " "); got != "ID:f PUNCT:( ALIAS_PHASE:ALIAS_PHASE ID:x PUNCT:) EOF:" {
		t.Fatalf("f((*)x) tokens = %s", got)
	}
	if toks, _ := Tokenize("x\n  y"); toks[1].Line != 2 || toks[1].Column != 3 {
		t.Fatalf("position of y = %d:%d, want 2:3", toks[1].Line, toks[1].Column)
	}
}

// The 45 reserved words of KPOL-LEX-5 must equal the specification's list.
func TestReservedWordsMatchSpecification(t *testing.T) {
	data, err := os.ReadFile("../../../specifications/kpol/kpol-formal-specification.md")
	if err != nil {
		t.Skipf("specification not available: %v", err)
	}
	m := regexp.MustCompile("(?s)KPOL-LEX-5.*?```text\n(.*?)```").FindSubmatch(data)
	if m == nil {
		t.Fatal("KPOL-LEX-5 block not found")
	}
	want := strings.Fields(string(m[1]))
	var got []string
	for w := range reservedWords {
		got = append(got, w)
	}
	sort.Strings(got)
	sort.Strings(want)
	if len(want) != 45 || strings.Join(got, " ") != strings.Join(want, " ") {
		t.Fatalf("reserved words differ from the specification:\n go  %v\n spec %v", got, want)
	}
}

func TestAnnexAExamples(t *testing.T) {
	cases := []struct {
		file      string
		initState int64 // W0 of CID 0 in the Annex A descriptor
		proof     bool
	}{
		{"increase.kpol", 10, false},
		{"decrease.kpol", 10, false},
		{"cascade_4concept.kpol", 10, true},
		{"bms_safety_cascade.kpol", 0, true},
	}
	for _, c := range cases {
		data, err := os.ReadFile("../../vmk-go/examples/" + c.file)
		if err != nil {
			t.Skipf("examples not available: %v", err)
		}
		m := mustParse(t, string(data))
		if m.ProofPresent != c.proof {
			t.Errorf("%s: ProofPresent = %v, want %v", c.file, m.ProofPresent, c.proof)
		}
		st, err := InitialState(m)
		if err != nil {
			t.Fatalf("%s: %v", c.file, err)
		}
		first := m.States[0].Name
		if v, ok := st[first].(Int); !ok || func() int64 { n, _ := v.Int64(); return n }() != c.initState {
			t.Errorf("%s: initial %s = %v, want %d", c.file, first, st[first], c.initState)
		}
		rep, err := Verify(m)
		if err != nil || !rep.Passed() {
			t.Errorf("%s: Proof does not pass: %+v %v", c.file, rep, err)
		}
		if c.proof && rep.TotalChecks == 0 {
			t.Errorf("%s: Proof is vacuous", c.file)
		}
	}
}
