package ekpol

import (
	"fmt"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

// Diagnostic codes of EKPOL (specification section 12).
const (
	CodeSyntax    = "EKPOL-SYNTAX-ERR"
	CodeType      = "EKPOL-TYPE-ERR"
	CodeInvariant = "EKPOL-INVARIANT-ERR"
	CodeRange     = "EKPOL-RANGE-ERR"
	CodeCollision = "EKPOL-COLLISION-ERR"
	CodeCycle     = "EKPOL-CYCLE-ERR"
	CodeProof     = "EKPOL-PROOF-ERR"
	// CodeInternal marks inputs on which the Python reference dies with an
	// unhandled exception instead of a diagnostic (for example int("010", 0)
	// inside an action, or an undeclared event in KPOL -> EKPOL). The Go port
	// reports them as ordinary errors with this code.
	CodeInternal = "EKPOL-INTERNAL"
)

func newErr(code, format string, args ...any) *kpol.Error {
	return &kpol.Error{Code: code, Msg: fmt.Sprintf(format, args...)}
}

func syntaxErr(format string, args ...any) *kpol.Error {
	return newErr(CodeSyntax, format, args...)
}

func internalErr(format string, args ...any) *kpol.Error {
	return newErr(CodeInternal, format, args...)
}
