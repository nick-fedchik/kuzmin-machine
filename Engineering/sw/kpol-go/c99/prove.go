package c99

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

// Names of the four Z3 checks, in certificate order.
const (
	CheckP1 = "P1_dag_lyapunov_acyclicity"
	CheckP2 = "P2_invariant_preservation_all_bv32"
	CheckP3 = "P3_no_commit_on_invalid_param_or_state"
	CheckP4 = "P4_c99_rtl_bitvec32_miter_equivalence"
)

// Certificate constants shared with the reference generator.
const (
	CertSchemaVersion = "1.0.0"
	// GeneratorName is kept identical to the reference so that certificates
	// and emitted headers of both implementations are interchangeable.
	GeneratorName = "Engineering/sw/kpol-ref/c99_emitter.py"
)

// RankEntry is one Lyapunov rank assignment (CID -> position in the schedule).
type RankEntry struct {
	CID  int
	Rank int
}

// Check is the outcome of one of P1..P4. Only the fields relevant to the
// check and its verdict are serialised (see JSON).
type Check struct {
	Name   string
	Status string
	Passed bool

	EdgesChecked           int         // P1
	LyapunovRank           []RankEntry // P1, when passed
	TopologicalOrder       []int       // P1, when passed
	ActiveConceptsVerified int         // P2, when passed
	QuantifiedDomain       string      // P2/P4, when passed
	Property               string      // P3, when passed
	Error                  string      // when failed
}

func (c Check) toJSON() jObj {
	o := jObj{{"status", c.Status}, {"passed", c.Passed}}
	switch c.Name {
	case CheckP1:
		if c.Status != "FAILED" {
			o = append(o, jKV{"edges_checked", c.EdgesChecked})
		}
		if c.Passed {
			o = append(o, jKV{"lyapunov_rank", rankJSON(c.LyapunovRank)}, jKV{"topological_order", c.TopologicalOrder})
		}
	case CheckP2:
		if c.Passed {
			o = append(o, jKV{"active_concepts_verified", c.ActiveConceptsVerified})
		}
	}
	if c.Passed {
		if c.QuantifiedDomain != "" {
			o = append(o, jKV{"quantified_domain", c.QuantifiedDomain})
		}
		if c.Property != "" {
			o = append(o, jKV{"property", c.Property})
		}
	} else {
		o = append(o, jKV{"error", c.Error})
	}
	return o
}

func rankJSON(r []RankEntry) jObj {
	o := make(jObj, len(r))
	for i, e := range r {
		o[i] = jKV{fmt.Sprint(e.CID), e.Rank}
	}
	return o
}

// Certificate is the Z3 safety certificate (the dict returned by
// prove_c99_descriptor_safety_z3).
type Certificate struct {
	SchemaVersion         string
	ModuleName            string
	Generator             string
	Solver                string
	Verdict               string
	Passed                bool
	DescriptorTableSHA256 string
	C99SourceSHA256       string
	ActiveConceptsCount   int
	ActiveCIDs            []int
	CascadeEdges          []Edge
	TopologicalOrder      []int
	LyapunovRank          []RankEntry
	WCETMaxCascadeSteps   int
	Checks                []Check
	Failures              []string
}

// Check returns the named check (CheckP1..CheckP4) or nil.
func (c *Certificate) Check(name string) *Check {
	for i := range c.Checks {
		if c.Checks[i].Name == name {
			return &c.Checks[i]
		}
	}
	return nil
}

// JSON serialises the certificate exactly as the reference CLI writes it:
// json.dumps(cert, indent=2, ensure_ascii=False) followed by a newline.
func (c *Certificate) JSON() ([]byte, error) {
	edges := make([]any, len(c.CascadeEdges))
	for i, e := range c.CascadeEdges {
		edges[i] = []any{e.Src, e.Dst}
	}
	checks := make(jObj, len(c.Checks))
	for i, ch := range c.Checks {
		checks[i] = jKV{ch.Name, ch.toJSON()}
	}
	root := jObj{
		{"schema_version", c.SchemaVersion},
		{"module_name", c.ModuleName},
		{"generator", c.Generator},
		{"solver", c.Solver},
		{"verdict", c.Verdict},
		{"passed", c.Passed},
		{"descriptor_table_sha256", c.DescriptorTableSHA256},
		{"c99_source_sha256", c.C99SourceSHA256},
		{"active_concepts_count", c.ActiveConceptsCount},
		{"active_cids", c.ActiveCIDs},
		{"cascade_edges", edges},
		{"topological_order", c.TopologicalOrder},
		{"lyapunov_rank", rankJSON(c.LyapunovRank)},
		{"wcet_max_cascade_steps", c.WCETMaxCascadeSteps},
		{"checks", checks},
		{"failures", c.Failures},
	}
	return []byte(marshalPythonJSON(root) + "\n"), nil
}

