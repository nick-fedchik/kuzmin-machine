// Command kpolc is the KPOL / EKPOL / KPOL-AUTH toolchain: compiler to CME-RAW-1
// images, EKPOL<->KPOL translator, C99 safety-module emitter with a Z3
// certificate, static checker, Proof verifier and reference interpreter.
package main

import (
	"fmt"
	"io"
	"os"
	"strings"
)

// Version is the kpolc toolchain version.
const Version = "0.1.0"

// Exit codes: 0 success, 1 failed verification, 2 usage / I/O / rejected source.
const (
	exitOK       = 0
	exitVerify   = 1
	exitRejected = 2
)

const usageText = `kpolc — KPOL / EKPOL / KPOL-AUTH toolchain

Usage: kpolc <command> [options] ...

Commands:
  build    SOURCE [IMAGE]   compile .kpol/.ekpol to a 1024-byte CME-RAW-1 image;
                            --emit-kpol/--emit-ekpol translate, --emit-c99/--emit-z3-cert
                            generate the C99 safety module and Z3 certificate
  check    SOURCE           parse and statically check a program
  verify   SOURCE           run the Proof block (.kpol) or embedded tests (.ekpol)
  run      SOURCE.kpol      feed events to the reference interpreter: -e 'Buy(count=1)'
  to-kpol  SOURCE.ekpol     translate EKPOL to classic KPOL on stdout
  to-ekpol SOURCE.kpol      translate KPOL to EKPOL on stdout (--ekpol-style symbolic|keyword)
  auth     INPUT [options]  KPOL-AUTH frontend and KPOL-AUTH-L1 lowering (--check, --emit-bram, --emit-dogo)
  auth-cst INPUT            print the KPOL-AUTH concrete syntax tree
  auth-run INPUT            lower an L1 program and feed writes to the Do/Go machine: -w Concept=value
  version                   print the toolchain version

Exit codes: 0 success, 1 verification failed, 2 usage error, I/O error or rejected source.
Event tracing over an image is done by the VMK debugger: vmk --program IMAGE --trace-events SPEC.
`

func main() {
	os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr))
}

func run(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprint(stderr, usageText)
		return exitRejected
	}
	cmd, rest := args[0], args[1:]
	switch cmd {
	case "build":
		return cmdBuild(rest, stdout, stderr)
	case "check":
		return cmdCheck(rest, stdout, stderr)
	case "verify":
		return cmdVerify(rest, stdout, stderr)
	case "run":
		return cmdRun(rest, stdout, stderr)
	case "to-kpol":
		return cmdTranslate(rest, true, stdout, stderr)
	case "to-ekpol":
		return cmdTranslate(rest, false, stdout, stderr)
	case "auth":
		return cmdAuth(rest, stdout, stderr)
	case "auth-cst":
		return cmdAuthCST(rest, stdout, stderr)
	case "auth-run":
		return cmdAuthRun(rest, stdout, stderr)
	case "version", "--version", "-v":
		fmt.Fprintf(stdout, "kpolc %s\n", Version)
		return exitOK
	case "help", "--help", "-h":
		fmt.Fprint(stdout, usageText)
		return exitOK
	}
	fmt.Fprintf(stderr, "kpolc: unknown command %q\n\n%s", cmd, usageText)
	return exitRejected
}

func isEKPOL(path string) bool { return strings.EqualFold(pathExt(path), ".ekpol") }

func pathExt(p string) string {
	if i := strings.LastIndexByte(p, '.'); i >= 0 && !strings.ContainsAny(p[i:], "/\\") {
		return p[i:]
	}
	return ""
}

func stem(p string) string {
	base := p
	if i := strings.LastIndexAny(base, "/\\"); i >= 0 {
		base = base[i+1:]
	}
	if i := strings.LastIndexByte(base, '.'); i > 0 {
		base = base[:i]
	}
	return base
}
