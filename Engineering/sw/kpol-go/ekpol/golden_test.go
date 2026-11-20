package ekpol

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"reflect"
	"strings"
	"testing"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

// The golden file is produced by testdata/gen_ekpol_golden.py from the Python
// reference (ekpol_frontend.py); every case records the oracle's verdicts.

type outcome struct {
	OK        bool           `json:"ok"`
	Code      string         `json:"code"`
	Message   string         `json:"message"`
	Crash     string         `json:"crash"`
	KpolError string         `json:"kpol_error"`
	SHA256    string         `json:"sha256"`
	Len       int            `json:"len"`
	Text      string         `json:"text"`
	Same      bool           `json:"same"`
	Program   map[string]any `json:"program"`
	Stage     string         `json:"stage"`
	ASCII     bool           `json:"ascii"`
	EkpolSHA  string         `json:"ekpol_sha256"`
	ImageSHA  string         `json:"image_sha256"`
	Kpol2SHA  string         `json:"kpol2_sha256"`
}

type goldenCase struct {
	ID                string              `json:"id"`
	Kind              string              `json:"kind"`
	Src               string              `json:"src"`
	Parse             *outcome            `json:"parse"`
	ParseCustomModule *string             `json:"parse_custom_module"`
	Validate          *outcome            `json:"validate"`
	Image             *outcome            `json:"image"`
	ToKPOL            *outcome            `json:"to_kpol"`
	ToKPOLSynth       *outcome            `json:"to_kpol_synth"`
	Roundtrip         map[string]*outcome `json:"roundtrip"`
	ToEKPOLSymbolic   *outcome            `json:"to_ekpol_symbolic"`
	ToEKPOLKeyword    *outcome            `json:"to_ekpol_keyword"`
}

func loadGolden(t *testing.T) []goldenCase {
	t.Helper()
	data, err := readGoldenGz("../testdata/ekpol_golden.json.gz")
	if err != nil {
		t.Fatalf("golden file: %v", err)
	}
	var f struct {
		Cases []goldenCase `json:"cases"`
	}
	if err := json.Unmarshal(data, &f); err != nil {
		t.Fatalf("golden file: %v", err)
	}
	if len(f.Cases) == 0 {
		t.Fatal("golden file has no cases")
	}
	return f.Cases
}

// kpolReady reports whether the KPOL parser the translators depend on is implemented.
func kpolReady() bool {
	_, err := kpol.Parse("")
	return err == nil || !strings.Contains(err.Error(), "not implemented yet")
}

func sha(b []byte) string {
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:])
}

// diffErr compares an error with the recorded outcome; it returns "" when they agree.
func diffErr(o *outcome, err error) string {
	var ke *kpol.Error
	switch {
	case o.OK:
		if err != nil {
			return "want success, got " + err.Error()
		}
	case err == nil:
		return "want error " + o.Code + ": " + o.Message + o.Crash + ", got success"
	case o.Crash != "":
		if !errors.As(err, &ke) || ke.Code != CodeInternal {
			return "want internal error for reference crash " + o.Crash + ", got " + err.Error()
		}
	case o.KpolError != "":
		if err.Error() != o.KpolError {
			return "want " + o.KpolError + ", got " + err.Error()
		}
	default:
		if !errors.As(err, &ke) || ke.Code != o.Code || ke.Msg != o.Message {
			return "want " + o.Code + ": " + o.Message + "\n got " + err.Error()
		}
	}
	return ""
}

// goldenReport collects mismatches and fails the test with a bounded report.
type goldenReport struct {
	t     *testing.T
	fails int
	total int
}

func (r *goldenReport) check(id, what, msg string) {
	r.total++
	if msg == "" {
		return
	}
	r.fails++
	if r.fails <= 25 {
		r.t.Errorf("%s [%s]: %s", id, what, msg)
	}
}

func (r *goldenReport) done() {
	r.t.Logf("%d checks, %d mismatches", r.total, r.fails)
	if r.fails > 25 {
		r.t.Errorf("... and %d more mismatches", r.fails-25)
	}
}

