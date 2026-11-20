package kpol

import (
	"errors"
	"fmt"
	"math"
	"math/big"
	"strings"
	"testing"
)

func iv(n int64) Value { return NewInt(n) }

func ev(name string, kv ...any) EventInput {
	p := map[string]Value{}
	for i := 0; i < len(kv); i += 2 {
		p[kv[i].(string)] = kv[i+1].(Value)
	}
	return EventInput{Name: name, Payload: p}
}

func dec(t testing.TB, s string) Decimal {
	t.Helper()
	d, finite, err := ParseDecimal(s)
	if err != nil || !finite {
		t.Fatalf("ParseDecimal(%q): %v", s, err)
	}
	return d
}

func newInterp(t testing.TB, src string, opts ...Option) *Interpreter {
	t.Helper()
	in, err := NewInterpreter(mustParse(t, src), opts...)
	if err != nil {
		t.Fatalf("NewInterpreter: %v", err)
	}
	return in
}

func stateText(in *Interpreter) string {
	st := in.State()
	var parts []string
	for _, s := range in.m.States {
		parts = append(parts, s.Name+"="+FormatValue(st[s.Name]))
	}
	return strings.Join(parts, " ")
}

func runOK(t testing.TB, in *Interpreter, events ...EventInput) *RunResult {
	t.Helper()
	res, err := in.Run(events)
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	return res
}

func wantList(t testing.TB, what string, got []string, want ...string) {
	t.Helper()
	if strings.Join(got, "|") != strings.Join(want, "|") {
		t.Errorf("%s = %q, want %q", what, got, want)
	}
}

func wantErr(t testing.TB, err error, msg string) {
	t.Helper()
	var e *Error
	if !errors.As(err, &e) || e.Msg != msg {
		t.Fatalf("error = %v, want %q", err, msg)
	}
}

func evalText(t testing.TB, text string, env map[string]Value) (string, error) {
	t.Helper()
	p, err := newExprParser(text)
	if err != nil {
		t.Fatal(err)
	}
	e, err := p()
	if err != nil {
		t.Fatal(err)
	}
	v, err := EvalExpr(e, env)
	if err != nil {
		return "", err
	}
	return encodeValue(v), nil
}

// KPOL-DYN-3: strong Kleene logic, short-circuit evaluation, definitional
// equality with Unknown.
func TestEvalKleeneTables(t *testing.T) {
	env := map[string]Value{"t": Bool(true), "f": Bool(false), "u": Unknown{}, "z": iv(0), "n": iv(5)}
	cases := map[string]string{
		"t and t": "b:true", "t and f": "b:false", "t and u": "u",
		"f and t": "b:false", "f and f": "b:false", "f and u": "b:false",
		"u and t": "u", "u and f": "b:false", "u and u": "u",
		"t or t": "b:true", "t or f": "b:true", "t or u": "b:true",
		"f or t": "b:true", "f or f": "b:false", "f or u": "u",
		"u or t": "b:true", "u or f": "u", "u or u": "u",
		"not t": "b:false", "not f": "b:true", "not u": "u",
		"u == u": "b:true", "u == n": "b:false", "n == u": "b:false", "u != u": "b:false", "u != n": "b:true",
		"u < n": "u", "n >= u": "u", "u + 1": "u", "-u": "u",
		"f and 1 / z == 1": "b:false", "t or 1 / z == 1": "b:true",
		"gcd(12, 18)": "i:6", "gcd(u, 3)": "u", "gcd(0, 0)": "i:0",
		"7 / 2": "f:3.5", "6 / 3": "f:2.0", "1 / 3": "f:0.3333333333333333",
	}
	for text, want := range cases {
		got, err := evalText(t, text, env)
		if err != nil || got != want {
			t.Errorf("%s = %s (%v), want %s", text, got, err, want)
		}
	}
	for _, text := range []string{"t and 1 / z == 1", "f or 1 / z == 1", "n / z"} {
		if _, err := evalText(t, text, env); err == nil || err.Error() != "division by zero" {
			t.Errorf("%s: want division by zero, got %v", text, err)
		}
	}
	if _, err := evalText(t, "missing", env); err == nil || err.Error() != "unresolved runtime name 'missing'" {
		t.Errorf("unresolved name: %v", err)
	}
}

