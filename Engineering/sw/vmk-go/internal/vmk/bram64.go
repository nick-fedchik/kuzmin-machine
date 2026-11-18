package vmk

import (
	"encoding/binary"
	"fmt"
	"sort"
	"strings"
)

// ConceptDescriptor represents one 16-byte slot (W0..W3) in the 64-slot CME-RAW-1 BRAM.
type ConceptDescriptor struct {
	CID           int    `json:"cid"`
	Name          string `json:"name"`
	TypeName      string `json:"type_name"`
	CurrentState  uint32 `json:"current_state"`
	OperandVal    uint32 `json:"operand_val"`
	PredOpcode    uint8  `json:"pred_opcode"`
	GuardFlags    uint8  `json:"guard_flags"`
	HazardLimit   uint8  `json:"hazard_limit"`
	ActionOpcode  uint8  `json:"action_opcode"`
	SubscriberCID uint32 `json:"subscriber_cid"`
}

// W0Int32 returns W0 interpreted as two's-complement signed int32.
func (d ConceptDescriptor) W0Int32() int32 {
	return int32(d.CurrentState)
}

// W1Int32 returns W1 interpreted as two's-complement signed int32.
func (d ConceptDescriptor) W1Int32() int32 {
	return int32(d.OperandVal)
}

// W2Word packs PredOpcode, GuardFlags, HazardLimit, and ActionOpcode into a 32-bit word.
func (d ConceptDescriptor) W2Word() uint32 {
	return uint32(d.PredOpcode) |
		(uint32(d.GuardFlags) << 8) |
		(uint32(d.HazardLimit) << 16) |
		(uint32(d.ActionOpcode) << 24)
}

// Pack encodes the descriptor into 16 little-endian bytes (W0..W3).
func (d ConceptDescriptor) Pack() [16]byte {
	var buf [16]byte
	binary.LittleEndian.PutUint32(buf[0:4], d.CurrentState)
	binary.LittleEndian.PutUint32(buf[4:8], d.OperandVal)
	binary.LittleEndian.PutUint32(buf[8:12], d.W2Word())
	binary.LittleEndian.PutUint32(buf[12:16], d.SubscriberCID)
	return buf
}

// IsConfigured returns true if any field in the 16-byte descriptor is non-zero.
func (d ConceptDescriptor) IsConfigured() bool {
	return d.GuardFlags != 0 ||
		d.CurrentState != 0 ||
		d.OperandVal != 0 ||
		d.PredOpcode != 0 ||
		d.ActionOpcode != 0 ||
		d.SubscriberCID != 0 ||
		d.HazardLimit != 0
}

// HasSubscriptionEdge returns true if this descriptor routes a commit to a subscriber.
func (d ConceptDescriptor) HasSubscriptionEdge() bool {
	return ((d.GuardFlags & GuardSubscriberEn) != 0) || (d.SubscriberCID != 0)
}

// DisassembleBRAM unpacks a 1024-byte CME-RAW-1 image into 64 ConceptDescriptors.
func DisassembleBRAM(data []byte, conceptNames []string) ([64]ConceptDescriptor, error) {
	var out [64]ConceptDescriptor
	if len(data) != 1024 {
		return out, fmt.Errorf("VMK-BRAM-SIZE: expected 1024 bytes, got %d", len(data))
	}
	for cid := 0; cid < 64; cid++ {
		off := cid * 16
		w0 := binary.LittleEndian.Uint32(data[off : off+4])
		w1 := binary.LittleEndian.Uint32(data[off+4 : off+8])
		w2 := binary.LittleEndian.Uint32(data[off+8 : off+12])
		w3 := binary.LittleEndian.Uint32(data[off+12 : off+16])
		name := fmt.Sprintf("Concept_%d", cid)
		if cid < len(conceptNames) && strings.TrimSpace(conceptNames[cid]) != "" {
			name = SanitizeIdent(conceptNames[cid], name)
		}
		out[cid] = ConceptDescriptor{
			CID:           cid,
			Name:          name,
			TypeName:      "Int32",
			CurrentState:  w0,
			OperandVal:    w1,
			PredOpcode:    uint8(w2 & 0xFF),
			GuardFlags:    uint8((w2 >> 8) & 0xFF),
			HazardLimit:   uint8((w2 >> 16) & 0xFF),
			ActionOpcode:  uint8((w2 >> 24) & 0xFF),
			SubscriberCID: w3,
		}
	}
	return out, nil
}

