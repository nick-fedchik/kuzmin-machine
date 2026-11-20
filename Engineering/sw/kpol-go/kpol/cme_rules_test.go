package kpol

import (
	"errors"
	"fmt"
	"reflect"
	"strings"
	"testing"
)

const cme1Base = `Problem M { Invariants { NonNeg: S >= 0; } }
Solution M {
  state S: Int32 = 10;
  event E(P: Int32);
  rule Step on E when P < 20 { set S := S + 1; }
}
Proof M { scenario Trace { step E(P = 5); expect S == 11; step E(P: 25); expect S == 11; } }
`

const cme2Base = `Problem M { Invariants { IA: A >= 0; IB: B >= 0; } }
Solution M {
  state A: Int32 = 0;
  state B: Int32 = 0;
  event E(x: Int32);
  rule RA on E when x < 50 { set A := A + 1; }
  rule RB on change(A) when A > 0 { set B := B + 1; }
}
Proof M { scenario T { step E(x = 1); expect A == 1; expect B == 1; step E(x = 100); expect A == 1; expect B == 1; } }
`

const cme1ProofBlock = "Proof M { scenario Trace { step E(P = 5); expect S == 11; step E(P: 25); expect S == 11; } }\n"

// edit applies the replacements old1, new1, old2, new2, ... to base.
func edit(t testing.TB, base string, pairs ...string) string {
	t.Helper()
	for i := 0; i < len(pairs); i += 2 {
		if !strings.Contains(base, pairs[i]) {
			t.Fatalf("%q not found in the program", pairs[i])
		}
	}
	return strings.NewReplacer(pairs...).Replace(base)
}

// cme2One is a single-state KPOL-CME-2 program with the given guard and action.
func cme2One(guard, action, initial string) string {
	return fmt.Sprintf(`Problem M { Invariants { IA: A >= 0; } }
Solution M {
  state A: Int32 = %s;
  event E(x: Int32);
  rule RA on E when %s { set A := %s; }
}
Proof M { scenario T { step E(x = 7); expect A >= 0; } }
`, initial, guard, action)
}

func compileText(t testing.TB, src, profile string, opts ...CompileOption) ([]Descriptor, error) {
	t.Helper()
	m, err := ParseUnchecked(src)
	if err != nil {
		t.Fatalf("parse: %v\n%s", err, src)
	}
	return CompileProfileDescriptors(m, profile, opts...)
}

type ruleCase struct {
	rule    string // KPOL-P1-n / KPOL-P2-n, for the failure message
	name    string
	src     string
	profile string
	msg     string // exact diagnostic; empty if the program is accepted
	opts    []CompileOption
}

func runRuleCases(t *testing.T, cases []ruleCase) {
	t.Helper()
	for _, c := range cases {
		_, err := compileText(t, c.src, c.profile, c.opts...)
		switch {
		case c.msg == "" && err != nil:
			t.Errorf("%s %s: rejected: %v", c.rule, c.name, err)
		case c.msg != "" && err == nil:
			t.Errorf("%s %s: accepted; want %q", c.rule, c.name, c.msg)
		case c.msg != "" && err.Error() != c.msg:
			t.Errorf("%s %s:\n  got  %q\n  want %q", c.rule, c.name, err.Error(), c.msg)
		}
	}
}

