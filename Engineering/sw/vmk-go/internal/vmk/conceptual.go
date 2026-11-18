package vmk

import (
	"fmt"
	"math"
	"strconv"
	"strings"
)

// AddressingKind represents the 4 canonical addressing modes of the Kuzmin Machine (RFC-001..018).
type AddressingKind string

const (
	AddrWrite AddressingKind = "←" // Write addressing
	AddrRead  AddressingKind = "→" // Read addressing
	AddrExec  AddressingKind = "|" // Execute / Call addressing
	AddrInit  AddressingKind = ":" // Init / Instance addressing
)

// ConceptValueType identifies the runtime type of a Conceptual VMK concept.
type ConceptValueType string

const (
	TypeBool    ConceptValueType = "?"
	TypeInt32   ConceptValueType = "Int32"
	TypeU64     ConceptValueType = "U64"
	TypeFloat64 ConceptValueType = "Float"
	TypeClass   ConceptValueType = "Class"
	TypeStream  ConceptValueType = "Stream"
)

// ConceptualSlot represents a rich typed concept in `--mode conceptual` (RFC-001..018).
type ConceptualSlot struct {
	CID          int              `json:"cid"`
	Name         string           `json:"name"`
	Type         ConceptValueType `json:"type"`
	Valid        bool             `json:"valid"`
	InitValid    bool             `json:"init_valid"`
	BoolVal      bool             `json:"bool_val"`
	InitBool     bool             `json:"init_bool"`
	IntVal       int64            `json:"int_val"`
	InitInt      int64            `json:"init_int"`
	FloatVal     float64          `json:"float_val"`
	InitFloat    float64          `json:"init_float"`
	Busy         bool             `json:"busy"`
	RuleSummary  string           `json:"rule_summary"`
	GateSummary  string           `json:"gate_summary"`
	SubSummary   string           `json:"sub_summary"`
	PostReadZero bool             `json:"post_read_zero"`
}

// FormatValue returns the Author-notation representation of the concept's current value:
// `_` if !Valid; `!` / `¬` for `?` (Bool); integer or float string otherwise.
func (s ConceptualSlot) FormatValue() string {
	if !s.Valid {
		return "_"
	}
	switch s.Type {
	case TypeBool:
		if s.BoolVal {
			return "!"
		}
		return "¬"
	case TypeFloat64:
		if s.FloatVal == math.Trunc(s.FloatVal) {
			return fmt.Sprintf("%.0f", s.FloatVal)
		}
		return strconv.FormatFloat(s.FloatVal, 'f', -1, 64)
	default:
		return strconv.FormatInt(s.IntVal, 10)
	}
}

// FormatInitValue returns the Author-notation representation of the concept's initial post-load value.
func (s ConceptualSlot) FormatInitValue() string {
	if !s.InitValid {
		return "_"
	}
	switch s.Type {
	case TypeBool:
		if s.InitBool {
			return "!"
		}
		return "¬"
	case TypeFloat64:
		if s.InitFloat == math.Trunc(s.InitFloat) {
			return fmt.Sprintf("%.0f", s.InitFloat)
		}
		return strconv.FormatFloat(s.InitFloat, 'f', -1, 64)
	default:
		return strconv.FormatInt(s.InitInt, 10)
	}
}

// ConceptualVM implements the educational/conceptual Virtual Machine of Kuzmin (RFC-001..018).
type ConceptualVM struct {
	ProgramName        string
	SourceCode         string
	Capacity           int
	PreLoadActive      int
	Slots              []ConceptualSlot
	NameToCID          map[string]int
	StdinHistory       []string
	StdoutHistory      []string
	StderrHistory      []string
	Steps              []CascadeTraceStep
	EventsProcessed    uint32
	Commits            uint32
	Rejects            uint32
	FaultPropagations  uint32
	LastCommittedState int32
	EventCounter       int
}

// NewConceptualVM creates a ConceptualVM with built-in virtual stream concepts STDIN, STDOUT, STDERR.
func NewConceptualVM(programName, sourceCode string, slots []ConceptualSlot) *ConceptualVM {
	vm := &ConceptualVM{
		ProgramName:   programName,
		SourceCode:    strings.TrimSpace(sourceCode),
		Capacity:      64,
		PreLoadActive: 3, // Built-in STDIN, STDOUT, STDERR before user program load
		NameToCID:     make(map[string]int),
	}
	for i := range slots {
		slots[i].CID = i
		slots[i].InitValid = slots[i].Valid
		slots[i].InitBool = slots[i].BoolVal
		slots[i].InitInt = slots[i].IntVal
		slots[i].InitFloat = slots[i].FloatVal
		vm.Slots = append(vm.Slots, slots[i])
		vm.NameToCID[strings.ToLower(slots[i].Name)] = i
	}
	// Built-in virtual stream concepts (STDIN, STDOUT, STDERR)
	streamNames := []string{"STDIN", "STDOUT", "STDERR"}
	for _, sn := range streamNames {
		if _, exists := vm.NameToCID[strings.ToLower(sn)]; !exists {
			cid := len(vm.Slots)
			slot := ConceptualSlot{
				CID:         cid,
				Name:        sn,
				Type:        TypeStream,
				Valid:       true,
				InitValid:   true,
				RuleSummary: "Virtual STDIO Stream",
				GateSummary: "•(Stream)",
				SubSummary:  "Host OS Pipe",
			}
			vm.Slots = append(vm.Slots, slot)
			vm.NameToCID[strings.ToLower(sn)] = cid
		}
	}
	return vm
}

