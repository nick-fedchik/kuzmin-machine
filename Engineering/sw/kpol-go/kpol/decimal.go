package kpol

import (
	"fmt"
	"math"
	"math/big"
	"strings"
)

// Decimal is a finite decimal number, coefficient × 10^exp, with the same
// observable behaviour as Python's decimal.Decimal under its default context
// (28 significant digits, ROUND_HALF_EVEN, Emax 999999, Emin -999999). The
// coefficient and exponent are preserved, so Decimal("2.50") prints as "2.50".
// Zero keeps its sign and exponent ("-0.0" is a valid value).
type Decimal struct {
	neg  bool
	coef *big.Int // never nil in values produced by this package; non-negative
	exp  int
}

const (
	decPrec = 28
	decEmax = 999999
	decEmin = -999999
)

var (
	bigZero = big.NewInt(0)
	bigOne  = big.NewInt(1)
	bigTen  = big.NewInt(10)
)

func pow10(n int) *big.Int {
	return new(big.Int).Exp(bigTen, big.NewInt(int64(n)), nil)
}

// numDigits returns the number of decimal digits of a non-negative integer
// (Python len(str(n))); zero has one digit.
func numDigits(n *big.Int) int {
	if n.Sign() == 0 {
		return 1
	}
	return len(n.Text(10))
}

func (d Decimal) coefficient() *big.Int {
	if d.coef == nil {
		return bigZero
	}
	return d.coef
}

// IsZero reports whether d equals zero.
func (d Decimal) IsZero() bool { return d.coefficient().Sign() == 0 }

// Sign returns -1, 0 or +1 according to the numeric sign of d.
func (d Decimal) Sign() int {
	switch {
	case d.IsZero():
		return 0
	case d.neg:
		return -1
	}
	return 1
}

// Coefficient returns a copy of the (non-negative) coefficient of d.
func (d Decimal) Coefficient() *big.Int { return new(big.Int).Set(d.coefficient()) }

// Exponent returns the decimal exponent of d.
func (d Decimal) Exponent() int { return d.exp }

// Negative reports whether the sign bit is set (true for "-0").
func (d Decimal) Negative() bool { return d.neg }

func (d Decimal) adjusted() int { return d.exp + numDigits(d.coefficient()) - 1 }

// DecimalFromBigInt converts an integer exactly (Python Decimal(int)).
func DecimalFromBigInt(x *big.Int) Decimal {
	return Decimal{neg: x.Sign() < 0, coef: new(big.Int).Abs(x), exp: 0}
}

// DecimalOf builds a Decimal from parts; coef must be non-negative.
func DecimalOf(neg bool, coef *big.Int, exp int) Decimal {
	return Decimal{neg: neg, coef: new(big.Int).Set(coef), exp: exp}
}

// ParseDecimal parses a plain decimal numeral: digits with an optional
// fraction and an optional exponent, preceded by an optional sign. Unicode
// decimal digits are accepted like Python's Decimal(str). Infinities and
// NaNs are reported by finite == false.
func ParseDecimal(s string) (d Decimal, finite bool, err error) {
	t := strings.TrimFunc(s, pyIsSpace)
	neg := false
	if strings.HasPrefix(t, "+") || strings.HasPrefix(t, "-") {
		neg = t[0] == '-'
		t = t[1:]
	}
	switch strings.ToLower(t) {
	case "inf", "infinity", "nan", "snan":
		return Decimal{}, false, nil
	}
	rs := []rune(t)
	var digits []byte
	fracLen := 0
	seenDot := false
	seenDigit := false
	i := 0
	for ; i < len(rs); i++ {
		r := rs[i]
		if r == '.' && !seenDot {
			seenDot = true
			continue
		}
		if !pyIsDecimal(r) {
			break
		}
		seenDigit = true
		digits = append(digits, byte('0'+pyDecimalValue(r)))
		if seenDot {
			fracLen++
		}
	}
	if !seenDigit {
		return Decimal{}, false, fmt.Errorf("invalid decimal literal %q", s)
	}
	exp := 0
	if i < len(rs) {
		if rs[i] != 'e' && rs[i] != 'E' {
			return Decimal{}, false, fmt.Errorf("invalid decimal literal %q", s)
		}
		i++
		eneg := false
		if i < len(rs) && (rs[i] == '+' || rs[i] == '-') {
			eneg = rs[i] == '-'
			i++
		}
		if i >= len(rs) {
			return Decimal{}, false, fmt.Errorf("invalid decimal literal %q", s)
		}
		ev := 0
		for ; i < len(rs); i++ {
			if !pyIsDecimal(rs[i]) {
				return Decimal{}, false, fmt.Errorf("invalid decimal literal %q", s)
			}
			ev = ev*10 + pyDecimalValue(rs[i])
			if ev > 1<<40 {
				return Decimal{}, false, fmt.Errorf("decimal exponent out of range in %q", s)
			}
		}
		if eneg {
			ev = -ev
		}
		exp = ev
	}
	coef, ok := new(big.Int).SetString(string(digits), 10)
	if !ok {
		return Decimal{}, false, fmt.Errorf("invalid decimal literal %q", s)
	}
	return Decimal{neg: neg, coef: coef, exp: exp - fracLen}, true, nil
}