// PackBRAM encodes 64 ConceptDescriptors into a 1024-byte CME-RAW-1 binary image.
func PackBRAM(descs [64]ConceptDescriptor) []byte {
	out := make([]byte, 1024)
	for cid := 0; cid < 64; cid++ {
		packed := descs[cid].Pack()
		copy(out[cid*16:(cid+1)*16], packed[:])
	}
	return out
}

// CRC8 computes CRC-8-CCITT (polynomial 0x07, init 0x00) over a byte slice (used for 16B hot rule packets).
func CRC8(data []byte) uint8 {
	var crc uint8
	for _, b := range data {
		crc ^= b
		for bit := 0; bit < 8; bit++ {
			if (crc & 0x80) != 0 {
				crc = (crc << 1) ^ 0x07
			} else {
				crc <<= 1
			}
		}
	}
	return crc
}

// DecodePredicateFormula returns the human-readable predicate formula (`::`) for a descriptor.
func DecodePredicateFormula(d ConceptDescriptor) string {
	if (d.GuardFlags & GuardAssumptionEn) == 0 {
		return "ASSUMP_DISABLED(false)"
	}
	opI32 := int32(d.OperandVal)
	opU32 := d.OperandVal
	invert := (d.GuardFlags & GuardInvertAssumption) != 0

	var raw string
	switch d.PredOpcode {
	case PredNOP:
		raw = "true"
	case PredEQ:
		raw = fmt.Sprintf("param == %d", opI32)
	case PredNEQ:
		raw = fmt.Sprintf("param != %d", opI32)
	case PredGT:
		raw = fmt.Sprintf("param > %d", opI32)
	case PredLT:
		raw = fmt.Sprintf("param < %d", opI32)
	case PredRANGE:
		lo16 := int16(uint16(opU32 & 0xFFFF))
		hi16 := int16(uint16((opU32 >> 16) & 0xFFFF))
		raw = fmt.Sprintf("%d <= param <= %d", lo16, hi16)
	case PredBITMASK:
		raw = fmt.Sprintf("(param & 0x%08X) != 0", opU32)
	case PredUGT:
		raw = fmt.Sprintf("u32(param) > 0x%08X", opU32)
	default:
		raw = fmt.Sprintf("UNKNOWN_PRED(0x%02X)", d.PredOpcode)
	}

	if invert {
		switch d.PredOpcode {
		case PredLT:
			return fmt.Sprintf("!(param < %d) [>= %d]", opI32, opI32)
		case PredGT:
			return fmt.Sprintf("!(param > %d) [<= %d]", opI32, opI32)
		case PredEQ:
			return fmt.Sprintf("!(param == %d) [!= %d]", opI32, opI32)
		default:
			return fmt.Sprintf("!(%s)", raw)
		}
	}
	return raw
}

// DecodeActionFormula returns the human-readable candidate action formula.
func DecodeActionFormula(d ConceptDescriptor) string {
	opI32 := int32(d.OperandVal)
	switch d.ActionOpcode {
	case ActAssign:
		return "W0' := param"
	case ActInc:
		return "W0' := W0 + 1"
	case ActDec:
		return "W0' := W0 - 1"
	case ActAdd:
		return fmt.Sprintf("W0' := W0 + %d", opI32)
	case ActSub:
		return fmt.Sprintf("W0' := W0 - %d", opI32)
	case ActNOP:
		return "W0' := W0"
	default:
		return fmt.Sprintf("INVALID_ACT(0x%02X)", d.ActionOpcode)
	}
}

// DecodeInvariantFormula returns the human-readable Big Dot (`•`) invariant gate formula.
func DecodeInvariantFormula(d ConceptDescriptor) string {
	if (d.GuardFlags & GuardInvariantEn) == 0 {
		return "INV_DISABLED(false)"
	}
	parts := []string{"cand >= 0", "!ovf32"}
	if (d.GuardFlags&GuardHazardEn) != 0 && d.HazardLimit != 0 {
		parts = append(parts, fmt.Sprintf("param <= %d", d.HazardLimit))
	}
	return strings.Join(parts, " && ")
}