// TestCMEProfile1Rules gives a positive and a negative case for each
// condition KPOL-P1-1..10 (KPOL-P1-11 is TestCMELowering1).
func TestCMEProfile1Rules(t *testing.T) {
	c1 := ProfileCME1
	runRuleCases(t, []ruleCase{
		{"KPOL-P1-1", "valid", cme1Base, c1, "", nil},
		{"KPOL-P1-1", "type error", edit(t, cme1Base, "= 10;", "= true;"), c1,
			"B3-TYPE: module M: initial value of 'S' has type KType(name='Bool', unit=None), expected KType(name='Int32', unit=None)", nil},
		{"KPOL-P1-2", "cascade_map absent", cme1Base, c1, "", nil},
		{"KPOL-P1-2", "empty cascade_map", cme1Base, c1, "B3-SHAPE: module M: cascade_map is outside KPOL-CME-1",
			[]CompileOption{WithCascadeMap(map[string]string{})}},
		{"KPOL-P1-2", "cascade_map", cme1Base, c1, "B3-SHAPE: module M: cascade_map is outside KPOL-CME-1",
			[]CompileOption{WithCascadeMap(map[string]string{"S": "0"})}},
		{"KPOL-P1-3", "one state, event, rule", cme1Base, c1, "", nil},
		{"KPOL-P1-3", "two states", edit(t, cme1Base, "event E", "state T: Int32 = 1; event E"), c1,
			"B3-SHAPE: module M: expected exactly one state, event and rule", nil},
		{"KPOL-P1-3", "Bool parameter", edit(t, cme1Base, "P: Int32", "P: Bool", "P < 20", "true", "step E(P = 5)", "step E(P = true)", "step E(P: 25)", "step E(P: false)"), c1,
			"B3-SHAPE: module M: event E: parameter P must be Int32", nil},
		{"KPOL-P1-3", "two parameters", edit(t, cme1Base, "P: Int32", "P: Int32, Q: Int32", "step E(P = 5)", "step E(P = 5, Q = 1)", "step E(P: 25)", "step E(P: 25, Q: 1)"), c1,
			"B3-SHAPE: module M: state S and event E: expected Int32 state and one parameter", nil},
		{"KPOL-P1-4", "initial 0", edit(t, cme1Base, "= 10;", "= 0;", "== 11", "== 1"), c1, "", nil},
		{"KPOL-P1-4", "initial 2147483647", edit(t, cme1Base, "= 10;", "= 2147483647;", "S == 11", "S == 2147483647", "step E(P = 5)", "step E(P = 50)"), c1, "", nil},
		{"KPOL-P1-4", "negative initial", edit(t, cme1Base, "= 10;", "= -1;"), c1,
			"B3-SHAPE: module M: state S initial: literal outside [0, 2147483647]", nil},
		{"KPOL-P1-4", "computed initial", edit(t, cme1Base, "= 10;", "= 5 + 5;"), c1,
			"B3-SHAPE: module M: state S initial: expected an Int32 literal", nil},
		{"KPOL-P1-5", "ordinary rule", cme1Base, c1, "", nil},
		{"KPOL-P1-5", "reject rule", edit(t, cme1Base, "on E when", "on reject E when"), c1,
			"B3-SHAPE: module M: rule Step: expected an ordinary rule on E", nil},
		{"KPOL-P1-5", "change rule", edit(t, cme1Base, "on E when P < 20", "on change(S) when true"), c1,
			"B3-SHAPE: module M: rule Step: expected an ordinary rule on E", nil},
		{"KPOL-P1-5", "two actions", edit(t, cme1Base, "set S := S + 1;", "set S := S + 1; set S := S + 1;"), c1,
			"B3-SHAPE: module M: rule Step: expected one assignment to S", nil},
		{"KPOL-P1-6", "S >= 0", cme1Base, c1, "", nil},
		{"KPOL-P1-6", "0 <= S", edit(t, cme1Base, "S >= 0;", "0 <= S;"), c1,
			"B3-INVARIANT: module M: expected only the invariant S >= 0", nil},
		{"KPOL-P1-6", "S > 0", edit(t, cme1Base, "S >= 0;", "S > 0;"), c1,
			"B3-INVARIANT: module M: expected only the invariant S >= 0", nil},
		{"KPOL-P1-6", "extra Goals", edit(t, cme1Base, "Invariants {", "Goals { G: S > 0; } Invariants {"), c1,
			"B3-INVARIANT: module M: expected only the invariant S >= 0", nil},
		{"KPOL-P1-6", "S >= 0.0 equals Literal(0)", edit(t, cme1Base, "S >= 0;", "S >= 0.0;"), c1, "", nil},
		{"KPOL-P1-7", "S - 1", edit(t, cme1Base, "S + 1;", "S - 1;", "== 11", "== 9"), c1, "", nil},
		{"KPOL-P1-7", "S + 2", edit(t, cme1Base, "S + 1;", "S + 2;"), c1,
			"B3-ACTION: module M: rule Step: expected S + 1 or S - 1", nil},
		{"KPOL-P1-7", "1 + S", edit(t, cme1Base, "S + 1;", "1 + S;"), c1,
			"B3-ACTION: module M: rule Step: expected S + 1 or S - 1", nil},
		{"KPOL-P1-7", "constant", edit(t, cme1Base, "S + 1;", "42;"), c1,
			"B3-ACTION: module M: rule Step: expected S + 1 or S - 1", nil},
		{"KPOL-P1-8", "true", edit(t, cme1Base, "P < 20", "true", cme1ProofBlock, ""), c1, "", nil},
		{"KPOL-P1-8", "P != -2147483648", edit(t, cme1Base, "P < 20", "P != -2147483648", cme1ProofBlock, ""), c1, "", nil},
		{"KPOL-P1-8", "false", edit(t, cme1Base, "P < 20", "false"), c1,
			"B3-GUARD: module M: rule Step: expected true or P compared with an Int32 literal", nil},
		{"KPOL-P1-8", "P >= 5", edit(t, cme1Base, "P < 20", "P >= 5"), c1,
			"B3-GUARD: module M: rule Step: expected true or P compared with an Int32 literal", nil},
		{"KPOL-P1-8", "K < P", edit(t, cme1Base, "P < 20", "20 > P"), c1,
			"B3-GUARD: module M: rule Step: expected true or P compared with an Int32 literal", nil},
		{"KPOL-P1-8", "computed limit", edit(t, cme1Base, "P < 20", "P < 10 + 10"), c1,
			"B3-GUARD: module M: rule Step guard: expected an Int32 literal", nil},
		{"KPOL-P1-8", "limit overflow", edit(t, cme1Base, "P < 20", "P < 2147483648"), c1,
			"B3-TYPE: module M: incompatible comparison: KType(name='Int32', unit=None) < KType(name='Number', unit=None)", nil},
		{"KPOL-P1-9", "scenario", cme1Base, c1, "", nil},
		{"KPOL-P1-9", "no Proof", edit(t, cme1Base, "Proof M { scenario Trace { step E(P = 5); expect S == 11; step E(P: 25); expect S == 11; } }\n", ""), c1, "", nil},
		{"KPOL-P1-9", "empty Proof", edit(t, cme1Base, "scenario Trace { step E(P = 5); expect S == 11; step E(P: 25); expect S == 11; }", ""), c1,
			"B3-PROOF: module M: Proof must contain at least one scenario", nil},
		{"KPOL-P1-9", "assert", edit(t, cme1Base, "scenario Trace { step E(P = 5); expect S == 11; step E(P: 25); expect S == 11; }", "assert A on E expect S >= 0;"), c1,
			"B3-PROOF: module M: only scenario is supported, not Proof/assert", nil},
		{"KPOL-P1-9", "no expect", edit(t, cme1Base, "expect S == 11; step E(P: 25); expect S == 11;", ""), c1,
			"B3-PROOF: module M: scenario Trace: expected at least one step and expect", nil},
		{"KPOL-P1-9", "expect before step", edit(t, cme1Base, "step E(P = 5); expect S == 11;", "expect S == 10; step E(P = 5);"), c1,
			"B3-PROOF: module M: scenario Trace: expected S == integer after a step", nil},
		{"KPOL-P1-9", "wrong expectation", edit(t, cme1Base, "S == 11; step", "S == 12; step"), c1,
			"B3-PROOF: module M: Proof failed: Trace: Expectation failed at step 2: state={'S': 11}", nil},
		{"KPOL-P1-9", "Unknown argument", edit(t, cme1Base, "P = 5", "P = Unknown"), c1,
			"B3-PROOF: module M: scenario Trace: expected an Int32 literal", nil},
		{"KPOL-P1-9", "wrong argument name", edit(t, cme1Base, "P = 5", "Q = 5"), c1,
			"B3-TYPE: module M: scenario 'Trace' step 'E' arguments do not match event parameters", nil},
		{"KPOL-P1-10", "ACL passes", cme1Base, c1, "", []CompileOption{WithACL(map[string]int{"S": CapRead | CapWrite})}},
		{"KPOL-P1-10", "ACL without CAP_WRITE", cme1Base, c1,
			"B3-ACL: module M: ACL violation: rule 'Step' writes to state 'S' without CAP_WRITE capability",
			[]CompileOption{WithACL(map[string]int{"S": CapRead})}},
	})
}

