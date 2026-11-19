//go:build public

package vmk

import (
	"bytes"
	"strings"
	"testing"
)

func TestPublicStandaloneSimOnlyTargetGuard(t *testing.T) {
	var outBuf, errBuf bytes.Buffer
	for _, badArgs := range [][]string{
		{"--mode", "bram64", "--example", "increase", "--stdio", "--target", "hw-mmio"},
		{"--mode", "conceptual", "--example", "if", "--target", "remote-board"},
		{"--example", "bms", "--connect", "custom-host"},
	} {
		outBuf.Reset()
		errBuf.Reset()
		code := RunCLI(badArgs, strings.NewReader("5\n"), &outBuf, &errBuf)
		if code != 2 || strings.TrimSpace(errBuf.String()) != ErrStandaloneSimOnly {
			t.Fatalf("expected exit code 2 and exact ErrStandaloneSimOnly for args %v, got code=%d stderr=%q",
				badArgs, code, errBuf.String())
		}
	}
	if _, err := NewMachineConnection("non-sim", nil); err == nil || err.Error() != ErrStandaloneSimOnly {
		t.Fatalf("expected NewMachineConnection(non-sim) to fail with ErrStandaloneSimOnly, got %v", err)
	}
}
