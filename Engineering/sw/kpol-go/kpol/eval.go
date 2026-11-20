package kpol

import (
	"fmt"
	"math/big"
)

// EvalExpr evaluates e under the environment env (⟦e⟧ρ, KPOL-DYN-3) with
// strong Kleene logic and short-circuit and/or. Equality with Unknown is
// definitional; ordering and arithmetic with Unknown give Unknown; division by
// zero is an error. The expression is not type-checked.
func EvalExpr(e Expr, env map[string]Value) (Value, error) {
	return eval(e, env)
}

func eval(e Expr, env map[string]Value) (Value, error) {
	switch x := e.(type) {
	case IntLit:
		return Int{x.V}, nil
	case DecLit:
		d, finite, err := ParseDecimal(x.Text)
		if err != nil || !finite {
			return nil, &Error{Msg: fmt.Sprintf("invalid number %s", pyRepr(x.Text))}
		}
		return d, nil
	case BoolLit:
		return Bool(x.V), nil
	case UnknownLit:
		return Unknown{}, nil
	case Name:
		v, ok := env[x.Name]
		if !ok {
			return nil, &Error{Msg: fmt.Sprintf("unresolved runtime name %s", pyRepr(x.Name))}
		}
		return v, nil
	case Call:
		return evalCall(x, env)
	case Unary:
		return evalUnary(x, env)
	case Binary:
		return evalBinary(x, env)
	}
	return nil, &Error{Msg: "invalid expression node"}
}

func evalCall(c Call, env map[string]Value) (Value, error) {
	values := make([]Value, len(c.Args))
	for i, a := range c.Args {
		v, err := eval(a, env)
		if err != nil {
			return nil, err
		}
		values[i] = v
	}
	if c.Name == "gcd" && len(values) == 2 {
		if IsUnknown(values[0]) || IsUnknown(values[1]) {
			return Unknown{}, nil
		}
		a, err := pyInt(values[0])
		if err != nil {
			return nil, err
		}
		b, err := pyInt(values[1])
		if err != nil {
			return nil, err
		}
		return Int{new(big.Int).GCD(nil, nil, new(big.Int).Abs(a), new(big.Int).Abs(b))}, nil
	}
	return nil, &Error{Msg: fmt.Sprintf("unsupported function %s", pyRepr(c.Name))}
}

// pyInt is Python's int(v) for runtime values.
func pyInt(v Value) (*big.Int, error) {
	switch x := v.(type) {
	case Bool, Int:
		n, _ := asInt(v)
		return n, nil
	case Decimal:
		return x.Trunc(), nil
	case Float:
		f := float64(x)
		if f != f {
			return nil, &Error{Code: CodeRTValue, Msg: "ValueError: cannot convert float NaN to integer"}
		}
		if f > 1.7976931348623157e308 || f < -1.7976931348623157e308 {
			return nil, &Error{Code: CodeRTOverflow, Msg: "OverflowError: cannot convert float infinity to integer"}
		}
		n, _ := new(big.Float).SetFloat64(f).Int(nil)
		return n, nil
	}
	return nil, &Error{Code: CodeRTType, Msg: fmt.Sprintf("int() argument must be a string or a real number, not '%s'", pyTypeName(v))}
}

func evalUnary(u Unary, env map[string]Value) (Value, error) {
	v, err := eval(u.X, env)
	if err != nil {
		return nil, err
	}
	switch u.Op {
	case "not":
		if IsUnknown(v) {
			return Unknown{}, nil
		}
		return Bool(!truthy(v)), nil
	case "-":
		if IsUnknown(v) {
			return Unknown{}, nil
		}
		return negate(v)
	}
	return nil, &Error{Msg: fmt.Sprintf("unsupported unary operator %s", pyRepr(u.Op))}
}

func isFalse(v Value) bool { b, ok := v.(Bool); return ok && !bool(b) }
func isTrue(v Value) bool  { b, ok := v.(Bool); return ok && bool(b) }

