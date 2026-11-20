package kpolauth

import (
	"fmt"
	"sort"
)

// Policy is the handling of one uncertainty gate (KPA-CTX-1).
type Policy string

const (
	// FailClosed stops processing with an error when the gate fires (default).
	FailClosed Policy = "fail-closed"
	// RecordDiagnostic records a warning in Program.Diagnostics and continues.
	RecordDiagnostic Policy = "record-diagnostic"
)

// NameLengthUnit selects the unit in which gate U07 measures Name(x) (limit 16).
type NameLengthUnit string

const (
	// UTF8Bytes measures the length in UTF-8 bytes (default, conservative).
	UTF8Bytes NameLengthUnit = "utf8_bytes"
	// Codepoints measures the length in Unicode code points.
	Codepoints NameLengthUnit = "codepoints"
)

// UncertaintyPoint is one unresolved language question with a single code.
type UncertaintyPoint struct {
	Code          string
	RFC           string
	Topic         string
	SourceStatus  string
	DefaultPolicy string
}

// UncertaintyRegistry returns the registry of the open questions of the
// dialect, KPOL-AUTH-U01..U12 in order (UNCERTAINTY_REGISTRY).
func UncertaintyRegistry() []UncertaintyPoint {
	out := make([]UncertaintyPoint, len(registryData))
	copy(out, registryData[:])
	return out
}

// LookupUncertainty returns the registry entry for code.
func LookupUncertainty(code string) (UncertaintyPoint, bool) {
	for _, p := range registryData {
		if p.Code == code {
			return p, true
		}
	}
	return UncertaintyPoint{}, false
}

// Config is the single configuration point of the uncertainty gates
// (AuthFrontendConfig). The zero value is the default configuration: every
// gate is fail-closed and U07 measures UTF-8 bytes.
type Config struct {
	// Policies overrides the policy of individual gates; absent codes are
	// FailClosed. Keys must be registered codes (KPOL-AUTH-U01..U12).
	Policies map[string]Policy
	// NameLengthUnit is the unit of gate U07; empty means UTF8Bytes.
	NameLengthUnit NameLengthUnit
}

// DefaultConfig returns the default configuration (all gates fail-closed,
// NameLengthUnit UTF8Bytes).
func DefaultConfig() Config {
	return Config{NameLengthUnit: UTF8Bytes}
}

// RecordAllConfig returns a configuration in which every gate records a
// diagnostic instead of stopping.
func RecordAllConfig() Config {
	cfg := DefaultConfig()
	cfg.Policies = make(map[string]Policy, len(registryData))
	for _, p := range registryData {
		cfg.Policies[p.Code] = RecordDiagnostic
	}
	return cfg
}

// Validate reports an unknown code, an unsupported policy or an unsupported
// name length unit, as the constructor of AuthFrontendConfig does.
func (c Config) Validate() error {
	switch c.NameLengthUnit {
	case "", UTF8Bytes, Codepoints:
	default:
		return &Error{Code: CodeConfig, Msg: fmt.Sprintf("Unsupported name_length_unit '%s'", c.NameLengthUnit)}
	}
	codes := make([]string, 0, len(c.Policies))
	for code := range c.Policies {
		codes = append(codes, code)
	}
	sort.Strings(codes)
	for _, code := range codes {
		if _, ok := LookupUncertainty(code); !ok {
			return &Error{Code: CodeConfig, Msg: fmt.Sprintf("Unknown uncertainty code: %s", code)}
		}
		switch c.Policies[code] {
		case FailClosed, RecordDiagnostic:
		default:
			return &Error{Code: CodeConfig, Msg: fmt.Sprintf("Unsupported policy '%s' for %s", c.Policies[code], code)}
		}
	}
	return nil
}

// PolicyFor returns the effective policy of a gate; unset gates are FailClosed.
func (c Config) PolicyFor(code string) Policy {
	if p, ok := c.Policies[code]; ok {
		return p
	}
	return FailClosed
}

// unit returns the effective U07 unit.
func (c Config) unit() NameLengthUnit {
	if c.NameLengthUnit == "" {
		return UTF8Bytes
	}
	return c.NameLengthUnit
}

// bailout carries a frontend error through the recursive-descent code; it is
// recovered at the package boundary and never escapes.
type bailout struct{ err *Error }

// frontend is the state shared by the lexer and the parser: configuration and
// the diagnostics recorded so far.
type frontend struct {
	cfg   Config
	diags []Diagnostic
}

// syntaxError records an error that is independent of the policy and returns
// the value to panic with.
func (f *frontend) syntaxError(code, msg string, span *Span) bailout {
	d := Diagnostic{Code: code, Severity: "error", Message: msg, Span: span}
	f.diags = append(f.diags, d)
	return bailout{&Error{Code: code, Msg: msg, Span: span, Diagnostic: &d}}
}

// emit records an uncertainty diagnostic and panics if the gate is fail-closed
// (emit_uncertainty).
func (f *frontend) emit(code, msg string, span *Span) {
	point, _ := LookupUncertainty(code)
	policy := f.cfg.PolicyFor(code)
	severity := "warning"
	if policy == FailClosed {
		severity = "error"
	}
	d := Diagnostic{
		Code:            code,
		Severity:        severity,
		Message:         msg,
		Span:            span,
		UncertaintyCode: code,
		SourceRef:       point.RFC,
	}
	f.diags = append(f.diags, d)
	if policy == FailClosed {
		panic(bailout{&Error{Code: code, Msg: msg, Span: span, Diagnostic: &d}})
	}
}

// recoverBailout converts a bailout panic into *err; other panics propagate.
func recoverBailout(err *error) {
	if r := recover(); r != nil {
		b, ok := r.(bailout)
		if !ok {
			panic(r)
		}
		*err = b.err
	}
}
