// This file defines the abstract syntax of KPOL (specification §4). The package
// documentation is in doc.go.

package kpol

import "math/big"

// Expr is a KPOL expression node (spec §4, KPOL-SYN-8).
type Expr interface{ exprNode() }

// IntLit is an integer literal (arbitrary precision; sign is a separate unary minus).
type IntLit struct{ V *big.Int }

// DecLit is a decimal literal such as "2.50". Text preserves the source spelling.
type DecLit struct{ Text string }

// BoolLit is the literal true or false.
type BoolLit struct{ V bool }

// UnknownLit is the literal Unknown.
type UnknownLit struct{}

// Name is a reference to a state or an event parameter.
type Name struct{ Name string }

// Unary is "not", "-", or the deprecated phase aliases "•" and "(*)" (KPOL-LEX-6).
type Unary struct {
	Op string
	X  Expr
}

// Binary is one of: or and == != < <= > >= + - * /.
type Binary struct {
	Op   string
	L, R Expr
}

// Call is a call of a built-in function; only gcd(a, b) exists.
type Call struct {
	Name string
	Args []Expr
}

func (IntLit) exprNode()     {}
func (DecLit) exprNode()     {}
func (BoolLit) exprNode()    {}
func (UnknownLit) exprNode() {}
func (Name) exprNode()       {}
func (Unary) exprNode()      {}
func (Binary) exprNode()     {}
func (Call) exprNode()       {}

// TypeRef is a KPOL type: Bool, Int32, U32, U64, Float<unit> or Pin.
// Unit is set only for Float. PinParams holds the optional identifiers of Pin<...>.
type TypeRef struct {
	Name      string
	Unit      string
	PinParams []string
}

// Requirement kinds.
const (
	KindAssumption = "Assumption"
	KindInvariant  = "Invariant"
	KindHazard     = "Hazard"
	KindAlert      = "Alert"
	KindGoal       = "Goal"
)

// Requirement is one entry of a Problem section.
type Requirement struct {
	Kind       string
	Name       string
	Event      string // "" if absent
	Target     string // "" if absent
	Expression Expr
}

// Param is a typed event parameter.
type Param struct {
	Name string
	Type TypeRef
}

// EventDecl declares an external event.
type EventDecl struct {
	Name   string
	Params []Param
}

// StateDecl declares a state with its initializer.
type StateDecl struct {
	Name    string
	Type    TypeRef
	Initial Expr
}

// SetAction is `set Name := Expression;`.
type SetAction struct {
	Name       string
	Expression Expr
}

// Rule reacts to an external event or to changes of states. For a rule on
// change(...) the parser sets Event to "change" (as the reference does) and
// Watch to the ordered, possibly repeating, tuple of observed states; for an
// event rule Watch is empty. Consumers may identify change rules by Watch.
type Rule struct {
	Name    string
	Event   string
	Reject  bool
	Watch   []string
	Guard   Expr // BoolLit{true} when `when` is absent
	Covers  string
	Actions []SetAction
}

// Arg is a named step argument.
type Arg struct {
	Name  string
	Value Expr
}

// ScenarioItem is either a StepAction or an ExpectCheck.
type ScenarioItem interface{ scenarioItem() }

// StepAction is `step Event(args);` inside a scenario.
type StepAction struct {
	Event string
	Args  []Arg
}

// ExpectCheck is `expect expr;` inside a scenario.
type ExpectCheck struct{ Expression Expr }

func (StepAction) scenarioItem()  {}
func (ExpectCheck) scenarioItem() {}

// ProofItem is either an AssertProperty or a Scenario.
type ProofItem interface{ proofItem() }

// AssertProperty is `assert Name on Event [when g] expect e;`.
type AssertProperty struct {
	Name        string
	Event       string
	Guard       Expr // BoolLit{true} when absent
	Expectation Expr
}

// Scenario is a named sequence of steps and expectations.
type Scenario struct {
	Name  string
	Items []ScenarioItem
}

func (AssertProperty) proofItem() {}
func (Scenario) proofItem()       {}

// Module is the parsed program (spec KPOL-SYN-8).
type Module struct {
	Name             string
	Requirements     []Requirement
	Events           []EventDecl
	States           []StateDecl
	Rules            []Rule
	ProofPresent     bool
	Proofs           []ProofItem
	PhaseAliasesUsed bool
	// SHA-256 (hex) of the three source files; set only by ParseTriad.
	ProblemHash, SolutionHash, ProofHash string
}
