package c99

import (
	"bytes"
	"encoding/json"
	"fmt"
	"hash/fnv"
	"math/rand"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"testing"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

var gccFlags = []string{"-std=c99", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic"}

const cDriver = `#include <stdio.h>
#include "module.h"

static void dump(const km_safety_ctx_t *c) {
    unsigned i;
    for (i = 0u; i < 64u; ++i) {
        printf("%s%ld", (i == 0u) ? "" : ",", (long)c->state[i]);
    }
    printf("|%llu|%lu,%lu,%lu,%lu,%ld\n", (unsigned long long)c->valid_mask,
           (unsigned long)c->events_processed, (unsigned long)c->commits,
           (unsigned long)c->rejects, (unsigned long)c->fault_propagations,
           (long)c->last_committed_state);
}

int main(void) {
    km_safety_ctx_t ctx;
    char op;
    long cid;
    long param;
    int valid;
    km_safety_init(&ctx);
    while (scanf(" %c %ld %ld %d", &op, &cid, &param, &valid) == 4) {
        if (op == 's') {
            km_safety_step_result_t r = km_safety_step_event(&ctx, (uint8_t)cid, (int32_t)param, valid != 0);
            printf("R %lu,%lu,%lu,%d,%ld,%d\n", (unsigned long)r.steps_executed, (unsigned long)r.commits,
                   (unsigned long)r.rejects, r.fault_propagated ? 1 : 0, (long)r.last_state, (int)r.status);
        } else if (op == 'i') {
            km_safety_invalidate_concept(&ctx, (uint8_t)cid);
        } else {
            km_safety_revalidate_concept(&ctx, (uint8_t)cid, (int32_t)param);
        }
        dump(&ctx);
    }
    return 0;
}
`

// scratchRoot creates a per-test scratch directory inside the package
// directory (never the system temp directory).
func scratchRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.MkdirTemp(".", ".scratch-")
	if err != nil {
		t.Fatal(err)
	}
	abs, err := filepath.Abs(dir)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.RemoveAll(abs) })
	return abs
}

func runCmd(dir string, name string, args ...string) (string, string, error) {
	cmd := exec.Command(name, args...)
	cmd.Dir = dir
	cmd.Env = append(os.Environ(), "TMPDIR="+dir, "TEMP="+dir, "TMP="+dir)
	var out, errb bytes.Buffer
	cmd.Stdout, cmd.Stderr = &out, &errb
	err := cmd.Run()
	return out.String(), errb.String(), err
}

