package kpolauth

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// scratchDir returns a work directory below the package directory, removed after the test.
func scratchDir(t *testing.T) string {
	t.Helper()
	dir, err := os.MkdirTemp(".", "clitest-")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.RemoveAll(dir) })
	return dir
}

func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(content), 0o666); err != nil {
		t.Fatal(err)
	}
}

func runCLI(args ...string) (code int, stdout, stderr string) {
	var out, errb bytes.Buffer
	code = RunCLI(args, &out, &errb)
	return code, out.String(), errb.String()
}

func TestCLISuccessTexts(t *testing.T) {
	dir := scratchDir(t)
	pages := filepath.Join(dir, "pages.auth")
	writeFile(t, pages, guidePages)
	const ok = "OK: 2 concepts, 1 subscriptions, 5 Do/Go words, 1024 BRAM bytes\n"

	for _, args := range [][]string{
		{pages},
		{pages, "--check"},
		{"--check", pages},
		{pages, "--check", "--emit-bram", filepath.Join(dir, "a.bin")},
	} {
		code, out, errText := runCLI(args...)
		if code != 0 || out != ok || errText != "" {
			t.Errorf("%v: code %d out %q err %q", args, code, out, errText)
		}
	}
	// Emission flags without --check keep the output quiet.
	code, out, errText := runCLI(pages, "--emit-dogo", filepath.Join(dir, "q.json"))
	if code != 0 || out != "" || errText != "" {
		t.Errorf("quiet emit: %d %q %q", code, out, errText)
	}
	code, out, _ = runCLI(filepath.Join(dir, "none"), "--check")
	if code != 1 || out != "" {
		t.Errorf("missing input: %d %q", code, out)
	}
}

func TestCLIEmitsReferenceArtifacts(t *testing.T) {
	dir := scratchDir(t)
	src := filepath.Join(dir, "thermal.auth")
	writeFile(t, src, thermalGraph)
	art := mustLower(t, thermalGraph)

	bram := filepath.Join(dir, "sub", "dir", "thermal.bram.bin")
	jsonOut := filepath.Join(dir, "thermal.dogo.json")
	binOut := filepath.Join(dir, "thermal.dogo.BIN") // the suffix is matched case-insensitively
	plain := filepath.Join(dir, "thermal.dogo")      // anything but .bin is JSON
	if code, _, errText := runCLI(src, "--emit-bram", bram, "--emit-dogo", jsonOut); code != 0 {
		t.Fatalf("exit %d: %s", code, errText)
	}
	if code, _, errText := runCLI(src, "--emit-dogo", binOut); code != 0 {
		t.Fatalf("exit %d: %s", code, errText)
	}
	if code, _, errText := runCLI(src, "--emit-dogo="+plain); code != 0 {
		t.Fatalf("exit %d: %s", code, errText)
	}
	read := func(p string) []byte {
		b, err := os.ReadFile(p)
		if err != nil {
			t.Fatal(err)
		}
		return b
	}
	if !bytes.Equal(read(bram), art.BRAMImage()) {
		t.Error("BRAM image differs")
	}
	wantJSON, _ := art.DoGoJSON()
	if !bytes.Equal(read(jsonOut), wantJSON) || !bytes.Equal(read(plain), wantJSON) {
		t.Error("JSON differs")
	}
	if !bytes.Equal(read(binOut), art.DoGoBinary()) || len(read(binOut)) != 4*len(art.CodeO()) {
		t.Error("binary Do/Go differs")
	}
	if !bytes.HasSuffix(wantJSON, []byte("}\n")) || !bytes.HasPrefix(wantJSON, []byte("{\n  \"format\": \"kpol-auth-dogo-0.1.0\",\n  \"concepts\": [\n    {\n      \"cid\": 0,")) {
		t.Errorf("JSON shape %q", wantJSON[:60])
	}
}