// String renders d like Python's str(Decimal): plain notation when the
// exponent is not positive and the adjusted exponent is at least -6,
// scientific notation otherwise.
func (d Decimal) String() string {
	sign := ""
	if d.neg {
		sign = "-"
	}
	digits := d.coefficient().Text(10)
	leftdigits := d.exp + len(digits)
	var dotplace int
	if d.exp <= 0 && leftdigits > -6 {
		dotplace = leftdigits
	} else {
		dotplace = 1
	}
	var intpart, fracpart string
	switch {
	case dotplace <= 0:
		intpart = "0"
		fracpart = "." + strings.Repeat("0", -dotplace) + digits
	case dotplace >= len(digits):
		intpart = digits + strings.Repeat("0", dotplace-len(digits))
	default:
		intpart = digits[:dotplace]
		fracpart = "." + digits[dotplace:]
	}
	exp := ""
	if leftdigits != dotplace {
		exp = fmt.Sprintf("E%+d", leftdigits-dotplace)
	}
	return sign + intpart + fracpart + exp
}

// Cmp compares the numeric values of d and o (-1, 0, +1); the representation
// (exponent, sign of zero) is ignored.
func (d Decimal) Cmp(o Decimal) int {
	switch {
	case d.IsZero() && o.IsZero():
		return 0
	case d.IsZero():
		if o.neg {
			return 1
		}
		return -1
	case o.IsZero():
		if d.neg {
			return -1
		}
		return 1
	}
	if d.neg != o.neg {
		if d.neg {
			return -1
		}
		return 1
	}
	sgn := 1
	if d.neg {
		sgn = -1
	}
	da, oa := d.adjusted(), o.adjusted()
	switch {
	case da > oa:
		return sgn
	case da < oa:
		return -sgn
	}
	a, b := d.coefficient(), o.coefficient()
	switch {
	case d.exp > o.exp:
		a = new(big.Int).Mul(a, pow10(d.exp-o.exp))
	case o.exp > d.exp:
		b = new(big.Int).Mul(b, pow10(o.exp-d.exp))
	}
	return sgn * a.Cmp(b)
}

// Trunc returns the integer part of d, rounded toward zero (Python int(d)).
func (d Decimal) Trunc() *big.Int {
	var r *big.Int
	if d.exp >= 0 {
		r = new(big.Int).Mul(d.coefficient(), pow10(d.exp))
	} else {
		r = new(big.Int).Quo(d.coefficient(), pow10(-d.exp))
	}
	if d.neg {
		r.Neg(r)
	}
	return r
}