// Reset restores all ConceptualVM slots to their post-load initial values and clears histories/counters.
func (vm *ConceptualVM) Reset() {
	for i := range vm.Slots {
		vm.Slots[i].Valid = vm.Slots[i].InitValid
		vm.Slots[i].BoolVal = vm.Slots[i].InitBool
		vm.Slots[i].IntVal = vm.Slots[i].InitInt
		vm.Slots[i].FloatVal = vm.Slots[i].InitFloat
		vm.Slots[i].Busy = false
	}
	vm.StdinHistory = nil
	vm.StdoutHistory = nil
	vm.StderrHistory = nil
	vm.Steps = nil
	vm.EventsProcessed = 0
	vm.Commits = 0
	vm.Rejects = 0
	vm.FaultPropagations = 0
	vm.LastCommittedState = 0
	vm.EventCounter = 0
}

// ModifySlotState updates a ConceptualVM slot's live value and validity bit '_' (What-If editor).
func (vm *ConceptualVM) ModifySlotState(cid int, rawVal string, valid bool) error {
	if cid < 0 || cid >= len(vm.Slots) {
		return fmt.Errorf("VMK-MOD-CID: invalid conceptual CID %d", cid)
	}
	slot := &vm.Slots[cid]
	valClean := strings.TrimSpace(rawVal)
	if !valid || valClean == "_" || strings.EqualFold(valClean, "undef") || strings.EqualFold(valClean, "invalid") {
		slot.Valid = false
		return nil
	}
	slot.Valid = true
	switch slot.Type {
	case TypeBool:
		switch strings.ToLower(valClean) {
		case "!", "true", "0":
			slot.BoolVal = true
			slot.IntVal = 0
		case "¬", "~false", "false", "1":
			slot.BoolVal = false
			slot.IntVal = 1
		default:
			return fmt.Errorf("VMK-MOD-VAL: invalid Bool value %q (expected !, ¬, true, or false)", valClean)
		}
	case TypeFloat64:
		fv, err := strconv.ParseFloat(valClean, 64)
		if err != nil {
			return fmt.Errorf("VMK-MOD-VAL: invalid Float value %q", valClean)
		}
		slot.FloatVal = fv
		slot.IntVal = int64(fv)
	default:
		iv, err := strconv.ParseInt(valClean, 0, 64)
		if err != nil {
			return fmt.Errorf("VMK-MOD-VAL: invalid integer value %q", valClean)
		}
		slot.IntVal = iv
		slot.FloatVal = float64(iv)
	}
	return nil
}