// KPOL-DYN-1 / DYN-2: domains, normalisation, Unknown handling.
func TestNormalize(t *testing.T) {
	big64 := new(big.Int).Lsh(big.NewInt(1), 64)
	cases := []struct {
		typ   TypeRef
		in    Value
		allow bool
		want  string // encodeValue of the result, or "!msg"
	}{
		{TypeRef{Name: "Bool"}, Bool(true), false, "b:true"},
		{TypeRef{Name: "Bool"}, iv(1), false, "!expected Bool value"},
		{TypeRef{Name: "Int32"}, iv(2147483647), false, "i:2147483647"},
		{TypeRef{Name: "Int32"}, iv(2147483648), false, "!expected Int32 value"},
		{TypeRef{Name: "Int32"}, iv(-2147483648), false, "i:-2147483648"},
		{TypeRef{Name: "Int32"}, iv(-2147483649), false, "!expected Int32 value"},
		{TypeRef{Name: "Int32"}, Bool(true), false, "!expected Int32 value"},
		{TypeRef{Name: "Int32"}, Float(2), false, "!expected Int32 value"},
		{TypeRef{Name: "U32"}, iv(-1), false, "!expected U32 value"},
		{TypeRef{Name: "U32"}, iv(4294967295), false, "i:4294967295"},
		{TypeRef{Name: "U64"}, NewBigInt(big64), false, "!expected U64 value"},
		{TypeRef{Name: "U64"}, NewBigInt(new(big.Int).Sub(big64, big.NewInt(1))), false, "i:18446744073709551615"},
		{TypeRef{Name: "Pin"}, Bool(true), false, "i:1"},
		{TypeRef{Name: "Pin"}, Bool(false), false, "i:0"},
		{TypeRef{Name: "Pin"}, iv(1), false, "i:1"},
		{TypeRef{Name: "Pin"}, iv(2), false, "!expected Pin value (0, 1, or Bool)"},
		{TypeRef{Name: "Float", Unit: "V"}, iv(3), false, "d:3"},
		{TypeRef{Name: "Float", Unit: "V"}, Float(2.5), false, "d:2.5"},
		{TypeRef{Name: "Float", Unit: "V"}, Float(1e16), false, "d:1E+16"},
		{TypeRef{Name: "Float", Unit: "V"}, Bool(true), false, "!expected finite Float value"},
		{TypeRef{Name: "Float", Unit: "V"}, Unknown{}, false, "!Unknown cannot be stored in a state"},
		{TypeRef{Name: "Int32"}, Unknown{}, true, "u"},
		{TypeRef{Name: "Weird"}, iv(1), false, "!unsupported runtime type 'Weird'"},
	}
	for _, c := range cases {
		got, err := normalize(c.in, c.typ, c.allow)
		text := ""
		if err != nil {
			text = "!" + err.Error()
		} else {
			text = encodeValue(got)
		}
		if text != c.want {
			t.Errorf("norm(%s, %s) = %s, want %s", FormatValue(c.in), c.typ.Name, text, c.want)
		}
	}
}

func TestInitialStateAndContracts(t *testing.T) {
	m := mustParse(t, mod("Invariants { I: x > 0; }", "state a: Int32 = 1; state f: Float<V> = 1 / 3; state x: Int32 = a - 1;"))
	st, err := InitialState(m)
	if err != nil {
		t.Fatal(err)
	}
	if encodeValue(st["a"]) != "i:1" || encodeValue(st["f"]) != "d:0.3333333333333333" || encodeValue(st["x"]) != "i:0" {
		t.Errorf("σ₀ = %v", st)
	}
	// InitialState does not check contracts; NewInterpreter does (KPOL-DYN-4 step 3).
	_, err = NewInterpreter(m)
	wantErr(t, err, "initial Invariant 'I' is not true")
	_, err = NewInterpreter(mustParse(t, mod("Assumptions { A: x > 0; B on E: x > 100; }", "state x: Int32 = 0;", "event E();")))
	wantErr(t, err, "initial Assumption 'A' is not true")
	// An assumption scoped to an event is not checked at start-up.
	if _, err = NewInterpreter(mustParse(t, mod("Assumptions { B on E: x > 100; }", "state x: Int32 = 0;", "event E();"))); err != nil {
		t.Fatal(err)
	}
	// D-K3: Int32 = 2.0 is accepted statically and rejected on initialisation.
	_, err = NewInterpreter(mustParse(t, mod("", "state x: Int32 = 2.0;")))
	wantErr(t, err, "expected Int32 value")
	// D-K2: dividing integers gives a binary float, which an integer state refuses.
	_, err = NewInterpreter(mustParse(t, mod("", "state x: Int32 = 4 / 2;")))
	wantErr(t, err, "expected Int32 value")
	_, err = NewInterpreter(mustParse(t, mod("", "state x: Int32 = Unknown;")))
	wantErr(t, err, "Unknown cannot be stored in a state")
}

