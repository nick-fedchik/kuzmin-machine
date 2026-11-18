package main

import (
	"os"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/vmk-go/internal/vmk"
)

func main() {
	os.Exit(vmk.RunCLI(os.Args[1:], os.Stdin, os.Stdout, os.Stderr))
}