// ExecuteGenericWrite executes a write/stimulus or fault '_' on any ConceptualVM slot.
func (vm *ConceptualVM) ExecuteGenericWrite(cid int, param int32, valid bool) CascadeTraceStep {
	if cid < 0 || cid >= len(vm.Slots) {
		cid = 0
	}
	slot := &vm.Slots[cid]
	lowName := strings.ToLower(slot.Name)
	if lowName == "if" && valid {
		return vm.ExecuteIfToggleImpulse()
	}
	if lowName == "sum" {
		return vm.ExecuteSumWrite(float64(param), valid)
	}

	evID := vm.EventCounter
	vm.EventCounter++
	vm.EventsProcessed++
	preStr := slot.FormatValue()
	preW0 := int32(slot.IntVal)

	if !valid {
		vm.Rejects++
		vm.FaultPropagations++
		errMsg := fmt.Sprintf("REJECT_FAULT: %s[cid=%d] kept %s (input valid=_)", slot.Name, cid, preStr)
		vm.StderrHistory = append(vm.StderrHistory, errMsg)
		st := CascadeTraceStep{
			StepIndex:     len(vm.Steps),
			EventID:       evID,
			CascadeStep:   0,
			Depth:         0,
			CID:           cid,
			ConceptName:   slot.Name,
			ConceptType:   string(slot.Type),
			EventDisplay:  fmt.Sprintf("Go %s ← _", slot.Name),
			PreDisplay:    preStr,
			PostDisplay:   preStr,
			Param:         0,
			ParamValid:    false,
			PreW0:         preW0,
			PreValid:      slot.Valid,
			PredFormula:   "Valid != _ => false",
			PredMatch:     false,
			ActionFormula: "N/A",
			CandidateW0:   preW0,
			InvFormula:    "•(Valid != _)",
			InvOK:         false,
			Verdict:       VerdictRejectFault,
			PostW0:        preW0,
			PostValid:     slot.Valid,
		}
		vm.Steps = append(vm.Steps, st)
		return st
	}

	slot.Valid = true
	switch slot.Type {
	case TypeBool:
		slot.BoolVal = param != 0
		if slot.BoolVal {
			slot.IntVal = 0
		} else {
			slot.IntVal = 1
		}
	case TypeFloat64:
		slot.FloatVal = float64(param)
		slot.IntVal = int64(param)
	default:
		slot.IntVal = int64(param)
		slot.FloatVal = float64(param)
	}
	postStr := slot.FormatValue()
	postW0 := int32(slot.IntVal)
	vm.Commits++
	vm.LastCommittedState = postW0
	msg := fmt.Sprintf("COMMIT: %s[cid=%d] = %s (pre=%s, ← := %d)", slot.Name, cid, postStr, preStr, param)
	vm.StdoutHistory = append(vm.StdoutHistory, msg)
	st := CascadeTraceStep{
		StepIndex:     len(vm.Steps),
		EventID:       evID,
		CascadeStep:   0,
		Depth:         0,
		CID:           cid,
		ConceptName:   slot.Name,
		ConceptType:   string(slot.Type),
		EventDisplay:  fmt.Sprintf("Go %s ← %d", slot.Name, param),
		PreDisplay:    preStr,
		PostDisplay:   postStr,
		Param:         param,
		ParamValid:    true,
		PreW0:         preW0,
		PreValid:      true,
		PredFormula:   "← write => true",
		PredMatch:     true,
		ActionFormula: fmt.Sprintf("%s := %d => %s", slot.Name, param, postStr),
		CandidateW0:   postW0,
		InvFormula:    "•(Conceptual Gate)",
		InvOK:         true,
		Verdict:       VerdictCommit,
		PostW0:        postW0,
		PostValid:     true,
	}
	vm.Steps = append(vm.Steps, st)
	return st
}

// ExecuteIfToggleImpulse executes one `Go If ←` write impulse on the T-flip-flop `If` (`? If _ ; ! If = ¬ ; ¬ = !`),
// enforcing RFC-001 Busy lock so that writing `If` inside `If`'s subscription does not oscillate infinitely.
func (vm *ConceptualVM) ExecuteIfToggleImpulse() CascadeTraceStep {
	cid := vm.NameToCID["if"]
	slot := &vm.Slots[cid]
	evID := vm.EventCounter
	vm.EventCounter++
	vm.EventsProcessed++

	preStr := slot.FormatValue()
	preValid := slot.Valid
	preW0 := int32(-1)
	if slot.Valid {
		if slot.BoolVal {
			preW0 = 0 // Author slide 4: ! (True) has code 0
		} else {
			preW0 = 1 // ¬ (False) has code 1
		}
	}

	// RFC-001 Busy lock prevents recursive self-retriggering within the same wave
	slot.Busy = true
	var predFormula, actFormula string
	if !slot.Valid {
		predFormula = "If :: _ => true"
		actFormula = "If ← ! (Busy=1 suppresses re-trigger)"
		slot.Valid = true
		slot.BoolVal = true
	} else if slot.BoolVal {
		predFormula = "If :: ! => true"
		actFormula = "If ← ¬ (Busy=1 suppresses re-trigger)"
		slot.BoolVal = false
	} else {
		predFormula = "If :: ¬ => true"
		actFormula = "If ← ! (Busy=1 suppresses re-trigger)"
		slot.BoolVal = true
	}
	slot.Busy = false

	postStr := slot.FormatValue()
	postW0 := int32(1)
	if slot.BoolVal {
		postW0 = 0
	}
	slot.IntVal = int64(postW0)
	vm.Commits++
	vm.LastCommittedState = postW0

	msg := fmt.Sprintf("COMMIT: If[cid=%d] = %s (pre=%s, RFC-001 Busy=self_suppress)", cid, postStr, preStr)
	vm.StdoutHistory = append(vm.StdoutHistory, msg)

	step := CascadeTraceStep{
		StepIndex:     len(vm.Steps),
		EventID:       evID,
		CascadeStep:   0,
		Depth:         0,
		CID:           cid,
		ConceptName:   slot.Name,
		ConceptType:   string(slot.Type),
		EventDisplay:  "Go If ← (Write)",
		PreDisplay:    preStr,
		PostDisplay:   postStr,
		Param:         1,
		ParamValid:    true,
		PreW0:         preW0,
		PreValid:      preValid,
		PredFormula:   predFormula,
		PredMatch:     true,
		ActionFormula: actFormula,
		CandidateW0:   postW0,
		InvFormula:    "•(RFC-001 Busy lock)",
		InvOK:         true,
		Verdict:       VerdictSuppressedSelf,
		PostW0:        postW0,
		PostValid:     true,
	}
	vm.Steps = append(vm.Steps, step)
	return step
}

