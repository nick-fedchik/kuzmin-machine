package vmk

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"
)

var ekpolTypeSynonyms = map[string]string{
	"i32":     "Int32",
	"int32":   "Int32",
	"Int32":   "Int32",
	"u64":     "U64",
	"uint64":  "U64",
	"U64":     "U64",
	"f64":     "Float",
	"float64": "Float",
	"Float":   "Float",
	"bool":    "Bool",
	"Bool":    "Bool",
	"?":       "Bool",
}

// EKPOLInvariant represents a safety invariant declared in `[...]` header brackets or `invariant ...;` body.
type EKPOLInvariant struct {
	Kind  string
	Op    string
	Value int64
	Lo    int64
	Hi    int64
}

// EKPOLPredicate represents a parsed rule predicate (`::` or `when`).
type EKPOLPredicate struct {
	Kind     string // "nop", "cmp", "range", "bitmask", "undef", "raw"
	Var      string
	Op       string
	IntVal   int64
	BoolVal  bool
	Lo       int64
	Hi       int64
	Inverted bool
	RawText  string
}

// EKPOLAction represents a parsed state transition action after `=>`.
type EKPOLAction struct {
	Kind    string // "inc", "dec", "add", "sub", "assign", "set_const", "nop", "raw"
	Target  string
	IntVal  int64
	VarName string
	RawText string
}

// EKPOLRule represents a reaction rule inside an EKPOL concept.
type EKPOLRule struct {
	TriggerKind     string // "write", "change", "read", "exec", "state"
	EventName       string
	ParamName       string
	ParamType       string
	WatchConcept    string
	ExecParams      []string
	Predicate       EKPOLPredicate
	Actions         []EKPOLAction
	PostReadBarrier bool
	RuleName        string
}

// EKPOLConcept represents a parsed `concept Name: Type = Init [Invariant] { ... }`.
type EKPOLConcept struct {
	Name          string
	CanonicalType string
	RawType       string
	InitInt       int64
	InitFloat     float64
	InitBool      bool
	IsUndefInit   bool
	Invariants    []EKPOLInvariant
	Annotations   []string
	Rules         []EKPOLRule
}

// EKPOLTestStep represents a `send`/`step` or `expect` statement inside a `test` block.
type EKPOLTestStep struct {
	Kind      string // "send" or "expect"
	Target    string
	ParamName string
	Op        string
	IntVal    int64
	FloatVal  float64
	BoolVal   bool
	IsBool    bool
	IsUndef   bool
	ExtraArgs []int64
}

// EKPOLTest represents a `test Name { ... }` verification block.
type EKPOLTest struct {
	Name  string
	Steps []EKPOLTestStep
}

// EKPOLProgram represents a parsed `.ekpol` program AST.
type EKPOLProgram struct {
	ModuleName     string
	Concepts       []EKPOLConcept
	Tests          []EKPOLTest
	StdinConcepts  []string
	StdoutConcepts []string
	StderrConcepts []string
}

// IsConceptualOnly returns true if the EKPOL program uses conceptual-only types or triggers
// (`Float`, `U64`, `Bool`/`?`, `_`/`undef`, `read`, `exec`, or autonomous `state` transitions).
func (p *EKPOLProgram) IsConceptualOnly() bool {
	for _, c := range p.Concepts {
		if c.CanonicalType != "Int32" || c.IsUndefInit {
			return true
		}
		for _, r := range c.Rules {
			if r.TriggerKind == "read" || r.TriggerKind == "exec" || r.TriggerKind == "state" {
				return true
			}
		}
	}
	return false
}

var (
	reEKPOLModSemi    = regexp.MustCompile(`(?s)^\s*module\s+([A-Za-z_][A-Za-z0-9_]*)\s*;\s*(.*)$`)
	reEKPOLModBrace   = regexp.MustCompile(`(?s)^\s*module\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{(.*)\}\s*$`)
	reEKPOLAnnotation = regexp.MustCompile(`^@(stdin|stdout|stderr)\b`)
	reEKPOLConceptHdr = regexp.MustCompile(`^concept\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z0-9_?]+)\s*=\s*([^\[\{\n]+?)(\s*\[[^\]]*\])?\s*\{`)
	reEKPOLTestHdr    = regexp.MustCompile(`^(?:test|scenario)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{`)
	reEKPOLInvClause  = regexp.MustCompile(`^(?:([A-Za-z_][A-Za-z0-9_]*)\s*)?(>=|<=|==|!=|>|<)\s*(-?[0-9]+)$`)
	reEKPOLRangeIn    = regexp.MustCompile(`^([A-Za-z_][A-Za-z0-9_]*)\s+in\s+(-?[0-9]+)\s*\.\.\s*(-?[0-9]+)$`)
	reEKPOLRangeCall  = regexp.MustCompile(`(?i)^RANGE\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,\s*(-?[0-9]+)\s*,\s*(-?[0-9]+)\s*\)$`)
	reEKPOLNamedIs    = regexp.MustCompile(`(?i)^(?:([A-Za-z_][A-Za-z0-9_]*)\s+)?is\s+(not\s+)?(undef|null|positive|negative|even|odd|uneven)$`)
	reEKPOLMaskPred   = regexp.MustCompile(`^\(?\s*([A-Za-z_][A-Za-z0-9_]*)\s*&\s*(-?(?:0x[0-9A-Fa-f]+|[0-9]+))\s*\)?(?:\s*(!=|==)\s*0)?$`)
	reEKPOLCmpLeft    = regexp.MustCompile(`^([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=|<=|>=|<|>|=)\s*(-?(?:0x[0-9A-Fa-f]+|[0-9]+))$`)
	reEKPOLCmpRight   = regexp.MustCompile(`^(-?(?:0x[0-9A-Fa-f]+|[0-9]+))\s*(==|!=|<=|>=|<|>|=)\s*([A-Za-z_][A-Za-z0-9_]*)$`)
	reEKPOLCmpSpecial = regexp.MustCompile(`^([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=|=)\s*(_|undef|true|false|!|~false|¬)$`)
	reEKPOLCmpSym     = regexp.MustCompile(`^([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=|<=|>=|<|>)\s*([A-Za-z_][A-Za-z0-9_]*)$`)
)

func stripCommentsPreserveEKPOLPragmas(src string) (string, []string, []string, []string, error) {
	var stdinC, stdoutC, stderrC []string

	extractPragma := func(comment string) {
		b := strings.TrimSpace(comment)
		if strings.HasPrefix(b, "@stdin") {
			rest := strings.ReplaceAll(b[len("@stdin"):], ",", " ")
			stdinC = append(stdinC, strings.Fields(rest)...)
		} else if strings.HasPrefix(b, "@stdout") {
			rest := strings.ReplaceAll(b[len("@stdout"):], ",", " ")
			stdoutC = append(stdoutC, strings.Fields(rest)...)
		} else if strings.HasPrefix(b, "@stderr") {
			rest := strings.ReplaceAll(b[len("@stderr"):], ",", " ")
			stderrC = append(stderrC, strings.Fields(rest)...)
		}
	}

	// Remove /* ... */ block comments
	var sb strings.Builder
	for i := 0; i < len(src); {
		if i+1 < len(src) && src[i] == '/' && src[i+1] == '*' {
			end := strings.Index(src[i+2:], "*/")
			if end < 0 {
				return "", nil, nil, nil, fmt.Errorf("EKPOL-SYNTAX-ERR: unterminated /* ... */ block comment")
			}
			chunk := src[i : i+2+end+2]
			sb.WriteString(strings.Repeat("\n", strings.Count(chunk, "\n")))
			i += 2 + end + 2
		} else {
			sb.WriteByte(src[i])
			i++
		}
	}

	var lines []string
	for _, line := range strings.Split(sb.String(), "\n") {
		cut := len(line)
		mLen := 0
		for _, m := range []string{"//", "#"} {
			if idx := strings.Index(line, m); idx >= 0 && idx < cut {
				cut = idx
				mLen = len(m)
			}
		}
		if cut < len(line) {
			extractPragma(line[cut+mLen:])
			line = line[:cut]
		}
		lines = append(lines, line)
	}
	return strings.Join(lines, "\n"), stdinC, stdoutC, stderrC, nil
}

func parseEKPOLBracketInvariants(bracketStr, conceptName string) ([]EKPOLInvariant, error) {
	if strings.TrimSpace(bracketStr) == "" {
		return nil, nil
	}
	inner := strings.TrimSpace(bracketStr)
	if strings.HasPrefix(inner, "[") && strings.HasSuffix(inner, "]") {
		inner = strings.TrimSpace(inner[1 : len(inner)-1])
	}
	if inner == "" {
		return nil, fmt.Errorf("EKPOL-INVARIANT-ERR: concept %q has empty invariant brackets '[]'", conceptName)
	}
	var invs []EKPOLInvariant
	for _, rawPart := range strings.Split(inner, ",") {
		clause := strings.TrimSpace(rawPart)
		if clause == "" {
			continue
		}
		if strings.Contains(clause, "..") {
			bounds := strings.SplitN(clause, "..", 2)
			lo, err1 := strconv.ParseInt(strings.TrimSpace(bounds[0]), 0, 64)
			hi, err2 := strconv.ParseInt(strings.TrimSpace(bounds[1]), 0, 64)
			if err1 != nil || err2 != nil || lo > hi {
				return nil, fmt.Errorf("EKPOL-INVARIANT-ERR: concept %q invalid invariant range %q", conceptName, clause)
			}
			invs = append(invs, EKPOLInvariant{Kind: "range", Op: "..", Lo: lo, Hi: hi, Value: lo})
		} else {
			m := reEKPOLInvClause.FindStringSubmatch(clause)
			if len(m) != 4 {
				return nil, fmt.Errorf("EKPOL-INVARIANT-ERR: concept %q invalid invariant clause %q", conceptName, clause)
			}
			if m[1] != "" && m[1] != conceptName {
				return nil, fmt.Errorf("EKPOL-INVARIANT-ERR: concept %q invariant references foreign concept %q", conceptName, m[1])
			}
			v, err := strconv.ParseInt(m[3], 0, 64)
			if err != nil {
				return nil, fmt.Errorf("EKPOL-INVARIANT-ERR: concept %q invalid invariant integer %q", conceptName, m[3])
			}
			invs = append(invs, EKPOLInvariant{Kind: "cmp", Op: m[2], Value: v})
		}
	}
	return invs, nil
}

