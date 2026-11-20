package ekpol

import (
	"strings"
)

var (
	reOnPrefix  = pyRe(`^on\s+`)
	reGuardKw   = pyRe(`^(?:::|when)\s+(.+)$`)
	reChangeSrc = pyRe(`^\(?\s*(` + identRe + `)\s*\)?(.*)$`)
	reOnWrite   = pyRe(`^on\s+[A-Za-z_]`)
	reEvParam   = pyRe(`^(` + identRe + `)\s*\(\s*(` + identRe + `)(?:\s*:\s*([A-Za-z0-9_?]+))?\s*\)(.*)$`)
	reParenOnly = pyRe(`^\(\s*(` + identRe + `)(?:\s*:\s*([A-Za-z0-9_?]+))?\s*\)(.*)$`)
	reBareParam = pyRe(`^(` + identRe + `)(?:\s*:\s*([A-Za-z0-9_?]+))?(.*)$`)
	reOnEvent   = pyRe(`^on\s+(` + identRe + `)(?:\s*\(\s*(` + identRe + `)(?:\s*:\s*([A-Za-z0-9_?]+))?\s*\))?(.*)$`)
)

// onKeyword matches "on" followed by one of the words at a word boundary and returns the remainder.
func onKeyword(lhs string, words ...string) (string, bool) {
	loc := reOnPrefix.FindStringIndex(lhs)
	if loc == nil {
		return "", false
	}
	after := lhs[loc[1]:]
	for _, w := range words {
		if strings.HasPrefix(after, w) && atWordEnd(after, len(w)) {
			return after[len(w):], true
		}
	}
	return "", false
}

// guardText extracts the guard of "(:: | when) guard"; ok is false when the text is not of that form.
func guardText(s string) (string, bool) {
	m := find(reGuardKw, s)
	if m == nil {
		return "", false
	}
	return pyStrip(m.group(1)), true
}

func hasTerminator(rhs string) bool {
	for _, t := range []string{"commit;", "commit", ".;", ".", "•;", "•", ";"} {
		if strings.HasSuffix(rhs, t) {
			return true
		}
	}
	return false
}

