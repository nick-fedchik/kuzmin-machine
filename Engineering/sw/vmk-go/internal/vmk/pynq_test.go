//go:build !public

package vmk

import (
	"bytes"
	"strings"
	"testing"
)

func TestEngineeringPYNQTargetAndRemoteExecSafety(t *testing.T) {
	// 1. Unreachable hardware target returns VMK-TARGET-IO and exit code 2
	var outBuf, errBuf bytes.Buffer
	code := RunCLI(
		[]string{"--mode", "bram64", "--example", "increase", "--stdio", "--target", "root@127.0.0.1:1"},
		strings.NewReader("5\n"),
		&outBuf,
		&errBuf,
	)
	if code != 2 || !strings.Contains(errBuf.String(), "VMK-TARGET-IO:") {
		t.Fatalf("expected exit code 2 and VMK-TARGET-IO on unreachable target, got code=%d stderr=%s", code, errBuf.String())
	}

	// 2. Verify safe PYNQ_SUDO_PASS handling in BuildPYNQRemoteExec (no shell interpolation, no default password)
	cmdNoPass, stdinNoPass := BuildPYNQRemoteExec("/home/xilinx/km_vmk_274_work", []int32{120, 180}, "")
	if stdinNoPass != "" || !strings.Contains(cmdNoPass, "sudo -n ./km_pynq_debug_probe program_image.bin 120 180") {
		t.Fatalf("unexpected BuildPYNQRemoteExec for empty password: cmd=%q stdin=%q", cmdNoPass, stdinNoPass)
	}
	specialPass := "p@ss'w0rd; echo $(id) `uname`"
	cmdWithPass, stdinWithPass := BuildPYNQRemoteExec("/home/xilinx/km_vmk_274_work", []int32{120}, specialPass)
	if strings.Contains(cmdWithPass, specialPass) || !strings.Contains(cmdWithPass, "sudo -S -p '' ./km_pynq_debug_probe program_image.bin 120") || stdinWithPass != specialPass+"\n" {
		t.Fatalf("unsafe BuildPYNQRemoteExec with special password: cmd=%q stdin=%q", cmdWithPass, stdinWithPass)
	}
	if gotQuote := ShellQuoteSingle("a'b"); gotQuote != "'a'\\''b'" {
		t.Fatalf("unexpected ShellQuoteSingle('a\\'b'): %q", gotQuote)
	}
}