// TestCMEProfile2Rules gives a positive and a negative case for each
// condition KPOL-P2-1..18 (KPOL-P2-19 is TestCMELowering2).
func TestCMEProfile2Rules(t *testing.T) {
	c2 := ProfileCME2
	oneState := func(guard, action string) string { return cme2One(guard, action, "0") }
	runRuleCases(t, []ruleCase{
		{"KPOL-P2-1", "valid", cme2Base, c2, "", nil},
		{"KPOL-P2-1", "type error", edit(t, cme2Base, "A: Int32 = 0", "A: Int32 = true"), c2,
			"CME2-TYPE: module M: initial value of 'A' has type KType(name='Bool', unit=None), expected KType(name='Int32', unit=None)", nil},
		{"KPOL-P2-2", "cascade_map", cme2Base, c2, "CME2-CASCADE: module M: cascade_map is outside KPOL-CME-2; declare cascades via 'on change(State)'",
			[]CompileOption{WithCascadeMap(map[string]string{"A": "B"})}},
		{"KPOL-P2-3", "not", edit(t, cme2Base, "x < 50", "not (x >= 50)"), c2, "", nil},
		{"KPOL-P2-3", "• alias", edit(t, cme2Base, "x < 50", "• (x >= 50)"), c2,
			"CME2-GUARD: module M: phase/dot alias ('•' or '(*)') is outside KPOL-CME-2 (#186); use 'not'", nil},
		{"KPOL-P2-3", "(*) alias", edit(t, cme2Base, "x < 50", "(*) (x >= 50)"), c2,
			"CME2-GUARD: module M: phase/dot alias ('•' or '(*)') is outside KPOL-CME-2 (#186); use 'not'", nil},
		{"KPOL-P2-4", "invariants only", cme2Base, c2, "", nil},
		{"KPOL-P2-4", "Assumption", edit(t, cme2Base, "Invariants {", "Assumptions { Ok: A >= 0; } Invariants {"), c2,
			"CME2-GUARD: module M: assumption Ok: declare preconditions in rule 'when' guards", nil},
		{"KPOL-P2-4", "Goal", edit(t, cme2Base, "Invariants {", "Goals { G: A >= 0; } Invariants {"), c2,
			"CME2-INVARIANT: module M: requirement G (Goal) is outside KPOL-CME-2", nil},
		{"KPOL-P2-5", "one state", cme2One("x < 5", "A + 1", "0"), c2, "", nil},
		{"KPOL-P2-5", "initial 2147483647", cme2One("x < 5", "A + 1", "2147483647"), c2, "", nil},
		{"KPOL-P2-5", "negative initial", cme2One("x < 5", "A + 1", "-1"), c2,
			"CME2-INVARIANT: module M: state A: initial value -1 violates invariant A >= 0", nil},
		{"KPOL-P2-5", "initial out of range", cme2One("x < 5", "A + 1", "2147483648"), c2,
			"CME2-TYPE: module M: initial value of 'A' has type KType(name='Number', unit=None), expected KType(name='Int32', unit=None)", nil},
		{"KPOL-P2-5", "state type", edit(t, cme2Base, "B: Int32", "B: U32"), c2,
			"CME2-TYPE: module M: state B: expected Int32", nil},
		{"KPOL-P2-6", "one parameter", cme2Base, c2, "", nil},
		{"KPOL-P2-6", "two parameters", edit(t, cme2Base, "x: Int32", "x: Int32, y: Int32", "step E(x = 1)", "step E(x = 1, y = 0)", "step E(x = 100)", "step E(x = 100, y = 0)"), c2,
			"CME2-SHAPE: module M: event E: expected exactly one Int32 parameter", nil},
		{"KPOL-P2-6", "parameter type", edit(t, cme2Base, "x: Int32", "x: U32"), c2,
			"CME2-TYPE: module M: event E: parameter x must be Int32", nil},
		{"KPOL-P2-7", "one rule per state", cme2Base, c2, "", nil},
		{"KPOL-P2-7", "reject", edit(t, cme2Base, "on E when", "on reject E when"), c2,
			"CME2-SHAPE: module M: rule RA: 'on reject' and 'covers' are outside KPOL-CME-2", nil},
		{"KPOL-P2-7", "two actions", edit(t, cme2Base, "set A := A + 1;", "set A := A + 1; set B := B + 1;"), c2,
			"CME2-SHAPE: module M: rule RA: expected exactly one set action", nil},
		{"KPOL-P2-7", "state without rule", edit(t, cme2Base, "rule RB on change(A) when A > 0 { set B := B + 1; }", ""), c2,
			"CME2-SHAPE: module M: states without rules: B", nil},
		{"KPOL-P2-7", "two rules for a state", edit(t, cme2Base, "rule RB on change(A) when A > 0 { set B := B + 1; }", "rule RB on change(A) when A > 0 { set B := B + 1; } rule RC on change(A) when A > 5 { set B := B + 2; }"), c2,
			"CME2-SHAPE: module M: state B: expected exactly one rule per state", nil},
		{"KPOL-P2-8", "single watched state", cme2Base, c2, "", nil},
		{"KPOL-P2-8", "two watched states", edit(t, cme2Base, "change(A)", "change(A, B)"), c2,
			"CME2-SHAPE: module M: rule RB: expected single-state on change(State)", nil},
		{"KPOL-P2-8", "event used twice", edit(t, cme2Base, "rule RB on change(A) when A > 0", "rule RB on E when x > 70"), c2,
			"CME2-SHAPE: module M: event E: bound to multiple rules; CME-RAW-1 dispatches one CID per event", nil},
		{"KPOL-P2-8", "unused event", edit(t, cme2Base, "event E(x: Int32);", "event E(x: Int32); event F(y: Int32);"), c2,
			"CME2-SHAPE: module M: unused event declarations: F", nil},
		{"KPOL-P2-9", "S >= 0 and 0 <= S", edit(t, cme2Base, "IA: A >= 0;", "IA: 0 <= A;"), c2, "", nil},
		{"KPOL-P2-9", "missing invariant", edit(t, cme2Base, " IB: B >= 0;", ""), c2,
			"CME2-INVARIANT: module M: missing 'State >= 0' invariant for: B", nil},
		{"KPOL-P2-9", "duplicate invariant", edit(t, cme2Base, "IB: B >= 0;", "IB: B >= 0; IC: A >= 0;"), c2,
			"CME2-INVARIANT: module M: invariant IC: expected unique 'State >= 0' per declared state", nil},
		{"KPOL-P2-9", "strict inequality", edit(t, cme2Base, "IB: B >= 0;", "IB: B > 0;"), c2,
			"CME2-INVARIANT: module M: invariant IB: expected unique 'State >= 0' per declared state", nil},
		{"KPOL-P2-9", "S >= 0.0 is not an int literal", edit(t, cme2Base, "IB: B >= 0;", "IB: B >= 0.0;"), c2,
			"CME2-INVARIANT: module M: invariant IB: expected unique 'State >= 0' per declared state", nil},
		{"KPOL-P2-10", "chain", cme2Base, c2, "", nil},
		{"KPOL-P2-10", "self-loop", edit(t, cme2Base, "rule RB on change(A) when A > 0 { set B := B + 1; }", "rule RB on change(B) when B > 5 { set B := B + 1; } rule RC on change(A) when A > 5 { set A := A + 1; }"), c2,
			"CME2-SHAPE: module M: state A: expected exactly one rule per state", nil},
		{"KPOL-P2-10", "self-subscription", edit(t, cme2Base, "rule RA on E when x < 50 { set A := A + 1; }", "rule RA on change(A) when A > 100 { set A := A + 1; } rule RE on E when x < 50 { set B := B + 1; }", "rule RB on change(A) when A > 0 { set B := B + 1; }", ""), c2,
			"CME2-CASCADE: module M: rule RA: self-subscription on A is forbidden", nil},
		{"KPOL-P2-10", "fan-out", `Problem M { Invariants { IA: A >= 0; IB: B >= 0; IC: C >= 0; } }
Solution M {
  state A: Int32 = 0; state B: Int32 = 0; state C: Int32 = 0;
  event E(x: Int32);
  rule RA on E when x < 50 { set A := A + 1; }
  rule RB on change(A) when A > 0 { set B := B + 1; }
  rule RC on change(A) when A > 0 { set C := C + 1; }
}
Proof M { scenario T { step E(x = 1); expect A == 1; } }
`, c2, "CME2-CASCADE: module M: state A: cascade fan-out > 1 (B, C) exceeds single-slot cascade_pending in CME-RAW-1", nil},
		{"KPOL-P2-10", "cycle", `Problem M { Invariants { IA: A >= 0; IB: B >= 0; } }
Solution M {
  state A: Int32 = 0; state B: Int32 = 0;
  rule RA on change(B) when B > 100 { set A := A + 1; }
  rule RB on change(A) when A > 100 { set B := B + 1; }
}
Proof M { scenario T { expect A == 0; } }
`, c2, "CME2-CASCADE: module M: cyclic cascade detected involving A", nil},
		{"KPOL-P2-11", "x op K", oneState("x >= -5", "A + 1"), c2, "", nil},
		{"KPOL-P2-11", "K op x", oneState("5 < x", "A + 1"), c2, "", nil},
		{"KPOL-P2-11", "not not", oneState("not not (x == 3)", "A + 1"), c2, "", nil},
		{"KPOL-P2-11", "literal", oneState("false", "A + 1"), c2, "", nil},
		{"KPOL-P2-11", "range", oneState("x >= 1 and x <= 5", "A + 1"), c2, "", nil},
		{"KPOL-P2-11", "or", oneState("x < 5 or x > 9", "A + 1"), c2,
			"CME2-GUARD: module M: rule RA: unsupported guard expression in KPOL-CME-2", nil},
		{"KPOL-P2-11", "state in guard", edit(t, cme2Base, "when x < 50", "when A < 50"), c2,
			"CME2-GUARD: module M: rule RA: guard must compare input x with an integer literal", nil},
		{"KPOL-P2-11", "arithmetic", oneState("x + 1 < 5", "A + 1"), c2,
			"CME2-GUARD: module M: rule RA: guard must compare input x with an integer literal", nil},
		{"KPOL-P2-11", "compound not", oneState("not (x < 5) and x > 1", "A + 1"), c2,
			"CME2-GUARD: module M: rule RA: expected comparison on x", nil},
		{"KPOL-P2-12", "int16 range", oneState("x >= -32768 and x <= 32767", "A + 1"), c2, "", nil},
		{"KPOL-P2-12", "reduced bounds", oneState("x > -32769 and x < 32768", "A + 1"), c2, "", nil},
		{"KPOL-P2-12", "above int16", oneState("x >= 0 and x <= 32768", "A + 1"), c2,
			"CME2-RANGE: module M: rule RA: range [0, 32768] outside int16 [-32768, 32767] or inverted", nil},
		{"KPOL-P2-12", "inverted", oneState("x >= 6 and x <= 5", "A + 1"), c2,
			"CME2-RANGE: module M: rule RA: range [6, 5] outside int16 [-32768, 32767] or inverted", nil},
		{"KPOL-P2-12", "empty after reduction", oneState("x > 5 and x < 6", "A + 1"), c2,
			"CME2-RANGE: module M: rule RA: range [6, 5] outside int16 [-32768, 32767] or inverted", nil},
		{"KPOL-P2-12", "two lower bounds", oneState("x > 1 and x >= 5", "A + 1"), c2,
			"CME2-RANGE: module M: rule RA: duplicate lower bound", nil},
		{"KPOL-P2-12", "equality in range", oneState("x == 1 and x < 5", "A + 1"), c2,
			"CME2-RANGE: module M: rule RA: range requires lower (>, >=) and upper (<, <=) bounds", nil},
		{"KPOL-P2-13", "assign x", oneState("true", "x"), c2, "", nil},
		{"KPOL-P2-13", "K + S", oneState("true", "7 + A"), c2, "", nil},
		{"KPOL-P2-13", "S - K", oneState("true", "A - 2147483647"), c2, "", nil},
		{"KPOL-P2-13", "constant", oneState("true", "5"), c2,
			"CME2-ACTION: module M: rule RA: expected 'x' or 'A +/- <1..2147483647>' (constant literal assignment requires CME-RAW-2, #185)", nil},
		{"KPOL-P2-13", "zero step", oneState("true", "A + 0"), c2,
			"CME2-ACTION: module M: rule RA action: literal 0 outside [1, 2147483647]", nil},
		{"KPOL-P2-13", "K - S", oneState("true", "2 - A"), c2,
			"CME2-ACTION: module M: rule RA: arithmetic action must update A", nil},
		{"KPOL-P2-13", "negative step", oneState("true", "A + -1"), c2,
			"CME2-ACTION: module M: rule RA action: literal -1 outside [1, 2147483647]", nil},
		{"KPOL-P2-14", "step publisher", cme2Base, c2, "", nil},
		{"KPOL-P2-14", "assign publisher", edit(t, cme2Base, "set A := A + 1;", "set A := x;"), c2,
			"CME2-CASCADE: module M: state A: cascade publisher must use a non-zero step action (+/- k) so CME-RAW-1 commit coincides with KPOL change()", nil},
		{"KPOL-P2-15", "guard false at load", cme2Base, c2, "", nil},
		{"KPOL-P2-15", "guard true at load", edit(t, cme2Base, "when A > 0", "when A >= 0"), c2,
			"CME2-CASCADE: module M: rule RB: on change(A) guard is active on initial state (0); CME-RAW-1 does not trigger cascades at load time", nil},
		{"KPOL-P2-15", "literal true guard", edit(t, cme2Base, "when A > 0", "when true"), c2,
			"CME2-CASCADE: module M: rule RB: on change(A) guard is active on initial state (0); CME-RAW-1 does not trigger cascades at load time", nil},
		{"KPOL-P2-16", "step without guard operand", oneState("true", "A + 5"), c2, "", nil},
		{"KPOL-P2-16", "guard literal with step 1", oneState("x < 5", "A + 1"), c2, "", nil},
		{"KPOL-P2-16", "guard literal with step 5", oneState("x < 5", "A + 5"), c2,
			"CME2-OPERAND-COLLISION: module M: rule RA: CME-RAW-1 shares one 32-bit operand_val between guard literal and ADD/SUB != 1 (#185)", nil},
		{"KPOL-P2-16", "range with SUB", oneState("x > 0 and x < 9", "A - 5"), c2,
			"CME2-OPERAND-COLLISION: module M: rule RA: CME-RAW-1 shares one 32-bit operand_val between guard literal and ADD/SUB != 1 (#185)", nil},
		{"KPOL-P2-17", "Proof", cme2Base, c2, "", nil},
		{"KPOL-P2-17", "expect-only Proof", edit(t, cme2Base, "step E(x = 1); expect A == 1; expect B == 1; step E(x = 100); expect A == 1; expect B == 1;", "expect A == 0;"), c2, "", nil},
		{"KPOL-P2-17", "no Proof", edit(t, cme2Base, "Proof M { scenario T { step E(x = 1); expect A == 1; expect B == 1; step E(x = 100); expect A == 1; expect B == 1; } }\n", ""), c2,
			"CME2-PROOF: module M: KPOL-CME-2 requires a non-empty Proof block", nil},
		{"KPOL-P2-17", "empty Proof", edit(t, cme2Base, "scenario T { step E(x = 1); expect A == 1; expect B == 1; step E(x = 100); expect A == 1; expect B == 1; }", ""), c2,
			"CME2-PROOF: module M: KPOL-CME-2 requires a non-empty Proof block", nil},
		{"KPOL-P2-17", "failing Proof", edit(t, cme2Base, "expect B == 1; step", "expect B == 2; step"), c2,
			"CME2-PROOF: module M: Proof failed: T: Expectation failed at step 3: state={'A': 1, 'B': 1}", nil},
		{"KPOL-P2-17", "zero checks", edit(t, cme2Base, "step E(x = 1); expect A == 1; expect B == 1; step E(x = 100); expect A == 1; expect B == 1;", "step E(x = 1);"), c2,
			"CME2-PROOF: module M: Proof failed: M: Vacuous Proof: declared Proof items evaluated zero executable checks", nil},
		{"KPOL-P2-17", "runtime error", edit(t, cme2Base, "step E(x = 1);", "step E(x = 1 / 0);"), c2,
			"CME2-PROOF: module M: reference execution failed: division by zero", nil},
		{"KPOL-P2-18", "ACL passes", cme2Base, c2, "", []CompileOption{WithACL(map[string]int{"A": 3, "B": 2})}},
		{"KPOL-P2-18", "ACL without CAP_WRITE", cme2Base, c2,
			"CME2-ACL: module M: ACL violation: rule 'RB' writes to state 'B' without CAP_WRITE capability",
			[]CompileOption{WithACL(map[string]int{"B": CapRead})}},
		{"KPOL-P2-18", "ACL after Proof", edit(t, cme2Base, "expect B == 1; step", "expect B == 2; step"), c2,
			"CME2-PROOF: module M: Proof failed: T: Expectation failed at step 3: state={'A': 1, 'B': 1}",
			[]CompileOption{WithACL(map[string]int{"B": 0})}},
	})
}

