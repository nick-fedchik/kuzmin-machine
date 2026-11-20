package ekpol

import "math/big"

// Range limits are functions so that no package-level *big.Int can be mutated by accident.
func minInt16() *big.Int { return big.NewInt(-32768) }
func maxInt16() *big.Int { return big.NewInt(32767) }

// flipCmpOp mirrors a comparison operator ("5 < x" is "x > 5").
func flipCmpOp(op string) (string, bool) {
	switch op {
	case "<":
		return ">", true
	case ">":
		return "<", true
	case "<=":
		return ">=", true
	case ">=":
		return "<=", true
	case "==", "!=":
		return op, true
	}
	return "", false
}
