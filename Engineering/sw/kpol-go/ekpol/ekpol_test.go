package ekpol

import (
	"bytes"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

const (
	examplesDir = "../../vmk-go/examples"
	guidesDir   = "../../../guides"
)

func readFile(t testing.TB, path string) string {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Skipf("repository file unavailable: %v", err)
	}
	return string(b)
}

// Annex A of the EKPOL specification (profile B64).
var annexA = []struct {
	name    string
	kpol    string
	profile string
	sha     string
}{
	{"increase", "increase", "KPOL-CME-1", "4df05b189b9bf12052d98ab6084e0256454c60cae4afd4449469c060ba8dcc5d"},
	{"decrease", "decrease", "KPOL-CME-1", "00ba66e57e21d14913c95d7d2fc8c45c3c450548510ca3155721d7eec67b78c3"},
	{"cascade_4concept", "cascade_4concept", "KPOL-CME-2", "032c4705c91cea6ddddb7d449cd0dcbd6ba62359af1f9e7a846f33c341a7ef38"},
	{"bms_safety_cascade", "bms_safety_cascade", "KPOL-CME-2", "de03442454424b5cf64478506f118c13f095ae24ba58db8894583c43567ea3ee"},
}

func compileKPOLProfile(t *testing.T, text, profile string) []byte {
	t.Helper()
	mod, err := kpol.ParseSyntax(text)
	if err != nil {
		t.Fatalf("parse generated KPOL: %v\n%s", err, text)
	}
	var img []byte
	if profile == "KPOL-CME-1" {
		img, err = compileCME1(mod)
	} else {
		img, err = compileCME2(mod)
	}
	if err != nil {
		t.Fatalf("%s compile: %v\n%s", profile, err, text)
	}
	return img
}

func TestAnnexAVectors(t *testing.T) {
	for _, v := range annexA {
		t.Run(v.name, func(t *testing.T) {
			src := readFile(t, filepath.Join(examplesDir, v.name+".ekpol"))
			if !isASCII(src) {
				t.Error("example must be pure ASCII")
			}
			img, err := CompileImage(src)
			if err != nil {
				t.Fatal(err)
			}
			if len(img) != kpol.ImageSize || sha(img) != v.sha {
				t.Fatalf("sha256 = %s, want %s", sha(img), v.sha)
			}

			// EKPOL -> KPOL -> profile image
			k1, err := ToKPOL(src, "EkpolModule")
			if err != nil {
				t.Fatal(err)
			}
			if got := sha(compileKPOLProfile(t, k1, v.profile)); got != v.sha {
				t.Errorf("KPOL profile image sha256 = %s, want %s", got, v.sha)
			}

			// KPOL -> EKPOL (both styles) -> image, ASCII only, and back to KPOL
			orig := readFile(t, filepath.Join(examplesDir, v.kpol+".kpol"))
			for _, style := range []string{"symbolic", "keyword"} {
				e, err := ToEKPOL(orig, style)
				if err != nil {
					t.Fatalf("%s: %v", style, err)
				}
				if !isASCII(e) {
					t.Errorf("%s output is not ASCII", style)
				}
				if style == "symbolic" && !(strings.Contains(e, "<-") && strings.Contains(e, "=>") && strings.Contains(e, " .")) {
					t.Errorf("symbolic notation expected:\n%s", e)
				}
				if style == "keyword" && !(strings.Contains(e, "on ") && strings.Contains(e, "when ") && strings.Contains(e, "commit;")) {
					t.Errorf("keyword notation expected:\n%s", e)
				}
				img, err := CompileImage(e)
				if err != nil || sha(img) != v.sha {
					t.Fatalf("%s: image %v err %v, want %s", style, sha(img), err, v.sha)
				}
				k2, err := ToKPOL(e, "EkpolModule")
				if err != nil {
					t.Fatal(err)
				}
				if got := sha(compileKPOLProfile(t, k2, v.profile)); got != v.sha {
					t.Errorf("%s: second KPOL image sha256 = %s", style, got)
				}
			}
		})
	}
}

