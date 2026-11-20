package kpolauth

import (
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"unicode"
	"unicode/utf8"
)

// CLI exit codes (specification §8.6).
const (
	ExitOK    = 0
	ExitIO    = 1 // KPOL-CLI-IO
	ExitAuth  = 2 // KPOL-AUTH-* (also command-line usage errors, as in argparse)
	ExitLower = 3 // KPOL-LOWER-*
)

const cliProg = "kpol_auth"

const cliUsage = "usage: kpol_auth [-h] [--check] [--emit-bram PATH] [--emit-dogo PATH] input\n"

const cliHelp = cliUsage + `
KPOL-AUTH native frontend & derived Do/Go + CME-RAW-1 lowering CLI (fail-
closed on KPOL-AUTH-* and KPOL-LOWER-*).

positional arguments:
  input             Path to input KPOL-AUTH source file (UTF-8).

options:
  -h, --help        show this help message and exit
  --check           Validate KPOL-AUTH syntax, uncertainty gates, and lowering
                    invariants.
  --emit-bram PATH  Write 1024-byte CME-RAW-1 BRAM routing image (.bin).
  --emit-dogo PATH  Write lowered Do/Go artifact (.json metadata+bytecode or
                    packed 32-bit .bin).
`

// CLIOptions tunes RunCLIWithOptions.
type CLIOptions struct {
	// Overwrite allows --emit-bram and --emit-dogo to replace existing files
	// (what "python -m kpol_auth" does). By default an existing output file is
	// an error (KPOL-CLI-IO) and no output is written.
	Overwrite bool
}

// RunCLI runs "kpol_auth INPUT [--check] [--emit-bram OUT.bin]
// [--emit-dogo OUT.json|OUT.bin]" and returns the exit code: 0 success, 1
// KPOL-CLI-IO, 2 KPOL-AUTH-* (and usage errors), 3 KPOL-LOWER-*. Flags, texts
// and artifact bytes are those of "python -m kpol_auth"; unlike it, RunCLI
// never overwrites an existing output file.
func RunCLI(args []string, stdout, stderr io.Writer) int {
	return RunCLIWithOptions(args, stdout, stderr, CLIOptions{})
}

// RunCLIWithOptions is RunCLI with explicit options.
func RunCLIWithOptions(args []string, stdout, stderr io.Writer, opts CLIOptions) int {
	a, code, done := parseCLIArgs(args, stdout, stderr)
	if done {
		return code
	}

	source, err := readSource(a.input)
	if err != nil {
		fmt.Fprintf(stderr, "KPOL-CLI-IO: %s\n", err)
		return ExitIO
	}

	artifact, err := LowerSource(source)
	if err != nil {
		var e *Error
		if !errors.As(err, &e) {
			e = &Error{Code: "KPOL-AUTH-INTERNAL", Msg: err.Error()}
		}
		fmt.Fprintf(stderr, "%s%s: %s\n", e.Code, formatSpan(e.Span), e.Msg)
		if strings.HasPrefix(e.Code, "KPOL-LOWER-") {
			return ExitLower
		}
		return ExitAuth
	}

	if err := emitOutputs(a, artifact, opts); err != nil {
		fmt.Fprintf(stderr, "KPOL-CLI-IO: %s\n", err)
		return ExitIO
	}

	if a.check || (a.emitBram == nil && a.emitDogo == nil) {
		fmt.Fprintf(stdout, "OK: %d concepts, %d subscriptions, %d Do/Go words, %d BRAM bytes\n",
			len(artifact.Concepts), len(artifact.Subscriptions), len(artifact.codeO), len(artifact.bram))
	}
	return ExitOK
}

func formatSpan(s *Span) string {
	if s == nil {
		return ""
	}
	return fmt.Sprintf(" [line %d, col %d, bytes %d..%d]", s.Line, s.Column, s.ByteOffset, s.ByteEnd)
}

// readSource reads the file as UTF-8 text with universal newlines
// (Path.read_text(encoding="utf-8")).
func readSource(path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", errors.New(osErrorText(err, path))
	}
	if !utf8.Valid(data) {
		pos := 0
		for pos < len(data) {
			r, size := utf8.DecodeRune(data[pos:])
			if r == utf8.RuneError && size == 1 {
				break
			}
			pos += size
		}
		return "", fmt.Errorf("'utf-8' codec can't decode byte 0x%02x in position %d: %s",
			data[pos], pos, utf8Failure(data[pos:]))
	}
	text := strings.ReplaceAll(string(data), "\r\n", "\n")
	return strings.ReplaceAll(text, "\r", "\n"), nil
}

