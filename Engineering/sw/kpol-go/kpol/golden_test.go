package kpol

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"sort"
	"strconv"
	"strings"
	"testing"
)

// The golden file is produced by testdata/gen_kpol_golden.py from the Python
// reference implementation; these tests replay it against the Go port.

type goldenErr struct {
	Kind string `json:"kind"`
	Text string `json:"text"`
}

type goldenVerify struct {
	Total    int         `json:"total"`
	Passed   int         `json:"passed"`
	Failures [][2]string `json:"failures"`
	Error    *goldenErr  `json:"error"`
}

type goldenBatch struct {
	Events []struct {
		Name    string            `json:"name"`
		Payload map[string]string `json:"payload"`
	} `json:"events"`
	Result *struct {
		State        [][2]string `json:"state"`
		Hazards      []string    `json:"hazards"`
		Alerts       []string    `json:"alerts"`
		Rejected     []string    `json:"rejected"`
		Diagnostics  []string    `json:"diagnostics"`
		GoalFailures []string    `json:"goal_failures"`
		Steps        int         `json:"steps"`
	} `json:"result"`
	Error      *goldenErr  `json:"error"`
	StateAfter [][2]string `json:"state_after"`
}

type goldenRun struct {
	Opts struct {
		FailClosed *bool             `json:"fail_closed"`
		Overrides  map[string]string `json:"overrides"`
		MaxEvents  *int              `json:"max_events"`
	} `json:"opts"`
	InitError *goldenErr    `json:"init_error"`
	InitState [][2]string   `json:"init_state"`
	Batches   []goldenBatch `json:"batches"`
}

type goldenCase struct {
	ID     string `json:"id"`
	Group  string `json:"group"`
	Source string `json:"source"`
	Tokens struct {
		OK    bool       `json:"ok"`
		N     int        `json:"n"`
		Sha   string     `json:"sha"`
		Error *goldenErr `json:"error"`
		List  [][]any    `json:"list"`
	} `json:"tokens"`
	Syntax struct {
		OK     bool       `json:"ok"`
		AstSha string     `json:"ast_sha"`
		Ast    string     `json:"ast"`
		Error  *goldenErr `json:"error"`
	} `json:"syntax"`
	Parse struct {
		OK    bool       `json:"ok"`
		Error *goldenErr `json:"error"`
	} `json:"parse"`
	Verify     *goldenVerify `json:"verify"`
	VerifyOpen *goldenVerify `json:"verify_open"`
	Runs       []goldenRun   `json:"runs"`
}

type goldenTriad struct {
	ID       string     `json:"id"`
	Problem  string     `json:"problem"`
	Solution string     `json:"solution"`
	Proof    string     `json:"proof"`
	Error    *goldenErr `json:"error"`
	OK       *struct {
		Ast          string `json:"ast"`
		ProblemHash  string `json:"problem_hash"`
		SolutionHash string `json:"solution_hash"`
		ProofHash    string `json:"proof_hash"`
		ProofPresent bool   `json:"proof_present"`
		Aliases      bool   `json:"aliases"`
	} `json:"ok"`
}

type goldenFile struct {
	Meta   map[string]any `json:"meta"`
	Cases  []goldenCase   `json:"cases"`
	Triads []goldenTriad  `json:"triads"`
	Eval   [][]string     `json:"eval"`
	Unary  [][]string     `json:"unary"`
	Norm   [][]any        `json:"norm"`
	Expr   struct {
		Env  map[string]string `json:"env"`
		Rows [][]string        `json:"rows"`
	} `json:"expr"`
}

func loadGolden(t *testing.T) *goldenFile {
	t.Helper()
	data, err := readGoldenGz("../testdata/kpol_golden.json.gz")
	if err != nil {
		t.Fatalf("read golden file: %v", err)
	}
	var g goldenFile
	if err := json.Unmarshal(data, &g); err != nil {
		t.Fatalf("decode golden file: %v", err)
	}
	return &g
}

