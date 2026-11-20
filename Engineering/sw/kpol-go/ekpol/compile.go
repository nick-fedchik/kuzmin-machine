package ekpol

import (
	"bytes"
	"errors"
	"strings"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

// proofErr wraps a diagnostic of the KPOL reference into EKPOL-PROOF-ERR (EKPOL-B64-16 / B64-20).
func proofErr(err error) error {
	var ke *kpol.Error
	if errors.As(err, &ke) {
		if strings.HasPrefix(ke.Code, "EKPOL-") {
			return ke
		}
		return &kpol.Error{Code: CodeProof, Msg: ke.Error()}
	}
	return &kpol.Error{Code: CodeProof, Msg: err.Error()}
}

// verifyEmbeddedTests runs the generated KPOL Proof against the reference semantics (EKPOL-B64-19).
func verifyEmbeddedTests(kpolText string) error {
	mod, err := parseKPOLSyntax(kpolText)
	if err != nil {
		return proofErr(err)
	}
	rep, err := verifyKPOLProof(mod)
	if err != nil {
		return proofErr(err)
	}
	if len(rep.failures) > 0 {
		reasons := make([]string, len(rep.failures))
		for i, f := range rep.failures {
			reasons[i] = f.where + ": " + f.message
		}
		return newErr(CodeProof, "embedded test verification failed: %s", strings.Join(reasons, "; "))
	}
	return nil
}

// CompileImage compiles EKPOL source to a 1024-byte CME-RAW-1 BRAM image
// (reference: compile_ekpol_to_bram_image on a string).
func CompileImage(src string) ([]byte, error) {
	p, err := Parse(src, "EkpolModule")
	if err != nil {
		return nil, err
	}
	return CompileProgram(p)
}

// CompileProgram compiles a parsed program to a 1024-byte CME-RAW-1 image. Programs
// without bitmask guards are cross-checked against the KPOL-CME-1/2 compiler
// (EKPOL-B64-20) and their embedded tests are executed.
func CompileProgram(p *Program) ([]byte, error) {
	descriptors, err := ValidateB64(p)
	if err != nil {
		return nil, err
	}
	direct := kpol.PackImage(descriptors)

	for i := range p.Concepts {
		if p.Concepts[i].Rules[0].Predicate.Kind == PredBitmask {
			return direct, nil
		}
	}

	multi := len(p.Concepts) > 1
	kpolText, err := ProgramToKPOL(p, multi && len(p.Tests) == 0)
	if err != nil {
		return nil, err
	}
	profile := "KPOL-CME-2"
	if len(p.Concepts) == 1 && len(p.Tests) == 0 {
		profile = "KPOL-CME-1"
	}
	if len(p.Concepts) == 1 {
		if k := p.Concepts[0].Rules[0].Actions[0].Kind; k != ActInc && k != ActDec {
			profile = "KPOL-CME-2"
			if len(p.Tests) == 0 {
				if kpolText, err = ProgramToKPOL(p, true); err != nil {
					return nil, err
				}
			}
		}
	}

	mod, err := parseKPOLSyntax(kpolText)
	if err != nil {
		return nil, proofErr(err)
	}
	var cross []byte
	if profile == "KPOL-CME-1" {
		cross, err = compileCME1(mod)
	} else {
		cross, err = compileCME2(mod)
	}
	if err != nil {
		return nil, proofErr(err)
	}
	if !bytes.Equal(direct, cross) {
		return nil, syntaxErr("internal lowering mismatch between EKPOL and KPOL-CME")
	}
	return direct, nil
}