func TestOverridesAndOptions(t *testing.T) {
	src := mod("", "state x: Int32 = 0; state y: Int32 = x + 1;")
	m := mustParse(t, src)
	in, err := NewInterpreter(m, WithOverrides(map[string]Value{"x": iv(5)}))
	if err != nil || stateText(in) != "x=5 y=6" {
		t.Fatalf("override x: %v %v", err, stateText(in))
	}
	in, _ = NewInterpreter(m, WithOverrides(map[string]Value{"y": iv(9)}))
	if stateText(in) != "x=0 y=9" {
		t.Errorf("override y: %s", stateText(in))
	}
	_, err = NewInterpreter(m, WithOverrides(map[string]Value{"q": iv(1), "p": iv(2)}))
	wantErr(t, err, "unknown initial state: p, q")
	_, err = NewInterpreter(m, WithOverrides(map[string]Value{"x": Unknown{}}))
	wantErr(t, err, "Unknown cannot be stored in a state")
	// The initialiser of an overridden state is still evaluated (reference behaviour).
	m2 := mustParse(t, mod("", "state x: Int32 = 1 / 0;"))
	_, err = NewInterpreter(m2, WithOverrides(map[string]Value{"x": iv(5)}))
	wantErr(t, err, "division by zero")
}

func TestRunLoopAndLimits(t *testing.T) {
	loop := mod("", "state a: Int32 = 0; state b: Int32 = 0;", "event E();",
		"rule T on E { set a := a + 1; } rule A on change(a) { set b := b + 1; } rule B on change(b) { set a := a + 1; }")
	in := newInterp(t, loop, WithMaxEvents(50))
	_, err := in.Run([]EventInput{ev("E")})
	wantErr(t, err, "event limit exceeded (50)")
	// The committed prefix of the aborted call stays in the interpreter state.
	if in.State()["a"].(Int).String() == "0" {
		t.Error("state of aborted run was rolled back")
	}
	in = newInterp(t, mod("", "state a: Int32 = 0;", "event E();", "rule T on E { set a := a + 1; }"))
	if res := runOK(t, in, ev("E"), ev("E"), ev("E")); res.Steps != 3 || stateText(in) != "a=3" {
		t.Errorf("steps=%d state=%s", res.Steps, stateText(in))
	}
	_, err = in.Run([]EventInput{ev("Nope")})
	wantErr(t, err, "unknown input event 'Nope'")
	_, err = in.Run([]EventInput{{Name: "change"}})
	wantErr(t, err, "invalid internal change event")
	_, err = in.Run([]EventInput{ev("E", "extra", iv(1))})
	wantErr(t, err, "payload for 'E' must contain exactly ")
}

// KPOL-DYN-5: the initial change events run exactly once, in the first call.
func TestInitialChangeEventsOnce(t *testing.T) {
	src := mod("", "state a: Int32 = 1; state n: Int32 = 0;", "event E();",
		"rule W on change(a) { set n := n + 1; } rule T on E { set a := a + 1; }")
	in := newInterp(t, src)
	if res := runOK(t, in); res.Steps != 1 || stateText(in) != "a=1 n=1" {
		t.Errorf("first run: steps=%d state=%s", res.Steps, stateText(in))
	}
	if res := runOK(t, in); res.Steps != 0 || stateText(in) != "a=1 n=1" {
		t.Errorf("second run: steps=%d state=%s", res.Steps, stateText(in))
	}
	runOK(t, in, ev("E"))
	if stateText(in) != "a=2 n=2" {
		t.Errorf("after E: %s", stateText(in))
	}
}

