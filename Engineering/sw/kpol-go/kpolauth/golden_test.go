package kpolauth

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
)

type goldenResult struct {
	OK      bool     `json:"ok"`
	Code    string   `json:"code"`
	Message string   `json:"message"`
	Span    []int    `json:"span"`
	H       string   `json:"h"`
	Crash   string   `json:"crash"`
	N       int      `json:"n"`
	Root    string   `json:"root"`
	DCodes  []string `json:"dcodes"`

	CodeO         []uint32 `json:"code_o"`
	BRAMSHA       string   `json:"bram_sha256"`
	DoGoSHA       string   `json:"dogo_sha256"`
	DoGoBinSHA    string   `json:"dogo_bin_sha256"`
	ConceptCount  int      `json:"concepts"`
	SubscriptionN int      `json:"subscriptions"`
}

type goldenCase struct {
	ID       int                          `json:"id"`
	Origin   string                       `json:"origin"`
	Src      string                       `json:"src"`
	Front    goldenResult                 `json:"front"`
	CP       goldenResult                 `json:"cp"`
	Rec      goldenResult                 `json:"rec"`
	RecCP    goldenResult                 `json:"reccp"`
	Lower    *goldenResult                `json:"lower"`
	LowerRec *goldenResult                `json:"lower_rec"`
	VM       map[string][]json.RawMessage `json:"vm"`
}

type goldenCLI struct {
	Src     string `json:"src"`
	JSON    string `json:"json"`
	BinHex  string `json:"bin_hex"`
	BRAMSHA string `json:"bram_sha256"`
}

type goldenSpecA2 struct {
	Src     string   `json:"src"`
	CodeO   []uint32 `json:"code_o"`
	BRAMSHA string   `json:"bram_sha256"`
}

type goldenFile struct {
	StepLimit int            `json:"step_limit"`
	Cases     []goldenCase   `json:"cases"`
	CLI       []goldenCLI    `json:"cli"`
	SpecA2    []goldenSpecA2 `json:"spec_a2"`
}

func loadGolden(t testing.TB) *goldenFile {
	t.Helper()
	path := filepath.Join("..", "testdata", "kpolauth_golden.json.gz")
	if p := os.Getenv("KPOLAUTH_GOLDEN"); p != "" {
		path = p // a larger corpus generated with --mutants / --lowering-mutants
	}
	data, err := readGoldenFile(path)
	if err != nil {
		t.Fatalf("golden file: %v", err)
	}
	var g goldenFile
	if err := json.Unmarshal(data, &g); err != nil {
		t.Fatalf("golden file: %v", err)
	}
	return &g
}

// mismatches collects the differences between Go and the golden file.
type mismatches struct {
	t     *testing.T
	count int
}

func (m *mismatches) addf(format string, args ...any) {
	m.count++
	if m.count <= 25 {
		m.t.Errorf(format, args...)
	}
}

func goldenCfgs() map[string]Config {
	cp := DefaultConfig()
	cp.NameLengthUnit = Codepoints
	recCP := RecordAllConfig()
	recCP.NameLengthUnit = Codepoints
	return map[string]Config{"cp": cp, "rec": RecordAllConfig(), "reccp": recCP}
}

// compareParse checks a Parse outcome against a golden frontend result.
func compareParse(m *mismatches, tag string, c *goldenCase, want goldenResult, cfg Config) *Program {
	prog, err := Parse(c.Src, cfg)
	if want.Crash != "" {
		var e *Error
		if !errors.As(err, &e) || e.Code != CodeNonDecimalDigit || want.Crash != "ValueError" {
			m.addf("case %d (%s) %s: reference crashed with %s, Go returned %v", c.ID, c.Origin, tag, want.Crash, err)
		}
		return nil
	}
	canon := parseCanon(prog, err)
	if shaStr(canon) != want.H {
		got := ""
		var e *Error
		if errors.As(err, &e) {
			got = e.Code + ": " + e.Msg
		}
		m.addf("case %d (%s) %s: canonical mismatch\n src=%q\n want ok=%v code=%s msg=%q\n got  ok=%v %s",
			c.ID, c.Origin, tag, c.Src, want.OK, want.Code, want.Message, err == nil, got)
		return prog
	}
	if tag != "front" {
		return prog
	}
	if err != nil {
		e := err.(*Error)
		if e.Code != want.Code || e.Msg != want.Message {
			m.addf("case %d %s: code/message %s %q != %s %q", c.ID, tag, e.Code, e.Msg, want.Code, want.Message)
		}
	} else {
		if len(prog.Items) != want.N {
			m.addf("case %d %s: %d items, want %d", c.ID, tag, len(prog.Items), want.N)
		}
		root := ""
		if len(prog.Items) > 0 {
			root = prog.Items[0].CSTName()
		}
		if root != want.Root && !(root == "" && want.Root == "") {
			m.addf("case %d %s: root %q, want %q", c.ID, tag, root, want.Root)
		}
	}
	return prog
}

