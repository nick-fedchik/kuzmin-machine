package kpol

import (
	"crypto/sha256"
	"encoding/hex"
	"strings"
)

// ParseTriad links independent problem, solution and proof sources into one
// module (reference: parse_triad_files). All three sources are mandatory;
// lines starting with "namespace " or "import " are dropped, the sources are
// concatenated and parsed as one module, and the SHA-256 digests of the
// original sources are recorded in the module. The result has no
// PhaseAliasesUsed flag, as in the reference.
func ParseTriad(problem, solution, proof string) (*Module, error) {
	if pyStrip(problem) == "" {
		return nil, &Error{Msg: "DO-178C DAL A violation: problem_src (.kproblem) is mandatory"}
	}
	if pyStrip(solution) == "" {
		return nil, &Error{Msg: "DO-178C DAL A violation: solution_src (.ksolution) is mandatory"}
	}
	if pyStrip(proof) == "" {
		return nil, &Error{Msg: "DO-178C DAL A violation: proof_src (.kproof) is mandatory and cannot be empty"}
	}
	combined := sanitizeTriad(problem) + "\n" + sanitizeTriad(solution) + "\n" + sanitizeTriad(proof)
	parsed, err := Parse(combined)
	if err != nil {
		return nil, err
	}
	if len(parsed.Proofs) == 0 {
		return nil, &Error{Msg: "DO-178C DAL A violation: module must declare at least one assert or scenario in Proof block"}
	}
	return &Module{
		Name:         parsed.Name,
		Requirements: parsed.Requirements,
		Events:       parsed.Events,
		States:       parsed.States,
		Rules:        parsed.Rules,
		ProofPresent: parsed.ProofPresent,
		Proofs:       parsed.Proofs,
		ProblemHash:  sha256Hex(problem),
		SolutionHash: sha256Hex(solution),
		ProofHash:    sha256Hex(proof),
	}, nil
}

func sanitizeTriad(src string) string {
	var lines []string
	for _, line := range pySplitLines(src) {
		s := pyStrip(line)
		if strings.HasPrefix(s, "namespace ") || strings.HasPrefix(s, "import ") {
			continue
		}
		lines = append(lines, line)
	}
	return strings.Join(lines, "\n")
}

func sha256Hex(s string) string {
	sum := sha256.Sum256([]byte(s))
	return hex.EncodeToString(sum[:])
}
