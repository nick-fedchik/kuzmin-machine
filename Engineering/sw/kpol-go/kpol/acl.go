package kpol

import (
	"fmt"
	"strings"
)

// Capability bits of the hardware security ACL (reference: CAP_*).
const (
	CapRead      = 0x01
	CapWrite     = 0x02
	CapPinOut    = 0x04
	CapCSPTx     = 0x08
	CapInterrupt = 0x10
	CapLocked    = 0x80
)

// CheckSecurityACL audits the module against the capability table acl
// (reference: check_module_security_acl): a Pin<Out> state needs CapPinOut,
// and a rule may only write a state that has CapWrite (and, for a Pin<Out>
// state, CapPinOut). States absent from acl have CapRead|CapWrite; entries
// for other names are kept and apply to rule targets. The violations are
// returned in the order of the reference; nil means that the module passes.
func CheckSecurityACL(m *Module, acl map[string]int) []string {
	if m == nil {
		return nil
	}
	var violations []string
	caps := make(map[string]int, len(m.States)+len(acl))
	for _, st := range m.States {
		caps[st.Name] = CapRead | CapWrite
	}
	for name, c := range acl {
		caps[name] = c
	}

	for _, st := range m.States {
		if isOutputPin(st.Type) && caps[st.Name]&CapPinOut == 0 {
			violations = append(violations, fmt.Sprintf(
				"ACL violation: state '%s' of type Pin<Out> requires CAP_PIN_OUT (0x04) capability", st.Name))
		}
	}
	for _, rule := range m.Rules {
		for _, act := range rule.Actions {
			if c, ok := caps[act.Name]; ok && c&CapWrite == 0 {
				violations = append(violations, fmt.Sprintf(
					"ACL violation: rule '%s' writes to state '%s' without CAP_WRITE capability", rule.Name, act.Name))
			}
			for _, st := range m.States {
				if st.Name != act.Name {
					continue
				}
				if isOutputPin(st.Type) && caps[act.Name]&CapPinOut == 0 {
					violations = append(violations, fmt.Sprintf(
						"ACL violation: rule '%s' writes to output pin '%s' without CAP_PIN_OUT capability", rule.Name, act.Name))
				}
				break
			}
		}
	}
	return violations
}

// isOutputPin reports whether t is Pin<..., Out, ...> (the reference splits
// the joined parameter list of a Pin type on commas).
func isOutputPin(t TypeRef) bool {
	if t.Name != "Pin" {
		return false
	}
	for _, p := range strings.Split(asKType(t).unit, ",") {
		if p == "Out" {
			return true
		}
	}
	return false
}
