package ekpol

import (
	"math/big"
	"slices"
	"strings"
	"unicode/utf8"
)

const identRe = `[A-Za-z_][A-Za-z0-9_]*`

var (
	reModuleSemi  = pyRe(`(?s)^module\s+(` + identRe + `)\s*;\s*(.*)$`)
	reModuleBrace = pyRe(`(?s)^module\s+(` + identRe + `)\s*\{(.*)\}\s*$`)
	reConcept     = pyRe(`^concept\s+(` + identRe + `)\s*:\s*([A-Za-z0-9_?]+)\s*=\s*([^\[\{\n]+?)(\s*\[[^\]]*\])?\s*\{`)
	reTestHeader  = pyRe(`^(?:test|scenario)\s+(` + identRe + `)\s*\{`)
	reInvClause   = pyRe(`^(?:(` + identRe + `)\s*)?(>=|<=|==|!=|>|<)\s*(-?[0-9]+)$`)
)

func isIdent(s string) bool {
	if s == "" {
		return false
	}
	for i := 0; i < len(s); i++ {
		c := s[i]
		ok := c == '_' || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z')
		if i > 0 {
			ok = ok || isASCIIDigit(c)
		}
		if !ok {
			return false
		}
	}
	return true
}

// canonicalType maps a type spelling to its canonical type (EKPOL-LEX-3).
func canonicalType(raw string) (string, bool) {
	switch raw {
	case "i32", "int32", "Int32":
		return TypeInt32, true
	case "u64", "uint64", "U64":
		return TypeU64, true
	case "f64", "float64", "Float":
		return TypeFloat, true
	case "bool", "Bool", "?":
		return TypeBool, true
	}
	return "", false
}

// canonOrSelf is TYPE_SYNONYMS.get(raw, raw).
func canonOrSelf(raw string) string {
	if c, ok := canonicalType(raw); ok {
		return c
	}
	return raw
}

// stripComments removes block and line comments and collects the STDIO pragmas (EKPOL-PRE-2..4).
func stripComments(source string) (clean string, stdin, stdout, stderr []string, err error) {
	extract := func(body string) {
		b := pyStrip(body)
		var dst *[]string
		var rest string
		switch {
		case strings.HasPrefix(b, "@stdin"):
			dst, rest = &stdin, b[len("@stdin"):]
		case strings.HasPrefix(b, "@stdout"):
			dst, rest = &stdout, b[len("@stdout"):]
		case strings.HasPrefix(b, "@stderr"):
			dst, rest = &stderr, b[len("@stderr"):]
		default:
			return
		}
		for _, t := range pyFields(strings.ReplaceAll(rest, ",", " ")) {
			if isIdent(t) {
				*dst = append(*dst, t)
			}
		}
	}

	var noBlock strings.Builder
	i := 0
	for i < len(source) {
		if strings.HasPrefix(source[i:], "/*") {
			end := strings.Index(source[i+2:], "*/")
			if end < 0 {
				return "", nil, nil, nil, syntaxErr("unterminated /* ... */ block comment")
			}
			end += i + 2
			noBlock.WriteString(strings.Repeat("\n", strings.Count(source[i:end+2], "\n")))
			i = end + 2
			continue
		}
		noBlock.WriteByte(source[i])
		i++
	}

	lines := pySplitLines(noBlock.String())
	for k, line := range lines {
		cut, markerLen := len(line), 0
		for _, m := range []string{"//", "#"} {
			if pos := strings.Index(line, m); pos >= 0 && pos < cut {
				cut, markerLen = pos, len(m)
			}
		}
		if cut < len(line) {
			extract(line[cut+markerLen:])
			lines[k] = line[:cut]
		}
	}
	return strings.Join(lines, "\n"), stdin, stdout, stderr, nil
}

// parseIntLiteral is _parse_int_literal.
func parseIntLiteral(text, code string) (*big.Int, error) {
	v, ok := pyInt0(text)
	if !ok {
		return nil, newErr(code, "invalid integer literal %s", pyRepr(text))
	}
	return v, nil
}

