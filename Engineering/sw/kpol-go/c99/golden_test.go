package c99

import (
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"os/exec"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"testing"
	"unicode/utf8"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

type goldenDoc struct {
	Meta struct {
		Z3CLI             string         `json:"z3_cli"`
		SolverPlaceholder string         `json:"solver_placeholder"`
		Counts            map[string]int `json:"counts"`
	} `json:"meta"`
	Pyspace     []int        `json:"pyspace"`
	Sanitize    [][2]string  `json:"sanitize"`
	EmitCases   []emitCase   `json:"emit_cases"`
	CertMutants []certMutant `json:"cert_mutants"`
	EngineCases []engineCase `json:"engine_cases"`
}

type refEmit struct {
	OK      bool    `json:"ok"`
	Exc     string  `json:"exc"`
	Message string  `json:"message"`
	SHA     string  `json:"c99_sha256"`
	Len     int     `json:"c99_len"`
	C99     *string `json:"c99"`
}

type refCert struct {
	OK       bool     `json:"ok"`
	Exc      string   `json:"exc"`
	Message  string   `json:"message"`
	JSONSHA  string   `json:"json_sha256"`
	JSON     *string  `json:"json"`
	Verdict  string   `json:"verdict"`
	Passed   bool     `json:"passed"`
	Statuses []string `json:"statuses"`
	Failures []string `json:"failures"`
}

type emitCase struct {
	ID              string            `json:"id"`
	Kind            string            `json:"kind"`
	Module          string            `json:"module"`
	Names           []string          `json:"names"`
	NameMap         map[string]string `json:"name_map"`
	AllowUnverified bool              `json:"allow_unverified"`
	Slots           [][5]uint64       `json:"slots"`
	ImageLen        *int              `json:"image_len"`
	DescList        [][]any           `json:"desc_list"`
	Emit            refEmit           `json:"emit"`
	Cert            refCert           `json:"cert"`
}

type refParse struct {
	OK         bool     `json:"ok"`
	Exc        string   `json:"exc"`
	Message    string   `json:"message"`
	Topo       []int    `json:"topo_order"`
	Reversed   bool     `json:"topo_loop_reversed"`
	DescSHA    string   `json:"descriptors_sha256"`
	FaultGate  bool     `json:"has_fault_gate"`
	Ops        []string `json:"ops"`
	RangeSext  bool     `json:"range_sext"`
	InvOvf     bool     `json:"inv_overflow"`
	InvNonneg  bool     `json:"inv_nonneg"`
	CommitInv  bool     `json:"commit_inv"`
	SelfSupres bool     `json:"self_suppress"`
}

type certMutant struct {
	ID     string      `json:"id"`
	Base   string      `json:"base"`
	Slots  [][5]uint64 `json:"slots"`
	Module string      `json:"module"`
	Names  []string    `json:"names"`
	Old    *string     `json:"old"`
	New    string      `json:"new"`
	Parse  refParse    `json:"parse"`
	Cert   refCert     `json:"cert"`
}

type engineCase struct {
	ID      string      `json:"id"`
	Slots   [][5]uint64 `json:"slots"`
	Events  [][]any     `json:"events"`
	Results [][]int64   `json:"results"`
	Digest  string      `json:"digest"`
	Final   struct {
		State     []int32 `json:"state"`
		ValidMask uint64  `json:"valid_mask"`
		Counters  []int64 `json:"counters"`
	} `json:"final"`
}

func loadGolden(t testing.TB) *goldenDoc {
	t.Helper()
	data, err := readGoldenGz(filepath.Join("..", "testdata", "c99_golden.json.gz"))
	if err != nil {
		t.Fatalf("read golden: %v", err)
	}
	var doc goldenDoc
	if err := json.Unmarshal(data, &doc); err != nil {
		t.Fatalf("decode golden: %v", err)
	}
	return &doc
}

func requireBinary(t testing.TB, name string) {
	t.Helper()
	if _, err := exec.LookPath(name); err != nil {
		t.Skipf("%s is not installed", name)
	}
}

func imageFromSlots(slots [][5]uint64) []byte {
	img := make([]byte, kpol.ImageSize)
	for _, s := range slots {
		off := int(s[0]) * kpol.SlotSize
		for w := 0; w < 4; w++ {
			binary.LittleEndian.PutUint32(img[off+4*w:], uint32(s[1+w]))
		}
	}
	return img
}

func (c *emitCase) options() Options {
	o := Options{ModuleName: c.Module, ConceptNames: c.Names, AllowUnverified: c.AllowUnverified}
	if c.NameMap != nil {
		o.ConceptNameMap = map[int]string{}
		for k, v := range c.NameMap {
			n, _ := strconv.Atoi(k)
			o.ConceptNameMap[n] = v
		}
	}
	return o
}

// input returns either a descriptor list (DescList cases) or an image.
func (c *emitCase) input() (descs []kpol.Descriptor, image []byte, useList bool) {
	switch {
	case c.DescList != nil:
		ds := []kpol.Descriptor{}
		for _, row := range c.DescList {
			f := func(i int) float64 { return row[i].(float64) }
			ds = append(ds, kpol.Descriptor{
				CID: int(f(0)), Name: row[1].(string), CurrentState: uint32(f(2)), OperandVal: uint32(f(3)),
				PredOpcode: uint8(f(4)), GuardFlags: uint8(f(5)), HazardLimit: uint8(f(6)), ActionOpcode: uint8(f(7)),
				SubscriberCID: uint32(f(8)),
			})
		}
		return ds, nil, true
	case c.ImageLen != nil:
		return nil, make([]byte, *c.ImageLen), false
	}
	return nil, imageFromSlots(c.Slots), false
}

func (c *emitCase) normalize() ([]kpol.Descriptor, error) {
	ds, img, useList := c.input()
	if useList {
		return NormalizeDescriptors(ds, c.options())
	}
	return NormalizeImage(img, c.options())
}

// renderOnly reproduces EmitC99 up to (and excluding) the Z3 certificate.
func renderOnly(descs []kpol.Descriptor, opts Options) (string, error) {
	active, edges := ExtractActiveCIDsAndEdges(descs)
	topo, err := ComputeTopologicalOrder(active, edges)
	if err != nil {
		if !opts.AllowUnverified {
			return "", &kpol.Error{Code: "C99-Z3-REJECTED", Msg: err.Error()}
		}
		topo = append([]int(nil), active...)
	}
	return renderC99(descs, topo, opts.moduleName(), tableSHA256(descs), defaultVerdictLabel, defaultSolverLabel), nil
}

// matchRefError checks a Go error against a reference exception record.
func matchRefError(t *testing.T, err error, exc, message string) {
	t.Helper()
	if err == nil {
		t.Errorf("expected error (%s: %s), got none", exc, message)
		return
	}
	var kerr *kpol.Error
	if !errors.As(err, &kerr) {
		t.Errorf("error %v is not a *kpol.Error", err)
		return
	}
	switch exc {
	case "C99EmitterError":
		if err.Error() != message {
			t.Errorf("error text\n got: %s\nwant: %s", err.Error(), message)
		}
	case "KpolError":
		// The Disassemble scaffold prefixes its code; the reference text has none.
		if kerr.Msg != message && err.Error() != message {
			t.Errorf("error text\n got: %s\nwant: %s", err.Error(), message)
		}
	default:
		// Unhandled Python exception (ValueError ...): Go reports a coded error.
		if !strings.HasSuffix(err.Error(), message) {
			t.Errorf("error text\n got: %s\nwant suffix: %s", err.Error(), message)
		}
	}
}

// certStatuses lists the check statuses in the reference's sorted-name order.
func certStatuses(c *Certificate) []string {
	var s []string
	for _, n := range []string{CheckP1, CheckP2, CheckP3, CheckP4} {
		s = append(s, c.Check(n).Status)
	}
	return s
}

func compareCert(t *testing.T, cert *Certificate, want refCert, placeholder string) {
	t.Helper()
	cert.Solver = placeholder
	raw, err := cert.JSON()
	if err != nil {
		t.Fatalf("JSON: %v", err)
	}
	if !json.Valid(raw) {
		t.Errorf("certificate is not valid JSON")
	}
	if cert.Verdict != want.Verdict || cert.Passed != want.Passed {
		t.Errorf("verdict %s/%v, want %s/%v", cert.Verdict, cert.Passed, want.Verdict, want.Passed)
	}
	if got := certStatuses(cert); !reflect.DeepEqual(got, want.Statuses) {
		t.Errorf("check statuses %v, want %v", got, want.Statuses)
	}
	if len(cert.Failures) != len(want.Failures) || (len(want.Failures) > 0 && !reflect.DeepEqual(cert.Failures, want.Failures)) {
		t.Errorf("failures\n got: %q\nwant: %q", cert.Failures, want.Failures)
	}
	if want.JSON != nil && string(raw) != *want.JSON {
		t.Errorf("certificate JSON differs from reference:\n%s\n---- want ----\n%s", raw, *want.JSON)
	}
	if got := sha256Hex(raw); got != want.JSONSHA {
		t.Errorf("certificate JSON sha256 %s, want %s", got, want.JSONSHA)
	}
}

func TestGoldenStatistics(t *testing.T) {
	doc := loadGolden(t)
	c := doc.Meta.Counts
	if c["emit_cases"] < 300 || c["emit_ok"]-c["corpus"] < 100 || c["cert_mutants"] < 50 || c["engine_cases"] < 50 {
		t.Fatalf("golden file too small: %v", c)
	}
	if len(doc.EmitCases) != c["emit_cases"] || len(doc.CertMutants) != c["cert_mutants"] || len(doc.EngineCases) != c["engine_cases"] {
		t.Fatalf("golden counts disagree with meta: %v", c)
	}
	t.Logf("golden: %d emit cases (%d emitted), %d certificate mutants, %d engine traces; reference %s",
		c["emit_cases"], c["emit_ok"], c["cert_mutants"], c["engine_cases"], doc.Meta.Z3CLI)
}

// TestGoldenRender needs no solver: the emitted text, its SHA-256 and the
// pre-Z3 diagnostics must equal the reference for every case.
func TestGoldenRender(t *testing.T) {
	doc := loadGolden(t)
	for i := range doc.EmitCases {
		c := &doc.EmitCases[i]
		t.Run(c.ID, func(t *testing.T) {
			descs, err := c.normalize()
			if err != nil {
				if c.Emit.OK {
					t.Fatalf("unexpected normalisation error: %v", err)
				}
				matchRefError(t, err, c.Emit.Exc, c.Emit.Message)
				return
			}
			text, err := renderOnly(descs, c.options())
			switch {
			case c.Emit.OK:
				if err != nil {
					t.Fatalf("unexpected error: %v", err)
				}
				if got := sha256Hex([]byte(text)); got != c.Emit.SHA || utf8.RuneCountInString(text) != c.Emit.Len {
					t.Errorf("C99 sha256/chars %s/%d, want %s/%d", got, utf8.RuneCountInString(text), c.Emit.SHA, c.Emit.Len)
				}
				if c.Emit.C99 != nil && text != *c.Emit.C99 {
					t.Errorf("C99 text differs from the reference")
				}
			case strings.HasPrefix(c.Emit.Message, "C99-Z3-REJECTED: C99-DAG-"):
				matchRefError(t, err, c.Emit.Exc, c.Emit.Message)
			default:
				if err != nil {
					t.Errorf("topology must be accepted before the certificate rejects it: %v", err)
				}
			}
		})
	}
}

// TestGoldenEmitAndCertificate runs the real fail-closed pipeline with Z3.
func TestGoldenEmitAndCertificate(t *testing.T) {
	requireBinary(t, "z3")
	doc := loadGolden(t)
	for i := range doc.EmitCases {
		c := &doc.EmitCases[i]
		t.Run(c.ID, func(t *testing.T) {
			t.Parallel()
			ds, img, useList := c.input()
			var text string
			var err error
			if useList {
				text, err = EmitC99(ds, c.options())
			} else {
				text, err = EmitC99FromImage(img, c.options())
			}
			if c.Emit.OK {
				if err != nil {
					t.Fatalf("EmitC99: %v", err)
				}
				if got := sha256Hex([]byte(text)); got != c.Emit.SHA {
					t.Errorf("C99 sha256 %s, want %s", got, c.Emit.SHA)
				}
				if c.Emit.C99 != nil && text != *c.Emit.C99 {
					t.Errorf("C99 text differs from the reference")
				}
			} else {
				matchRefError(t, err, c.Emit.Exc, c.Emit.Message)
				text = ""
			}

			var cert *Certificate
			if useList {
				cert, err = ProveZ3(ds, text, c.options())
			} else {
				cert, err = ProveZ3FromImage(img, text, c.options())
			}
			if !c.Cert.OK {
				matchRefError(t, err, c.Cert.Exc, c.Cert.Message)
				return
			}
			if err != nil {
				t.Fatalf("ProveZ3: %v", err)
			}
			if !strings.HasPrefix(cert.Solver, "z3-cli (") {
				t.Errorf("solver label %q", cert.Solver)
			}
			compareCert(t, cert, c.Cert, doc.Meta.SolverPlaceholder)
			if c.Emit.OK != cert.Passed && !c.AllowUnverified {
				t.Errorf("emit ok=%v but certificate passed=%v", c.Emit.OK, cert.Passed)
			}
		})
	}
}

func mutatedSource(t *testing.T, m *certMutant) (image []byte, opts Options, src string) {
	t.Helper()
	image = imageFromSlots(m.Slots)
	opts = Options{ModuleName: m.Module, ConceptNames: m.Names}
	descs, err := NormalizeImage(image, opts)
	if err != nil {
		t.Fatal(err)
	}
	base, err := renderOnly(descs, opts)
	if err != nil {
		t.Fatal(err)
	}
	if m.Old == nil {
		return image, opts, m.New
	}
	if n := strings.Count(base, *m.Old); n != 1 {
		t.Fatalf("mutation anchor %q occurs %d times", *m.Old, n)
	}
	return image, opts, strings.Replace(base, *m.Old, m.New, 1)
}

func TestGoldenParseMutants(t *testing.T) {
	doc := loadGolden(t)
	for i := range doc.CertMutants {
		m := &doc.CertMutants[i]
		t.Run(m.ID, func(t *testing.T) {
			_, _, src := mutatedSource(t, m)
			p, err := ParseEmittedC99Source(src)
			if !m.Parse.OK {
				matchRefError(t, err, m.Parse.Exc, m.Parse.Message)
				return
			}
			if err != nil {
				t.Fatalf("ParseEmittedC99Source: %v", err)
			}
			var packed []byte
			for _, d := range p.Descriptors {
				pk := d.Pack()
				packed = append(packed, pk[:]...)
			}
			ops := []string{p.PredEqOp, p.PredNeqOp, p.PredGtOp, p.PredLtOp, p.RangeLoOp, p.RangeHiOp,
				p.ActIncOp, p.ActDecOp, p.ActAddOp, p.ActSubOp, p.SubOvfXorOp}
			if !reflect.DeepEqual(p.TopoOrder, m.Parse.Topo) || p.TopoLoopReversed != m.Parse.Reversed ||
				sha256Hex(packed) != m.Parse.DescSHA || p.HasFaultGate != m.Parse.FaultGate ||
				!reflect.DeepEqual(ops, m.Parse.Ops) || p.RangeSext != m.Parse.RangeSext ||
				p.InvariantChecksOverflow != m.Parse.InvOvf || p.InvariantChecksNonneg != m.Parse.InvNonneg ||
				p.CommitChecksInvariant != m.Parse.CommitInv || p.HasSelfSuppress != m.Parse.SelfSupres {
				t.Errorf("parsed module differs from reference: %+v vs %+v", p, m.Parse)
			}
		})
	}
}

func TestGoldenCertificateMutants(t *testing.T) {
	requireBinary(t, "z3")
	doc := loadGolden(t)
	for i := range doc.CertMutants {
		m := &doc.CertMutants[i]
		t.Run(m.ID, func(t *testing.T) {
			t.Parallel()
			image, opts, src := mutatedSource(t, m)
			cert, err := ProveZ3FromImage(image, src, opts)
			if !m.Cert.OK {
				matchRefError(t, err, m.Cert.Exc, m.Cert.Message)
				return
			}
			if err != nil {
				t.Fatalf("ProveZ3: %v", err)
			}
			compareCert(t, cert, m.Cert, doc.Meta.SolverPlaceholder)
		})
	}
}

func engineDigestLine(e *Engine) string {
	parts := make([]string, len(e.State))
	for i, s := range e.State {
		parts[i] = strconv.Itoa(int(s))
	}
	return fmt.Sprintf("%s|%d|%d,%d,%d,%d,%d\n", strings.Join(parts, ","), e.ValidMask, e.EventsProcessed,
		e.Commits, e.Rejects, e.FaultPropagations, e.LastCommittedState)
}

func TestGoldenEngine(t *testing.T) {
	doc := loadGolden(t)
	for i := range doc.EngineCases {
		c := &doc.EngineCases[i]
		t.Run(c.ID, func(t *testing.T) {
			eng, err := NewEngineFromImage(imageFromSlots(c.Slots), Options{})
			if err != nil {
				t.Fatalf("NewEngine: %v", err)
			}
			var digest strings.Builder
			var results [][]int64
			for _, ev := range c.Events {
				op, cid, param := ev[0].(string), int(ev[1].(float64)), int32(ev[2].(float64))
				switch op {
				case "s":
					r := eng.Step(cid, param, ev[3].(bool))
					fault := int64(0)
					if r.FaultPropagated {
						fault = 1
					}
					results = append(results, []int64{int64(r.StepsExecuted), int64(r.Commits), int64(r.Rejects), fault, int64(r.LastState), int64(r.Status)})
				case "i":
					eng.InvalidateConcept(cid)
				case "r":
					eng.RevalidateConcept(cid, param)
				}
				digest.WriteString(engineDigestLine(eng))
			}
			if !reflect.DeepEqual(results, c.Results) {
				t.Errorf("step results differ:\n got: %v\nwant: %v", results, c.Results)
			}
			if got := sha256Hex([]byte(digest.String())); got != c.Digest {
				t.Errorf("state digest %s, want %s", got, c.Digest)
			}
			if !reflect.DeepEqual(eng.State[:], c.Final.State) || eng.ValidMask != c.Final.ValidMask {
				t.Errorf("final state/valid mask differ")
			}
			counters := []int64{int64(eng.EventsProcessed), int64(eng.Commits), int64(eng.Rejects), int64(eng.FaultPropagations), int64(eng.LastCommittedState)}
			if !reflect.DeepEqual(counters, c.Final.Counters) {
				t.Errorf("counters %v, want %v", counters, c.Final.Counters)
			}
		})
	}
}

func TestGoldenSanitizeAndWhitespace(t *testing.T) {
	doc := loadGolden(t)
	for _, v := range doc.Sanitize {
		if got := sanitizeIdent(v[0], "FALLBACK"); got != v[1] {
			t.Errorf("sanitizeIdent(%q) = %q, want %q", v[0], got, v[1])
		}
	}
	want := map[rune]bool{}
	for _, cp := range doc.Pyspace {
		want[rune(cp)] = true
	}
	for cp := rune(0); cp <= 0x10FFFF; cp++ {
		if cp >= 0xD800 && cp < 0xE000 {
			continue
		}
		if isPySpace(cp) != want[cp] {
			t.Fatalf("isPySpace(U+%04X) = %v, want %v", cp, isPySpace(cp), want[cp])
		}
	}
}