// TestCLIDiagnosticsAndExitCodes: the failure formats of __main__.py, and no
// output file is created when parsing or lowering fails.
func TestCLIDiagnosticsAndExitCodes(t *testing.T) {
	dir := scratchDir(t)
	cases := []struct {
		name, src string
		code      int
		stderr    string
	}{
		{"u04", "Static(@runtime, OpenBracket, A, CloseBracket)\n", 2,
			"KPOL-AUTH-U04 [line 1, col 8, bytes 7..8]: Момент виконання OpenBracket/CloseBracket (рантайм vs транслятор) не визначено автором (RFC-015).\n"},
		{"u12", "Property(DefBit=1, Value=_)\n", 2,
			"KPOL-AUTH-U12 [line 1, col 9, bytes 8..27]: Розмежування Def[i]=0 та елемента зі станом '_' не визначено автором (RFC-018 / RFC-010 п. 3).\n"},
		{"lex", "Температура ¤ x\n", 2,
			"KPOL-AUTH-LEX-01 [line 1, col 13, bytes 23..25]: Несподіваний символ '¤' у потоці KPOL-AUTH.\n"},
		{"eof", "A •", 2, "KPOL-AUTH-SYNTAX-01: Несподіваний кінець файлу.\n"},
		{"crlf positions", "Concept(A, 0)\r\nConcept(B, 0)\r\n¤", 2,
			"KPOL-AUTH-LEX-01 [line 3, col 1, bytes 28..30]: Несподіваний символ '¤' у потоці KPOL-AUTH.\n"},
		{"cycle2", "Concept(A, 0)\nConcept(B, 0)\nA • Assign(B, A)\nB • Assign(A, B)\n", 3,
			"KPOL-LOWER-CYCLE: Цикл у графі каскадів BRAM через концепт C0 (C1 -> C0).\n"},
		{"cycle self", "Concept(C0, 1)\nC0 • Assign(C0, C0 + 1)\n", 3,
			"KPOL-LOWER-CYCLE: Самопетля каскаду BRAM не допускається: dst_cid (0) == src_cid (0).\n"},
		{"unsupported", "Def(1, 0, 1, 0, 0, 0, 0)", 3,
			"KPOL-LOWER-UNSUPPORTED-CST [line 1, col 1, bytes 0..24]: Конструкція 'DefLayoutCST' не підтримується в lowering.\n"},
		{"unsupported op", "Concept(A, 0) Concept(B, 0) A • Assign(B, A / 2)", 3,
			"KPOL-LOWER-UNSUPPORTED-OP [line 1, col 45, bytes 46..47]: Оператор '/' не підтримується в Do/Go lowering.\n"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			in := filepath.Join(dir, c.name+".kpol")
			writeFile(t, in, c.src)
			bram, dogo := filepath.Join(dir, c.name+".bram"), filepath.Join(dir, c.name+".json")
			code, out, errText := runCLI(in, "--check", "--emit-bram", bram, "--emit-dogo", dogo)
			if code != c.code || out != "" || errText != c.stderr {
				t.Errorf("code %d out %q\n got err %q\nwant err %q", code, out, errText, c.stderr)
			}
			for _, p := range []string{bram, dogo} {
				if _, err := os.Stat(p); err == nil {
					t.Errorf("%s must not be created on failure", p)
				}
			}
		})
	}

	bad := filepath.Join(dir, "bad.kpol")
	if err := os.WriteFile(bad, []byte("Concept(A, \xff)"), 0o666); err != nil {
		t.Fatal(err)
	}
	if code, _, errText := runCLI(bad); code != 1 || !strings.HasPrefix(errText, "KPOL-CLI-IO: 'utf-8' codec can't decode byte 0xff in position 11") {
		t.Errorf("invalid UTF-8: %d %q", code, errText)
	}
	code, _, errText := runCLI(filepath.Join(dir, "absent.kpol"))
	if code != 1 || errText != "KPOL-CLI-IO: [Errno 2] No such file or directory: '"+filepath.Join(dir, "absent.kpol")+"'\n" {
		t.Errorf("absent input: %d %q", code, errText)
	}
	if code, _, errText = runCLI(dir); code != 1 || !strings.Contains(errText, "[Errno 21] Is a directory") {
		t.Errorf("directory input: %d %q", code, errText)
	}
}

