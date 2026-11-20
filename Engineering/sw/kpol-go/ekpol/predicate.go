package ekpol

import (
	"math/big"
	"strings"
)

var (
	reRangeIn   = pyRe(`^(` + identRe + `)\s+in\s+(-?[0-9]+)\s*\.\.\s*(-?[0-9]+)$`)
	reRangeCall = pyRe(`(?i)^RANGE\s*\(\s*(` + identRe + `)\s*,\s*(-?[0-9]+)\s*,\s*(-?[0-9]+)\s*\)$`)
	reAndSplit  = pyRe(`\s+(?:&&|and)\s+`)
	reNamed     = pyRe(`(?i)^(?:(` + identRe + `)\s+)?is\s+(not\s+)?(undef|null|positive|negative|even|odd|uneven)$`)
	reMask      = pyRe(`^\(?\s*(` + identRe + `)\s*&\s*(-?(?:0x[0-9A-Fa-f]+|[0-9]+))\s*\)?(?:\s*(!=|==)\s*0)?$`)
	reSpecial   = pyRe(`^(` + identRe + `)\s*(==|!=|=)\s*(_|undef|true|false|!|~false|¬)$`)
	reCmpLeft   = pyRe(`^(` + identRe + `)\s*(==|!=|<=|>=|<|>|=)\s*(-?(?:0x[0-9A-Fa-f]+|[0-9]+))$`)
	reCmpRight  = pyRe(`^(-?(?:0x[0-9A-Fa-f]+|[0-9]+))\s*(==|!=|<=|>=|<|>|=)\s*(` + identRe + `)$`)
	reSymbolic  = pyRe(`^(` + identRe + `)\s*(==|!=|<=|>=|<|>)\s*(` + identRe + `)$`)
)

// outerParensBalanced reports whether the leading "(" of g is closed by its final ")".
func outerParensBalanced(g string) bool {
	depth := 0
	for i := 0; i < len(g); i++ {
		switch g[i] {
		case '(':
			depth++
		case ')':
			depth--
			if depth == 0 && i < len(g)-1 {
				return false
			}
		}
	}
	return true
}

// parseSingleCmpClause parses "var op int" or "int op var" into (var, op, int).
func parseSingleCmpClause(clause, defaultVar, concept string) (string, string, *big.Int, error) {
	s := pyStrip(clause)
	for strings.HasPrefix(s, "(") && strings.HasSuffix(s, ")") {
		s = pyStrip(s[1 : len(s)-1])
	}
	if m := find(reCmpLeft, s); m != nil {
		op := m.group(2)
		if op == "=" {
			op = "=="
		}
		val, err := parseIntLiteral(m.group(3), CodeSyntax)
		if err != nil {
			return "", "", nil, err
		}
		return m.group(1), op, val, nil
	}
	if m := find(reCmpRight, s); m != nil {
		val, err := parseIntLiteral(m.group(1), CodeSyntax)
		if err != nil {
			return "", "", nil, err
		}
		op := m.group(2)
		if op == "=" {
			op = "=="
		}
		flipped, _ := flipCmpOp(op)
		return m.group(3), flipped, val, nil
	}
	return "", "", nil, syntaxErr("concept %s: cannot parse guard comparison %s (expected comparison on %s)", pyRepr(concept), pyRepr(clause), pyRepr(defaultVar))
}

func noneOrInt(v *big.Int) string {
	if v == nil {
		return "None"
	}
	return v.String()
}

