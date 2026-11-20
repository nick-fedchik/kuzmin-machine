package c99

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os/exec"
	"strings"
	"time"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

// ErrZ3Required is returned (fail-closed, finding F-02) when no usable "z3"
// binary is available. The text deliberately equals the reference
// RuntimeError (which also names the Python package this port does not use).
var ErrZ3Required = &kpol.Error{Msg: "Z3 solver is required: neither z3-solver Python package nor 'z3' binary is installed"}

const defaultZ3Timeout = 60 * time.Second

// solver runs SMT-LIB2 queries through "z3 -in -smt2".
type solver struct {
	path    string
	timeout time.Duration
}

func newSolver(opts Options) (*solver, error) {
	path := opts.Z3Path
	if path == "" {
		path = "z3"
	}
	resolved, err := exec.LookPath(path)
	if err != nil {
		return nil, ErrZ3Required
	}
	timeout := opts.Z3Timeout
	if timeout <= 0 {
		timeout = defaultZ3Timeout
	}
	return &solver{path: resolved, timeout: timeout}, nil
}

func (s *solver) run(args []string, stdin string) (stdout, stderr string, code int, err error) {
	ctx, cancel := context.WithTimeout(context.Background(), s.timeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, s.path, args...)
	cmd.WaitDelay = time.Second
	cmd.Stdin = strings.NewReader(stdin)
	var out, errb bytes.Buffer
	cmd.Stdout, cmd.Stderr = &out, &errb
	runErr := cmd.Run()
	if ctx.Err() != nil {
		return "", "", -1, &kpol.Error{Code: "C99-Z3-TIMEOUT", Msg: fmt.Sprintf("z3 did not finish within %s", s.timeout)}
	}
	var exitErr *exec.ExitError
	switch {
	case runErr == nil:
		return out.String(), errb.String(), 0, nil
	case errors.As(runErr, &exitErr):
		return out.String(), errb.String(), exitErr.ExitCode(), nil
	}
	return "", "", -1, &kpol.Error{Code: "C99-Z3-EXEC", Msg: runErr.Error()}
}

// version mirrors _detect_z3_cli_version.
func (s *solver) version() (string, error) {
	out, errOut, code, err := s.run([]string{"--version"}, "")
	if err != nil {
		return "", err
	}
	if code != 0 {
		return "", &kpol.Error{Code: "C99-Z3-EXEC", Msg: fmt.Sprintf("z3 --version failed (rc=%d): %s", code, pyStrip(errOut))}
	}
	return "z3-cli (" + pyStrip(out) + ")", nil
}

// check mirrors _solve_smt2 on the CLI path: it appends (check-sat) and
// returns the verdict ("sat", "unsat" or "unknown") together with the
// stripped stdout, which the reference uses as the "witness" text.
func (s *solver) check(query string) (verdict, output string, err error) {
	out, errOut, code, err := s.run([]string{"-in", "-smt2"}, query+"\n(check-sat)\n")
	if err != nil {
		return "", "", err
	}
	if code != 0 && !strings.Contains(out, "sat") {
		detail := pyStrip(errOut)
		if detail == "" {
			detail = pyStrip(out)
		}
		return "", "", &kpol.Error{Msg: fmt.Sprintf("z3 CLI failed (rc=%d): %s", code, detail)}
	}
	for _, line := range strings.Split(out, "\n") {
		switch l := pyStrip(line); l {
		case "sat", "unsat", "unknown":
			return l, pyStrip(out), nil
		}
	}
	return "unknown", pyStrip(out), nil
}
