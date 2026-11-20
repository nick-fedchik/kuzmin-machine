package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

const examples = "../../../vmk-go/examples"

func runCLI(t *testing.T, args ...string) (int, string, string) {
	t.Helper()
	var out, errb bytes.Buffer
	code := run(args, strings.NewReader(""), &out, &errb)
	return code, out.String(), errb.String()
}

func write(t *testing.T, dir, name, text string) string {
	t.Helper()
	p := filepath.Join(dir, name)
	if err := os.WriteFile(p, []byte(text), 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

// The Annex A vectors of both formal specifications must be reproduced by
// "kpolc build" (the images, not only the library).
func TestBuildReproducesSpecificationVectors(t *testing.T) {
	row := regexp.MustCompile("\\| \\[`([a-z0-9_]+\\.e?kpol)`\\]\\([^)]*\\) \\| `?([A-Z0-9-]+)`? \\| `([0-9a-f]{64})`")
	for _, spec := range []string{"kpol-formal-specification.md", "ekpol-formal-specification.md"} {
		text, err := os.ReadFile(filepath.Join("../../../../specifications/kpol", spec))
		if err != nil {
			t.Fatal(err)
		}
		rows := row.FindAllStringSubmatch(string(text), -1)
		if len(rows) != 4 {
			t.Fatalf("%s: found %d vectors, want 4", spec, len(rows))
		}
		for _, m := range rows {
			args := []string{"build"}
			if strings.HasPrefix(spec, "kpol-") {
				args = append(args, "--profile", m[2])
			}
			img := filepath.Join(t.TempDir(), "image.bin")
			code, _, errs := runCLI(t, append(args, filepath.Join(examples, m[1]), img)...)
			if code != 0 {
				t.Fatalf("%s %s: exit %d: %s", m[1], m[2], code, errs)
			}
			data, _ := os.ReadFile(img)
			sum := sha256.Sum256(data)
			if hex.EncodeToString(sum[:]) != m[3] {
				t.Errorf("%s %s: sha256 %x, want %s", m[1], m[2], sum, m[3])
			}
		}
	}
}

func TestBuildNeverOverwritesAndDiagnosesProfile(t *testing.T) {
	dir := t.TempDir()
	img := filepath.Join(dir, "a.bin")
	src := filepath.Join(examples, "increase.kpol")
	if code, _, errs := runCLI(t, "build", "--profile", "KPOL-CME-1", src, img); code != 0 {
		t.Fatalf("first build failed: %s", errs)
	}
	if code, _, errs := runCLI(t, "build", "--profile", "KPOL-CME-1", src, img); code != 2 || !strings.Contains(errs, "File exists") {
		t.Errorf("second build: exit %d, stderr %q", code, errs)
	}
	if code, _, errs := runCLI(t, "build", "--profile", "KPOL-CME-1", filepath.Join(examples, "bms_safety_cascade.kpol"), filepath.Join(dir, "b.bin")); code != 2 || !strings.HasPrefix(errs, "B3-SHAPE") {
		t.Errorf("bms in CME-1: exit %d, stderr %q", code, errs)
	}
	if _, err := os.Stat(filepath.Join(dir, "b.bin")); err == nil {
		t.Error("a rejected build must not leave an image behind")
	}
}

const cashDesk = `Problem Cash { Invariants { Stock: Left >= 0; } }
Solution Cash {
    state Left: Int32 = 1;
    event Buy(count: Int32);
    rule Sell on Buy when count == 1 { set Left := Left - 1; }
}
Proof Cash {
    scenario One { step Buy(count = 1); expect Left == 0; }
}
`

func TestVerifyCheckAndRun(t *testing.T) {
	dir := t.TempDir()
	good := write(t, dir, "cash.kpol", cashDesk)
	if code, out, _ := runCLI(t, "verify", good); code != 0 || !strings.Contains(out, "Cash: 1/1 checks passed") {
		t.Errorf("verify: exit %d, out %q", code, out)
	}
	bad := write(t, dir, "bad.kpol", strings.Replace(cashDesk, "Left == 0", "Left == 1", 1))
	if code, out, _ := runCLI(t, "verify", bad); code != 1 || !strings.Contains(out, "FAIL One") {
		t.Errorf("failing proof: exit %d, out %q", code, out)
	}
	broken := write(t, dir, "broken.kpol", strings.Replace(cashDesk, "set Left := Left - 1;", "set Left := Missing;", 1))
	if code, _, errs := runCLI(t, "check", broken); code != 2 || !strings.Contains(errs, "Missing") {
		t.Errorf("check: exit %d, stderr %q", code, errs)
	}
	code, out, _ := runCLI(t, "run", "-e", "Buy(count=1)", "-e", "Buy(count=1)", good)
	if code != 0 || !strings.Contains(out, "state:       Left=0") || !strings.Contains(out, "InvariantViolation:Stock") {
		t.Errorf("run: exit %d, out %q", code, out)
	}
	if code, _, errs := runCLI(t, "run", "-e", "Buy(count=x)", good); code != 2 || !strings.Contains(errs, "invalid value") {
		t.Errorf("bad event value: exit %d, stderr %q", code, errs)
	}
}

func TestTranslateRoundTrip(t *testing.T) {
	code, out, errs := runCLI(t, "to-kpol", filepath.Join(examples, "increase.ekpol"))
	if code != 0 || !strings.Contains(out, "Problem") {
		t.Fatalf("to-kpol: exit %d, stderr %q", code, errs)
	}
	back := write(t, t.TempDir(), "increase.kpol", out)
	code, out2, errs := runCLI(t, "to-ekpol", "--ekpol-style", "keyword", back)
	if code != 0 || !strings.Contains(out2, "on ") {
		t.Fatalf("to-ekpol: exit %d, stderr %q, out %q", code, errs, out2)
	}
}

func TestAuthCommands(t *testing.T) {
	dir := t.TempDir()
	prog := write(t, dir, "pages.auth", "Concept(Page, 0)\nConcept(Next, 0)\nPage • Assign(Next, Page + 1)\n")
	if code, out, _ := runCLI(t, "auth", prog, "--check"); code != 0 || !strings.HasPrefix(out, "OK: 2 concepts, 1 subscriptions, 5 Do/Go words") {
		t.Errorf("auth --check: exit %d, out %q", code, out)
	}
	if code, out, _ := runCLI(t, "auth-run", "-w", "Page=4", prog); code != 0 || !strings.Contains(out, "Page=4 Next=5") {
		t.Errorf("auth-run: exit %d, out %q", code, out)
	}
	group := write(t, dir, "group.auth", "Collection(Letter)[Min=1, Max=15]")
	if code, out, _ := runCLI(t, "auth-cst", group); code != 0 || !strings.Contains(out, "effective=1..16") {
		t.Errorf("auth-cst: exit %d, out %q", code, out)
	}
	if code, _, errs := runCLI(t, "auth", group, "--check"); code != 3 || !strings.HasPrefix(errs, "KPOL-LOWER-UNSUPPORTED-CST") {
		t.Errorf("group is not an L1 program: exit %d, stderr %q", code, errs)
	}
}

func TestUsageErrors(t *testing.T) {
	if code, _, _ := runCLI(t); code != 2 {
		t.Errorf("no command: exit %d", code)
	}
	if code, _, errs := runCLI(t, "nope"); code != 2 || !strings.Contains(errs, "unknown command") {
		t.Errorf("unknown command: exit %d, stderr %q", code, errs)
	}
	if code, _, errs := runCLI(t, "build", "--trace-events", "0:1", "x.kpol", "y.bin"); code != 2 || !strings.Contains(errs, "vmk") {
		t.Errorf("trace redirect: exit %d, stderr %q", code, errs)
	}
}
