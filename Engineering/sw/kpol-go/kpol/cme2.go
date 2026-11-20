package kpol

import (
	"fmt"
	"math/big"
	"sort"
	"strings"
)

// cme2 holds the facts gathered about a module while checking KPOL-P2-*.
type cme2 struct {
	profileCtx
	stateIndex   map[string]int
	initial      map[string]*big.Int
	eventParam   map[string]string
	ruleByTarget map[string]*Rule
	subscriberOf map[string]string // cascade source -> destination
}

// cme2Flip mirrors a comparison operator ("K < x" is "x > K"); "" if op is not one.
func cme2Flip(op string) string {
	switch op {
	case "<":
		return ">"
	case ">":
		return "<"
	case "<=":
		return ">="
	case ">=":
		return "<="
	case "==", "!=":
		return op
	}
	return ""
}

// integer is integer_raw (unbounded) when bounded is false, and integer()
// with the range [min, max] otherwise.
func (p *cme2) integer(e Expr, code, location string, bounded bool, min, max *big.Int) (*big.Int, error) {
	v, ok := cmeIntLiteral(e)
	if !ok {
		return nil, p.fail(code, "%s: expected an integer literal", location)
	}
	if bounded && (v.Cmp(min) < 0 || v.Cmp(max) > 0) {
		return nil, p.fail(code, "%s: literal %s outside [%s, %s]", location, v, min, max)
	}
	return v, nil
}

// compileCME2 implements KPOL-P2-1..19 (reference: _compile_cme2_profile).
func compileCME2(m *Module, cfg *compileConfig) ([]Descriptor, error) {
	p := &cme2{
		profileCtx:   profileCtx{m},
		stateIndex:   map[string]int{},
		initial:      map[string]*big.Int{},
		eventParam:   map[string]string{},
		ruleByTarget: map[string]*Rule{},
		subscriberOf: map[string]string{},
	}
	if err := p.check("CME2-TYPE"); err != nil {
		return nil, err
	}
	if cfg.cascade {
		return nil, p.fail("CME2-CASCADE", "cascade_map is outside KPOL-CME-2; declare cascades via 'on change(State)'")
	}
	if m.PhaseAliasesUsed {
		return nil, p.fail("CME2-GUARD", "phase/dot alias ('•' or '(*)') is outside KPOL-CME-2 (#186); use 'not'")
	}
	for _, req := range m.Requirements {
		switch req.Kind {
		case KindHazard:
			return nil, p.fail("CME2-HAZARD", "hazard %s: KPOL Hazards latch a Bool target state via 'on reject', "+
				"which CME-RAW-1 does not write back to BRAM; express input bounds in rule 'when' guards", req.Name)
		case KindAssumption:
			return nil, p.fail("CME2-GUARD", "assumption %s: declare preconditions in rule 'when' guards", req.Name)
		case KindInvariant:
		default:
			return nil, p.fail("CME2-INVARIANT", "requirement %s (%s) is outside KPOL-CME-2", req.Name, req.Kind)
		}
	}
	if len(m.States) < 1 || len(m.States) > 64 {
		return nil, p.fail("CME2-SHAPE", "expected 1..64 states, got %d", len(m.States))
	}
	if err := p.states(); err != nil {
		return nil, err
	}
	if err := p.events(); err != nil {
		return nil, err
	}
	if err := p.rules(); err != nil {
		return nil, err
	}
	if err := p.invariants(); err != nil {
		return nil, err
	}
	if err := p.cascades(); err != nil {
		return nil, err
	}

	ds := make([]Descriptor, 0, len(m.States))
	for cid := range m.States {
		d, err := p.lower(cid)
		if err != nil {
			return nil, err
		}
		ds = append(ds, d)
	}

	if !m.ProofPresent || len(m.Proofs) == 0 {
		return nil, p.fail("CME2-PROOF", "KPOL-CME-2 requires a non-empty Proof block")
	}
	if err := p.proof("CME2-PROOF"); err != nil {
		return nil, err
	}
	if err := p.acl("CME2-ACL", cfg); err != nil {
		return nil, err
	}
	return ds, nil
}