func evalBinary(b Binary, env map[string]Value) (Value, error) {
	switch b.Op {
	case "and":
		left, err := eval(b.L, env)
		if err != nil {
			return nil, err
		}
		if isFalse(left) {
			return Bool(false), nil
		}
		right, err := eval(b.R, env)
		if err != nil {
			return nil, err
		}
		if isFalse(right) {
			return Bool(false), nil
		}
		if isTrue(left) && isTrue(right) {
			return Bool(true), nil
		}
		return Unknown{}, nil
	case "or":
		left, err := eval(b.L, env)
		if err != nil {
			return nil, err
		}
		if isTrue(left) {
			return Bool(true), nil
		}
		right, err := eval(b.R, env)
		if err != nil {
			return nil, err
		}
		if isTrue(right) {
			return Bool(true), nil
		}
		if isFalse(left) && isFalse(right) {
			return Bool(false), nil
		}
		return Unknown{}, nil
	}
	left, err := eval(b.L, env)
	if err != nil {
		return nil, err
	}
	right, err := eval(b.R, env)
	if err != nil {
		return nil, err
	}
	if b.Op == "==" || b.Op == "!=" {
		if IsUnknown(left) || IsUnknown(right) {
			equal := IsUnknown(left) && IsUnknown(right)
			return Bool(equal == (b.Op == "==")), nil
		}
	}
	if IsUnknown(left) || IsUnknown(right) {
		return Unknown{}, nil
	}
	switch b.Op {
	case "==":
		return Bool(Equal(left, right)), nil
	case "!=":
		return Bool(!Equal(left, right)), nil
	case "<", "<=", ">", ">=":
		if !isNumeric(left) || !isNumeric(right) {
			return nil, &Error{Code: CodeRTType, Msg: fmt.Sprintf("'%s' not supported between instances of '%s' and '%s'", b.Op, pyTypeName(left), pyTypeName(right))}
		}
		c, unordered, err := compareNumbers(left, right, true)
		if err != nil {
			return nil, err
		}
		if unordered {
			return Bool(false), nil
		}
		switch b.Op {
		case "<":
			return Bool(c < 0), nil
		case "<=":
			return Bool(c <= 0), nil
		case ">":
			return Bool(c > 0), nil
		}
		return Bool(c >= 0), nil
	case "+", "-", "*":
		return arith(b.Op, left, right)
	case "/":
		if Equal(right, Int{}) {
			return nil, &Error{Msg: "division by zero"}
		}
		return arith("/", left, right)
	}
	return nil, &Error{Msg: fmt.Sprintf("unsupported operator %s", pyRepr(b.Op))}
}

// normalize is norm(v, τ) (KPOL-DYN-2): it validates a value before it is
// stored in a state or event parameter. Unknown is allowed only for parameters.
func normalize(v Value, t TypeRef, allowUnknown bool) (Value, error) {
	if IsUnknown(v) {
		if allowUnknown {
			return v, nil
		}
		return nil, &Error{Msg: "Unknown cannot be stored in a state"}
	}
	switch t.Name {
	case "Bool":
		if _, ok := v.(Bool); ok {
			return v, nil
		}
		return nil, &Error{Msg: "expected Bool value"}
	case "U32", "U64":
		bits := 32
		if t.Name == "U64" {
			bits = 64
		}
		if n, ok := v.(Int); ok {
			x := n.big()
			if x.Sign() >= 0 && x.BitLen() <= bits {
				return v, nil
			}
		}
		return nil, &Error{Msg: fmt.Sprintf("expected %s value", t.Name)}
	case "Int32":
		if n, ok := v.(Int); ok {
			x := n.big()
			if x.BitLen() <= 31 || (x.Sign() < 0 && new(big.Int).Add(x, bigOne).BitLen() <= 31) {
				return v, nil
			}
		}
		return nil, &Error{Msg: "expected Int32 value"}
	case "Float":
		d, ok := toFiniteDecimal(v)
		if !ok {
			return nil, &Error{Msg: "expected finite Float value"}
		}
		return d, nil
	case "Pin":
		switch x := v.(type) {
		case Bool:
			if x {
				return NewInt(1), nil
			}
			return NewInt(0), nil
		case Int:
			if n := x.big(); n.Sign() >= 0 && n.Cmp(bigOne) <= 0 {
				return v, nil
			}
		}
		return nil, &Error{Msg: "expected Pin value (0, 1, or Bool)"}
	}
	return nil, &Error{Msg: fmt.Sprintf("unsupported runtime type %s", pyRepr(t.Name))}
}

// maxIntStrDigits is CPython's default limit for int→str conversion.
const maxIntStrDigits = 4300

// toFiniteDecimal is Decimal(str(v)) followed by the finiteness check.
func toFiniteDecimal(v Value) (Decimal, bool) {
	switch x := v.(type) {
	case Decimal:
		return x, true
	case Int:
		n := x.big()
		if len(new(big.Int).Abs(n).Text(10)) > maxIntStrDigits {
			return Decimal{}, false
		}
		return DecimalFromBigInt(n), true
	case Float:
		d, finite, err := ParseDecimal(pyFloatRepr(float64(x)))
		if err != nil || !finite {
			return Decimal{}, false
		}
		return d, true
	}
	return Decimal{}, false
}