// ExecuteSumWrite executes `Go Sum ← x` (`← += x`) on the `Sum` accumulator.
func (vm *ConceptualVM) ExecuteSumWrite(x float64, valid bool) CascadeTraceStep {
	cid := vm.NameToCID["sum"]
	slot := &vm.Slots[cid]
	evID := vm.EventCounter
	vm.EventCounter++
	vm.EventsProcessed++

	preStr := slot.FormatValue()
	preW0 := int32(slot.FloatVal)

	if !valid || !slot.Valid {
		vm.Rejects++
		vm.FaultPropagations++
		errMsg := fmt.Sprintf("REJECT_FAULT: Sum[cid=%d] kept %s (input valid=_)", cid, preStr)
		vm.StderrHistory = append(vm.StderrHistory, errMsg)
		step := CascadeTraceStep{
			StepIndex:     len(vm.Steps),
			EventID:       evID,
			CascadeStep:   0,
			Depth:         0,
			CID:           cid,
			ConceptName:   slot.Name,
			ConceptType:   string(slot.Type),
			EventDisplay:  "Go Sum ← _",
			PreDisplay:    preStr,
			PostDisplay:   preStr,
			Param:         0,
			ParamValid:    false,
			PreW0:         preW0,
			PreValid:      slot.Valid,
			PredFormula:   "← @ Float x",
			PredMatch:     false,
			ActionFormula: "Sum += x",
			CandidateW0:   preW0,
			InvFormula:    "•(Valid != _)",
			InvOK:         false,
			Verdict:       VerdictRejectFault,
			PostW0:        preW0,
			PostValid:     slot.Valid,
		}
		vm.Steps = append(vm.Steps, step)
		return step
	}

	slot.FloatVal += x
	slot.IntVal = int64(slot.FloatVal)
	postStr := slot.FormatValue()
	postW0 := int32(slot.FloatVal)
	vm.Commits++
	vm.LastCommittedState = postW0

	msg := fmt.Sprintf("COMMIT: Sum[cid=%d] = %s (pre=%s, ← += %v)", cid, postStr, preStr, x)
	vm.StdoutHistory = append(vm.StdoutHistory, msg)

	step := CascadeTraceStep{
		StepIndex:     len(vm.Steps),
		EventID:       evID,
		CascadeStep:   0,
		Depth:         0,
		CID:           cid,
		ConceptName:   slot.Name,
		ConceptType:   string(slot.Type),
		EventDisplay:  fmt.Sprintf("Go Sum ← %v", x),
		PreDisplay:    preStr,
		PostDisplay:   postStr,
		Param:         int32(x),
		ParamValid:    true,
		PreW0:         preW0,
		PreValid:      true,
		PredFormula:   "← @ Float x => true",
		PredMatch:     true,
		ActionFormula: fmt.Sprintf("Sum += %v => %s", x, postStr),
		CandidateW0:   postW0,
		InvFormula:    "•(finite Float)",
		InvOK:         true,
		Verdict:       VerdictCommit,
		PostW0:        postW0,
		PostValid:     true,
	}
	vm.Steps = append(vm.Steps, step)
	return step
}

// ExecuteSumReadWithPostDotReset executes `Go Sum →` with RFC-013 post-addressing Big Dot barrier `→ • Sum = 0`.
// Phase 1 returns the current value to the reader/STDOUT; Phase 2 (after `•`) resets `Sum = 0`.
func (vm *ConceptualVM) ExecuteSumReadWithPostDotReset() (float64, float64, CascadeTraceStep) {
	cid := vm.NameToCID["sum"]
	slot := &vm.Slots[cid]
	evID := vm.EventCounter
	vm.EventCounter++
	vm.EventsProcessed++

	preStr := slot.FormatValue()
	preW0 := int32(slot.FloatVal)

	// RFC-013 Post-Read Big DotBarrier (`→ • Sum = 0`):
	// Step 1: Read bus captures current value BEFORE post-dot reset
	readReturnedVal := slot.FloatVal
	if slot.PostReadZero {
		slot.FloatVal = 0
		slot.IntVal = 0
	}
	postAfterDot := slot.FloatVal
	postStr := slot.FormatValue()
	postW0 := int32(postAfterDot)

	vm.Commits++
	vm.LastCommittedState = postW0
	readMsg := fmt.Sprintf("READ: Sum = %v (post-dot → • reset Sum = %s)", readReturnedVal, postStr)
	vm.StdoutHistory = append(vm.StdoutHistory, readMsg)

	step := CascadeTraceStep{
		StepIndex:     len(vm.Steps),
		EventID:       evID,
		CascadeStep:   0,
		Depth:         0,
		CID:           cid,
		ConceptName:   slot.Name,
		ConceptType:   string(slot.Type),
		EventDisplay:  "Go Sum → •",
		PreDisplay:    preStr,
		PostDisplay:   fmt.Sprintf("%s (Read=%v)", postStr, readReturnedVal),
		Param:         preW0,
		ParamValid:    true,
		PreW0:         preW0,
		PreValid:      true,
		PredFormula:   "→ (Read phase 1) => true",
		PredMatch:     true,
		ActionFormula: fmt.Sprintf("STDOUT ← %v; • Sum := 0", readReturnedVal),
		CandidateW0:   postW0,
		InvFormula:    "•(RFC-013 Post-Read Barrier)",
		InvOK:         true,
		Verdict:       VerdictCommit,
		PostW0:        postW0,
		PostValid:     true,
	}
	vm.Steps = append(vm.Steps, step)
	return readReturnedVal, postAfterDot, step
}