func compareLower(m *mismatches, tag string, c *goldenCase, want *goldenResult, prog *Program) *Artifact {
	art, err := Lower(prog)
	if want.Crash != "" {
		var e *Error
		if !errors.As(err, &e) || e.Code != CodeLowerNonDecimalDigit || want.Crash != "ValueError" {
			m.addf("case %d (%s) %s: reference crashed with %s, Go returned %v", c.ID, c.Origin, tag, want.Crash, err)
		}
		return nil
	}
	if shaStr(lowerCanon(art, err)) != want.H {
		var e *Error
		got := "ok"
		if errors.As(err, &e) {
			got = e.Code + ": " + e.Msg
		}
		m.addf("case %d (%s) %s: lowering mismatch\n src=%q\n want ok=%v %s %q\n got  %s",
			c.ID, c.Origin, tag, c.Src, want.OK, want.Code, want.Message, got)
		return art
	}
	if err != nil {
		e := err.(*Error)
		if tag != "lower" {
			return nil
		}
		if e.Code != want.Code || e.Msg != want.Message {
			m.addf("case %d %s: code/message %s %q != %s %q", c.ID, tag, e.Code, e.Msg, want.Code, want.Message)
		}
		if (e.Span == nil) != (want.Span == nil) {
			m.addf("case %d %s: span presence differs", c.ID, tag)
		}
		return nil
	}
	return art
}

func compareArtifact(m *mismatches, c *goldenCase, want *goldenResult, art *Artifact) {
	if !equalWords(art.CodeO(), want.CodeO) {
		m.addf("case %d: code_o %x, want %x", c.ID, art.CodeO(), want.CodeO)
	}
	if got := shaHex(art.BRAMImage()); got != want.BRAMSHA {
		m.addf("case %d: BRAM sha %s, want %s", c.ID, got, want.BRAMSHA)
	}
	doc, _ := art.DoGoJSON()
	if got := shaHex(doc); got != want.DoGoSHA {
		m.addf("case %d: DoGoJSON sha %s, want %s", c.ID, got, want.DoGoSHA)
	}
	if got := shaHex(art.DoGoBinary()); got != want.DoGoBinSHA {
		m.addf("case %d: Do/Go binary sha %s, want %s", c.ID, got, want.DoGoBinSHA)
	}
	if len(art.Concepts) != want.ConceptCount || len(art.Subscriptions) != want.SubscriptionN {
		m.addf("case %d: table sizes %d/%d, want %d/%d", c.ID, len(art.Concepts), len(art.Subscriptions),
			want.ConceptCount, want.SubscriptionN)
	}
}

func equalWords(a, b []uint32) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

// compareVM replays the golden traces on the Go machine.
func compareVM(m *mismatches, c *goldenCase, art *Artifact) {
	for label, steps := range c.VM {
		machine := NewMachine(art)
		for n, raw := range steps {
			var parts []json.RawMessage
			if err := json.Unmarshal(raw, &parts); err != nil || len(parts) < 3 {
				m.addf("case %d: bad VM step %s", c.ID, raw)
				return
			}
			var cid int
			var val int64
			_ = json.Unmarshal(parts[0], &cid)
			_ = json.Unmarshal(parts[1], &val)
			err := machine.TriggerExternal(cid, val)

			var tag string
			if json.Unmarshal(parts[2], &tag) == nil {
				var e *Error
				wantCodes := map[string][]string{
					"steps":                {CodeVMSteps},
					"overflow":             {CodeVMOverflow},
					"error:IndexError":     {CodeVMIndex, CodeVMStack},
					"error:AssertionError": {CodeVMOpcode, CodeVMExit},
				}[tag]
				if !errors.As(err, &e) || !slices.Contains(wantCodes, e.Code) {
					m.addf("case %d vm %s step %d: reference %q, Go %v", c.ID, label, n, tag, err)
				}
				break
			}
			if err != nil {
				m.addf("case %d vm %s step %d: unexpected error %v", c.ID, label, n, err)
				break
			}
			var values []int64
			var bigDot []int
			_ = json.Unmarshal(parts[2], &values)
			_ = json.Unmarshal(parts[3], &bigDot)
			if !equalInts64(machine.Values(), values) || !equalInts(machine.BigDotOK(), bigDot) {
				m.addf("case %d (%s) vm %s step %d (%d<-%d): Go %v %v, want %v %v", c.ID, c.Origin, label, n,
					cid, val, machine.Values(), machine.BigDotOK(), values, bigDot)
				break
			}
		}
	}
}

