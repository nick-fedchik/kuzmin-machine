package main

import (
	"encoding/json"
	"fmt"
	"io"
	"math/big"
	"strings"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/ekpol"
	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

func singleSource(name string, args []string, stderr io.Writer) (string, bool) {
	fs := newFlagSet(name, stderr)
	pos, err := parseFlags(fs, args)
	if err != nil || len(pos) != 1 {
		if err == nil {
			fmt.Fprintf(stderr, "usage: kpolc %s SOURCE\n", name)
		}
		return "", false
	}
	return pos[0], true
}

func cmdCheck(args []string, stdout, stderr io.Writer) int {
	path, ok := singleSource("check", args, stderr)
	if !ok {
		return exitRejected
	}
	if isEKPOL(path) {
		text, err := readSource(path, "EKPOL")
		if err != nil {
			return fail(stderr, exitRejected, "%v", err)
		}
		prog, err := ekpol.Parse(text, stem(path))
		if err != nil {
			return fail(stderr, exitRejected, "%v", err)
		}
		if prog.IsConceptualOnly() {
			fmt.Fprintf(stdout, "OK: %s: %d concepts (conceptual constructs; not compilable to EKPOL-B64)\n", prog.ModuleName, len(prog.Concepts))
			return exitOK
		}
		if _, err := ekpol.ValidateB64(prog); err != nil {
			return fail(stderr, exitRejected, "%v", err)
		}
		fmt.Fprintf(stdout, "OK: %s: %d concepts, %d tests (EKPOL-B64)\n", prog.ModuleName, len(prog.Concepts), len(prog.Tests))
		return exitOK
	}
	text, err := readSource(path, "KPOL")
	if err != nil {
		return fail(stderr, exitRejected, "%v", err)
	}
	mod, err := kpol.Parse(text)
	if err != nil {
		return fail(stderr, exitRejected, "%s: %v", path, err)
	}
	proof := "no Proof"
	if mod.ProofPresent {
		proof = "with Proof"
	}
	fmt.Fprintf(stdout, "OK: %s: %d states, %d events, %d rules, %s\n", mod.Name, len(mod.States), len(mod.Events), len(mod.Rules), proof)
	return exitOK
}

func cmdVerify(args []string, stdout, stderr io.Writer) int {
	path, ok := singleSource("verify", args, stderr)
	if !ok {
		return exitRejected
	}
	if isEKPOL(path) {
		text, err := readSource(path, "EKPOL")
		if err != nil {
			return fail(stderr, exitRejected, "%v", err)
		}
		prog, err := ekpol.Parse(text, stem(path))
		if err != nil {
			return fail(stderr, exitRejected, "%v", err)
		}
		// Embedded tests are executed while compiling to the B64 image.
		if _, err := ekpol.CompileProgram(prog); err != nil {
			if strings.HasPrefix(err.Error(), "EKPOL-PROOF-ERR") {
				return fail(stderr, exitVerify, "%v", err)
			}
			return fail(stderr, exitRejected, "%v", err)
		}
		fmt.Fprintf(stdout, "%s: %d embedded tests passed\n", prog.ModuleName, len(prog.Tests))
		return exitOK
	}
	text, err := readSource(path, "KPOL")
	if err != nil {
		return fail(stderr, exitRejected, "%v", err)
	}
	mod, err := kpol.Parse(text)
	if err != nil {
		return fail(stderr, exitRejected, "%s: %v", path, err)
	}
	report, err := kpol.Verify(mod)
	if err != nil {
		return fail(stderr, exitRejected, "%s: %v", path, err)
	}
	fmt.Fprintf(stdout, "%s: %d/%d checks passed\n", mod.Name, report.PassedChecks, report.TotalChecks)
	for _, f := range report.Failures {
		fmt.Fprintf(stdout, "FAIL %s: %s\n", f.ScenarioOrAssert, f.Message)
	}
	if !mod.ProofPresent {
		fmt.Fprintln(stdout, "note: the module has no Proof block")
	}
	if !report.Passed() {
		return exitVerify
	}
	return exitOK
}

func cmdTranslate(args []string, toKPOL bool, stdout, stderr io.Writer) int {
	name := "to-ekpol"
	if toKPOL {
		name = "to-kpol"
	}
	fs := newFlagSet(name, stderr)
	style := fs.String("ekpol-style", "symbolic", "EKPOL style: symbolic or keyword")
	pos, err := parseFlags(fs, args)
	if err != nil {
		return exitRejected
	}
	if len(pos) != 1 {
		return fail(stderr, exitRejected, "usage: kpolc %s [--ekpol-style symbolic|keyword] SOURCE", name)
	}
	if *style != "symbolic" && *style != "keyword" {
		return fail(stderr, exitRejected, "kpolc %s: invalid --ekpol-style %q", name, *style)
	}
	text, err := readSource(pos[0], "EKPOL")
	if err != nil {
		return fail(stderr, exitRejected, "%v", err)
	}
	var out string
	if toKPOL {
		out, err = ekpol.ToKPOL(text, stem(pos[0]))
	} else {
		if isEKPOL(pos[0]) {
			// EKPOL -> EKPOL: restyle through the classic form, as the reference CLI does.
			if text, err = ekpol.ToKPOL(text, stem(pos[0])); err != nil {
				return fail(stderr, exitRejected, "%v", err)
			}
		}
		out, err = ekpol.ToEKPOL(text, *style)
	}
	if err != nil {
		return fail(stderr, exitRejected, "%v", err)
	}
	fmt.Fprint(stdout, out)
	return exitOK
}

func cmdRun(args []string, stdout, stderr io.Writer) int {
	fs := newFlagSet("run", stderr)
	var events stringList
	fs.Var(&events, "e", "event to send, e.g. 'Buy(count=1)'; repeatable (each is one run call)")
	asJSON := fs.Bool("json", false, "print one JSON object per event")
	maxEvents := fs.Int("max-events", kpol.DefaultMaxEvents, "event limit per run call")
	pos, err := parseFlags(fs, args)
	if err != nil {
		return exitRejected
	}
	if len(pos) != 1 {
		return fail(stderr, exitRejected, "usage: kpolc run [-e 'Event(arg=value)']... [--json] SOURCE.kpol")
	}
	text, err := readSource(pos[0], "KPOL")
	if err != nil {
		return fail(stderr, exitRejected, "%v", err)
	}
	mod, err := kpol.Parse(text)
	if err != nil {
		return fail(stderr, exitRejected, "%s: %v", pos[0], err)
	}
	in, err := kpol.NewInterpreter(mod, kpol.WithMaxEvents(*maxEvents))
	if err != nil {
		return fail(stderr, exitRejected, "%s: %v", pos[0], err)
	}
	for _, spec := range events {
		ev, err := parseEvent(spec)
		if err != nil {
			return fail(stderr, exitRejected, "kpolc run: %v", err)
		}
		res, err := in.Run([]kpol.EventInput{ev})
		if err != nil {
			fmt.Fprintf(stderr, "%s: %v\n", spec, err)
			return exitRejected
		}
		if *asJSON {
			printRunJSON(stdout, spec, mod, res)
		} else {
			printRun(stdout, spec, mod, res)
		}
	}
	return exitOK
}

func formatValue(v kpol.Value) string {
	if b, ok := v.(kpol.Bool); ok {
		if b {
			return "true"
		}
		return "false"
	}
	return kpol.FormatValue(v)
}

func listOrDash(items []string) string {
	if len(items) == 0 {
		return "-"
	}
	return strings.Join(items, ", ")
}

func printRun(w io.Writer, spec string, m *kpol.Module, r *kpol.RunResult) {
	fmt.Fprintf(w, "> %s\n", spec)
	var parts []string
	for _, st := range m.States {
		parts = append(parts, fmt.Sprintf("%s=%s", st.Name, formatValue(r.State[st.Name])))
	}
	fmt.Fprintf(w, "  state:       %s\n", strings.Join(parts, " "))
	fmt.Fprintf(w, "  hazards:     %s\n", listOrDash(r.Hazards))
	fmt.Fprintf(w, "  alerts:      %s\n", listOrDash(r.Alerts))
	fmt.Fprintf(w, "  rejected:    %s\n", listOrDash(r.Rejected))
	fmt.Fprintf(w, "  diagnostics: %s\n", listOrDash(r.Diagnostics))
	fmt.Fprintf(w, "  goals:       %s\n", listOrDash(r.GoalFailures))
	fmt.Fprintf(w, "  steps:       %d\n", r.Steps)
}

func printRunJSON(w io.Writer, spec string, m *kpol.Module, r *kpol.RunResult) {
	state := make([][2]string, 0, len(m.States))
	for _, st := range m.States {
		state = append(state, [2]string{st.Name, formatValue(r.State[st.Name])})
	}
	nonNil := func(s []string) []string {
		if s == nil {
			return []string{}
		}
		return s
	}
	out := map[string]any{
		"event": spec, "state": state, "hazards": nonNil(r.Hazards), "alerts": nonNil(r.Alerts),
		"rejected": nonNil(r.Rejected), "diagnostics": nonNil(r.Diagnostics), "goal_failures": nonNil(r.GoalFailures), "steps": r.Steps,
	}
	data, _ := json.Marshal(out)
	fmt.Fprintln(w, string(data))
}

// parseEvent parses 'Name(arg=value, ...)' where value is an integer, a
// decimal, true, false or Unknown.
func parseEvent(spec string) (kpol.EventInput, error) {
	spec = strings.TrimSpace(spec)
	open := strings.IndexByte(spec, '(')
	if open < 0 {
		return kpol.EventInput{Name: spec, Payload: map[string]kpol.Value{}}, validName(spec)
	}
	if !strings.HasSuffix(spec, ")") {
		return kpol.EventInput{}, fmt.Errorf("invalid event %q: expected Name(arg=value, ...)", spec)
	}
	ev := kpol.EventInput{Name: strings.TrimSpace(spec[:open]), Payload: map[string]kpol.Value{}}
	if err := validName(ev.Name); err != nil {
		return ev, err
	}
	body := strings.TrimSpace(spec[open+1 : len(spec)-1])
	if body == "" {
		return ev, nil
	}
	for _, part := range strings.Split(body, ",") {
		name, raw, ok := strings.Cut(part, "=")
		if !ok {
			return ev, fmt.Errorf("invalid argument %q in event %q: expected name=value", strings.TrimSpace(part), spec)
		}
		name, raw = strings.TrimSpace(name), strings.TrimSpace(raw)
		if err := validName(name); err != nil {
			return ev, err
		}
		v, err := parseValue(raw)
		if err != nil {
			return ev, fmt.Errorf("argument %s of %q: %v", name, spec, err)
		}
		ev.Payload[name] = v
	}
	return ev, nil
}

func validName(s string) error {
	if s == "" {
		return fmt.Errorf("empty name in event specification")
	}
	for i, r := range s {
		if !(r == '_' || r >= 'A' && r <= 'Z' || r >= 'a' && r <= 'z' || i > 0 && r >= '0' && r <= '9') {
			return fmt.Errorf("invalid name %q", s)
		}
	}
	return nil
}

func parseValue(raw string) (kpol.Value, error) {
	switch raw {
	case "true":
		return kpol.Bool(true), nil
	case "false":
		return kpol.Bool(false), nil
	case "Unknown":
		return kpol.Unknown{}, nil
	}
	if n, ok := new(big.Int).SetString(raw, 10); ok {
		return kpol.NewBigInt(n), nil
	}
	if d, finite, err := kpol.ParseDecimal(raw); err == nil && finite {
		return d, nil
	}
	return nil, fmt.Errorf("invalid value %q (expected integer, decimal, true, false or Unknown)", raw)
}