// decimalFromFloatExact converts a finite float64 exactly (Decimal.from_float).
func decimalFromFloatExact(f float64) Decimal {
	bits := math.Float64bits(f)
	neg := bits>>63 == 1
	e := int(bits >> 52 & 0x7ff)
	m := bits & (1<<52 - 1)
	if e == 0 {
		e = 1
	} else {
		m |= 1 << 52
	}
	e -= 1075
	n := new(big.Int).SetUint64(m)
	if n.Sign() == 0 {
		return Decimal{neg: neg, coef: n, exp: 0}
	}
	for e < 0 && n.Bit(0) == 0 {
		n.Rsh(n, 1)
		e++
	}
	if e >= 0 {
		n.Lsh(n, uint(e))
		return Decimal{neg: neg, coef: n, exp: 0}
	}
	n.Mul(n, new(big.Int).Exp(big.NewInt(5), big.NewInt(int64(-e)), nil))
	return Decimal{neg: neg, coef: n, exp: e}
}

// decOverflow is the error raised where Python raises decimal.Overflow.
func decOverflow() error {
	return &Error{Code: CodeRTDecimal, Msg: "decimal.Overflow: above Emax"}
}

func etiny() int { return decEmin - decPrec + 1 }
func etop() int  { return decEmax - decPrec + 1 }

// roundHalfEvenDrop drops the lowest `drop` digits of coef, rounding half to
// even. It returns the retained quotient.
func roundHalfEvenDrop(coef *big.Int, drop int) *big.Int {
	if drop <= 0 {
		return new(big.Int).Set(coef)
	}
	p := pow10(drop)
	q, r := new(big.Int).QuoRem(coef, p, new(big.Int))
	half := new(big.Int).Rsh(p, 1)
	switch c := r.Cmp(half); {
	case c > 0:
		q.Add(q, bigOne)
	case c == 0 && q.Bit(0) == 1:
		q.Add(q, bigOne)
	}
	return q
}

// decFix is Decimal._fix under the default context: it rounds to 28 digits
// and enforces the exponent range.
func decFix(neg bool, coef *big.Int, exp int) (Decimal, error) {
	tiny, top := etiny(), etop()
	if coef.Sign() == 0 {
		newExp := exp
		if newExp < tiny {
			newExp = tiny
		}
		if newExp > decEmax {
			newExp = decEmax
		}
		return Decimal{neg: neg, coef: new(big.Int), exp: newExp}, nil
	}
	nd := numDigits(coef)
	expMin := nd + exp - decPrec
	if expMin > top {
		return Decimal{}, decOverflow()
	}
	subnormal := expMin < tiny
	if subnormal {
		expMin = tiny
	}
	if exp < expMin {
		digits := nd + exp - expMin
		var kept *big.Int
		if digits < 0 {
			kept = new(big.Int)
		} else {
			kept = roundHalfEvenDrop(coef, nd-digits)
			if len(kept.Text(10)) > decPrec && kept.Sign() != 0 {
				kept.Quo(kept, bigTen)
				expMin++
			}
		}
		if expMin > top {
			return Decimal{}, decOverflow()
		}
		return Decimal{neg: neg, coef: kept, exp: expMin}, nil
	}
	return Decimal{neg: neg, coef: new(big.Int).Set(coef), exp: exp}, nil
}

// decRescale is Decimal._rescale with ROUND_HALF_EVEN.
func decRescale(d Decimal, exp int) Decimal {
	if d.IsZero() {
		return Decimal{neg: d.neg, coef: new(big.Int), exp: exp}
	}
	if d.exp >= exp {
		return Decimal{neg: d.neg, coef: new(big.Int).Mul(d.coefficient(), pow10(d.exp-exp)), exp: exp}
	}
	nd := numDigits(d.coefficient())
	digits := nd + d.exp - exp
	if digits < 0 {
		return Decimal{neg: d.neg, coef: new(big.Int), exp: exp}
	}
	return Decimal{neg: d.neg, coef: roundHalfEvenDrop(d.coefficient(), nd-digits), exp: exp}
}

type workRep struct {
	sign int
	n    *big.Int
	exp  int
}

func newWorkRep(d Decimal) *workRep {
	s := 0
	if d.neg {
		s = 1
	}
	return &workRep{s, new(big.Int).Set(d.coefficient()), d.exp}
}

