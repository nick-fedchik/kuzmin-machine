package kpolauth

import (
	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

// Codes of the diagnostics that the reference implementation does not define
// because it fails with an unhandled exception (or never terminates) there.
const (
	// CodeNonDecimalDigit is returned by the parser when an INT token contains a
	// character accepted by str.isdigit but not by int() (decision D-A1); the
	// reference raises ValueError.
	CodeNonDecimalDigit = "KPOL-AUTH-INT-01"
	// CodeLowerNonDecimalDigit is the lowering counterpart of CodeNonDecimalDigit.
	CodeLowerNonDecimalDigit = "KPOL-LOWER-INT-01"
	// CodeNestingLimit is returned when groups, parameters or ":=" chains nest
	// deeper than MaxNesting; the reference raises RecursionError much earlier.
	CodeNestingLimit = "KPOL-AUTH-LIMIT-01"
	// CodeConfig is returned for an invalid Config (ValueError in the reference).
	CodeConfig = "KPOL-AUTH-CONFIG"
)

// Span is a source location: 1-based line and column in Unicode code points,
// 0-based code point offset and length, and the exact UTF-8 byte range
// (ByteEnd is exclusive).
type Span struct {
	Line       int
	Column     int
	Offset     int
	Length     int
	EndLine    int
	EndColumn  int
	ByteOffset int
	ByteEnd    int
}

// Diagnostic is one frontend diagnostic. Severity is "error" or "warning".
// UncertaintyCode and SourceRef are empty for syntax and lexical errors.
type Diagnostic struct {
	Code            string
	Severity        string
	Message         string
	Span            *Span
	UncertaintyCode string
	SourceRef       string
}

// Error is a KPOL-AUTH frontend, lowering or VM error. Code is the diagnostic
// code (KPOL-AUTH-*, KPOL-LOWER-*, KPOL-CLI-IO); Msg is the message text of the
// reference implementation. Error() returns "<Code>: <Msg>", the str() of the
// Python exceptions.
type Error struct {
	Code string
	Msg  string
	// Span locates the problem; nil when the reference gives no location.
	Span *Span
	// Diagnostic is the frontend diagnostic behind the error, nil for lowering,
	// VM and configuration errors.
	Diagnostic *Diagnostic
}

func (e *Error) Error() string { return e.Code + ": " + e.Msg }

// As lets errors.As convert an *Error to a *kpol.Error, so that code written
// for the common diagnostic type of the toolchain handles KPOL-AUTH errors too.
func (e *Error) As(target any) bool {
	if t, ok := target.(**kpol.Error); ok {
		*t = &kpol.Error{Code: e.Code, Msg: e.Msg}
		return true
	}
	return false
}
