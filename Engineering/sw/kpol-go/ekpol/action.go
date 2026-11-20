package ekpol

import (
	"math/big"
	"strings"
)

var (
	reAugAction = pyRe(`^(` + identRe + `)\s*(\+=|-=)\s*(.+)$`)
	reSetAction = pyRe(`^(` + identRe + `)\s*(?::=|=)\s*(.+)$`)
	reBinAction = pyRe(`^(` + identRe + `)\s*([+\-])\s*(-?[0-9]+)$`)
	reSendStep  = pyRe(`^(?:send|step)\s+(` + identRe + `)\s*\((.*)\)$`)
	reExpect    = pyRe(`^expect\s+(` + identRe + `)\s*(==|=|!=|<=|>=|<|>)\s*(.+)$`)
)

func stepAction(add bool, target string, step *big.Int, raw string) Action {
	one := step.Cmp(big.NewInt(1)) == 0
	switch {
	case one && add:
		return Action{Kind: ActInc, Target: target, Operand: Int64Value(1), RawText: raw}
	case one:
		return Action{Kind: ActDec, Target: target, Operand: Int64Value(1), RawText: raw}
	case add:
		return Action{Kind: ActAdd, Target: target, Operand: IntValue(step), RawText: raw}
	}
	return Action{Kind: ActSub, Target: target, Operand: IntValue(step), RawText: raw}
}

// parseActions parses the action list after "=>" (EKPOL-SYN-10).
func parseActions(actionStr, concept, inputVar string) ([]Action, error) {
	s := pyStrip(actionStr)
	for {
		prev := s
		for _, suf := range []string{"commit;", "commit", ".;", ".", "•;", "•", ";"} {
			if strings.HasSuffix(s, suf) {
				s = pyStrip(s[:len(s)-len(suf)])
			}
		}
		if s == prev {
			break
		}
	}
	if s == "" {
		return nil, syntaxErr("concept %s: empty action after '=>'", pyRepr(concept))
	}
	if s == "pass" || s == "nop" {
		return []Action{{Kind: ActNop, Target: concept, Operand: Int64Value(0), RawText: s}}, nil
	}

	var parts []string
	for _, p := range strings.Split(s, ";") {
		if p = pyStrip(p); p != "" {
			parts = append(parts, p)
		}
	}
	var actions []Action
	for _, part := range parts {
		if part == "pass" || part == "nop" {
			actions = append(actions, Action{Kind: ActNop, Target: concept, Operand: Int64Value(0), RawText: part})
			continue
		}

		if m := find(reAugAction, part); m != nil {
			tgt, op, rhs := m.group(1), m.group(2), pyStrip(m.group(3))
			if step, ok := pyInt0(rhs); ok {
				actions = append(actions, stepAction(op == "+=", tgt, step, part))
			} else {
				actions = append(actions, Action{Kind: ActRaw, Target: tgt, Operand: TextValue(rhs), RawText: part})
			}
			continue
		}

		if m := find(reSetAction, part); m != nil {
			tgt := m.group(1)
			rhs := pyStrip(m.group(2))
			if b := find(reBinAction, rhs); b != nil && b.group(1) == tgt {
				step, ok := pyInt0(b.group(3))
				if !ok {
					return nil, internalErr("unhandled reference exception ValueError: invalid literal for int() with base 0: %s", pyRepr(b.group(3)))
				}
				actions = append(actions, stepAction(b.group(2) == "+", tgt, step, part))
				continue
			}
			switch {
			case rhs == inputVar && inputVar != "":
				actions = append(actions, Action{Kind: ActAssign, Target: tgt, Operand: TextValue(rhs), RawText: part})
			case rhs == "true" || rhs == "!" || rhs == "false" || rhs == "~false" || rhs == "¬" || rhs == "_" || rhs == "undef":
				v := BoolValue(rhs == "true" || rhs == "!")
				if rhs == "_" || rhs == "undef" {
					v = UndefValue()
				}
				actions = append(actions, Action{Kind: ActSetConst, Target: tgt, Operand: v, RawText: part})
			default:
				if c, ok := pyInt0(rhs); ok {
					actions = append(actions, Action{Kind: ActSetConst, Target: tgt, Operand: IntValue(c), RawText: part})
				} else if isIdent(rhs) {
					actions = append(actions, Action{Kind: ActAssign, Target: tgt, Operand: TextValue(rhs), RawText: part})
				} else {
					actions = append(actions, Action{Kind: ActRaw, Target: tgt, Operand: TextValue(rhs), RawText: part})
				}
			}
			continue
		}

		return nil, syntaxErr("concept %s: invalid action %s", pyRepr(concept), pyRepr(part))
	}
	return actions, nil
}

