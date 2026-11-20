package kpol

import (
	"fmt"
	"math/big"
	"strings"
)

// reservedWords are the 45 reserved words of KPOL-LEX-5.
var reservedWords = map[string]bool{
	"Problem": true, "Solution": true, "Proof": true, "Assumptions": true, "Invariants": true,
	"Hazards": true, "Alerts": true, "Goals": true,
	"event": true, "state": true, "rule": true, "on": true, "reject": true, "change": true,
	"when": true, "covers": true, "set": true, "to": true,
	"Bool": true, "Int32": true, "U32": true, "U64": true, "Float": true, "Pin": true, "Void": true,
	"true": true, "false": true, "Unknown": true, "gcd": true, "and": true, "or": true, "not": true,
	"assert": true, "scenario": true, "step": true, "expect": true,
	"every": true, "within": true, "timeout": true, "supervise": true,
	"channel": true, "Rendezvous": true, "Stream": true, "send": true, "receive": true,
}

// IsReserved reports whether w is one of the 45 reserved words (KPOL-LEX-5).
func IsReserved(w string) bool { return reservedWords[w] }

// maxExprDepth bounds expression nesting; the reference fails with Python's
// recursion limit long before.
const maxExprDepth = 10000

var validUnits = map[string]bool{
	"V": true, "A": true, "W": true, "s": true, "J": true, "degC": true, "bar": true,
	"ns": true, "us": true, "ms": true, "min": true, "h": true, "mm_s": true, "L_min": true,
}

type parseFailure struct{ err error }

type parser struct {
	toks  []Token
	idx   int
	depth int
}

func (p *parser) tok() Token { return p.toks[p.idx] }

func (p *parser) fail(format string, a ...any) {
	t := p.tok()
	panic(parseFailure{&Error{Msg: fmt.Sprintf("%d:%d: %s", t.Line, t.Column, fmt.Sprintf(format, a...))}})
}

func (p *parser) accept(v string) bool {
	if p.tok().Value == v {
		p.idx++
		return true
	}
	return false
}

func (p *parser) expect(v string) {
	if !p.accept(v) {
		p.fail("expected %s, got %s", pyRepr(v), pyRepr(p.tok().Value))
	}
}

func (p *parser) identifier() string {
	t := p.tok()
	if t.Kind != TokID {
		p.fail("expected identifier")
	}
	if reservedWords[t.Value] {
		p.fail("reserved keyword %s cannot be an identifier", pyRepr(t.Value))
	}
	p.idx++
	return t.Value
}

// ParseUnchecked lexes and parses src without the static checks of Check
// (reference: Parser(source).parse()). It reports KPOL-LEX-* and KPOL-SYN-*
// violations as "line:column: message" errors.
func ParseUnchecked(src string) (m *Module, err error) {
	toks, err := Tokenize(src)
	if err != nil {
		return nil, err
	}
	p := &parser{toks: toks}
	defer func() {
		if r := recover(); r != nil {
			pf, ok := r.(parseFailure)
			if !ok {
				panic(r)
			}
			m, err = nil, pf.err
		}
	}()
	return p.parseModule(), nil
}

// ParseSyntax is a synonym of ParseUnchecked.
func ParseSyntax(src string) (*Module, error) { return ParseUnchecked(src) }

var sectionKinds = map[string]string{
	"Assumptions": KindAssumption,
	"Invariants":  KindInvariant,
	"Hazards":     KindHazard,
	"Alerts":      KindAlert,
	"Goals":       KindGoal,
}