// lowering returns the expected descriptor fields of a comparison guard
// (KPOL-P2-19): inv counts the outer `not`s.
func loweringOf(op string, k int64, nots int) (pred uint8, invert bool, operand uint32) {
	invert = nots%2 == 1
	switch op {
	case "==":
		pred = PredEQ
	case "!=":
		pred = PredNEQ
	case "<":
		pred = PredLT
	case ">":
		pred = PredGT
	case ">=":
		pred, invert = PredLT, !invert
	case "<=":
		pred, invert = PredGT, !invert
	}
	return pred, invert, uint32(int32(k))
}

var mirrorOp = map[string]string{"==": "==", "!=": "!=", "<": ">", ">": "<", "<=": ">=", ">=": "<="}

// TestCMELowering1 is KPOL-P1-11: CID 0 = {init, K or 0, pred, 0x03, 0, inc/dec, 0}.
func TestCMELowering1(t *testing.T) {
	preds := map[string]uint8{"<": PredLT, ">": PredGT, "==": PredEQ, "!=": PredNEQ}
	for _, init := range []int64{0, 10, 2147483647} {
		for _, step := range []struct {
			text string
			op   uint8
		}{{"S + 1", ActInc}, {"S - 1", ActDec}} {
			guards := []struct {
				text string
				pred uint8
				k    int64
			}{{"true", PredNOP, 0}}
			for op, p := range preds {
				for _, k := range []int64{-2147483648, -1, 0, 20, 2147483647} {
					guards = append(guards, struct {
						text string
						pred uint8
						k    int64
					}{fmt.Sprintf("P %s %d", op, k), p, k})
				}
			}
			for _, g := range guards {
				src := edit(t, cme1Base, "= 10;", fmt.Sprintf("= %d;", init), "P < 20", g.text, "S + 1;", step.text+";",
					cme1ProofBlock, "")
				ds, err := compileText(t, src, ProfileCME1)
				if err != nil {
					t.Fatalf("%s: %v", g.text, err)
				}
				want := Descriptor{CID: 0, Name: "S", CurrentState: uint32(init), OperandVal: uint32(int32(g.k)),
					PredOpcode: g.pred, GuardFlags: 0x03, ActionOpcode: step.op}
				if len(ds) != 1 || ds[0] != want {
					t.Fatalf("%s, %s, init %d: %+v, want %+v", g.text, step.text, init, ds, want)
				}
			}
		}
	}
	// Negative controls: the opposite comparison or step changes the slot.
	a, _ := compileText(t, cme1Base, ProfileCME1)
	b, _ := compileText(t, edit(t, cme1Base, "P < 20", "P > 20", cme1ProofBlock, ""), ProfileCME1)
	if a[0].PredOpcode == b[0].PredOpcode {
		t.Error("< and > lower to the same predicate")
	}
}

