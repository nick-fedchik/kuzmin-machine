package kpol

import (
	"fmt"
	"math/big"
)

// cme1Integer is the reference helper integer() of _compile_cme1_profile: an
// integer literal (optionally negated) in [min, 2147483647].
func (c profileCtx) cme1Integer(e Expr, code, location string, min *big.Int) (*big.Int, error) {
	v, ok := cmeIntLiteral(e)
	if !ok {
		return nil, c.fail(code, "%s: expected an Int32 literal", location)
	}
	if v.Cmp(min) < 0 || v.Cmp(cmeMaxInt32()) > 0 {
		return nil, c.fail(code, "%s: literal outside [%s, 2147483647]", location, min)
	}
	return v, nil
}

// compileCME1 implements KPOL-P1-1..11 (reference: _compile_cme1_profile).
func compileCME1(m *Module, cfg *compileConfig) ([]Descriptor, error) {
	c := profileCtx{m}
	if err := c.check("B3-TYPE"); err != nil {
		return nil, err
	}
	if cfg.cascade {
		return nil, c.fail("B3-SHAPE", "cascade_map is outside KPOL-CME-1")
	}
	if len(m.States) != 1 || len(m.Events) != 1 || len(m.Rules) != 1 {
		return nil, c.fail("B3-SHAPE", "expected exactly one state, event and rule")
	}
	state, event, rule := m.States[0], m.Events[0], m.Rules[0]
	if !cmeIsInt32(state.Type) || len(event.Params) != 1 {
		return nil, c.fail("B3-SHAPE", "state %s and event %s: expected Int32 state and one parameter", state.Name, event.Name)
	}
	parameter := event.Params[0].Name
	if !cmeIsInt32(event.Params[0].Type) {
		return nil, c.fail("B3-SHAPE", "event %s: parameter %s must be Int32", event.Name, parameter)
	}
	initial, err := c.cme1Integer(state.Initial, "B3-SHAPE", "state "+state.Name+" initial", bigZero)
	if err != nil {
		return nil, err
	}
	if rule.Event != event.Name || rule.Reject || len(rule.Watch) > 0 || rule.Covers != "" {
		return nil, c.fail("B3-SHAPE", "rule %s: expected an ordinary rule on %s", rule.Name, event.Name)
	}
	if len(rule.Actions) != 1 || rule.Actions[0].Name != state.Name {
		return nil, c.fail("B3-SHAPE", "rule %s: expected one assignment to %s", rule.Name, state.Name)
	}
	if len(m.Requirements) != 1 || !cme1NonNegInvariant(m.Requirements[0], state.Name) {
		return nil, c.fail("B3-INVARIANT", "expected only the invariant %s >= 0", state.Name)
	}

	action, isBin := rule.Actions[0].Expression.(Binary)
	validAction := false
	if isBin {
		lit, isLit := action.R.(IntLit)
		validAction = (action.Op == "+" || action.Op == "-") && cmeIsName(action.L, state.Name) && isLit && lit.V.Cmp(bigOne) == 0
	}
	if !validAction {
		return nil, c.fail("B3-ACTION", "rule %s: expected %s + 1 or %s - 1", rule.Name, state.Name, state.Name)
	}
	actionOpcode := uint8(ActInc)
	if action.Op == "-" {
		actionOpcode = ActDec
	}

	var predicate uint8
	operand := big.NewInt(0)
	if b, ok := rule.Guard.(BoolLit); ok && b.V {
		predicate = PredNOP
	} else if g, ok := rule.Guard.(Binary); ok && cmeIsName(g.L, parameter) && cme1GuardOp(g.Op) != 0xFF {
		predicate = cme1GuardOp(g.Op)
		operand, err = c.cme1Integer(g.R, "B3-GUARD", fmt.Sprintf("rule %s guard", rule.Name), cmeMinInt32())
		if err != nil {
			return nil, err
		}
	} else {
		return nil, c.fail("B3-GUARD", "rule %s: expected true or %s compared with an Int32 literal", rule.Name, parameter)
	}

	if m.ProofPresent && len(m.Proofs) == 0 {
		return nil, c.fail("B3-PROOF", "Proof must contain at least one scenario")
	}
	for _, item := range m.Proofs {
		scenario, ok := item.(Scenario)
		if !ok {
			return nil, c.fail("B3-PROOF", "only scenario is supported, not Proof/assert")
		}
		if err := c.cme1Scenario(scenario, event.Name, parameter, state.Name); err != nil {
			return nil, err
		}
	}
	if len(m.Proofs) > 0 {
		if err := c.proof("B3-PROOF"); err != nil {
			return nil, err
		}
	}

	if err := c.acl("B3-ACL", cfg); err != nil {
		return nil, err
	}
	return []Descriptor{{
		CID: 0, Name: state.Name, CurrentState: cmeU32(initial), OperandVal: cmeU32(operand),
		PredOpcode: predicate, GuardFlags: GuardAssumptionEn | GuardInvariantEn, ActionOpcode: actionOpcode,
	}}, nil
}

// cme1GuardOp maps the comparison of KPOL-P1-8 to its predicate opcode; 0xFF
// marks any other operator.
func cme1GuardOp(op string) uint8 {
	switch op {
	case "<":
		return PredLT
	case ">":
		return PredGT
	case "==":
		return PredEQ
	case "!=":
		return PredNEQ
	}
	return 0xFF
}

// cme1NonNegInvariant is KPOL-P1-6: exactly `Invariant … : S >= 0` without
// `on` or `to`. The comparison is the reference's dataclass equality with
// Binary(">=", Name(S), Literal(0)).
func cme1NonNegInvariant(r Requirement, state string) bool {
	if r.Kind != KindInvariant || r.Event != "" || r.Target != "" {
		return false
	}
	b, ok := r.Expression.(Binary)
	return ok && b.Op == ">=" && cmeIsName(b.L, state) && cmeZeroLiteral(b.R)
}

// cme1Scenario is the per-scenario part of KPOL-P1-9.
func (c profileCtx) cme1Scenario(s Scenario, event, parameter, state string) error {
	location := "scenario " + s.Name
	seenStep, expects := false, 0
	for _, item := range s.Items {
		switch it := item.(type) {
		case StepAction:
			if it.Event != event || len(it.Args) != 1 || it.Args[0].Name != parameter {
				return c.fail("B3-PROOF", "%s: expected step %s(%s=integer)", location, event, parameter)
			}
			if _, err := c.cme1Integer(it.Args[0].Value, "B3-PROOF", location, cmeMinInt32()); err != nil {
				return err
			}
			seenStep = true
		case ExpectCheck:
			b, ok := it.Expression.(Binary)
			if !seenStep || !ok || b.Op != "==" || !cmeIsName(b.L, state) {
				return c.fail("B3-PROOF", "%s: expected %s == integer after a step", location, state)
			}
			if _, err := c.cme1Integer(b.R, "B3-PROOF", location, cmeMinInt32()); err != nil {
				return err
			}
			expects++
		default:
			return c.fail("B3-PROOF", "%s: unsupported scenario item", location)
		}
	}
	if !seenStep || expects == 0 {
		return c.fail("B3-PROOF", "%s: expected at least one step and expect", location)
	}
	return nil
}