// KPOL-DYN-8: snapshot semantics, conflicts, unknown guards and writes,
// invariants, cascade order.
func TestTransactions(t *testing.T) {
	t.Run("simultaneous-assignment", func(t *testing.T) {
		in := newInterp(t, mod("", "state a: Int32 = 1; state b: Int32 = 2;", "event Swap();",
			"rule R on Swap { set a := b; set b := a; }"))
		runOK(t, in, ev("Swap"))
		if got := stateText(in); got != "a=2 b=1" {
			t.Errorf("swap = %s", got)
		}
	})
	t.Run("conflicting-writes", func(t *testing.T) {
		in := newInterp(t, mod("", "state x: Int32 = 0; state y: Int32 = 0;", "event E(p: Int32);",
			"rule A on E { set x := 1; set y := p; } rule B on E when p > 0 { set x := 2; }"))
		res := runOK(t, in, ev("E", "p", iv(5)))
		wantList(t, "diagnostics", res.Diagnostics, "ConflictingWrites:x")
		if stateText(in) != "x=0 y=0" {
			t.Errorf("aborted transaction changed state: %s", stateText(in))
		}
		res = runOK(t, in, ev("E", "p", iv(0)))
		wantList(t, "diagnostics", res.Diagnostics)
		if stateText(in) != "x=1 y=0" {
			t.Errorf("state = %s", stateText(in))
		}
	})
	t.Run("equal-decimals-do-not-conflict", func(t *testing.T) {
		in := newInterp(t, mod("", "state f: Float<V> = 0;", "event E();",
			"rule A on E { set f := 1.0; } rule B on E { set f := 1.00; }"))
		res := runOK(t, in, ev("E"))
		wantList(t, "diagnostics", res.Diagnostics)
		if got := stateText(in); got != "f=1.00" {
			t.Errorf("last write wins: %s", got)
		}
	})
	t.Run("unknown-guard-and-write", func(t *testing.T) {
		in := newInterp(t, mod("", "state x: Int32 = 0;", "event E(p: Int32);",
			"rule G on E when p > 0 { set x := 1; } rule W on E when p == 7 { set x := p; }"))
		res := runOK(t, in, ev("E", "p", Unknown{}))
		wantList(t, "diagnostics", res.Diagnostics, "UnknownGuard:G")
		in = newInterp(t, mod("", "state x: Int32 = 0;", "event E(p: Int32);", "rule W on E { set x := p; }"))
		res = runOK(t, in, ev("E", "p", Unknown{}))
		wantList(t, "diagnostics", res.Diagnostics, "UnknownWrite:W:x")
	})
	t.Run("invariant-abort", func(t *testing.T) {
		in := newInterp(t, mod("Invariants { Cap: x <= 3; }", "state x: Int32 = 0;", "event E();", "rule R on E { set x := x + 2; }"))
		res := runOK(t, in, ev("E"), ev("E"))
		wantList(t, "diagnostics", res.Diagnostics, "InvariantViolation:Cap")
		if stateText(in) != "x=2" {
			t.Errorf("state = %s", stateText(in))
		}
	})
	t.Run("cascade-is-breadth-first-in-watch-order", func(t *testing.T) {
		in := newInterp(t, mod("", "state a: Int32 = 0; state b: Int32 = 0; state log: Int32 = 0;", "event E();",
			"rule T on E { set a := 1; set b := 1; }"+
				" rule P on change(a, b) { set log := log * 10 + 1; }"+
				" rule Q on change(b, a) { set log := log * 10 + 2; }"))
		// Initial change events: (a,b) then (b,a) give log 12; E repeats both: 1212.
		runOK(t, in, ev("E"))
		if got := stateText(in); got != "a=1 b=1 log=1212" {
			t.Errorf("state = %s", got)
		}
	})
	t.Run("equal-value-write-does-not-wake-subscribers", func(t *testing.T) {
		in := newInterp(t, mod("", "state a: Int32 = 0; state n: Int32 = 0;", "event E();",
			"rule T on E { set a := 0; } rule W on change(a) { set n := n + 1; }"))
		runOK(t, in)
		before := stateText(in)
		runOK(t, in, ev("E"), ev("E"))
		if stateText(in) != before {
			t.Errorf("a write of an equal value triggered change: %s -> %s", before, stateText(in))
		}
	})
	t.Run("same-tuple-different-order-are-distinct", func(t *testing.T) {
		in := newInterp(t, mod("", "state a: Int32 = 0; state b: Int32 = 0; state x: Int32 = 0; state y: Int32 = 0;", "event E();",
			"rule T on E { set a := 1; } rule P on change(a, b) { set x := x + 1; } rule Q on change(b, a) { set y := y + 1; }"))
		runOK(t, in, ev("E"))
		if got := stateText(in); got != "a=1 b=0 x=2 y=2" {
			t.Errorf("state = %s", got)
		}
	})
}