func (p *parser) parseModule() *Module {
	p.expect("Problem")
	name := p.identifier()
	p.expect("{")
	m := &Module{Name: name}
	seen := map[string]bool{}
	for !p.accept("}") {
		if p.tok().Kind != TokID {
			p.fail("expected Problem section")
		}
		section := p.tok().Value
		p.idx++
		kind, ok := sectionKinds[section]
		if !ok {
			p.fail("unknown Problem section %s", pyRepr(section))
		}
		if seen[section] {
			p.fail("duplicate Problem section %s", pyRepr(section))
		}
		seen[section] = true
		p.expect("{")
		for !p.accept("}") {
			req := Requirement{Kind: kind, Name: p.identifier()}
			if p.accept("on") {
				req.Event = p.identifier()
			}
			if p.accept("to") {
				req.Target = p.identifier()
			}
			p.expect(":")
			req.Expression = p.expression(0)
			p.expect(";")
			m.Requirements = append(m.Requirements, req)
		}
	}

	p.expect("Solution")
	if sol := p.identifier(); sol != name {
		p.fail("Problem/Solution name mismatch: %s vs %s", pyRepr(name), pyRepr(sol))
	}
	p.expect("{")
	for !p.accept("}") {
		switch {
		case p.accept("event"):
			m.Events = append(m.Events, p.eventDecl())
		case p.accept("state"):
			m.States = append(m.States, p.stateDecl())
		case p.accept("rule"):
			m.Rules = append(m.Rules, p.rule())
		default:
			p.fail("expected event, state, or rule declaration")
		}
	}

	m.ProofPresent = p.accept("Proof")
	if m.ProofPresent {
		if pn := p.identifier(); pn != name {
			p.fail("Problem/Proof name mismatch: %s vs %s", pyRepr(name), pyRepr(pn))
		}
		p.expect("{")
		for !p.accept("}") {
			switch {
			case p.accept("assert"):
				m.Proofs = append(m.Proofs, p.assertDecl())
			case p.accept("scenario"):
				m.Proofs = append(m.Proofs, p.scenarioDecl())
			default:
				p.fail("expected 'assert' or 'scenario' in Proof block")
			}
		}
	}

	if p.tok().Kind != TokEOF {
		p.fail("unexpected text after module")
	}
	for _, t := range p.toks {
		if t.Kind == TokAliasPhase {
			m.PhaseAliasesUsed = true
			break
		}
	}
	return m
}

func (p *parser) assertDecl() AssertProperty {
	a := AssertProperty{Name: p.identifier()}
	p.expect("on")
	a.Event = p.identifier()
	hasBlock := p.accept("{")
	a.Guard = BoolLit{true}
	if p.accept("when") {
		a.Guard = p.expression(0)
	}
	p.expect("expect")
	a.Expectation = p.expression(0)
	p.expect(";")
	if hasBlock {
		p.expect("}")
	}
	return a
}

func (p *parser) scenarioDecl() Scenario {
	s := Scenario{Name: p.identifier()}
	p.expect("{")
	for !p.accept("}") {
		switch {
		case p.accept("step"):
			st := StepAction{Event: p.identifier()}
			p.expect("(")
			if !p.accept(")") {
				for {
					argName := p.identifier()
					if !(p.accept(":") || p.accept("=")) {
						p.fail("expected ':' or '=' in step argument")
					}
					st.Args = append(st.Args, Arg{Name: argName, Value: p.expression(0)})
					if p.accept(")") {
						break
					}
					p.expect(",")
				}
			}
			p.expect(";")
			s.Items = append(s.Items, st)
		case p.accept("expect"):
			e := p.expression(0)
			p.expect(";")
			s.Items = append(s.Items, ExpectCheck{e})
		default:
			p.fail("expected 'step' or 'expect' inside scenario")
		}
	}
	return s
}

func (p *parser) eventDecl() EventDecl {
	ev := EventDecl{Name: p.identifier()}
	p.expect("(")
	if !p.accept(")") {
		for {
			name := p.identifier()
			p.expect(":")
			ev.Params = append(ev.Params, Param{Name: name, Type: p.typeRef()})
			if p.accept(")") {
				break
			}
			p.expect(",")
		}
	}
	p.expect(";")
	return ev
}

func (p *parser) typeRef() TypeRef {
	if p.tok().Kind != TokID {
		p.fail("expected type")
	}
	name := p.tok().Value
	p.idx++
	switch name {
	case "Float":
		p.expect("<")
		unit := p.identifier()
		p.expect(">")
		if !validUnits[unit] {
			p.fail("unknown unit %s", pyRepr(unit))
		}
		return TypeRef{Name: name, Unit: unit}
	case "Pin":
		if p.accept("<") {
			parts := []string{p.identifier()}
			for p.accept(",") {
				parts = append(parts, p.identifier())
			}
			p.expect(">")
			return TypeRef{Name: name, PinParams: parts}
		}
		return TypeRef{Name: name}
	case "Bool", "Int32", "U32", "U64":
		return TypeRef{Name: name}
	}
	p.fail("unknown type %s", pyRepr(name))
	return TypeRef{}
}

func (p *parser) stateDecl() StateDecl {
	s := StateDecl{Name: p.identifier()}
	p.expect(":")
	s.Type = p.typeRef()
	p.expect("=")
	s.Initial = p.expression(0)
	p.expect(";")
	return s
}