func jsonRoundTrip(t *testing.T, v any) any {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	var out any
	if err := json.Unmarshal(b, &out); err != nil {
		t.Fatal(err)
	}
	return out
}

func TestGoldenParse(t *testing.T) {
	r := &goldenReport{t: t}
	for _, c := range loadGolden(t) {
		if c.Kind != "ekpol" {
			continue
		}
		p, err := Parse(c.Src, "EkpolModule")
		if msg := diffErr(&outcome{OK: c.Parse.OK, Code: c.Parse.Code, Message: c.Parse.Message, Crash: c.Parse.Crash}, err); msg != "" {
			r.check(c.ID, "parse", msg)
			continue
		}
		r.check(c.ID, "parse", "")
		if err != nil {
			continue
		}
		got := jsonRoundTrip(t, dumpProgram(p))
		want := jsonRoundTrip(t, c.Parse.Program)
		if !reflect.DeepEqual(got, want) {
			gb, _ := json.Marshal(got)
			wb, _ := json.Marshal(want)
			r.check(c.ID, "program", "got  "+string(gb)+"\nwant "+string(wb))
		}
		custom, err := Parse(c.Src, "MyMod")
		if err != nil || c.ParseCustomModule == nil || custom.ModuleName != *c.ParseCustomModule {
			r.check(c.ID, "custom module", "mismatch")
		}
	}
	r.done()
}

func TestGoldenValidate(t *testing.T) {
	r := &goldenReport{t: t}
	for _, c := range loadGolden(t) {
		if c.Kind != "ekpol" || !c.Parse.OK {
			continue
		}
		p, err := Parse(c.Src, "EkpolModule")
		if err != nil {
			continue
		}
		ds, err := ValidateB64(p)
		if msg := diffErr(c.Validate, err); msg != "" {
			r.check(c.ID, "validate", msg)
			continue
		}
		if err == nil {
			if len(ds) != 64 {
				r.check(c.ID, "validate", "descriptor count")
			} else if got := sha(kpol.PackImage(ds)); got != c.Validate.SHA256 {
				r.check(c.ID, "validate", "image sha "+got+" want "+c.Validate.SHA256)
			} else {
				r.check(c.ID, "validate", "")
			}
		}
	}
	r.done()
}

func parseFailure(c *goldenCase) *outcome {
	return &outcome{OK: false, Code: c.Parse.Code, Message: c.Parse.Message, Crash: c.Parse.Crash}
}

func TestGoldenToKPOL(t *testing.T) {
	ready := kpolReady()
	r := &goldenReport{t: t}
	skipped := 0
	for _, c := range loadGolden(t) {
		if c.Kind != "ekpol" {
			continue
		}
		if !c.Parse.OK {
			_, err := ToKPOL(c.Src, "EkpolModule")
			r.check(c.ID, "to_kpol(parse failure)", diffErr(parseFailure(&c), err))
			continue
		}
		p, err := Parse(c.Src, "EkpolModule")
		if err != nil {
			continue
		}
		needsKPOL := len(p.Tests) > 0
		if needsKPOL && !ready {
			skipped++
			continue
		}
		text, err := ProgramToKPOL(p, false)
		if msg := diffErr(c.ToKPOL, err); msg != "" {
			r.check(c.ID, "to_kpol", msg)
		} else if err == nil && text != c.ToKPOL.Text {
			r.check(c.ID, "to_kpol", "text differs:\n"+text+"\nwant:\n"+c.ToKPOL.Text)
		} else {
			r.check(c.ID, "to_kpol", "")
		}

		text, err = ProgramToKPOL(p, true)
		want := c.ToKPOLSynth
		if want.Same {
			want = c.ToKPOL
		}
		if msg := diffErr(want, err); msg != "" {
			r.check(c.ID, "to_kpol(synth)", msg)
		} else if err == nil && text != want.Text {
			r.check(c.ID, "to_kpol(synth)", "text differs:\n"+text+"\nwant:\n"+want.Text)
		} else {
			r.check(c.ID, "to_kpol(synth)", "")
		}
	}
	if skipped > 0 {
		t.Logf("skipped %d cases that execute embedded tests: kpol parser/verifier not implemented yet", skipped)
	}
	r.done()
}