func sha256Hex(b []byte) string {
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:])
}

func tableSHA256(descs []kpol.Descriptor) string {
	packed := make([]byte, 0, len(descs)*kpol.SlotSize)
	for _, d := range descs {
		p := d.Pack()
		packed = append(packed, p[:]...)
	}
	return sha256Hex(packed)
}

// ProveZ3 formally verifies the descriptor table and the (parsed) C99 source
// with Z3, mirroring prove_c99_descriptor_safety_z3. An empty c99Source means
// "render the reference source for these descriptors". Failed properties are
// reported in the returned certificate (Passed == false); errors are limited
// to malformed input (C99-SHAPE, C99-PARSE) and an unusable solver
// (ErrZ3Required and Z3 runtime failures).
func ProveZ3(descriptors []kpol.Descriptor, c99Source string, opts Options) (*Certificate, error) {
	descs, err := NormalizeDescriptors(descriptors, opts)
	if err != nil {
		return nil, err
	}
	return proveNormalized(descs, c99Source, opts)
}

// ProveZ3FromImage is ProveZ3 for a 1024-byte BRAM image.
func ProveZ3FromImage(image []byte, c99Source string, opts Options) (*Certificate, error) {
	descs, err := NormalizeImage(image, opts)
	if err != nil {
		return nil, err
	}
	return proveNormalized(descs, c99Source, opts)
}

func proveNormalized(descs []kpol.Descriptor, c99Source string, opts Options) (*Certificate, error) {
	sv, err := newSolver(opts)
	if err != nil {
		return nil, err
	}
	version, err := sv.version()
	if err != nil {
		return nil, err
	}
	return prove(sv, version, descs, c99Source, opts)
}

func prove(sv *solver, version string, descs []kpol.Descriptor, c99Source string, opts Options) (*Certificate, error) {
	moduleName := opts.moduleName()
	imageSHA := tableSHA256(descs)
	active, edges := ExtractActiveCIDsAndEdges(descs)

	topo, topoErr := ComputeTopologicalOrder(active, edges)
	if topoErr != nil {
		topo = append([]int(nil), active...)
	}
	if c99Source == "" {
		c99Source = renderC99(descs, topo, moduleName, imageSHA, defaultVerdictLabel, defaultSolverLabel)
	}
	parsed, err := ParseEmittedC99Source(c99Source)
	if err != nil {
		return nil, err
	}
	effTopo := append([]int(nil), parsed.TopoOrder...)
	if parsed.TopoLoopReversed {
		for i, j := 0, len(effTopo)-1; i < j; i, j = i+1, j-1 {
			effTopo[i], effTopo[j] = effTopo[j], effTopo[i]
		}
	}
	defs := smtDefs(parsed)

	var failures []string
	var checks []Check
	var rank []RankEntry

	p1, p1Fail, err := checkP1(sv, edges, active, effTopo)
	if err != nil {
		return nil, err
	}
	if p1.Passed {
		rank = p1.LyapunovRank
	} else {
		failures = append(failures, p1Fail)
	}
	checks = append(checks, p1)

	p2, p2Fail, err := checkP2(sv, defs, descs, parsed, active)
	if err != nil {
		return nil, err
	}
	if !p2.Passed {
		failures = append(failures, p2Fail)
	}
	checks = append(checks, p2)

	p3, p3Fail, err := checkP3(sv, defs, parsed, active)
	if err != nil {
		return nil, err
	}
	if !p3.Passed {
		failures = append(failures, p3Fail)
	}
	checks = append(checks, p3)

	p4, p4Fail, err := checkP4(sv, defs, descs, parsed)
	if err != nil {
		return nil, err
	}
	if !p4.Passed {
		failures = append(failures, p4Fail)
	}
	checks = append(checks, p4)

	passed := len(failures) == 0
	verdict := "REJECTED"
	if passed {
		verdict = "VERIFIED"
	}
	cascade := make([]Edge, len(edges))
	copy(cascade, edges)
	return &Certificate{
		SchemaVersion:         CertSchemaVersion,
		ModuleName:            moduleName,
		Generator:             GeneratorName,
		Solver:                version,
		Verdict:               verdict,
		Passed:                passed,
		DescriptorTableSHA256: imageSHA,
		C99SourceSHA256:       sha256Hex([]byte(c99Source)),
		ActiveConceptsCount:   len(active),
		ActiveCIDs:            active,
		CascadeEdges:          cascade,
		TopologicalOrder:      effTopo,
		LyapunovRank:          rank,
		WCETMaxCascadeSteps:   len(effTopo),
		Checks:                checks,
		Failures:              failures,
	}, nil
}