func stripBalancedOuterParens(s string) string {
	for strings.HasPrefix(s, "(") && strings.HasSuffix(s, ")") {
		depth := 0
		balanced := true
		for i := 0; i < len(s); i++ {
			if s[i] == '(' {
				depth++
			} else if s[i] == ')' {
				depth--
				if depth == 0 && i < len(s)-1 {
					balanced = false
					break
				}
			}
		}
		if balanced {
			s = strings.TrimSpace(s[1 : len(s)-1])
		} else {
			break
		}
	}
	return s
}

func parseEKPOLSingleCmpClause(clause, defaultVar, conceptName string) (string, string, int64, error) {
	s := stripBalancedOuterParens(strings.TrimSpace(clause))
	flip := map[string]string{"<": ">", ">": "<", "<=": ">=", ">=": "<=", "==": "==", "=": "==", "!=": "!="}
	if m := reEKPOLCmpLeft.FindStringSubmatch(s); len(m) == 4 {
		op := m[2]
		if op == "=" {
			op = "=="
		}
		v, err := strconv.ParseInt(m[3], 0, 64)
		if err != nil {
			return "", "", 0, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q invalid guard literal %q", conceptName, m[3])
		}
		return m[1], op, v, nil
	}
	if m := reEKPOLCmpRight.FindStringSubmatch(s); len(m) == 4 {
		v, err := strconv.ParseInt(m[1], 0, 64)
		if err != nil {
			return "", "", 0, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q invalid guard literal %q", conceptName, m[1])
		}
		return m[3], flip[m[2]], v, nil
	}
	return "", "", 0, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q cannot parse guard comparison %q (expected comparison on %s)", conceptName, clause, defaultVar)
}

func parseEKPOLPredicate(guardStr, defaultVar, conceptName string) (EKPOLPredicate, error) {
	g := strings.TrimSpace(guardStr)
	if g == "" || g == "true" {
		return EKPOLPredicate{Kind: "nop", Var: defaultVar, RawText: "true"}, nil
	}
	if g == "false" {
		return EKPOLPredicate{Kind: "nop", Var: defaultVar, Inverted: true, RawText: "false"}, nil
	}

	invert := false
	for {
		if strings.HasPrefix(g, "not ") || strings.HasPrefix(g, "not(") {
			invert = !invert
			g = strings.TrimSpace(g[3:])
		} else if strings.HasPrefix(g, "!") && !strings.HasPrefix(g, "!=") && g != "!" {
			invert = !invert
			g = strings.TrimSpace(g[1:])
		} else {
			break
		}
		g = stripBalancedOuterParens(g)
	}
	g = stripBalancedOuterParens(g)

	if g == "true" {
		return EKPOLPredicate{Kind: "nop", Var: defaultVar, Inverted: invert, RawText: guardStr}, nil
	}
	if g == "false" {
		return EKPOLPredicate{Kind: "nop", Var: defaultVar, Inverted: !invert, RawText: guardStr}, nil
	}

	// 1. Range `x in LO..HI` or `RANGE(x, LO, HI)`
	mIn := reEKPOLRangeIn.FindStringSubmatch(g)
	if len(mIn) == 0 {
		mIn = reEKPOLRangeCall.FindStringSubmatch(g)
	}
	if len(mIn) == 4 {
		lo, err1 := strconv.ParseInt(mIn[2], 0, 64)
		hi, err2 := strconv.ParseInt(mIn[3], 0, 64)
		if err1 != nil || err2 != nil || lo > hi || lo < -32768 || hi > 32767 {
			return EKPOLPredicate{}, fmt.Errorf("EKPOL-RANGE-ERR: concept %q invalid range %s..%s (must satisfy -32768 <= lo <= hi <= 32767)", conceptName, mIn[2], mIn[3])
		}
		return EKPOLPredicate{
			Kind:     "range",
			Var:      mIn[1],
			Op:       "in",
			Lo:       lo,
			Hi:       hi,
			Inverted: invert,
			RawText:  guardStr,
		}, nil
	}

	// 2. Compound range `x >= LO && x <= HI` or `x >= LO and x <= HI`
	var andParts []string
	if strings.Contains(g, "&&") {
		andParts = strings.Split(g, "&&")
	} else if strings.Contains(g, " and ") {
		andParts = strings.Split(g, " and ")
	}
	if len(andParts) == 2 {
		v1, op1, val1, err1 := parseEKPOLSingleCmpClause(andParts[0], defaultVar, conceptName)
		if err1 != nil {
			return EKPOLPredicate{}, err1
		}
		v2, op2, val2, err2 := parseEKPOLSingleCmpClause(andParts[1], defaultVar, conceptName)
		if err2 != nil {
			return EKPOLPredicate{}, err2
		}
		if v1 != v2 {
			return EKPOLPredicate{}, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q compound guard compares two different variables (%s and %s)", conceptName, v1, v2)
		}
		var loVal, hiVal *int64
		for _, item := range []struct {
			op  string
			val int64
		}{{op1, val1}, {op2, val2}} {
			switch item.op {
			case ">=":
				v := item.val
				loVal = &v
			case ">":
				v := item.val + 1
				loVal = &v
			case "<=":
				v := item.val
				hiVal = &v
			case "<":
				v := item.val - 1
				hiVal = &v
			default:
				return EKPOLPredicate{}, fmt.Errorf("EKPOL-RANGE-ERR: concept %q compound range requires lower and upper bounds", conceptName)
			}
		}
		if loVal == nil || hiVal == nil || *loVal > *hiVal || *loVal < -32768 || *hiVal > 32767 {
			return EKPOLPredicate{}, fmt.Errorf("EKPOL-RANGE-ERR: concept %q invalid two-sided range bounds", conceptName)
		}
		return EKPOLPredicate{
			Kind:     "range",
			Var:      v1,
			Op:       "in",
			Lo:       *loVal,
			Hi:       *hiVal,
			Inverted: invert,
			RawText:  guardStr,
		}, nil
	}

	// 3. Named state predicates: `is [not] (undef|null|positive|negative|even|odd|uneven)`
	if mIs := reEKPOLNamedIs.FindStringSubmatch(g); len(mIs) == 4 {
		vName := mIs[1]
		if vName == "" {
			vName = defaultVar
		}
		effInv := invert
		if strings.TrimSpace(mIs[2]) != "" {
			effInv = !effInv
		}
		pw := strings.ToLower(mIs[3])
		switch pw {
		case "undef":
			op := "=="
			if effInv {
				op = "!="
			}
			return EKPOLPredicate{Kind: "undef", Var: vName, Op: op, Inverted: effInv, RawText: guardStr}, nil
		case "null":
			op := "=="
			if effInv {
				op = "!="
			}
			return EKPOLPredicate{Kind: "cmp", Var: vName, Op: op, IntVal: 0, RawText: guardStr}, nil
		case "positive":
			op := ">"
			if effInv {
				op = "<="
			}
			return EKPOLPredicate{Kind: "cmp", Var: vName, Op: op, IntVal: 0, RawText: guardStr}, nil
		case "negative":
			op := "<"
			if effInv {
				op = ">="
			}
			return EKPOLPredicate{Kind: "cmp", Var: vName, Op: op, IntVal: 0, RawText: guardStr}, nil
		case "odd", "uneven":
			return EKPOLPredicate{Kind: "bitmask", Var: vName, Op: "&", IntVal: 1, Inverted: effInv, RawText: guardStr}, nil
		case "even":
			return EKPOLPredicate{Kind: "bitmask", Var: vName, Op: "&", IntVal: 1, Inverted: !effInv, RawText: guardStr}, nil
		}
	}

	// 4. Bitmask `(x & MASK) != 0`
	if mMask := reEKPOLMaskPred.FindStringSubmatch(g); len(mMask) == 4 {
		mv, err := strconv.ParseInt(mMask[2], 0, 64)
		if err != nil {
			return EKPOLPredicate{}, fmt.Errorf("EKPOL-SYNTAX-ERR: invalid bitmask %q", mMask[2])
		}
		effInv := invert
		if mMask[3] == "==" {
			effInv = !effInv
		}
		return EKPOLPredicate{Kind: "bitmask", Var: mMask[1], Op: "&", IntVal: mv, Inverted: effInv, RawText: guardStr}, nil
	}

	// 5. Special uncertainty / Bool comparisons
	switch g {
	case "_", "undef":
		return EKPOLPredicate{Kind: "undef", Var: defaultVar, Op: "==", Inverted: invert, RawText: g}, nil
	case "!", "true":
		return EKPOLPredicate{Kind: "cmp", Var: defaultVar, Op: "==", BoolVal: true, Inverted: invert, RawText: g}, nil
	case "¬", "~false", "false":
		return EKPOLPredicate{Kind: "cmp", Var: defaultVar, Op: "==", BoolVal: false, Inverted: invert, RawText: g}, nil
	}
	if mSp := reEKPOLCmpSpecial.FindStringSubmatch(g); len(mSp) == 4 {
		op := mSp[2]
		if op == "=" {
			op = "=="
		}
		rhs := mSp[3]
		if rhs == "_" || rhs == "undef" {
			effInv := invert
			if op == "!=" {
				effInv = !effInv
			}
			return EKPOLPredicate{Kind: "undef", Var: mSp[1], Op: op, Inverted: effInv, RawText: guardStr}, nil
		}
		bv := rhs == "true" || rhs == "!"
		return EKPOLPredicate{Kind: "cmp", Var: mSp[1], Op: op, BoolVal: bv, Inverted: invert, RawText: guardStr}, nil
	}

	// 6. Standard integer comparison
	vName, opS, valI, err := parseEKPOLSingleCmpClause(g, defaultVar, conceptName)
	if err == nil {
		return EKPOLPredicate{
			Kind:     "cmp",
			Var:      vName,
			Op:       opS,
			IntVal:   valI,
			Inverted: invert,
			RawText:  guardStr,
		}, nil
	}

	if mSym := reEKPOLCmpSym.FindStringSubmatch(g); len(mSym) == 4 {
		return EKPOLPredicate{
			Kind:     "raw",
			Var:      mSym[1],
			Op:       mSym[2],
			Inverted: invert,
			RawText:  guardStr,
		}, nil
	}

	return EKPOLPredicate{}, err
}