// parsePredicate normalizes a guard (EKPOL-SYN-7..9). hasGuard is false when the rule has no guard.
func parsePredicate(guardStr string, hasGuard bool, defaultVar, concept string) (*Predicate, error) {
	nop := func(inverted bool, raw string) *Predicate {
		return &Predicate{Kind: PredNop, Var: defaultVar, Op: "==", Value: Int64Value(0), Inverted: inverted, RawText: raw}
	}
	if !hasGuard {
		return nop(false, "true"), nil
	}
	g := pyStrip(guardStr)
	if g == "" || g == "true" {
		return nop(false, "true"), nil
	}
	if g == "false" {
		return nop(true, "false"), nil
	}
	raw := pyStrip(guardStr)

	invert := false
prefixes:
	for {
		switch {
		case strings.HasPrefix(g, "not ") || strings.HasPrefix(g, "not("):
			invert = !invert
			g = pyStrip(g[3:])
		case strings.HasPrefix(g, "!") && !strings.HasPrefix(g, "!=") && g != "!":
			invert = !invert
			g = pyStrip(g[1:])
		default:
			break prefixes
		}
		if strings.HasPrefix(g, "(") && strings.HasSuffix(g, ")") && outerParensBalanced(g) {
			g = pyStrip(g[1 : len(g)-1])
		}
	}
	for strings.HasPrefix(g, "(") && strings.HasSuffix(g, ")") {
		if !outerParensBalanced(g) {
			break
		}
		g = pyStrip(g[1 : len(g)-1])
	}

	if g == "true" {
		return nop(invert, raw), nil
	}
	if g == "false" {
		return nop(!invert, raw), nil
	}

	// 1. range: x in LO..HI | RANGE(x, LO, HI)
	m := find(reRangeIn, g)
	if m == nil {
		m = find(reRangeCall, g)
	}
	if m != nil {
		lo, err := parseIntLiteral(m.group(2), CodeRange)
		if err != nil {
			return nil, err
		}
		hi, err := parseIntLiteral(m.group(3), CodeRange)
		if err != nil {
			return nil, err
		}
		if lo.Cmp(hi) > 0 || lo.Cmp(minInt16()) < 0 || hi.Cmp(maxInt16()) > 0 {
			return nil, newErr(CodeRange, "concept %s: invalid range %s..%s (must satisfy -32768 <= lo <= hi <= 32767)", pyRepr(concept), lo, hi)
		}
		return &Predicate{Kind: PredRange, Var: m.group(1), Op: "in", Value: Int64Value(0), Lo: lo, Hi: hi, Inverted: invert, RawText: raw}, nil
	}

	// 2. compound range: x >= LO && x <= HI
	if parts := reAndSplit.Split(g, -1); len(parts) == 2 {
		v1, op1, val1, err := parseSingleCmpClause(parts[0], defaultVar, concept)
		if err != nil {
			return nil, err
		}
		v2, op2, val2, err := parseSingleCmpClause(parts[1], defaultVar, concept)
		if err != nil {
			return nil, err
		}
		if v1 != v2 {
			return nil, syntaxErr("concept %s: compound guard compares two different variables (%s and %s)", pyRepr(concept), pyRepr(v1), pyRepr(v2))
		}
		var lo, hi *big.Int
		for _, c := range []struct {
			op  string
			val *big.Int
		}{{op1, val1}, {op2, val2}} {
			switch c.op {
			case ">=":
				lo = c.val
			case ">":
				lo = new(big.Int).Add(c.val, big.NewInt(1))
			case "<=":
				hi = c.val
			case "<":
				hi = new(big.Int).Sub(c.val, big.NewInt(1))
			default:
				return nil, newErr(CodeRange, "concept %s: compound range requires lower (>, >=) and upper (<, <=) bounds", pyRepr(concept))
			}
		}
		if lo == nil || hi == nil || lo.Cmp(hi) > 0 || lo.Cmp(minInt16()) < 0 || hi.Cmp(maxInt16()) > 0 {
			return nil, newErr(CodeRange, "concept %s: invalid two-sided range [%s, %s]", pyRepr(concept), noneOrInt(lo), noneOrInt(hi))
		}
		return &Predicate{Kind: PredRange, Var: v1, Op: "in", Value: Int64Value(0), Lo: lo, Hi: hi, Inverted: invert, RawText: raw}, nil
	}

	// 3. named state predicates
	if m := find(reNamed, g); m != nil {
		v := m.group(1)
		if v == "" {
			v = defaultVar
		}
		isNot := m.has(2)
		word := strings.ToLower(m.group(3))
		eff := invert != isNot
		switch word {
		case "undef":
			op := "=="
			if eff {
				op = "!="
			}
			return &Predicate{Kind: PredUndef, Var: v, Op: op, Value: UndefValue(), Inverted: eff, RawText: raw}, nil
		case "null":
			op := "=="
			if eff {
				op = "!="
			}
			return &Predicate{Kind: PredCmp, Var: v, Op: op, Value: Int64Value(0), RawText: raw}, nil
		case "positive":
			op := ">"
			if eff {
				op = "<="
			}
			return &Predicate{Kind: PredCmp, Var: v, Op: op, Value: Int64Value(0), RawText: raw}, nil
		case "negative":
			op := "<"
			if eff {
				op = ">="
			}
			return &Predicate{Kind: PredCmp, Var: v, Op: op, Value: Int64Value(0), RawText: raw}, nil
		case "odd", "uneven":
			return &Predicate{Kind: PredBitmask, Var: v, Op: "&", Value: Int64Value(1), Inverted: eff, RawText: raw}, nil
		case "even":
			return &Predicate{Kind: PredBitmask, Var: v, Op: "&", Value: Int64Value(1), Inverted: !eff, RawText: raw}, nil
		}
	}

	// 4. explicit bitmask
	if m := find(reMask, g); m != nil {
		mask, err := parseIntLiteral(m.group(2), CodeSyntax)
		if err != nil {
			return nil, err
		}
		eff := invert != (m.group(3) == "==")
		return &Predicate{Kind: PredBitmask, Var: m.group(1), Op: "&", Value: IntValue(mask), Inverted: eff, RawText: raw}, nil
	}

	// 5. uncertainty / Bool comparison
	switch g {
	case "_", "undef":
		return &Predicate{Kind: PredUndef, Var: defaultVar, Op: "==", Value: UndefValue(), Inverted: invert, RawText: g}, nil
	case "!", "true":
		return &Predicate{Kind: PredCmp, Var: defaultVar, Op: "==", Value: BoolValue(true), Inverted: invert, RawText: g}, nil
	case "¬", "~false", "false":
		return &Predicate{Kind: PredCmp, Var: defaultVar, Op: "==", Value: BoolValue(false), Inverted: invert, RawText: g}, nil
	}
	if m := find(reSpecial, g); m != nil {
		op := m.group(2)
		if op == "=" {
			op = "=="
		}
		rhs := m.group(3)
		if rhs == "_" || rhs == "undef" {
			return &Predicate{Kind: PredUndef, Var: m.group(1), Op: op, Value: UndefValue(), Inverted: invert != (op == "!="), RawText: raw}, nil
		}
		return &Predicate{Kind: PredCmp, Var: m.group(1), Op: op, Value: BoolValue(rhs == "true" || rhs == "!"), Inverted: invert, RawText: raw}, nil
	}

	// 6. numeric comparison, then symbol-to-symbol
	v, op, val, err := parseSingleCmpClause(g, defaultVar, concept)
	if err == nil {
		return &Predicate{Kind: PredCmp, Var: v, Op: op, Value: IntValue(val), Inverted: invert, RawText: raw}, nil
	}
	if m := find(reSymbolic, g); m != nil {
		return &Predicate{Kind: PredRaw, Var: m.group(1), Op: m.group(2), Value: TextValue(m.group(3)), Inverted: invert, RawText: raw}, nil
	}
	return nil, err
}
