package kpol

import (
	"fmt"
	"math"
	"math/big"
	"strconv"
	"strings"
)

// Value is a runtime value of the KPOL interpreter: Bool, Int, Decimal, Float
// or Unknown. The dynamic types mirror the Python reference: Int is an
// arbitrary-precision integer, Decimal a decimal with a 28-digit context, and
// Float a binary double that only arises from dividing two integers (D-K2).
type Value interface{ valueNode() }

// Bool is a logical value.
type Bool bool

// Int is an arbitrary-precision integer. The zero value is 0.
type Int struct{ v *big.Int }

// Float is a binary floating-point number (the result of Int / Int, D-K2).
type Float float64

// Unknown is the third truth value ⊥ of the strong Kleene logic.
type Unknown struct{}

func (Bool) valueNode()    {}
func (Int) valueNode()     {}
func (Decimal) valueNode() {}
func (Float) valueNode()   {}
func (Unknown) valueNode() {}

// NewInt returns the integer n.
func NewInt(n int64) Int { return Int{big.NewInt(n)} }

// NewBigInt returns the integer x; x is copied.
func NewBigInt(x *big.Int) Int { return Int{new(big.Int).Set(x)} }

// Big returns a copy of the integer as a *big.Int.
func (i Int) Big() *big.Int { return new(big.Int).Set(i.big()) }

func (i Int) big() *big.Int {
	if i.v == nil {
		return bigZero
	}
	return i.v
}

// Int64 returns the value as an int64 and whether it fits.
func (i Int) Int64() (int64, bool) { return i.big().Int64(), i.big().IsInt64() }

// String returns the decimal representation.
func (i Int) String() string { return i.big().String() }

// IsUnknown reports whether v is the Unknown value.
func IsUnknown(v Value) bool {
	_, ok := v.(Unknown)
	return ok
}

// FormatValue renders v exactly as Python's str() does for the reference
// value: True/False, integers, Decimal in scientific-string form, floats in
// shortest repr, and Unknown.
func FormatValue(v Value) string {
	switch x := v.(type) {
	case Bool:
		if x {
			return "True"
		}
		return "False"
	case Int:
		return x.String()
	case Decimal:
		return x.String()
	case Float:
		return pyFloatRepr(float64(x))
	case Unknown:
		return "Unknown"
	case nil:
		return "None"
	}
	return fmt.Sprintf("%v", v)
}

// ReprValue renders v like Python's repr(): as FormatValue, except that a
// Decimal is written Decimal('2.50').
func ReprValue(v Value) string {
	if d, ok := v.(Decimal); ok {
		return "Decimal('" + d.String() + "')"
	}
	return FormatValue(v)
}

// pyFloatRepr renders f like Python's repr(float).
func pyFloatRepr(f float64) string {
	switch {
	case math.IsNaN(f):
		return "nan"
	case math.IsInf(f, 1):
		return "inf"
	case math.IsInf(f, -1):
		return "-inf"
	}
	s := strconv.FormatFloat(f, 'e', -1, 64)
	sign := ""
	if s[0] == '-' {
		sign = "-"
		s = s[1:]
	}
	mant, expText, _ := strings.Cut(s, "e")
	exp10, _ := strconv.Atoi(expText)
	digits := strings.Replace(mant, ".", "", 1)
	decpt := exp10 + 1
	var out string
	switch {
	case decpt <= -4 || decpt > 16:
		out = digits[:1]
		if len(digits) > 1 {
			out += "." + digits[1:]
		}
		e := decpt - 1
		esign := "+"
		if e < 0 {
			esign = "-"
			e = -e
		}
		out += fmt.Sprintf("e%s%02d", esign, e)
	case decpt <= 0:
		out = "0." + strings.Repeat("0", -decpt) + digits
	case decpt >= len(digits):
		out = digits + strings.Repeat("0", decpt-len(digits)) + ".0"
	default:
		out = digits[:decpt] + "." + digits[decpt:]
	}
	return sign + out
}