// DecodeW2Summary returns the packed W2 word and decoded summary string.
func DecodeW2Summary(d ConceptDescriptor) (uint32, string) {
	w2 := d.W2Word()
	predStr := DecodePredicateFormula(d)
	actStr := DecodeActionFormula(d)
	invStr := "•(OFF)"
	if (d.GuardFlags & GuardInvariantEn) != 0 {
		invStr = "•(cand>=0 && !ovf)"
	}
	return w2, fmt.Sprintf("::(%s) | %s | %s", predStr, actStr, invStr)
}

// DecodeW3Subscriber returns the human-readable subscriber routing description for W3.
func DecodeW3Subscriber(d ConceptDescriptor, all [64]ConceptDescriptor) string {
	if !d.HasSubscriptionEdge() {
		return "None (0)"
	}
	target := int(d.SubscriberCID)
	if target < 0 || target >= 64 {
		return fmt.Sprintf("OUT_OF_RANGE(C%d)", target)
	}
	if target == d.CID {
		return fmt.Sprintf("SELF_LOOP(C%d -> suppressed)", target)
	}
	return fmt.Sprintf("-> C%d (%s)", target, all[target].Name)
}

// WatchpointTrigger records a watchpoint or breakpoint firing during wave debugging.
type WatchpointTrigger struct {
	StepIndex    int    `json:"step_index"`
	EventID      int    `json:"event_id"`
	CascadeDepth int    `json:"cascade_depth"`
	CID          int    `json:"cid"`
	ConceptName  string `json:"concept_name"`
	Reason       string `json:"reason"`
	Verdict      string `json:"verdict"`
	PreW0        int32  `json:"pre_w0"`
	PostW0       int32  `json:"post_w0"`
	Param        int32  `json:"param"`
	ParamValid   bool   `json:"param_valid"`
}

// CascadeTraceStep records all 10 phases of a single concept evaluation step.
type CascadeTraceStep struct {
	StepIndex              int      `json:"step_index"`
	EventID                int      `json:"event_id"`
	CascadeStep            int      `json:"cascade_step"`
	Depth                  int      `json:"depth"`
	CID                    int      `json:"cid"`
	ConceptName            string   `json:"concept_name"`
	ConceptType            string   `json:"concept_type,omitempty"`
	EventDisplay           string   `json:"event_display,omitempty"`
	PreDisplay             string   `json:"pre_display,omitempty"`
	PostDisplay            string   `json:"post_display,omitempty"`
	Param                  int32    `json:"param"`
	ParamValid             bool     `json:"param_valid"`
	PreW0                  int32    `json:"pre_w0"`
	PreValid               bool     `json:"pre_valid"`
	PredFormula            string   `json:"pred_formula"`
	PredMatch              bool     `json:"pred_match"`
	ActionFormula          string   `json:"action_formula"`
	CandidateW0            int32    `json:"candidate_w0"`
	ArithOverflow          bool     `json:"arith_overflow"`
	InvFormula             string   `json:"inv_formula"`
	InvOK                  bool     `json:"inv_ok"`
	Verdict                string   `json:"verdict"`
	PostW0                 int32    `json:"post_w0"`
	PostValid              bool     `json:"post_valid"`
	EnqueuedSubscriberCID  *int     `json:"enqueued_subscriber_cid"`
	EnqueuedSubscriberName *string  `json:"enqueued_subscriber_name"`
	WatchpointsHit         []string `json:"watchpoints_hit"`
}

// QueuedEvent represents an event in the 16-entry ingress FIFO queue.
type QueuedEvent struct {
	CID        int
	Param      int32
	ParamValid bool
}