// buildDriver compiles the emitted module together with the C driver using
// the strict flags of the reference suite and returns the executable path.
func buildDriver(t *testing.T, dir, source string) string {
	t.Helper()
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	for name, body := range map[string]string{"module.h": source, "driver.c": cDriver} {
		if err := os.WriteFile(filepath.Join(dir, name), []byte(body), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	args := append(append([]string{}, gccFlags...), "-o", "driver", "driver.c")
	_, stderr, err := runCmd(dir, "gcc", args...)
	if err != nil || strings.TrimSpace(stderr) != "" {
		t.Fatalf("gcc strict C99 build failed: %v\n%s", err, stderr)
	}
	return filepath.Join(dir, "driver")
}

type event struct {
	op    byte
	cid   int
	param int32
	valid bool
}

func (e event) line() string {
	v := 0
	if e.valid {
		v = 1
	}
	return fmt.Sprintf("%c %d %d %d\n", e.op, e.cid, e.param, v)
}

// goTranscript runs events on the Go Engine and renders the driver's output format.
func goTranscript(eng *Engine, events []event) string {
	var b strings.Builder
	for _, ev := range events {
		switch ev.op {
		case 's':
			r := eng.Step(ev.cid, ev.param, ev.valid)
			fault := 0
			if r.FaultPropagated {
				fault = 1
			}
			fmt.Fprintf(&b, "R %d,%d,%d,%d,%d,%d\n", r.StepsExecuted, r.Commits, r.Rejects, fault, r.LastState, r.Status)
		case 'i':
			eng.InvalidateConcept(ev.cid)
		default:
			eng.RevalidateConcept(ev.cid, ev.param)
		}
		b.WriteString(engineDigestLine(eng))
	}
	return b.String()
}

func runDriver(t *testing.T, exe string, events []event) string {
	t.Helper()
	var in strings.Builder
	for _, ev := range events {
		in.WriteString(ev.line())
	}
	cmd := exec.Command(exe)
	cmd.Stdin = strings.NewReader(in.String())
	var out bytes.Buffer
	cmd.Stdout = &out
	if err := cmd.Run(); err != nil {
		t.Fatalf("driver failed: %v", err)
	}
	return out.String()
}

func firstDifference(got, want string) string {
	g, w := strings.Split(got, "\n"), strings.Split(want, "\n")
	for i := 0; i < len(g) && i < len(w); i++ {
		if g[i] != w[i] {
			return fmt.Sprintf("line %d:\n C: %s\nGo: %s", i+1, g[i], w[i])
		}
	}
	return fmt.Sprintf("length differs: C %d lines, Go %d lines", len(g), len(w))
}

func goldenEvents(raw [][]any) []event {
	var out []event
	for _, ev := range raw {
		valid := true
		if b, ok := ev[3].(bool); ok {
			valid = b
		}
		out = append(out, event{op: ev[0].(string)[0], cid: int(ev[1].(float64)), param: int32(ev[2].(float64)), valid: valid})
	}
	return out
}

// randomEvents builds a seeded mix of valid, guard-rejected, invariant-blocked,
// fault and invalid-CID events for a table.
func randomEvents(descs []kpol.Descriptor, seed string, n int) []event {
	h := fnv.New64a()
	h.Write([]byte(seed))
	rng := rand.New(rand.NewSource(int64(h.Sum64())))
	var configured []int
	params := []int32{0, 1, -1, 2, 5, 50, 100, 120, 150, 180, 250, 5000, 2147483647, -2147483648}
	for _, d := range descs {
		if IsDescriptorConfigured(d) {
			configured = append(configured, d.CID)
			op := int32(d.OperandVal)
			params = append(params, op, op-1, op+1, int32(d.HazardLimit), int32(d.HazardLimit)+1,
				int32(int16(d.OperandVal&0xFFFF)), int32(int16(d.OperandVal>>16)))
		}
	}
	if len(configured) == 0 {
		configured = []int{0}
	}
	evs := make([]event, 0, n)
	for i := 0; i < n; i++ {
		cid := configured[rng.Intn(len(configured))]
		if rng.Float64() > 0.8 {
			cid = []int{rng.Intn(64), 64, 99, -1, 255}[rng.Intn(5)]
		}
		switch r := rng.Float64(); {
		case r < 0.82:
			evs = append(evs, event{'s', cid, params[rng.Intn(len(params))], rng.Float64() < 0.88})
		case r < 0.91:
			evs = append(evs, event{'i', cid, 0, true})
		default:
			evs = append(evs, event{'r', cid, []int32{0, 1, 2, 7, -1, 100, 2147483647}[rng.Intn(7)], true})
		}
	}
	return evs
}

// TestC99CompilesAndMatchesEngine compiles every emitted module with the
// strict C99 flags (zero warnings) and compares the C state machine with the
// Go Engine over golden and seeded event traces.
func TestC99CompilesAndMatchesEngine(t *testing.T) {
	requireBinary(t, "gcc")
	doc := loadGolden(t)
	root := scratchRoot(t)
	traces := map[string][][]any{}
	for _, e := range doc.EngineCases {
		traces[e.ID] = e.Events
	}
	compiled := 0
	for i := range doc.EmitCases {
		c := &doc.EmitCases[i]
		if !c.Emit.OK {
			continue
		}
		compiled++
		dir := filepath.Join(root, strconv.Itoa(i))
		t.Run(c.ID, func(t *testing.T) {
			t.Parallel()
			descs, err := c.normalize()
			if err != nil {
				t.Fatal(err)
			}
			src, err := renderOnly(descs, c.options())
			if err != nil {
				t.Fatal(err)
			}
			events := randomEvents(descs, c.ID, 150)
			if raw, ok := traces[c.ID]; ok {
				events = append(goldenEvents(raw), events...)
			}
			eng, err := NewEngine(descs, c.options())
			if err != nil {
				// Unverified emission of an unsafe table: only the strict build is checked.
				if !c.AllowUnverified {
					t.Fatal(err)
				}
				buildDriver(t, dir, src)
				return
			}
			want := goTranscript(eng, events)
			got := runDriver(t, buildDriver(t, dir, src), events)
			if got != want {
				t.Errorf("C99 module diverges from the Go engine: %s", firstDifference(got, want))
			}
		})
	}
	if compiled < 150 {
		t.Fatalf("only %d modules compiled", compiled)
	}
}

func bmsArtifacts(t *testing.T) (dir string, image []byte) {
	t.Helper()
	dir = filepath.Join("..", "..", "..", "validation", "kpol-cme", "c99-emitter-270")
	image, err := os.ReadFile(filepath.Join(dir, "bms_safety_cascade.bin"))
	if err != nil {
		t.Skipf("committed BMS artifacts are not available: %v", err)
	}
	return dir, image
}

var bmsOptions = Options{
	ModuleName:   "BmsSafetyCascade",
	ConceptNames: []string{"Cell_Delta_mV", "Module_Thermal_Guard", "Pack_Fault_Latch", "Contactor_Interlock"},
}

// randomTable builds a table of up to 12 concepts with arbitrary opcodes,
// guards and operands; subscribers mostly point forward so that many tables
// are acyclic, with occasional backward edges that NewEngine must reject.
func randomTable(rng *rand.Rand) []kpol.Descriptor {
	n := 1 + rng.Intn(12)
	operands := []uint32{0, 1, 2, 50, 100, 5000, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, 0x00640001, 0x7FFF8000, 0x80007FFF, rng.Uint32()}
	states := []uint32{0, 1, 2, 10, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, rng.Uint32()}
	var ds []kpol.Descriptor
	for cid := 0; cid < n; cid++ {
		d := kpol.Descriptor{
			CID: cid, CurrentState: states[rng.Intn(len(states))], OperandVal: operands[rng.Intn(len(operands))],
			PredOpcode:   uint8([]int{0, 1, 2, 3, 4, 5, 6, 6, 7, 0xFF}[rng.Intn(10)]),
			ActionOpcode: uint8([]int{0, 1, 2, 3, 4, 4, 5, 0xFF}[rng.Intn(8)]),
			GuardFlags:   []uint8{0x03, 0x13, 0x1B, 0x0B, 0x17, 0x1F, 0x01, 0x02, 0x10, 0x00, uint8(rng.Intn(256))}[rng.Intn(11)],
			HazardLimit:  []uint8{0, 0, 1, 50, 255}[rng.Intn(5)],
		}
		switch r := rng.Float64(); {
		case r < 0.55 && cid+1 < n:
			d.SubscriberCID = uint32(cid + 1 + rng.Intn(n-cid-1))
		case r < 0.62:
			d.SubscriberCID = uint32(rng.Intn(64))
		}
		ds = append(ds, d)
	}
	return ds
}

// TestC99MatchesEngineOnRandomTables is a differential fuzz of the emitted C99
// against the Go engine over seeded random acyclic tables.
func TestC99MatchesEngineOnRandomTables(t *testing.T) {
	requireBinary(t, "gcc")
	root := scratchRoot(t)
	rng := rand.New(rand.NewSource(0xC99))
	checked := 0
	for i := 0; checked < 120 && i < 1000; i++ {
		raw := randomTable(rng)
		descs, err := NormalizeDescriptors(raw, Options{})
		if err != nil {
			t.Fatal(err)
		}
		eng, err := NewEngine(descs, Options{})
		if err != nil {
			continue
		}
		checked++
		name := fmt.Sprintf("table%03d", checked)
		src, err := renderOnly(descs, Options{ModuleName: name})
		if err != nil {
			t.Fatal(err)
		}
		events := randomEvents(descs, name, 300)
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			want := goTranscript(eng, events)
			got := runDriver(t, buildDriver(t, filepath.Join(root, name), src), events)
			if got != want {
				t.Errorf("C99 diverges from the Go engine on %+v: %s", raw, firstDifference(got, want))
			}
		})
	}
	if checked < 120 {
		t.Fatalf("only %d acyclic random tables generated", checked)
	}
}

