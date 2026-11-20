package ekpol

import (
	"math/big"
	"strings"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

// pyNum is a Python int that may in fact be a bool (bool is an int subclass), which
// changes how it prints.
type pyNum struct {
	v      *big.Int
	isBool bool
}

func (n pyNum) String() string {
	if n.isBool {
		if n.v.Sign() != 0 {
			return "True"
		}
		return "False"
	}
	return n.v.String()
}

func (n pyNum) plus(d int64) pyNum { return pyNum{v: new(big.Int).Add(n.v, big.NewInt(d))} }

// literalValue returns the runtime value of a literal node.
func literalValue(e kpol.Expr) (kpol.Value, bool) {
	switch e.(type) {
	case kpol.IntLit, kpol.DecLit, kpol.BoolLit, kpol.UnknownLit:
		v, err := kpol.EvalExpr(e, nil)
		if err != nil {
			return nil, false
		}
		return v, true
	}
	return nil, false
}

func isLiteral(e kpol.Expr) bool {
	_, ok := literalValue(e)
	return ok
}

// literalStr is str(Literal.value).
func literalStr(e kpol.Expr) string {
	v, _ := literalValue(e)
	return kpol.FormatValue(v)
}

// exprRepr reproduces the dataclass repr of a reference AST node.
func exprRepr(e kpol.Expr) string {
	switch x := e.(type) {
	case kpol.Name:
		return "Name(value=" + pyRepr(x.Name) + ")"
	case kpol.Unary:
		op := x.Op
		if op == "•" || op == "(*)" {
			op = "not"
		}
		return "Unary(operator=" + pyRepr(op) + ", operand=" + exprRepr(x.X) + ")"
	case kpol.Binary:
		return "Binary(operator=" + pyRepr(x.Op) + ", left=" + exprRepr(x.L) + ", right=" + exprRepr(x.R) + ")"
	case kpol.Call:
		args := make([]string, len(x.Args))
		for i, a := range x.Args {
			args[i] = exprRepr(a)
		}
		tuple := "(" + strings.Join(args, ", ")
		if len(args) == 1 {
			tuple += ","
		}
		return "Call(name=" + pyRepr(x.Name) + ", arguments=" + tuple + "))"
	}
	v, _ := literalValue(e)
	return "Literal(value=" + kpol.ReprValue(v) + ")"
}

func unaryOp(u kpol.Unary) string {
	if u.Op == "•" || u.Op == "(*)" {
		return "not"
	}
	return u.Op
}

// intOfLiteral is int(Literal.value); ok is false for Unknown (TypeError in Python).
func intOfLiteral(e kpol.Expr) (*big.Int, bool) {
	switch x := e.(type) {
	case kpol.IntLit:
		return x.V, true
	case kpol.BoolLit:
		if x.V {
			return big.NewInt(1), true
		}
		return big.NewInt(0), true
	case kpol.DecLit:
		intPart, _, _ := strings.Cut(x.Text, ".")
		v, ok := new(big.Int).SetString(intPart, 10)
		return v, ok
	}
	return nil, false
}

// evalLit is _eval_lit of the reference.
func evalLit(node kpol.Expr) (pyNum, error) {
	switch x := node.(type) {
	case kpol.IntLit:
		return pyNum{v: x.V}, nil
	case kpol.BoolLit:
		n := pyNum{v: big.NewInt(0), isBool: true}
		if x.V {
			n.v = big.NewInt(1)
		}
		return n, nil
	case kpol.Unary:
		if unaryOp(x) == "-" && isLiteral(x.X) {
			v, ok := intOfLiteral(x.X)
			if !ok {
				return pyNum{}, internalErr("unhandled reference exception TypeError: int() argument must be a string, a bytes-like object or a real number, not '_Unknown'")
			}
			return pyNum{v: new(big.Int).Neg(v)}, nil
		}
	}
	return pyNum{}, syntaxErr("unsupported guard literal %s", exprRepr(node))
}

func normCmp(node kpol.Binary) (string, string, pyNum, error) {
	if n, ok := node.L.(kpol.Name); ok {
		v, err := evalLit(node.R)
		return n.Name, node.Op, v, err
	}
	if n, ok := node.R.(kpol.Name); ok {
		flipped, known := flipCmpOp(node.Op)
		if !known {
			return "", "", pyNum{}, internalErr("unhandled reference exception KeyError: %s", pyRepr(node.Op))
		}
		v, err := evalLit(node.L)
		return n.Name, flipped, v, err
	}
	return "", "", pyNum{}, syntaxErr("invalid comparison %s", exprRepr(node))
}

func negated(base, style string) string {
	if style == "keyword" {
		return "not (" + base + ")"
	}
	return "!(" + base + ")"
}

// kpolGuardToEKPOL renders a KPOL guard in EKPOL (section 10.2).
func kpolGuardToEKPOL(expr kpol.Expr, style string) (string, error) {
	invert := false
	cur := expr
	for {
		u, ok := cur.(kpol.Unary)
		if !ok {
			break
		}
		if op := unaryOp(u); op != "not" && op != "!" {
			break
		}
		invert = !invert
		cur = u.X
	}

	if b, ok := cur.(kpol.BoolLit); ok {
		val := b.V
		if invert {
			val = !val
		}
		if val {
			return "true", nil
		}
		return "false", nil
	}

	if b, ok := cur.(kpol.Binary); ok && b.Op == "and" {
		l, lok := b.L.(kpol.Binary)
		r, rok := b.R.(kpol.Binary)
		if lok && rok {
			v1, op1, val1, err := normCmp(l)
			if err != nil {
				return "", err
			}
			v2, op2, val2, err := normCmp(r)
			if err != nil {
				return "", err
			}
			bound := func(op string, val pyNum, lowOps bool) *pyNum {
				switch {
				case lowOps && op == ">=", !lowOps && op == "<=":
					return &val
				case lowOps && op == ">":
					n := val.plus(1)
					return &n
				case !lowOps && op == "<":
					n := val.plus(-1)
					return &n
				}
				return nil
			}
			lo, hi := bound(op1, val1, true), bound(op2, val2, false)
			if lo == nil || hi == nil {
				lo, hi = bound(op2, val2, true), bound(op1, val1, false)
			}
			if v1 == v2 && lo != nil && hi != nil {
				base := v1 + " in " + lo.String() + ".." + hi.String()
				if invert {
					return negated(base, style), nil
				}
				return base, nil
			}
		}
	}

	if b, ok := cur.(kpol.Binary); ok {
		v, op, val, err := normCmp(b)
		if err != nil {
			return "", err
		}
		base := v + " " + op + " " + val.String()
		if invert {
			return negated(base, style), nil
		}
		return base, nil
	}
	return "", syntaxErr("unsupported KPOL guard expression %s", exprRepr(expr))
}

func kpolActionToEKPOL(act *kpol.SetAction) (string, error) {
	expr := act.Expression
	if b, ok := expr.(kpol.Binary); ok && (b.Op == "+" || b.Op == "-") {
		aug := "-="
		if b.Op == "+" {
			aug = "+="
		}
		if n, ok := b.L.(kpol.Name); ok && n.Name == act.Name && isLiteral(b.R) {
			return act.Name + " " + aug + " " + literalStr(b.R), nil
		}
		if n, ok := b.R.(kpol.Name); ok && b.Op == "+" && n.Name == act.Name && isLiteral(b.L) {
			return act.Name + " += " + literalStr(b.L), nil
		}
	}
	if n, ok := expr.(kpol.Name); ok {
		return act.Name + " = " + n.Name, nil
	}
	if isLiteral(expr) {
		return act.Name + " = " + literalStr(expr), nil
	}
	return "", syntaxErr("unsupported KPOL action expression %s", exprRepr(expr))
}

// ToEKPOL translates a classic KPOL module (KPOL-CME-1 or KPOL-CME-2) into ASCII EKPOL
// in the given style, "symbolic" or "keyword" (reference: transpile_kpol_to_ekpol).
func ToEKPOL(kpolSrc, style string) (string, error) {
	if style != "symbolic" && style != "keyword" {
		return "", syntaxErr("unsupported EKPOL formatting style %s (expected 'symbolic' or 'keyword')", pyRepr(style))
	}
	_, cStdin, cStdout, cStderr, err := stripComments(kpolSrc)
	if err != nil {
		return "", err
	}
	mod, err := parseKPOLSyntax(kpolSrc)
	if err != nil {
		return "", syntaxErr("failed to parse input KPOL: %s", err.Error())
	}

	typeLabel := "i32"
	if style != "symbolic" {
		typeLabel = "int32"
	}
	eventMap := map[string]*kpol.EventDecl{}
	for i := range mod.Events {
		eventMap[mod.Events[i].Name] = &mod.Events[i]
	}
	rulesByState := map[string]*kpol.Rule{}
	for i := range mod.Rules {
		if len(mod.Rules[i].Actions) > 0 {
			rulesByState[mod.Rules[i].Actions[0].Name] = &mod.Rules[i]
		}
	}
	eventToConcept := map[string]string{}
	for i := range mod.States {
		if r := rulesByState[mod.States[i].Name]; r != nil && r.Event != "change" {
			eventToConcept[r.Event] = mod.States[i].Name
		}
	}

	stdinSet := map[string]bool{}
	if len(cStdin) > 0 {
		for _, n := range cStdin {
			stdinSet[n] = true
		}
	} else if len(mod.States) > 0 {
		stdinSet[mod.States[0].Name] = true
	}
	stdoutSet := map[string]bool{}
	if len(cStdout) > 0 {
		for _, n := range cStdout {
			stdoutSet[n] = true
		}
	} else {
		for i := range mod.States {
			stdoutSet[mod.States[i].Name] = true
		}
	}
	stderrSet := map[string]bool{}
	for _, n := range cStderr {
		stderrSet[n] = true
	}

	lines := []string{"module " + mod.Name + ";", ""}
	for i := range mod.States {
		st := &mod.States[i]
		if stdinSet[st.Name] {
			lines = append(lines, "@stdin")
		}
		if stdoutSet[st.Name] {
			lines = append(lines, "@stdout")
		}
		if stderrSet[st.Name] {
			lines = append(lines, "@stderr")
		}

		initVal := "0"
		if isLiteral(st.Initial) {
			initVal = literalStr(st.Initial)
		}
		lines = append(lines, "concept "+st.Name+": "+typeLabel+" = "+initVal+" [>= 0] {")

		if rule := rulesByState[st.Name]; rule != nil {
			guard, err := kpolGuardToEKPOL(rule.Guard, style)
			if err != nil {
				return "", err
			}
			act, err := kpolActionToEKPOL(&rule.Actions[0])
			if err != nil {
				return "", err
			}
			if rule.Event == "change" {
				if len(rule.Watch) == 0 {
					return "", internalErr("unhandled reference exception IndexError: tuple index out of range")
				}
				w := rule.Watch[0]
				if style == "symbolic" {
					lines = append(lines, "    ~ "+w+" :: "+guard+" => "+act+" .")
				} else {
					lines = append(lines, "    on change("+w+") when "+guard+" => "+act+" commit;")
				}
			} else {
				ev, ok := eventMap[rule.Event]
				if !ok {
					return "", internalErr("unhandled reference exception KeyError: %s", pyRepr(rule.Event))
				}
				if len(ev.Params) == 0 {
					return "", internalErr("unhandled reference exception IndexError: tuple index out of range")
				}
				p := ev.Params[0].Name
				if style == "symbolic" {
					lines = append(lines, "    <- "+rule.Event+"("+p+") :: "+guard+" => "+act+" .")
				} else {
					lines = append(lines, "    on "+rule.Event+"("+p+") when "+guard+" => "+act+" commit;")
				}
			}
		}
		lines = append(lines, "}", "")
	}

	for _, item := range mod.Proofs {
		sc, ok := item.(kpol.Scenario)
		if !ok {
			continue
		}
		lines = append(lines, "test "+sc.Name+" {")
		for _, it := range sc.Items {
			switch s := it.(type) {
			case kpol.StepAction:
				target, found := eventToConcept[s.Event]
				if !found {
					target = s.Event
				}
				if len(s.Args) == 0 {
					return "", internalErr("unhandled reference exception IndexError: tuple index out of range")
				}
				argV := "0"
				switch a := s.Args[0].Value.(type) {
				case kpol.Unary:
					if unaryOp(a) == "-" && isLiteral(a.X) {
						n, ok := intOfLiteral(a.X)
						if !ok {
							return "", internalErr("unhandled reference exception TypeError: int() argument must be a string, a bytes-like object or a real number, not '_Unknown'")
						}
						argV = new(big.Int).Neg(n).String()
					}
				default:
					if isLiteral(a) {
						argV = literalStr(a)
					}
				}
				lines = append(lines, "    send "+target+"("+argV+");")
			case kpol.ExpectCheck:
				if b, ok := s.Expression.(kpol.Binary); ok {
					if n, isName := b.L.(kpol.Name); isName && isLiteral(b.R) {
						lines = append(lines, "    expect "+n.Name+" "+b.Op+" "+literalStr(b.R)+";")
					}
				}
			}
		}
		lines = append(lines, "}", "")
	}

	return strings.TrimRightFunc(strings.Join(lines, "\n"), pyIsSpace) + "\n", nil
}