// decodeValue parses the tagged text written by the generator's enc().
func decodeValue(t testing.TB, s string) Value {
	t.Helper()
	if s == "u" {
		return Unknown{}
	}
	tag, text, ok := strings.Cut(s, ":")
	if !ok {
		t.Fatalf("bad value %q", s)
	}
	switch tag {
	case "b":
		return Bool(text == "true")
	case "i":
		base := 10
		if strings.HasPrefix(strings.TrimPrefix(text, "-"), "0x") {
			base = 0
		}
		n, ok := new(big.Int).SetString(text, base)
		if !ok {
			t.Fatalf("bad int %q", s)
		}
		return Int{n}
	case "d":
		d, finite, err := ParseDecimal(text)
		if err != nil || !finite {
			t.Fatalf("bad decimal %q: %v", s, err)
		}
		return d
	case "f":
		f, err := strconv.ParseFloat(text, 64)
		if err != nil {
			t.Fatalf("bad float %q: %v", s, err)
		}
		return Float(f)
	}
	t.Fatalf("bad value tag %q", s)
	return nil
}

func encodeValue(v Value) string {
	switch x := v.(type) {
	case Unknown:
		return "u"
	case Bool:
		if x {
			return "b:true"
		}
		return "b:false"
	case Int:
		return "i:" + x.String()
	case Decimal:
		return "d:" + x.String()
	case Float:
		return "f:" + FormatValue(x)
	}
	return "?:" + FormatValue(v)
}

func errMismatch(err error, want *goldenErr) string {
	if want == nil {
		if err != nil {
			return "unexpected error: " + err.Error()
		}
		return ""
	}
	if err == nil {
		return fmt.Sprintf("expected %s error %q, got success", want.Kind, want.Text)
	}
	var e *Error
	if !errors.As(err, &e) {
		return fmt.Sprintf("error %T is not *kpol.Error: %v", err, err)
	}
	switch want.Kind {
	case "kpol":
		if e.Code != "" || e.Msg != want.Text {
			return fmt.Sprintf("error mismatch:\n   go: [%s] %q\n  ref: %q", e.Code, e.Msg, want.Text)
		}
	default:
		if e.Code == "" {
			return fmt.Sprintf("reference crashed (%s) but Go returned a plain error %q", want.Text, e.Msg)
		}
	}
	return ""
}

func tokenDigest(toks []Token) string {
	lines := make([]string, len(toks))
	for i, tk := range toks {
		lines[i] = fmt.Sprintf("%s\t%s\t%d\t%d", tk.Kind, tk.Value, tk.Line, tk.Column)
	}
	sum := sha256.Sum256([]byte(strings.Join(lines, "\n")))
	return hex.EncodeToString(sum[:])
}

func dumpExpr(e Expr) string {
	switch x := e.(type) {
	case IntLit:
		return "(lit int " + x.V.String() + ")"
	case DecLit:
		d, _, _ := ParseDecimal(x.Text)
		return "(lit dec " + d.String() + ")"
	case BoolLit:
		return fmt.Sprintf("(lit bool %t)", x.V)
	case UnknownLit:
		return "(lit unk)"
	case Name:
		return "(name " + x.Name + ")"
	case Unary:
		return "(un " + x.Op + " " + dumpExpr(x.X) + ")"
	case Binary:
		return "(bin " + x.Op + " " + dumpExpr(x.L) + " " + dumpExpr(x.R) + ")"
	case Call:
		parts := make([]string, len(x.Args))
		for i, a := range x.Args {
			parts[i] = dumpExpr(a)
		}
		return "(call " + x.Name + " " + strings.Join(parts, " ") + ")"
	}
	return "(?)"
}

func dumpType(t TypeRef) string {
	unit := t.Unit
	if len(t.PinParams) > 0 {
		unit = strings.Join(t.PinParams, ",")
	}
	if unit != "" {
		return t.Name + "<" + unit + ">"
	}
	return t.Name
}

func orDash(s string) string {
	if s == "" {
		return "-"
	}
	return s
}

func b2i(b bool) int {
	if b {
		return 1
	}
	return 0
}