// states checks KPOL-P2-5 and assigns CIDs in declaration order.
func (p *cme2) states() error {
	for cid, st := range p.m.States {
		if !cmeIsInt32(st.Type) {
			return p.fail("CME2-TYPE", "state %s: expected Int32", st.Name)
		}
		v, err := p.integer(st.Initial, "CME2-SHAPE", "state "+st.Name+" initial", true, cmeMinInt32(), cmeMaxInt32())
		if err != nil {
			return err
		}
		if v.Sign() < 0 {
			return p.fail("CME2-INVARIANT", "state %s: initial value %s violates invariant %s >= 0", st.Name, v, st.Name)
		}
		p.stateIndex[st.Name] = cid
		p.initial[st.Name] = v
	}
	return nil
}

// events checks KPOL-P2-6.
func (p *cme2) events() error {
	for _, ev := range p.m.Events {
		if len(ev.Params) != 1 {
			return p.fail("CME2-SHAPE", "event %s: expected exactly one Int32 parameter", ev.Name)
		}
		param := ev.Params[0]
		if !cmeIsInt32(param.Type) {
			return p.fail("CME2-TYPE", "event %s: parameter %s must be Int32", ev.Name, param.Name)
		}
		if _, clash := p.stateIndex[param.Name]; clash {
			return p.fail("CME2-SHAPE", "event %s: parameter %s shadows a state name", ev.Name, param.Name)
		}
		p.eventParam[ev.Name] = param.Name
	}
	return nil
}

// rules checks KPOL-P2-7 and KPOL-P2-8.
func (p *cme2) rules() error {
	usedEvents := map[string]bool{}
	for i := range p.m.Rules {
		rule := &p.m.Rules[i]
		if rule.Reject || rule.Covers != "" {
			return p.fail("CME2-SHAPE", "rule %s: 'on reject' and 'covers' are outside KPOL-CME-2", rule.Name)
		}
		if len(rule.Actions) != 1 {
			return p.fail("CME2-SHAPE", "rule %s: expected exactly one set action", rule.Name)
		}
		target := rule.Actions[0].Name
		if _, ok := p.stateIndex[target]; !ok {
			return p.fail("CME2-SHAPE", "rule %s: unknown target state %s", rule.Name, target)
		}
		if _, dup := p.ruleByTarget[target]; dup {
			return p.fail("CME2-SHAPE", "state %s: expected exactly one rule per state", target)
		}
		p.ruleByTarget[target] = rule

		if rule.triggerEvent() == "change" {
			if len(rule.Watch) != 1 {
				return p.fail("CME2-SHAPE", "rule %s: expected single-state on change(State)", rule.Name)
			}
			if _, ok := p.stateIndex[rule.Watch[0]]; !ok {
				return p.fail("CME2-SHAPE", "rule %s: unknown watched state %s", rule.Name, rule.Watch[0])
			}
			continue
		}
		if len(rule.Watch) > 0 {
			return p.fail("CME2-SHAPE", "rule %s: unexpected watch list on external event", rule.Name)
		}
		if _, ok := p.eventParam[rule.Event]; !ok {
			return p.fail("CME2-SHAPE", "rule %s: unknown event %s", rule.Name, rule.Event)
		}
		if usedEvents[rule.Event] {
			return p.fail("CME2-SHAPE", "event %s: bound to multiple rules; CME-RAW-1 dispatches one CID per event", rule.Event)
		}
		usedEvents[rule.Event] = true
	}

	if len(p.ruleByTarget) != len(p.m.States) {
		var missing []string
		for _, st := range p.m.States {
			if _, ok := p.ruleByTarget[st.Name]; !ok {
				missing = append(missing, st.Name)
			}
		}
		return p.fail("CME2-SHAPE", "states without rules: %s", strings.Join(missing, ", "))
	}
	if len(usedEvents) != len(p.eventParam) {
		var unused []string
		for name := range p.eventParam {
			if !usedEvents[name] {
				unused = append(unused, name)
			}
		}
		sort.Strings(unused)
		return p.fail("CME2-SHAPE", "unused event declarations: %s", strings.Join(unused, ", "))
	}
	return nil
}