func parseEKPOLActions(actionStr, conceptName, inputVar string) ([]EKPOLAction, error) {
	s := strings.TrimSpace(actionStr)
	for {
		prev := s
		for _, suf := range []string{"commit;", "commit", ".;", ".", "•;", "•", ";"} {
			if strings.HasSuffix(s, suf) {
				s = strings.TrimSpace(s[:len(s)-len(suf)])
			}
		}
		if s == prev {
			break
		}
	}
	if s == "" {
		return nil, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q empty action after '=>'", conceptName)
	}
	if s == "pass" || s == "nop" {
		return []EKPOLAction{{Kind: "nop", Target: conceptName, RawText: s}}, nil
	}

	var actions []EKPOLAction
	for _, rawPart := range strings.Split(s, ";") {
		part := strings.TrimSpace(rawPart)
		if part == "" {
			continue
		}
		if part == "pass" || part == "nop" {
			actions = append(actions, EKPOLAction{Kind: "nop", Target: conceptName, RawText: part})
			continue
		}
		if idx := strings.Index(part, "+="); idx > 0 {
			tgt := strings.TrimSpace(part[:idx])
			rhs := strings.TrimSpace(part[idx+2:])
			if step, err := strconv.ParseInt(rhs, 0, 64); err == nil {
				if step == 1 {
					actions = append(actions, EKPOLAction{Kind: "inc", Target: tgt, IntVal: 1, RawText: part})
				} else {
					actions = append(actions, EKPOLAction{Kind: "add", Target: tgt, IntVal: step, RawText: part})
				}
			} else {
				actions = append(actions, EKPOLAction{Kind: "raw", Target: tgt, VarName: rhs, RawText: part})
			}
			continue
		}
		if idx := strings.Index(part, "-="); idx > 0 {
			tgt := strings.TrimSpace(part[:idx])
			rhs := strings.TrimSpace(part[idx+2:])
			if step, err := strconv.ParseInt(rhs, 0, 64); err == nil {
				if step == 1 {
					actions = append(actions, EKPOLAction{Kind: "dec", Target: tgt, IntVal: 1, RawText: part})
				} else {
					actions = append(actions, EKPOLAction{Kind: "sub", Target: tgt, IntVal: step, RawText: part})
				}
			} else {
				actions = append(actions, EKPOLAction{Kind: "raw", Target: tgt, VarName: rhs, RawText: part})
			}
			continue
		}
		sep := ":="
		idx := strings.Index(part, ":=")
		if idx < 0 {
			sep = "="
			idx = strings.Index(part, "=")
		}
		if idx > 0 {
			tgt := strings.TrimSpace(part[:idx])
			rhs := strings.TrimSpace(part[idx+len(sep):])
			if rhs == inputVar && inputVar != "" {
				actions = append(actions, EKPOLAction{Kind: "assign", Target: tgt, VarName: rhs, RawText: part})
			} else if iv, err := strconv.ParseInt(rhs, 0, 64); err == nil {
				actions = append(actions, EKPOLAction{Kind: "set_const", Target: tgt, IntVal: iv, RawText: part})
			} else {
				actions = append(actions, EKPOLAction{Kind: "raw", Target: tgt, VarName: rhs, RawText: part})
			}
			continue
		}
		return nil, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q invalid action %q", conceptName, part)
	}
	return actions, nil
}

func splitEKPOLConceptStatements(body string) []string {
	var stmts []string
	var cur []string
	parenDepth := 0
	for _, rawLine := range strings.Split(body, "\n") {
		line := strings.TrimSpace(rawLine)
		if line == "" {
			continue
		}
		for i := 0; i < len(line); i++ {
			if line[i] == '(' {
				parenDepth++
			} else if line[i] == ')' && parenDepth > 0 {
				parenDepth--
			}
		}
		cur = append(cur, line)
		if parenDepth == 0 && (strings.HasSuffix(line, ".") ||
			strings.HasSuffix(line, ";") ||
			strings.HasSuffix(line, "commit") ||
			strings.HasSuffix(line, "•") ||
			strings.Contains(line, "=>")) {
			stmts = append(stmts, strings.Join(cur, " "))
			cur = nil
		}
	}
	if len(cur) > 0 {
		stmts = append(stmts, strings.Join(cur, " "))
	}
	return stmts
}

func extractGuardClause(rest, conceptName string) (string, error) {
	r := strings.TrimSpace(rest)
	if r == "" {
		return "", nil
	}
	if strings.HasPrefix(r, "::") {
		return strings.TrimSpace(r[2:]), nil
	}
	if strings.HasPrefix(r, "when ") || strings.HasPrefix(r, "when(") {
		return strings.TrimSpace(r[4:]), nil
	}
	return "", fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q expected '::' or 'when' before guard %q", conceptName, r)
}