// BRAM64Engine implements the hardware-accurate 64-slot CME-RAW-1 / CFG-P / CFG-P-HA VMK engine.
type BRAM64Engine struct {
	ModuleName       string
	Profile          string
	ModeLabel        string
	SourceCode       string
	Bank0            [64]ConceptDescriptor
	Bank1            [64]ConceptDescriptor
	ActiveBank       int
	SwapPending      bool
	SwapCount        uint32
	ShadowW0Override [64]bool

	ActiveCIDs       []int
	TopologicalOrder []int
	InitialState     [64]int32
	State            [64]int32
	InitialValidMask uint64
	ValidMask        uint64

	FIFOQueue     []QueuedEvent
	FIFOCapacity  int
	FIFOOverflow  bool
	DroppedEvents uint32

	WatchCIDs          map[int]bool
	BreakOnReject      bool
	WatchStateChange   bool
	ThresholdWatch     map[int]int32
	StopOnBreakpoint   bool
	HaltedOnBreakpoint bool

	EventsProcessed    uint32
	Commits            uint32
	Rejects            uint32
	FaultPropagations  uint32
	LastCommittedState int32
	EventCounter       int

	Steps              []CascadeTraceStep
	WatchpointTriggers []WatchpointTrigger
}

// NewBRAM64Engine initializes a 64-slot BRAM VMK engine from a 1024-byte image or descriptor slice.
func NewBRAM64Engine(bramBytes []byte, profile, moduleName, sourceCode string, conceptNames []string) (*BRAM64Engine, error) {
	descs, err := DisassembleBRAM(bramBytes, conceptNames)
	if err != nil {
		return nil, err
	}
	if moduleName == "" {
		moduleName = "km_debug"
	}
	if profile == "" {
		profile = "KPOL-CME-2"
	}
	eng := &BRAM64Engine{
		ModuleName:       moduleName,
		Profile:          profile,
		SourceCode:       strings.TrimSpace(sourceCode),
		Bank0:            descs,
		Bank1:            descs,
		ActiveBank:       0,
		InitialValidMask: 0xFFFFFFFFFFFFFFFF,
		ValidMask:        0xFFFFFFFFFFFFFFFF,
		FIFOCapacity:     16,
		WatchCIDs:        make(map[int]bool),
		ThresholdWatch:   make(map[int]int32),
		WatchStateChange: true,
	}
	for cid := 0; cid < 64; cid++ {
		eng.InitialState[cid] = int32(descs[cid].CurrentState)
		eng.State[cid] = int32(descs[cid].CurrentState)
	}
	eng.recomputeActiveAndTopo()
	return eng, nil
}

// Descriptors returns a pointer to the currently active BRAM bank (Bank0 or Bank1).
func (e *BRAM64Engine) Descriptors() *[64]ConceptDescriptor {
	if e.ActiveBank == 1 {
		return &e.Bank1
	}
	return &e.Bank0
}

// ShadowDescriptors returns a pointer to the currently inactive shadow BRAM bank.
func (e *BRAM64Engine) ShadowDescriptors() *[64]ConceptDescriptor {
	if e.ActiveBank == 1 {
		return &e.Bank0
	}
	return &e.Bank1
}

// HotUpdateShadowSlot updates a descriptor slot in the shadow bank verified by CRC-8-CCITT,
// and marks SwapPending for atomic bank switching at the ST_IDLE boundary (CFG-P-HA).
func (e *BRAM64Engine) HotUpdateShadowSlot(cid int, packet16 []byte, expectedCRC8 uint8, overrideW0 bool) error {
	if cid < 0 || cid >= 64 {
		return fmt.Errorf("VMK-HA-CID: invalid slot CID %d", cid)
	}
	if len(packet16) != 16 {
		return fmt.Errorf("VMK-HA-LEN: expected 16-byte descriptor packet, got %d", len(packet16))
	}
	actualCRC := CRC8(packet16)
	if actualCRC != expectedCRC8 {
		return fmt.Errorf("VMK-HA-CRC8: CRC-8 mismatch (expected 0x%02X, got 0x%02X)", expectedCRC8, actualCRC)
	}
	w0 := binary.LittleEndian.Uint32(packet16[0:4])
	w1 := binary.LittleEndian.Uint32(packet16[4:8])
	w2 := binary.LittleEndian.Uint32(packet16[8:12])
	w3 := binary.LittleEndian.Uint32(packet16[12:16])

	shadow := e.ShadowDescriptors()
	curName := shadow[cid].Name
	if !overrideW0 {
		w0 = uint32(e.State[cid])
	}
	shadow[cid] = ConceptDescriptor{
		CID:           cid,
		Name:          curName,
		TypeName:      "Int32",
		CurrentState:  w0,
		OperandVal:    w1,
		PredOpcode:    uint8(w2 & 0xFF),
		GuardFlags:    uint8((w2 >> 8) & 0xFF),
		HazardLimit:   uint8((w2 >> 16) & 0xFF),
		ActionOpcode:  uint8((w2 >> 24) & 0xFF),
		SubscriberCID: w3,
	}
	e.ShadowW0Override[cid] = overrideW0
	e.SwapPending = true
	return nil
}