// parseConceptRule classifies and parses one rule instruction (EKPOL-SYN-3..6).
func parseConceptRule(stmt, concept string) (*Rule, error) {
	s := pyStrip(stmt)
	lhsRaw, rhsRaw, ok := strings.Cut(s, "=>")
	if !ok {
		return nil, syntaxErr("concept %s: rule %s is missing '=>' action arrow", pyRepr(concept), pyRepr(s))
	}
	lhs := pyStrip(lhsRaw)
	rhs := pyStrip(rhsRaw)
	terminated := hasTerminator(rhs)

	// 1. read
	if restOn, isOn := onKeyword(lhs, "read"); strings.HasPrefix(lhs, "->") || isOn {
		var restLhs string
		if strings.HasPrefix(lhs, "->") {
			restLhs = pyStrip(lhs[2:])
		} else {
			restLhs = pyStrip(restOn)
		}
		guard := ""
		hasGuard := false
		if restLhs != "" {
			g, ok := guardText(restLhs)
			if !ok {
				return nil, syntaxErr("concept %s: invalid read guard %s", pyRepr(concept), pyRepr(restLhs))
			}
			guard, hasGuard = g, true
		}
		postDot := false
		switch {
		case strings.HasPrefix(rhs, "."):
			postDot = true
			rhs = pyStrip(rhs[1:])
		case strings.HasPrefix(rhs, "•"):
			postDot = true
			rhs = pyStrip(rhs[len("•"):])
		case strings.HasPrefix(rhs, "after") && atWordEnd(rhs, len("after")):
			postDot = true
			rhs = pyStrip(rhs[len("after"):])
		}
		pred, err := parsePredicate(guard, hasGuard, concept, concept)
		if err != nil {
			return nil, err
		}
		acts, err := parseActions(rhs, concept, concept)
		if err != nil {
			return nil, err
		}
		return &Rule{
			TriggerKind:     TriggerRead,
			EventName:       "read",
			ParamName:       concept,
			ParamType:       TypeInt32,
			Predicate:       *pred,
			Actions:         acts,
			PostReadBarrier: postDot,
		}, nil
	}

	if !terminated {
		return nil, syntaxErr("concept %s: rule %s is missing Big Dot terminator ('.', 'commit', or ';')", pyRepr(concept), pyRepr(s))
	}

	// 2. change subscription
	if restOn, isOn := onKeyword(lhs, "change"); strings.HasPrefix(lhs, "~") || isOn {
		var rest string
		if strings.HasPrefix(lhs, "~") {
			rest = pyStrip(lhs[1:])
		} else {
			rest = pyStrip(restOn)
		}
		m := find(reChangeSrc, rest)
		if m == nil {
			return nil, syntaxErr("concept %s: invalid change subscription %s", pyRepr(concept), pyRepr(lhs))
		}
		src := m.group(1)
		guardPart := pyStrip(m.group(2))
		guard, hasGuard := "", false
		if guardPart != "" {
			g, ok := guardText(guardPart)
			if !ok {
				return nil, syntaxErr("concept %s: invalid guard syntax %s", pyRepr(concept), pyRepr(guardPart))
			}
			guard, hasGuard = g, true
		}
		pred, err := parsePredicate(guard, hasGuard, src, concept)
		if err != nil {
			return nil, err
		}
		acts, err := parseActions(rhs, concept, src)
		if err != nil {
			return nil, err
		}
		return &Rule{
			TriggerKind:  TriggerChange,
			EventName:    "change",
			ParamName:    src,
			ParamType:    TypeInt32,
			WatchConcept: src,
			Predicate:    *pred,
			Actions:      acts,
		}, nil
	}

	// 3. exec / call
	if restOn, isOn := onKeyword(lhs, "call", "exec"); strings.HasPrefix(lhs, "|") || isOn {
		var rest string
		if strings.HasPrefix(lhs, "|") {
			rest = pyStrip(lhs[1:])
		} else {
			rest = pyStrip(restOn)
		}
		var params []string
		if strings.HasPrefix(rest, "(") {
			closeIdx := strings.Index(rest, ")")
			if closeIdx < 0 {
				return nil, syntaxErr("concept %s: unclosed '(' in exec rule", pyRepr(concept))
			}
			inner := pyStrip(rest[1:closeIdx])
			if inner != "" {
				for _, tok := range strings.Split(inner, ",") {
					head, _, _ := strings.Cut(tok, ":")
					if p := pyStrip(head); p != "" {
						params = append(params, p)
					}
				}
			}
			rest = pyStrip(rest[closeIdx+1:])
		}
		guard, hasGuard := "", false
		if rest != "" {
			g, ok := guardText(rest)
			if !ok {
				return nil, syntaxErr("concept %s: invalid exec guard %s", pyRepr(concept), pyRepr(rest))
			}
			guard, hasGuard = g, true
		}
		defaultVar := concept
		if len(params) > 0 {
			defaultVar = params[0]
		}
		pred, err := parsePredicate(guard, hasGuard, defaultVar, concept)
		if err != nil {
			return nil, err
		}
		acts, err := parseActions(rhs, concept, defaultVar)
		if err != nil {
			return nil, err
		}
		return &Rule{
			TriggerKind: TriggerExec,
			EventName:   "call",
			ParamName:   defaultVar,
			ParamType:   TypeInt32,
			ExecParams:  params,
			Predicate:   *pred,
			Actions:     acts,
		}, nil
	}

	// 4. write
	if strings.HasPrefix(lhs, "<-") || reOnWrite.MatchString(lhs) {
		evName := ""
		paramName := "param"
		paramType := TypeInt32
		var guardPart string

		if strings.HasPrefix(lhs, "<-") {
			rest := pyStrip(lhs[2:])
			switch {
			case find(reEvParam, rest) != nil:
				m := find(reEvParam, rest)
				if raw := m.group(1); raw != "write" && raw != "input" {
					evName = raw
				}
				paramName = m.group(2)
				if t := m.group(3); t != "" {
					paramType = canonOrSelf(t)
				}
				guardPart = pyStrip(m.group(4))
			case find(reParenOnly, rest) != nil:
				m := find(reParenOnly, rest)
				paramName = m.group(1)
				if t := m.group(2); t != "" {
					paramType = canonOrSelf(t)
				}
				guardPart = pyStrip(m.group(3))
			default:
				if m := find(reBareParam, rest); m != nil && m.group(1) != "when" {
					paramName = m.group(1)
					if t := m.group(2); t != "" {
						paramType = canonOrSelf(t)
					}
					guardPart = pyStrip(m.group(3))
				} else {
					guardPart = rest
				}
			}
		} else {
			m := find(reOnEvent, lhs)
			if m == nil {
				return nil, syntaxErr("concept %s: invalid 'on' trigger %s", pyRepr(concept), pyRepr(lhs))
			}
			if raw := m.group(1); raw != "write" && raw != "input" {
				evName = raw
			}
			if p := m.group(2); p != "" {
				paramName = p
			}
			if t := m.group(3); t != "" {
				paramType = canonOrSelf(t)
			}
			guardPart = pyStrip(m.group(4))
		}

		guard, hasGuard := "", false
		if guardPart != "" {
			g, ok := guardText(guardPart)
			if !ok {
				return nil, syntaxErr("concept %s: expected '::' or 'when' before guard %s", pyRepr(concept), pyRepr(guardPart))
			}
			guard, hasGuard = g, true
		}
		pred, err := parsePredicate(guard, hasGuard, paramName, concept)
		if err != nil {
			return nil, err
		}
		acts, err := parseActions(rhs, concept, paramName)
		if err != nil {
			return nil, err
		}
		return &Rule{
			TriggerKind: TriggerWrite,
			EventName:   evName,
			ParamName:   paramName,
			ParamType:   paramType,
			Predicate:   *pred,
			Actions:     acts,
		}, nil
	}

	// 5. autonomous state transition
	if g, ok := guardText(lhs); ok {
		pred, err := parsePredicate(g, true, concept, concept)
		if err != nil {
			return nil, err
		}
		acts, err := parseActions(rhs, concept, concept)
		if err != nil {
			return nil, err
		}
		return &Rule{
			TriggerKind: TriggerState,
			ParamName:   concept,
			ParamType:   TypeInt32,
			Predicate:   *pred,
			Actions:     acts,
		}, nil
	}

	return nil, syntaxErr("concept %s: unrecognized rule trigger %s", pyRepr(concept), pyRepr(lhs))
}