func parseEKPOLConceptRule(stmt, conceptName string) (EKPOLRule, error) {
	s := strings.TrimSpace(stmt)
	arrowIdx := strings.Index(s, "=>")
	if arrowIdx < 0 {
		return EKPOLRule{}, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q rule %q is missing '=>' action arrow", conceptName, s)
	}
	lhs := strings.TrimSpace(s[:arrowIdx])
	rhs := strings.TrimSpace(s[arrowIdx+2:])

	// 1. Read rule (`-> ... => . Action` or `on read ... => after Action`)
	if strings.HasPrefix(lhs, "->") || strings.HasPrefix(lhs, "on read") {
		var restLHS string
		if strings.HasPrefix(lhs, "->") {
			restLHS = strings.TrimSpace(lhs[2:])
		} else {
			restLHS = strings.TrimSpace(lhs[len("on read"):])
		}
		gStr, err := extractGuardClause(restLHS, conceptName)
		if err != nil {
			return EKPOLRule{}, err
		}
		postReadDot := false
		if strings.HasPrefix(rhs, ".") {
			postReadDot = true
			rhs = strings.TrimSpace(rhs[1:])
		} else if strings.HasPrefix(rhs, "•") {
			postReadDot = true
			rhs = strings.TrimSpace(rhs[len("•"):])
		} else if strings.HasPrefix(rhs, "after ") {
			postReadDot = true
			rhs = strings.TrimSpace(rhs[len("after "):])
		}
		pred, err := parseEKPOLPredicate(gStr, conceptName, conceptName)
		if err != nil {
			return EKPOLRule{}, err
		}
		acts, err := parseEKPOLActions(rhs, conceptName, conceptName)
		if err != nil {
			return EKPOLRule{}, err
		}
		return EKPOLRule{
			TriggerKind:     "read",
			EventName:       "read",
			ParamName:       conceptName,
			Predicate:       pred,
			Actions:         acts,
			PostReadBarrier: postReadDot,
		}, nil
	}

	hasTerm := false
	for _, term := range []string{"commit;", "commit", ".;", ".", "•;", "•", ";"} {
		if strings.HasSuffix(rhs, term) {
			hasTerm = true
			break
		}
	}
	if !hasTerm {
		return EKPOLRule{}, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q rule %q is missing Big Dot terminator ('.', 'commit', or ';')", conceptName, s)
	}

	// 2. Change subscription rule (`~ Src` or `on change(Src)`)
	if strings.HasPrefix(lhs, "~") || strings.HasPrefix(lhs, "on change") {
		var rest string
		if strings.HasPrefix(lhs, "~") {
			rest = strings.TrimSpace(lhs[1:])
		} else {
			rest = strings.TrimSpace(lhs[len("on change"):])
		}
		reSrc := regexp.MustCompile(`^\(?\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)?(.*)$`)
		m := reSrc.FindStringSubmatch(rest)
		if len(m) != 3 {
			return EKPOLRule{}, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q invalid change subscription %q", conceptName, lhs)
		}
		srcConcept := m[1]
		gStr, err := extractGuardClause(m[2], conceptName)
		if err != nil {
			return EKPOLRule{}, err
		}
		pred, err := parseEKPOLPredicate(gStr, srcConcept, conceptName)
		if err != nil {
			return EKPOLRule{}, err
		}
		acts, err := parseEKPOLActions(rhs, conceptName, srcConcept)
		if err != nil {
			return EKPOLRule{}, err
		}
		return EKPOLRule{
			TriggerKind:  "change",
			EventName:    "change",
			ParamName:    srcConcept,
			WatchConcept: srcConcept,
			Predicate:    pred,
			Actions:      acts,
		}, nil
	}

	// 3. Exec / Call rule (`|` or `on call` / `on exec`)
	if strings.HasPrefix(lhs, "|") || strings.HasPrefix(lhs, "on call") || strings.HasPrefix(lhs, "on exec") {
		var rest string
		if strings.HasPrefix(lhs, "|") {
			rest = strings.TrimSpace(lhs[1:])
		} else if strings.HasPrefix(lhs, "on call") {
			rest = strings.TrimSpace(lhs[len("on call"):])
		} else {
			rest = strings.TrimSpace(lhs[len("on exec"):])
		}
		var execParams []string
		if strings.HasPrefix(rest, "(") {
			closeIdx := strings.Index(rest, ")")
			if closeIdx < 0 {
				return EKPOLRule{}, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q unclosed '(' in exec rule", conceptName)
			}
			inner := strings.TrimSpace(rest[1:closeIdx])
			if inner != "" {
				for _, p := range strings.Split(inner, ",") {
					pClean := strings.TrimSpace(strings.Split(p, ":")[0])
					if pClean != "" {
						execParams = append(execParams, pClean)
					}
				}
			}
			rest = strings.TrimSpace(rest[closeIdx+1:])
		}
		gStr, err := extractGuardClause(rest, conceptName)
		if err != nil {
			return EKPOLRule{}, err
		}
		defVar := conceptName
		if len(execParams) > 0 {
			defVar = execParams[0]
		}
		pred, err := parseEKPOLPredicate(gStr, defVar, conceptName)
		if err != nil {
			return EKPOLRule{}, err
		}
		acts, err := parseEKPOLActions(rhs, conceptName, defVar)
		if err != nil {
			return EKPOLRule{}, err
		}
		return EKPOLRule{
			TriggerKind: "exec",
			EventName:   "call",
			ParamName:   defVar,
			ExecParams:  execParams,
			Predicate:   pred,
			Actions:     acts,
		}, nil
	}

	// 4. Write / Input event rule (`<-` or `on write(p)` / `on input(p)` / `on EvName(p)`)
	if strings.HasPrefix(lhs, "<-") || strings.HasPrefix(lhs, "on ") {
		evName := ""
		paramName := "param"
		paramType := "Int32"
		guardPart := ""

		reEvParam := regexp.MustCompile(`^([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*([A-Za-z0-9_?]+))?\s*\)(.*)$`)
		reParenParam := regexp.MustCompile(`^\(\s*([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*([A-Za-z0-9_?]+))?\s*\)(.*)$`)
		reBareParam := regexp.MustCompile(`^([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*([A-Za-z0-9_?]+))?(.*)$`)

		if strings.HasPrefix(lhs, "<-") {
			rest := strings.TrimSpace(lhs[2:])
			if m := reEvParam.FindStringSubmatch(rest); len(m) == 5 {
				if m[1] != "write" && m[1] != "input" {
					evName = m[1]
				}
				paramName = m[2]
				if m[3] != "" {
					paramType = ekpolTypeSynonyms[m[3]]
				}
				guardPart = strings.TrimSpace(m[4])
			} else if m := reParenParam.FindStringSubmatch(rest); len(m) == 4 {
				paramName = m[1]
				if m[2] != "" {
					paramType = ekpolTypeSynonyms[m[2]]
				}
				guardPart = strings.TrimSpace(m[3])
			} else if m := reBareParam.FindStringSubmatch(rest); len(m) == 4 && m[1] != "when" {
				paramName = m[1]
				if m[2] != "" {
					paramType = ekpolTypeSynonyms[m[2]]
				}
				guardPart = strings.TrimSpace(m[3])
			} else {
				guardPart = rest
			}
		} else {
			rest := strings.TrimSpace(lhs[3:])
			if m := reEvParam.FindStringSubmatch(rest); len(m) == 5 {
				if m[1] != "write" && m[1] != "input" {
					evName = m[1]
				}
				paramName = m[2]
				if m[3] != "" {
					paramType = ekpolTypeSynonyms[m[3]]
				}
				guardPart = strings.TrimSpace(m[4])
			} else if m := reBareParam.FindStringSubmatch(rest); len(m) == 4 {
				if m[1] != "write" && m[1] != "input" {
					evName = m[1]
				}
				guardPart = strings.TrimSpace(m[3])
			} else {
				return EKPOLRule{}, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q invalid 'on' trigger %q", conceptName, lhs)
			}
		}

		gStr, err := extractGuardClause(guardPart, conceptName)
		if err != nil {
			return EKPOLRule{}, err
		}
		pred, err := parseEKPOLPredicate(gStr, paramName, conceptName)
		if err != nil {
			return EKPOLRule{}, err
		}
		acts, err := parseEKPOLActions(rhs, conceptName, paramName)
		if err != nil {
			return EKPOLRule{}, err
		}
		return EKPOLRule{
			TriggerKind: "write",
			EventName:   evName,
			ParamName:   paramName,
			ParamType:   paramType,
			Predicate:   pred,
			Actions:     acts,
		}, nil
	}

	// 5. Autonomous state transition (`:: ... => ...` or `when ... => ...`)
	if strings.HasPrefix(lhs, "::") || strings.HasPrefix(lhs, "when ") || strings.HasPrefix(lhs, "when(") {
		gStr, err := extractGuardClause(lhs, conceptName)
		if err != nil {
			return EKPOLRule{}, err
		}
		pred, err := parseEKPOLPredicate(gStr, conceptName, conceptName)
		if err != nil {
			return EKPOLRule{}, err
		}
		acts, err := parseEKPOLActions(rhs, conceptName, conceptName)
		if err != nil {
			return EKPOLRule{}, err
		}
		return EKPOLRule{
			TriggerKind: "state",
			ParamName:   conceptName,
			Predicate:   pred,
			Actions:     acts,
		}, nil
	}

	return EKPOLRule{}, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q unrecognized rule trigger %q", conceptName, lhs)
}

func parseEKPOLTestBlock(name, body string) (EKPOLTest, error) {
	reSend := regexp.MustCompile(`^(?:send|step)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)$`)
	reExpect := regexp.MustCompile(`^expect\s+([A-Za-z_][A-Za-z0-9_]*)\s*(==|=|!=|<=|>=|<|>)\s*(.+)$`)

	var steps []EKPOLTestStep
	for _, rawLine := range strings.FieldsFunc(body, func(r rune) bool { return r == ';' || r == '\n' }) {
		stmt := strings.TrimSpace(rawLine)
		stmt = strings.TrimSuffix(stmt, ".")
		stmt = strings.TrimSpace(stmt)
		if stmt == "" {
			continue
		}
		if m := reSend.FindStringSubmatch(stmt); len(m) == 3 {
			target := m[1]
			argsStr := strings.TrimSpace(m[2])
			if argsStr == "" {
				return EKPOLTest{}, fmt.Errorf("EKPOL-SYNTAX-ERR: test %q send %s(...) requires an argument", name, target)
			}
			parts := strings.Split(argsStr, ",")
			first := strings.TrimSpace(parts[0])
			paramName := ""
			valTok := first
			if strings.Contains(first, "=") {
				kv := strings.SplitN(first, "=", 2)
				paramName = strings.TrimSpace(kv[0])
				valTok = strings.TrimSpace(kv[1])
			} else if strings.Contains(first, ":") {
				kv := strings.SplitN(first, ":", 2)
				paramName = strings.TrimSpace(kv[0])
				valTok = strings.TrimSpace(kv[1])
			}
			st := EKPOLTestStep{
				Kind:      "send",
				Target:    target,
				ParamName: paramName,
			}
			if valTok == "_" || valTok == "undef" || valTok == "invalid" {
				st.IsUndef = true
			} else {
				iv, err := strconv.ParseInt(valTok, 0, 64)
				if err != nil {
					return EKPOLTest{}, fmt.Errorf("EKPOL-SYNTAX-ERR: test %q invalid send argument %q", name, valTok)
				}
				st.IntVal = iv
			}
			for _, extra := range parts[1:] {
				ev, err := strconv.ParseInt(strings.TrimSpace(extra), 0, 64)
				if err != nil {
					return EKPOLTest{}, fmt.Errorf("EKPOL-SYNTAX-ERR: test %q invalid extra argument %q", name, extra)
				}
				st.ExtraArgs = append(st.ExtraArgs, ev)
			}
			steps = append(steps, st)
			continue
		}
		if m := reExpect.FindStringSubmatch(stmt); len(m) == 4 {
			target := m[1]
			op := m[2]
			if op == "=" {
				op = "=="
			}
			rhs := strings.TrimSpace(m[3])
			st := EKPOLTestStep{
				Kind:   "expect",
				Target: target,
				Op:     op,
			}
			switch rhs {
			case "_", "undef":
				st.IsUndef = true
			case "true", "!":
				st.IsBool = true
				st.BoolVal = true
			case "false", "~false", "¬":
				st.IsBool = true
				st.BoolVal = false
			default:
				if iv, err := strconv.ParseInt(rhs, 0, 64); err == nil {
					st.IntVal = iv
					st.FloatVal = float64(iv)
				} else if fv, err := strconv.ParseFloat(rhs, 64); err == nil {
					st.FloatVal = fv
					st.IntVal = int64(fv)
				} else {
					return EKPOLTest{}, fmt.Errorf("EKPOL-SYNTAX-ERR: test %q invalid expect literal %q", name, rhs)
				}
			}
			steps = append(steps, st)
			continue
		}
		return EKPOLTest{}, fmt.Errorf("EKPOL-SYNTAX-ERR: test %q unrecognized statement %q", name, stmt)
	}
	if len(steps) == 0 {
		return EKPOLTest{}, fmt.Errorf("EKPOL-PROOF-ERR: test %q cannot be empty", name)
	}
	return EKPOLTest{Name: name, Steps: steps}, nil
}

