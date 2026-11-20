package kpol

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"testing"
)

// The CME golden file is produced by testdata/gen_cme_golden.py from the Python
// reference implementation; these tests replay it against the Go profile
// compilers.

type cmeGoldenResult struct {
	OK    bool       `json:"ok"`
	Kind  string     `json:"kind"`
	Text  string     `json:"text"`
	Sha   string     `json:"sha"`
	Slots []string   `json:"slots"` // "<cid>:<32 hex digits>" for every non-zero slot
	Dis   [][]uint64 `json:"dis"`   // cid, W0, W1, pred, flags, hazard, action, W3 as decoded by the reference
}

type cmeGoldenCase struct {
	ID             string            `json:"id"`
	Group          string            `json:"group"`
	Src            int               `json:"src"`
	Profile        string            `json:"profile"`
	ACL            map[string]int    `json:"acl"`
	Cascade        map[string]string `json:"cascade"`
	Rule           string            `json:"rule"`
	Pol            string            `json:"pol"`
	StripAliasFlag bool              `json:"strip_alias_flag"`
	Mutant         *struct {
		Base string `json:"base"`
		Kind string `json:"kind"`
	} `json:"mutant"`
	Result cmeGoldenResult `json:"result"`
}

type cmeGoldenACL struct {
	ID         string         `json:"id"`
	Src        int            `json:"src"`
	ACL        map[string]int `json:"acl"`
	Violations []string       `json:"violations"`
}

type cmeGolden struct {
	Meta struct {
		Cases   int `json:"cases"`
		Mutants int `json:"mutants"`
	} `json:"meta"`
	Sources    []string          `json:"sources"`
	Cases      []cmeGoldenCase   `json:"cases"`
	ACLSources []string          `json:"acl_sources"`
	ACLDirect  []cmeGoldenACL    `json:"acl_direct"`
	parsed     map[int]*cmeParse `json:"-"`
}

type cmeParse struct {
	m   *Module
	err error
}

var (
	cmeGoldenOnce sync.Once
	cmeGoldenData *cmeGolden
	cmeGoldenErr  error
)

func loadCMEGolden(t testing.TB) *cmeGolden {
	t.Helper()
	cmeGoldenOnce.Do(func() {
		data, err := readGoldenGz("../testdata/cme_golden.json.gz")
		if err != nil {
			cmeGoldenErr = err
			return
		}
		g := &cmeGolden{}
		if err := json.Unmarshal(data, g); err != nil {
			cmeGoldenErr = err
			return
		}
		g.parsed = make(map[int]*cmeParse)
		cmeGoldenData = g
	})
	if cmeGoldenErr != nil {
		t.Fatalf("cme_golden.json: %v", cmeGoldenErr)
	}
	return cmeGoldenData
}

// module parses source i once; the reference builds modules with Parser(...).parse().
func (g *cmeGolden) module(i int) (*Module, error) {
	if p, ok := g.parsed[i]; ok {
		return p.m, p.err
	}
	m, err := ParseUnchecked(g.Sources[i])
	g.parsed[i] = &cmeParse{m, err}
	return m, err
}

func (c *cmeGoldenCase) options() []CompileOption {
	var opts []CompileOption
	if c.ACL != nil {
		opts = append(opts, WithACL(c.ACL))
	}
	if c.Cascade != nil {
		opts = append(opts, WithCascadeMap(c.Cascade))
	}
	return opts
}

// crashCodes are the Code values that stand for an unhandled Python exception.
var crashCodes = map[string]bool{CodeRTType: true, CodeRTOverflow: true, CodeRTDecimal: true, CodeRTValue: true, CodeParseDepth: true}

// slotsOf lists the non-zero slots of an image in the golden notation.
func slotsOf(img []byte) []string {
	var out []string
	for cid := 0; cid < SlotCount; cid++ {
		raw := img[cid*SlotSize : (cid+1)*SlotSize]
		zero := true
		for _, b := range raw {
			if b != 0 {
				zero = false
			}
		}
		if !zero {
			out = append(out, fmt.Sprintf("%d:%s", cid, hex.EncodeToString(raw)))
		}
	}
	return out
}