// SwapBanksAtIdleBoundary performs an atomic CFG-P-HA bank swap at the ST_IDLE boundary,
// preserving live W0 states for slots without explicit shadow W0 override.
func (e *BRAM64Engine) SwapBanksAtIdleBoundary() {
	if !e.SwapPending {
		return
	}
	shadow := e.ShadowDescriptors()
	for cid := 0; cid < 64; cid++ {
		if e.ShadowW0Override[cid] {
			e.State[cid] = int32(shadow[cid].CurrentState)
		} else {
			shadow[cid].CurrentState = uint32(e.State[cid])
		}
		e.ShadowW0Override[cid] = false
	}
	if e.ActiveBank == 0 {
		e.ActiveBank = 1
		e.Bank0 = e.Bank1
	} else {
		e.ActiveBank = 0
		e.Bank1 = e.Bank0
	}
	e.SwapPending = false
	e.SwapCount++
	e.recomputeActiveAndTopo()
}

// EnqueueFIFO pushes an external event into the 16-entry ingress FIFO queue.
func (e *BRAM64Engine) EnqueueFIFO(cid int, param int32, paramValid bool) bool {
	if len(e.FIFOQueue) >= e.FIFOCapacity {
		e.FIFOOverflow = true
		e.DroppedEvents++
		return false
	}
	e.FIFOQueue = append(e.FIFOQueue, QueuedEvent{
		CID:        cid,
		Param:      param,
		ParamValid: paramValid,
	})
	return true
}

// DrainFIFO executes all events currently queued in the 16-entry FIFO.
func (e *BRAM64Engine) DrainFIFO() []CascadeTraceStep {
	var allSteps []CascadeTraceStep
	for len(e.FIFOQueue) > 0 {
		if e.HaltedOnBreakpoint && e.StopOnBreakpoint {
			break
		}
		ev := e.FIFOQueue[0]
		e.FIFOQueue = e.FIFOQueue[1:]
		wave := e.StepEvent(ev.CID, ev.Param, ev.ParamValid)
		allSteps = append(allSteps, wave...)
		if e.SwapPending {
			e.SwapBanksAtIdleBoundary()
		}
	}
	return allSteps
}

func (e *BRAM64Engine) recomputeActiveAndTopo() {
	descs := e.Descriptors()
	activeSet := make(map[int]bool)
	type edge struct{ src, dst int }
	var edges []edge
	for cid := 0; cid < 64; cid++ {
		d := descs[cid]
		if d.IsConfigured() {
			activeSet[cid] = true
		}
		if d.HasSubscriptionEdge() {
			activeSet[cid] = true
			dst := int(d.SubscriberCID)
			edges = append(edges, edge{cid, dst})
			if dst >= 0 && dst < 64 {
				activeSet[dst] = true
			}
		}
	}
	if len(activeSet) == 0 {
		activeSet[0] = true
	}
	var active []int
	for cid := range activeSet {
		active = append(active, cid)
	}
	sort.Ints(active)
	e.ActiveCIDs = active

	adj := make(map[int][]int)
	indeg := make(map[int]int)
	validDAG := true
	for _, u := range active {
		indeg[u] = 0
	}
	for _, ed := range edges {
		if ed.dst < 0 || ed.dst >= 64 || ed.src == ed.dst {
			validDAG = false
			break
		}
		adj[ed.src] = append(adj[ed.src], ed.dst)
		indeg[ed.dst]++
	}
	if !validDAG {
		e.TopologicalOrder = append([]int(nil), active...)
		return
	}
	var ready []int
	for _, u := range active {
		if indeg[u] == 0 {
			ready = append(ready, u)
		}
	}
	sort.Ints(ready)
	var topo []int
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
	if len(topo) != len(active) {
		e.TopologicalOrder = append([]int(nil), active...)
	} else {
		e.TopologicalOrder = topo
	}
}