func TestExampleClassification(t *testing.T) {
	b64 := map[string]bool{"increase": true, "decrease": true, "cascade_4concept": true, "bms_safety_cascade": true}
	conceptual := []string{"factorial", "if_toggle", "nod_euclid", "sum_autoreset", "tachometer"}
	for name := range b64 {
		p, err := Parse(readFile(t, filepath.Join(examplesDir, name+".ekpol")), "EkpolModule")
		if err != nil {
			t.Fatal(err)
		}
		if p.IsConceptualOnly() {
			t.Errorf("%s must not be conceptual-only", name)
		}
	}
	for _, name := range conceptual {
		src := readFile(t, filepath.Join(examplesDir, name+".ekpol"))
		p, err := Parse(src, "EkpolModule")
		if err != nil {
			t.Fatalf("%s: %v", name, err)
		}
		if !p.IsConceptualOnly() {
			t.Errorf("%s must be conceptual-only", name)
		}
		if _, err := ValidateB64(p); err == nil || !strings.HasPrefix(err.Error(), "EKPOL-TYPE-ERR") {
			t.Errorf("%s: B64 validation = %v, want EKPOL-TYPE-ERR", name, err)
		}
	}
}

func wantErr(t *testing.T, name string, err error, want string) {
	t.Helper()
	if err == nil {
		t.Errorf("%s: accepted, want %s", name, want)
		return
	}
	if err.Error() != want {
		t.Errorf("%s:\n got  %s\n want %s", name, err, want)
	}
}