// parseTestBlock parses the body of "test Name { ... }" (EKPOL-SYN-11).
func parseTestBlock(name, body string) (*Test, error) {
	var steps []TestStep
	for _, raw := range strings.FieldsFunc(body, func(r rune) bool { return r == ';' || r == '\n' }) {
		stmt := pyStrip(raw)
		if stmt == "" {
			continue
		}
		if strings.HasSuffix(stmt, ".") {
			stmt = pyStrip(stmt[:len(stmt)-1])
		}
		if stmt == "" {
			continue
		}

		if m := find(reSendStep, stmt); m != nil {
			target := m.group(1)
			argsStr := pyStrip(m.group(2))
			if argsStr == "" {
				return nil, syntaxErr("test %s: send/step %s(...) requires an argument", pyRepr(name), target)
			}
			var argParts []string
			for _, a := range strings.Split(argsStr, ",") {
				if a = pyStrip(a); a != "" {
					argParts = append(argParts, a)
				}
			}
			if len(argParts) == 0 {
				return nil, internalErr("unhandled reference exception IndexError: list index out of range")
			}
			first := argParts[0]
			step := TestStep{Kind: StepSend, Target: target, Op: "=="}
			valTok := first
			if strings.ContainsAny(first, "=:") {
				sep := ":"
				if strings.Contains(first, "=") {
					sep = "="
				}
				k, v, _ := strings.Cut(first, sep)
				step.ParamName, step.HasParamName = pyStrip(k), true
				valTok = pyStrip(v)
			}
			if valTok == "_" || valTok == "undef" || valTok == "invalid" {
				step.Value = UndefValue()
			} else {
				v, err := parseIntLiteral(valTok, CodeSyntax)
				if err != nil {
					return nil, err
				}
				step.Value = IntValue(v)
			}
			for _, tok := range argParts[1:] {
				v, err := parseIntLiteral(tok, CodeSyntax)
				if err != nil {
					return nil, err
				}
				step.ExtraArgs = append(step.ExtraArgs, v)
			}
			steps = append(steps, step)
			continue
		}

		if m := find(reExpect, stmt); m != nil {
			op := m.group(2)
			if op == "=" {
				op = "=="
			}
			rhs := pyStrip(m.group(3))
			var val Value
			switch rhs {
			case "_", "undef":
				val = UndefValue()
			case "true", "!":
				val = BoolValue(true)
			case "false", "~false", "¬":
				val = BoolValue(false)
			default:
				if i, ok := pyInt0(rhs); ok {
					val = IntValue(i)
				} else if f, ok := pyFloat(rhs); ok {
					val = FloatValue(f)
				} else {
					return nil, syntaxErr("test %s: invalid expect literal %s", pyRepr(name), pyRepr(rhs))
				}
			}
			steps = append(steps, TestStep{Kind: StepExpect, Target: m.group(1), Op: op, Value: val})
			continue
		}

		return nil, syntaxErr("test %s: unrecognized test statement %s", pyRepr(name), pyRepr(stmt))
	}
	if len(steps) == 0 {
		return nil, newErr(CodeProof, "test %s: test block cannot be empty", pyRepr(name))
	}
	return &Test{Name: name, Steps: steps}, nil
}