// ExecuteNodCall executes `U64 Nod | @ U64 ( a_ > b -=b , b_ > a -=a ) =a` for `Nod(aInit, bInit)`.
func (vm *ConceptualVM) ExecuteNodCall(aInit, bInit int64) (int64, int, []CascadeTraceStep) {
	cidA := vm.NameToCID["a"]
	cidB := vm.NameToCID["b"]
	cidNod := vm.NameToCID["nod"]

	vm.Slots[cidA].IntVal = aInit
	vm.Slots[cidA].Valid = aInit > 0
	vm.Slots[cidB].IntVal = bInit
	vm.Slots[cidB].Valid = bInit > 0

	evID := vm.EventCounter
	vm.EventCounter++

	var waveSteps []CascadeTraceStep
	a := aInit
	b := bInit
	subSteps := 0

	for a != b && subSteps < 1024 {
		subSteps++
		vm.EventsProcessed++
		preDisp := fmt.Sprintf("a=%d, b=%d", a, b)
		if a > b {
			nextA := a - b
			postDisp := fmt.Sprintf("a=%d, b=%d", nextA, b)
			vm.Slots[cidA].IntVal = nextA
			vm.Commits++
			vm.LastCommittedState = int32(nextA)
			bName := "b"
			st := CascadeTraceStep{
				StepIndex:              len(vm.Steps),
				EventID:                evID,
				CascadeStep:            subSteps - 1,
				Depth:                  subSteps - 1,
				CID:                    cidA,
				ConceptName:            "a",
				ConceptType:            "U64",
				EventDisplay:           fmt.Sprintf("Wave #%d (a=%d,b=%d)", subSteps, a, b),
				PreDisplay:             preDisp,
				PostDisplay:            postDisp,
				Param:                  int32(b),
				ParamValid:             true,
				PreW0:                  int32(a),
				PreValid:               true,
				PredFormula:            fmt.Sprintf("a > b (%d > %d)", a, b),
				PredMatch:              true,
				ActionFormula:          fmt.Sprintf("a -= b => %d", nextA),
				CandidateW0:            int32(nextA),
				InvFormula:             "•(a > 0)",
				InvOK:                  true,
				Verdict:                VerdictCommit,
				PostW0:                 int32(nextA),
				PostValid:              true,
				EnqueuedSubscriberCID:  &cidB,
				EnqueuedSubscriberName: &bName,
			}
			vm.Steps = append(vm.Steps, st)
			waveSteps = append(waveSteps, st)
			a = nextA
		} else {
			nextB := b - a
			postDisp := fmt.Sprintf("a=%d, b=%d", a, nextB)
			vm.Slots[cidB].IntVal = nextB
			vm.Commits++
			vm.LastCommittedState = int32(nextB)
			aName := "a"
			st := CascadeTraceStep{
				StepIndex:              len(vm.Steps),
				EventID:                evID,
				CascadeStep:            subSteps - 1,
				Depth:                  subSteps - 1,
				CID:                    cidB,
				ConceptName:            "b",
				ConceptType:            "U64",
				EventDisplay:           fmt.Sprintf("Wave #%d (a=%d,b=%d)", subSteps, a, b),
				PreDisplay:             preDisp,
				PostDisplay:            postDisp,
				Param:                  int32(a),
				ParamValid:             true,
				PreW0:                  int32(b),
				PreValid:               true,
				PredFormula:            fmt.Sprintf("b > a (%d > %d)", b, a),
				PredMatch:              true,
				ActionFormula:          fmt.Sprintf("b -= a => %d", nextB),
				CandidateW0:            int32(nextB),
				InvFormula:             "•(b > 0)",
				InvOK:                  true,
				Verdict:                VerdictCommit,
				PostW0:                 int32(nextB),
				PostValid:              true,
				EnqueuedSubscriberCID:  &cidA,
				EnqueuedSubscriberName: &aName,
			}
			vm.Steps = append(vm.Steps, st)
			waveSteps = append(waveSteps, st)
			b = nextB
		}
	}

	// Final convergence step: a == b, both predicates false -> wave extinguishes and returns =a
	vm.EventsProcessed++
	vm.Slots[cidNod].IntVal = a
	vm.Slots[cidNod].Valid = true
	vm.Commits++
	vm.LastCommittedState = int32(a)
	convStep := CascadeTraceStep{
		StepIndex:     len(vm.Steps),
		EventID:       evID,
		CascadeStep:   subSteps,
		Depth:         subSteps,
		CID:           cidNod,
		ConceptName:   "Nod",
		ConceptType:   "U64",
		EventDisplay:  fmt.Sprintf("Converged (a==b==%d)", a),
		PreDisplay:    fmt.Sprintf("a=%d, b=%d", a, b),
		PostDisplay:   fmt.Sprintf("Nod=%d", a),
		Param:         int32(a),
		ParamValid:    true,
		PreW0:         int32(a),
		PreValid:      true,
		PredFormula:   "a > b (false) && b > a (false)",
		PredMatch:     true,
		ActionFormula: fmt.Sprintf("Return =a (%d)", a),
		CandidateW0:   int32(a),
		InvFormula:    "•(Wave extinguished)",
		InvOK:         true,
		Verdict:       VerdictCommit,
		PostW0:        int32(a),
		PostValid:     true,
	}
	vm.Steps = append(vm.Steps, convStep)
	waveSteps = append(waveSteps, convStep)

	msg := fmt.Sprintf("COMMIT: Nod[cid=%d] = %d (a_init=%d, b_init=%d, sub_steps=%d, total_steps=%d)", cidNod, a, aInit, bInit, subSteps, subSteps+1)
	vm.StdoutHistory = append(vm.StdoutHistory, msg)
	return a, subSteps, waveSteps
}