// Negative controls: one or more cases for every diagnostic class of section 12.
// The texts are those of the reference implementation.
func TestDiagnostics(t *testing.T) {
	const a = "concept A: i32 = 0 [>= 0] { "
	cases := []struct{ name, src, want string }{
		{"empty source", "  // c\n", "EKPOL-SYNTAX-ERR: empty EKPOL source"},
		{"missing arrow", a + "<- E(p) A += 1 . }", "EKPOL-SYNTAX-ERR: concept 'A': rule '<- E(p) A += 1 .' is missing '=>' action arrow"},
		{"missing terminator", a + "<- E(p) => A += 1 }", "EKPOL-SYNTAX-ERR: concept 'A': rule '<- E(p) => A += 1' is missing Big Dot terminator ('.', 'commit', or ';')"},
		{"stray text", a + "<- E(p) => A += 1 . }\nfoo", "EKPOL-SYNTAX-ERR: unexpected token near 'foo'"},
		{"duplicate concept", a + "<- E(p) => A += 1 . }\n" + a + "<- F(p) => A += 1 . }", "EKPOL-SYNTAX-ERR: duplicate concept declaration 'A'"},
		{"unclosed brace", a + "<- E(p) => A += 1 .", "EKPOL-SYNTAX-ERR: concept 'A': unclosed '{' in concept body"},
		{"unterminated comment", "/* open", "EKPOL-SYNTAX-ERR: unterminated /* ... */ block comment"},
		{"unknown type", "concept A: i64 = 0 [>= 0] { <- E(p) => A += 1 . }", "EKPOL-TYPE-ERR: concept 'A': unsupported type 'i64' (expected i32/int32/Int32, u64/uint64/U64, f64/float64/Float, or bool/Bool/?)"},
		{"init out of range", "concept A: i32 = 2147483648 [>= 0] { <- E(p) => A += 1 . }", "EKPOL-TYPE-ERR: concept 'A': Int32 initial value 2147483648 out of range"},
		{"conceptual type in B64", "concept A: u64 = 0 [>= 0] { <- E(p) => A += 1 . }", "EKPOL-TYPE-ERR: concept 'A' has type U64, but CME-RAW-1 bram64 requires Int32 (i32/int32/Int32)"},
		{"undef init in B64", "concept A: i32 = _ [>= 0] { <- E(p) => A += 1 . }", "EKPOL-TYPE-ERR: concept 'A': initial state '_' / undef requires --mode conceptual (CME-RAW-1 W0 stores signed Int32)"},
		{"empty invariant", "concept A: i32 = 0 [] { <- E(p) => A += 1 . }", "EKPOL-INVARIANT-ERR: concept 'A': empty invariant brackets '[]'"},
		{"inverted invariant", "concept A: i32 = 0 [5..1] { <- E(p) => A += 1 . }", "EKPOL-INVARIANT-ERR: concept 'A': inverted invariant range [5..1]"},
		{"foreign invariant", "concept A: i32 = 0 [B >= 0] { <- E(p) => A += 1 . }", "EKPOL-INVARIANT-ERR: concept 'A': invariant references foreign concept 'B'"},
		{"missing invariant", "concept A: i32 = 0 { <- E(p) => A += 1 . }", "EKPOL-INVARIANT-ERR: concept 'A': missing safety invariant '[>= 0]' in concept header or body"},
		{"negative initial", "concept A: i32 = -1 [>= 0] { <- E(p) => A += 1 . }", "EKPOL-INVARIANT-ERR: concept 'A': initial value -1 violates safety invariant A >= 0"},
		{"range beyond int16", a + "<- E(p) :: p in 0..70000 => A += 1 . }", "EKPOL-RANGE-ERR: concept 'A': invalid range 0..70000 (must satisfy -32768 <= lo <= hi <= 32767)"},
		{"swapped range bounds", a + "<- E(p) :: p in 9..1 => A += 1 . }", "EKPOL-RANGE-ERR: concept 'A': invalid range 9..1 (must satisfy -32768 <= lo <= hi <= 32767)"},
		{"incomplete range pair", a + "<- E(p) :: p >= 1 && p >= 5 => A += 1 . }", "EKPOL-RANGE-ERR: concept 'A': invalid two-sided range [5, None]"},
		{"operand collision", a + "<- E(p) :: p in 0..9 => A += 5 . }", "EKPOL-COLLISION-ERR: concept 'A': CME-RAW-1 shares one 32-bit W1 operand_val between guard literal and ADD/SUB step != 1"},
		{"self subscription", a + "~ A :: A >= 1 => A += 1 . }", "EKPOL-CYCLE-ERR: concept 'A': self-subscription (A -> A) is forbidden in bram64"},
		{"fan-out", a + "<- E(p) => A += 1 . }\nconcept B: i32 = 0 [>= 0] { ~ A :: A >= 1 => B += 1 . }\nconcept C: i32 = 0 [>= 0] { ~ A :: A >= 1 => C += 1 . }", "EKPOL-CYCLE-ERR: concept 'A': cascade fan-out > 1 (B, C) exceeds single-slot subscriber_cid"},
		{"undeclared source", a + "~ Z :: Z >= 1 => A += 1 . }", "EKPOL-CYCLE-ERR: concept 'A': subscribes to undeclared concept 'Z'"},
		{"guard active at start", "concept A: i32 = 3 [>= 0] { <- E(p) => A += 1 . }\nconcept B: i32 = 0 [>= 0] { ~ A :: A >= 1 => B += 1 . }", "EKPOL-CYCLE-ERR: concept 'B': on change(A) guard is active on initial state (3)"},
		{"publisher without step", a + "<- E(p) => A = p . }\nconcept B: i32 = 0 [>= 0] { ~ A :: A >= 1 => B += 1 . }", "EKPOL-CYCLE-ERR: concept 'A': cascade publisher must use a non-zero step action (+/- K)"},
		{"empty test", a + "<- E(p) => A += 1 . }\ntest T { }", "EKPOL-PROOF-ERR: test 'T': test block cannot be empty"},
		{"unknown send target", a + "<- E(p) => A += 1 . }\ntest T { send Z(1); expect A == 1; }", "EKPOL-PROOF-ERR: test 'T': unknown target concept or event 'Z'"},
		{"failing expectation", a + "<- E(p) :: p < 50 => A += 1 . }\nconcept B: i32 = 0 [>= 0] { ~ A :: A >= 2 => B += 1 . }\ntest T { send A(1); expect A == 1; expect B == 1; }", "EKPOL-PROOF-ERR: embedded test verification failed: T: Expectation failed at step 3: state={'A': 1, 'B': 0}"},
		{"CME-2 needs a proof", a + "<- E(p) => A = p . }", "EKPOL-PROOF-ERR: CME2-PROOF: module A: KPOL-CME-2 requires a non-empty Proof block"},
		{"CME-1 guard shape", a + "<- E(p) :: p >= 3 => A += 1 . }", "EKPOL-PROOF-ERR: B3-GUARD: module A: rule R_A: expected true or p compared with an Int32 literal"},
		{"CME-1 range guard", a + "<- E(p) :: p in 1..9 => A += 1 . }", "EKPOL-PROOF-ERR: B3-GUARD: module A: rule R_A: expected true or p compared with an Int32 literal"},
		{"step outside CME-2", a + "<- E(p) => A += 4294967297 . }\ntest T { send A(1); expect A == 1; }", "EKPOL-PROOF-ERR: + has an invalid integer literal"},
		{"reserved KPOL word", "concept state: i32 = 0 [>= 0] { <- E(p) => state += 1 . }\ntest T { send state(1); expect state == 1; }", "EKPOL-PROOF-ERR: 3:9: reserved keyword 'state' cannot be an identifier"},
		{"clashing derived events", "concept A_B: i32 = 0 [>= 0] { <- (p) => A_B += 1 . }\nconcept AB: i32 = 0 [>= 0] { <- (p) => AB += 1 . }\ntest T { send AB(1); expect AB == 1; }", "EKPOL-PROOF-ERR: duplicate event declaration"},
	}
	for _, c := range cases {
		_, err := CompileImage(c.src)
		wantErr(t, c.name, err, c.want)
		var ke *kpol.Error
		if err != nil {
			ke, _ = err.(*kpol.Error)
			if ke == nil || !strings.HasPrefix(c.want, ke.Code+": ") {
				t.Errorf("%s: error %T %v is not a *kpol.Error with the leading code", c.name, err, err)
			}
		}
	}
}

