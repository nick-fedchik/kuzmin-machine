package ekpol

import (
	"math/big"
	"strings"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

// lowU32 is v & 0xFFFFFFFF with Python two's-complement semantics.
func lowU32(v *big.Int) uint32 {
	return uint32(new(big.Int).And(v, big.NewInt(0xFFFFFFFF)).Uint64())
}

func low16(v *big.Int) uint32 {
	return uint32(new(big.Int).And(v, big.NewInt(0xFFFF)).Uint64())
}

// evalPredOnInt evaluates a predicate on an integer (EKPOL-B64-11 / section 9.4).
func evalPredOnInt(p *Predicate, val *big.Int) bool {
	res := false
	switch p.Kind {
	case PredNop:
		res = true
	case PredCmp:
		c := val.Cmp(p.Value.Int)
		switch p.Op {
		case "==":
			res = c == 0
		case "!=":
			res = c != 0
		case "<":
			res = c < 0
		case ">":
			res = c > 0
		case "<=":
			res = c <= 0
		case ">=":
			res = c >= 0
		}
	case PredRange:
		res = p.Lo.Cmp(val) <= 0 && val.Cmp(p.Hi) <= 0
	case PredBitmask:
		res = new(big.Int).And(val, p.Value.Int).Sign() != 0
	}
	if p.Inverted {
		return !res
	}
	return res
}

// ValidateB64 checks the program against the EKPOL-B64 / CME-RAW-1 rules
// (specification section 9.1) and lowers it to 64 descriptors (section 9.2).
func ValidateB64(p *Program) ([]kpol.Descriptor, error) {
	n := len(p.Concepts)
	if n < 1 || n > 64 {
		return nil, syntaxErr("expected 1..64 concepts for bram64, got %d", n)
	}

	conceptIndex := make(map[string]int, n)
	initialEnv := make(map[string]*big.Int, n)

	for cid := range p.Concepts {
		c := &p.Concepts[cid]
		if c.Type != TypeInt32 {
			return nil, newErr(CodeType, "concept %s has type %s, but CME-RAW-1 bram64 requires Int32 (i32/int32/Int32)", pyRepr(c.Name), c.Type)
		}
		if c.UndefInit || c.Initial.Kind != ValueInt {
			return nil, newErr(CodeType, "concept %s: initial state '_' / undef requires --mode conceptual (CME-RAW-1 W0 stores signed Int32)", pyRepr(c.Name))
		}
		hasNonNeg := false
		for _, inv := range c.Invariants {
			switch {
			case inv.Kind == "cmp" && inv.Op == ">=" && inv.Value.Sign() >= 0:
				hasNonNeg = true
			case inv.Kind == "cmp" && inv.Op == ">" && inv.Value.Cmp(big.NewInt(-1)) >= 0:
				hasNonNeg = true
			case inv.Kind == "range" && inv.Lo != nil && inv.Lo.Sign() >= 0:
				hasNonNeg = true
			}
		}
		if !hasNonNeg {
			return nil, newErr(CodeInvariant, "concept %s: missing safety invariant '[>= 0]' in concept header or body", pyRepr(c.Name))
		}
		if c.Initial.Int.Sign() < 0 {
			return nil, newErr(CodeInvariant, "concept %s: initial value %s violates safety invariant %s >= 0", pyRepr(c.Name), c.Initial.Int, c.Name)
		}
		if len(c.Rules) != 1 {
			return nil, syntaxErr("concept %s: expected exactly 1 reaction rule for bram64, got %d", pyRepr(c.Name), len(c.Rules))
		}
		conceptIndex[c.Name] = cid
		initialEnv[c.Name] = c.Initial.Int
	}

	subscriberOf := map[string]string{}
	for i := range p.Concepts {
		c := &p.Concepts[i]
		rule := &c.Rules[0]
		switch rule.TriggerKind {
		case TriggerChange:
			src := rule.WatchConcept
			if src == "" {
				src = rule.ParamName
			}
			if _, ok := conceptIndex[src]; !ok {
				return nil, newErr(CodeCycle, "concept %s: subscribes to undeclared concept %s", pyRepr(c.Name), pyRepr(src))
			}
			if src == c.Name {
				return nil, newErr(CodeCycle, "concept %s: self-subscription (%s -> %s) is forbidden in bram64", pyRepr(c.Name), src, c.Name)
			}
			if prev, ok := subscriberOf[src]; ok {
				return nil, newErr(CodeCycle, "concept %s: cascade fan-out > 1 (%s, %s) exceeds single-slot subscriber_cid", pyRepr(src), prev, c.Name)
			}
			subscriberOf[src] = c.Name
		case TriggerWrite:
		default:
			return nil, newErr(CodeType, "concept %s: trigger kind %s requires --mode conceptual", pyRepr(c.Name), pyRepr(rule.TriggerKind))
		}
	}

	// 3-colour DFS cycle detection
	visit := make(map[string]int, n)
	for i := range p.Concepts {
		c := &p.Concepts[i]
		if visit[c.Name] != 0 {
			continue
		}
		cur, hasCur := c.Name, true
		var trail []string
		for hasCur && visit[cur] == 0 {
			visit[cur] = 1
			trail = append(trail, cur)
			cur, hasCur = subscriberOf[cur]
		}
		if hasCur && visit[cur] == 1 {
			return nil, newErr(CodeCycle, "cyclic cascade subscription detected involving concept %s (%s)", pyRepr(cur), strings.Join(append(trail, cur), " -> "))
		}
		for _, node := range trail {
			visit[node] = 2
		}
	}

	descriptors := make([]kpol.Descriptor, 0, 64)
	for cid := range p.Concepts {
		c := &p.Concepts[cid]
		rule := &c.Rules[0]
		inputVar := rule.ParamName
		if rule.TriggerKind == TriggerChange {
			inputVar = rule.WatchConcept
		}
		pred := &rule.Predicate

		if pred.Kind != PredNop && pred.Var != inputVar {
			return nil, syntaxErr("concept %s: guard variable %s does not match rule parameter %s", pyRepr(c.Name), pyRepr(pred.Var), pyRepr(inputVar))
		}

		guardUsesOp := false
		var guardOp uint32
		invert := pred.Inverted
		var predOpcode uint8

		switch pred.Kind {
		case PredNop:
			predOpcode = kpol.PredNOP
		case PredRange:
			if pred.Lo.Cmp(pred.Hi) > 0 || pred.Lo.Cmp(minInt16()) < 0 || pred.Hi.Cmp(maxInt16()) > 0 {
				return nil, newErr(CodeRange, "concept %s: range %s..%s outside int16 [-32768, 32767]", pyRepr(c.Name), pred.Lo, pred.Hi)
			}
			predOpcode = kpol.PredRANGE
			guardUsesOp = true
			guardOp = low16(pred.Hi)<<16 | low16(pred.Lo)
		case PredBitmask:
			predOpcode = kpol.PredBITMASK
			guardUsesOp = true
			guardOp = lowU32(pred.Value.Int)
		case PredCmp:
			if pred.Value.Kind != ValueInt {
				return nil, newErr(CodeType, "concept %s: guard comparison in bram64 requires Int32 literal", pyRepr(c.Name))
			}
			guardUsesOp = true
			guardOp = lowU32(pred.Value.Int)
			switch pred.Op {
			case "==":
				predOpcode = kpol.PredEQ
			case "!=":
				predOpcode = kpol.PredNEQ
			case "<":
				predOpcode = kpol.PredLT
			case ">":
				predOpcode = kpol.PredGT
			case ">=":
				predOpcode = kpol.PredLT
				invert = !invert
			case "<=":
				predOpcode = kpol.PredGT
				invert = !invert
			default:
				return nil, syntaxErr("concept %s: unsupported operator %s", pyRepr(c.Name), pyRepr(pred.Op))
			}
		default:
			return nil, newErr(CodeType, "concept %s: predicate %s is only supported in --mode conceptual", pyRepr(c.Name), pyRepr(pred.RawText))
		}

		if rule.TriggerKind == TriggerChange {
			if evalPredOnInt(pred, initialEnv[inputVar]) {
				return nil, newErr(CodeCycle, "concept %s: on change(%s) guard is active on initial state (%s)", pyRepr(c.Name), inputVar, initialEnv[inputVar])
			}
		}

		if len(rule.Actions) != 1 {
			return nil, syntaxErr("concept %s: bram64 rule requires exactly 1 action, got %d", pyRepr(c.Name), len(rule.Actions))
		}
		act := &rule.Actions[0]
		if act.Target != c.Name {
			return nil, syntaxErr("concept %s: rule action must update %s, not %s", pyRepr(c.Name), pyRepr(c.Name), pyRepr(act.Target))
		}

		actUsesOp := false
		var actOp uint32
		var actOpcode uint8
		switch {
		case act.Kind == ActInc:
			actOpcode = kpol.ActInc
		case act.Kind == ActDec:
			actOpcode = kpol.ActDec
		case act.Kind == ActAdd || act.Kind == ActSub:
			step := act.Operand.Int
			if step.Cmp(big.NewInt(1)) < 0 {
				return nil, syntaxErr("concept %s: step literal must be >= 1, got %s", pyRepr(c.Name), step)
			}
			actOpcode = kpol.ActSub
			if act.Kind == ActAdd {
				actOpcode = kpol.ActAdd
			}
			actUsesOp = true
			actOp = lowU32(step)
		case act.Kind == ActAssign && act.Operand.Kind == ValueText && act.Operand.Text == inputVar:
			actOpcode = kpol.ActAssign
		default:
			return nil, syntaxErr("concept %s: unsupported bram64 action %s (expected += 1, -= 1, += K, -= K, or = %s)", pyRepr(c.Name), pyRepr(act.RawText), inputVar)
		}

		_, isPublisher := subscriberOf[c.Name]
		if isPublisher && actOpcode != kpol.ActInc && actOpcode != kpol.ActDec && actOpcode != kpol.ActAdd && actOpcode != kpol.ActSub {
			return nil, newErr(CodeCycle, "concept %s: cascade publisher must use a non-zero step action (+/- K)", pyRepr(c.Name))
		}
		if guardUsesOp && actUsesOp {
			return nil, newErr(CodeCollision, "concept %s: CME-RAW-1 shares one 32-bit W1 operand_val between guard literal and ADD/SUB step != 1", pyRepr(c.Name))
		}

		operand := actOp
		if guardUsesOp {
			operand = guardOp
		}
		flags := uint8(kpol.GuardAssumptionEn | kpol.GuardInvariantEn)
		if invert {
			flags |= kpol.GuardInvertAssumption
		}
		var subCID uint32
		if isPublisher {
			subCID = uint32(conceptIndex[subscriberOf[c.Name]])
			flags |= kpol.GuardSubscriberEn
		}
		descriptors = append(descriptors, kpol.Descriptor{
			CID:           cid,
			Name:          c.Name,
			CurrentState:  lowU32(c.Initial.Int),
			OperandVal:    operand,
			PredOpcode:    predOpcode,
			GuardFlags:    flags,
			HazardLimit:   0,
			ActionOpcode:  actOpcode,
			SubscriberCID: subCID,
		})
	}
	for cid := len(descriptors); cid < 64; cid++ {
		descriptors = append(descriptors, kpol.Descriptor{CID: cid, Name: "Concept_" + itoa(cid)})
	}
	return descriptors, nil
}