// checkP1: strict DAG acyclicity (Lyapunov ranking) and consistency of the
// parsed C99 schedule with every W3 subscription edge.
func checkP1(sv *solver, edges []Edge, active, effTopo []int) (Check, string, error) {
	var sb strings.Builder
	sb.WriteString("(set-logic QF_LIA)")
	for cid := 0; cid < NumConcepts; cid++ {
		fmt.Fprintf(&sb, "\n(declare-const rank_%d Int)", cid)
		fmt.Fprintf(&sb, "\n(assert (and (>= rank_%d 0) (< rank_%d 64)))", cid, cid)
	}
	topoPos := make(map[int]int, len(effTopo))
	for idx, cid := range effTopo {
		topoPos[cid] = idx
	}
	for _, e := range edges {
		if e.Dst >= NumConcepts {
			sb.WriteString("\n(assert false)")
			continue
		}
		fmt.Fprintf(&sb, "\n(assert (< rank_%d rank_%d))", e.Src, e.Dst)
		ps, okS := topoPos[e.Src]
		pd, okD := topoPos[int(e.Dst)]
		if !okS || !okD || ps >= pd {
			sb.WriteString("\n(assert false)")
		}
	}
	verdict, _, err := sv.check(sb.String())
	if err != nil {
		return Check{}, "", err
	}
	if verdict == "sat" {
		if _, topoErr := ComputeTopologicalOrder(active, edges); topoErr != nil {
			msg := fmt.Sprintf("%s: %s", CheckP1, topoErr)
			return Check{Name: CheckP1, Status: "FAILED", Error: topoErr.Error()}, msg, nil
		}
		var rank []RankEntry
		index := map[int]int{}
		for r, cid := range effTopo {
			if at, seen := index[cid]; seen {
				rank[at].Rank = r
			} else {
				index[cid] = len(rank)
				rank = append(rank, RankEntry{CID: cid, Rank: r})
			}
		}
		return Check{
			Name: CheckP1, Status: "SAT_RANKING_FOUND", Passed: true,
			EdgesChecked: len(edges), LyapunovRank: rank, TopologicalOrder: effTopo,
		}, "", nil
	}
	msg := fmt.Sprintf("%s: Z3 returned UNSAT for strict ranking rank[src] < rank[dst] on edges %s and parsed C99 schedule %s",
		CheckP1, edgesRepr(edges), intsRepr(effTopo))
	return Check{Name: CheckP1, Status: "UNSAT_CYCLE_OR_SCHEDULE_VIOLATION", EdgesChecked: len(edges), Error: msg}, msg, nil
}

func hexArgs(d kpol.Descriptor) (op, pr, gf, hz, ac string) {
	return fmt.Sprintf("#x%08x", d.OperandVal), fmt.Sprintf("#x%02x", d.PredOpcode),
		fmt.Sprintf("#x%02x", d.GuardFlags), fmt.Sprintf("#x%02x", d.HazardLimit),
		fmt.Sprintf("#x%02x", d.ActionOpcode)
}