// ExecuteFactorialCall executes `U64 Factorial | @ U64 n [ 0 1 ] { Factorial = 1 Exit } = Factorial(n - 1) * n`.
func (vm *ConceptualVM) ExecuteFactorialCall(n int64) (int64, []CascadeTraceStep) {
	cidN := vm.NameToCID["n"]
	cidFact := vm.NameToCID["factorial"]
	evID := vm.EventCounter
	vm.EventCounter++

	if n < 0 {
		vm.EventsProcessed++
		vm.Rejects++
		errMsg := fmt.Sprintf("REJECT_GUARD: Factorial[cid=%d] invalid negative n=%d", cidFact, n)
		vm.StderrHistory = append(vm.StderrHistory, errMsg)
		st := CascadeTraceStep{
			StepIndex:     len(vm.Steps),
			EventID:       evID,
			CascadeStep:   0,
			Depth:         0,
			CID:           cidFact,
			ConceptName:   "Factorial",
			ConceptType:   "U64",
			EventDisplay:  fmt.Sprintf("Factorial | %d", n),
			PreDisplay:    vm.Slots[cidFact].FormatValue(),
			PostDisplay:   vm.Slots[cidFact].FormatValue(),
			Param:         int32(n),
			ParamValid:    true,
			PredFormula:   "n >= 0 => false",
			PredMatch:     false,
			ActionFormula: "N/A",
			InvFormula:    "•(U64 >= 0)",
			InvOK:         false,
			Verdict:       VerdictRejectGuard,
		}
		vm.Steps = append(vm.Steps, st)
		return 0, []CascadeTraceStep{st}
	}

	var waveSteps []CascadeTraceStep
	// Trace descent to base case n in [ 0 1 ] -> { Factorial = 1 Exit } and ascent multiplication
	acc := int64(1)
	depth := 0
	for k := n; k >= 1; k-- {
		vm.EventsProcessed++
		vm.Slots[cidN].IntVal = k
		vm.Slots[cidN].Valid = true
		if k == 1 || k == 0 {
			vm.Slots[cidFact].IntVal = 1
			vm.Slots[cidFact].Valid = true
			vm.Commits++
			st := CascadeTraceStep{
				StepIndex:     len(vm.Steps),
				EventID:       evID,
				CascadeStep:   depth,
				Depth:         depth,
				CID:           cidFact,
				ConceptName:   "Factorial",
				ConceptType:   "U64",
				EventDisplay:  fmt.Sprintf("Call | n=%d", k),
				PreDisplay:    fmt.Sprintf("n=%d", k),
				PostDisplay:   "Factorial=1 (Exit)",
				Param:         int32(k),
				ParamValid:    true,
				PreW0:         int32(k),
				PreValid:      true,
				PredFormula:   fmt.Sprintf("n [ 0 1 ] (n=%d) => true", k),
				PredMatch:     true,
				ActionFormula: "{ Factorial = 1; Exit }",
				CandidateW0:   1,
				InvFormula:    "•(Base case Exit)",
				InvOK:         true,
				Verdict:       VerdictCommit,
				PostW0:        1,
				PostValid:     true,
			}
			vm.Steps = append(vm.Steps, st)
			waveSteps = append(waveSteps, st)
			depth++
			break
		}
		fName := "Factorial"
		st := CascadeTraceStep{
			StepIndex:              len(vm.Steps),
			EventID:                evID,
			CascadeStep:            depth,
			Depth:                  depth,
			CID:                    cidN,
			ConceptName:            "n",
			ConceptType:            "U64",
			EventDisplay:           fmt.Sprintf("Call | n=%d", k),
			PreDisplay:             fmt.Sprintf("n=%d", k),
			PostDisplay:            fmt.Sprintf("recurse n-1=%d", k-1),
			Param:                  int32(k),
			ParamValid:             true,
			PreW0:                  int32(k),
			PreValid:               true,
			PredFormula:            fmt.Sprintf("n [ 0 1 ] (n=%d) => false", k),
			PredMatch:              true,
			ActionFormula:          fmt.Sprintf("defer * %d; call Factorial(%d)", k, k-1),
			CandidateW0:            int32(k - 1),
			InvFormula:             "•(n > 1)",
			InvOK:                  true,
			Verdict:                VerdictCommit,
			PostW0:                 int32(k - 1),
			PostValid:              true,
			EnqueuedSubscriberCID:  &cidFact,
			EnqueuedSubscriberName: &fName,
		}
		vm.Commits++
		vm.Steps = append(vm.Steps, st)
		waveSteps = append(waveSteps, st)
		depth++
	}

	for k := int64(2); k <= n; k++ {
		vm.EventsProcessed++
		preAcc := acc
		acc = acc * k
		vm.Slots[cidFact].IntVal = acc
		vm.Slots[cidFact].Valid = true
		vm.Commits++
		vm.LastCommittedState = int32(acc)
		st := CascadeTraceStep{
			StepIndex:     len(vm.Steps),
			EventID:       evID,
			CascadeStep:   depth,
			Depth:         depth,
			CID:           cidFact,
			ConceptName:   "Factorial",
			ConceptType:   "U64",
			EventDisplay:  fmt.Sprintf("Return * n=%d", k),
			PreDisplay:    fmt.Sprintf("Factorial=%d", preAcc),
			PostDisplay:   fmt.Sprintf("Factorial=%d", acc),
			Param:         int32(k),
			ParamValid:    true,
			PreW0:         int32(preAcc),
			PreValid:      true,
			PredFormula:   "unwind multiplication => true",
			PredMatch:     true,
			ActionFormula: fmt.Sprintf("Factorial := %d * %d => %d", preAcc, k, acc),
			CandidateW0:   int32(acc),
			InvFormula:    "•(U64 no overflow)",
			InvOK:         true,
			Verdict:       VerdictCommit,
			PostW0:        int32(acc),
			PostValid:     true,
		}
		vm.Steps = append(vm.Steps, st)
		waveSteps = append(waveSteps, st)
		depth++
	}

	msg := fmt.Sprintf("COMMIT: Factorial[cid=%d] = %d (n=%d)", cidFact, acc, n)
	vm.StdoutHistory = append(vm.StdoutHistory, msg)
	return acc, waveSteps
}