func parseInitValue(rawInit, canon, concept string) (Value, bool, error) {
	s := pyStrip(rawInit)
	if s == "_" || s == "undef" || s == "Unknown" {
		return UndefValue(), true, nil
	}
	switch canon {
	case TypeBool:
		switch s {
		case "true", "True", "!":
			return BoolValue(true), false, nil
		case "false", "False", "~false", "¬":
			return BoolValue(false), false, nil
		}
		return Value{}, false, newErr(CodeType, "concept %s: invalid Bool initial value %s (expected true, false, !, ~false, or _/undef)", pyRepr(concept), pyRepr(rawInit))
	case TypeFloat:
		if s == "true" || s == "false" || s == "!" {
			return Value{}, false, newErr(CodeType, "concept %s: expected Float initial value, got %s", pyRepr(concept), pyRepr(rawInit))
		}
		f, ok := pyFloat(s)
		if !ok {
			return Value{}, false, newErr(CodeType, "concept %s: invalid Float initial value %s", pyRepr(concept), pyRepr(rawInit))
		}
		return FloatValue(f), false, nil
	case TypeInt32, TypeU64:
		if s == "true" || s == "false" || s == "!" || s == "~false" || strings.Contains(s, ".") {
			return Value{}, false, newErr(CodeType, "concept %s: expected integer initial value for %s, got %s", pyRepr(concept), canon, pyRepr(rawInit))
		}
		v, ok := pyInt0(s)
		if !ok {
			return Value{}, false, newErr(CodeType, "concept %s: invalid integer initial value %s", pyRepr(concept), pyRepr(rawInit))
		}
		if canon == TypeU64 && (v.Sign() < 0 || v.BitLen() > 64) {
			return Value{}, false, newErr(CodeType, "concept %s: U64 initial value %s out of range", pyRepr(concept), v.String())
		}
		if canon == TypeInt32 && (v.Cmp(big.NewInt(-1<<31)) < 0 || v.Cmp(big.NewInt(1<<31-1)) > 0) {
			return Value{}, false, newErr(CodeType, "concept %s: Int32 initial value %s out of range", pyRepr(concept), v.String())
		}
		return IntValue(v), false, nil
	}
	return Value{}, false, newErr(CodeType, "concept %s: unsupported type %s", pyRepr(concept), pyRepr(canon))
}

// parseBracketInvariants parses "[...]" invariant clauses (EKPOL-STA-2).
func parseBracketInvariants(bracket, concept string) ([]Invariant, error) {
	if bracket == "" {
		return nil, nil
	}
	inner := pyStrip(bracket)
	if strings.HasPrefix(inner, "[") && strings.HasSuffix(inner, "]") {
		inner = pyStrip(inner[1 : len(inner)-1])
	}
	if inner == "" {
		return nil, newErr(CodeInvariant, "concept %s: empty invariant brackets '[]'", pyRepr(concept))
	}
	var invs []Invariant
	for _, part := range strings.Split(inner, ",") {
		clause := pyStrip(part)
		if clause == "" {
			continue
		}
		if lo, hi, ok := strings.Cut(clause, ".."); ok {
			loV, err := parseIntLiteral(lo, CodeInvariant)
			if err != nil {
				return nil, err
			}
			hiV, err := parseIntLiteral(hi, CodeInvariant)
			if err != nil {
				return nil, err
			}
			if loV.Cmp(hiV) > 0 {
				return nil, newErr(CodeInvariant, "concept %s: inverted invariant range [%s..%s]", pyRepr(concept), loV, hiV)
			}
			invs = append(invs, Invariant{Kind: "range", Op: "..", Lo: loV, Hi: hiV, Value: loV})
			continue
		}
		m := find(reInvClause, clause)
		if m == nil {
			return nil, newErr(CodeInvariant, "concept %s: invalid invariant clause %s", pyRepr(concept), pyRepr(clause))
		}
		if m.has(1) && m.group(1) != concept {
			return nil, newErr(CodeInvariant, "concept %s: invariant references foreign concept %s", pyRepr(concept), pyRepr(m.group(1)))
		}
		v, err := parseIntLiteral(m.group(3), CodeInvariant)
		if err != nil {
			return nil, err
		}
		invs = append(invs, Invariant{Kind: "cmp", Op: m.group(2), Value: v})
	}
	return invs, nil
}