// dumpModule mirrors dump_module in the generator.
func dumpModule(m *Module) string {
	out := []string{fmt.Sprintf("module %s aliases=%d proof=%d", m.Name, b2i(m.PhaseAliasesUsed), b2i(m.ProofPresent))}
	for _, r := range m.Requirements {
		out = append(out, fmt.Sprintf("req %s %s on=%s to=%s %s", r.Kind, r.Name, orDash(r.Event), orDash(r.Target), dumpExpr(r.Expression)))
	}
	for _, e := range m.Events {
		ps := make([]string, len(e.Params))
		for i, p := range e.Params {
			ps[i] = p.Name + ":" + dumpType(p.Type)
		}
		out = append(out, "event "+e.Name+"("+strings.Join(ps, ",")+")")
	}
	for _, s := range m.States {
		out = append(out, fmt.Sprintf("state %s %s %s", s.Name, dumpType(s.Type), dumpExpr(s.Initial)))
	}
	for _, r := range m.Rules {
		on := r.Event
		if r.triggerEvent() == "change" {
			on = "change(" + strings.Join(r.Watch, ",") + ")"
		}
		out = append(out, fmt.Sprintf("rule %s on=%s reject=%d covers=%s when %s", r.Name, on, b2i(r.Reject), orDash(r.Covers), dumpExpr(r.Guard)))
		for _, a := range r.Actions {
			out = append(out, fmt.Sprintf("  set %s %s", a.Name, dumpExpr(a.Expression)))
		}
	}
	for _, item := range m.Proofs {
		switch p := item.(type) {
		case AssertProperty:
			out = append(out, fmt.Sprintf("assert %s on=%s when %s expect %s", p.Name, p.Event, dumpExpr(p.Guard), dumpExpr(p.Expectation)))
		case Scenario:
			out = append(out, "scenario "+p.Name)
			for _, it := range p.Items {
				switch s := it.(type) {
				case StepAction:
					args := make([]string, len(s.Args))
					for i, a := range s.Args {
						args[i] = a.Name + "=" + dumpExpr(a.Value)
					}
					out = append(out, "  step "+s.Event+" "+strings.Join(args, " "))
				case ExpectCheck:
					out = append(out, "  expect "+dumpExpr(s.Expression))
				}
			}
		}
	}
	return strings.Join(out, "\n")
}

func stateList(m *Module, st map[string]Value) [][2]string {
	out := make([][2]string, 0, len(m.States))
	for _, s := range m.States {
		out = append(out, [2]string{s.Name, encodeValue(st[s.Name])})
	}
	return out
}

func listMismatch(what string, got, want []string) string {
	if len(got) == 0 && len(want) == 0 {
		return ""
	}
	if strings.Join(got, "\x00") != strings.Join(want, "\x00") || len(got) != len(want) {
		return fmt.Sprintf("%s: go %q, ref %q", what, got, want)
	}
	return ""
}

func stateMismatch(what string, m *Module, st map[string]Value, want [][2]string) string {
	got := stateList(m, st)
	if fmt.Sprint(got) != fmt.Sprint(want) {
		return fmt.Sprintf("%s: go %v, ref %v", what, got, want)
	}
	return ""
}

func verifyMismatch(rep *VerificationReport, err error, want *goldenVerify) string {
	if want.Error != nil {
		return errMismatch(err, want.Error)
	}
	if err != nil {
		return "unexpected error: " + err.Error()
	}
	if rep.TotalChecks != want.Total || rep.PassedChecks != want.Passed {
		return fmt.Sprintf("verify counts: go %d/%d, ref %d/%d", rep.PassedChecks, rep.TotalChecks, want.Passed, want.Total)
	}
	if len(rep.Failures) != len(want.Failures) {
		return fmt.Sprintf("verify failures: go %v, ref %v", rep.Failures, want.Failures)
	}
	for i, f := range rep.Failures {
		if f.ScenarioOrAssert != want.Failures[i][0] || f.Message != want.Failures[i][1] {
			return fmt.Sprintf("verify failure %d:\n   go: %q %q\n  ref: %q %q", i, f.ScenarioOrAssert, f.Message, want.Failures[i][0], want.Failures[i][1])
		}
	}
	return ""
}