func TestGuideAntiPatterns(t *testing.T) {
	guide := readFile(t, filepath.Join(guidesDir, "kpol-ekpol-language-guide.md"))
	blocks := regexp.MustCompile("(?s)```ekpol\n(.*?)```").FindAllStringSubmatch(guide, -1)
	wantCycle := "EKPOL-CYCLE-ERR: cyclic cascade subscription detected involving concept 'Thermal_Stage_A' (Thermal_Stage_A -> Thermal_Stage_B -> Thermal_Stage_A)"
	wantCollision := "EKPOL-COLLISION-ERR: concept 'God_BMS_Controller': CME-RAW-1 shares one 32-bit W1 operand_val between guard literal and ADD/SUB step != 1"
	var cycles, collisions, valid int
	for _, m := range blocks {
		block := m[1]
		switch {
		case strings.Contains(block, "ANTI-PATTERN: EKPOL-CYCLE-ERR"):
			cycles++
			_, err := CompileImage(block)
			wantErr(t, "cycle anti-pattern", err, wantCycle)
		case strings.Contains(block, "ANTI-PATTERN: EKPOL-COLLISION-ERR"):
			collisions++
			_, err := CompileImage(block)
			wantErr(t, "collision anti-pattern", err, wantCollision)
		default:
			valid++
			p, err := Parse(block, "EkpolModule")
			if err != nil {
				t.Errorf("guide block %d: %v", valid, err)
				continue
			}
			if !p.IsConceptualOnly() {
				if img, err := CompileImage(block); err != nil || len(img) != kpol.ImageSize {
					t.Errorf("guide block %d (%s): image %d bytes, err %v", valid, p.ModuleName, len(img), err)
				}
			}
		}
	}
	if cycles != 1 || collisions != 1 || valid < 14 {
		t.Errorf("guide corpus: %d cycle, %d collision, %d valid blocks", cycles, collisions, valid)
	}
}