// TestCMELowering2 is KPOL-P2-19 for comparisons, ranges, actions and cascade wiring.
func TestCMELowering2(t *testing.T) {
	for _, op := range []string{"==", "!=", "<", ">", ">=", "<="} {
		for _, k := range []int64{0, 1, -1, 100, 2147483647, -2147483648} {
			for nots := 0; nots <= 3; nots++ {
				guard := fmt.Sprintf("x %s %d", op, k)
				if nots > 0 {
					guard = strings.Repeat("not ", nots) + "(" + guard + ")"
				}
				pred, inv, operand := loweringOf(op, k, nots)
				checkLowered(t, guard, "A + 1", pred, inv, operand, ActInc)
				if nots == 0 {
					// K op x is the mirrored x op' K
					pred, inv, operand := loweringOf(mirrorOp[op], k, 0)
					checkLowered(t, fmt.Sprintf("%d %s x", k, op), "A + 1", pred, inv, operand, ActInc)
				}
			}
		}
	}
	for _, r := range [][2]int64{{-32768, 32767}, {0, 0}, {-1, 1}, {5, 20}, {-100, -50}, {32767, 32767}} {
		want := uint32(uint16(r[1]))<<16 | uint32(uint16(r[0]))
		checkLowered(t, fmt.Sprintf("x >= %d and x <= %d", r[0], r[1]), "A + 1", PredRANGE, false, want, ActInc)
		checkLowered(t, fmt.Sprintf("not (x >= %d and x <= %d)", r[0], r[1]), "A + 1", PredRANGE, true, want, ActInc)
		checkLowered(t, fmt.Sprintf("x > %d and x < %d", r[0]-1, r[1]+1), "A + 1", PredRANGE, false, want, ActInc)
		checkLowered(t, fmt.Sprintf("%d <= x and %d >= x", r[0], r[1]), "A + 1", PredRANGE, false, want, ActInc)
	}
	checkLowered(t, "true", "x", PredNOP, false, 0, ActAssign)
	checkLowered(t, "false", "x", PredNOP, true, 0, ActAssign)
	checkLowered(t, "not false", "A - 1", PredNOP, false, 0, ActDec)
	checkLowered(t, "not true", "A + 2", PredNOP, true, 2, ActAdd)
	checkLowered(t, "true", "7 + A", PredNOP, false, 7, ActAdd)
	checkLowered(t, "true", "A - 2147483647", PredNOP, false, 2147483647, ActSub)
	checkLowered(t, "x < 5", "A - 1", PredLT, false, 5, ActDec)

	// Negative control: x >= K and x < K differ only in the invert flag.
	ge, _ := compileText(t, cme2One("x >= 5", "A + 1", "0"), ProfileCME2)
	lt, _ := compileText(t, cme2One("x < 5", "A + 1", "0"), ProfileCME2)
	if ge[0].PredOpcode != lt[0].PredOpcode || ge[0].GuardFlags^lt[0].GuardFlags != GuardInvertAssumption {
		t.Errorf(">= and < differ in more than the invert flag: %+v %+v", ge[0], lt[0])
	}
}

