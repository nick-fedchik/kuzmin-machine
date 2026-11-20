package main

import (
	"fmt"
	"io"
	"os"
	"strings"
	"unicode/utf8"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/c99"
	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/ekpol"
	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

type outputFile struct {
	path string
	data []byte
}

func readSource(path, prefix string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("%s-IO: %s: %v", prefix, path, err)
	}
	if !utf8.Valid(data) {
		return "", fmt.Errorf("%s-IO: %s: invalid UTF-8", prefix, path)
	}
	return string(data), nil
}

// writeExclusive creates every file without overwriting, removing the
// already created ones if a later write fails.
func writeExclusive(files []outputFile) error {
	var created []string
	for _, f := range files {
		out, err := os.OpenFile(f.path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o644)
		if err == nil {
			_, err = out.Write(f.data)
			if cerr := out.Close(); err == nil {
				err = cerr
			}
			created = append(created, f.path)
		}
		if err != nil {
			for _, p := range created {
				_ = os.Remove(p)
			}
			return err
		}
	}
	return nil
}

func cmdBuild(args []string, stdout, stderr io.Writer) int {
	fs := newFlagSet("build", stderr)
	profile := fs.String("profile", "", "target profile: KPOL-CME-1, KPOL-CME-2 or EKPOL (default: EKPOL for .ekpol, else KPOL-CME-1)")
	emitKPOL := fs.String("emit-kpol", "", "translate the .ekpol input to classic KPOL at this new path")
	emitEKPOL := fs.String("emit-ekpol", "", "translate the .kpol input to EKPOL at this new path")
	style := fs.String("ekpol-style", "symbolic", "EKPOL formatting style: symbolic or keyword")
	emitC99 := fs.String("emit-c99", "", "new C99 safety module path")
	emitZ3 := fs.String("emit-z3-cert", "", "new Z3 safety certificate JSON path")
	dump := fs.Bool("dump-concepts", false, "print the compiled descriptor table")
	trace := fs.String("trace-events", "", "not provided: trace an image with the VMK debugger")
	pos, err := parseFlags(fs, args)
	if err != nil {
		return exitRejected
	}
	if *trace != "" {
		return fail(stderr, exitRejected, "kpolc build: --trace-events is provided by VMK: build the image, then run\n  vmk --program IMAGE --trace-events %q", *trace)
	}
	if len(pos) < 1 || len(pos) > 2 {
		return fail(stderr, exitRejected, "usage: kpolc build [options] SOURCE [IMAGE]")
	}
	switch *profile {
	case "", kpol.ProfileCME1, kpol.ProfileCME2, "EKPOL":
	default:
		return fail(stderr, exitRejected, "kpolc build: invalid --profile %q (choose KPOL-CME-1, KPOL-CME-2 or EKPOL)", *profile)
	}
	if *style != "symbolic" && *style != "keyword" {
		return fail(stderr, exitRejected, "kpolc build: invalid --ekpol-style %q (choose symbolic or keyword)", *style)
	}
	source, imagePath := pos[0], ""
	if len(pos) == 2 {
		imagePath = pos[1]
	}
	ekInput := *profile == "EKPOL" || (*profile == "" && isEKPOL(source))
	effective, prefix := *profile, "B3"
	switch {
	case ekInput:
		effective, prefix = "EKPOL", "EKPOL"
	case effective == "":
		effective = kpol.ProfileCME1
	case effective == kpol.ProfileCME2:
		prefix = "CME2"
	}
	if imagePath == "" && *emitKPOL == "" && *emitEKPOL == "" {
		return fail(stderr, exitRejected, "kpolc build: the IMAGE argument is required")
	}
	text, err := readSource(source, prefix)
	if err != nil {
		return fail(stderr, exitRejected, "%v", err)
	}

	var (
		image       []byte
		kpolText    string
		ekpolText   string
		moduleName  = stem(source)
		conceptName []string
	)
	if ekInput {
		prog, err := ekpol.Parse(text, stem(source))
		if err != nil {
			return fail(stderr, exitRejected, "%v", err)
		}
		moduleName, conceptName = prog.ModuleName, prog.ConceptNames()
		if image, err = ekpol.CompileProgram(prog); err != nil {
			return fail(stderr, exitRejected, "%v", err)
		}
		if *emitKPOL != "" || *emitEKPOL != "" {
			if kpolText, err = ekpol.ProgramToKPOL(prog, false); err != nil {
				return fail(stderr, exitRejected, "%v", err)
			}
		}
		if *emitEKPOL != "" {
			if ekpolText, err = ekpol.ToEKPOL(kpolText, *style); err != nil {
				return fail(stderr, exitRejected, "%v", err)
			}
		}
	} else {
		mod, err := kpol.ParseSyntax(text)
		if err != nil {
			return fail(stderr, exitRejected, "%s-SYNTAX: %s: %v", prefix, source, err)
		}
		moduleName = mod.Name
		for _, st := range mod.States {
			conceptName = append(conceptName, st.Name)
		}
		if imagePath != "" || *emitC99 != "" || *emitZ3 != "" || *dump {
			if image, err = kpol.CompileProfile(mod, effective); err != nil {
				return fail(stderr, exitRejected, "%v", err)
			}
		}
		if *emitEKPOL != "" {
			if ekpolText, err = ekpol.ToEKPOL(text, *style); err != nil {
				return fail(stderr, exitRejected, "%v", err)
			}
		}
		if *emitKPOL != "" {
			kpolText = text
		}
	}

	var c99Text string
	var cert *c99.Certificate
	if *emitC99 != "" || *emitZ3 != "" {
		c99Text, cert, err = c99.EmitC99FromImageWithCertificate(image, c99.Options{ModuleName: moduleName, ConceptNames: conceptName})
		if err != nil {
			return fail(stderr, exitRejected, "%s-C99: %v", prefix, err)
		}
		if !cert.Passed {
			reasons := strings.Join(cert.Failures, "; ")
			if reasons == "" {
				reasons = "Z3 verification failed"
			}
			return fail(stderr, exitRejected, "%s-Z3: %s", prefix, reasons)
		}
	}

	var outputs []outputFile
	add := func(path string, data []byte) {
		if path != "" {
			outputs = append(outputs, outputFile{path, data})
		}
	}
	for _, p := range []string{imagePath, *emitKPOL, *emitEKPOL, *emitC99, *emitZ3} {
		if p == "" {
			continue
		}
		if _, err := os.Lstat(p); err == nil {
			return fail(stderr, exitRejected, "%s-IO: %s: File exists", prefix, p)
		}
	}
	add(imagePath, image)
	add(*emitKPOL, []byte(kpolText))
	add(*emitEKPOL, []byte(ekpolText))
	add(*emitC99, []byte(c99Text))
	if *emitZ3 != "" {
		js, err := cert.JSON()
		if err != nil {
			return fail(stderr, exitRejected, "%s-C99: %v", prefix, err)
		}
		add(*emitZ3, js)
	}
	if err := writeExclusive(outputs); err != nil {
		return fail(stderr, exitRejected, "%s-IO: %v", prefix, err)
	}
	if *dump {
		printDescriptors(stdout, image, conceptName)
	}
	return exitOK
}