func TestGoldenImage(t *testing.T) {
	if !kpolReady() {
		t.Skip("kpol.Parse is not implemented yet: CME cross-check unavailable")
	}
	r := &goldenReport{t: t}
	for _, c := range loadGolden(t) {
		if c.Kind != "ekpol" {
			continue
		}
		img, err := CompileImage(c.Src)
		if !c.Parse.OK {
			r.check(c.ID, "image(parse failure)", diffErr(parseFailure(&c), err))
			continue
		}
		if msg := diffErr(c.Image, err); msg != "" {
			r.check(c.ID, "image", msg)
			continue
		}
		if err == nil && (len(img) != 1024 || sha(img) != c.Image.SHA256) {
			r.check(c.ID, "image", "sha "+sha(img)+" want "+c.Image.SHA256)
			continue
		}
		r.check(c.ID, "image", "")
	}
	r.done()
}

func TestGoldenToEKPOL(t *testing.T) {
	if !kpolReady() {
		t.Skip("kpol.Parse is not implemented yet: KPOL -> EKPOL golden cases skipped")
	}
	r := &goldenReport{t: t}
	for _, c := range loadGolden(t) {
		if c.Kind != "kpol" {
			continue
		}
		for style, want := range map[string]*outcome{"symbolic": c.ToEKPOLSymbolic, "keyword": c.ToEKPOLKeyword} {
			text, err := ToEKPOL(c.Src, style)
			if msg := diffErr(want, err); msg != "" {
				r.check(c.ID, "to_ekpol "+style, msg)
			} else if err == nil && text != want.Text {
				r.check(c.ID, "to_ekpol "+style, "text differs:\n"+text+"\nwant:\n"+want.Text)
			} else {
				r.check(c.ID, "to_ekpol "+style, "")
			}
			if err != nil {
				continue
			}
			rt := c.Roundtrip[style]
			img, err := CompileImage(text)
			if rt == nil {
				continue
			}
			if rt.Stage == "image" {
				r.check(c.ID, "kpol roundtrip "+style, diffErr(&outcome{Code: rt.Code, Message: rt.Message, Crash: rt.Crash}, err))
				continue
			}
			if err != nil {
				r.check(c.ID, "kpol roundtrip "+style, err.Error())
				continue
			}
			r.check(c.ID, "kpol roundtrip "+style, "")
			if sha(img) != rt.ImageSHA || rt.ASCII != isASCII(text) {
				r.check(c.ID, "kpol roundtrip "+style, "image or ASCII mismatch")
			}
		}
	}
	r.done()
}

func TestGoldenRoundtrip(t *testing.T) {
	if !kpolReady() {
		t.Skip("kpol.Parse is not implemented yet: EKPOL -> KPOL -> EKPOL round trip skipped")
	}
	r := &goldenReport{t: t}
	for _, c := range loadGolden(t) {
		if c.Kind != "ekpol" || c.Roundtrip == nil {
			continue
		}
		k1, err := ToKPOL(c.Src, "EkpolModule")
		if err != nil {
			r.check(c.ID, "roundtrip", "ToKPOL failed: "+err.Error())
			continue
		}
		orig, err := CompileImage(c.Src)
		if err != nil {
			r.check(c.ID, "roundtrip", "CompileImage failed: "+err.Error())
			continue
		}
		for style, want := range c.Roundtrip {
			e1, err := ToEKPOL(k1, style)
			if want.Stage == "to_ekpol" {
				r.check(c.ID, "roundtrip "+style, diffErr(&outcome{Code: want.Code, Message: want.Message, Crash: want.Crash}, err))
				continue
			}
			if err != nil {
				r.check(c.ID, "roundtrip "+style, "ToEKPOL: "+err.Error())
				continue
			}
			if !isASCII(e1) || want.ASCII != isASCII(e1) || sha([]byte(e1)) != want.EkpolSHA {
				r.check(c.ID, "roundtrip "+style, "EKPOL text mismatch:\n"+e1)
				continue
			}
			img, err := CompileImage(e1)
			if want.Stage == "image" {
				r.check(c.ID, "roundtrip "+style, diffErr(&outcome{Code: want.Code, Message: want.Message, Crash: want.Crash}, err))
				continue
			}
			if err != nil || sha(img) != want.ImageSHA {
				r.check(c.ID, "roundtrip "+style, "image mismatch")
				continue
			}
			k2, err := ToKPOL(e1, "EkpolModule")
			if want.Stage == "to_kpol" {
				r.check(c.ID, "roundtrip "+style, diffErr(&outcome{Code: want.Code, Message: want.Message, Crash: want.Crash}, err))
				continue
			}
			if err != nil || sha([]byte(k2)) != want.Kpol2SHA {
				r.check(c.ID, "roundtrip "+style, "second KPOL mismatch")
				continue
			}
			r.check(c.ID, "roundtrip "+style, "")
			_ = orig
		}
	}
	r.done()
}