// splitConceptStatements splits a concept body into statements (EKPOL-SEG-1).
func splitConceptStatements(body string) []string {
	var statements []string
	var cur []string
	depth := 0
	for _, raw := range pySplitLines(body) {
		line := pyStrip(raw)
		if line == "" {
			continue
		}
		for i := 0; i < len(line); i++ {
			switch line[i] {
			case '(':
				depth++
			case ')':
				if depth > 0 {
					depth--
				}
			}
		}
		cur = append(cur, line)
		if depth == 0 && (strings.HasSuffix(line, ".") || strings.HasSuffix(line, ";") ||
			strings.HasSuffix(line, "commit") || strings.HasSuffix(line, "•") || strings.Contains(line, "=>")) {
			statements = append(statements, strings.Join(cur, " "))
			cur = nil
		}
	}
	if len(cur) > 0 {
		statements = append(statements, strings.Join(cur, " "))
	}
	return statements
}

// matchBrace returns the index of the "}" closing the "{" at open, or -1.
func matchBrace(text string, open int) int {
	depth := 0
	for pos := open; pos < len(text); pos++ {
		switch text[pos] {
		case '{':
			depth++
		case '}':
			depth--
			if depth == 0 {
				return pos
			}
		}
	}
	return -1
}

func firstNRunes(s string, n int) string {
	end := 0
	for i := 0; i < n && end < len(s); i++ {
		_, w := utf8.DecodeRuneInString(s[end:])
		end += w
	}
	return s[:end]
}

// Parse parses an EKPOL 0.1.0 program (symbolic, keyword or mixed notation).
// defaultModuleName is used when the source has no "module" header; when it equals
// "EkpolModule" the reference's name heuristics (EKPOL-STA-3) apply.
func Parse(src, defaultModuleName string) (*Program, error) {
	clean, stdinList, stdoutList, stderrList, err := stripComments(src)
	if err != nil {
		return nil, err
	}
	text := pyStrip(clean)
	if text == "" {
		return nil, syntaxErr("empty EKPOL source")
	}

	moduleName := defaultModuleName
	if m := find(reModuleSemi, text); m != nil {
		moduleName = m.group(1)
		text = pyStrip(m.group(2))
	} else if m := find(reModuleBrace, text); m != nil {
		moduleName = m.group(1)
		text = pyStrip(m.group(2))
	}

	var concepts []Concept
	var tests []Test
	var pending []string

	idx := 0
	for idx < len(text) {
		r, w := utf8.DecodeRuneInString(text[idx:])
		if pyIsSpace(r) {
			idx += w
			continue
		}
		rest := text[idx:]

		if strings.HasPrefix(rest, "@") {
			matched := ""
			for _, name := range []string{"stdin", "stdout", "stderr"} {
				if strings.HasPrefix(rest[1:], name) && atWordEnd(rest, 1+len(name)) {
					matched = name
					break
				}
			}
			if matched != "" {
				tok := "@" + matched
				if !slices.Contains(pending, tok) {
					pending = append(pending, tok)
				}
				idx += 1 + len(matched)
				continue
			}
		}

		if m := find(reConcept, rest); m != nil {
			c, end, err := parseConceptDecl(text, idx, m, pending)
			if err != nil {
				return nil, err
			}
			pending = nil
			idx = end
			for _, a := range c.Annotations {
				switch a {
				case "@stdin":
					if !slices.Contains(stdinList, c.Name) {
						stdinList = append(stdinList, c.Name)
					}
				case "@stdout":
					if !slices.Contains(stdoutList, c.Name) {
						stdoutList = append(stdoutList, c.Name)
					}
				case "@stderr":
					if !slices.Contains(stderrList, c.Name) {
						stderrList = append(stderrList, c.Name)
					}
				}
			}
			concepts = append(concepts, *c)
			continue
		}

		if m := find(reTestHeader, rest); m != nil {
			if len(pending) > 0 {
				return nil, syntaxErr("dangling annotations %s before test block", pyReprList(pending))
			}
			name := m.group(1)
			braceStart := idx + m.end() - 1
			pos := matchBrace(text, braceStart)
			if pos < 0 {
				return nil, syntaxErr("test %s: unclosed '{' in test block", pyRepr(name))
			}
			t, err := parseTestBlock(name, text[braceStart+1:pos])
			if err != nil {
				return nil, err
			}
			tests = append(tests, *t)
			idx = pos + 1
			continue
		}

		snippet := pySplitLines(firstNRunes(rest, 40))[0]
		return nil, syntaxErr("unexpected token near %s", pyRepr(snippet))
	}

	if len(concepts) == 0 {
		return nil, syntaxErr("program must declare at least one concept")
	}
	seen := map[string]bool{}
	for i := range concepts {
		if seen[concepts[i].Name] {
			return nil, syntaxErr("duplicate concept declaration %s", pyRepr(concepts[i].Name))
		}
		seen[concepts[i].Name] = true
	}

	if moduleName == "EkpolModule" {
		moduleName = heuristicModuleName(concepts)
	}
	if len(stdinList) == 0 {
		stdinList = []string{concepts[0].Name}
	}
	if len(stdoutList) == 0 {
		for i := range concepts {
			stdoutList = append(stdoutList, concepts[i].Name)
		}
	}
	return &Program{
		ModuleName:     moduleName,
		Concepts:       concepts,
		Tests:          tests,
		StdinConcepts:  stdinList,
		StdoutConcepts: stdoutList,
		StderrConcepts: stderrList,
	}, nil
}