// Reset restores initial states, validity bits, and clears all trace logs.
func (e *BRAM64Engine) Reset() {
	e.State = e.InitialState
	for cid := 0; cid < 64; cid++ {
		e.Bank0[cid].CurrentState = uint32(e.InitialState[cid])
		e.Bank1[cid].CurrentState = uint32(e.InitialState[cid])
	}
	e.ValidMask = e.InitialValidMask
	e.EventsProcessed = 0
	e.Commits = 0
	e.Rejects = 0
	e.FaultPropagations = 0
	e.LastCommittedState = 0
	e.EventCounter = 0
	e.HaltedOnBreakpoint = false
	e.Steps = nil
	e.WatchpointTriggers = nil
	e.FIFOQueue = nil
	e.FIFOOverflow = false
	e.DroppedEvents = 0
}

// InvalidateConcept forces concept cid into the uncertainty state '_' (valid=0).
func (e *BRAM64Engine) InvalidateConcept(cid int) {
	if cid >= 0 && cid < 64 {
		e.ValidMask &^= (uint64(1) << uint(cid))
	}
}

// RevalidateConcept recovers concept cid from '_' if recoveredState >= 0.
func (e *BRAM64Engine) RevalidateConcept(cid int, recoveredState int32) {
	if cid >= 0 && cid < 64 {
		if recoveredState < 0 {
			e.ValidMask &^= (uint64(1) << uint(cid))
		} else {
			e.State[cid] = recoveredState
			e.ValidMask |= (uint64(1) << uint(cid))
		}
	}
}

// EvalPredicate evaluates predicate `::` (including invert flag) for descriptor d.
func (e *BRAM64Engine) EvalPredicate(d ConceptDescriptor, curParam int32) bool {
	paramU32 := uint32(curParam)
	var predRaw bool
	switch d.PredOpcode {
	case PredNOP:
		predRaw = true
	case PredEQ:
		predRaw = paramU32 == d.OperandVal
	case PredNEQ:
		predRaw = paramU32 != d.OperandVal
	case PredGT:
		predRaw = curParam > int32(d.OperandVal)
	case PredLT:
		predRaw = curParam < int32(d.OperandVal)
	case PredRANGE:
		lo16 := int32(int16(uint16(d.OperandVal & 0xFFFF)))
		hi16 := int32(int16(uint16((d.OperandVal >> 16) & 0xFFFF)))
		predRaw = curParam >= lo16 && curParam <= hi16
	case PredBITMASK:
		predRaw = (paramU32 & d.OperandVal) != 0
	case PredUGT:
		predRaw = paramU32 > d.OperandVal
	default:
		predRaw = false
	}

	assumpKnown := (d.GuardFlags & GuardAssumptionEn) != 0
	assumpTrue := predRaw
	if (d.GuardFlags & GuardInvertAssumption) != 0 {
		assumpTrue = !predRaw
	}
	return assumpKnown && assumpTrue
}

// EvalAction computes (candidateW0, actionValid, arithOverflow) using modular uint32 arithmetic.
func (e *BRAM64Engine) EvalAction(d ConceptDescriptor, curW0, curParam int32) (int32, bool, bool) {
	curU32 := uint32(curW0)
	paramU32 := uint32(curParam)
	actionValid := true
	arithOverflow := false
	var candU32 uint32

	switch d.ActionOpcode {
	case ActAssign:
		candU32 = paramU32
	case ActInc:
		candU32 = curU32 + 1
		arithOverflow = curU32 == 0x7FFFFFFF
	case ActDec:
		candU32 = curU32 - 1
		arithOverflow = curU32 == 0x80000000
	case ActAdd:
		candU32 = curU32 + d.OperandVal
		arithOverflow = (((curU32 ^ d.OperandVal) & 0x80000000) == 0) && (((candU32 ^ curU32) & 0x80000000) != 0)
	case ActSub:
		candU32 = curU32 - d.OperandVal
		arithOverflow = (((curU32 ^ d.OperandVal) & 0x80000000) != 0) && (((candU32 ^ curU32) & 0x80000000) != 0)
	case ActNOP:
		candU32 = curU32
	default:
		candU32 = curU32
		actionValid = false
	}

	return int32(candU32), actionValid, arithOverflow
}