// KPOL-DYN-7: presentation phases A, B and C.
func TestPresentationPhases(t *testing.T) {
	src := mod("Assumptions { Pos on E: p > 0; } Hazards { Over on E to trip: p > 10; } Alerts { Warn on E: p > 5; Maybe on E: q > 0; }",
		"state trip: Bool = false; state s: Int32 = 0;", "event E(p: Int32, q: Int32);",
		"rule Cover on reject E when p > 10 covers Over { set trip := true; }"+
			" rule Go on E { set s := p; } rule Rej on reject E { set s := 0 - 1; }")
	in := newInterp(t, src)

	res := runOK(t, in, ev("E", "p", iv(7), "q", iv(1)))
	wantList(t, "alerts", res.Alerts, "Warn", "Maybe")
	wantList(t, "rejected", res.Rejected)
	if stateText(in) != "trip=False s=7" {
		t.Errorf("phase C: %s", stateText(in))
	}

	in = newInterp(t, src)
	res = runOK(t, in, ev("E", "p", iv(11), "q", iv(1)))
	wantList(t, "hazards", res.Hazards, "Over")
	wantList(t, "rejected", res.Rejected, "RejectedHazard:Over")
	if stateText(in) != "trip=True s=-1" {
		t.Errorf("phase B reject: %s", stateText(in))
	}

	in = newInterp(t, src)
	res = runOK(t, in, ev("E", "p", Unknown{}, "q", iv(1)))
	// Assumption Pos is Unknown, i.e. not true: phase A rejects the input.
	wantList(t, "rejected", res.Rejected, "RejectedInput:E")
	wantList(t, "diagnostics", res.Diagnostics, "UnknownHazard:Over", "UnknownGuard:Cover")

	// D-K7: an Unknown Alert is logged in phase B but not in phase A.
	in = newInterp(t, src)
	res = runOK(t, in, ev("E", "p", iv(0), "q", Unknown{}))
	wantList(t, "phase A diagnostics", res.Diagnostics)
	in = newInterp(t, src)
	res = runOK(t, in, ev("E", "p", iv(1), "q", Unknown{}))
	wantList(t, "phase B diagnostics", res.Diagnostics, "UnknownAlert:Maybe")

	// Unknown hazard blocks fail-closed, passes fail-open.
	hz := mod("Hazards { H on A to t: p > 10; }", "state t: Bool = false; state s: Int32 = 0;", "event A(p: Int32);",
		"rule HA on reject A when p > 10 covers H { set t := true; } rule Go on A { set s := 1; }")
	in = newInterp(t, hz)
	res = runOK(t, in, ev("A", "p", Unknown{}))
	wantList(t, "rejected", res.Rejected, "RejectedHazardUnknown:H")
	in = newInterp(t, hz, WithFailClosedHazards(false))
	res = runOK(t, in, ev("A", "p", Unknown{}))
	wantList(t, "rejected", res.Rejected)
	wantList(t, "diagnostics", res.Diagnostics, "UnknownHazard:H")
	if stateText(in) != "t=False s=1" {
		t.Errorf("fail-open: %s", stateText(in))
	}
}