func heuristicModuleName(concepts []Concept) string {
	if len(concepts) == 1 {
		c0 := &concepts[0]
		if c0.Name == "Counter" && len(c0.Rules) > 0 && len(c0.Rules[0].Actions) > 0 {
			switch c0.Rules[0].Actions[0].Kind {
			case ActInc:
				return "Increase"
			case ActDec:
				if c0.Initial.equalsInt(10) {
					return "Decrease"
				}
				return "DecreaseFromOne"
			}
		}
		return c0.Name
	}
	names := make([]string, len(concepts))
	for i := range concepts {
		names[i] = concepts[i].Name
	}
	switch {
	case slices.Equal(names, []string{"Cell_Delta_mV", "Module_Thermal_Guard", "Pack_Fault_Latch", "Contactor_Interlock"}):
		return "BmsSafetyCascade"
	case slices.Equal(names, []string{"C0", "C1", "C2", "C3"}):
		return "Cascade4Concept"
	}
	return concepts[0].Name
}

// parseConceptDecl parses a concept whose header matched m at text[idx:]; it returns the
// concept and the offset just past its closing brace.
func parseConceptDecl(text string, idx int, m *reMatch, pending []string) (*Concept, int, error) {
	name := m.group(1)
	rawType := pyStrip(m.group(2))
	rawInit := pyStrip(m.group(3))
	bracket := m.group(4)

	canon, ok := canonicalType(rawType)
	if !ok {
		return nil, 0, newErr(CodeType, "concept %s: unsupported type %s (expected i32/int32/Int32, u64/uint64/U64, f64/float64/Float, or bool/Bool/?)", pyRepr(name), pyRepr(rawType))
	}
	initVal, undef, err := parseInitValue(rawInit, canon, name)
	if err != nil {
		return nil, 0, err
	}
	invs, err := parseBracketInvariants(bracket, name)
	if err != nil {
		return nil, 0, err
	}

	braceStart := idx + m.end() - 1
	pos := matchBrace(text, braceStart)
	if pos < 0 {
		return nil, 0, syntaxErr("concept %s: unclosed '{' in concept body", pyRepr(name))
	}
	body := text[braceStart+1 : pos]

	anns := append([]string(nil), pending...)
	var rules []Rule
	for _, stmt := range splitConceptStatements(body) {
		st := pyStrip(stmt)
		if st == "" {
			continue
		}
		switch st {
		case "@stdin", "@stdout", "@stderr", "@stdin;", "@stdout;", "@stderr;":
			a := strings.TrimRight(st, ";")
			if !slices.Contains(anns, a) {
				anns = append(anns, a)
			}
			continue
		}
		if strings.HasPrefix(st, "invariant ") {
			invBody := pyStrip(strings.TrimRight(st[len("invariant "):], ";."))
			if _, after, ok := strings.Cut(invBody, ":"); ok {
				invBody = pyStrip(after)
			}
			more, err := parseBracketInvariants("["+invBody+"]", name)
			if err != nil {
				return nil, 0, err
			}
			invs = append(invs, more...)
			continue
		}
		rule, err := parseConceptRule(st, name)
		if err != nil {
			return nil, 0, err
		}
		rules = append(rules, *rule)
	}

	return &Concept{
		Name:        name,
		Type:        canon,
		RawType:     rawType,
		Initial:     initVal,
		UndefInit:   undef,
		Invariants:  invs,
		Annotations: anns,
		Rules:       rules,
	}, pos + 1, nil
}
