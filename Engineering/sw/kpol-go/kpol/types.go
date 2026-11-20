package kpol

import (
	"fmt"
	"math/big"
	"strings"
)

// ktype is a static type: a declared type (Bool, Int32, U32, U64, Float with
// a unit, Pin with joined parameter names) or one of the auxiliary types
// Number (a literal) and Unknown. An empty unit stands for Python's None.
type ktype struct{ name, unit string }

var (
	tBool    = ktype{"Bool", ""}
	tUnknown = ktype{"Unknown", ""}
	tNumber  = ktype{"Number", ""}
)

// String reproduces the repr of the reference dataclass; it appears in
// diagnostics, for example "KType(name='Int32', unit=None)".
func (k ktype) String() string {
	unit := "None"
	if k.unit != "" {
		unit = pyRepr(k.unit)
	}
	return fmt.Sprintf("KType(name=%s, unit=%s)", pyRepr(k.name), unit)
}

func asKType(t TypeRef) ktype {
	unit := t.Unit
	if len(t.PinParams) > 0 {
		unit = strings.Join(t.PinParams, ",")
	}
	return ktype{t.Name, unit}
}

func (k ktype) numeric() bool {
	switch k.name {
	case "Number", "Int32", "U32", "U64", "Float":
		return true
	}
	return false
}

func (k ktype) integer() bool {
	return k.name == "U64" || k.name == "U32" || k.name == "Int32"
}

// compatible is τₑ ⊒ τₐ without constant folding (KPOL-STA-5, steps 3–7).
func compatible(expected, actual ktype) bool {
	if actual.name == "Unknown" {
		return true
	}
	if expected == actual {
		return true
	}
	if actual.name == "Number" && expected.numeric() {
		return true
	}
	if expected.name == "Float" && actual.name == "Float" {
		return expected.unit == actual.unit
	}
	if expected.name == "Pin" && (actual.name == "Number" || actual.name == "Int32" || actual.name == "Bool" || actual.numeric()) {
		return true
	}
	return false
}

// constantNumber folds literals, unary minus and + - * (the function fold of
// KPOL-STA-5). ok is false when e has no constant value.
func constantNumber(e Expr) (v Value, ok bool, err error) {
	switch x := e.(type) {
	case IntLit:
		return Int{x.V}, true, nil
	case DecLit:
		d, finite, perr := ParseDecimal(x.Text)
		if perr != nil || !finite {
			return nil, false, &Error{Msg: fmt.Sprintf("invalid number %s", pyRepr(x.Text))}
		}
		return d, true, nil
	case Unary:
		if x.Op != "-" {
			return nil, false, nil
		}
		inner, ok, err := constantNumber(x.X)
		if err != nil || !ok {
			return nil, false, err
		}
		r, err := negate(inner)
		if err != nil {
			return nil, false, err
		}
		return r, true, nil
	case Binary:
		if x.Op != "+" && x.Op != "-" && x.Op != "*" {
			return nil, false, nil
		}
		l, ok, err := constantNumber(x.L)
		if err != nil || !ok {
			return nil, false, err
		}
		r, ok, err := constantNumber(x.R)
		if err != nil || !ok {
			return nil, false, err
		}
		res, err := arith(x.Op, l, r)
		if err != nil {
			return nil, false, err
		}
		return res, true, nil
	}
	return nil, false, nil
}