// pyTypeName names the Python type of the reference value.
func pyTypeName(v Value) string {
	switch v.(type) {
	case Bool:
		return "bool"
	case Int:
		return "int"
	case Decimal:
		return "decimal.Decimal"
	case Float:
		return "float"
	case Unknown:
		return "_Unknown"
	}
	return "NoneType"
}

func typeError(op string, a, b Value) error {
	return &Error{Code: CodeRTType, Msg: fmt.Sprintf("unsupported operand type(s) for %s: '%s' and '%s'", op, pyTypeName(a), pyTypeName(b))}
}

// asInt views Bool and Int as integers, as Python does.
func asInt(v Value) (*big.Int, bool) {
	switch x := v.(type) {
	case Bool:
		if x {
			return bigOne, true
		}
		return bigZero, true
	case Int:
		return x.big(), true
	}
	return nil, false
}

func isNumeric(v Value) bool {
	switch v.(type) {
	case Bool, Int, Decimal, Float:
		return true
	}
	return false
}

// intToFloat converts like Python's int→float (round half to even, OverflowError).
func intToFloat(x *big.Int) (float64, error) {
	if x.IsInt64() {
		n := x.Int64()
		if n > -(1<<53) && n < 1<<53 {
			return float64(n), nil
		}
	}
	f, _ := new(big.Float).SetInt(x).Float64()
	if math.IsInf(f, 0) {
		return 0, &Error{Code: CodeRTOverflow, Msg: "OverflowError: int too large to convert to float"}
	}
	return f, nil
}

func toFloat(v Value) (float64, error) {
	switch x := v.(type) {
	case Float:
		return float64(x), nil
	case Bool, Int:
		n, _ := asInt(v)
		return intToFloat(n)
	}
	return 0, fmt.Errorf("not a float operand")
}

func toDecimal(v Value) (Decimal, bool) {
	switch x := v.(type) {
	case Decimal:
		return x, true
	case Bool, Int:
		n, _ := asInt(v)
		return DecimalFromBigInt(n), true
	}
	return Decimal{}, false
}

// arith applies + - * / to two non-Unknown values with Python's dynamic
// semantics; the caller has already rejected a zero divisor.
func arith(op string, a, b Value) (Value, error) {
	_, af := a.(Float)
	_, bf := b.(Float)
	if af || bf {
		if !isNumeric(a) || !isNumeric(b) {
			return nil, typeError(op, a, b)
		}
		if _, ok := a.(Decimal); ok {
			return nil, typeError(op, a, b)
		}
		if _, ok := b.(Decimal); ok {
			return nil, typeError(op, a, b)
		}
		x, err := toFloat(a)
		if err != nil {
			return nil, err
		}
		y, err := toFloat(b)
		if err != nil {
			return nil, err
		}
		switch op {
		case "+":
			return Float(x + y), nil
		case "-":
			return Float(x - y), nil
		case "*":
			return Float(x * y), nil
		case "/":
			return Float(x / y), nil
		}
		return nil, fmt.Errorf("unsupported operator %q", op)
	}
	_, ad := a.(Decimal)
	_, bd := b.(Decimal)
	if ad || bd {
		x, ok1 := toDecimal(a)
		y, ok2 := toDecimal(b)
		if !ok1 || !ok2 {
			return nil, typeError(op, a, b)
		}
		var r Decimal
		var err error
		switch op {
		case "+":
			r, err = decAdd(x, y)
		case "-":
			r, err = decSub(x, y)
		case "*":
			r, err = decMul(x, y)
		case "/":
			r, err = decDiv(x, y)
		default:
			return nil, fmt.Errorf("unsupported operator %q", op)
		}
		if err != nil {
			return nil, err
		}
		return r, nil
	}
	x, ok1 := asInt(a)
	y, ok2 := asInt(b)
	if !ok1 || !ok2 {
		return nil, typeError(op, a, b)
	}
	switch op {
	case "+":
		return Int{new(big.Int).Add(x, y)}, nil
	case "-":
		return Int{new(big.Int).Sub(x, y)}, nil
	case "*":
		return Int{new(big.Int).Mul(x, y)}, nil
	case "/":
		if y.Sign() == 0 {
			return nil, &Error{Msg: "division by zero"}
		}
		q, _ := new(big.Rat).SetFrac(x, y).Float64()
		if math.IsInf(q, 0) {
			return nil, &Error{Code: CodeRTOverflow, Msg: "OverflowError: integer division result too large for a float"}
		}
		if q == 0 && (x.Sign() < 0) != (y.Sign() < 0) {
			q = math.Copysign(0, -1)
		}
		return Float(q), nil
	}
	return nil, fmt.Errorf("unsupported operator %q", op)
}