func equalInts64(a, b []int64) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func equalInts(a, b []int) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

// TestGoldenDifferential replays the corpus, the systematic mutations, the CLI
// artifacts and the VM traces recorded from the Python reference.
func TestGoldenDifferential(t *testing.T) {
	g := loadGolden(t)
	if g.StepLimit != DefaultStepLimit {
		t.Fatalf("golden step limit %d != DefaultStepLimit %d", g.StepLimit, DefaultStepLimit)
	}
	m := &mismatches{t: t}
	cfgs := goldenCfgs()
	var compared, lowered, vmTraces, mutants int

	for i := range g.Cases {
		c := &g.Cases[i]
		if strings.HasPrefix(c.Origin, "mutant:") {
			mutants++
		}
		prog := compareParse(m, "front", c, c.Front, DefaultConfig())
		compareParse(m, "cp", c, c.CP, cfgs["cp"])
		recProg := compareParse(m, "rec", c, c.Rec, cfgs["rec"])
		compareParse(m, "reccp", c, c.RecCP, cfgs["reccp"])
		compared += 4

		if c.LowerRec != nil && recProg != nil {
			compareLower(m, "lower_rec", c, c.LowerRec, recProg)
			compared++
		}
		if c.Lower != nil && prog != nil {
			art := compareLower(m, "lower", c, c.Lower, prog)
			compared++
			if c.Lower.OK && art != nil {
				lowered++
				compareArtifact(m, c, c.Lower, art)
				compareVM(m, c, art)
				vmTraces += len(c.VM)
			}
		} else if c.Lower != nil && prog == nil && c.Front.Crash == "" {
			m.addf("case %d: golden has a lowering result but Go parse failed", c.ID)
		}
	}
	t.Logf("golden: %d cases (%d mutants), %d comparisons, %d lowered artifacts, %d VM traces, %d mismatches",
		len(g.Cases), mutants, compared, lowered, vmTraces, m.count)
	if mutants < 300 {
		t.Errorf("golden file has %d mutants, need at least 300", mutants)
	}
	if m.count != 0 {
		t.Errorf("%d differences from the Python reference", m.count)
	}
}

// TestGoldenSpecA2 checks the Annex A.2 vectors recorded from the specification.
func TestGoldenSpecA2(t *testing.T) {
	g := loadGolden(t)
	if len(g.SpecA2) != 3 {
		t.Fatalf("expected 3 A.2 vectors, got %d", len(g.SpecA2))
	}
	for _, v := range g.SpecA2 {
		art, err := LowerSource(v.Src)
		if err != nil {
			t.Fatalf("%q: %v", v.Src, err)
		}
		if !equalWords(art.CodeO(), v.CodeO) || shaHex(art.BRAMImage()) != v.BRAMSHA {
			t.Errorf("%q: artifact differs from the specification", v.Src)
		}
	}
}

// TestGoldenCLIArtifacts compares DoGoJSON and the binary form byte for byte.
func TestGoldenCLIArtifacts(t *testing.T) {
	g := loadGolden(t)
	if len(g.CLI) < 20 {
		t.Fatalf("only %d CLI cases", len(g.CLI))
	}
	for i, c := range g.CLI {
		art, err := LowerSource(c.Src)
		if err != nil {
			t.Fatalf("cli case %d: %v", i, err)
		}
		doc, _ := art.DoGoJSON()
		if string(doc) != c.JSON {
			t.Errorf("cli case %d: JSON differs\n got: %s\nwant: %s", i, doc, c.JSON)
		}
		if got := hx(string(art.DoGoBinary())); got != c.BinHex {
			t.Errorf("cli case %d: binary differs", i)
		}
		if shaHex(art.BRAMImage()) != c.BRAMSHA {
			t.Errorf("cli case %d: BRAM differs", i)
		}
	}
}
