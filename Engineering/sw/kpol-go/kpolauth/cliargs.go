package kpolauth

import (
	"fmt"
	"io"
	"regexp"
	"strings"
)

// cliArgs is the result of parsing the command line.
type cliArgs struct {
	input    string
	check    bool
	emitBram *string
	emitDogo *string
}

// The parser reproduces the argparse behaviour of __main__.py that is
// observable from the command line: long options may be abbreviated, values may
// be attached with "=", "--" ends the options, and errors print the usage and
// exit with code 2.

var negativeNumber = regexp.MustCompile(`^-\d+$|^-\d*\.\d+$`)

// cliOptions lists the option strings in definition order.
var cliOptions = []string{"-h", "--help", "--check", "--emit-bram", "--emit-dogo"}

type wordKind int

const (
	wordPositional wordKind = iota
	wordOption
	wordUnknown
	wordAmbiguous
)

// word is a classified command-line word (argparse._parse_optional).
type word struct {
	kind        wordKind
	option      string
	explicit    string
	hasExplicit bool
	matches     []string
}

func classify(text string) word {
	if text == "" || text[0] != '-' {
		return word{kind: wordPositional}
	}
	for _, o := range cliOptions {
		if text == o {
			return word{kind: wordOption, option: o}
		}
	}
	if len(text) == 1 {
		return word{kind: wordPositional}
	}
	name, value, hasValue := strings.Cut(text, "=")
	if hasValue {
		for _, o := range cliOptions {
			if name == o {
				return word{kind: wordOption, option: o, explicit: value, hasExplicit: true}
			}
		}
	}
	if strings.HasPrefix(text, "--") {
		var matches []string
		for _, o := range cliOptions {
			if strings.HasPrefix(o, "--") && strings.HasPrefix(o, name) {
				matches = append(matches, o)
			}
		}
		switch len(matches) {
		case 0:
		case 1:
			return word{kind: wordOption, option: matches[0], explicit: value, hasExplicit: hasValue}
		default:
			return word{kind: wordAmbiguous, matches: matches}
		}
	} else if strings.HasPrefix(text, "-h") {
		// A cluster such as -hx runs the help action first, like argparse.
		return word{kind: wordOption, option: "-h"}
	}
	if negativeNumber.MatchString(text) || strings.Contains(text, " ") {
		return word{kind: wordPositional}
	}
	return word{kind: wordUnknown}
}

func usageError(stderr io.Writer, format string, args ...any) int {
	fmt.Fprint(stderr, cliUsage)
	fmt.Fprintf(stderr, "%s: error: %s\n", cliProg, fmt.Sprintf(format, args...))
	return ExitAuth
}

func ambiguousError(stderr io.Writer, text string, w word) int {
	return usageError(stderr, "ambiguous option: %s could match %s", text, strings.Join(w.matches, ", "))
}

// parseCLIArgs parses the command line. It returns done=true with the exit code
// when the command must stop (help or a usage error).
func parseCLIArgs(args []string, stdout, stderr io.Writer) (a cliArgs, code int, done bool) {
	var extras []string
	haveInput, afterSep := false, false
	for i := 0; i < len(args); i++ {
		text := args[i]
		if !afterSep && text == "--" {
			afterSep = true
			continue
		}
		w := word{kind: wordPositional}
		if !afterSep {
			w = classify(text)
		}
		switch w.kind {
		case wordAmbiguous:
			return a, ambiguousError(stderr, text, w), true
		case wordPositional:
			if haveInput {
				extras = append(extras, text)
			} else {
				a.input, haveInput = text, true
			}
		case wordUnknown:
			extras = append(extras, text)
		case wordOption:
			switch w.option {
			case "-h", "--help":
				if w.hasExplicit {
					return a, usageError(stderr, "argument -h/--help: ignored explicit argument %s", pyRepr(w.explicit)), true
				}
				fmt.Fprint(stdout, cliHelp)
				return a, ExitOK, true
			case "--check":
				if w.hasExplicit {
					return a, usageError(stderr, "argument --check: ignored explicit argument %s", pyRepr(w.explicit)), true
				}
				a.check = true
			default:
				value := w.explicit
				if !w.hasExplicit {
					if i+1 >= len(args) || args[i+1] == "--" || classify(args[i+1]).kind != wordPositional {
						return a, usageError(stderr, "argument %s: expected one argument", w.option), true
					}
					i++
					value = args[i]
				}
				if w.option == "--emit-bram" {
					a.emitBram = &value
				} else {
					a.emitDogo = &value
				}
			}
		}
	}
	if !haveInput {
		return a, usageError(stderr, "the following arguments are required: input"), true
	}
	if len(extras) > 0 {
		return a, usageError(stderr, "unrecognized arguments: %s", strings.Join(extras, " ")), true
	}
	return a, ExitOK, false
}
