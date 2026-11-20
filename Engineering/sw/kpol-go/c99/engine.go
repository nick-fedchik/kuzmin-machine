package c99

import "github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"

// Step status codes, equal to km_safety_status_t in the emitted C99.
const (
	StatusCommitted      = 0
	StatusRejectedGuard  = 1
	StatusRejectedFault  = 2
	StatusRejectedBadCID = 3
)

const (
	maxCascadeIterations = 64
	allConceptsValidMask = ^uint64(0)
	signBit              = 0x80000000
)

// StepResult is the per-event cascade telemetry (km_safety_step_result_t).
type StepResult struct {
	StepsExecuted   int
	Commits         int
	Rejects         int
	FaultPropagated bool
	LastState       int32
	Status          int
}

// Engine is the bit-exact reference model of the 64-concept CFG-P table with
// explicit validity tracking (ReferenceCmeSafetyEngine). Counters wrap at 32
// bits like the C99 context. The exported state fields may be inspected or
// restored by tests, but Step is the only transition function.
type Engine struct {
	Descriptors        []kpol.Descriptor
	ActiveCIDs         []int
	Edges              []Edge
	TopoOrder          []int
	State              [NumConcepts]int32
	ValidMask          uint64
	EventsProcessed    uint32
	Commits            uint32
	Rejects            uint32
	FaultPropagations  uint32
	LastCommittedState int32
}

// NewEngine normalises the descriptors and builds an engine in its initial
// state; a cyclic or out-of-range subscription graph is rejected with the
// C99-DAG-* errors of ComputeTopologicalOrder.
func NewEngine(descriptors []kpol.Descriptor, opts Options) (*Engine, error) {
	descs, err := NormalizeDescriptors(descriptors, opts)
	if err != nil {
		return nil, err
	}
	return newEngine(descs)
}

// NewEngineFromImage is NewEngine for a 1024-byte BRAM image.
func NewEngineFromImage(image []byte, opts Options) (*Engine, error) {
	descs, err := NormalizeImage(image, opts)
	if err != nil {
		return nil, err
	}
	return newEngine(descs)
}

func newEngine(descs []kpol.Descriptor) (*Engine, error) {
	active, edges := ExtractActiveCIDsAndEdges(descs)
	topo, err := ComputeTopologicalOrder(active, edges)
	if err != nil {
		return nil, err
	}
	e := &Engine{
		Descriptors: descs, ActiveCIDs: active, Edges: edges, TopoOrder: topo,
		ValidMask: allConceptsValidMask,
	}
	for cid, d := range descs {
		e.State[cid] = int32(d.CurrentState)
	}
	return e, nil
}

// InvalidateConcept marks a concept as uncertain ('_'); out-of-range CIDs are ignored.
func (e *Engine) InvalidateConcept(cid int) {
	if cid >= 0 && cid < NumConcepts {
		e.ValidMask &^= 1 << uint(cid)
	}
}

// RevalidateConcept restores a concept with a recovered non-negative state; a
// negative state leaves (or makes) the concept invalid.
func (e *Engine) RevalidateConcept(cid int, recovered int32) {
	if cid < 0 || cid >= NumConcepts {
		return
	}
	if recovered < 0 {
		e.ValidMask &^= 1 << uint(cid)
		return
	}
	e.State[cid] = recovered
	e.ValidMask |= 1 << uint(cid)
}

// Step processes one event at rootCID and follows the commit cascade.
func (e *Engine) Step(rootCID int, param int32, paramValid bool) StepResult {
	if rootCID < 0 || rootCID >= NumConcepts {
		e.EventsProcessed++
		e.Rejects++
		e.FaultPropagations++
		return StepResult{
			StepsExecuted: 1, Rejects: 1, FaultPropagated: true,
			LastState: e.LastCommittedState, Status: StatusRejectedBadCID,
		}
	}

	var steps, commits, rejects int
	faultProp := false
	cid := rootCID
	curParam, curValid := param, paramValid

	for iter := 0; iter < maxCascadeIterations; iter++ {
		d := e.Descriptors[cid]
		steps++
		e.EventsProcessed++

		if !curValid || e.ValidMask>>uint(cid)&1 == 0 {
			e.Rejects++
			e.FaultPropagations++
			rejects++
			faultProp = true
			break
		}

		paramU := uint32(curParam)
		var predRaw bool
		switch d.PredOpcode {
		case kpol.PredNOP:
			predRaw = true
		case kpol.PredEQ:
			predRaw = paramU == d.OperandVal
		case kpol.PredNEQ:
			predRaw = paramU != d.OperandVal
		case kpol.PredGT:
			predRaw = curParam > int32(d.OperandVal)
		case kpol.PredLT:
			predRaw = curParam < int32(d.OperandVal)
		case kpol.PredRANGE:
			lo := int32(int16(d.OperandVal & 0xFFFF))
			hi := int32(int16(d.OperandVal >> 16))
			predRaw = lo <= curParam && curParam <= hi
		case kpol.PredBITMASK:
			predRaw = paramU&d.OperandVal != 0
		}

		curU := uint32(e.State[cid])
		candU := curU
		actionValid := true
		overflow := false
		switch d.ActionOpcode {
		case kpol.ActAssign:
			candU = paramU
		case kpol.ActInc:
			candU = curU + 1
			overflow = curU == 0x7FFFFFFF
		case kpol.ActDec:
			candU = curU - 1
			overflow = curU == signBit
		case kpol.ActAdd:
			candU = curU + d.OperandVal
			overflow = (curU^d.OperandVal)&signBit == 0 && (candU^curU)&signBit != 0
		case kpol.ActSub:
			candU = curU - d.OperandVal
			overflow = (curU^d.OperandVal)&signBit != 0 && (candU^curU)&signBit != 0
		default:
			actionValid = false
		}

		assumpTrue := predRaw
		if d.GuardFlags&kpol.GuardInvertAssumption != 0 {
			assumpTrue = !predRaw
		}
		hazard := d.GuardFlags&kpol.GuardHazardEn != 0 && d.HazardLimit != 0 && curParam > int32(d.HazardLimit)
		commit := actionValid &&
			d.GuardFlags&kpol.GuardAssumptionEn != 0 && assumpTrue &&
			d.GuardFlags&kpol.GuardInvariantEn != 0 && !overflow && candU&signBit == 0 &&
			!hazard
		if !commit {
			e.Rejects++
			rejects++
			break
		}

		e.State[cid] = int32(candU)
		e.Commits++
		e.LastCommittedState = int32(candU)
		commits++

		subEn := d.GuardFlags&kpol.GuardSubscriberEn != 0 || d.SubscriberCID != 0
		next := int(d.SubscriberCID & 0x3F)
		if d.SubscriberCID < NumConcepts && subEn && next != cid {
			curParam = e.State[cid]
			curValid = e.ValidMask>>uint(cid)&1 != 0
			cid = next
			continue
		}
		break
	}

	status := StatusRejectedGuard
	switch {
	case commits > 0:
		status = StatusCommitted
	case faultProp:
		status = StatusRejectedFault
	}
	return StepResult{
		StepsExecuted: steps, Commits: commits, Rejects: rejects,
		FaultPropagated: faultProp, LastState: e.LastCommittedState, Status: status,
	}
}