// TestBMSCommittedArtifacts: the emitted C99 and certificate must equal the
// committed reference artifacts byte for byte (the solver label aside).
func TestBMSCommittedArtifacts(t *testing.T) {
	requireBinary(t, "z3")
	dir, image := bmsArtifacts(t)
	want, err := os.ReadFile(filepath.Join(dir, "bms_safety_cascade_gen.c"))
	if err != nil {
		t.Fatal(err)
	}
	got, emitCert, err := EmitC99FromImageWithCertificate(image, bmsOptions)
	if err != nil {
		t.Fatal(err)
	}
	if got != string(want) {
		t.Fatalf("emitted C99 differs from committed bms_safety_cascade_gen.c")
	}
	if strings.Contains(got, "KM_MUTANT_") {
		t.Errorf("production C99 must not contain KM_MUTANT_ macros")
	}

	cert, err := ProveZ3FromImage(image, got, bmsOptions)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := cert.JSON()
	if err != nil {
		t.Fatal(err)
	}
	if emitRaw, _ := emitCert.JSON(); !bytes.Equal(emitRaw, raw) {
		t.Errorf("EmitC99WithCertificate and ProveZ3 disagree on the certificate")
	}
	committed, err := os.ReadFile(filepath.Join(dir, "bms_safety_z3_certificate.json"))
	if err != nil {
		t.Fatal(err)
	}
	solverLine := regexp.MustCompile(`(?m)^  "solver": ".*",$`)
	normalized := solverLine.ReplaceAllString(string(committed), `  "solver": `+strconv.Quote(cert.Solver)+`,`)
	if string(raw) != normalized {
		t.Errorf("certificate differs from the committed one:\n%s", raw)
	}
	if !cert.Passed || cert.Verdict != "VERIFIED" || cert.DescriptorTableSHA256 != sha256Hex(image) ||
		!reflectEqualInts(cert.TopologicalOrder, []int{0, 1, 2, 3}) {
		t.Errorf("unexpected BMS certificate: %+v", cert)
	}
}