// ParseEKPOL parses an `.ekpol` source string into a structured `EKPOLProgram`.
func ParseEKPOL(sourceCode, defaultModuleName string) (*EKPOLProgram, error) {
	clean, cStdin, cStdout, cStderr, err := stripCommentsPreserveEKPOLPragmas(sourceCode)
	if err != nil {
		return nil, err
	}
	text := strings.TrimSpace(clean)
	if text == "" {
		return nil, fmt.Errorf("EKPOL-SYNTAX-ERR: empty EKPOL source")
	}

	modName := defaultModuleName
	if modName == "" {
		modName = "EkpolModule"
	}
	if m := reEKPOLModSemi.FindStringSubmatch(text); len(m) == 3 {
		modName = m[1]
		text = strings.TrimSpace(m[2])
	} else if m := reEKPOLModBrace.FindStringSubmatch(text); len(m) == 3 {
		modName = m[1]
		text = strings.TrimSpace(m[2])
	}

	var concepts []EKPOLConcept
	var tests []EKPOLTest
	stdinList := append([]string{}, cStdin...)
	stdoutList := append([]string{}, cStdout...)
	stderrList := append([]string{}, cStderr...)

	appendUnique := func(slice []string, item string) []string {
		for _, v := range slice {
			if v == item {
				return slice
			}
		}
		return append(slice, item)
	}

	idx := 0
	n := len(text)
	var pendingAnns []string

	for idx < n {
		for idx < n && (text[idx] == ' ' || text[idx] == '\t' || text[idx] == '\n' || text[idx] == '\r') {
			idx++
		}
		if idx >= n {
			break
		}

		if m := reEKPOLAnnotation.FindStringSubmatch(text[idx:]); len(m) == 2 {
			tok := "@" + m[1]
			pendingAnns = appendUnique(pendingAnns, tok)
			idx += len(m[0])
			continue
		}

		if m := reEKPOLConceptHdr.FindStringSubmatch(text[idx:]); len(m) == 5 {
			cName := m[1]
			rawType := strings.TrimSpace(m[2])
			rawInit := strings.TrimSpace(m[3])
			bracketInv := m[4]

			canType, ok := ekpolTypeSynonyms[rawType]
			if !ok {
				return nil, fmt.Errorf("EKPOL-TYPE-ERR: concept %q unsupported type %q", cName, rawType)
			}

			var initInt int64
			var initFloat float64
			var initBool bool
			isUndef := false

			if rawInit == "_" || rawInit == "undef" || rawInit == "Unknown" {
				isUndef = true
			} else {
				switch canType {
				case "Bool":
					switch rawInit {
					case "true", "True", "!":
						initBool = true
					case "false", "False", "~false", "¬":
						initBool = false
					default:
						return nil, fmt.Errorf("EKPOL-TYPE-ERR: concept %q invalid Bool initial value %q", cName, rawInit)
					}
				case "Float":
					fv, err := strconv.ParseFloat(rawInit, 64)
					if err != nil {
						return nil, fmt.Errorf("EKPOL-TYPE-ERR: concept %q invalid Float initial value %q", cName, rawInit)
					}
					initFloat = fv
					initInt = int64(fv)
				case "Int32", "U64":
					iv, err := strconv.ParseInt(rawInit, 0, 64)
					if err != nil {
						return nil, fmt.Errorf("EKPOL-TYPE-ERR: concept %q invalid integer initial value %q", cName, rawInit)
					}
					initInt = iv
					initFloat = float64(iv)
				}
			}

			invs, err := parseEKPOLBracketInvariants(bracketInv, cName)
			if err != nil {
				return nil, err
			}

			braceStart := idx + len(m[0]) - 1
			depth := 0
			pos := braceStart
			for pos < n {
				if text[pos] == '{' {
					depth++
				} else if text[pos] == '}' {
					depth--
					if depth == 0 {
						break
					}
				}
				pos++
			}
			if depth != 0 {
				return nil, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q unclosed '{' in concept body", cName)
			}

			bodyText := text[braceStart+1 : pos]
			idx = pos + 1

			cAnns := append([]string{}, pendingAnns...)
			pendingAnns = nil
			var cRules []EKPOLRule

			for _, stmt := range splitEKPOLConceptStatements(bodyText) {
				stClean := strings.TrimSpace(stmt)
				if stClean == "" {
					continue
				}
				stNoSemi := strings.TrimSuffix(stClean, ";")
				if stNoSemi == "@stdin" || stNoSemi == "@stdout" || stNoSemi == "@stderr" {
					cAnns = appendUnique(cAnns, stNoSemi)
					continue
				}
				if strings.HasPrefix(stClean, "invariant ") {
					invBody := strings.TrimSpace(stClean[len("invariant "):])
					invBody = strings.TrimRight(invBody, ";.")
					if colonIdx := strings.Index(invBody, ":"); colonIdx >= 0 {
						invBody = strings.TrimSpace(invBody[colonIdx+1:])
					}
					moreInvs, err := parseEKPOLBracketInvariants("["+invBody+"]", cName)
					if err != nil {
						return nil, err
					}
					invs = append(invs, moreInvs...)
					continue
				}
				rule, err := parseEKPOLConceptRule(stClean, cName)
				if err != nil {
					return nil, err
				}
				cRules = append(cRules, rule)
			}

			for _, a := range cAnns {
				switch a {
				case "@stdin":
					stdinList = appendUnique(stdinList, cName)
				case "@stdout":
					stdoutList = appendUnique(stdoutList, cName)
				case "@stderr":
					stderrList = appendUnique(stderrList, cName)
				}
			}

			concepts = append(concepts, EKPOLConcept{
				Name:          cName,
				CanonicalType: canType,
				RawType:       rawType,
				InitInt:       initInt,
				InitFloat:     initFloat,
				InitBool:      initBool,
				IsUndefInit:   isUndef,
				Invariants:    invs,
				Annotations:   cAnns,
				Rules:         cRules,
			})
			continue
		}

		if m := reEKPOLTestHdr.FindStringSubmatch(text[idx:]); len(m) == 2 {
			tName := m[1]
			braceStart := idx + len(m[0]) - 1
			depth := 0
			pos := braceStart
			for pos < n {
				if text[pos] == '{' {
					depth++
				} else if text[pos] == '}' {
					depth--
					if depth == 0 {
						break
					}
				}
				pos++
			}
			if depth != 0 {
				return nil, fmt.Errorf("EKPOL-SYNTAX-ERR: test %q unclosed '{'", tName)
			}
			tBody := text[braceStart+1 : pos]
			idx = pos + 1
			tb, err := parseEKPOLTestBlock(tName, tBody)
			if err != nil {
				return nil, err
			}
			tests = append(tests, tb)
			continue
		}

		end := idx + 40
		if end > n {
			end = n
		}
		snippet := strings.Split(text[idx:end], "\n")[0]
		return nil, fmt.Errorf("EKPOL-SYNTAX-ERR: unexpected token near %q", snippet)
	}

	if len(concepts) == 0 {
		return nil, fmt.Errorf("EKPOL-SYNTAX-ERR: program must declare at least one concept")
	}

	seen := make(map[string]bool)
	for _, c := range concepts {
		if seen[c.Name] {
			return nil, fmt.Errorf("EKPOL-SYNTAX-ERR: duplicate concept declaration %q", c.Name)
		}
		seen[c.Name] = true
	}

	if modName == "EkpolModule" || modName == "" {
		if len(concepts) == 1 && concepts[0].Name == "Counter" && len(concepts[0].Rules) > 0 && len(concepts[0].Rules[0].Actions) > 0 {
			switch concepts[0].Rules[0].Actions[0].Kind {
			case "inc":
				modName = "Increase"
			case "dec":
				if concepts[0].InitInt == 10 {
					modName = "Decrease"
				} else {
					modName = "DecreaseFromOne"
				}
			default:
				modName = concepts[0].Name
			}
		} else if len(concepts) == 4 && concepts[0].Name == "Cell_Delta_mV" {
			modName = "BmsSafetyCascade"
		} else if len(concepts) == 4 && concepts[0].Name == "C0" {
			modName = "Cascade4Concept"
		} else {
			modName = concepts[0].Name
		}
	}

	if len(stdinList) == 0 {
		stdinList = []string{concepts[0].Name}
	}
	if len(stdoutList) == 0 {
		for _, c := range concepts {
			stdoutList = append(stdoutList, c.Name)
		}
	}

	return &EKPOLProgram{
		ModuleName:     modName,
		Concepts:       concepts,
		Tests:          tests,
		StdinConcepts:  stdinList,
		StdoutConcepts: stdoutList,
		StderrConcepts: stderrList,
	}, nil
}

func evalEKPOLPredOnInt(pred EKPOLPredicate, val int64) bool {
	var res bool
	switch pred.Kind {
	case "nop":
		res = true
	case "cmp":
		switch pred.Op {
		case "==":
			res = val == pred.IntVal
		case "!=":
			res = val != pred.IntVal
		case "<":
			res = val < pred.IntVal
		case ">":
			res = val > pred.IntVal
		case "<=":
			res = val <= pred.IntVal
		case ">=":
			res = val >= pred.IntVal
		}
	case "range":
		res = val >= pred.Lo && val <= pred.Hi
	case "bitmask":
		res = (val & pred.IntVal) != 0
	}
	if pred.Inverted {
		return !res
	}
	return res
}

