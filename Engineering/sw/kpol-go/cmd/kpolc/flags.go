package main

import (
	"flag"
	"fmt"
	"io"
	"strings"
)

// parseFlags parses flags that may be interleaved with positional arguments
// (as argparse does) and returns the positional arguments.
func parseFlags(fs *flag.FlagSet, args []string) ([]string, error) {
	var positional []string
	for {
		if err := fs.Parse(args); err != nil {
			return nil, err
		}
		args = fs.Args()
		if len(args) == 0 {
			return positional, nil
		}
		positional = append(positional, args[0])
		args = args[1:]
	}
}

func newFlagSet(name string, stderr io.Writer) *flag.FlagSet {
	fs := flag.NewFlagSet("kpolc "+name, flag.ContinueOnError)
	fs.SetOutput(stderr)
	return fs
}

// stringList is a repeatable string flag.
type stringList []string

func (s *stringList) String() string     { return strings.Join(*s, ",") }
func (s *stringList) Set(v string) error { *s = append(*s, v); return nil }

func fail(stderr io.Writer, code int, format string, a ...any) int {
	fmt.Fprintf(stderr, format+"\n", a...)
	return code
}