// ExecuteTachometerEvent executes either a wheel pulse `Tick` (incrementing Revolutions and Distance += stepM)
// or a timer event `_Tick(dtSec)` (computing Speed = Revolutions * stepM / dtSec and resetting Revolutions = 0).
func (vm *ConceptualVM) ExecuteTachometerEvent(eventKind string, param float64) []CascadeTraceStep {
	cidRev := vm.NameToCID["revolutions"]
	cidDist := vm.NameToCID["distance"]
	cidSpd := vm.NameToCID["speed"]

	evID := vm.EventCounter
	vm.EventCounter++
	var wave []CascadeTraceStep

	const wheelCircumferenceM = 2.0

	if strings.EqualFold(eventKind, "Tick") {
		// Step 1: Revolutions += 1
		vm.EventsProcessed++
		preRev := vm.Slots[cidRev].IntVal
		postRev := preRev + 1
		vm.Slots[cidRev].IntVal = postRev
		vm.Commits++
		distName := "Distance"
		st1 := CascadeTraceStep{
			StepIndex:              len(vm.Steps),
			EventID:                evID,
			CascadeStep:            0,
			Depth:                  0,
			CID:                    cidRev,
			ConceptName:            "Revolutions",
			ConceptType:            "U64",
			EventDisplay:           "Tick ← 1",
			PreDisplay:             strconv.FormatInt(preRev, 10),
			PostDisplay:            strconv.FormatInt(postRev, 10),
			Param:                  1,
			ParamValid:             true,
			PreW0:                  int32(preRev),
			PreValid:               true,
			PredFormula:            "on Tick => true",
			PredMatch:              true,
			ActionFormula:          fmt.Sprintf("Revolutions += 1 => %d", postRev),
			CandidateW0:            int32(postRev),
			InvFormula:             "•(Revolutions >= 0)",
			InvOK:                  true,
			Verdict:                VerdictCommit,
			PostW0:                 int32(postRev),
			PostValid:              true,
			EnqueuedSubscriberCID:  &cidDist,
			EnqueuedSubscriberName: &distName,
		}
		vm.Steps = append(vm.Steps, st1)
		wave = append(wave, st1)

		// Step 2: Distance += 2m
		vm.EventsProcessed++
		preDist := vm.Slots[cidDist].FloatVal
		postDist := preDist + wheelCircumferenceM
		vm.Slots[cidDist].FloatVal = postDist
		vm.Slots[cidDist].IntVal = int64(postDist)
		vm.Commits++
		vm.LastCommittedState = int32(postDist)
		st2 := CascadeTraceStep{
			StepIndex:     len(vm.Steps),
			EventID:       evID,
			CascadeStep:   1,
			Depth:         1,
			CID:           cidDist,
			ConceptName:   "Distance",
			ConceptType:   "Float",
			EventDisplay:  "Tick • Distance",
			PreDisplay:    fmt.Sprintf("%.0f", preDist),
			PostDisplay:   fmt.Sprintf("%.0f", postDist),
			Param:         int32(wheelCircumferenceM),
			ParamValid:    true,
			PreW0:         int32(preDist),
			PreValid:      true,
			PredFormula:   "on Tick => true",
			PredMatch:     true,
			ActionFormula: fmt.Sprintf("Distance += 2 => %.0f", postDist),
			CandidateW0:   int32(postDist),
			InvFormula:    "•(Distance >= 0)",
			InvOK:         true,
			Verdict:       VerdictCommit,
			PostW0:        int32(postDist),
			PostValid:     true,
		}
		vm.Steps = append(vm.Steps, st2)
		wave = append(wave, st2)
		vm.StdoutHistory = append(vm.StdoutHistory, fmt.Sprintf("COMMIT: Tachometer.Tick -> Revolutions=%d, Distance=%.0f", postRev, postDist))
		return wave
	}

	// _Tick timer event: Speed = (Revolutions * 2.0) / dtSec; then • Revolutions = 0
	dt := param
	if dt <= 0 {
		dt = 1.0
	}
	vm.EventsProcessed++
	revs := vm.Slots[cidRev].IntVal
	preSpd := vm.Slots[cidSpd].FloatVal
	newSpd := (float64(revs) * wheelCircumferenceM) / dt
	vm.Slots[cidSpd].FloatVal = newSpd
	vm.Slots[cidSpd].IntVal = int64(newSpd)
	vm.Slots[cidRev].IntVal = 0
	vm.Commits++
	vm.LastCommittedState = int32(newSpd)

	st := CascadeTraceStep{
		StepIndex:     len(vm.Steps),
		EventID:       evID,
		CascadeStep:   0,
		Depth:         0,
		CID:           cidSpd,
		ConceptName:   "Speed",
		ConceptType:   "Float",
		EventDisplay:  fmt.Sprintf("_Tick(dt=%.0fs) → •", dt),
		PreDisplay:    fmt.Sprintf("Speed=%.0f, Rev=%d", preSpd, revs),
		PostDisplay:   fmt.Sprintf("Speed=%.0f, Rev=0", newSpd),
		Param:         int32(dt),
		ParamValid:    true,
		PreW0:         int32(preSpd),
		PreValid:      true,
		PredFormula:   "on _Tick timer => true",
		PredMatch:     true,
		ActionFormula: fmt.Sprintf("Speed := (%d * 2) / %.0f => %.0f; • Revolutions := 0", revs, dt, newSpd),
		CandidateW0:   int32(newSpd),
		InvFormula:    "•(RFC-013 Post-Read Revolutions=0)",
		InvOK:         true,
		Verdict:       VerdictCommit,
		PostW0:        int32(newSpd),
		PostValid:     true,
	}
	vm.Steps = append(vm.Steps, st)
	wave = append(wave, st)
	vm.StdoutHistory = append(vm.StdoutHistory, fmt.Sprintf("COMMIT: Tachometer._Tick -> Speed=%.0f, Revolutions=0 (Distance=%.0f)", newSpd, vm.Slots[cidDist].FloatVal))
	return wave
}