// checkCMECase replays one golden case; it returns the empty string on a match.
func checkCMECase(g *cmeGolden, c *cmeGoldenCase) string {
	m, err := g.module(c.Src)
	if err != nil {
		return "ParseUnchecked rejects a source accepted by the reference: " + err.Error()
	}
	if c.StripAliasFlag {
		cp := *m
		cp.PhaseAliasesUsed = false
		m = &cp
	}
	opts := c.options()
	img, err := CompileProfile(m, c.Profile, opts...)
	ds, derr := CompileProfileDescriptors(m, c.Profile, opts...)
	if (err == nil) != (derr == nil) || (err != nil && err.Error() != derr.Error()) {
		return fmt.Sprintf("CompileProfile (%v) and CompileProfileDescriptors (%v) disagree", err, derr)
	}
	res := c.Result
	if !res.OK {
		var e *Error
		if err == nil {
			return fmt.Sprintf("accepted; reference: %s %q", res.Kind, res.Text)
		}
		if !errors.As(err, &e) || e.Code == "" {
			return fmt.Sprintf("error %v is not a coded *Error", err)
		}
		if res.Kind == "crash" {
			if !crashCodes[e.Code] {
				return fmt.Sprintf("reference crashed with %s; got %q", res.Text, err)
			}
			return ""
		}
		if err.Error() != res.Text {
			return fmt.Sprintf("error\n  got  %q\n  want %q", err.Error(), res.Text)
		}
		return ""
	}
	if err != nil {
		return fmt.Sprintf("rejected: %v; reference accepted", err)
	}
	if len(img) != ImageSize {
		return fmt.Sprintf("image has %d bytes", len(img))
	}
	if sum := sha256.Sum256(img); hex.EncodeToString(sum[:]) != res.Sha {
		return fmt.Sprintf("sha256 %x, want %s", sum, res.Sha)
	}
	if got := slotsOf(img); strings.Join(got, ",") != strings.Join(res.Slots, ",") {
		return fmt.Sprintf("slots\n  got  %v\n  want %v", got, res.Slots)
	}

	// kpol.Disassemble must agree with the reference decoding, and the
	// descriptors returned by CompileProfileDescriptors must be the same slots.
	dis, err := Disassemble(img)
	if err != nil {
		return "Disassemble: " + err.Error()
	}
	if len(dis) != SlotCount {
		return fmt.Sprintf("Disassemble returned %d slots", len(dis))
	}
	want := map[int][]uint64{}
	for _, d := range res.Dis {
		want[int(d[0])] = d
	}
	for cid, d := range dis {
		row := []uint64{uint64(cid), uint64(d.CurrentState), uint64(d.OperandVal), uint64(d.PredOpcode),
			uint64(d.GuardFlags), uint64(d.HazardLimit), uint64(d.ActionOpcode), uint64(d.SubscriberCID)}
		w, programmed := want[cid]
		if !programmed {
			w = []uint64{uint64(cid), 0, 0, 0, 0, 0, 0, 0}
		}
		if fmt.Sprint(row) != fmt.Sprint(w) {
			return fmt.Sprintf("Disassemble slot %d = %v, reference %v", cid, row, w)
		}
	}
	for i, d := range ds {
		if d.CID != i || d.Name != m.States[i].Name {
			return fmt.Sprintf("descriptor %d is %d/%q, want state %q", i, d.CID, d.Name, m.States[i].Name)
		}
		dd := dis[i]
		dd.Name = d.Name
		if dd != d {
			return fmt.Sprintf("descriptor %d = %+v, Disassemble %+v", i, d, dd)
		}
	}
	for cid := len(ds); cid < SlotCount; cid++ {
		if _, programmed := want[cid]; programmed {
			return fmt.Sprintf("slot %d is programmed but CompileProfileDescriptors returned %d descriptors", cid, len(ds))
		}
	}
	return ""
}

func TestCMEGolden(t *testing.T) {
	g := loadCMEGolden(t)
	if len(g.Cases) < 1000 {
		t.Fatalf("golden file has only %d cases", len(g.Cases))
	}
	byGroup := map[string][2]int{} // group -> {cases, mismatches}
	mismatches := 0
	for i := range g.Cases {
		c := &g.Cases[i]
		msg := checkCMECase(g, c)
		n := byGroup[c.Group]
		n[0]++
		if msg != "" {
			n[1]++
			mismatches++
			if mismatches <= 25 {
				t.Errorf("%s [%s]: %s", c.ID, c.Profile, msg)
			}
		}
		byGroup[c.Group] = n
	}
	t.Logf("cases=%d mutants=%d mismatches=%d groups=%v", len(g.Cases), g.Meta.Mutants, mismatches, byGroup)
	if mismatches > 0 {
		t.Fatalf("%d golden mismatches", mismatches)
	}
}