// D-K4: the hazard latch consults the hazards logged by the whole Run call.
func TestHazardLatchScopeDK4(t *testing.T) {
	src := mod("Hazards { H on B to t: p > 10; } Assumptions { Pos on B: p > 0; }",
		"state t: Bool = false;", "event B(p: Int32); event R();",
		"rule HB on reject B when p > 10 covers H { set t := true; } rule Rs on R { set t := false; }")
	in := newInterp(t, src)
	runOK(t, in, ev("B", "p", iv(11)), ev("R"), ev("B", "p", iv(-1)))
	if got := stateText(in); got != "t=True" {
		t.Errorf("same Run: %s, want t=True (latched by the earlier hazard)", got)
	}
	in = newInterp(t, src)
	runOK(t, in, ev("B", "p", iv(11)), ev("R"))
	runOK(t, in, ev("B", "p", iv(-1)))
	if got := stateText(in); got != "t=False" {
		t.Errorf("separate Run calls: %s, want t=False", got)
	}

	// An explicit write of the target during the rejection wins over the latch.
	latch := mod("Hazards { H on A to t: p > 10; }", "state t: Bool = false;", "event A(p: Int32);",
		"rule HA on A when p > 10 covers H { set t := true; } rule Clr on reject A { set t := false; }")
	in = newInterp(t, latch)
	runOK(t, in, ev("A", "p", iv(11)))
	if got := stateText(in); got != "t=False" {
		t.Errorf("explicit write: %s", got)
	}
}

func TestGoalFailuresAndSteps(t *testing.T) {
	in := newInterp(t, mod("Goals { G1: x > 0; G2: x > 5; G3: Unknown == Unknown; G4: x < y; }",
		"state x: Int32 = 0; state y: Int32 = 1;", "event E(p: Int32);", "rule R on E { set x := p; }"))
	res := runOK(t, in, ev("E", "p", iv(3)))
	wantList(t, "goal failures", res.GoalFailures, "G2", "G4")
	res = runOK(t, in, ev("E", "p", iv(7)))
	wantList(t, "goal failures", res.GoalFailures, "G4")
}

// KPOL-DYN arithmetic: the numeric tower of the reference.
func TestNumericTower(t *testing.T) {
	cases := []struct{ a, op, b, want string }{
		{"i:1", "+", "b:true", "i:2"},
		{"b:true", "*", "d:1.5", "d:1.5"},
		{"d:0.1", "+", "d:0.2", "d:0.3"},
		{"d:1.0", "/", "i:3", "d:0.3333333333333333333333333333"},
		{"d:2.50", "*", "d:2", "d:5.00"},
		{"d:1E+3", "+", "i:1", "d:1001"},
		{"i:1", "/", "i:3", "f:0.3333333333333333"},
		{"i:0", "/", "i:-5", "f:-0.0"},
		{"f:0.5", "+", "i:1", "f:1.5"},
		{"f:0.5", "*", "b:true", "f:0.5"},
		{"i:7", "/", "i:2", "f:3.5"},
		{"d:1.5", "==", "f:1.5", "b:true"},
		{"d:0.1", "==", "f:0.1", "b:false"},
		{"i:2", "==", "d:2.00", "b:true"},
		{"b:true", "==", "i:1", "b:true"},
		{"f:inf", ">", "i:5", "b:true"},
		{"d:-0.0", "==", "i:0", "b:true"},
		{"d:9999999999999999999999999999", "+", "i:1", "d:1.000000000000000000000000000E+28"},
		{"d:99999999999999999999999999995", "+", "i:0", "d:1.000000000000000000000000000E+29"},
		{"d:0.00", "*", "i:-1", "d:-0.00"},
		{"d:0", "-", "d:0", "d:0"},
	}
	for _, c := range cases {
		env := map[string]Value{"a": decodeValue(t, c.a), "b": decodeValue(t, c.b)}
		v, err := EvalExpr(Binary{Op: c.op, L: Name{"a"}, R: Name{"b"}}, env)
		if err != nil || encodeValue(v) != c.want {
			t.Errorf("%s %s %s = %v (%v), want %s", c.a, c.op, c.b, encodeValue(v), err, c.want)
		}
	}
	// A binary float cannot be mixed with a Decimal (TypeError in the reference).
	_, err := EvalExpr(Binary{Op: "+", L: Name{"a"}, R: Name{"b"}}, map[string]Value{"a": Float(1), "b": dec(t, "1")})
	var e *Error
	if !errors.As(err, &e) || e.Code != CodeRTType {
		t.Errorf("float+Decimal: %v", err)
	}
	// Decimal overflow is reported with a coded error instead of a crash.
	_, err = EvalExpr(Binary{Op: "*", L: Name{"a"}, R: Name{"b"}}, map[string]Value{"a": dec(t, "9999999999999999999999999999E+999972"), "b": iv(10)})
	if !errors.As(err, &e) || e.Code != CodeRTDecimal {
		t.Errorf("Decimal overflow: %v", err)
	}
}