// TestCLIDoesNotOverwrite: existing output files are kept and nothing is written.
func TestCLIDoesNotOverwrite(t *testing.T) {
	dir := scratchDir(t)
	in := filepath.Join(dir, "in.kpol")
	writeFile(t, in, guidePages)
	bram, dogo := filepath.Join(dir, "o.bram"), filepath.Join(dir, "o.json")
	writeFile(t, dogo, "precious")

	code, _, errText := runCLI(in, "--emit-bram", bram, "--emit-dogo", dogo)
	if code != 1 || errText != "KPOL-CLI-IO: [Errno 17] File exists: '"+dogo+"'\n" {
		t.Errorf("code %d err %q", code, errText)
	}
	if b, _ := os.ReadFile(dogo); string(b) != "precious" {
		t.Errorf("existing file modified: %q", b)
	}
	if _, err := os.Stat(bram); err == nil {
		t.Error("no output may be written when another output exists")
	}
	// Both outputs exist: still refused, contents intact.
	writeFile(t, bram, "also precious")
	if code, _, _ = runCLI(in, "--emit-bram", bram); code != 1 {
		t.Errorf("code %d", code)
	}
	if b, _ := os.ReadFile(bram); string(b) != "also precious" {
		t.Error("existing BRAM file modified")
	}

	// RunCLIWithOptions{Overwrite} replaces them, like "python -m kpol_auth".
	var out, errb bytes.Buffer
	if code := RunCLIWithOptions([]string{in, "--emit-bram", bram, "--emit-dogo", dogo}, &out, &errb, CLIOptions{Overwrite: true}); code != 0 {
		t.Fatalf("overwrite: %d %s", code, errb.String())
	}
	if b, _ := os.ReadFile(bram); !bytes.Equal(b, mustLower(t, guidePages).BRAMImage()) {
		t.Error("BRAM image not replaced")
	}
	if b, _ := os.ReadFile(dogo); !strings.HasPrefix(string(b), "{\n") {
		t.Error("JSON not replaced")
	}

	// A parent that is a regular file is an I/O error.
	if code, _, errText := runCLI(in, "--emit-bram", filepath.Join(in, "x")); code != 1 || !strings.Contains(errText, "[Errno 17] File exists: '"+in+"'") {
		t.Errorf("parent is a file: %d %q", code, errText)
	}
}

func TestCLIUsage(t *testing.T) {
	const usage = "usage: kpol_auth [-h] [--check] [--emit-bram PATH] [--emit-dogo PATH] input\n"
	dir := scratchDir(t)
	in := filepath.Join(dir, "in.kpol")
	writeFile(t, in, guidePages)
	cases := []struct {
		args []string
		code int
		err  string
	}{
		{nil, 2, "the following arguments are required: input"},
		{[]string{"--bogus"}, 2, "the following arguments are required: input"},
		{[]string{in, "--bogus"}, 2, "unrecognized arguments: --bogus"},
		{[]string{in, "extra", "more"}, 2, "unrecognized arguments: extra more"},
		{[]string{in, "-c"}, 2, "unrecognized arguments: -c"},
		{[]string{in, "--emit-bram"}, 2, "argument --emit-bram: expected one argument"},
		{[]string{in, "--emit-dogo", "--check"}, 2, "argument --emit-dogo: expected one argument"},
		{[]string{in, "--em", "x"}, 2, "ambiguous option: --em could match --emit-bram, --emit-dogo"},
		{[]string{in, "--check=1"}, 2, "argument --check: ignored explicit argument '1'"},
		{[]string{in, "--help=1"}, 2, "argument -h/--help: ignored explicit argument '1'"},
	}
	for _, c := range cases {
		code, out, errText := runCLI(c.args...)
		if code != c.code || out != "" || errText != usage+"kpol_auth: error: "+c.err+"\n" {
			t.Errorf("%v: %d %q %q", c.args, code, out, errText)
		}
	}
	for _, args := range [][]string{{"-h"}, {"--help"}, {in, "--he"}, {in, "-hx"}} {
		code, out, errText := runCLI(args...)
		if code != 0 || errText != "" || !strings.HasPrefix(out, usage+"\nKPOL-AUTH native frontend") ||
			!strings.Contains(out, "  --emit-bram PATH  Write 1024-byte CME-RAW-1 BRAM routing image (.bin).\n") {
			t.Errorf("%v: help %d %q", args, code, out)
		}
	}
	// Abbreviations, "--" and negative-number-like words.
	for _, args := range [][]string{{"--ch", in}, {"--", in}, {in, "--emit-b=" + filepath.Join(dir, "x.bin")}} {
		if code, _, errText := runCLI(args...); code != 0 {
			t.Errorf("%v: %d %s", args, code, errText)
		}
	}
	if code, _, errText := runCLI("-5"); code != 1 || !strings.Contains(errText, "No such file or directory: '-5'") {
		t.Errorf("negative number is a positional: %d %q", code, errText)
	}
}