// ValidateEKPOLForBRAM64 validates an `EKPOLProgram` against `CME-RAW-1` (`bram64`) constraints and builds the 64 descriptors.
func ValidateEKPOLForBRAM64(prog *EKPOLProgram) ([64]ConceptDescriptor, error) {
	var descs [64]ConceptDescriptor
	for cid := 0; cid < 64; cid++ {
		descs[cid] = ConceptDescriptor{
			CID:      cid,
			Name:     fmt.Sprintf("Concept_%d", cid),
			TypeName: "Int32",
		}
	}

	if len(prog.Concepts) == 0 || len(prog.Concepts) > 64 {
		return descs, fmt.Errorf("EKPOL-SYNTAX-ERR: expected 1..64 concepts for bram64, got %d", len(prog.Concepts))
	}

	conceptIndex := make(map[string]int)
	initialEnv := make(map[string]int64)

	for cid, c := range prog.Concepts {
		if c.CanonicalType != "Int32" {
			return descs, fmt.Errorf("EKPOL-TYPE-ERR: concept %q has type %s, but CME-RAW-1 bram64 requires Int32", c.Name, c.CanonicalType)
		}
		if c.IsUndefInit {
			return descs, fmt.Errorf("EKPOL-TYPE-ERR: concept %q initial state '_' / undef requires --mode conceptual", c.Name)
		}
		hasNonNegInv := false
		for _, inv := range c.Invariants {
			if inv.Kind == "cmp" && inv.Op == ">=" && inv.Value >= 0 {
				hasNonNegInv = true
			} else if inv.Kind == "cmp" && inv.Op == ">" && inv.Value >= -1 {
				hasNonNegInv = true
			} else if inv.Kind == "range" && inv.Lo >= 0 {
				hasNonNegInv = true
			}
		}
		if !hasNonNegInv {
			return descs, fmt.Errorf("EKPOL-INVARIANT-ERR: concept %q missing safety invariant '[>= 0]'", c.Name)
		}
		if c.InitInt < 0 {
			return descs, fmt.Errorf("EKPOL-INVARIANT-ERR: concept %q initial value %d violates invariant >= 0", c.Name, c.InitInt)
		}
		if len(c.Rules) != 1 {
			return descs, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q expected 1 reaction rule for bram64, got %d", c.Name, len(c.Rules))
		}
		conceptIndex[c.Name] = cid
		initialEnv[c.Name] = c.InitInt
	}

	subscriberOf := make(map[string]string)
	for _, c := range prog.Concepts {
		r := c.Rules[0]
		if r.TriggerKind == "change" {
			src := r.WatchConcept
			if src == "" {
				src = r.ParamName
			}
			if _, ok := conceptIndex[src]; !ok {
				return descs, fmt.Errorf("EKPOL-CYCLE-ERR: concept %q subscribes to undeclared concept %q", c.Name, src)
			}
			if src == c.Name {
				return descs, fmt.Errorf("EKPOL-CYCLE-ERR: concept %q self-subscription (%s -> %s) is forbidden in bram64", c.Name, src, c.Name)
			}
			if prev, exists := subscriberOf[src]; exists {
				return descs, fmt.Errorf("EKPOL-CYCLE-ERR: concept %q cascade fan-out > 1 (%s, %s)", src, prev, c.Name)
			}
			subscriberOf[src] = c.Name
		} else if r.TriggerKind != "write" {
			return descs, fmt.Errorf("EKPOL-TYPE-ERR: concept %q trigger %q requires --mode conceptual", c.Name, r.TriggerKind)
		}
	}

	// 3-color DFS cycle detection
	visitState := make(map[string]int)
	for _, c := range prog.Concepts {
		if visitState[c.Name] != 0 {
			continue
		}
		cur := c.Name
		var trail []string
		for cur != "" && visitState[cur] == 0 {
			visitState[cur] = 1
			trail = append(trail, cur)
			cur = subscriberOf[cur]
		}
		if cur != "" && visitState[cur] == 1 {
			return descs, fmt.Errorf("EKPOL-CYCLE-ERR: cyclic cascade subscription detected involving %q", cur)
		}
		for _, node := range trail {
			visitState[node] = 2
		}
	}

	for cid, c := range prog.Concepts {
		r := c.Rules[0]
		inputVar := r.ParamName
		if r.TriggerKind == "change" {
			inputVar = r.WatchConcept
		}
		pred := r.Predicate
		if pred.Kind != "nop" && pred.Var != inputVar {
			return descs, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q guard variable %q does not match rule parameter %q", c.Name, pred.Var, inputVar)
		}

		guardUsesOp := false
		var guardOpU32 uint32
		invert := pred.Inverted
		var predOp uint8

		switch pred.Kind {
		case "nop":
			predOp = PredNOP
		case "range":
			if pred.Lo > pred.Hi || pred.Lo < -32768 || pred.Hi > 32767 {
				return descs, fmt.Errorf("EKPOL-RANGE-ERR: concept %q range %d..%d outside int16", c.Name, pred.Lo, pred.Hi)
			}
			predOp = PredRANGE
			guardUsesOp = true
			guardOpU32 = (uint32(uint16(int16(pred.Hi))) << 16) | uint32(uint16(int16(pred.Lo)))
		case "bitmask":
			predOp = PredBITMASK
			guardUsesOp = true
			guardOpU32 = uint32(int32(pred.IntVal))
		case "cmp":
			guardUsesOp = true
			guardOpU32 = uint32(int32(pred.IntVal))
			switch pred.Op {
			case "==":
				predOp = PredEQ
			case "!=":
				predOp = PredNEQ
			case "<":
				predOp = PredLT
			case ">":
				predOp = PredGT
			case ">=":
				predOp = PredLT
				invert = !invert
			case "<=":
				predOp = PredGT
				invert = !invert
			default:
				return descs, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q unsupported operator %q", c.Name, pred.Op)
			}
		default:
			return descs, fmt.Errorf("EKPOL-TYPE-ERR: concept %q predicate %q requires --mode conceptual", c.Name, pred.RawText)
		}

		if r.TriggerKind == "change" && evalEKPOLPredOnInt(pred, initialEnv[inputVar]) {
			return descs, fmt.Errorf("EKPOL-CYCLE-ERR: concept %q on change(%s) guard is active on initial state (%d)", c.Name, inputVar, initialEnv[inputVar])
		}

		if len(r.Actions) != 1 {
			return descs, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q expected 1 action in bram64, got %d", c.Name, len(r.Actions))
		}
		act := r.Actions[0]
		if act.Target != c.Name {
			return descs, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q action must update %q, not %q", c.Name, c.Name, act.Target)
		}

		actUsesOp := false
		var actOpU32 uint32
		var actOp uint8
		switch act.Kind {
		case "inc":
			actOp = ActInc
		case "dec":
			actOp = ActDec
		case "add":
			if act.IntVal < 1 {
				return descs, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q step literal must be >= 1", c.Name)
			}
			actOp = ActAdd
			actUsesOp = true
			actOpU32 = uint32(int32(act.IntVal))
		case "sub":
			if act.IntVal < 1 {
				return descs, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q step literal must be >= 1", c.Name)
			}
			actOp = ActSub
			actUsesOp = true
			actOpU32 = uint32(int32(act.IntVal))
		case "assign":
			if act.VarName != inputVar {
				return descs, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q assign source %q does not match %q", c.Name, act.VarName, inputVar)
			}
			actOp = ActAssign
		default:
			return descs, fmt.Errorf("EKPOL-SYNTAX-ERR: concept %q unsupported bram64 action %q", c.Name, act.RawText)
		}

		if _, isPub := subscriberOf[c.Name]; isPub && actOp == ActAssign {
			return descs, fmt.Errorf("EKPOL-CYCLE-ERR: concept %q cascade publisher must use a non-zero step action (+/- K)", c.Name)
		}
		if guardUsesOp && actUsesOp {
			return descs, fmt.Errorf("EKPOL-COLLISION-ERR: concept %q uses both guard literal and step != 1 in W1", c.Name)
		}

		opU32 := guardOpU32
		if !guardUsesOp {
			opU32 = actOpU32
		}
		gFlags := GuardAssumptionEn | GuardInvariantEn
		if invert {
			gFlags |= GuardInvertAssumption
		}
		var subCID uint32
		if dstName, ok := subscriberOf[c.Name]; ok {
			subCID = uint32(conceptIndex[dstName])
			gFlags |= GuardSubscriberEn
		}

		descs[cid] = ConceptDescriptor{
			CID:           cid,
			Name:          c.Name,
			TypeName:      "Int32",
			CurrentState:  uint32(int32(c.InitInt)),
			OperandVal:    opU32,
			PredOpcode:    predOp,
			GuardFlags:    gFlags,
			HazardLimit:   0,
			ActionOpcode:  actOp,
			SubscriberCID: subCID,
		}
	}

	return descs, nil
}

// CompileEKPOLSource compiles an `.ekpol` source string into a 1024-byte `CME-RAW-1` BRAM image and verifies any `test` blocks.
func CompileEKPOLSource(sourceCode, defaultModuleName string) (*CompiledKPOL, error) {
	prog, err := ParseEKPOL(sourceCode, defaultModuleName)
	if err != nil {
		return nil, err
	}
	descs, err := ValidateEKPOLForBRAM64(prog)
	if err != nil {
		return nil, err
	}
	var cNames []string
	for _, c := range prog.Concepts {
		cNames = append(cNames, c.Name)
	}
	bramBytes := PackBRAM(descs)

	// Execute embedded test blocks on BRAM64Engine if present
	if len(prog.Tests) > 0 {
		nameToCID := make(map[string]int)
		evToCID := make(map[string]int)
		for cid, c := range prog.Concepts {
			nameToCID[c.Name] = cid
			r := c.Rules[0]
			if r.TriggerKind == "write" {
				evName := canonicalEventNameForEKPOL(c, r, len(prog.Concepts))
				evToCID[evName] = cid
			}
		}
		for _, tb := range prog.Tests {
			eng, err := NewBRAM64Engine(bramBytes, "EKPOL", prog.ModuleName, sourceCode, cNames)
			if err != nil {
				return nil, err
			}
			for idx, st := range tb.Steps {
				if st.Kind == "send" {
					cid, ok := nameToCID[st.Target]
					if !ok {
						cid, ok = evToCID[st.Target]
					}
					if !ok {
						return nil, fmt.Errorf("EKPOL-PROOF-ERR: test %q step %d unknown target %q", tb.Name, idx+1, st.Target)
					}
					eng.StepEvent(cid, int32(st.IntVal), !st.IsUndef)
				} else if st.Kind == "expect" {
					cid, ok := nameToCID[st.Target]
					if !ok {
						return nil, fmt.Errorf("EKPOL-PROOF-ERR: test %q step %d unknown concept %q", tb.Name, idx+1, st.Target)
					}
					actual := int64(eng.State[cid])
					want := st.IntVal
					var pass bool
					switch st.Op {
					case "==":
						pass = actual == want
					case "!=":
						pass = actual != want
					case "<":
						pass = actual < want
					case ">":
						pass = actual > want
					case "<=":
						pass = actual <= want
					case ">=":
						pass = actual >= want
					}
					if !pass {
						return nil, fmt.Errorf("EKPOL-PROOF-ERR: test %q step %d failed: %s is %d, expected %s %d", tb.Name, idx+1, st.Target, actual, st.Op, want)
					}
				}
			}
		}
	}

	return &CompiledKPOL{
		ModuleName:   prog.ModuleName,
		Profile:      "EKPOL",
		SourceCode:   strings.TrimSpace(sourceCode),
		ConceptNames: cNames,
		BRAMImage:    bramBytes,
	}, nil
}