func TestFormatValue(t *testing.T) {
	cases := []struct {
		v    Value
		want string
	}{
		{Bool(true), "True"}, {Bool(false), "False"}, {Unknown{}, "Unknown"}, {iv(-12), "-12"},
		{dec(t, "2.50"), "2.50"}, {dec(t, "1E+3"), "1E+3"}, {dec(t, "0.0000001"), "1E-7"}, {dec(t, "0.000001"), "0.000001"},
		{dec(t, "100"), "100"}, {dec(t, "-0.0"), "-0.0"}, {dec(t, "123456789012345678901234567890"), "123456789012345678901234567890"},
		{Float(2.0), "2.0"}, {Float(1e16), "1e+16"}, {Float(1e15), "1000000000000000.0"}, {Float(1.5e-7), "1.5e-07"},
		{Float(0.0001), "0.0001"}, {Float(0.00001), "1e-05"}, {Float(123456.789), "123456.789"}, {Float(math.Copysign(0, -1)), "-0.0"},
		{Float(1.0 / 3), "0.3333333333333333"},
	}
	for _, c := range cases {
		if got := FormatValue(c.v); got != c.want {
			t.Errorf("FormatValue(%#v) = %q, want %q", c.v, got, c.want)
		}
	}
	if got := ReprValue(dec(t, "2.50")); got != "Decimal('2.50')" {
		t.Errorf("ReprValue = %q", got)
	}
}

func TestDecimalParsingAndRounding(t *testing.T) {
	if d := dec(t, "007.50"); d.String() != "7.50" || d.Exponent() != -2 {
		t.Errorf("007.50 -> %s exp %d", d, d.Exponent())
	}
	if d := dec(t, "٣.٥"); d.String() != "3.5" {
		t.Errorf("Arabic-Indic digits -> %s", d)
	}
	for _, bad := range []string{"", ".", "1.2.3", "abc", "1e", "--1"} {
		if _, _, err := ParseDecimal(bad); err == nil {
			t.Errorf("ParseDecimal(%q) accepted", bad)
		}
	}
	if _, finite, _ := ParseDecimal("inf"); finite {
		t.Error("inf is not finite")
	}
	// Round-half-even at 28 significant digits.
	for _, c := range []struct{ a, b, want string }{
		{"1000000000000000000000000000.5", "0", "1000000000000000000000000000"},
		{"1000000000000000000000000001.5", "0", "1000000000000000000000000002"},
		{"1000000000000000000000000000.6", "0", "1000000000000000000000000001"},
	} {
		r, err := EvalExpr(Binary{Op: "+", L: DecLit{Text: c.a}, R: DecLit{Text: c.b}}, nil)
		if err != nil || FormatValue(r) != c.want {
			t.Errorf("%s + %s = %v (%v), want %s", c.a, c.b, r, err, c.want)
		}
	}
}