func TestCMEGoldenSize(t *testing.T) {
	g := loadCMEGolden(t)
	if g.Meta.Mutants < 500 {
		t.Errorf("only %d systematic mutations", g.Meta.Mutants)
	}
	groups := map[string]int{}
	for _, c := range g.Cases {
		groups[c.Group]++
	}
	for _, want := range []struct {
		group string
		n     int
	}{{"file", 14}, {"guide", 10}, {"pytest", 50}, {"hand", 300}, {"mutation", 1000}, {"acl", 60}, {"cascade", 40}, {"profile", 10}} {
		if groups[want.group] < want.n {
			t.Errorf("group %q has %d cases, want at least %d", want.group, groups[want.group], want.n)
		}
	}
}

// TestCMEGoldenACLDirect replays check_module_security_acl, including Pin<Out> states.
func TestCMEGoldenACLDirect(t *testing.T) {
	g := loadCMEGolden(t)
	if len(g.ACLDirect) < 20 {
		t.Fatalf("only %d direct ACL cases", len(g.ACLDirect))
	}
	withViolations := 0
	for _, c := range g.ACLDirect {
		m, err := ParseUnchecked(g.ACLSources[c.Src])
		if err != nil {
			t.Fatalf("%s: %v", c.ID, err)
		}
		got := CheckSecurityACL(m, c.ACL)
		if strings.Join(got, "\n") != strings.Join(c.Violations, "\n") {
			t.Errorf("%s: violations\n  got  %q\n  want %q", c.ID, got, c.Violations)
		}
		if len(c.Violations) > 0 {
			withViolations++
		}
	}
	if withViolations < 20 {
		t.Errorf("only %d direct ACL cases have violations", withViolations)
	}
}

// TestCMEGoldenDiagnosticsCovered: every class of profile diagnostic has golden
// cases (the negative control of the compilers).
func TestCMEGoldenDiagnosticsCovered(t *testing.T) {
	g := loadCMEGolden(t)
	seen := map[string]int{}
	for _, c := range g.Cases {
		if !c.Result.OK && c.Result.Kind == "kpol" {
			seen[c.Result.Text[:strings.Index(c.Result.Text, ":")]]++
		}
	}
	for _, code := range []string{
		"B3-TYPE", "B3-SHAPE", "B3-INVARIANT", "B3-ACTION", "B3-GUARD", "B3-PROOF", "B3-ACL", "B3-PROFILE",
		"CME2-TYPE", "CME2-SHAPE", "CME2-INVARIANT", "CME2-GUARD", "CME2-HAZARD", "CME2-RANGE", "CME2-ACTION",
		"CME2-CASCADE", "CME2-OPERAND-COLLISION", "CME2-PROOF", "CME2-ACL",
	} {
		if seen[code] < 5 {
			t.Errorf("only %d golden cases end in %s", seen[code], code)
		}
	}
}

// TestCMEGoldenCoverage requires, for every condition of KPOL-P1-1..10 and
// KPOL-P2-1..18, a positive and a negative golden case.
func TestCMEGoldenCoverage(t *testing.T) {
	g := loadCMEGolden(t)
	type key struct{ rule, pol string }
	seen := map[key]int{}
	for _, c := range g.Cases {
		if c.Rule != "" {
			seen[key{c.Rule, c.Pol}]++
		}
	}
	for i := 1; i <= 11; i++ {
		for _, pol := range []string{"pos", "neg"} {
			if i == 11 && pol == "neg" {
				continue // lowering: see TestCMELoweringMatrix
			}
			if seen[key{fmt.Sprintf("P1-%d", i), pol}] == 0 {
				t.Errorf("no %s case for KPOL-P1-%d", pol, i)
			}
		}
	}
	for i := 1; i <= 19; i++ {
		for _, pol := range []string{"pos", "neg"} {
			if i == 19 && pol == "neg" {
				continue
			}
			if seen[key{fmt.Sprintf("P2-%d", i), pol}] == 0 {
				t.Errorf("no %s case for KPOL-P2-%d", pol, i)
			}
		}
	}
}