// utf8Failure names the reason the UTF-8 decoder of Python gives for the
// invalid sequence at the start of b.
func utf8Failure(b []byte) string {
	lead := b[0]
	need := 0
	switch {
	case lead >= 0xC2 && lead <= 0xDF:
		need = 2
	case lead >= 0xE0 && lead <= 0xEF:
		need = 3
	case lead >= 0xF0 && lead <= 0xF4:
		need = 4
	default:
		return "invalid start byte"
	}
	for i := 1; i < need; i++ {
		if i >= len(b) {
			return "unexpected end of data"
		}
		if b[i]&0xC0 != 0x80 {
			return "invalid continuation byte"
		}
	}
	return "invalid continuation byte"
}

func emitOutputs(a cliArgs, art *Artifact, opts CLIOptions) error {
	type output struct {
		path string
		data []byte
	}
	var outs []output
	if a.emitBram != nil {
		outs = append(outs, output{*a.emitBram, art.BRAMImage()})
	}
	if a.emitDogo != nil {
		data := art.DoGoBinary()
		if strings.ToLower(pathSuffix(*a.emitDogo)) != ".bin" {
			var err error
			if data, err = art.DoGoJSON(); err != nil {
				return err
			}
		}
		outs = append(outs, output{*a.emitDogo, data})
	}
	if !opts.Overwrite {
		for _, o := range outs {
			if _, err := os.Lstat(o.path); err == nil {
				return errors.New(osErrorText(&fs.PathError{Op: "open", Path: o.path, Err: syscall.EEXIST}, o.path))
			}
		}
	}
	for _, o := range outs {
		if err := mkdirParents(filepath.Dir(o.path)); err != nil {
			return errors.New(osErrorText(err, filepath.Dir(o.path)))
		}
		flags := os.O_WRONLY | os.O_CREATE | os.O_EXCL
		if opts.Overwrite {
			flags = os.O_WRONLY | os.O_CREATE | os.O_TRUNC
		}
		f, err := os.OpenFile(o.path, flags, 0o666)
		if err != nil {
			return errors.New(osErrorText(err, o.path))
		}
		_, werr := f.Write(o.data)
		if cerr := f.Close(); werr == nil {
			werr = cerr
		}
		if werr != nil {
			return errors.New(osErrorText(werr, o.path))
		}
	}
	return nil
}

// mkdirParents is Path.mkdir(parents=True, exist_ok=True): an existing
// non-directory is reported as EEXIST.
func mkdirParents(dir string) error {
	err := os.MkdirAll(dir, 0o777)
	if err != nil {
		if st, serr := os.Stat(dir); serr == nil && !st.IsDir() {
			return &fs.PathError{Op: "mkdir", Path: dir, Err: syscall.EEXIST}
		}
	}
	return err
}

// pathSuffix is pathlib.PurePath.suffix.
func pathSuffix(p string) string {
	name := filepath.Base(p)
	if i := strings.LastIndexByte(name, '.'); i > 0 && i < len(name)-1 {
		return name[i:]
	}
	return ""
}

// osErrorText formats an I/O error like str(OSError) in Python:
// "[Errno 2] No such file or directory: 'path'".
func osErrorText(err error, path string) string {
	var errno syscall.Errno
	if !errors.As(err, &errno) {
		return err.Error()
	}
	var pe *fs.PathError
	if errors.As(err, &pe) && pe.Path != "" {
		path = pe.Path
	}
	msg := errno.Error()
	if msg != "" {
		msg = strings.ToUpper(msg[:1]) + msg[1:]
	}
	return fmt.Sprintf("[Errno %d] %s: %s", int(errno), msg, pyRepr(path))
}

// pyRepr is repr(str) for the characters that occur in paths.
func pyRepr(s string) string {
	quote := byte('\'')
	if strings.Contains(s, "'") && !strings.Contains(s, `"`) {
		quote = '"'
	}
	var b strings.Builder
	b.WriteByte(quote)
	for _, r := range s {
		switch {
		case r == rune(quote) || r == '\\':
			b.WriteByte('\\')
			b.WriteRune(r)
		case r == '\n':
			b.WriteString(`\n`)
		case r == '\r':
			b.WriteString(`\r`)
		case r == '\t':
			b.WriteString(`\t`)
		case r < 0x20 || r == 0x7f:
			fmt.Fprintf(&b, `\x%02x`, r)
		case unicode.IsPrint(r):
			b.WriteRune(r)
		case r < 0x100:
			fmt.Fprintf(&b, `\x%02x`, r)
		case r < 0x10000:
			fmt.Fprintf(&b, `\u%04x`, r)
		default:
			fmt.Fprintf(&b, `\U%08x`, r)
		}
	}
	b.WriteByte(quote)
	return b.String()
}
