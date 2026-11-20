// Package kpolauth implements the KPOL-AUTH native dialect toolchain of the
// Kuzmin Machine: lexer, concrete syntax tree parser with the uncertainty gates
// KPOL-AUTH-U01..U12, the KPOL-AUTH-L1 lowering to Do/Go bytecode and the
// CME-RAW-1 routing image, the reference Do/Go stack VM and the command-line
// driver.
//
// The normative definition is Engineering/specifications/kpol/
// kpol-auth-formal-specification.md (rules KPA-LEX, KPA-SYN, KPA-CTX, KPA-CST,
// KPA-L and KPA-VM). The Python package Engineering/sw/kpol-auth is the oracle
// for differential tests; every diagnostic text matches it. Where the reference
// raises an unhandled exception (decision D-A1, deep nesting) or never
// terminates (D-A10) the Go port returns an ordinary *Error with its own code
// instead: CodeNonDecimalDigit, CodeLowerNonDecimalDigit, CodeNestingLimit and
// CodeVMSteps.
//
// Source text positions are expressed in Unicode code points and UTF-8 bytes
// (KPA-LEX-1). Character classes (str.isdigit, str.isalpha, str.isalnum) are
// frozen from the Python reference so that the lexer does not depend on the
// Unicode version of the Go toolchain.
package kpolauth