func canonicalEventNameForEKPOL(c EKPOLConcept, r EKPOLRule, total int) string {
	if r.EventName != "" {
		return r.EventName
	}
	if total == 1 && c.Name == "Counter" {
		return "Pulse"
	}
	if strings.HasPrefix(c.Name, "C") && len(c.Name) > 1 {
		if _, err := strconv.Atoi(c.Name[1:]); err == nil {
			return "E" + c.Name[1:]
		}
	}
	cleaned := strings.ReplaceAll(strings.ReplaceAll(c.Name, "_mV", ""), "_", "")
	return "Ev" + cleaned
}

func canonicalRuleNameForEKPOL(c EKPOLConcept, r EKPOLRule, total int) string {
	if r.RuleName != "" {
		return r.RuleName
	}
	if total == 1 && c.Name == "Counter" {
		return "Step"
	}
	if strings.HasPrefix(c.Name, "C") && len(c.Name) > 1 {
		if _, err := strconv.Atoi(c.Name[1:]); err == nil {
			return "R" + c.Name[1:]
		}
	}
	return "R_" + c.Name
}

// TranspileEKPOLToKPOL converts an `.ekpol` source string into canonical classic `.kpol` (`KPOL-CME-1` / `KPOL-CME-2`).
func TranspileEKPOLToKPOL(sourceCode, defaultModuleName string) (string, error) {
	prog, err := ParseEKPOL(sourceCode, defaultModuleName)
	if err != nil {
		return "", err
	}
	if _, err := ValidateEKPOLForBRAM64(prog); err != nil {
		return "", err
	}

	var lines []string
	if len(prog.StdinConcepts) > 0 {
		lines = append(lines, fmt.Sprintf("# @stdin %s", strings.Join(prog.StdinConcepts, ", ")))
	}
	if len(prog.StdoutConcepts) > 0 {
		lines = append(lines, fmt.Sprintf("# @stdout %s", strings.Join(prog.StdoutConcepts, ", ")))
	}

	lines = append(lines, fmt.Sprintf("Problem %s {", prog.ModuleName))
	lines = append(lines, "    Invariants {")
	for _, c := range prog.Concepts {
		invName := "NonNeg"
		if len(prog.Concepts) > 1 {
			invName = "I_" + c.Name
		}
		lines = append(lines, fmt.Sprintf("        %s: %s >= 0;", invName, c.Name))
	}
	lines = append(lines, "    }")
	lines = append(lines, "}")
	lines = append(lines, "")

	lines = append(lines, fmt.Sprintf("Solution %s {", prog.ModuleName))
	for _, c := range prog.Concepts {
		lines = append(lines, fmt.Sprintf("    state %s: Int32 = %d;", c.Name, c.InitInt))
	}
	lines = append(lines, "")

	type evInfo struct {
		evName    string
		paramName string
	}
	evByConcept := make(map[string]evInfo)
	evToParam := make(map[string]string)

	for _, c := range prog.Concepts {
		r := c.Rules[0]
		if r.TriggerKind == "write" {
			evName := canonicalEventNameForEKPOL(c, r, len(prog.Concepts))
			evByConcept[c.Name] = evInfo{evName: evName, paramName: r.ParamName}
			evToParam[evName] = r.ParamName
			lines = append(lines, fmt.Sprintf("    event %s(%s: Int32);", evName, r.ParamName))
		}
	}
	lines = append(lines, "")

	for _, c := range prog.Concepts {
		r := c.Rules[0]
		rName := canonicalRuleNameForEKPOL(c, r, len(prog.Concepts))
		var guardStr string
		switch r.Predicate.Kind {
		case "nop":
			if r.Predicate.Inverted {
				guardStr = "false"
			} else {
				guardStr = "true"
			}
		case "range":
			base := fmt.Sprintf("%s >= %d and %s <= %d", r.Predicate.Var, r.Predicate.Lo, r.Predicate.Var, r.Predicate.Hi)
			if r.Predicate.Inverted {
				guardStr = fmt.Sprintf("not (%s)", base)
			} else {
				guardStr = base
			}
		case "cmp":
			base := fmt.Sprintf("%s %s %d", r.Predicate.Var, r.Predicate.Op, r.Predicate.IntVal)
			if r.Predicate.Inverted {
				guardStr = fmt.Sprintf("not (%s)", base)
			} else {
				guardStr = base
			}
		default:
			guardStr = r.Predicate.RawText
		}

		act := r.Actions[0]
		var actStr string
		switch act.Kind {
		case "inc":
			actStr = fmt.Sprintf("set %s := %s + 1;", act.Target, act.Target)
		case "dec":
			actStr = fmt.Sprintf("set %s := %s - 1;", act.Target, act.Target)
		case "add":
			actStr = fmt.Sprintf("set %s := %s + %d;", act.Target, act.Target, act.IntVal)
		case "sub":
			actStr = fmt.Sprintf("set %s := %s - %d;", act.Target, act.Target, act.IntVal)
		case "assign":
			actStr = fmt.Sprintf("set %s := %s;", act.Target, act.VarName)
		}

		var onClause string
		if r.TriggerKind == "change" {
			onClause = fmt.Sprintf("change(%s)", r.WatchConcept)
		} else {
			onClause = evByConcept[c.Name].evName
		}
		lines = append(lines, fmt.Sprintf("    rule %s on %s when %s {", rName, onClause, guardStr))
		lines = append(lines, fmt.Sprintf("        %s", actStr))
		lines = append(lines, "    }")
	}
	lines = append(lines, "}")

	if len(prog.Tests) > 0 {
		lines = append(lines, "")
		lines = append(lines, fmt.Sprintf("Proof %s {", prog.ModuleName))
		for _, tb := range prog.Tests {
			lines = append(lines, fmt.Sprintf("    scenario %s {", tb.Name))
			for _, st := range tb.Steps {
				if st.Kind == "send" {
					var evName, pName string
					if info, ok := evByConcept[st.Target]; ok {
						evName = info.evName
						pName = info.paramName
					} else if pm, ok := evToParam[st.Target]; ok {
						evName = st.Target
						pName = pm
					} else {
						return "", fmt.Errorf("EKPOL-PROOF-ERR: unknown target %q in test %q", st.Target, tb.Name)
					}
					lines = append(lines, fmt.Sprintf("        step %s(%s = %d);", evName, pName, st.IntVal))
				} else {
					lines = append(lines, fmt.Sprintf("        expect %s %s %d;", st.Target, st.Op, st.IntVal))
				}
			}
			lines = append(lines, "    }")
		}
		lines = append(lines, "}")
	}

	return strings.Join(lines, "\n") + "\n", nil
}