// invariants checks KPOL-P2-9: one `S >= 0` (or `0 <= S`) per state.
func (p *cme2) invariants() error {
	seen := map[string]bool{}
	for _, req := range p.m.Requirements {
		if req.Event != "" || req.Target != "" {
			return p.fail("CME2-INVARIANT", "invariant %s: unexpected event or target", req.Name)
		}
		matched := ""
		if b, ok := req.Expression.(Binary); ok {
			if n, isName := b.L.(Name); b.Op == ">=" && isName && p.isState(n.Name) && cmeStrictZero(b.R) {
				matched = n.Name
			} else if n, isName := b.R.(Name); b.Op == "<=" && isName && p.isState(n.Name) && cmeStrictZero(b.L) {
				matched = n.Name
			}
		}
		if matched == "" || seen[matched] {
			return p.fail("CME2-INVARIANT", "invariant %s: expected unique 'State >= 0' per declared state", req.Name)
		}
		seen[matched] = true
	}
	if len(seen) != len(p.stateIndex) {
		var missing []string
		for _, st := range p.m.States {
			if !seen[st.Name] {
				missing = append(missing, st.Name)
			}
		}
		return p.fail("CME2-INVARIANT", "missing 'State >= 0' invariant for: %s", strings.Join(missing, ", "))
	}
	return nil
}

func (p *cme2) isState(name string) bool { _, ok := p.stateIndex[name]; return ok }

// cmeStrictZero is `type(value) is int and value == 0`: unlike the CME-1
// invariant test, a Bool or Decimal zero does not qualify.
func cmeStrictZero(e Expr) bool {
	lit, ok := e.(IntLit)
	return ok && lit.V.Sign() == 0
}

// cascades checks KPOL-P2-10: single fan-out, no self-loop, no cycle.
func (p *cme2) cascades() error {
	for _, rule := range p.m.Rules {
		if rule.triggerEvent() != "change" {
			continue
		}
		dst, src := rule.Actions[0].Name, rule.Watch[0]
		if src == dst {
			return p.fail("CME2-CASCADE", "rule %s: self-subscription on %s is forbidden", rule.Name, src)
		}
		if prev, ok := p.subscriberOf[src]; ok {
			return p.fail("CME2-CASCADE", "state %s: cascade fan-out > 1 (%s, %s) "+
				"exceeds single-slot cascade_pending in CME-RAW-1", src, prev, dst)
		}
		p.subscriberOf[src] = dst
	}

	visit := make(map[string]int, len(p.m.States))
	for _, st := range p.m.States {
		if visit[st.Name] != 0 {
			continue
		}
		cur, more := st.Name, true
		var trail []string
		for more && visit[cur] == 0 {
			visit[cur] = 1
			trail = append(trail, cur)
			cur, more = p.subscriberOf[cur]
		}
		if more && visit[cur] == 1 {
			return p.fail("CME2-CASCADE", "cyclic cascade detected involving %s", cur)
		}
		for _, n := range trail {
			visit[n] = 2
		}
	}
	return nil
}

// cmeCmp is a canonical comparison `x op K`.
type cmeCmp struct {
	op  string
	val *big.Int
}

// canonicalCmp is the reference helper canonical_cmp: it brings `x op K` or
// `K op x` into the form `x op K`. wide skips the Int32 range check (the
// int16 test of the range form comes later).
func (p *cme2) canonicalCmp(node Expr, input, rule string, wide bool) (cmeCmp, error) {
	b, ok := node.(Binary)
	if !ok || cme2Flip(b.Op) == "" {
		return cmeCmp{}, p.fail("CME2-GUARD", "rule %s: expected comparison on %s", rule, input)
	}
	var op string
	var rhs Expr
	switch {
	case cmeIsName(b.L, input):
		op, rhs = b.Op, b.R
	case cmeIsName(b.R, input):
		op, rhs = cme2Flip(b.Op), b.L
	default:
		return cmeCmp{}, p.fail("CME2-GUARD", "rule %s: guard must compare input %s with an integer literal", rule, input)
	}
	v, err := p.integer(rhs, "CME2-GUARD", "rule "+rule+" guard", !wide, cmeMinInt32(), cmeMaxInt32())
	if err != nil {
		return cmeCmp{}, err
	}
	return cmeCmp{op, v}, nil
}

