package ekpol

import (
	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

// proofFailure is one failed check of a KPOL Proof.
type proofFailure struct{ where, message string }

// proofReport mirrors the reference VerificationReport.
type proofReport struct {
	total, passed int
	failures      []proofFailure
}

// parseKPOLSyntax is Parser(src).parse() of the reference: no static checking.
func parseKPOLSyntax(src string) (*kpol.Module, error) {
	return kpol.ParseSyntax(src)
}

// verifyKPOLProof is verify_module (fail-closed hazards, as in the reference default).
func verifyKPOLProof(m *kpol.Module) (*proofReport, error) {
	rep, err := kpol.VerifyModule(m, true)
	if err != nil {
		return nil, err
	}
	out := &proofReport{total: rep.TotalChecks, passed: rep.PassedChecks}
	for _, f := range rep.Failures {
		out.failures = append(out.failures, proofFailure{where: f.ScenarioOrAssert, message: f.Message})
	}
	return out, nil
}