var predNames = map[uint8]string{
	kpol.PredNOP: "NOP", kpol.PredEQ: "EQ", kpol.PredNEQ: "NEQ", kpol.PredGT: "GT",
	kpol.PredLT: "LT", kpol.PredRANGE: "RANGE", kpol.PredBITMASK: "BITMASK",
}

var actNames = map[uint8]string{
	kpol.ActAssign: "ASSIGN", kpol.ActInc: "INC", kpol.ActDec: "DEC", kpol.ActAdd: "ADD", kpol.ActSub: "SUB",
}

func opName(names map[uint8]string, v uint8) string {
	if n, ok := names[v]; ok {
		return n
	}
	return fmt.Sprintf("0x%02X", v)
}

func printDescriptors(w io.Writer, image []byte, names []string) {
	descs, err := kpol.Disassemble(image)
	if err != nil {
		fmt.Fprintf(w, "%v\n", err)
		return
	}
	nameWidth := len("Name")
	display := func(d kpol.Descriptor) string {
		if d.CID < len(names) {
			return names[d.CID]
		}
		return d.Name
	}
	for _, d := range descs {
		if c99.IsDescriptorConfigured(d) && len(display(d)) > nameWidth {
			nameWidth = len(display(d))
		}
	}
	fmt.Fprintf(w, "%-4s %-*s %-12s %-12s %-8s %-6s %-6s %-7s %s\n", "CID", nameWidth, "Name", "W0", "W1", "Pred", "Guard", "Haz", "Action", "Subscriber")
	for _, d := range descs {
		if !c99.IsDescriptorConfigured(d) {
			continue
		}
		fmt.Fprintf(w, "%-4d %-*s %-12d %-12d %-8s 0x%02X   %-6d %-7s %d\n", d.CID, nameWidth, display(d), int32(d.CurrentState), int32(d.OperandVal),
			opName(predNames, d.PredOpcode), d.GuardFlags, d.HazardLimit, opName(actNames, d.ActionOpcode), d.SubscriberCID)
	}
}