func replayRun(t *testing.T, m *Module, run goldenRun) []string {
	var diffs []string
	var opts []Option
	if run.Opts.FailClosed != nil {
		opts = append(opts, WithFailClosedHazards(*run.Opts.FailClosed))
	}
	if run.Opts.Overrides != nil {
		ov := map[string]Value{}
		for k, v := range run.Opts.Overrides {
			ov[k] = decodeValue(t, v)
		}
		opts = append(opts, WithOverrides(ov))
	}
	if run.Opts.MaxEvents != nil {
		opts = append(opts, WithMaxEvents(*run.Opts.MaxEvents))
	}
	in, err := NewInterpreter(m, opts...)
	if run.InitError != nil {
		if d := errMismatch(err, run.InitError); d != "" {
			diffs = append(diffs, "init: "+d)
		}
		return diffs
	}
	if err != nil {
		return append(diffs, "init: unexpected error: "+err.Error())
	}
	if d := stateMismatch("init state", m, in.State(), run.InitState); d != "" {
		diffs = append(diffs, d)
	}
	for bi, b := range run.Batches {
		events := make([]EventInput, len(b.Events))
		for i, e := range b.Events {
			payload := map[string]Value{}
			for k, v := range e.Payload {
				payload[k] = decodeValue(t, v)
			}
			events[i] = EventInput{Name: e.Name, Payload: payload}
		}
		res, err := in.Run(events)
		if b.Error != nil {
			if d := errMismatch(err, b.Error); d != "" {
				diffs = append(diffs, fmt.Sprintf("batch %d: %s", bi, d))
			}
			if d := stateMismatch(fmt.Sprintf("batch %d state after error", bi), m, in.State(), b.StateAfter); d != "" {
				diffs = append(diffs, d)
			}
			continue
		}
		if err != nil {
			diffs = append(diffs, fmt.Sprintf("batch %d: unexpected error: %v", bi, err))
			continue
		}
		w := b.Result
		for _, d := range []string{
			stateMismatch(fmt.Sprintf("batch %d state", bi), m, res.State, w.State),
			listMismatch(fmt.Sprintf("batch %d hazards", bi), res.Hazards, w.Hazards),
			listMismatch(fmt.Sprintf("batch %d alerts", bi), res.Alerts, w.Alerts),
			listMismatch(fmt.Sprintf("batch %d rejected", bi), res.Rejected, w.Rejected),
			listMismatch(fmt.Sprintf("batch %d diagnostics", bi), res.Diagnostics, w.Diagnostics),
			listMismatch(fmt.Sprintf("batch %d goal_failures", bi), res.GoalFailures, w.GoalFailures),
		} {
			if d != "" {
				diffs = append(diffs, d)
			}
		}
		if res.Steps != w.Steps {
			diffs = append(diffs, fmt.Sprintf("batch %d steps: go %d, ref %d", bi, res.Steps, w.Steps))
		}
	}
	return diffs
}