// checkP2: the parsed C99 commit gate never admits a negative candidate or a
// signed overflow, for every cur_state and ev_param in BitVec(32).
func checkP2(sv *solver, defs string, descs []kpol.Descriptor, parsed *ParsedModule, active []int) (Check, string, error) {
	var cfgErrors, disjuncts []string
	for _, cid := range active {
		spec, impl := descs[cid], parsed.Descriptors[cid]
		if !IsDescriptorConfigured(spec) && !IsDescriptorConfigured(impl) {
			continue
		}
		init := int32(impl.CurrentState)
		if impl.GuardFlags&kpol.GuardInvariantEn == 0 {
			cfgErrors = append(cfgErrors, fmt.Sprintf("C%d (%s) has CME_GUARD_INVARIANT_EN disabled (guard_flags=0x%02X)", cid, spec.Name, impl.GuardFlags))
		}
		if impl.GuardFlags&kpol.GuardAssumptionEn == 0 {
			cfgErrors = append(cfgErrors, fmt.Sprintf("C%d (%s) has CME_GUARD_ASSUMPTION_EN disabled (guard_flags=0x%02X)", cid, spec.Name, impl.GuardFlags))
		}
		if init < 0 {
			cfgErrors = append(cfgErrors, fmt.Sprintf("C%d (%s) has negative initial state %d violating state >= 0", cid, spec.Name, init))
		}
		if impl.PredOpcode > kpol.PredBITMASK {
			cfgErrors = append(cfgErrors, fmt.Sprintf("C%d (%s) has unsupported pred_opcode=0x%02X", cid, spec.Name, impl.PredOpcode))
		}
		if impl.ActionOpcode > kpol.ActSub {
			cfgErrors = append(cfgErrors, fmt.Sprintf("C%d (%s) has unsupported action_opcode=0x%02X", cid, spec.Name, impl.ActionOpcode))
		}
		op, pr, gf, hz, ac := hexArgs(impl)
		disjuncts = append(disjuncts, fmt.Sprintf(
			"(and (commit_c99_fn cur_state ev_param %s %s %s %s %s) (or (bvslt (cand_c99_fn cur_state ev_param %s %s) #x00000000) (ovf_rtl cur_state %s %s)))",
			op, pr, gf, hz, ac, op, ac, op, ac))
	}
	orExpr := "false"
	if len(disjuncts) > 0 {
		orExpr = "(or " + strings.Join(disjuncts, " ") + ")"
	}
	script := "(set-logic QF_BV)\n" + defs +
		"\n(declare-const cur_state (_ BitVec 32))\n" +
		"(declare-const ev_param (_ BitVec 32))\n" +
		"(assert " + orExpr + ")\n"
	verdict, model, err := sv.check(script)
	if err != nil {
		return Check{}, "", err
	}
	if len(cfgErrors) > 0 || verdict != "unsat" {
		cex := ""
		if verdict == "sat" {
			cex = " Z3 counterexample: " + model
		}
		detail := pyStrip(strings.Join(cfgErrors, "; ") + cex)
		msg := CheckP2 + ": " + detail
		return Check{Name: CheckP2, Status: "FAILED", Error: detail}, msg, nil
	}
	return Check{
		Name: CheckP2, Status: "UNSAT", Passed: true, ActiveConceptsVerified: len(active),
		QuantifiedDomain: "forall cur_state, ev_param in BitVec(32) on parsed C99 transition & table",
	}, "", nil
}

// checkP3: Fail-Closed non-masking of an invalid sensor value or concept.
func checkP3(sv *solver, defs string, parsed *ParsedModule, active []int) (Check, string, error) {
	faultGate := "false"
	if parsed.HasFaultGate {
		faultGate = "(or (not ev_param_valid) (not concept_valid))"
	}
	var disjuncts []string
	for _, cid := range active {
		impl := parsed.Descriptors[cid]
		if !IsDescriptorConfigured(impl) {
			continue
		}
		op, pr, gf, hz, ac := hexArgs(impl)
		disjuncts = append(disjuncts, fmt.Sprintf(
			"(let ((fault_rej %s) (core_cm (commit_c99_fn cur_state ev_param %s %s %s %s %s)) (cand (cand_c99_fn cur_state ev_param %s %s))) "+
				"(let ((final_cm (and (not fault_rej) core_cm)) (next_st (ite (and (not fault_rej) core_cm) cand cur_state)) "+
				"(fault_inc (ite fault_rej #x00000001 #x00000000))) "+
				"(or final_cm (not (= next_st cur_state)) (not (= fault_inc #x00000001)))))",
			faultGate, op, pr, gf, hz, ac, op, ac))
	}
	orExpr := "(not " + faultGate + ")"
	if len(disjuncts) > 0 {
		orExpr = "(or " + strings.Join(disjuncts, " ") + ")"
	}
	script := "(set-logic QF_BV)\n" + defs +
		"\n(declare-const cur_state (_ BitVec 32))\n" +
		"(declare-const ev_param (_ BitVec 32))\n" +
		"(declare-const ev_param_valid Bool)\n" +
		"(declare-const concept_valid Bool)\n" +
		"(assert (or (not ev_param_valid) (not concept_valid)))\n" +
		"(assert " + orExpr + ")\n"
	verdict, model, err := sv.check(script)
	if err != nil {
		return Check{}, "", err
	}
	if verdict == "unsat" {
		return Check{
			Name: CheckP3, Status: "UNSAT", Passed: true,
			Property: "(!ev_param_valid || !concept_valid) => (!commit && next_state == cur_state && fault_propagations_inc == 1)",
		}, "", nil
	}
	msg := fmt.Sprintf("%s: parsed C99 source fails to block invalid sensor/concept (Z3 witness: %s)", CheckP3, model)
	return Check{Name: CheckP3, Status: "SAT_COUNTEREXAMPLE", Error: msg}, msg, nil
}