// Negative controls M1..M5 of test_ekpol_278.py, expressed against the Go implementation.
func TestMutantControls(t *testing.T) {
	bms := readFile(t, filepath.Join(examplesDir, "bms_safety_cascade.ekpol"))

	t.Run("M1 cycle detection", func(t *testing.T) {
		cyclic := "concept C0: i32 = 0 [>= 0] { ~ C1 :: C1 >= 1 => C0 += 1 . }\nconcept C1: i32 = 0 [>= 0] { ~ C0 :: C0 >= 1 => C1 += 1 . }\n"
		_, err := CompileImage(cyclic)
		wantErr(t, "cycle", err, "EKPOL-CYCLE-ERR: cyclic cascade subscription detected involving concept 'C0' (C0 -> C1 -> C0)")
		chain := "concept C0: i32 = 0 [>= 0] { <- E(p) => C0 += 1 . }\nconcept C1: i32 = 0 [>= 0] { ~ C0 :: C0 >= 1 => C1 += 1 . }\n"
		if _, err := CompileImage(chain); err != nil {
			t.Errorf("acyclic chain rejected: %v", err)
		}
	})

	t.Run("M2 range bounds packing", func(t *testing.T) {
		p, err := Parse(bms, "EkpolModule")
		if err != nil {
			t.Fatal(err)
		}
		ds, err := ValidateB64(p)
		if err != nil {
			t.Fatal(err)
		}
		if got, want := ds[0].OperandVal, uint32(5000)<<16|50; got != want || ds[0].PredOpcode != kpol.PredRANGE {
			t.Errorf("W1 = %#x opcode %d, want %#x (hi<<16|lo) RANGE", got, ds[0].PredOpcode, want)
		}
		swapped := strings.Replace(bms, "delta_mv in 50..5000", "delta_mv in 5000..50", 1)
		if _, err := CompileImage(swapped); err == nil || !strings.HasPrefix(err.Error(), "EKPOL-RANGE-ERR") {
			t.Errorf("swapped bounds: %v", err)
		}
	})

	t.Run("M3 keyword vs symbolic", func(t *testing.T) {
		kpolText := readFile(t, filepath.Join(examplesDir, "bms_safety_cascade.kpol"))
		sym, err := ToEKPOL(kpolText, "symbolic")
		if err != nil {
			t.Fatal(err)
		}
		kw, err := ToEKPOL(kpolText, "keyword")
		if err != nil {
			t.Fatal(err)
		}
		symImg, err1 := CompileImage(sym)
		kwImg, err2 := CompileImage(kw)
		if err1 != nil || err2 != nil || !bytes.Equal(symImg, kwImg) {
			t.Fatalf("styles diverge: %v %v", err1, err2)
		}
		broken := strings.ReplaceAll(kw, "on change(Cell_Delta_mV)", "on write(Cell_Delta_mV)")
		if img, err := CompileImage(broken); err == nil && bytes.Equal(img, kwImg) {
			t.Error("replacing on change by on write went undetected")
		}
	})

	t.Run("M4 post-read dot order", func(t *testing.T) {
		for _, tc := range []struct {
			rule    string
			barrier bool
			action  string
		}{
			{"-> => . Sum = 0", true, "Sum = 0"},
			{"-> => Sum = 0", false, "Sum = 0"},
			{"on read => after Sum = 0;", true, "Sum = 0"},
			{"on read => Sum = 0;", false, "Sum = 0"},
			{"-> => • Sum = 0", true, "Sum = 0"},
		} {
			p, err := Parse("concept Sum: f64 = 0 [>= 0] {\n"+tc.rule+"\n}", "M")
			if err != nil {
				t.Fatalf("%s: %v", tc.rule, err)
			}
			r := p.Concepts[0].Rules[0]
			if r.TriggerKind != TriggerRead || r.PostReadBarrier != tc.barrier || r.Actions[0].RawText != tc.action {
				t.Errorf("%s: kind %s barrier %v action %q", tc.rule, r.TriggerKind, r.PostReadBarrier, r.Actions[0].RawText)
			}
		}
	})

	t.Run("M5 invariant bracket drop", func(t *testing.T) {
		p, err := Parse(bms, "EkpolModule")
		if err != nil {
			t.Fatal(err)
		}
		ds, err := ValidateB64(p)
		if err != nil {
			t.Fatal(err)
		}
		for _, d := range ds[:4] {
			if d.GuardFlags&kpol.GuardInvariantEn == 0 || d.GuardFlags&kpol.GuardAssumptionEn == 0 {
				t.Errorf("%s: guard flags %#x lack the invariant/assumption enables", d.Name, d.GuardFlags)
			}
		}
		dropped := strings.Replace(bms, "Cell_Delta_mV: i32 = 0 [>= 0]", "Cell_Delta_mV: i32 = 0", 1)
		_, err = CompileImage(dropped)
		wantErr(t, "dropped invariant", err, "EKPOL-INVARIANT-ERR: concept 'Cell_Delta_mV': missing safety invariant '[>= 0]' in concept header or body")
	})
}