func compareCase(t *testing.T, c goldenCase) []string {
	var diffs []string
	toks, err := Tokenize(c.Source)
	if c.Tokens.OK {
		if err != nil {
			diffs = append(diffs, "tokenize: unexpected error: "+err.Error())
		} else if len(toks) != c.Tokens.N || tokenDigest(toks) != c.Tokens.Sha {
			diffs = append(diffs, fmt.Sprintf("tokenize: token stream differs (go %d tokens, ref %d)", len(toks), c.Tokens.N))
		}
		if c.Tokens.List != nil && err == nil {
			for i, row := range c.Tokens.List {
				if i >= len(toks) {
					break
				}
				tk := toks[i]
				if row[0] != tk.Kind || row[1] != tk.Value || int(row[2].(float64)) != tk.Line || int(row[3].(float64)) != tk.Column {
					diffs = append(diffs, fmt.Sprintf("tokenize: token %d go %v ref %v", i, tk, row))
					break
				}
			}
		}
	} else if d := errMismatch(err, c.Tokens.Error); d != "" {
		diffs = append(diffs, "tokenize: "+d)
	}

	m, err := ParseUnchecked(c.Source)
	if c.Syntax.OK {
		if err != nil {
			return append(diffs, "syntax: unexpected error: "+err.Error())
		}
		dump := dumpModule(m)
		sum := sha256.Sum256([]byte(dump))
		if hex.EncodeToString(sum[:]) != c.Syntax.AstSha {
			msg := "syntax: AST differs"
			if c.Syntax.Ast != "" {
				msg += fmt.Sprintf("\n--- go\n%s\n--- ref\n%s", dump, c.Syntax.Ast)
			}
			diffs = append(diffs, msg)
		}
	} else if d := errMismatch(err, c.Syntax.Error); d != "" {
		return append(diffs, "syntax: "+d)
	}

	pm, err := Parse(c.Source)
	if c.Parse.OK {
		if err != nil {
			return append(diffs, "parse: unexpected error: "+err.Error())
		}
	} else {
		if d := errMismatch(err, c.Parse.Error); d != "" {
			diffs = append(diffs, "parse: "+d)
		}
		return diffs
	}
	if c.Verify == nil {
		return diffs
	}
	rep, err := Verify(pm)
	if d := verifyMismatch(rep, err, c.Verify); d != "" {
		diffs = append(diffs, "verify: "+d)
	}
	rep, err = VerifyModule(pm, false)
	if d := verifyMismatch(rep, err, c.VerifyOpen); d != "" {
		diffs = append(diffs, "verify(fail-open): "+d)
	}
	for ri, run := range c.Runs {
		for _, d := range replayRun(t, pm, run) {
			diffs = append(diffs, fmt.Sprintf("run %d: %s", ri, d))
		}
	}
	return diffs
}

func report(t *testing.T, what string, total int, diffs []string) {
	t.Helper()
	t.Logf("%s: %d checked, %d mismatches", what, total, len(diffs))
	for i, d := range diffs {
		if i >= 25 {
			t.Errorf("... and %d more", len(diffs)-i)
			break
		}
		t.Error(d)
	}
}

func TestGoldenCases(t *testing.T) {
	g := loadGolden(t)
	groups := map[string]int{}
	accepted := 0
	var diffs []string
	for _, c := range g.Cases {
		groups[c.Group]++
		if c.Parse.OK {
			accepted++
		}
		for _, d := range compareCase(t, c) {
			diffs = append(diffs, fmt.Sprintf("[%s] %s", c.ID, d))
		}
	}
	names := make([]string, 0, len(groups))
	for k := range groups {
		names = append(names, k)
	}
	sort.Strings(names)
	for _, k := range names {
		t.Logf("group %-9s %d", k, groups[k])
	}
	t.Logf("accepted modules: %d of %d", accepted, len(g.Cases))
	if groups["mutation"] < 300 {
		t.Errorf("golden file has %d mutations, want >= 300", groups["mutation"])
	}
	report(t, "module cases", len(g.Cases), diffs)
}

func TestGoldenTriads(t *testing.T) {
	g := loadGolden(t)
	var diffs []string
	for _, c := range g.Triads {
		m, err := ParseTriad(c.Problem, c.Solution, c.Proof)
		if c.Error != nil {
			if d := errMismatch(err, c.Error); d != "" {
				diffs = append(diffs, fmt.Sprintf("[%s] %s", c.ID, d))
			}
			continue
		}
		if err != nil {
			diffs = append(diffs, fmt.Sprintf("[%s] unexpected error: %v", c.ID, err))
			continue
		}
		if dumpModule(m) != c.OK.Ast {
			diffs = append(diffs, fmt.Sprintf("[%s] AST differs:\n%s\n---\n%s", c.ID, dumpModule(m), c.OK.Ast))
		}
		if m.ProblemHash != c.OK.ProblemHash || m.SolutionHash != c.OK.SolutionHash || m.ProofHash != c.OK.ProofHash {
			diffs = append(diffs, fmt.Sprintf("[%s] hashes differ", c.ID))
		}
		if m.ProofPresent != c.OK.ProofPresent || m.PhaseAliasesUsed != c.OK.Aliases {
			diffs = append(diffs, fmt.Sprintf("[%s] flags differ: proof=%v aliases=%v", c.ID, m.ProofPresent, m.PhaseAliasesUsed))
		}
	}
	report(t, "triads", len(g.Triads), diffs)
}

