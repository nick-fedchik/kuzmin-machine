// Package ekpol implements EKPOL 0.1.0 (Ergonomic KPOL): the front end
// (comment/pragma stripping, program, concept, rule, guard, action and test
// parsing for both the symbolic and the keyword notation), the EKPOL-B64
// profile (lowering to CME-RAW-1 descriptors and BRAM images) and the
// EKPOL <-> KPOL translators.
//
// The normative definition is Engineering/specifications/kpol/
// ekpol-formal-specification.md; Engineering/sw/kpol-ref/ekpol_frontend.py is
// the oracle the package is tested against. Every diagnostic is a *kpol.Error
// whose Code is one of the EKPOL-* codes of the specification (section 12) and
// whose message text is identical to the reference.
package ekpol

import (
	"math/big"
	"strconv"
)

// Canonical concept types (EKPOL-LEX-3).
const (
	TypeInt32 = "Int32"
	TypeU64   = "U64"
	TypeFloat = "Float"
	TypeBool  = "Bool"
)

// Rule trigger kinds (EKPOL-STA-4).
const (
	TriggerWrite  = "write"
	TriggerChange = "change"
	TriggerRead   = "read"
	TriggerExec   = "exec"
	TriggerState  = "state"
)

// Predicate kinds (EKPOL-SYN-9).
const (
	PredNop     = "nop"
	PredCmp     = "cmp"
	PredRange   = "range"
	PredBitmask = "bitmask"
	PredUndef   = "undef"
	PredRaw     = "raw"
)

// Action kinds (EKPOL-SYN-10).
const (
	ActInc      = "inc"
	ActDec      = "dec"
	ActAdd      = "add"
	ActSub      = "sub"
	ActAssign   = "assign"
	ActSetConst = "set_const"
	ActNop      = "nop"
	ActRaw      = "raw"
)

// Test step kinds (EKPOL-SYN-11).
const (
	StepSend   = "send"
	StepExpect = "expect"
)

// ValueKind discriminates Value.
type ValueKind uint8

// Value kinds. ValueUndef is the uncertainty value written "_" / undef.
const (
	ValueUndef ValueKind = iota
	ValueBool
	ValueInt
	ValueFloat
	ValueText
)

// Value is a dynamically typed literal: an uncertain value, a Bool, an
// arbitrary-precision integer, a Float or an identifier / raw text.
type Value struct {
	Kind ValueKind
	Bool bool
	Int  *big.Int
	Flt  float64
	Text string
}

// UndefValue returns the uncertainty value "_".
func UndefValue() Value { return Value{Kind: ValueUndef} }

// BoolValue returns a Bool value.
func BoolValue(b bool) Value { return Value{Kind: ValueBool, Bool: b} }

// IntValue returns an integer value.
func IntValue(i *big.Int) Value { return Value{Kind: ValueInt, Int: i} }

// Int64Value returns an integer value.
func Int64Value(i int64) Value { return Value{Kind: ValueInt, Int: big.NewInt(i)} }

// FloatValue returns a Float value.
func FloatValue(f float64) Value { return Value{Kind: ValueFloat, Flt: f} }

// TextValue returns an identifier or raw-text value.
func TextValue(s string) Value { return Value{Kind: ValueText, Text: s} }

// IsInt reports whether v is a (non-Bool) integer.
func (v Value) IsInt() bool { return v.Kind == ValueInt }

// String formats v like Python's str().
func (v Value) String() string {
	switch v.Kind {
	case ValueUndef:
		return "_"
	case ValueBool:
		if v.Bool {
			return "True"
		}
		return "False"
	case ValueInt:
		return v.Int.String()
	case ValueFloat:
		return pyFloatRepr(v.Flt)
	default:
		return v.Text
	}
}

// Repr formats v like Python's repr().
func (v Value) Repr() string {
	switch v.Kind {
	case ValueUndef:
		return "'_'"
	case ValueText:
		return pyRepr(v.Text)
	default:
		return v.String()
	}
}

// equalsInt reports Python's v == n.
func (v Value) equalsInt(n int64) bool {
	switch v.Kind {
	case ValueInt:
		return v.Int.Cmp(big.NewInt(n)) == 0
	case ValueFloat:
		return v.Flt == float64(n)
	case ValueBool:
		return (v.Bool && n == 1) || (!v.Bool && n == 0)
	}
	return false
}

// Invariant is a concept safety invariant declared in "[...]" or "invariant ...;" (EKPOL-STA-2).
type Invariant struct {
	Kind  string // "cmp" or "range"
	Op    string
	Value *big.Int
	Lo    *big.Int // nil unless Kind == "range"
	Hi    *big.Int // nil unless Kind == "range"
}

// Predicate is a normalized rule guard (EKPOL-SYN-9).
type Predicate struct {
	Kind     string
	Var      string
	Op       string
	Value    Value
	Lo, Hi   *big.Int
	Inverted bool
	RawText  string
}

// Action is a single state update after "=>".
type Action struct {
	Kind    string
	Target  string
	Operand Value
	RawText string
}

// Rule is a reaction rule of a concept.
type Rule struct {
	TriggerKind string
	// EventName is "" for an anonymous event (and for non-write triggers other than the
	// fixed "read", "change", "call" names set by the parser).
	EventName       string
	ParamName       string
	ParamType       string
	WatchConcept    string // "" when absent
	ExecParams      []string
	Predicate       Predicate
	Actions         []Action
	PostReadBarrier bool
	RuleName        string // "" when absent
}

// Concept is a parsed concept declaration.
type Concept struct {
	Name        string
	Type        string // canonical type
	RawType     string
	Initial     Value
	UndefInit   bool
	Invariants  []Invariant
	Annotations []string
	Rules       []Rule
}

// TestStep is a "send"/"step" or "expect" statement of a test block.
type TestStep struct {
	Kind         string
	Target       string
	ParamName    string
	HasParamName bool
	Op           string
	Value        Value
	ExtraArgs    []*big.Int
}

// Test is a built-in verification scenario.
type Test struct {
	Name  string
	Steps []TestStep
}

// Program is a parsed EKPOL program.
type Program struct {
	ModuleName     string
	Concepts       []Concept
	Tests          []Test
	StdinConcepts  []string
	StdoutConcepts []string
	StderrConcepts []string
}

// ConceptNames returns the concept names in declaration order; the index of a
// name is its CID in the EKPOL-B64 image.
func (p *Program) ConceptNames() []string {
	names := make([]string, len(p.Concepts))
	for i := range p.Concepts {
		names[i] = p.Concepts[i].Name
	}
	return names
}

// IsConceptualOnly reports whether the program uses constructs whose semantics
// EKPOL 0.1.0 leaves undefined (specification section 11): non-Int32 types,
// the undefined initial value, or read/exec/state rules.
func (p *Program) IsConceptualOnly() bool {
	for i := range p.Concepts {
		c := &p.Concepts[i]
		if c.Type != TypeInt32 || c.UndefInit {
			return true
		}
		for j := range c.Rules {
			switch c.Rules[j].TriggerKind {
			case TriggerRead, TriggerExec, TriggerState:
				return true
			}
		}
	}
	return false
}

func itoa(n int) string { return strconv.Itoa(n) }