// EvalInvariantGate evaluates the Big Dot (`•`) invariant & hazard gate (`kpol_txn_gate_v2.sv`).
func (e *BRAM64Engine) EvalInvariantGate(d ConceptDescriptor, candI32, curParam int32, actionValid, arithOverflow bool) bool {
	invKnown := (d.GuardFlags & GuardInvariantEn) != 0
	candU32 := uint32(candI32)
	invTrue := (!arithOverflow) && ((candU32 & 0x80000000) == 0)
	hazTrue := ((d.GuardFlags & GuardHazardEn) != 0) && (d.HazardLimit != 0) && (curParam > int32(d.HazardLimit))
	return actionValid && invKnown && invTrue && (!hazTrue)
}

func (e *BRAM64Engine) resolveSubscriber(d ConceptDescriptor) (*int, bool) {
	subValid := d.SubscriberCID < 64
	subEn := ((d.GuardFlags & GuardSubscriberEn) != 0) || (d.SubscriberCID != 0)
	if !(subValid && subEn) {
		return nil, false
	}
	nextCID := int(d.SubscriberCID & 0x3F)
	if nextCID == d.CID {
		return nil, true
	}
	return &nextCID, false
}

// StepEvent executes one external stimulus and traces every resulting cascade step (up to depth 64).
func (e *BRAM64Engine) StepEvent(rootCID int, param int32, paramValid bool) []CascadeTraceStep {
	if e.HaltedOnBreakpoint && e.StopOnBreakpoint {
		return nil
	}

	eventID := e.EventCounter
	e.EventCounter++

	if rootCID < 0 || rootCID >= 64 {
		e.EventsProcessed++
		e.Rejects++
		e.FaultPropagations++
		stepIdx := len(e.Steps)
		var reasons []string
		if e.BreakOnReject {
			reasons = append(reasons, "BREAK_ON_REJECT(BAD_CID)")
		}
		badStep := CascadeTraceStep{
			StepIndex:      stepIdx,
			EventID:        eventID,
			CascadeStep:    0,
			Depth:          0,
			CID:            rootCID,
			ConceptName:    fmt.Sprintf("INVALID_CID_%d", rootCID),
			ConceptType:    "Int32",
			Param:          param,
			ParamValid:     paramValid,
			PreW0:          0,
			PreValid:       false,
			PredFormula:    "N/A",
			PredMatch:      false,
			ActionFormula:  "N/A",
			CandidateW0:    0,
			ArithOverflow:  false,
			InvFormula:     "cid in 0..63",
			InvOK:          false,
			Verdict:        VerdictRejectFault,
			PostW0:         0,
			PostValid:      false,
			WatchpointsHit: reasons,
		}
		e.Steps = append(e.Steps, badStep)
		for _, r := range reasons {
			e.WatchpointTriggers = append(e.WatchpointTriggers, WatchpointTrigger{
				StepIndex:    stepIdx,
				EventID:      eventID,
				CascadeDepth: 0,
				CID:          rootCID,
				ConceptName:  badStep.ConceptName,
				Reason:       r,
				Verdict:      VerdictRejectFault,
				PreW0:        0,
				PostW0:       0,
				Param:        param,
				ParamValid:   paramValid,
			})
		}
		if len(reasons) > 0 && e.StopOnBreakpoint {
			e.HaltedOnBreakpoint = true
		}
		return []CascadeTraceStep{badStep}
	}

	var waveSteps []CascadeTraceStep
	cid := rootCID
	curParam := param
	curValid := paramValid
	descs := e.Descriptors()

	for depth := 0; depth < 64; depth++ {
		d := descs[cid]
		stepIdx := len(e.Steps)
		e.EventsProcessed++

		preW0 := e.State[cid]
		preValid := ((e.ValidMask >> uint(cid)) & 1) != 0

		predFormula := DecodePredicateFormula(d)
		actFormula := DecodeActionFormula(d)
		invFormula := DecodeInvariantFormula(d)

		candW0, actionValid, arithOvf := e.EvalAction(d, preW0, curParam)
		predMatch := e.EvalPredicate(d, curParam)
		invOK := e.EvalInvariantGate(d, candW0, curParam, actionValid, arithOvf)

		var enqueuedCID *int
		var enqueuedName *string
		var verdict string
		var postW0 int32
		var postValid bool

		// Phase 1: Fail-Closed Uncertainty '_' / Sensor Fault Check
		isUncertaintyFault := (!curValid) || (!preValid)
		if isUncertaintyFault {
			verdict = VerdictRejectFault
			predMatch = false
			invOK = false
			postW0 = preW0
			postValid = preValid
			e.Rejects++
			e.FaultPropagations++
		} else if !predMatch {
			// Phase 2: Guard / Assumption '::' Rejected
			verdict = VerdictRejectGuard
			postW0 = preW0
			postValid = preValid
			e.Rejects++
		} else if !invOK {
			// Phase 3: Big Dot '•' Invariant / Hazard Gate Rejected (Fail-Closed!)
			verdict = VerdictRejectInvariant
			postW0 = preW0
			postValid = preValid
			e.Rejects++
		} else {
			// Phase 4: Commit State & Resolve Subscriber W3
			postW0 = candW0
			postValid = preValid
			e.State[cid] = postW0
			descs[cid].CurrentState = uint32(postW0)
			e.Commits++
			e.LastCommittedState = postW0
			var suppressedSelf bool
			enqueuedCID, suppressedSelf = e.resolveSubscriber(d)
			if suppressedSelf {
				verdict = VerdictSuppressedSelf
			} else {
				verdict = VerdictCommit
			}
			if enqueuedCID != nil {
				nm := descs[*enqueuedCID].Name
				enqueuedName = &nm
			}
		}

		var hitReasons []string
		if e.WatchCIDs[cid] {
			hitReasons = append(hitReasons, fmt.Sprintf("WATCH_CID(C%d:%s)", cid, d.Name))
		}
		if e.BreakOnReject && (verdict == VerdictRejectGuard || verdict == VerdictRejectInvariant || verdict == VerdictRejectFault) {
			hitReasons = append(hitReasons, fmt.Sprintf("BREAK_ON_REJECT(%s)", verdict))
		}
		if e.WatchStateChange && postW0 != preW0 {
			hitReasons = append(hitReasons, fmt.Sprintf("STATE_CHANGE(%d->%d)", preW0, postW0))
		}
		if thr, ok := e.ThresholdWatch[cid]; ok {
			if postW0 >= thr && preW0 < thr {
				hitReasons = append(hitReasons, fmt.Sprintf("THRESHOLD_REACHED(C%d>=%d)", cid, thr))
			}
		}

		stepRecord := CascadeTraceStep{
			StepIndex:              stepIdx,
			EventID:                eventID,
			CascadeStep:            depth,
			Depth:                  depth,
			CID:                    cid,
			ConceptName:            d.Name,
			ConceptType:            "Int32",
			Param:                  curParam,
			ParamValid:             curValid,
			PreW0:                  preW0,
			PreValid:               preValid,
			PredFormula:            predFormula,
			PredMatch:              predMatch,
			ActionFormula:          actFormula,
			CandidateW0:            candW0,
			ArithOverflow:          arithOvf,
			InvFormula:             invFormula,
			InvOK:                  invOK,
			Verdict:                verdict,
			PostW0:                 postW0,
			PostValid:              postValid,
			EnqueuedSubscriberCID:  enqueuedCID,
			EnqueuedSubscriberName: enqueuedName,
			WatchpointsHit:         hitReasons,
		}
		e.Steps = append(e.Steps, stepRecord)
		waveSteps = append(waveSteps, stepRecord)

		for _, r := range hitReasons {
			e.WatchpointTriggers = append(e.WatchpointTriggers, WatchpointTrigger{
				StepIndex:    stepIdx,
				EventID:      eventID,
				CascadeDepth: depth,
				CID:          cid,
				ConceptName:  d.Name,
				Reason:       r,
				Verdict:      verdict,
				PreW0:        preW0,
				PostW0:       postW0,
				Param:        curParam,
				ParamValid:   curValid,
			})
		}

		if len(hitReasons) > 0 && e.StopOnBreakpoint {
			e.HaltedOnBreakpoint = true
			break
		}

		if enqueuedCID != nil {
			cid = *enqueuedCID
			curParam = postW0
			curValid = postValid
		} else {
			break
		}
	}

	return waveSteps
}