func isASCII(s string) bool {
	for i := 0; i < len(s); i++ {
		if s[i] >= 0x80 {
			return false
		}
	}
	return true
}

// dumpProgram renders a Program in the shape written by gen_ekpol_golden.py.
func dumpProgram(p *Program) map[string]any {
	str := func(s string) any { return s }
	nullable := func(s string) any {
		if s == "" {
			return nil
		}
		return s
	}
	bigStr := func(v interface{ String() string }, isNil bool) any {
		if isNil {
			return nil
		}
		return v.String()
	}
	concepts := make([]any, 0, len(p.Concepts))
	for i := range p.Concepts {
		c := &p.Concepts[i]
		invs := make([]any, 0)
		for _, inv := range c.Invariants {
			invs = append(invs, map[string]any{
				"kind": inv.Kind, "op": inv.Op, "value": inv.Value.String(),
				"lo": bigStr(inv.Lo, inv.Lo == nil), "hi": bigStr(inv.Hi, inv.Hi == nil),
			})
		}
		rules := make([]any, 0)
		for j := range c.Rules {
			r := &c.Rules[j]
			acts := make([]any, 0)
			for _, a := range r.Actions {
				acts = append(acts, map[string]any{"kind": a.Kind, "target": a.Target, "operand": a.Operand.Repr(), "raw": a.RawText})
			}
			pr := &r.Predicate
			rules = append(rules, map[string]any{
				"trigger": r.TriggerKind, "event": nullable(r.EventName), "param": r.ParamName, "param_type": r.ParamType,
				"watch": nullable(r.WatchConcept), "exec": append([]string{}, r.ExecParams...),
				"pred": map[string]any{
					"kind": pr.Kind, "var": pr.Var, "op": pr.Op, "value": pr.Value.Repr(),
					"lo": bigStr(pr.Lo, pr.Lo == nil), "hi": bigStr(pr.Hi, pr.Hi == nil),
					"inverted": pr.Inverted, "raw": pr.RawText,
				},
				"actions": acts, "post_read": r.PostReadBarrier, "rule_name": nullable(r.RuleName),
			})
		}
		concepts = append(concepts, map[string]any{
			"name": c.Name, "type": c.Type, "raw_type": c.RawType, "init": c.Initial.Repr(), "undef": c.UndefInit,
			"invariants": invs, "annotations": append([]string{}, c.Annotations...), "rules": rules,
		})
	}
	tests := make([]any, 0)
	for _, t := range p.Tests {
		steps := make([]any, 0)
		for _, s := range t.Steps {
			var param any
			if s.HasParamName {
				param = s.ParamName
			}
			extra := make([]any, 0)
			for _, x := range s.ExtraArgs {
				extra = append(extra, x.String())
			}
			steps = append(steps, map[string]any{
				"kind": s.Kind, "target": s.Target, "param": param, "op": s.Op, "value": s.Value.Repr(), "extra": extra,
			})
		}
		tests = append(tests, map[string]any{"name": t.Name, "steps": steps})
	}
	return map[string]any{
		"module": str(p.ModuleName), "stdin": append([]string{}, p.StdinConcepts...),
		"stdout": append([]string{}, p.StdoutConcepts...), "stderr": append([]string{}, p.StderrConcepts...),
		"conceptual_only": p.IsConceptualOnly(), "concepts": concepts, "tests": tests,
	}
}