// compatibleExpr is τₑ ⊒ (τₐ, e) of KPOL-STA-5: constant literals are checked
// against the integer ranges and Pin values before the structural rules.
func compatibleExpr(expected, actual ktype, e Expr) (bool, error) {
	if actual.name == "Number" && (expected.name == "U64" || expected.name == "U32" || expected.name == "Int32") {
		value, ok, err := constantNumber(e)
		if err != nil {
			return false, err
		}
		if ok {
			iv, err := pyInt(value)
			if err != nil {
				return false, err
			}
			if !Equal(value, Int{iv}) {
				return false, nil
			}
			var lower, upper *big.Int
			switch expected.name {
			case "U32":
				lower, upper = bigZero, new(big.Int).Sub(new(big.Int).Lsh(bigOne, 32), bigOne)
			case "U64":
				lower, upper = bigZero, new(big.Int).Sub(new(big.Int).Lsh(bigOne, 64), bigOne)
			default:
				lower = new(big.Int).Neg(new(big.Int).Lsh(bigOne, 31))
				upper = new(big.Int).Sub(new(big.Int).Lsh(bigOne, 31), bigOne)
			}
			return lower.Cmp(iv) <= 0 && iv.Cmp(upper) <= 0, nil
		}
	}
	if expected.name == "Pin" && actual.name == "Number" {
		value, ok, err := constantNumber(e)
		if err != nil {
			return false, err
		}
		if ok {
			return Equal(value, Int{}) || Equal(value, NewInt(1)), nil
		}
	}
	return compatible(expected, actual), nil
}

func joinNumeric(l, r ktype) (ktype, error) {
	switch {
	case l.name == "Unknown":
		return r, nil
	case r.name == "Unknown":
		return l, nil
	case l.name == "Number":
		return r, nil
	case r.name == "Number":
		return l, nil
	case l != r:
		return ktype{}, &Error{Msg: fmt.Sprintf("incompatible numeric types: %s and %s", l, r)}
	}
	return l, nil
}

func unitProduct(a, b string) (string, bool) {
	switch [2]string{a, b} {
	case [2]string{"V", "A"}, [2]string{"A", "V"}:
		return "W", true
	case [2]string{"W", "s"}, [2]string{"s", "W"}:
		return "J", true
	}
	return "", false
}

func isBoolish(k ktype) bool { return k == tBool || k == tUnknown }

func staticErr(format string, a ...any) error {
	return &Error{Msg: fmt.Sprintf(format, a...)}
}

// infer computes the static type of e in the environment env (KPOL-STA-4,
// §5.3). It reports the first violated typing rule as an error.
func infer(e Expr, env map[string]ktype) (ktype, error) {
	switch x := e.(type) {
	case BoolLit:
		return tBool, nil
	case UnknownLit:
		return tUnknown, nil
	case IntLit, DecLit:
		return tNumber, nil
	case Name:
		t, ok := env[x.Name]
		if !ok {
			return ktype{}, staticErr("unresolved name %s", pyRepr(x.Name))
		}
		return t, nil
	case Call:
		if x.Name != "gcd" || len(x.Args) != 2 {
			return ktype{}, staticErr("unsupported function %s", pyRepr(x.Name))
		}
		types := make([]ktype, len(x.Args))
		for i, a := range x.Args {
			t, err := infer(a, env)
			if err != nil {
				return ktype{}, err
			}
			types[i] = t
		}
		for i, a := range x.Args {
			ok, err := compatibleExpr(ktype{"U64", ""}, types[i], a)
			if err != nil {
				return ktype{}, err
			}
			if !ok {
				return ktype{}, staticErr("gcd arguments must be U64")
			}
		}
		return ktype{"U64", ""}, nil
	case Unary:
		operand, err := infer(x.X, env)
		if err != nil {
			return ktype{}, err
		}
		if x.Op == "not" {
			if !isBoolish(operand) {
				return ktype{}, staticErr("not requires Bool")
			}
			return tBool, nil
		}
		if x.Op == "-" && operand.numeric() {
			return operand, nil
		}
		return ktype{}, staticErr("invalid unary operation %s", pyRepr(x.Op))
	case Binary:
		return inferBinary(x, env)
	}
	return ktype{}, staticErr("invalid expression node")
}

