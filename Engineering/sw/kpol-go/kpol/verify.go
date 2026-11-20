package kpol

import (
	"fmt"
	"strings"
)

// VerificationFailure is one failed check of a Proof block.
type VerificationFailure struct{ ScenarioOrAssert, Message string }

// VerificationReport is the outcome of Verify (KPOL-PRF-1).
type VerificationReport struct {
	TotalChecks, PassedChecks int
	Failures                  []VerificationFailure
}

// Passed reports whether no check failed.
func (r *VerificationReport) Passed() bool { return len(r.Failures) == 0 }

// Verify checks the Proof block of m: every scenario runs on a fresh
// interpreter, asserts are evaluated around each step, and vacuous asserts or
// an entirely vacuous Proof are reported as failures (KPOL-PRF-1). A returned
// error is a runtime error raised inside a scenario. Only
// WithFailClosedHazards is meaningful among the options.
func Verify(m *Module, opts ...Option) (*VerificationReport, error) {
	cfg := newConfig(opts)
	report := &VerificationReport{}
	var asserts []AssertProperty
	var scenarios []Scenario
	for _, item := range m.Proofs {
		switch p := item.(type) {
		case AssertProperty:
			asserts = append(asserts, p)
		case Scenario:
			scenarios = append(scenarios, p)
		}
	}
	activated := map[string]bool{}

	for _, sc := range scenarios {
		in, err := NewInterpreter(m, WithFailClosedHazards(cfg.failClosed))
		if err != nil {
			return nil, err
		}
		for i, item := range sc.Items {
			idx := i + 1
			switch it := item.(type) {
			case StepAction:
				payload := map[string]Value{}
				for _, a := range it.Args {
					v, err := eval(a.Value, in.state)
					if err != nil {
						return nil, err
					}
					payload[a.Name] = v
				}
				pre := mergeEnv(in.state, payload)
				var active []AssertProperty
				for _, prop := range asserts {
					if prop.Event != it.Event {
						continue
					}
					report.TotalChecks++
					g, err := eval(prop.Guard, pre)
					if err != nil {
						return nil, err
					}
					if isTrue(g) {
						activated[prop.Name] = true
						active = append(active, prop)
					} else {
						report.PassedChecks++
					}
				}
				if _, err := in.Run([]EventInput{{Name: it.Event, Payload: payload}}); err != nil {
					return nil, err
				}
				post := mergeEnv(in.state, payload)
				for _, prop := range active {
					v, err := eval(prop.Expectation, post)
					if err != nil {
						return nil, err
					}
					if isTrue(v) {
						report.PassedChecks++
					} else {
						report.Failures = append(report.Failures, VerificationFailure{
							prop.Name,
							fmt.Sprintf("Assert violated in scenario %s step %d (%s)", sc.Name, idx, it.Event),
						})
					}
				}
			case ExpectCheck:
				report.TotalChecks++
				v, err := eval(it.Expression, in.state)
				if err != nil {
					return nil, err
				}
				if isTrue(v) {
					report.PassedChecks++
				} else {
					report.Failures = append(report.Failures, VerificationFailure{
						sc.Name,
						fmt.Sprintf("Expectation failed at step %d: state=%s", idx, reprState(m, in.state)),
					})
				}
			}
		}
	}

	for _, prop := range asserts {
		if !activated[prop.Name] {
			report.Failures = append(report.Failures, VerificationFailure{
				prop.Name,
				fmt.Sprintf("Vacuous assert %s: guard was never satisfied in any scenario", pyRepr(prop.Name)),
			})
		}
	}
	if len(m.Proofs) > 0 && report.TotalChecks == 0 && len(report.Failures) == 0 {
		report.Failures = append(report.Failures, VerificationFailure{
			m.Name, "Vacuous Proof: declared Proof items evaluated zero executable checks",
		})
	}
	return report, nil
}

// VerifyModule is Verify with an explicit fail-closed switch (reference:
// verify_module(module, fail_closed_hazards)).
func VerifyModule(m *Module, failClosedHazards bool) (*VerificationReport, error) {
	return Verify(m, WithFailClosedHazards(failClosedHazards))
}

// reprState renders the state like Python's repr of the reference dict:
// {'x': 1, 'ok': True, 'v': Decimal('2.50')} in declaration order.
func reprState(m *Module, state map[string]Value) string {
	parts := make([]string, 0, len(m.States))
	for _, s := range m.States {
		parts = append(parts, pyRepr(s.Name)+": "+ReprValue(state[s.Name]))
	}
	return "{" + strings.Join(parts, ", ") + "}"
}