// negate is unary minus with Python semantics (-True is -1).
func negate(v Value) (Value, error) {
	switch x := v.(type) {
	case Bool:
		if x {
			return NewInt(-1), nil
		}
		return NewInt(0), nil
	case Int:
		return Int{new(big.Int).Neg(x.big())}, nil
	case Decimal:
		r, err := decNeg(x)
		if err != nil {
			return nil, err
		}
		return r, nil
	case Float:
		return -x, nil
	}
	return nil, &Error{Code: CodeRTType, Msg: fmt.Sprintf("bad operand type for unary -: '%s'", pyTypeName(v))}
}

// truthy is Python's bool(v).
func truthy(v Value) bool {
	switch x := v.(type) {
	case Bool:
		return bool(x)
	case Int:
		return x.big().Sign() != 0
	case Decimal:
		return !x.IsZero()
	case Float:
		return x != 0
	}
	return true
}

// compareNumbers orders two numeric values exactly. unordered is true when a
// NaN is involved. A Decimal–NaN ordering raises in Python (InvalidOperation);
// ordering reports that case as an error.
func compareNumbers(a, b Value, ordering bool) (c int, unordered bool, err error) {
	af, aIsF := a.(Float)
	bf, bIsF := b.(Float)
	switch {
	case aIsF && bIsF:
		x, y := float64(af), float64(bf)
		switch {
		case math.IsNaN(x) || math.IsNaN(y):
			return 0, true, nil
		case x < y:
			return -1, false, nil
		case x > y:
			return 1, false, nil
		}
		return 0, false, nil
	case aIsF || bIsF:
		var f float64
		var other Value
		sign := 1
		if aIsF {
			f, other = float64(af), b
		} else {
			f, other, sign = float64(bf), a, -1
		}
		if math.IsNaN(f) {
			if _, isDec := other.(Decimal); isDec && ordering {
				return 0, true, &Error{Code: CodeRTDecimal, Msg: "decimal.InvalidOperation: comparison involving NaN"}
			}
			return 0, true, nil
		}
		var r int
		if math.IsInf(f, 0) {
			if f > 0 {
				r = 1
			} else {
				r = -1
			}
		} else if d, ok := other.(Decimal); ok {
			r = decimalFromFloatExact(f).Cmp(d)
		} else {
			n, _ := asInt(other)
			r = new(big.Float).SetFloat64(f).Cmp(new(big.Float).SetInt(n))
		}
		return r * sign, false, nil
	}
	_, ad := a.(Decimal)
	_, bd := b.(Decimal)
	if ad || bd {
		x, _ := toDecimal(a)
		y, _ := toDecimal(b)
		return x.Cmp(y), false, nil
	}
	x, _ := asInt(a)
	y, _ := asInt(b)
	return x.Cmp(y), false, nil
}

// Equal reports Python's a == b for runtime values: numbers compare by exact
// numeric value across Bool, Int, Decimal and Float (True == 1, 2.0 == 2),
// and Unknown equals only Unknown.
func Equal(a, b Value) bool {
	if isNumeric(a) && isNumeric(b) {
		c, unordered, _ := compareNumbers(a, b, false)
		return !unordered && c == 0
	}
	_, au := a.(Unknown)
	_, bu := b.(Unknown)
	return au && bu
}
