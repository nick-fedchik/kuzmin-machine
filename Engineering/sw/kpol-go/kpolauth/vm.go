package kpolauth

import (
	"fmt"
	"math/big"
)

// DefaultStepLimit is the default bound on the number of subscription lines one
// TriggerExternal call may execute. The reference VM has no bound and does not
// terminate on cascades such as "OnAbort(A) • Assign(A, 1)" with a rejected
// value (decision D-A10); the Go VM reports CodeVMSteps instead.
const DefaultStepLimit = 20000

// Codes of the errors of the reference VM. The reference raises AssertionError,
// IndexError or runs without bound where these are returned.
const (
	// CodeVMSteps: the step limit was exceeded.
	CodeVMSteps = "KPOL-AUTH-VM-STEPS"
	// CodeVMOverflow: a value accepted by the guard does not fit int64.
	CodeVMOverflow = "KPOL-AUTH-VM-OVERFLOW"
	// CodeVMExit: a line ended without EXIT.
	CodeVMExit = "KPOL-AUTH-VM-EXIT"
	// CodeVMOpcode: unexpected opcode or sub-operation.
	CodeVMOpcode = "KPOL-AUTH-VM-OPCODE"
	// CodeVMStack: pop from an empty stack.
	CodeVMStack = "KPOL-AUTH-VM-STACK"
	// CodeVMIndex: concept, subscription or code index out of range.
	CodeVMIndex = "KPOL-AUTH-VM-INDEX"
)

// Machine is the reference Do/Go stack VM (KPA-VM-1..5), a port of
// ReferenceDoGoVM that mirrors km_mcu_fpga_bridge.c without its overflow
// behaviour (D-A11). Stack arithmetic is exact; a value is stored as int64 and
// storing a value outside that range is an error.
type Machine struct {
	// StepLimit bounds the lines executed per TriggerExternal call; zero means
	// DefaultStepLimit.
	StepLimit int

	art      *Artifact
	valCur   []int64
	valPrev  []int64
	bigDotOK []int
	queue    []int
}

// NewMachine creates a VM in the initial state of KPA-VM-1: every concept holds
// its initial value, all "big dot" flags are 0 and the queue is empty. The
// artifact must not be nil.
func NewMachine(a *Artifact) *Machine {
	m := &Machine{art: a}
	m.valCur = make([]int64, len(a.Concepts))
	m.valPrev = make([]int64, len(a.Concepts))
	m.bigDotOK = make([]int, len(a.Concepts))
	for i, c := range a.Concepts {
		m.valCur[i], m.valPrev[i] = c.InitVal, c.InitVal
	}
	return m
}

// Values returns a copy of the current concept values (val_cur).
func (m *Machine) Values() []int64 { return append([]int64(nil), m.valCur...) }

// Previous returns a copy of the values before the last accepted write
// (val_prev).
func (m *Machine) Previous() []int64 { return append([]int64(nil), m.valPrev...) }

// BigDotOK returns a copy of the "big dot" flags: 1 after a write rejected by
// the guard of the concept (the property "•" is false), 0 after an accepted one.
func (m *Machine) BigDotOK() []int { return append([]int(nil), m.bigDotOK...) }

// Queue returns the indices of the subscriptions waiting in the FIFO queue.
func (m *Machine) Queue() []int { return append([]int(nil), m.queue...) }

func vmErr(code, format string, args ...any) *Error {
	return &Error{Code: code, Msg: fmt.Sprintf(format, args...)}
}

// eventVector is _eval_event_vector (KPA-VM-2).
func (m *Machine) eventVector(cid int) int {
	v := m.valCur[cid]
	vec := EvAlways
	switch {
	case v == 0:
		vec |= EvNull
	case v > 0:
		vec |= EvPositive
	default:
		vec |= EvNegative
	}
	if v&1 == 0 {
		vec |= EvEven
	} else {
		vec |= EvUneven
	}
	if v != m.valPrev[cid] {
		vec |= EvChanged
	}
	return vec
}

// WriteConcept is write_concept (KPA-VM-3): it applies the guard of the concept,
// stores the value and queues the triggered subscriptions without running them.
func (m *Machine) WriteConcept(cid int, value int64) error {
	return m.write(cid, big.NewInt(value))
}