// KPOL-PRF-1.
func TestVerify(t *testing.T) {
	src := mod("Invariants { I: x >= 0; }", "state x: Int32 = 0; state f: Float<V> = 1.50;", "event E(p: Int32);",
		"rule R on E when p > 0 { set x := p; set f := f * 2; }",
		"assert Pos on E when p > 0 expect x == p;"+
			" assert Never on E when p > 1000 expect x == 0;"+
			" assert Bad on E when p > 0 expect x == 0;"+
			" scenario S1 { step E(p: 3); expect x == 3; expect x == 4; step E(p: -1); expect f == 3; }")
	rep, err := Verify(mustParse(t, src))
	if err != nil {
		t.Fatal(err)
	}
	if rep.TotalChecks != 9 || rep.PassedChecks != 7 {
		t.Errorf("counts %d/%d, want 7/9", rep.PassedChecks, rep.TotalChecks)
	}
	want := []VerificationFailure{
		{"Bad", "Assert violated in scenario S1 step 1 (E)"},
		{"S1", "Expectation failed at step 3: state={'x': 3, 'f': Decimal('3.00')}"},
		{"Never", "Vacuous assert 'Never': guard was never satisfied in any scenario"},
	}
	if fmt.Sprint(rep.Failures) != fmt.Sprint(want) {
		t.Errorf("failures:\n got %v\nwant %v", rep.Failures, want)
	}

	m := mustParse(t, "Problem M { }\nSolution M { }\nProof M { scenario S { } }")
	rep, err = Verify(m)
	if err != nil || len(rep.Failures) != 1 || rep.Failures[0].Message != "Vacuous Proof: declared Proof items evaluated zero executable checks" ||
		rep.Failures[0].ScenarioOrAssert != "M" {
		t.Errorf("vacuous proof: %+v %v", rep, err)
	}
	if rep, _ = Verify(mustParse(t, "Problem M { }\nSolution M { }")); rep.TotalChecks != 0 || !rep.Passed() {
		t.Errorf("no Proof must pass vacuously: %+v", rep)
	}

	// A runtime error inside a scenario propagates.
	_, err = Verify(mustParse(t, mod("", "state f: Float<V> = 1;", "event E();", "rule R on E { set f := f / 0; }",
		"scenario S { step E(); }")))
	wantErr(t, err, "division by zero")
	// D-K5: the last duplicate argument wins.
	rep, err = Verify(mustParse(t, mod("", "state x: Int32 = 0;", "event E(p: Int32);", "rule R on E { set x := p; }",
		"scenario S { step E(p: 1, p: 2); expect x == 2; }")))
	if err != nil || !rep.Passed() || rep.TotalChecks != 1 {
		t.Errorf("duplicate step argument: %+v %v", rep, err)
	}
}

func TestParseTriad(t *testing.T) {
	p := "Problem P { Invariants { I: X >= 0; } }"
	s := "Solution P { state X: Int32 = 0; }"
	_, err := ParseTriad(p, s, "Proof P {}")
	wantErr(t, err, "DO-178C DAL A violation: module must declare at least one assert or scenario in Proof block")
	_, err = ParseTriad(p, s, " \n")
	wantErr(t, err, "DO-178C DAL A violation: proof_src (.kproof) is mandatory and cannot be empty")
	_, err = ParseTriad("", s, "Proof P { scenario S { expect X == 0; } }")
	wantErr(t, err, "DO-178C DAL A violation: problem_src (.kproblem) is mandatory")
	m, err := ParseTriad(p, "namespace N;\nimport A::B;\n"+s, "Proof P { scenario S1 { expect X == 0; } }")
	if err != nil {
		t.Fatal(err)
	}
	if len(m.ProblemHash) != 64 || len(m.SolutionHash) != 64 || len(m.ProofHash) != 64 || !m.ProofPresent {
		t.Errorf("hashes/flags: %+v", m)
	}
	if m.ProblemHash != sha256Hex(p) {
		t.Error("problem hash is not SHA-256 of the original source")
	}
}

func FuzzParse(f *testing.F) {
	f.Add(mod("Invariants { I: x >= 0; }", "state x: Int32 = 0;", "event E(p: Int32);", "rule R on E when p > 0 { set x := p; }",
		"scenario S { step E(p: 3); expect x == 3; }"))
	f.Add("Problem M { Hazards { H on E to t: p > 1; } }\nSolution M { state t: Bool = false; event E(p: Int32); " +
		"rule R on reject E when p > 1 covers H { set t := true; } }")
	f.Add("a<-1 (*) • /* x */ 1. ²")
	f.Fuzz(func(t *testing.T, src string) {
		m, err := Parse(src)
		if err != nil {
			return
		}
		if rep, err := Verify(m); err == nil && rep == nil {
			t.Fatal("nil report without error")
		}
		if in, err := NewInterpreter(m, WithMaxEvents(200)); err == nil {
			var events []EventInput
			for _, e := range m.Events {
				p := map[string]Value{}
				for _, prm := range e.Params {
					p[prm.Name] = Unknown{}
				}
				events = append(events, EventInput{Name: e.Name, Payload: p})
			}
			_, _ = in.Run(events)
		}
	})
}
