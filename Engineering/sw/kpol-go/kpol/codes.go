package kpol

// Diagnostic codes for conditions where the Python reference raises an
// exception other than KpolError (an unhandled crash). The port reports them
// as ordinary *Error values carrying one of these codes.
const (
	// CodeRTType: unsupported operand types, e.g. binary float mixed with Decimal.
	CodeRTType = "KPOL-RT-TYPE"
	// CodeRTOverflow: a number exceeds the range of the target representation.
	CodeRTOverflow = "KPOL-RT-OVERFLOW"
	// CodeRTDecimal: decimal.Overflow / decimal.InvalidOperation in the reference.
	CodeRTDecimal = "KPOL-RT-DECIMAL"
	// CodeRTValue: ValueError in the reference (for example the literal "²", D-K1).
	CodeRTValue = "KPOL-RT-VALUE"
	// CodeParseDepth: expression nesting exceeds the parser limit (the reference
	// hits Python's recursion limit instead).
	CodeParseDepth = "KPOL-PARSE-DEPTH"
)
