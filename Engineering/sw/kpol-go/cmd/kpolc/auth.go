package main

import (
	"fmt"
	"io"
	"math/big"
	"strconv"
	"strings"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpolauth"
)

func cmdAuth(args []string, stdout, stderr io.Writer) int {
	return kpolauth.RunCLI(args, stdout, stderr)
}

func readAuthSource(path string, stderr io.Writer) (string, bool) {
	text, err := readSource(path, "KPOL")
	if err != nil {
		fmt.Fprintln(stderr, err)
		return "", false
	}
	return text, true
}

// cmdAuthCST prints the concrete syntax tree of a KPOL-AUTH linear text.
func cmdAuthCST(args []string, stdout, stderr io.Writer) int {
	path, ok := singleSource("auth-cst", args, stderr)
	if !ok {
		return exitRejected
	}
	text, ok := readAuthSource(path, stderr)
	if !ok {
		return exitRejected
	}
	prog, err := kpolauth.Parse(text, kpolauth.DefaultConfig())
	if err != nil {
		fmt.Fprintf(stderr, "%v\n", err)
		return exitRejected
	}
	for _, item := range prog.Items {
		dumpNode(stdout, item, 0)
	}
	return exitOK
}

func bigText(x *big.Int) string {
	if x == nil {
		return "-"
	}
	return x.String()
}

func dumpNode(w io.Writer, n kpolauth.Node, depth int) {
	pad := strings.Repeat("  ", depth)
	child := func(c kpolauth.Node) { dumpNode(w, c, depth+1) }
	switch v := n.(type) {
	case *kpolauth.Identifier:
		fmt.Fprintf(w, "%sIdentifier %s\n", pad, v.Token.Value)
	case *kpolauth.Literal:
		fmt.Fprintf(w, "%sLiteral %s\n", pad, v.Token.Value)
	case *kpolauth.Uninit:
		fmt.Fprintf(w, "%sUninit _\n", pad)
	case *kpolauth.Param:
		fmt.Fprintf(w, "%sParam @\n", pad)
		child(v.Target)
	case *kpolauth.BracketGroup:
		fmt.Fprintf(w, "%sGroup %s%s (%s)\n", pad, v.OpenToken.Value, v.CloseToken.Value, v.Kind)
		for _, e := range v.Elements {
			child(e)
		}
	case *kpolauth.Construct:
		fmt.Fprintf(w, "%sConstruct %s\n", pad, v.Name.Token.Value)
		for _, e := range v.Group.Elements {
			child(e)
		}
	case *kpolauth.GroupBounds:
		fmt.Fprintf(w, "%sGroupBounds Min=%s Max=%s effective=%s..%s\n", pad, bigText(v.MinRaw), bigText(v.MaxRaw), bigText(v.MinEffective), bigText(v.MaxEffective))
		child(v.Target)
		child(v.Group)
	case *kpolauth.DefLayout:
		bits := make([]string, len(v.Bits))
		for i, b := range v.Bits {
			bits[i] = bigText(b)
		}
		fmt.Fprintf(w, "%sDefLayout bits=[%s]\n", pad, strings.Join(bits, " "))
	case *kpolauth.SubscriptionSeq:
		fmt.Fprintf(w, "%sSubscriptionSeq •\n", pad)
		child(v.Left)
		child(v.Right)
	case *kpolauth.Assignment:
		fmt.Fprintf(w, "%sAssignment :=\n", pad)
		child(v.Target)
		child(v.Value)
	case *kpolauth.BinaryExpr:
		fmt.Fprintf(w, "%sBinaryExpr %s\n", pad, v.OpToken.Value)
		child(v.Left)
		child(v.Right)
	default:
		fmt.Fprintf(w, "%s%s\n", pad, n.CSTName())
	}
}

// cmdAuthRun lowers a KPOL-AUTH-L1 program and feeds external writes to the
// reference Do/Go machine.
func cmdAuthRun(args []string, stdout, stderr io.Writer) int {
	fs := newFlagSet("auth-run", stderr)
	var writes stringList
	fs.Var(&writes, "w", "external write Concept=value, e.g. -w Mark=4; repeatable")
	pos, err := parseFlags(fs, args)
	if err != nil {
		return exitRejected
	}
	if len(pos) != 1 {
		fmt.Fprintln(stderr, "usage: kpolc auth-run [-w Concept=value]... INPUT")
		return exitRejected
	}
	text, ok := readAuthSource(pos[0], stderr)
	if !ok {
		return exitRejected
	}
	art, err := kpolauth.LowerSource(text)
	if err != nil {
		fmt.Fprintf(stderr, "%v\n", err)
		return exitRejected
	}
	machine := kpolauth.NewMachine(art)
	state := func() string {
		vals := machine.Values()
		parts := make([]string, len(art.Concepts))
		for i, c := range art.Concepts {
			parts[i] = fmt.Sprintf("%s=%d", c.Name, vals[i])
		}
		return strings.Join(parts, " ")
	}
	fmt.Fprintf(stdout, "init          %s\n", state())
	for _, w := range writes {
		name, raw, found := strings.Cut(w, "=")
		name = strings.TrimSpace(name)
		value, convErr := strconv.ParseInt(strings.TrimSpace(raw), 10, 64)
		if !found || convErr != nil {
			fmt.Fprintf(stderr, "kpolc auth-run: invalid write %q (expected Concept=integer)\n", w)
			return exitRejected
		}
		cid := -1
		for _, c := range art.Concepts {
			if c.Name == name {
				cid = c.CID
			}
		}
		if cid < 0 {
			fmt.Fprintf(stderr, "kpolc auth-run: unknown concept %q\n", name)
			return exitRejected
		}
		if err := machine.TriggerExternal(cid, value); err != nil {
			fmt.Fprintf(stderr, "%v\n", err)
			return exitRejected
		}
		fmt.Fprintf(stdout, "write %-8s %s\n", fmt.Sprintf("%s=%d", name, value), state())
	}
	return exitOK
}