// normalizeWork aligns two operands for addition (_pydecimal._normalize).
func normalizeWork(op1, op2 *workRep) {
	var tmp, other *workRep
	if op1.exp < op2.exp {
		tmp, other = op2, op1
	} else {
		tmp, other = op1, op2
	}
	tmpLen := numDigits(tmp.n)
	otherLen := numDigits(other.n)
	exp := tmp.exp + min(-1, tmpLen-decPrec-2)
	if otherLen+other.exp-1 < exp {
		other.n = big.NewInt(1)
		other.exp = exp
	}
	tmp.n = new(big.Int).Mul(tmp.n, pow10(tmp.exp-other.exp))
	tmp.exp = other.exp
}

func decAdd(a, b Decimal) (Decimal, error) {
	exp := min(a.exp, b.exp)
	switch {
	case a.IsZero() && b.IsZero():
		return decFix(a.neg && b.neg, new(big.Int), exp)
	case a.IsZero():
		r := decRescale(b, max(exp, b.exp-decPrec-1))
		return decFix(r.neg, r.coefficient(), r.exp)
	case b.IsZero():
		r := decRescale(a, max(exp, a.exp-decPrec-1))
		return decFix(r.neg, r.coefficient(), r.exp)
	}
	op1, op2 := newWorkRep(a), newWorkRep(b)
	normalizeWork(op1, op2)
	var resSign int
	if op1.sign != op2.sign {
		c := op1.n.Cmp(op2.n)
		if c == 0 {
			return decFix(false, new(big.Int), exp)
		}
		if c < 0 {
			op1, op2 = op2, op1
		}
		if op1.sign == 1 {
			resSign = 1
			op1.sign, op2.sign = op2.sign, op1.sign
		}
	} else if op1.sign == 1 {
		resSign = 1
		op1.sign, op2.sign = 0, 0
	}
	var n *big.Int
	if op2.sign == 0 {
		n = new(big.Int).Add(op1.n, op2.n)
	} else {
		n = new(big.Int).Sub(op1.n, op2.n)
	}
	return decFix(resSign == 1, n, op1.exp)
}

func decNegate(d Decimal) Decimal { return Decimal{neg: !d.neg, coef: d.coefficient(), exp: d.exp} }

func decSub(a, b Decimal) (Decimal, error) { return decAdd(a, decNegate(b)) }

// decNeg is unary minus (Decimal.__neg__): -0 is +0, and the result is
// rounded to the context precision.
func decNeg(d Decimal) (Decimal, error) {
	if d.IsZero() {
		return decFix(false, new(big.Int), d.exp)
	}
	return decFix(!d.neg, d.coefficient(), d.exp)
}

func decMul(a, b Decimal) (Decimal, error) {
	neg := a.neg != b.neg
	exp := a.exp + b.exp
	if a.IsZero() || b.IsZero() {
		return decFix(neg, new(big.Int), exp)
	}
	return decFix(neg, new(big.Int).Mul(a.coefficient(), b.coefficient()), exp)
}

// decDiv is Decimal.__truediv__; the divisor must be non-zero.
func decDiv(a, b Decimal) (Decimal, error) {
	neg := a.neg != b.neg
	if a.IsZero() {
		return decFix(neg, new(big.Int), a.exp-b.exp)
	}
	shift := numDigits(b.coefficient()) - numDigits(a.coefficient()) + decPrec + 1
	exp := a.exp - b.exp - shift
	var coeff, rem *big.Int
	if shift >= 0 {
		coeff, rem = new(big.Int).QuoRem(new(big.Int).Mul(a.coefficient(), pow10(shift)), b.coefficient(), new(big.Int))
	} else {
		coeff, rem = new(big.Int).QuoRem(a.coefficient(), new(big.Int).Mul(b.coefficient(), pow10(-shift)), new(big.Int))
	}
	if rem.Sign() != 0 {
		if new(big.Int).Rem(coeff, big.NewInt(5)).Sign() == 0 {
			coeff.Add(coeff, bigOne)
		}
	} else {
		ideal := a.exp - b.exp
		for exp < ideal && new(big.Int).Rem(coeff, bigTen).Sign() == 0 {
			coeff.Quo(coeff, bigTen)
			exp++
		}
	}
	return decFix(neg, coeff, exp)
}