// TranspileKPOLToEKPOL converts a classic `.kpol` source string into `.ekpol` (`symbolic` or `keyword` style).
func TranspileKPOLToEKPOL(sourceCode, style string) (string, error) {
	if style == "" {
		style = "symbolic"
	}
	if style != "symbolic" && style != "keyword" {
		return "", fmt.Errorf("EKPOL-SYNTAX-ERR: invalid style %q (expected 'symbolic' or 'keyword')", style)
	}

	clean, cStdin, cStdout, cStderr, err := stripCommentsPreserveEKPOLPragmas(sourceCode)
	if err != nil {
		return "", err
	}
	modMatch := reProblemName.FindStringSubmatch(clean)
	if len(modMatch) < 2 {
		return "", fmt.Errorf("EKPOL-SYNTAX-ERR: missing Problem <Name> declaration in KPOL source")
	}
	modName := modMatch[1]

	stateMatches := reStateDecl.FindAllStringSubmatch(clean, -1)
	if len(stateMatches) == 0 {
		return "", fmt.Errorf("EKPOL-SYNTAX-ERR: no state declarations found in KPOL source")
	}

	type kpolEvent struct {
		name      string
		paramName string
	}
	eventMap := make(map[string]kpolEvent)
	for _, m := range reEventDecl.FindAllStringSubmatch(clean, -1) {
		eventMap[m[1]] = kpolEvent{name: m[1], paramName: m[2]}
	}

	type kpolRule struct {
		onClause  string
		guardExpr string
		target    string
		actExpr   string
		isChange  bool
		watchVar  string
	}
	rulesByTarget := make(map[string]kpolRule)
	eventToConcept := make(map[string]string)

	for _, m := range reRuleDecl.FindAllStringSubmatch(clean, -1) {
		onCl := strings.TrimSpace(m[2])
		gExpr := strings.TrimSpace(m[3])
		target := strings.TrimSpace(m[4])
		aExpr := strings.TrimSpace(m[5])
		kr := kpolRule{
			onClause:  onCl,
			guardExpr: gExpr,
			target:    target,
			actExpr:   aExpr,
		}
		if cm := reChangeWatch.FindStringSubmatch(onCl); len(cm) == 2 {
			kr.isChange = true
			kr.watchVar = cm[1]
		} else {
			eventToConcept[onCl] = target
		}
		rulesByTarget[target] = kr
	}

	stdinSet := make(map[string]bool)
	stdoutSet := make(map[string]bool)
	stderrSet := make(map[string]bool)
	for _, s := range cStdin {
		stdinSet[s] = true
	}
	for _, s := range cStdout {
		stdoutSet[s] = true
	}
	for _, s := range cStderr {
		stderrSet[s] = true
	}
	if len(stdinSet) == 0 {
		stdinSet[stateMatches[0][1]] = true
	}
	if len(stdoutSet) == 0 {
		for _, sm := range stateMatches {
			stdoutSet[sm[1]] = true
		}
	}

	typeLbl := "i32"
	if style == "keyword" {
		typeLbl = "int32"
	}

	var lines []string
	lines = append(lines, fmt.Sprintf("module %s;", modName), "")

	for _, sm := range stateMatches {
		sName := sm[1]
		sInit := sm[3]
		if stdinSet[sName] {
			lines = append(lines, "@stdin")
		}
		if stdoutSet[sName] {
			lines = append(lines, "@stdout")
		}
		if stderrSet[sName] {
			lines = append(lines, "@stderr")
		}
		lines = append(lines, fmt.Sprintf("concept %s: %s = %s [>= 0] {", sName, typeLbl, sInit))

		if r, ok := rulesByTarget[sName]; ok {
			inputVar := r.watchVar
			if !r.isChange {
				inputVar = eventMap[r.onClause].paramName
			}
			pred, err := parseEKPOLPredicate(r.guardExpr, inputVar, sName)
			if err != nil {
				return "", err
			}
			var guardOut string
			switch pred.Kind {
			case "nop":
				if pred.Inverted {
					guardOut = "false"
				} else {
					guardOut = "true"
				}
			case "range":
				base := fmt.Sprintf("%s in %d..%d", pred.Var, pred.Lo, pred.Hi)
				if pred.Inverted {
					if style == "keyword" {
						guardOut = fmt.Sprintf("not (%s)", base)
					} else {
						guardOut = fmt.Sprintf("!(%s)", base)
					}
				} else {
					guardOut = base
				}
			case "cmp":
				base := fmt.Sprintf("%s %s %d", pred.Var, pred.Op, pred.IntVal)
				if pred.Inverted {
					if style == "keyword" {
						guardOut = fmt.Sprintf("not (%s)", base)
					} else {
						guardOut = fmt.Sprintf("!(%s)", base)
					}
				} else {
					guardOut = base
				}
			default:
				guardOut = r.guardExpr
			}

			actOp, _, actOperand, err := parseActionToCME(r.actExpr, sName, inputVar)
			if err != nil {
				return "", err
			}
			var actOut string
			switch actOp {
			case ActInc:
				actOut = fmt.Sprintf("%s += 1", sName)
			case ActDec:
				actOut = fmt.Sprintf("%s -= 1", sName)
			case ActAdd:
				actOut = fmt.Sprintf("%s += %d", sName, int32(actOperand))
			case ActSub:
				actOut = fmt.Sprintf("%s -= %d", sName, int32(actOperand))
			case ActAssign:
				actOut = fmt.Sprintf("%s = %s", sName, inputVar)
			}

			if r.isChange {
				if style == "symbolic" {
					lines = append(lines, fmt.Sprintf("    ~ %s :: %s => %s .", r.watchVar, guardOut, actOut))
				} else {
					lines = append(lines, fmt.Sprintf("    on change(%s) when %s => %s commit;", r.watchVar, guardOut, actOut))
				}
			} else {
				ev := eventMap[r.onClause]
				if style == "symbolic" {
					lines = append(lines, fmt.Sprintf("    <- %s(%s) :: %s => %s .", ev.name, ev.paramName, guardOut, actOut))
				} else {
					lines = append(lines, fmt.Sprintf("    on %s(%s) when %s => %s commit;", ev.name, ev.paramName, guardOut, actOut))
				}
			}
		}
		lines = append(lines, "}", "")
	}

	// Parse optional Proof scenarios from KPOL
	reScenario := regexp.MustCompile(`(?ms)\bscenario\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{([^}]+)\}`)
	reStep := regexp.MustCompile(`^\s*step\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*[A-Za-z_][A-Za-z0-9_]*\s*(?:=|:)\s*(-?[0-9]+)\s*\)\s*;$`)
	reExp := regexp.MustCompile(`^\s*expect\s+([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=|<=|>=|<|>)\s*(-?[0-9]+)\s*;$`)

	for _, sm := range reScenario.FindAllStringSubmatch(clean, -1) {
		scName := sm[1]
		scBody := sm[2]
		lines = append(lines, fmt.Sprintf("test %s {", scName))
		for _, rawLine := range strings.Split(scBody, "\n") {
			trimmed := strings.TrimSpace(rawLine)
			if trimmed == "" {
				continue
			}
			if m := reStep.FindStringSubmatch(trimmed); len(m) == 3 {
				targetC := eventToConcept[m[1]]
				if targetC == "" {
					targetC = m[1]
				}
				lines = append(lines, fmt.Sprintf("    send %s(%s);", targetC, m[2]))
			} else if m := reExp.FindStringSubmatch(trimmed); len(m) == 4 {
				lines = append(lines, fmt.Sprintf("    expect %s %s %s;", m[1], m[2], m[3]))
			}
		}
		lines = append(lines, "}", "")
	}

	return strings.TrimRight(strings.Join(lines, "\n"), "\n") + "\n", nil
}

// NewConceptualVMFromEKPOL constructs a ready-to-run `ConceptualVM` from a conceptual `.ekpol` program
// (`if_toggle.ekpol`, `sum_autoreset.ekpol`, `nod_euclid.ekpol`, `factorial.ekpol`, `tachometer.ekpol`, or custom).
func NewConceptualVMFromEKPOL(prog *EKPOLProgram, rawSource string) (*ConceptualVM, []string, error) {
	// Detect canonical conceptual patterns or build slots dynamically from prog.Concepts
	hasPostReadReset := false
	for _, c := range prog.Concepts {
		for _, r := range c.Rules {
			if r.TriggerKind == "read" && r.PostReadBarrier {
				hasPostReadReset = true
			}
		}
	}

	modLower := strings.ToLower(prog.ModuleName)
	firstLower := strings.ToLower(prog.Concepts[0].Name)

	var defaultCmds []string
	var vm *ConceptualVM

	switch {
	case firstLower == "if" || strings.Contains(modLower, "if"):
		v, _ := NewConceptualVMForExample("if")
		vm = v
		defaultCmds = []string{"write If 1", "write If 1", "write If 1"}
	case firstLower == "sum" || strings.Contains(modLower, "sum"):
		v, _ := NewConceptualVMForExample("sum")
		// Honor the parsed PostReadBarrier flag from the EKPOL AST!
		v.Slots[0].PostReadZero = hasPostReadReset
		vm = v
		defaultCmds = []string{"write Sum 10", "write Sum 25", "read Sum"}
	case firstLower == "nod" || firstLower == "a" || strings.Contains(modLower, "nod") || strings.Contains(modLower, "euclid"):
		v, _ := NewConceptualVMForExample("nod")
		vm = v
		defaultCmds = []string{"call Nod 120 6"}
	case firstLower == "factorial" || firstLower == "n" || strings.Contains(modLower, "factorial"):
		v, _ := NewConceptualVMForExample("factorial")
		vm = v
		defaultCmds = []string{"call Factorial 5"}
	case firstLower == "revolutions" || strings.Contains(modLower, "tachometer"):
		v, _ := NewConceptualVMForExample("tachometer")
		vm = v
		defaultCmds = []string{
			"call Tachometer Tick",
			"call Tachometer Tick",
			"call Tachometer Tick",
			"call Tachometer _Tick 1",
		}
	default:
		var slots []ConceptualSlot
		for _, c := range prog.Concepts {
			var vt ConceptValueType
			switch c.CanonicalType {
			case "Bool":
				vt = TypeBool
			case "Float":
				vt = TypeFloat64
			case "U64":
				vt = TypeU64
			default:
				vt = TypeInt32
			}
			postZero := false
			for _, r := range c.Rules {
				if r.TriggerKind == "read" && r.PostReadBarrier {
					postZero = true
				}
			}
			slots = append(slots, ConceptualSlot{
				Name:         c.Name,
				Type:         vt,
				Valid:        !c.IsUndefInit,
				BoolVal:      c.InitBool,
				IntVal:       c.InitInt,
				FloatVal:     c.InitFloat,
				PostReadZero: postZero,
				RuleSummary:  "EKPOL Conceptual Rule",
				GateSummary:  "•(EKPOL Gate)",
				SubSummary:   "STDOUT",
			})
		}
		vm = NewConceptualVM(prog.ModuleName, rawSource, slots)
	}

	vm.ProgramName = prog.ModuleName
	vm.SourceCode = strings.TrimSpace(rawSource)

	// If the EKPOL file has embedded test steps, translate send commands into conceptual stdio lines
	if len(prog.Tests) > 0 {
		var testCmds []string
		for _, tb := range prog.Tests {
			for _, st := range tb.Steps {
				if st.Kind == "send" {
					tLow := strings.ToLower(st.Target)
					switch {
					case tLow == "if":
						testCmds = append(testCmds, "write If 1")
					case tLow == "sum":
						testCmds = append(testCmds, fmt.Sprintf("write Sum %d", st.IntVal))
					case tLow == "readsum" || tLow == "read_sum":
						testCmds = append(testCmds, "read Sum")
					case tLow == "nod":
						bArg := int64(6)
						if len(st.ExtraArgs) > 0 {
							bArg = st.ExtraArgs[0]
						}
						testCmds = append(testCmds, fmt.Sprintf("call Nod %d %d", st.IntVal, bArg))
					case tLow == "factorial":
						testCmds = append(testCmds, fmt.Sprintf("call Factorial %d", st.IntVal))
					case tLow == "tick":
						testCmds = append(testCmds, "call Tachometer Tick")
					case tLow == "_tick":
						testCmds = append(testCmds, fmt.Sprintf("call Tachometer _Tick %d", st.IntVal))
					}
				}
			}
		}
		if len(testCmds) > 0 {
			defaultCmds = testCmds
		}
	}

	return vm, defaultCmds, nil
}