func inferBinary(x Binary, env map[string]ktype) (ktype, error) {
	left, err := infer(x.L, env)
	if err != nil {
		return ktype{}, err
	}
	right, err := infer(x.R, env)
	if err != nil {
		return ktype{}, err
	}
	op := x.Op
	switch op {
	case "and", "or":
		if !isBoolish(left) || !isBoolish(right) {
			return ktype{}, staticErr("%s requires Bool operands", op)
		}
		return tBool, nil
	case "==", "!=", "<", "<=", ">", ">=":
		if left.name == "Unknown" || right.name == "Unknown" {
			return tBool, nil
		}
		ok, err := compatibleExpr(left, right, x.R)
		if err != nil {
			return ktype{}, err
		}
		if !ok {
			ok, err = compatibleExpr(right, left, x.L)
			if err != nil {
				return ktype{}, err
			}
		}
		if !ok {
			return ktype{}, staticErr("incompatible comparison: %s %s %s", left, op, right)
		}
		if op != "==" && op != "!=" && !(left.numeric() && right.numeric()) {
			return ktype{}, staticErr("%s requires numeric operands", op)
		}
		return tBool, nil
	case "+", "-", "*":
		if !(left.numeric() && right.numeric()) {
			return ktype{}, staticErr("%s requires numeric operands", op)
		}
		if left.integer() {
			ok, err := compatibleExpr(left, right, x.R)
			if err != nil {
				return ktype{}, err
			}
			if !ok {
				return ktype{}, staticErr("%s has an invalid integer literal", op)
			}
		}
		if right.integer() {
			ok, err := compatibleExpr(right, left, x.L)
			if err != nil {
				return ktype{}, err
			}
			if !ok {
				return ktype{}, staticErr("%s has an invalid integer literal", op)
			}
		}
		if (left.name == "Float" && left.unit == "degC") || (right.name == "Float" && right.unit == "degC") {
			return ktype{}, staticErr("arithmetic on absolute degC values is unsupported")
		}
		if op != "*" {
			return joinNumeric(left, right)
		}
		if left.name == "Number" {
			return right, nil
		}
		if right.name == "Number" {
			return left, nil
		}
		if left.name == "Float" && right.name == "Float" {
			unit, ok := unitProduct(left.unit, right.unit)
			if !ok {
				return ktype{}, staticErr("unsupported unit product: %s*%s", noneIfEmpty(left.unit), noneIfEmpty(right.unit))
			}
			return ktype{"Float", unit}, nil
		}
		return joinNumeric(left, right)
	case "/":
		if !(left.numeric() && right.numeric()) {
			return ktype{}, staticErr("/ requires numeric operands")
		}
		if left.name == "Float" && left.unit == "degC" {
			return ktype{}, staticErr("arithmetic on absolute degC values is unsupported")
		}
		if right.name == "Number" {
			return left, nil
		}
		if left.name == "Float" && right.name == "Float" && left.unit == right.unit {
			return tNumber, nil
		}
		return ktype{}, staticErr("unsupported unit division: %s/%s", left, right)
	}
	return ktype{}, staticErr("unsupported operator %s", pyRepr(op))
}

func noneIfEmpty(s string) string {
	if s == "" {
		return "None"
	}
	return s
}

// exprEqual is the structural equality of the reference dataclasses used by
// the covers condition (KPOL-STA-11). Literal values compare with Python's
// ==, so true equals 1 and 2.0 equals 2.
func exprEqual(a, b Expr) bool {
	switch x := a.(type) {
	case IntLit, DecLit, BoolLit, UnknownLit:
		switch b.(type) {
		case IntLit, DecLit, BoolLit, UnknownLit:
			return literalEqual(a, b)
		}
		return false
	case Name:
		y, ok := b.(Name)
		return ok && x.Name == y.Name
	case Unary:
		y, ok := b.(Unary)
		return ok && x.Op == y.Op && exprEqual(x.X, y.X)
	case Binary:
		y, ok := b.(Binary)
		return ok && x.Op == y.Op && exprEqual(x.L, y.L) && exprEqual(x.R, y.R)
	case Call:
		y, ok := b.(Call)
		if !ok || x.Name != y.Name || len(x.Args) != len(y.Args) {
			return false
		}
		for i := range x.Args {
			if !exprEqual(x.Args[i], y.Args[i]) {
				return false
			}
		}
		return true
	}
	return false
}

func literalEqual(a, b Expr) bool {
	va, errA := eval(a, nil)
	vb, errB := eval(b, nil)
	if errA != nil || errB != nil {
		return false
	}
	return Equal(va, vb)
}