func TestNotationEquivalence(t *testing.T) {
	pairs := [][2]string{
		{"<- Pulse(param) :: param < 20 => Counter += 1 .", "on Pulse(param) when param < 20 => Counter += 1 commit;"},
		{"<- (param) :: param in 3..9 => Counter = param .", "on write(param) when param in 3..9 => Counter := param commit;"},
		{"<- Pulse(param) :: !(param == 2) => Counter -= 1 .", "on Pulse(param) when not (param == 2) => Counter -= 1 commit;"},
		{"<- Pulse(param) :: param >= 1 && param <= 5 => Counter += 1 .", "on Pulse(param) when param in 1..5 => Counter += 1 commit;"},
		{"<- Pulse(param) => Counter -= 3 .", "on Pulse(param) => Counter = Counter - 3 commit;"},
	}
	for _, pair := range pairs {
		var imgs [][]byte
		var progs []*Program
		for _, rule := range pair {
			src := "module N;\nconcept Counter: i32 = 10 [>= 0] {\n    " + rule + "\n}\ntest T { send Counter(5); expect Counter >= 0; }\n"
			p, err := Parse(src, "EkpolModule")
			if err != nil {
				t.Fatalf("%s: %v", rule, err)
			}
			img, err := CompileProgram(p)
			if err != nil {
				t.Fatalf("%s: %v", rule, err)
			}
			imgs = append(imgs, img)
			progs = append(progs, p)
		}
		if !bytes.Equal(imgs[0], imgs[1]) {
			t.Errorf("%q and %q lower differently", pair[0], pair[1])
		}
		a, b := progs[0].Concepts[0].Rules[0], progs[1].Concepts[0].Rules[0]
		if a.Predicate.Kind != b.Predicate.Kind || a.Predicate.Op != b.Predicate.Op || a.Predicate.Inverted != b.Predicate.Inverted ||
			a.Actions[0].Kind != b.Actions[0].Kind || a.TriggerKind != b.TriggerKind {
			t.Errorf("%q and %q parse differently: %+v / %+v", pair[0], pair[1], a, b)
		}
	}
}

