package c99

import (
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

// bmsDescriptors is the 4-stage BMS safety cascade of the reference suite
// (Cell_Delta_mV -> Module_Thermal_Guard -> Pack_Fault_Latch -> Contactor_Interlock).
func bmsDescriptors() []kpol.Descriptor {
	return []kpol.Descriptor{
		{CID: 0, OperandVal: 327680050, PredOpcode: kpol.PredRANGE, GuardFlags: 0x13, ActionOpcode: kpol.ActInc, SubscriberCID: 1},
		{CID: 1, OperandVal: 1, PredOpcode: kpol.PredLT, GuardFlags: 0x1B, ActionOpcode: kpol.ActInc, SubscriberCID: 2},
		{CID: 2, CurrentState: 2, OperandVal: 1, PredOpcode: kpol.PredLT, GuardFlags: 0x1B, ActionOpcode: kpol.ActDec, SubscriberCID: 3},
		{CID: 3, CurrentState: 10, OperandVal: 2, PredOpcode: kpol.PredEQ, GuardFlags: 0x0B, ActionOpcode: kpol.ActAssign},
	}
}

func withDescriptor(base []kpol.Descriptor, cid int, edit func(*kpol.Descriptor)) []kpol.Descriptor {
	out := append([]kpol.Descriptor(nil), base...)
	edit(&out[cid])
	return out
}

func failedChecks(c *Certificate) []string {
	var failed []string
	for _, ch := range c.Checks {
		if !ch.Passed {
			failed = append(failed, ch.Name)
		}
	}
	return failed
}

func asKpolError(t *testing.T, err error) *kpol.Error {
	t.Helper()
	var kerr *kpol.Error
	if !errors.As(err, &kerr) {
		t.Fatalf("error %v is not a *kpol.Error", err)
	}
	return kerr
}

func TestTopologicalOrder(t *testing.T) {
	// Kahn with a smallest-first ready set: 5 -> 1 and 3 -> 1 yields 3, 5, 1, not DFS order.
	order, err := ComputeTopologicalOrder([]int{1, 3, 5}, []Edge{{Src: 5, Dst: 1}, {Src: 3, Dst: 1}})
	if err != nil || !reflect.DeepEqual(order, []int{3, 5, 1}) {
		t.Fatalf("order %v, err %v", order, err)
	}
	order, err = ComputeTopologicalOrder([]int{0, 1, 2}, []Edge{{Src: 2, Dst: 0}})
	if err != nil || !reflect.DeepEqual(order, []int{1, 2, 0}) {
		t.Fatalf("order %v, err %v", order, err)
	}

	cases := []struct {
		name  string
		edges []Edge
		want  string
	}{
		{"range", []Edge{{Src: 3, Dst: 64}}, "C99-DAG-RANGE: concept C3 has out-of-range subscriber_cid=64 (expected 0..63)"},
		{"self loop", []Edge{{Src: 2, Dst: 2}}, "C99-DAG-CYCLE: self-subscription loop detected on concept C2 -> C2"},
		{"cycle", []Edge{{Src: 0, Dst: 1}, {Src: 1, Dst: 2}, {Src: 2, Dst: 1}}, "C99-DAG-CYCLE: cyclic subscription graph detected involving CIDs [1, 2]"},
		{"first bad edge wins", []Edge{{Src: 4, Dst: 4}, {Src: 3, Dst: 99}}, "C99-DAG-CYCLE: self-subscription loop detected on concept C4 -> C4"},
	}
	for _, c := range cases {
		_, err := ComputeTopologicalOrder([]int{0, 1, 2, 3, 4}, c.edges)
		if err == nil || err.Error() != c.want {
			t.Errorf("%s: error %v, want %q", c.name, err, c.want)
		}
	}
	if _, err := ComputeTopologicalOrder([]int{64}, nil); asKpolError(t, err).Code != "C99-SHAPE" {
		t.Errorf("out-of-range active CID must be a shape error")
	}
}

func TestExtractActiveCIDsAndEdges(t *testing.T) {
	descs, err := NormalizeDescriptors(withDescriptor(bmsDescriptors(), 3, func(d *kpol.Descriptor) { d.SubscriberCID = 0 }), Options{})
	if err != nil {
		t.Fatal(err)
	}
	active, edges := ExtractActiveCIDsAndEdges(descs)
	if !reflect.DeepEqual(active, []int{0, 1, 2, 3}) || !reflect.DeepEqual(edges, []Edge{{0, 1}, {1, 2}, {2, 3}}) {
		t.Errorf("active %v edges %v", active, edges)
	}
	empty, _ := NormalizeDescriptors(nil, Options{})
	if a, e := ExtractActiveCIDsAndEdges(empty); !reflect.DeepEqual(a, []int{0}) || len(e) != 0 {
		t.Errorf("empty table: active %v edges %v", a, e)
	}
	// W3 == 0 with the subscriber-enable flag is an edge to C0.
	flagged, _ := NormalizeDescriptors([]kpol.Descriptor{{CID: 5, GuardFlags: kpol.GuardSubscriberEn}}, Options{})
	if _, e := ExtractActiveCIDsAndEdges(flagged); !reflect.DeepEqual(e, []Edge{{5, 0}}) {
		t.Errorf("flag-only edge missing: %v", e)
	}
}

func TestNormalizeDescriptorsShapeAndNames(t *testing.T) {
	in := []kpol.Descriptor{{CID: 1, Name: "own"}, {CID: 1}}
	if _, err := NormalizeDescriptors(in, Options{}); err == nil || err.Error() != "C99-SHAPE: descriptor CIDs must be unique in 0..63" {
		t.Errorf("duplicate CID error: %v", err)
	}
	if _, err := NormalizeDescriptors(make([]kpol.Descriptor, 65), Options{}); err == nil || err.Error() != "C99-SHAPE: expected at most 64 descriptors, got 65" {
		t.Errorf("too many descriptors error: %v", err)
	}
	if _, err := NormalizeDescriptors([]kpol.Descriptor{{CID: -1}}, Options{}); asKpolError(t, err).Code != "C99-SHAPE" {
		t.Errorf("negative CID must be rejected")
	}

	src := []kpol.Descriptor{{CID: 2, Name: "3rd stage!", GuardFlags: 3}, {CID: 0, Name: ""}}
	out, err := NormalizeDescriptors(src, Options{ConceptNames: []string{"", "x y"}, ConceptNameMap: map[int]string{2: "  9 Lives "}})
	if err != nil {
		t.Fatal(err)
	}
	if len(out) != 64 || out[0].Name != "Concept_0" || out[1].Name != "x_y" || out[2].Name != "_9_Lives" || out[63].Name != "Concept_63" {
		t.Errorf("names: %q %q %q %q", out[0].Name, out[1].Name, out[2].Name, out[63].Name)
	}
	if src[0].Name != "3rd stage!" {
		t.Errorf("input was modified")
	}
	if sanitizeIdent("   ", "FB") != "FB" || sanitizeIdent("é1", "FB") != "_1" {
		t.Errorf("sanitizeIdent fallbacks wrong")
	}
}

func TestParsePyInt(t *testing.T) {
	good := map[string]string{"0": "0", "00": "0", "10": "10", "0x1F": "31", "0X1f": "31", "-5": "-5", "-0": "0", "99999999999999999999": "99999999999999999999"}
	for in, want := range good {
		v, err := parsePyInt(in)
		if err != nil || v.String() != want {
			t.Errorf("parsePyInt(%q) = %v, %v; want %s", in, v, err, want)
		}
	}
	for _, in := range []string{"01", "-012", "0x", "08", ""} {
		_, err := parsePyInt(in)
		if err == nil || asKpolError(t, err).Code != "C99-PARSE" || !strings.Contains(err.Error(), "invalid literal for int() with base 0: '"+in+"'") {
			t.Errorf("parsePyInt(%q) error %v", in, err)
		}
	}
}

func TestParsePristineModule(t *testing.T) {
	descs, _ := NormalizeDescriptors(bmsDescriptors(), Options{})
	src, err := renderOnly(descs, Options{})
	if err != nil {
		t.Fatal(err)
	}
	p, err := ParseEmittedC99Source(src)
	if err != nil {
		t.Fatal(err)
	}
	ops := []string{p.PredEqOp, p.PredNeqOp, p.PredGtOp, p.PredLtOp, p.RangeLoOp, p.RangeHiOp, p.ActIncOp, p.ActDecOp, p.ActAddOp, p.ActSubOp, p.SubOvfXorOp}
	if !reflect.DeepEqual(ops, []string{"==", "!=", ">", "<", ">=", "<=", "+", "-", "+", "-", "!="}) {
		t.Errorf("operators %v", ops)
	}
	if !reflect.DeepEqual(p.TopoOrder, []int{0, 1, 2, 3}) || p.TopoLoopReversed || !p.HasFaultGate || !p.RangeSext ||
		!p.InvariantChecksOverflow || !p.InvariantChecksNonneg || !p.CommitChecksInvariant || !p.HasSelfSuppress {
		t.Errorf("pristine module parsed wrongly: %+v", p)
	}
	for cid := range descs {
		if p.Descriptors[cid].Pack() != descs[cid].Pack() {
			t.Fatalf("C%d does not round-trip through the emitted table", cid)
		}
	}
}

func TestPythonJSONFormatting(t *testing.T) {
	got := marshalPythonJSON(jObj{
		{"s", "q\"\\\n\r\t\b\f\x01é☃\u2028"},
		{"empty_list", []int{}},
		{"empty_obj", jObj{}},
		{"nested", []any{[]any{1, uint32(4294967295)}, true, nil}},
		{"o", jObj{{"k", "v"}}},
	})
	want := "{\n  \"s\": \"q\\\"\\\\\\n\\r\\t\\b\\f\\u0001é☃\u2028\",\n  \"empty_list\": [],\n  \"empty_obj\": {},\n" +
		"  \"nested\": [\n    [\n      1,\n      4294967295\n    ],\n    true,\n    null\n  ],\n  \"o\": {\n    \"k\": \"v\"\n  }\n}"
	if got != want {
		t.Errorf("got:\n%s\nwant:\n%s", got, want)
	}
}

func TestDefaultModuleName(t *testing.T) {
	requireBinary(t, "z3")
	src, err := EmitC99(bmsDescriptors(), Options{})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(src, "#ifndef KM_SAFETY_AUTOGEN_KM_SAFETY_H") || !strings.Contains(src, " * Module: km_safety\n") {
		t.Errorf("default module name not applied")
	}
	cert, err := ProveZ3(bmsDescriptors(), src, Options{})
	if err != nil || cert.ModuleName != "km_safety" || !cert.Passed {
		t.Errorf("certificate %+v, err %v", cert, err)
	}
}

func TestEngineBMSTrace(t *testing.T) {
	eng, err := NewEngine(bmsDescriptors(), Options{})
	if err != nil {
		t.Fatal(err)
	}
	type step struct {
		cid   int
		param int32
		valid bool
		want  StepResult
	}
	steps := []step{
		{0, 15, true, StepResult{1, 0, 1, false, 0, StatusRejectedGuard}},   // below the 50 mV window
		{0, 5500, true, StepResult{1, 0, 1, false, 0, StatusRejectedGuard}}, // above the 5000 mV window
		{0, 0, false, StepResult{1, 0, 1, true, 0, StatusRejectedFault}},    // CRC fault on 0 mV must not be masked as 0
		{0, 120, false, StepResult{1, 0, 1, true, 0, StatusRejectedFault}},
		{0, 120, true, StepResult{4, 4, 0, false, 1, StatusCommitted}},
	}
	for i, s := range steps {
		if got := eng.Step(s.cid, s.param, s.valid); got != s.want {
			t.Errorf("step %d: got %+v, want %+v", i, got, s.want)
		}
	}
	if !reflect.DeepEqual(eng.State[:4], []int32{1, 1, 1, 1}) {
		t.Fatalf("state %v", eng.State[:4])
	}
	eng.InvalidateConcept(2)
	if eng.ValidMask != 0xFFFFFFFFFFFFFFFB {
		t.Errorf("valid mask %#x", eng.ValidMask)
	}
	if got, want := eng.Step(0, 150, true), (StepResult{3, 2, 1, true, 2, StatusCommitted}); got != want {
		t.Errorf("mid-cascade fault: got %+v, want %+v", got, want)
	}
	eng.RevalidateConcept(2, -1)
	if eng.ValidMask&(1<<2) != 0 {
		t.Errorf("negative recovered state must keep the concept invalid")
	}
	eng.RevalidateConcept(2, 1)
	if got, want := eng.Step(0, 180, true), (StepResult{4, 4, 0, false, 0, StatusCommitted}); got != want {
		t.Errorf("recovered cascade: got %+v, want %+v", got, want)
	}
	if got, want := eng.Step(0, 250, true), (StepResult{3, 2, 1, false, 4, StatusCommitted}); got != want { // 0 - 1 violates state >= 0
		t.Errorf("invariant block: got %+v, want %+v", got, want)
	}
	if got, want := eng.Step(10, 100, true), (StepResult{1, 0, 1, false, 4, StatusRejectedGuard}); got != want {
		t.Errorf("inactive slot: got %+v, want %+v", got, want)
	}
	if got, want := eng.Step(10, 100, false), (StepResult{1, 0, 1, true, 4, StatusRejectedFault}); got != want {
		t.Errorf("inactive slot, invalid param: got %+v, want %+v", got, want)
	}
	for _, cid := range []int{99, -1, 64} {
		if got, want := eng.Step(cid, 100, true), (StepResult{1, 0, 1, true, 4, StatusRejectedBadCID}); got != want {
			t.Errorf("bad CID %d: got %+v, want %+v", cid, got, want)
		}
	}
	if !reflect.DeepEqual(eng.State[:4], []int32{4, 4, 0, 0}) || eng.FaultPropagations != 7 || eng.Commits != 12 {
		t.Errorf("final state %v faults %d commits %d", eng.State[:4], eng.FaultPropagations, eng.Commits)
	}
	eng.InvalidateConcept(200) // out-of-range CIDs are ignored
	eng.RevalidateConcept(-3, 5)
}

func TestEngineRejectsCyclicTables(t *testing.T) {
	cyclic := withDescriptor(bmsDescriptors(), 1, func(d *kpol.Descriptor) { d.SubscriberCID = 0 })
	if _, err := NewEngine(cyclic, Options{}); err == nil || err.Error() != "C99-DAG-CYCLE: cyclic subscription graph detected involving CIDs [0, 1]" {
		t.Errorf("cyclic table: %v", err)
	}
	oor := withDescriptor(bmsDescriptors(), 3, func(d *kpol.Descriptor) { d.SubscriberCID = 64 })
	if _, err := NewEngine(oor, Options{}); err == nil || !strings.HasPrefix(err.Error(), "C99-DAG-RANGE") {
		t.Errorf("out-of-range subscriber: %v", err)
	}
}

// TestReferenceNegativeControls mirrors the M1..M4 controls of the reference
// suite: each seeded defect must be rejected by exactly the expected checks.
func TestReferenceNegativeControls(t *testing.T) {
	requireBinary(t, "z3")
	opts := Options{ModuleName: "BmsSafetyCascade"}
	descs, _ := NormalizeDescriptors(bmsDescriptors(), opts)
	base, err := renderOnly(descs, opts)
	if err != nil {
		t.Fatal(err)
	}
	if cert, err := ProveZ3(bmsDescriptors(), base, opts); err != nil || !cert.Passed || len(failedChecks(cert)) != 0 {
		t.Fatalf("positive control failed: %+v %v", cert, err)
	}

	mutate := func(old, new string) string {
		if strings.Count(base, old) != 1 {
			t.Fatalf("anchor %q not unique", old)
		}
		return strings.Replace(base, old, new, 1)
	}
	cases := []struct {
		name   string
		source string
		failed []string
	}{
		{"M1 bypass invariant", mutate("invariant_true   = (!arith_overflow) && ((cand_u32 & 0x80000000u) == 0u);", "invariant_true   = true; (void)arith_overflow;"), []string{CheckP2, CheckP4}},
		{"M2 mask invalid sensor", mutate("if ((!ev_param_valid) || (!concept_valid)) {", "if (false && ((!ev_param_valid) || (!concept_valid))) {"), []string{CheckP3}},
		{"M3 wrong topological order", mutate("uint8_t cid = KM_SAFETY_TOPO_ORDER[topo_idx];", "uint8_t cid = KM_SAFETY_TOPO_ORDER[(KM_SAFETY_NUM_ACTIVE_TOPO - 1u) - topo_idx];"), []string{CheckP1}},
		{"M4 PRED_GT >=", mutate("case KM_CME_PRED_GT:\n            pred_raw = (ev_param > op_i32);", "case KM_CME_PRED_GT:\n            pred_raw = (ev_param >= op_i32);"), []string{CheckP4}},
		{"M4 PRED_RANGE zero-extension", mutate("int32_t lo_i32 = km_u16_to_i32_sext((uint16_t)(d->operand & 0xFFFFu));", "int32_t lo_i32 = (int32_t)(uint16_t)(d->operand & 0xFFFFu);"), []string{CheckP4}},
		{"M4 ACT_SUB overflow mask", mutate("arith_overflow = (((cur_u32 ^ d->operand) & 0x80000000u) != 0u) &&", "arith_overflow = (((cur_u32 ^ d->operand) & 0x80000000u) == 0u) &&"), []string{CheckP4}},
		{"table row tampered", mutate("0x13u, 0x00u, 0x01u, 1u }", "0x13u, 0x00u, 0x01u, 2u }"), []string{CheckP4}},
	}
	for _, c := range cases {
		cert, err := ProveZ3(bmsDescriptors(), c.source, opts)
		if err != nil {
			t.Errorf("%s: %v", c.name, err)
			continue
		}
		if cert.Passed || cert.Verdict != "REJECTED" || !reflect.DeepEqual(failedChecks(cert), c.failed) {
			t.Errorf("%s: passed=%v failed=%v, want %v (failures %q)", c.name, cert.Passed, failedChecks(cert), c.failed, cert.Failures)
		}
		if len(cert.Failures) != len(c.failed) {
			t.Errorf("%s: %d failure messages for %d failed checks", c.name, len(cert.Failures), len(c.failed))
		}
	}

	// Descriptor-level defects: cycle, self-loop, disabled invariant, bad opcode, negative init.
	unsafe := []struct {
		name   string
		descs  []kpol.Descriptor
		failed string
		emit   string
	}{
		{"cycle", withDescriptor(bmsDescriptors(), 1, func(d *kpol.Descriptor) { d.SubscriberCID = 0 }), CheckP1, "C99-Z3-REJECTED: C99-DAG-CYCLE: cyclic subscription graph detected involving CIDs [0, 1]"},
		{"self loop", withDescriptor(bmsDescriptors(), 0, func(d *kpol.Descriptor) { d.SubscriberCID = 0 }), CheckP1, "C99-Z3-REJECTED: C99-DAG-CYCLE: self-subscription loop detected on concept C0 -> C0"},
		{"out of range", withDescriptor(bmsDescriptors(), 3, func(d *kpol.Descriptor) { d.SubscriberCID = 64 }), CheckP1, "C99-Z3-REJECTED: C99-DAG-RANGE: concept C3 has out-of-range subscriber_cid=64 (expected 0..63)"},
		{"invariant disabled", withDescriptor(bmsDescriptors(), 2, func(d *kpol.Descriptor) { d.GuardFlags &^= kpol.GuardInvariantEn }), CheckP2, "C99-Z3-REJECTED: P2_invariant_preservation_all_bv32: C2 (Concept_2) has CME_GUARD_INVARIANT_EN disabled (guard_flags=0x19)"},
		{"negative initial state", withDescriptor(bmsDescriptors(), 1, func(d *kpol.Descriptor) { d.CurrentState = 0xFFFFFFFF }), CheckP2, ""},
		{"unsupported action", withDescriptor(bmsDescriptors(), 1, func(d *kpol.Descriptor) { d.ActionOpcode = 9 }), CheckP2, ""},
	}
	for _, u := range unsafe {
		cert, err := ProveZ3(u.descs, "", Options{})
		if err != nil {
			t.Errorf("%s: %v", u.name, err)
			continue
		}
		if cert.Passed || cert.Check(u.failed).Passed {
			t.Errorf("%s: %s should fail (failed: %v)", u.name, u.failed, failedChecks(cert))
		}
		_, err = EmitC99(u.descs, Options{})
		if err == nil || asKpolError(t, err).Code != "C99-Z3-REJECTED" || (u.emit != "" && err.Error() != u.emit) {
			t.Errorf("%s: EmitC99 error %v, want %q", u.name, err, u.emit)
		}
	}
}

func TestOptionsCertificateAndUnverified(t *testing.T) {
	requireBinary(t, "z3")
	cyclic := withDescriptor(bmsDescriptors(), 1, func(d *kpol.Descriptor) { d.SubscriberCID = 0 })
	src, err := EmitC99(cyclic, Options{AllowUnverified: true})
	if err != nil {
		t.Fatalf("AllowUnverified must emit the unsafe module: %v", err)
	}
	if !strings.Contains(src, "Topological Order: [0, 1, 2, 3]") {
		t.Errorf("fallback schedule is the active CID order")
	}

	failing := &Certificate{Passed: false, Failures: []string{"P2_x: boom", "P4_y: bang"}}
	if _, err := EmitC99(bmsDescriptors(), Options{Certificate: failing}); err == nil || err.Error() != "C99-Z3-REJECTED: P2_x: boom; P4_y: bang" {
		t.Errorf("failed precomputed certificate: %v", err)
	}
	if _, err := EmitC99(bmsDescriptors(), Options{Certificate: &Certificate{}}); err == nil || err.Error() != "C99-Z3-REJECTED: unknown Z3 failure" {
		t.Errorf("certificate without failures: %v", err)
	}
	if _, err := EmitC99(bmsDescriptors(), Options{Certificate: &Certificate{Passed: true}}); err != nil {
		t.Errorf("verified precomputed certificate: %v", err)
	}
}

func TestFailClosedWithoutZ3(t *testing.T) {
	missing := Options{Z3Path: filepath.Join(scratchRoot(t), "no-such-z3")}
	if src, err := EmitC99(bmsDescriptors(), missing); !errors.Is(err, ErrZ3Required) || src != "" {
		t.Errorf("EmitC99 without z3: %q, %v", src, err)
	}
	if cert, err := ProveZ3(bmsDescriptors(), "", missing); !errors.Is(err, ErrZ3Required) || cert != nil {
		t.Errorf("ProveZ3 without z3: %v, %v", cert, err)
	}
	if _, err := EmitC99FromImage(kpol.PackImage(bmsDescriptors()), missing); !errors.Is(err, ErrZ3Required) {
		t.Errorf("EmitC99FromImage without z3: %v", err)
	}
	if !strings.HasPrefix(ErrZ3Required.Error(), "Z3 solver is required") {
		t.Errorf("message %q", ErrZ3Required)
	}

	t.Setenv("PATH", scratchRoot(t))
	if _, err := EmitC99(bmsDescriptors(), Options{}); !errors.Is(err, ErrZ3Required) {
		t.Errorf("empty PATH: %v", err)
	}
	// Even a table that would be rejected for its topology is judged only after the shape checks,
	// but shape errors take precedence over the missing solver exactly as in the reference.
	if _, err := ProveZ3(make([]kpol.Descriptor, 65), "", Options{}); asKpolError(t, err).Code != "C99-SHAPE" {
		t.Errorf("shape error must precede solver lookup: %v", err)
	}
}

func fakeZ3(t *testing.T, dir, name, body string) string {
	t.Helper()
	path := filepath.Join(dir, name)
	script := "#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo 'Z3 version fake'; exit 0; fi\n" + body
	if err := os.WriteFile(path, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}
	return path
}

// TestSolverMisbehaviour: anything but a clean "unsat" must never certify.
func TestSolverMisbehaviour(t *testing.T) {
	requireBinary(t, "sh")
	dir := scratchRoot(t)

	unknown := Options{Z3Path: fakeZ3(t, dir, "unknown", "cat >/dev/null\necho unknown\n")}
	cert, err := ProveZ3(bmsDescriptors(), "", unknown)
	if err != nil || cert.Passed || len(failedChecks(cert)) != 4 || cert.Solver != "z3-cli (Z3 version fake)" {
		t.Errorf("unknown verdicts: %+v, %v", cert, err)
	}
	if _, err := EmitC99(bmsDescriptors(), unknown); err == nil || asKpolError(t, err).Code != "C99-Z3-REJECTED" {
		t.Errorf("EmitC99 with unknown verdicts: %v", err)
	}

	always := Options{Z3Path: fakeZ3(t, dir, "sat", "cat >/dev/null\necho sat\n")}
	cert, err = ProveZ3(bmsDescriptors(), "", always)
	if err != nil || cert.Passed || !cert.Check(CheckP1).Passed || cert.Check(CheckP2).Passed || cert.Check(CheckP3).Passed || cert.Check(CheckP4).Passed {
		t.Errorf("sat verdicts: %+v, %v", cert, err)
	}
	if got := cert.Check(CheckP3).Error; !strings.HasSuffix(got, "(Z3 witness: sat)") {
		t.Errorf("witness text %q", got)
	}

	broken := Options{Z3Path: fakeZ3(t, dir, "broken", "cat >/dev/null\necho '(error \"line 1: bad\")'\nexit 1\n")}
	if cert, err := ProveZ3(bmsDescriptors(), "", broken); err == nil || cert != nil || !strings.Contains(err.Error(), "z3 CLI failed (rc=1): (error \"line 1: bad\")") {
		t.Errorf("failing z3: %v, %v", cert, err)
	}

	slow := Options{Z3Path: fakeZ3(t, dir, "slow", "exec sleep 5\n"), Z3Timeout: 200 * time.Millisecond}
	start := time.Now()
	if _, err := ProveZ3(bmsDescriptors(), "", slow); err == nil || asKpolError(t, err).Code != "C99-Z3-TIMEOUT" {
		t.Errorf("timeout: %v", err)
	}
	if time.Since(start) > 3*time.Second {
		t.Errorf("timeout was not enforced promptly")
	}

	noVersion := Options{Z3Path: filepath.Join(dir, "noversion")}
	if err := os.WriteFile(noVersion.Z3Path, []byte("#!/bin/sh\nexit 3\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	if _, err := ProveZ3(bmsDescriptors(), "", noVersion); err == nil || !strings.Contains(err.Error(), "z3 --version failed (rc=3)") {
		t.Errorf("version failure: %v", err)
	}
}

func TestConcurrentEmission(t *testing.T) {
	requireBinary(t, "z3")
	var wg sync.WaitGroup
	outs := make([]string, 6)
	errs := make([]error, len(outs))
	for i := range outs {
		wg.Add(1)
		go func() {
			defer wg.Done()
			outs[i], errs[i] = EmitC99(bmsDescriptors(), Options{ModuleName: "Concurrent"})
		}()
	}
	wg.Wait()
	for i := range outs {
		if errs[i] != nil || outs[i] != outs[0] {
			t.Fatalf("emission %d differs or failed: %v", i, errs[i])
		}
	}
}