func reflectEqualInts(a, b []int) bool {
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

// TestBMSMultiTUAndBenchmark ports the multi-translation-unit (F-08) and
// benchmark-harness checks of the reference suite to the emitted module.
func TestBMSMultiTUAndBenchmark(t *testing.T) {
	requireBinary(t, "gcc")
	dir, image := bmsArtifacts(t)
	descs, err := NormalizeImage(image, bmsOptions)
	if err != nil {
		t.Fatal(err)
	}
	src, err := renderOnly(descs, bmsOptions)
	if err != nil {
		t.Fatal(err)
	}
	root := scratchRoot(t)
	write := func(name, body string) {
		if err := os.WriteFile(filepath.Join(root, name), []byte(body), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	write("bms_safety_cascade_gen.c", src)
	write("tu1.c", `#include "bms_safety_cascade_gen.c"
int tu2_helper(void);
int main(void) {
    km_safety_ctx_t ctx;
    km_safety_init(&ctx);
    (void)km_safety_step_event(&ctx, 0u, 120, true);
    return (ctx.commits == 4u && tu2_helper() == 4) ? 0 : 1;
}
`)
	write("tu2.c", `#include "bms_safety_cascade_gen.c"
int tu2_helper(void);
int tu2_helper(void) {
    km_safety_ctx_t c2;
    km_safety_init(&c2);
    (void)km_safety_step_event(&c2, 0u, 120, true);
    return (int)c2.commits;
}
`)
	args := append(append([]string{}, gccFlags...), "tu1.c", "tu2.c", "-o", "multi_tu")
	if _, stderr, err := runCmd(root, "gcc", args...); err != nil {
		t.Fatalf("multi-TU build failed (duplicate symbols?): %v\n%s", err, stderr)
	}
	if _, _, err := runCmd(root, filepath.Join(root, "multi_tu")); err != nil {
		t.Fatalf("multi-TU program failed: %v", err)
	}

	bench, err := os.ReadFile(filepath.Join(dir, "bms_c99_hil_bench.c"))
	if err != nil {
		t.Skipf("benchmark harness not available: %v", err)
	}
	write("bench.c", string(bench))
	args = append(append([]string{}, gccFlags...), "bench.c", "-lm", "-o", "bench")
	if _, stderr, err := runCmd(root, "gcc", args...); err != nil {
		t.Fatalf("benchmark build failed: %v\n%s", err, stderr)
	}
	out, _, err := runCmd(root, filepath.Join(root, "bench"))
	if err != nil {
		t.Fatalf("benchmark failed: %v", err)
	}
	var parsed struct {
		Verdict       string `json:"verdict"`
		FinalState    []int  `json:"hw_trace_final_state"`
		Events        int    `json:"hw_trace_events"`
		Commits       int    `json:"hw_trace_commits"`
		Rejects       int    `json:"hw_trace_rejects"`
		FaultTraceHit int    `json:"fault_trace_fault_propagations"`
	}
	if err := json.Unmarshal([]byte(out), &parsed); err != nil {
		t.Fatalf("benchmark output: %v\n%s", err, out)
	}
	if parsed.Verdict != "PASS" || !reflectEqualInts(parsed.FinalState, []int{4, 4, 0, 0}) ||
		parsed.Events != 18 || parsed.Commits != 12 || parsed.Rejects != 6 || parsed.FaultTraceHit != 3 {
		t.Errorf("benchmark result differs from the reference: %+v", parsed)
	}
}

// TestBMSTraceMatchesEngine ports the reference equivalence trace (guard
// rejects, fault gate, validity mask, recovery, invariant block, bad CID).
func TestBMSTraceMatchesEngine(t *testing.T) {
	requireBinary(t, "gcc")
	_, image := bmsArtifacts(t)
	descs, err := NormalizeImage(image, bmsOptions)
	if err != nil {
		t.Fatal(err)
	}
	src, err := renderOnly(descs, bmsOptions)
	if err != nil {
		t.Fatal(err)
	}
	trace := bmsTrace()
	eng, err := NewEngineFromImage(image, bmsOptions)
	if err != nil {
		t.Fatal(err)
	}
	want := goTranscript(eng, trace)
	got := runDriver(t, buildDriver(t, filepath.Join(scratchRoot(t), "bms"), src), trace)
	if got != want {
		t.Fatalf("C99 diverges from the Go engine: %s", firstDifference(got, want))
	}
	if !reflectEqualInts([]int{int(eng.State[0]), int(eng.State[1]), int(eng.State[2]), int(eng.State[3])}, []int{4, 4, 0, 0}) ||
		eng.FaultPropagations != 5 {
		t.Errorf("unexpected final BMS state %v, faults %d", eng.State[:4], eng.FaultPropagations)
	}
}

func bmsTrace() []event {
	return []event{
		{'s', 0, 15, true}, {'s', 0, 5500, true}, {'s', 0, 0, false}, {'s', 0, 120, false}, {'s', 0, 120, true},
		{'i', 2, 0, true}, {'s', 0, 150, true}, {'r', 2, 1, true}, {'s', 0, 180, true}, {'s', 0, 250, true},
		{'s', 10, 100, true}, {'s', 10, 100, false}, {'s', 99, 100, true},
	}
}

func mutateOnce(t *testing.T, src, old, new string) string {
	t.Helper()
	if n := strings.Count(src, old); n != 1 {
		t.Fatalf("expected exactly one occurrence of %q, found %d", old, n)
	}
	return strings.Replace(src, old, new, 1)
}

// TestRuntimeNegativeControls (AGENTS.md §4.1 mutants M1..M3): each mutated
// module must compile and then visibly diverge from the Go engine, while the
// unmutated module matches on the same events.
func TestRuntimeNegativeControls(t *testing.T) {
	requireBinary(t, "gcc")
	_, image := bmsArtifacts(t)
	descs, err := NormalizeImage(image, bmsOptions)
	if err != nil {
		t.Fatal(err)
	}
	src, err := renderOnly(descs, bmsOptions)
	if err != nil {
		t.Fatal(err)
	}
	root := scratchRoot(t)
	mutants := []struct {
		name   string
		mutant string
		events []event
	}{
		{"M1_bypass_invariant", mutateOnce(t, src,
			"invariant_true   = (!arith_overflow) && ((cand_u32 & 0x80000000u) == 0u);",
			"invariant_true   = true; (void)arith_overflow;"),
			[]event{{'s', 0, 120, true}, {'s', 0, 180, true}, {'s', 0, 250, true}}},
		{"M2_mask_invalid_sensor", mutateOnce(t, src,
			"if ((!ev_param_valid) || (!concept_valid)) {",
			"if (false && ((!ev_param_valid) || (!concept_valid))) {"),
			[]event{{'s', 0, 0, false}}},
		{"M2_mask_invalid_concept", mutateOnce(t, src,
			"if ((!ev_param_valid) || (!concept_valid)) {",
			"if (false && ((!ev_param_valid) || (!concept_valid))) {"),
			[]event{{'i', 2, 0, true}, {'s', 0, 120, true}}},
		{"M3_wrong_topo_order", mutateOnce(t, src,
			"uint8_t cid = KM_SAFETY_TOPO_ORDER[topo_idx];",
			"uint8_t cid = KM_SAFETY_TOPO_ORDER[(KM_SAFETY_NUM_ACTIVE_TOPO - 1u) - topo_idx];"),
			[]event{{'s', 0, 120, true}}},
	}
	for i, m := range mutants {
		eng, err := NewEngineFromImage(image, bmsOptions)
		if err != nil {
			t.Fatal(err)
		}
		want := goTranscript(eng, m.events)

		eng2, _ := NewEngineFromImage(image, bmsOptions)
		clean := runDriver(t, buildDriver(t, filepath.Join(root, fmt.Sprintf("clean%d", i)), src), m.events)
		if clean != goTranscript(eng2, m.events) {
			t.Errorf("%s: unmutated module should match the engine", m.name)
		}
		got := runDriver(t, buildDriver(t, filepath.Join(root, fmt.Sprintf("mut%d", i)), m.mutant), m.events)
		if got == want {
			t.Errorf("%s: mutant is indistinguishable from the engine on %v", m.name, m.events)
		}
	}
}