func TestProgramModel(t *testing.T) {
	src := "// @stdin A, B\n# @stdout A\n# @stderr B, C\n/* @stdin Z */\n@stdout\nconcept A: i32 = 0 [>= 0] {\n    @stderr;\n    <- E(p) => A += 1 .\n}\nconcept B: i32 = 2 [>= 0, <= 9] {\n    invariant B: 1..8;\n    ~ A :: A >= 1 => B -= 1 .\n}\ntest T { send A(1); expect B == 1; }\n"
	p, err := Parse(src, "Fallback")
	if err != nil {
		t.Fatal(err)
	}
	if p.ModuleName != "Fallback" || strings.Join(p.ConceptNames(), ",") != "A,B" {
		t.Errorf("module %q concepts %v", p.ModuleName, p.ConceptNames())
	}
	if got := strings.Join(p.StdinConcepts, ","); got != "A,B" {
		t.Errorf("stdin = %s", got)
	}
	if got := strings.Join(p.StdoutConcepts, ","); got != "A" {
		t.Errorf("stdout = %s", got)
	}
	if got := strings.Join(p.StderrConcepts, ","); got != "B,C,A" {
		t.Errorf("stderr = %s", got)
	}
	if len(p.Concepts[1].Invariants) != 3 || p.Concepts[1].Invariants[2].Kind != "range" || p.Concepts[1].Invariants[2].Hi.Int64() != 8 {
		t.Errorf("invariants = %+v", p.Concepts[1].Invariants)
	}
	if len(p.Tests) != 1 || p.Tests[0].Steps[0].Kind != StepSend || p.Tests[0].Steps[1].Value.Int.Int64() != 1 {
		t.Errorf("tests = %+v", p.Tests)
	}
	if p.IsConceptualOnly() {
		t.Error("Int32 write/change program is not conceptual-only")
	}

	names := map[string]string{
		"concept Counter: i32 = 10 [>= 0] { <- (p) => Counter += 1 . }":                      "Increase",
		"concept Counter: i32 = 10 [>= 0] { <- (p) => Counter -= 1 . }":                      "Decrease",
		"concept Counter: i32 = 1 [>= 0] { <- (p) => Counter -= 1 . }":                       "DecreaseFromOne",
		"concept Counter: i32 = 1 [>= 0] { <- (p) => Counter += 2 . }":                       "Counter",
		"concept X: i32 = 1 [>= 0] { <- (p) => X += 1 . }":                                   "X",
		"module EkpolModule;\nconcept Counter: i32 = 10 [>= 0] { <- (p) => Counter += 1 . }": "Increase",
		"module Own;\nconcept Counter: i32 = 10 [>= 0] { <- (p) => Counter += 1 . }":         "Own",
	}
	for src, want := range names {
		p, err := Parse(src, "EkpolModule")
		if err != nil || p.ModuleName != want {
			t.Errorf("%q: module %v, %v; want %s", src, p, err, want)
		}
	}
	for _, kind := range []string{"u64", "f64", "bool", "?"} {
		p, err := Parse("concept X: "+kind+" = 0 { when X == X => X = 1 . }", "M")
		if kind == "bool" || kind == "?" {
			p, err = Parse("concept X: "+kind+" = true { when X == true => X = false . }", "M")
		}
		if err != nil || !p.IsConceptualOnly() {
			t.Errorf("%s: conceptual-only = %v, %v", kind, p != nil && p.IsConceptualOnly(), err)
		}
	}
}