func resultText(v Value, err error) string {
	if err == nil {
		return encodeValue(v)
	}
	var e *Error
	if errors.As(err, &e) && e.Code == "" {
		return "!kpol:" + e.Msg
	}
	return "!crash"
}

func wantText(s string) string {
	if strings.HasPrefix(s, "!crash:") {
		return "!crash"
	}
	return s
}

func TestGoldenEval(t *testing.T) {
	g := loadGolden(t)
	var diffs []string
	for _, row := range g.Eval {
		op := row[0]
		env := map[string]Value{"a": decodeValue(t, row[1]), "b": decodeValue(t, row[2])}
		v, err := EvalExpr(Binary{Op: op, L: Name{"a"}, R: Name{"b"}}, env)
		if got, want := resultText(v, err), wantText(row[3]); got != want {
			diffs = append(diffs, fmt.Sprintf("%s %s %s: go %s, ref %s", row[1], op, row[2], got, want))
		}
	}
	for _, row := range g.Unary {
		var e Expr
		env := map[string]Value{"a": decodeValue(t, row[1])}
		var want string
		switch row[0] {
		case "gcd":
			env["b"] = decodeValue(t, row[2])
			e = Call{Name: "gcd", Args: []Expr{Name{"a"}, Name{"b"}}}
			want = row[3]
		default:
			e = Unary{Op: row[0], X: Name{"a"}}
			want = row[2]
		}
		v, err := EvalExpr(e, env)
		if got := resultText(v, err); got != wantText(want) {
			diffs = append(diffs, fmt.Sprintf("%v: go %s, ref %s", row, got, want))
		}
	}
	report(t, "eval vectors", len(g.Eval)+len(g.Unary), diffs)
}

func TestGoldenNorm(t *testing.T) {
	g := loadGolden(t)
	var diffs []string
	for _, row := range g.Norm {
		tn := row[0].(string)
		v := decodeValue(t, row[1].(string))
		allow := row[2].(bool)
		want := wantText(row[3].(string))
		ref := TypeRef{Name: tn}
		switch tn {
		case "Float":
			ref.Unit = "V"
		case "Pin":
			ref.PinParams = nil
		}
		got, err := normalize(v, ref, allow)
		if r := resultText(got, err); r != want {
			diffs = append(diffs, fmt.Sprintf("norm %s %v allow=%v: go %s, ref %s", tn, row[1], allow, r, want))
		}
	}
	report(t, "norm vectors", len(g.Norm), diffs)
}

func TestGoldenExpr(t *testing.T) {
	g := loadGolden(t)
	env := map[string]Value{}
	for k, v := range g.Expr.Env {
		env[k] = decodeValue(t, v)
	}
	var diffs []string
	for _, row := range g.Expr.Rows {
		var got string
		p, err := newExprParser(row[0])
		if err == nil {
			var e Expr
			e, err = p()
			if err == nil {
				var v Value
				v, err = EvalExpr(e, env)
				got = resultText(v, err)
				if err == nil {
					got = "ok:" + got
				}
			}
		}
		if err != nil && got == "" {
			got = resultText(nil, err)
		}
		if want := wantText(row[1]); got != want {
			diffs = append(diffs, fmt.Sprintf("%q: go %s, ref %s", row[0], got, want))
		}
	}
	report(t, "expression strings", len(g.Expr.Rows), diffs)
}

// newExprParser returns a function that parses text as a single expression.
func newExprParser(text string) (func() (e Expr, err error), error) {
	toks, err := Tokenize(text)
	if err != nil {
		return nil, err
	}
	return func() (e Expr, err error) {
		p := &parser{toks: toks}
		defer func() {
			if r := recover(); r != nil {
				pf, ok := r.(parseFailure)
				if !ok {
					panic(r)
				}
				e, err = nil, pf.err
			}
		}()
		e = p.expression(0)
		if p.tok().Kind != TokEOF {
			return nil, &Error{Msg: "trailing"}
		}
		return e, nil
	}, nil
}