func (m *Machine) write(cid int, v *big.Int) error {
	if cid < 0 || cid >= len(m.art.Concepts) {
		return vmErr(CodeVMIndex, "concept index %d out of range", cid)
	}
	c := m.art.Concepts[cid]
	subs, err := m.ownedSubs(c)
	if err != nil {
		return err
	}
	if c.Flags&FlagHWProtected != 0 {
		ok := true
		if c.LowerBound != nil && v.Cmp(big.NewInt(*c.LowerBound)) < 0 {
			ok = false
		}
		if c.UpperBound != nil && v.Cmp(big.NewInt(*c.UpperBound)) > 0 {
			ok = false
		}
		if !ok {
			m.bigDotOK[cid] = 1
			for i, s := range subs {
				if s.Phase == PhaseOnAbort {
					m.queue = append(m.queue, c.FirstSubIdx+i)
				}
			}
			return nil
		}
	}
	if !v.IsInt64() {
		return vmErr(CodeVMOverflow, "value %s of concept %d does not fit int64", v, cid)
	}
	m.valPrev[cid] = m.valCur[cid]
	m.valCur[cid] = v.Int64()
	m.bigDotOK[cid] = 0

	ev := m.eventVector(cid)
	for i, s := range subs {
		if s.Phase == PhasePostChange && s.TriggerMask&ev != 0 {
			m.queue = append(m.queue, c.FirstSubIdx+i)
		}
	}
	return nil
}

// ownedSubs returns the subscriptions first_sub_idx .. first_sub_idx+sub_count-1
// of a concept.
func (m *Machine) ownedSubs(c LoweredConcept) ([]LoweredSubscription, error) {
	if c.SubCount == 0 {
		return nil, nil
	}
	if c.FirstSubIdx < 0 || c.SubCount < 0 || c.FirstSubIdx+c.SubCount > len(m.art.Subscriptions) {
		return nil, vmErr(CodeVMIndex, "subscription range %d+%d of concept %d out of range",
			c.FirstSubIdx, c.SubCount, c.CID)
	}
	return m.art.Subscriptions[c.FirstSubIdx : c.FirstSubIdx+c.SubCount], nil
}

// execLine is _exec_sub (KPA-VM-4).
func (m *Machine) execLine(subIdx int) error {
	sub := m.art.Subscriptions[subIdx]
	var stack []*big.Int
	pop := func() (*big.Int, error) {
		if len(stack) == 0 {
			return nil, vmErr(CodeVMStack, "pop from empty stack in subscription S%d", subIdx)
		}
		v := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		return v, nil
	}
	for pc := sub.LineStartPC; pc < sub.LineStartPC+sub.LineLen; pc++ {
		if pc < 0 || pc >= len(m.art.codeO) {
			return vmErr(CodeVMIndex, "code index %d out of range", pc)
		}
		word := m.art.codeO[pc]
		opc := int(word>>28) & 0x0F
		subOp := int(word>>24) & 0x0F
		operand := int(word & 0xFFFF)

		switch opc {
		case OpcImm:
			imm := operand
			if operand&0x8000 != 0 {
				imm = operand - 0x10000
			}
			stack = append(stack, big.NewInt(int64(imm)))
		case OpcGo:
			switch subOp {
			case GoRead:
				if operand >= len(m.valCur) {
					return vmErr(CodeVMIndex, "concept index %d out of range", operand)
				}
				stack = append(stack, big.NewInt(m.valCur[operand]))
			case GoWrite:
				v, err := pop()
				if err != nil {
					return err
				}
				if err := m.write(operand, v); err != nil {
					return err
				}
			default:
				return vmErr(CodeVMOpcode, "Unexpected GO sub_op %d", subOp)
			}
		case OpcDo:
			rhs, err := pop()
			if err != nil {
				return err
			}
			lhs, err := pop()
			if err != nil {
				return err
			}
			switch subOp {
			case DoAdd:
				stack = append(stack, new(big.Int).Add(lhs, rhs))
			case DoSub:
				stack = append(stack, new(big.Int).Sub(lhs, rhs))
			case DoMul:
				stack = append(stack, new(big.Int).Mul(lhs, rhs))
			default:
				return vmErr(CodeVMOpcode, "Unexpected DO sub_op %d", subOp)
			}
		case OpcExit:
			return nil
		default:
			return vmErr(CodeVMOpcode, "Unexpected opcode 0x%x", opc)
		}
	}
	return vmErr(CodeVMExit, "Subscription S%d missing KM_OPC_EXIT", subIdx)
}

// Run executes the queued subscription lines in FIFO order until the queue is
// empty (the loop of KPA-VM-5). On error the queue is cleared.
func (m *Machine) Run() error {
	limit := m.StepLimit
	if limit <= 0 {
		limit = DefaultStepLimit
	}
	for steps := 0; len(m.queue) > 0; {
		if steps >= limit {
			m.queue = nil
			return vmErr(CodeVMSteps, "more than %d subscription lines executed", limit)
		}
		steps++
		subIdx := m.queue[0]
		m.queue = m.queue[1:]
		if err := m.execLine(subIdx); err != nil {
			m.queue = nil
			return err
		}
	}
	return nil
}

// TriggerExternal writes value into the concept and runs the resulting cascade
// (trigger_external, KPA-VM-5). After an error the machine state is unspecified
// except that the queue is empty.
func (m *Machine) TriggerExternal(cid int, value int64) error {
	if err := m.WriteConcept(cid, value); err != nil {
		m.queue = nil
		return err
	}
	return m.Run()
}