// lower builds the descriptor of the state with index cid (KPOL-P2-11..16,
// KPOL-P2-19).
func (p *cme2) lower(cid int) (Descriptor, error) {
	state := p.m.States[cid]
	rule := p.ruleByTarget[state.Name]
	isChange := rule.triggerEvent() == "change"
	input := ""
	if isChange {
		input = rule.Watch[0]
	} else {
		input = p.eventParam[rule.Event]
	}

	g := rule.Guard
	invert := false
	for {
		u, ok := g.(Unary)
		if !ok {
			break
		}
		if u.Op == "not" || u.Op == "!" {
			invert = !invert
			g = u.X
			continue
		}
		if u.Op == "•" {
			return Descriptor{}, p.fail("CME2-GUARD", "rule %s: operator '•' is outside KPOL-CME-2 (#186); use 'not'", rule.Name)
		}
		break
	}

	var pred uint8
	guardUsesOperand := false
	var guardOperand uint32
	switch gx := g.(type) {
	case BoolLit:
		pred = PredNOP
		if !gx.V {
			invert = !invert
		}
	case Binary:
		switch {
		case gx.Op == "and":
			lo, hi, err := p.rangeBounds(gx, input, rule.Name)
			if err != nil {
				return Descriptor{}, err
			}
			pred = PredRANGE
			guardUsesOperand = true
			guardOperand = uint32(uint16(hi.Int64()))<<16 | uint32(uint16(lo.Int64()))
		case cme2Flip(gx.Op) != "":
			c, err := p.canonicalCmp(gx, input, rule.Name, false)
			if err != nil {
				return Descriptor{}, err
			}
			guardUsesOperand = true
			guardOperand = cmeU32(c.val)
			switch c.op {
			case "==":
				pred = PredEQ
			case "!=":
				pred = PredNEQ
			case "<":
				pred = PredLT
			case ">":
				pred = PredGT
			case ">=":
				pred = PredLT
				invert = !invert
			case "<=":
				pred = PredGT
				invert = !invert
			}
		default:
			return Descriptor{}, p.fail("CME2-GUARD", "rule %s: unsupported guard expression in KPOL-CME-2", rule.Name)
		}
	default:
		return Descriptor{}, p.fail("CME2-GUARD", "rule %s: unsupported guard expression in KPOL-CME-2", rule.Name)
	}

	if isChange {
		env := make(map[string]Value, len(p.initial))
		for k, v := range p.initial {
			env[k] = NewBigInt(v)
		}
		v, err := EvalExpr(rule.Guard, env)
		if err != nil {
			return Descriptor{}, err
		}
		if b, ok := v.(Bool); !ok || bool(b) {
			return Descriptor{}, p.fail("CME2-CASCADE", "rule %s: on change(%s) guard is active on initial state "+
				"(%s); CME-RAW-1 does not trigger cascades at load time", rule.Name, input, p.initial[input])
		}
	}

	act, actOperand, actUsesOperand, err := p.action(rule, state.Name, input)
	if err != nil {
		return Descriptor{}, err
	}
	dst, isPublisher := p.subscriberOf[state.Name]
	if isPublisher && act == ActAssign {
		return Descriptor{}, p.fail("CME2-CASCADE", "state %s: cascade publisher must use a non-zero step action (+/- k) "+
			"so CME-RAW-1 commit coincides with KPOL change()", state.Name)
	}
	if guardUsesOperand && actUsesOperand {
		return Descriptor{}, p.fail("CME2-OPERAND-COLLISION", "rule %s: CME-RAW-1 shares one 32-bit operand_val between guard literal "+
			"and ADD/SUB != 1 (#185)", rule.Name)
	}

	operand := actOperand
	if guardUsesOperand {
		operand = guardOperand
	}
	flags := uint8(GuardAssumptionEn | GuardInvariantEn)
	if invert {
		flags |= GuardInvertAssumption
	}
	var sub uint32
	if isPublisher {
		sub = uint32(p.stateIndex[dst])
		flags |= GuardSubscriberEn
	}
	return Descriptor{
		CID: cid, Name: state.Name, CurrentState: cmeU32(p.initial[state.Name]), OperandVal: operand,
		PredOpcode: pred, GuardFlags: flags, ActionOpcode: act, SubscriberCID: sub,
	}, nil
}

