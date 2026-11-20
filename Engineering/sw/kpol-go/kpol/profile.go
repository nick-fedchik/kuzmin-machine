package kpol

import (
	"errors"
	"fmt"
	"math/big"
	"strings"
)

// Execution profiles of KPOL on the CME-RAW-1 image (specification §7).
const (
	// ProfileCME1 is the single-concept profile KPOL-CME-1 (§7.3, KPOL-P1-*).
	ProfileCME1 = "KPOL-CME-1"
	// ProfileCME2 is the cascading multi-concept profile KPOL-CME-2 (§7.4, KPOL-P2-*).
	ProfileCME2 = "KPOL-CME-2"
)

// CompileOption configures CompileProfile and CompileProfileDescriptors.
type CompileOption func(*compileConfig)

type compileConfig struct {
	acl     map[string]int
	cascade bool // cascade_map is not None
}

// WithACL supplies the capability table of the security ACL gate (reference
// parameter acl_table, KPOL-P1-10 / KPOL-P2-18): state name -> CAP_* mask.
// States without an entry have CapRead|CapWrite. A nil or empty map is the
// same as no table.
func WithACL(acl map[string]int) CompileOption {
	return func(c *compileConfig) { c.acl = acl }
}

// WithCascadeMap supplies the reference parameter cascade_map. Both profiles
// reject it (KPOL-P1-2, KPOL-P2-2: cascades are declared with `on change`).
// As in the reference, where only None means "absent", a nil map is absent
// and any non-nil map, even an empty one, is rejected. Keys and values are
// state names or decimal CIDs; they are never interpreted by the profiles.
func WithCascadeMap(m map[string]string) CompileOption {
	return func(c *compileConfig) { c.cascade = m != nil }
}

// CompileProfile lowers a KPOL module to a 1024-byte CME-RAW-1 image under the
// named profile (reference: compile_concept_microcode_bram_image with the
// profile argument; KPOL-P1-1..11 and KPOL-P2-1..19). The module is checked
// first; every violation is an *Error whose Code is B3-* (KPOL-CME-1) or
// CME2-* (KPOL-CME-2) and whose text is "<code>: module <name>: <message>",
// identical to the reference. An unknown profile is B3-PROFILE. The Proof gate
// runs Verify.
//
// Where the reference dies with an unhandled Python exception instead of a
// KpolError (for example a float added to a Decimal while a Proof runs), the
// *Error of the front end or interpreter, which carries one of the Code*
// constants of codes.go, is returned as it is: it is not a profile diagnostic.
func CompileProfile(m *Module, profile string, opts ...CompileOption) ([]byte, error) {
	ds, err := CompileProfileDescriptors(m, profile, opts...)
	if err != nil {
		return nil, err
	}
	return PackImage(ds), nil
}

// CompileProfileDescriptors is CompileProfile before packing: it returns the
// programmed descriptors in CID order (CID 0 for KPOL-CME-1; one per state for
// KPOL-CME-2), named after their states. All other slots of the image are zero.
func CompileProfileDescriptors(m *Module, profile string, opts ...CompileOption) ([]Descriptor, error) {
	var cfg compileConfig
	for _, o := range opts {
		if o != nil {
			o(&cfg)
		}
	}
	switch profile {
	case ProfileCME1:
		return compileCME1(m, &cfg)
	case ProfileCME2:
		return compileCME2(m, &cfg)
	}
	return nil, &Error{Code: "B3-PROFILE", Msg: "unsupported profile " + pyRepr(profile)}
}

// profileCtx carries the module name used by every profile diagnostic.
type profileCtx struct{ m *Module }

func (c profileCtx) fail(code, format string, a ...any) error {
	return &Error{Code: code, Msg: fmt.Sprintf("module %s: %s", c.m.Name, fmt.Sprintf(format, a...))}
}

// check is the first gate of both profiles (KPOL-P1-1, KPOL-P2-1): the module
// must pass the static semantics. A crash-equivalent error (non-empty Code)
// is not a KpolError in the reference and is therefore passed through.
func (c profileCtx) check(code string) error {
	if c.m == nil {
		return &Error{Code: code, Msg: "module is nil"}
	}
	if err := Check(c.m); err != nil {
		var e *Error
		if errors.As(err, &e) && e.Code != "" {
			return err
		}
		return c.fail(code, "%s", err.Error())
	}
	return nil
}

// proof runs the Proof gate (KPOL-P1-9 / KPOL-P2-17 tail): the Proof must pass
// with at least one check, all of them satisfied.
func (c profileCtx) proof(code string) error {
	rep, err := Verify(c.m)
	if err != nil {
		var e *Error
		if errors.As(err, &e) && e.Code != "" {
			return err
		}
		return c.fail(code, "reference execution failed: %s", err.Error())
	}
	if rep.TotalChecks == 0 || rep.PassedChecks != rep.TotalChecks || len(rep.Failures) > 0 {
		reasons := make([]string, len(rep.Failures))
		for i, f := range rep.Failures {
			reasons[i] = f.ScenarioOrAssert + ": " + f.Message
		}
		return c.fail(code, "Proof failed: %s", strings.Join(reasons, "; "))
	}
	return nil
}

// acl is the ACL gate shared by the profiles.
func (c profileCtx) acl(code string, cfg *compileConfig) error {
	if v := CheckSecurityACL(c.m, cfg.acl); len(v) > 0 {
		return c.fail(code, "%s", strings.Join(v, "; "))
	}
	return nil
}

func cmeIsName(e Expr, name string) bool {
	n, ok := e.(Name)
	return ok && n.Name == name
}

// cmeIntLiteral recognises an integer literal or a minus sign in front of one
// (the reference tests type(value) is int, so Bool and Decimal literals are
// not integers).
func cmeIntLiteral(e Expr) (*big.Int, bool) {
	switch x := e.(type) {
	case IntLit:
		return x.V, true
	case Unary:
		if lit, ok := x.X.(IntLit); ok && x.Op == "-" {
			return new(big.Int).Neg(lit.V), true
		}
	}
	return nil, false
}

// cmeZeroLiteral is the dataclass equality with Literal(0): the reference
// compares the Python values, and 0 == False == Decimal("0.00").
func cmeZeroLiteral(e Expr) bool {
	switch x := e.(type) {
	case IntLit:
		return x.V.Sign() == 0
	case BoolLit:
		return !x.V
	case DecLit:
		d, finite, err := ParseDecimal(x.Text)
		return err == nil && finite && d.IsZero()
	}
	return false
}

func cmeMinInt32() *big.Int { return big.NewInt(-1 << 31) }
func cmeMaxInt32() *big.Int { return big.NewInt(1<<31 - 1) }

// cmeU32 is value & 0xFFFFFFFF for a value already known to fit 64 bits.
func cmeU32(v *big.Int) uint32 { return uint32(v.Int64()) }

// cmeIsInt32 is TypeRef(name) == TypeRef("Int32").
func cmeIsInt32(t TypeRef) bool {
	return t.Name == "Int32" && t.Unit == "" && len(t.PinParams) == 0
}