func checkLowered(t *testing.T, guard, action string, pred uint8, invert bool, operand uint32, act uint8) {
	t.Helper()
	ds, err := compileText(t, cme2One(guard, action, "3"), ProfileCME2)
	if err != nil {
		t.Errorf("%s / %s: %v", guard, action, err)
		return
	}
	flags := uint8(GuardAssumptionEn | GuardInvariantEn)
	if invert {
		flags |= GuardInvertAssumption
	}
	want := Descriptor{CID: 0, Name: "A", CurrentState: 3, OperandVal: operand, PredOpcode: pred, GuardFlags: flags, ActionOpcode: act}
	if len(ds) != 1 || ds[0] != want {
		t.Errorf("%s / %s: %+v, want %+v", guard, action, ds, want)
	}
}

// TestCMELoweringCascade covers publisher flag, subscriber CID and slot order.
func TestCMELoweringCascade(t *testing.T) {
	src := `Problem M { Invariants { IB: B >= 0; IA: A >= 0; IC: C >= 0; } }
Solution M {
  state B: Int32 = 4;
  state A: Int32 = 0;
  state C: Int32 = 9;
  event E(x: Int32);
  event F(y: Int32);
  rule RB on change(C) when C > 9 { set B := B - 1; }
  rule RA on E when x < 50 { set A := x; }
  rule RC on F when y > 0 { set C := C + 1; }
}
Proof M { scenario T { step F(y = 1); expect C == 10; expect B == 3; step E(x = 6); expect A == 6; } }
`
	ds, err := compileText(t, src, ProfileCME2)
	if err != nil {
		t.Fatal(err)
	}
	// C publishes to CID 0 (B): subscriber_cid is 0 and only flag bit 4 tells a
	// publisher from a plain concept.
	want := []Descriptor{
		{CID: 0, Name: "B", CurrentState: 4, OperandVal: 9, PredOpcode: PredGT, GuardFlags: 0x03, ActionOpcode: ActDec},
		{CID: 1, Name: "A", CurrentState: 0, OperandVal: 50, PredOpcode: PredLT, GuardFlags: 0x03, ActionOpcode: ActAssign},
		{CID: 2, Name: "C", CurrentState: 9, OperandVal: 0, PredOpcode: PredGT, GuardFlags: 0x13, ActionOpcode: ActInc, SubscriberCID: 0},
	}
	if !reflect.DeepEqual(ds, want) {
		t.Errorf("descriptors\n got  %+v\n want %+v", ds, want)
	}
}

