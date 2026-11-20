// Package c99 translates 64-slot CME-RAW-1 descriptor tables (KPOL-CME-1,
// KPOL-CME-2, EKPOL-B64 and KPOL-AUTH images) into a deterministic,
// MISRA-oriented C99 safety state machine and proves the emitted source safe
// with an external Z3 process.
//
// It is a port of Engineering/sw/kpol-ref/c99_emitter.py. The emitted text is
// byte-identical to the reference; the Z3 certificate is built from the
// emitted C99 text itself (tables, schedule and transition expressions are
// parsed back and encoded as SMT-LIB2 QF_BV/QF_LIA queries), so mutations of
// the C source are caught.
//
// Fail-closed contract: emission and certification require a working
// "z3" binary and never return a synthetic VERIFIED verdict.
package c99

import (
	"fmt"
	"sort"
	"strings"
	"time"
	"unicode"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

// NumConcepts is the number of concept slots in a CME-RAW-1 table.
const NumConcepts = kpol.SlotCount

// DefaultModuleName is used when Options.ModuleName is empty.
const DefaultModuleName = "km_safety"

// Options configures emission, certification and the reference engine.
type Options struct {
	// ModuleName is the module name (default "km_safety"); it is sanitised
	// for C identifiers and kept verbatim in the certificate.
	ModuleName string
	// ConceptNames maps concept index (CID) to a display name; empty entries
	// keep the descriptor's own name.
	ConceptNames []string
	// ConceptNameMap overrides ConceptNames for the given CIDs.
	ConceptNameMap map[int]string
	// Certificate is an optional precomputed certificate (reference
	// z3_certificate); when nil, EmitC99 computes one with ProveZ3.
	Certificate *Certificate
	// AllowUnverified corresponds to require_z3_verified=False: a cyclic table
	// or a failed certificate does not abort emission. Z3 is still required.
	AllowUnverified bool
	// Z3Path is the z3 binary; empty means exec.LookPath("z3").
	Z3Path string
	// Z3Timeout bounds each z3 invocation (default 60 s, as in the reference).
	Z3Timeout time.Duration
}

func (o Options) moduleName() string {
	if o.ModuleName == "" {
		return DefaultModuleName
	}
	return o.ModuleName
}

// Edge is a directed subscription edge (source CID -> W3 subscriber_cid).
type Edge struct {
	Src int
	Dst uint32
}

func shapeError(format string, args ...any) error {
	return &kpol.Error{Code: "C99-SHAPE", Msg: fmt.Sprintf(format, args...)}
}

// isPySpace reports whether r is whitespace according to Python's str.isspace.
func isPySpace(r rune) bool {
	switch {
	case r >= 0x1c && r <= 0x1f:
		return true
	case r == 0x180e:
		return false
	}
	return unicode.IsSpace(r)
}

func pyStrip(s string) string {
	return strings.TrimFunc(s, isPySpace)
}

// sanitizeIdent mirrors _sanitize_c_ident: every code point outside
// [0-9A-Za-z_] becomes '_', and a leading digit gets a '_' prefix.
func sanitizeIdent(name, fallback string) string {
	var b strings.Builder
	for _, r := range pyStrip(name) {
		switch {
		case r >= '0' && r <= '9', r >= 'A' && r <= 'Z', r >= 'a' && r <= 'z', r == '_':
			b.WriteRune(r)
		default:
			b.WriteByte('_')
		}
	}
	cleaned := b.String()
	if cleaned == "" {
		return fallback
	}
	if cleaned[0] >= '0' && cleaned[0] <= '9' {
		cleaned = "_" + cleaned
	}
	return cleaned
}

func (o Options) conceptName(cid int, own string) string {
	raw := ""
	if v, ok := o.ConceptNameMap[cid]; ok && v != "" {
		raw = v
	} else if cid < len(o.ConceptNames) && o.ConceptNames[cid] != "" {
		raw = o.ConceptNames[cid]
	}
	if raw == "" {
		raw = own
	}
	if raw == "" {
		raw = fmt.Sprintf("Concept_%d", cid)
	}
	return sanitizeIdent(raw, fmt.Sprintf("Concept_%d", cid))
}

// NormalizeDescriptors converts a descriptor list into exactly 64 descriptors
// indexed by CID (missing slots become zero descriptors named "Concept_<cid>"
// and names are sanitised into C identifiers). It mirrors normalize_descriptors
// for descriptor sequences; the input is not modified.
func NormalizeDescriptors(src []kpol.Descriptor, opts Options) ([]kpol.Descriptor, error) {
	if len(src) > NumConcepts {
		return nil, shapeError("expected at most 64 descriptors, got %d", len(src))
	}
	byCID := make(map[int]kpol.Descriptor, len(src))
	for _, d := range src {
		if d.CID < 0 || d.CID >= NumConcepts {
			return nil, shapeError("descriptor CIDs must be unique in 0..63")
		}
		byCID[d.CID] = d
	}
	if len(byCID) != len(src) {
		return nil, shapeError("descriptor CIDs must be unique in 0..63")
	}
	full := make([]kpol.Descriptor, NumConcepts)
	for cid := range full {
		if d, ok := byCID[cid]; ok {
			full[cid] = d
		} else {
			full[cid] = kpol.Descriptor{CID: cid, Name: fmt.Sprintf("Concept_%d", cid)}
		}
	}
	return finishNormalize(full, opts), nil
}

// NormalizeImage disassembles a 1024-byte BRAM image and normalises it.
func NormalizeImage(image []byte, opts Options) ([]kpol.Descriptor, error) {
	ds, err := kpol.Disassemble(image)
	if err != nil {
		return nil, err
	}
	return finishNormalize(ds, opts), nil
}

func finishNormalize(full []kpol.Descriptor, opts Options) []kpol.Descriptor {
	out := make([]kpol.Descriptor, NumConcepts)
	for cid := range out {
		d := full[cid]
		d.CID = cid
		d.Name = opts.conceptName(cid, d.Name)
		out[cid] = d
	}
	return out
}

// IsDescriptorConfigured reports whether the slot is non-empty.
func IsDescriptorConfigured(d kpol.Descriptor) bool {
	return d.GuardFlags != 0 || d.CurrentState != 0 || d.OperandVal != 0 ||
		d.PredOpcode != 0 || d.ActionOpcode != 0 || d.SubscriberCID != 0 || d.HazardLimit != 0
}

// HasSubscriptionEdge matches km_concept_micro_engine.sv subscription enable.
func HasSubscriptionEdge(d kpol.Descriptor) bool {
	return d.GuardFlags&kpol.GuardSubscriberEn != 0 || d.SubscriberCID != 0
}

// ExtractActiveCIDsAndEdges returns the sorted active CIDs and the directed
// subscription edges (src, W3) in CID order.
func ExtractActiveCIDsAndEdges(ds []kpol.Descriptor) ([]int, []Edge) {
	var active [NumConcepts]bool
	var edges []Edge
	for _, d := range ds {
		if IsDescriptorConfigured(d) {
			active[d.CID] = true
		}
		if HasSubscriptionEdge(d) {
			active[d.CID] = true
			edges = append(edges, Edge{Src: d.CID, Dst: d.SubscriberCID})
			if d.SubscriberCID < NumConcepts {
				active[d.SubscriberCID] = true
			}
		}
	}
	cids := make([]int, 0, NumConcepts)
	for cid, on := range active {
		if on {
			cids = append(cids, cid)
		}
	}
	if len(cids) == 0 {
		cids = append(cids, 0)
	}
	return cids, edges
}

func intsRepr(v []int) string {
	parts := make([]string, len(v))
	for i, x := range v {
		parts[i] = fmt.Sprint(x)
	}
	return "[" + strings.Join(parts, ", ") + "]"
}

func edgesRepr(edges []Edge) string {
	parts := make([]string, len(edges))
	for i, e := range edges {
		parts[i] = fmt.Sprintf("(%d, %d)", e.Src, e.Dst)
	}
	return "[" + strings.Join(parts, ", ") + "]"
}

// ComputeTopologicalOrder returns the lexicographically smallest topological
// order of the active CIDs, or a C99-DAG-RANGE / C99-DAG-CYCLE error.
//
// This is an intentional static tightening over the RTL: a descriptor with
// subscriber_cid >= 64 merely deasserts the target-valid signal in hardware,
// whereas the emitter rejects it.
func ComputeTopologicalOrder(active []int, edges []Edge) ([]int, error) {
	var inSet [NumConcepts]bool
	for _, c := range active {
		if c < 0 || c >= NumConcepts {
			return nil, shapeError("active CID %d outside 0..63", c)
		}
		inSet[c] = true
	}
	for _, e := range edges {
		if e.Src < 0 || e.Src >= NumConcepts {
			return nil, shapeError("edge source CID %d outside 0..63", e.Src)
		}
		if e.Dst >= NumConcepts {
			return nil, &kpol.Error{Code: "C99-DAG-RANGE", Msg: fmt.Sprintf(
				"concept C%d has out-of-range subscriber_cid=%d (expected 0..63)", e.Src, e.Dst)}
		}
		if e.Src == int(e.Dst) {
			return nil, &kpol.Error{Code: "C99-DAG-CYCLE", Msg: fmt.Sprintf(
				"self-subscription loop detected on concept C%d -> C%d", e.Src, e.Dst)}
		}
		inSet[e.Src] = true
		inSet[e.Dst] = true
	}
	var adj [NumConcepts][]int
	var indeg [NumConcepts]int
	for _, e := range edges {
		adj[e.Src] = append(adj[e.Src], int(e.Dst))
		indeg[e.Dst]++
	}
	var ready []int
	total := 0
	for cid, on := range inSet {
		if on {
			total++
			if indeg[cid] == 0 {
				ready = append(ready, cid)
			}
		}
	}
	topo := make([]int, 0, total)
	for len(ready) > 0 {
		u := ready[0]
		ready = ready[1:]
		topo = append(topo, u)
		for _, v := range adj[u] {
			indeg[v]--
			if indeg[v] == 0 {
				ready = append(ready, v)
				sort.Ints(ready)
			}
		}
	}
	if len(topo) != total {
		var placed [NumConcepts]bool
		for _, c := range topo {
			placed[c] = true
		}
		var cyclic []int
		for cid, on := range inSet {
			if on && !placed[cid] {
				cyclic = append(cyclic, cid)
			}
		}
		return nil, &kpol.Error{Code: "C99-DAG-CYCLE", Msg: fmt.Sprintf(
			"cyclic subscription graph detected involving CIDs %s", intsRepr(cyclic))}
	}
	return topo, nil
}
