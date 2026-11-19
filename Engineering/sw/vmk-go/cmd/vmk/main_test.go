package main

import (
	"bytes"
	"strings"
	"testing"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/vmk-go/internal/vmk"
)

func TestMainVersionAndSubcommands(t *testing.T) {
	var out, errBuf bytes.Buffer
	code := vmk.RunCLI([]string{"version"}, strings.NewReader(""), &out, &errBuf)
	if code != 0 || !strings.Contains(out.String(), "VMK (Virtual Machine of Kuzmin) v0.3.1") {
		t.Fatalf("unexpected version output (code=%d): %s", code, out.String())
	}

	out.Reset()
	errBuf.Reset()
	code = vmk.RunCLI([]string{"tui", "--example", "if"}, strings.NewReader(""), &out, &errBuf)
	if code != 0 || !strings.Contains(out.String(), "IfToggle") {
		t.Fatalf("unexpected tui subcommand output (code=%d): %s", code, out.String())
	}
}