func TestCMEMaxStates(t *testing.T) {
	build := func(n int) string {
		var b strings.Builder
		b.WriteString("Problem M { Invariants {")
		for i := 0; i < n; i++ {
			fmt.Fprintf(&b, " I%d: S%d >= 0;", i, i)
		}
		b.WriteString(" } }\nSolution M {\n")
		for i := 0; i < n; i++ {
			fmt.Fprintf(&b, "state S%d: Int32 = %d;\nevent E%d(p%d: Int32);\nrule R%d on E%d { set S%d := S%d + 1; }\n", i, i, i, i, i, i, i, i)
		}
		b.WriteString("}\nProof M { scenario T { step E0(p0 = 1); expect S0 == 1; } }\n")
		return b.String()
	}
	ds, err := compileText(t, build(64), ProfileCME2)
	if err != nil || len(ds) != 64 {
		t.Fatalf("64 states: %d descriptors, %v", len(ds), err)
	}
	img, _ := CompileProfile(mustParseUnchecked(t, build(64)), ProfileCME2)
	if len(img) != ImageSize || img[63*16] != 63 {
		t.Errorf("slot 63 is not programmed: % x", img[63*16:64*16])
	}
	if _, err := compileText(t, build(65), ProfileCME2); err == nil || err.Error() != "CME2-SHAPE: module M: expected 1..64 states, got 65" {
		t.Errorf("65 states: %v", err)
	}
	m := &Module{Name: "Empty"}
	if _, err := CompileProfile(m, ProfileCME2); err == nil || err.Error() != "CME2-SHAPE: module Empty: expected 1..64 states, got 0" {
		t.Errorf("no states: %v", err)
	}
}

// TestCMEUnsupportedProfile: the reference formats the name with Python's repr.
func TestCMEUnsupportedProfile(t *testing.T) {
	m := mustParseUnchecked(t, cme1Base)
	for name, want := range map[string]string{
		"":              "B3-PROFILE: unsupported profile ''",
		"unknown":       "B3-PROFILE: unsupported profile 'unknown'",
		"kpol-cme-1":    "B3-PROFILE: unsupported profile 'kpol-cme-1'",
		"it's":          `B3-PROFILE: unsupported profile "it's"`,
		"both ' and \"": `B3-PROFILE: unsupported profile 'both \' and "'`,
		"tab\t":         `B3-PROFILE: unsupported profile 'tab\t'`,
		"КПОЛ":          "B3-PROFILE: unsupported profile 'КПОЛ'",
	} {
		img, err := CompileProfile(m, name)
		var e *Error
		if img != nil || !errors.As(err, &e) || e.Code != "B3-PROFILE" || err.Error() != want {
			t.Errorf("%q: %v, want %s", name, err, want)
		}
	}
	// The profile is dispatched before anything else is looked at.
	if _, err := CompileProfile(nil, "x"); err == nil || err.Error() != "B3-PROFILE: unsupported profile 'x'" {
		t.Errorf("nil module: %v", err)
	}
}