func (p *parser) rule() Rule {
	r := Rule{Name: p.identifier()}
	p.expect("on")
	r.Reject = p.accept("reject")
	if p.accept("change") {
		r.Event = "change"
	} else {
		r.Event = p.identifier()
	}
	if r.Event == "change" {
		p.expect("(")
		r.Watch = []string{p.identifier()}
		for p.accept(",") {
			r.Watch = append(r.Watch, p.identifier())
		}
		p.expect(")")
	}
	r.Guard = BoolLit{true}
	if p.accept("when") {
		r.Guard = p.expression(0)
	}
	if p.accept("covers") {
		r.Covers = p.identifier()
	}
	p.expect("{")
	for !p.accept("}") {
		p.expect("set")
		target := p.identifier()
		p.expect(":=")
		r.Actions = append(r.Actions, SetAction{Name: target, Expression: p.expression(0)})
		p.expect(";")
	}
	return r
}

func precedence(op string) (int, bool) {
	switch op {
	case "or":
		return 1, true
	case "and":
		return 2, true
	case "==", "!=", "<", "<=", ">", ">=":
		return 3, true
	case "+", "-":
		return 4, true
	case "*", "/":
		return 5, true
	}
	return 0, false
}

// expression parses with precedence climbing; minimum is the lowest binding
// power accepted (KPOL-SYN-5: unary operators bind tighter than any binary one).
func (p *parser) expression(minimum int) Expr {
	p.depth++
	defer func() { p.depth-- }()
	if p.depth > maxExprDepth {
		panic(parseFailure{&Error{Code: CodeParseDepth, Msg: fmt.Sprintf("%d:%d: expression nesting is too deep", p.tok().Line, p.tok().Column)}})
	}
	t := p.tok()
	var left Expr
	switch {
	case t.Value == "not" || t.Value == "-" || t.Kind == TokAliasPhase:
		p.idx++
		op := t.Value
		if t.Kind == TokAliasPhase {
			op = "not"
		}
		left = Unary{Op: op, X: p.expression(6)}
	case t.Value == "(":
		p.idx++
		left = p.expression(0)
		p.expect(")")
	case t.Kind == TokNumber:
		p.idx++
		left = p.number(t)
	case t.Kind == TokID:
		p.idx++
		switch {
		case t.Value == "true":
			left = BoolLit{true}
		case t.Value == "false":
			left = BoolLit{false}
		case t.Value == "Unknown":
			left = UnknownLit{}
		case t.Value == "gcd" && p.accept("("):
			first := p.expression(0)
			p.expect(",")
			second := p.expression(0)
			p.expect(")")
			left = Call{Name: "gcd", Args: []Expr{first, second}}
		default:
			left = Name{t.Value}
		}
	default:
		p.fail("expected expression")
	}
	for {
		op := p.tok().Value
		prec, ok := precedence(op)
		if !ok || prec < minimum {
			break
		}
		p.idx++
		right := p.expression(prec + 1)
		left = Binary{Op: op, L: left, R: right}
	}
	return left
}

// number converts a NUMBER token; like the reference it accepts every Unicode
// decimal digit and fails on digits that are not decimal (D-K1).
func (p *parser) number(t Token) Expr {
	var b strings.Builder
	hasDot := false
	for _, r := range t.Value {
		switch {
		case r == '.':
			hasDot = true
			b.WriteByte('.')
		case pyIsDecimal(r):
			b.WriteByte(byte('0' + pyDecimalValue(r)))
		default:
			if hasDot || strings.ContainsRune(t.Value, '.') {
				panic(parseFailure{&Error{Msg: fmt.Sprintf("%d:%d: invalid number", t.Line, t.Column)}})
			}
			panic(parseFailure{&Error{Code: CodeRTValue, Msg: fmt.Sprintf("%d:%d: ValueError: invalid literal for int() with base 10: %s", t.Line, t.Column, pyRepr(t.Value))}})
		}
	}
	text := b.String()
	if hasDot {
		return DecLit{Text: text}
	}
	if len(text) > maxIntStrDigits {
		panic(parseFailure{&Error{Code: CodeRTValue, Msg: fmt.Sprintf("%d:%d: ValueError: Exceeds the limit (%d digits) for integer string conversion", t.Line, t.Column, maxIntStrDigits)}})
	}
	n, _ := new(big.Int).SetString(text, 10)
	return IntLit{V: n}
}