// rangeBounds handles the two-sided guard `a and b` (KPOL-P2-11, KPOL-P2-12)
// and returns the inclusive bounds [lo, hi], already known to be int16.
func (p *cme2) rangeBounds(g Binary, input, rule string) (lo, hi *big.Int, err error) {
	l, err := p.canonicalCmp(g.L, input, rule, true)
	if err != nil {
		return nil, nil, err
	}
	r, err := p.canonicalCmp(g.R, input, rule, true)
	if err != nil {
		return nil, nil, err
	}
	for _, c := range [2]cmeCmp{l, r} {
		switch c.op {
		case ">=", ">":
			if lo != nil {
				return nil, nil, p.fail("CME2-RANGE", "rule %s: duplicate lower bound", rule)
			}
			lo = c.val
			if c.op == ">" {
				lo = new(big.Int).Add(c.val, bigOne)
			}
		case "<=", "<":
			if hi != nil {
				return nil, nil, p.fail("CME2-RANGE", "rule %s: duplicate upper bound", rule)
			}
			hi = c.val
			if c.op == "<" {
				hi = new(big.Int).Sub(c.val, bigOne)
			}
		default:
			return nil, nil, p.fail("CME2-RANGE", "rule %s: range requires lower (>, >=) and upper (<, <=) bounds", rule)
		}
	}
	if lo == nil || hi == nil {
		return nil, nil, p.fail("CME2-RANGE", "rule %s: incomplete two-sided range", rule)
	}
	minI16, maxI16 := big.NewInt(-32768), big.NewInt(32767)
	if lo.Cmp(minI16) < 0 || lo.Cmp(maxI16) > 0 || hi.Cmp(minI16) < 0 || hi.Cmp(maxI16) > 0 || lo.Cmp(hi) > 0 {
		return nil, nil, p.fail("CME2-RANGE", "rule %s: range [%s, %s] outside int16 [-32768, 32767] or inverted", rule, lo, hi)
	}
	return lo, hi, nil
}

// action classifies the single assignment of rule (KPOL-P2-13): `set S := x`,
// `S + K`, `K + S` or `S - K` with K in [1, 2³¹-1]; K = 1 selects INC/DEC and
// every other K ADD/SUB with the step in operand_val.
func (p *cme2) action(rule *Rule, state, input string) (opcode uint8, operand uint32, usesOperand bool, err error) {
	expr := rule.Actions[0].Expression
	if cmeIsName(expr, input) {
		return ActAssign, 0, false, nil
	}
	b, ok := expr.(Binary)
	if !ok || (b.Op != "+" && b.Op != "-") {
		return 0, 0, false, p.fail("CME2-ACTION", "rule %s: expected '%s' or '%s +/- <1..2147483647>' "+
			"(constant literal assignment requires CME-RAW-2, #185)", rule.Name, input, state)
	}
	var stepExpr Expr
	switch {
	case cmeIsName(b.L, state):
		stepExpr = b.R
	case b.Op == "+" && cmeIsName(b.R, state):
		stepExpr = b.L
	default:
		return 0, 0, false, p.fail("CME2-ACTION", "rule %s: arithmetic action must update %s", rule.Name, state)
	}
	step, err := p.integer(stepExpr, "CME2-ACTION", fmt.Sprintf("rule %s action", rule.Name), true, bigOne, cmeMaxInt32())
	if err != nil {
		return 0, 0, false, err
	}
	if step.Cmp(bigOne) == 0 {
		if b.Op == "+" {
			return ActInc, 0, false, nil
		}
		return ActDec, 0, false, nil
	}
	if b.Op == "+" {
		return ActAdd, cmeU32(step), true, nil
	}
	return ActSub, cmeU32(step), true, nil
}