func TestCMEOptions(t *testing.T) {
	m := mustParseUnchecked(t, cme1Base)
	if _, err := CompileProfile(m, ProfileCME1, WithCascadeMap(nil)); err != nil {
		t.Errorf("a nil cascade map is absent: %v", err)
	}
	if _, err := CompileProfile(m, ProfileCME1, WithACL(nil), WithACL(map[string]int{})); err != nil {
		t.Errorf("empty ACL: %v", err)
	}
	// Later options win.
	if _, err := CompileProfile(m, ProfileCME1, WithACL(map[string]int{"S": 0}), WithACL(map[string]int{"S": 3})); err != nil {
		t.Errorf("last ACL wins: %v", err)
	}
	// Only the first violated gate is reported: the type error precedes cascade_map.
	bad := mustParseUnchecked(t, edit(t, cme1Base, "= 10;", "= true;"))
	_, err := CompileProfile(bad, ProfileCME1, WithCascadeMap(map[string]string{}))
	var e *Error
	if !errors.As(err, &e) || e.Code != "B3-TYPE" {
		t.Errorf("gate order: %v", err)
	}
}

// TestCMENilAndHandBuilt covers inputs the parser cannot produce.
func TestCMENilAndHandBuilt(t *testing.T) {
	for _, p := range []string{ProfileCME1, ProfileCME2} {
		if _, err := CompileProfile(nil, p); err == nil {
			t.Errorf("%s: nil module accepted", p)
		}
	}
	// Unary "•" and "!" never come out of the parser; the static gate stops them first.
	for _, op := range []string{"•", "!"} {
		m := mustParseUnchecked(t, cme2Base)
		m.Rules[0].Guard = Unary{Op: op, X: Binary{Op: ">=", L: Name{"x"}, R: IntLit{V: bigOne}}}
		want := "CME2-TYPE: module M: invalid unary operation '" + op + "'"
		if _, err := CompileProfile(m, ProfileCME2); err == nil || err.Error() != want {
			t.Errorf("Unary %s: %v, want %s", op, err, want)
		}
	}
	// A change rule written as the interpreter keeps it: Event empty, Watch set.
	m := mustParseUnchecked(t, cme2Base)
	m.Rules[1].Event = ""
	want, _ := compileText(t, cme2Base, ProfileCME2)
	got, err := CompileProfileDescriptors(m, ProfileCME2)
	if err != nil || !reflect.DeepEqual(got, want) {
		t.Errorf("change rule without Event: %v", err)
	}
}

// TestCMECrashCodes: where the reference dies with an unhandled Python
// exception the port returns a coded error that is not a profile code.
func TestCMECrashCodes(t *testing.T) {
	src := edit(t, cme2Base, "step E(x = 1);", "step E(x = 5 / 2 + 1.0);")
	_, err := compileText(t, src, ProfileCME2)
	var e *Error
	if !errors.As(err, &e) || e.Code != CodeRTType {
		t.Errorf("float + Decimal in a Proof step: %v", err)
	}
}

func TestCMEDoesNotMutateModule(t *testing.T) {
	for _, p := range []struct{ src, profile string }{{cme1Base, ProfileCME1}, {cme2Base, ProfileCME2}} {
		m := mustParseUnchecked(t, p.src)
		first, err := CompileProfile(m, p.profile)
		if err != nil {
			t.Fatal(err)
		}
		second, err := CompileProfile(m, p.profile)
		if err != nil || string(first) != string(second) {
			t.Errorf("%s: second compile differs (%v)", p.profile, err)
		}
		if !reflect.DeepEqual(m, mustParseUnchecked(t, p.src)) {
			t.Errorf("%s: module was modified", p.profile)
		}
	}
}

func TestCheckSecurityACL(t *testing.T) {
	src := `Problem P { Invariants { I: S >= 0; } }
Solution P {
  state S: Int32 = 1;
  state Led: Pin<Out> = 0;
  state Mix: Pin<In,Out> = 1;
  state Inp: Pin<In> = 0;
  event E(x: Int32);
  rule R on E { set S := S + 1; set Led := 1; set Inp := 1; }
}
`
	m := mustParseUnchecked(t, src)
	pinState := func(n string) string {
		return fmt.Sprintf("ACL violation: state '%s' of type Pin<Out> requires CAP_PIN_OUT (0x04) capability", n)
	}
	const ledWrite = "ACL violation: rule 'R' writes to output pin 'Led' without CAP_PIN_OUT capability"
	for _, c := range []struct {
		name string
		acl  map[string]int
		want []string
	}{
		{"default capabilities", nil, []string{pinState("Led"), pinState("Mix"), ledWrite}},
		{"empty table", map[string]int{}, []string{pinState("Led"), pinState("Mix"), ledWrite}},
		{"pins granted", map[string]int{"Led": CapRead | CapWrite | CapPinOut, "Mix": CapPinOut}, nil},
		{"write revoked", map[string]int{"S": CapRead, "Led": CapPinOut, "Mix": CapPinOut},
			[]string{"ACL violation: rule 'R' writes to state 'S' without CAP_WRITE capability",
				"ACL violation: rule 'R' writes to state 'Led' without CAP_WRITE capability"}},
		{"unknown names are ignored", map[string]int{"Nope": 0, "Led": CapWrite | CapPinOut, "Mix": CapPinOut}, nil},
		{"negative mask", map[string]int{"Led": -1, "Mix": -1}, nil},
		{"locked bit only", map[string]int{"Led": CapLocked, "Mix": CapPinOut},
			[]string{pinState("Led"), "ACL violation: rule 'R' writes to state 'Led' without CAP_WRITE capability", ledWrite}},
	} {
		if got := CheckSecurityACL(m, c.acl); !reflect.DeepEqual(got, c.want) {
			t.Errorf("%s:\n got  %q\n want %q", c.name, got, c.want)
		}
	}
	if got := CheckSecurityACL(nil, nil); got != nil {
		t.Errorf("nil module: %q", got)
	}
}