// checkP4: the full BitVec(32) miter between the CFG-P RTL specification and
// the parsed C99 expressions, plus concrete table equality.
func checkP4(sv *solver, defs string, descs []kpol.Descriptor, parsed *ParsedModule) (Check, string, error) {
	var diffs []string
	for cid := 0; cid < NumConcepts; cid++ {
		if descs[cid].Pack() != parsed.Descriptors[cid].Pack() {
			diffs = append(diffs, fmt.Sprintf("C%d descriptor mismatch between CFG-P spec and parsed C99 table", cid))
		}
	}
	script := "(set-logic QF_BV)\n" + defs +
		"\n(declare-const cur_state (_ BitVec 32))\n" +
		"(declare-const ev_param (_ BitVec 32))\n" +
		"(declare-const operand (_ BitVec 32))\n" +
		"(declare-const pred_op (_ BitVec 8))\n" +
		"(declare-const guard_fl (_ BitVec 8))\n" +
		"(declare-const haz_lim (_ BitVec 8))\n" +
		"(declare-const act_op (_ BitVec 8))\n" +
		"(declare-const subscriber_cid (_ BitVec 32))\n" +
		"(declare-const cid (_ BitVec 6))\n" +
		"(assert\n" +
		"  (let ((cm_r (commit_rtl cur_state ev_param operand pred_op guard_fl haz_lim act_op))\n" +
		"        (cm_c (commit_c99_fn cur_state ev_param operand pred_op guard_fl haz_lim act_op))\n" +
		"        (cand_r (cand_rtl cur_state ev_param operand act_op))\n" +
		"        (cand_c (cand_c99_fn cur_state ev_param operand act_op))\n" +
		"        (ovf_r (ovf_rtl cur_state operand act_op))\n" +
		"        (ovf_c (ovf_c99_fn cur_state ev_param operand act_op)))\n" +
		"    (or (not (= cm_r cm_c))\n" +
		"        (not (= (ite cm_r cand_r cur_state) (ite cm_c cand_c cur_state)))\n" +
		"        (not (= ovf_r ovf_c))\n" +
		"        (not (= (trig_rtl cm_r guard_fl subscriber_cid cid)\n" +
		"                (trig_c99 cm_c guard_fl subscriber_cid cid))))))\n"
	verdict, model, err := sv.check(script)
	if err != nil {
		return Check{}, "", err
	}
	if len(diffs) > 0 || verdict != "unsat" {
		cex := ""
		if verdict == "sat" {
			cex = " Z3 miter witness: " + model
		}
		msg := CheckP4 + ": divergence between CFG-P RTL spec and parsed C99 source: " + pyStrip(strings.Join(diffs, "; ")+cex)
		return Check{Name: CheckP4, Status: "SAT_DIVERGENCE", Error: msg}, msg, nil
	}
	return Check{
		Name: CheckP4, Status: "UNSAT", Passed: true,
		QuantifiedDomain: "forall cur_state, ev_param, operand in BitVec(32), pred_op, action_op, guard_flags, hazard_limit in BitVec(8) on parsed C99 vs CFG-P RTL spec",
	}, "", nil
}