func TestDescriptorLayout(t *testing.T) {
	src := "module L;\nconcept A: i32 = 7 [>= 0] { <- E(p) :: p > 3 => A += 1 . }\nconcept B: i32 = 0 [>= 0] { ~ A :: A >= 9 => B -= 1 . }\nconcept C: i32 = 4 [>= 0] { <- F(q) :: !(q <= 6) => C = q . }\n"
	p, err := Parse(src, "M")
	if err != nil {
		t.Fatal(err)
	}
	ds, err := ValidateB64(p)
	if err != nil {
		t.Fatal(err)
	}
	if len(ds) != 64 || ds[3].Name != "Concept_3" || ds[63].CID != 63 {
		t.Fatalf("padding: %d descriptors, slot 3 %q", len(ds), ds[3].Name)
	}
	a, b, c := ds[0], ds[1], ds[2]
	if a.PredOpcode != kpol.PredGT || a.OperandVal != 3 || a.ActionOpcode != kpol.ActInc || a.SubscriberCID != 1 ||
		a.GuardFlags != kpol.GuardAssumptionEn|kpol.GuardInvariantEn|kpol.GuardSubscriberEn || a.CurrentState != 7 {
		t.Errorf("A = %+v", a)
	}
	// ">= 9" lowers to LT 9 with the invert flag
	if b.PredOpcode != kpol.PredLT || b.OperandVal != 9 || b.GuardFlags != kpol.GuardAssumptionEn|kpol.GuardInvariantEn|kpol.GuardInvertAssumption || b.ActionOpcode != kpol.ActDec {
		t.Errorf("B = %+v", b)
	}
	// "!(q <= 6)": GT 6 inverted twice
	if c.PredOpcode != kpol.PredGT || c.OperandVal != 6 || c.GuardFlags != kpol.GuardAssumptionEn|kpol.GuardInvariantEn || c.ActionOpcode != kpol.ActAssign {
		t.Errorf("C = %+v", c)
	}
	if img := kpol.PackImage(ds); len(img) != kpol.ImageSize {
		t.Errorf("image length %d", len(img))
	}
}

func TestToEKPODStyle(t *testing.T) {
	src := readFile(t, filepath.Join(examplesDir, "increase.kpol"))
	_, err := ToEKPOL(src, "bogus")
	wantErr(t, "style", err, "EKPOL-SYNTAX-ERR: unsupported EKPOL formatting style 'bogus' (expected 'symbolic' or 'keyword')")
	_, err = ToEKPOL("Problem", "symbolic")
	if err == nil || !strings.HasPrefix(err.Error(), "EKPOL-SYNTAX-ERR: failed to parse input KPOL: ") {
		t.Errorf("bad KPOL: %v", err)
	}
	out, err := ToEKPOL(src, "symbolic")
	if err != nil || !strings.HasPrefix(out, "module Increase;\n\n@stdin\n@stdout\nconcept Counter: i32 = 10 [>= 0] {\n    <- Pulse(param) :: param < 20 => Counter += 1 .\n}\n") {
		t.Errorf("symbolic:\n%s\n%v", out, err)
	}
}

func FuzzParse(f *testing.F) {
	entries, _ := filepath.Glob(filepath.Join(examplesDir, "*.ekpol"))
	for _, e := range entries {
		if b, err := os.ReadFile(e); err == nil {
			f.Add(string(b))
		}
	}
	f.Add("concept A: i32 = 0 [>= 0] { <- E(p) :: p in 1..5 => A += 1 . }\ntest T { send A(1); expect A == 1; }")
	f.Fuzz(func(t *testing.T, src string) {
		p, err := Parse(src, "EkpolModule")
		if err != nil {
			return
		}
		_ = p.IsConceptualOnly()
		if _, err := CompileImage(src); err == nil {
			if k, err := ToKPOL(src, "EkpolModule"); err == nil {
				if e, err := ToEKPOL(k, "keyword"); err == nil && !isASCII(e) {
					t.Fatalf("non-ASCII EKPOL from %q", src)
				}
			}
		}
	})
}

func FuzzToEKPOL(f *testing.F) {
	entries, _ := filepath.Glob(filepath.Join(examplesDir, "*.kpol"))
	for _, e := range entries {
		if b, err := os.ReadFile(e); err == nil {
			f.Add(string(b))
		}
	}
	f.Fuzz(func(t *testing.T, src string) {
		for _, style := range []string{"symbolic", "keyword"} {
			_, _ = ToEKPOL(src, style)
		}
	})
}
