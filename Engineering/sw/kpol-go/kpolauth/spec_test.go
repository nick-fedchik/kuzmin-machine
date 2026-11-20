package kpolauth

import (
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"testing"
)

// firstCode returns the diagnostic code of err ("" if nil).
func firstCode(err error) string {
	var e *Error
	if errors.As(err, &e) {
		return e.Code
	}
	if err != nil {
		return "non-kpolauth:" + err.Error()
	}
	return ""
}

func mustParse(t *testing.T, src string) *Program {
	t.Helper()
	p, err := Parse(src, DefaultConfig())
	if err != nil {
		t.Fatalf("Parse(%q): %v", src, err)
	}
	return p
}

func mustLower(t *testing.T, src string) *Artifact {
	t.Helper()
	a, err := LowerSource(src)
	if err != nil {
		t.Fatalf("LowerSource(%q): %v", src, err)
	}
	return a
}

func wordsHex(words []uint32) string {
	parts := make([]string, len(words))
	for i, w := range words {
		parts[i] = fmt.Sprintf("%08x", w)
	}
	return strings.Join(parts, " ")
}

// TestAnnexA1 checks the frontend vectors EX-01..EX-18 of Annex A.1:
// verdict, first diagnostic code and CST root.
func TestAnnexA1(t *testing.T) {
	cases := []struct {
		id, src, code, root string
	}{
		{"EX-01", `Collection(Letter)[Min=1, Max=15]`, "", "GroupBounds"},
		{"EX-02", `{ Item }[Min=1, Max=0]`, "", "GroupBounds"},
		{"EX-03", `Def(1, 0, 1, 0, 0, 0, 0)`, "", "DefLayout"},
		{"EX-04", `Static(OpenBracket, ItemA, CloseBracket)`, "", "Construct"},
		{"EX-05", `(A, B) • Do(A, B)`, "", "SubscriptionSeq"},
		{"EX-06", `• Flag`, "KPOL-AUTH-SYNTAX-03", ""},
		{"EX-07", `Collection(A, B, C)[Min=1, Max=2, Logic=AND]`, "KPOL-AUTH-U01", ""},
		{"EX-08", `Array(A, B)[Min=Byte(1), Max=2]`, "KPOL-AUTH-U02", ""},
		{"EX-09", `Static(OpenBracket, A, CloseBracked)`, "KPOL-AUTH-U03", ""},
		{"EX-10", `Static(@runtime, OpenBracket, A, CloseBracket)`, "KPOL-AUTH-U04", ""},
		{"EX-11", `#legacy_comment`, "KPOL-AUTH-U05", ""},
		{"EX-12", `"text \" quote"`, "KPOL-AUTH-U06", ""},
		{"EX-13", `Name("ПривітСвітДовгеІм")`, "KPOL-AUTH-U07", ""},
		{"EX-14", `Flag := (A • B)`, "KPOL-AUTH-U08", ""},
		{"EX-15", `A • busy(A)`, "KPOL-AUTH-U09", ""},
		{"EX-16", `C := _ + B`, "KPOL-AUTH-U10", ""},
		{"EX-17", `Def(1, 0, 0, 0, 0, 0, 0, 1)`, "KPOL-AUTH-U11", ""},
		{"EX-18", `Property(DefBit=1, Value=_)`, "KPOL-AUTH-U12", ""},
	}
	for _, c := range cases {
		t.Run(c.id, func(t *testing.T) {
			prog, err := Parse(c.src, DefaultConfig())
			if got := firstCode(err); got != c.code {
				t.Fatalf("code %q, want %q (err %v)", got, c.code, err)
			}
			if c.code != "" {
				return
			}
			if len(prog.Items) != 1 || len(prog.Diagnostics) != 0 {
				t.Fatalf("items %d, diagnostics %d", len(prog.Items), len(prog.Diagnostics))
			}
			var root string
			switch n := prog.Items[0].(type) {
			case *GroupBounds:
				root = "GroupBounds"
				if c.id == "EX-01" && (n.MinEffective.Int64() != 1 || n.MaxEffective.Int64() != 16) {
					t.Errorf("EX-01 bounds %s..%s, want 1..16", n.MinEffective, n.MaxEffective)
				}
				if c.id == "EX-02" && (n.MinEffective.Int64() != 1 || n.MaxEffective.Int64() != 1) {
					t.Errorf("EX-02 bounds %s..%s, want 1..1", n.MinEffective, n.MaxEffective)
				}
			case *DefLayout:
				root = "DefLayout"
			case *Construct:
				root = "Construct"
				if !n.Group.HasStubBrackets {
					t.Error("EX-04: hasStubBrackets must be true")
				}
			case *SubscriptionSeq:
				root = "SubscriptionSeq"
			}
			if root != c.root {
				t.Errorf("root %q, want %q", root, c.root)
			}
		})
	}
}

// TestAuthorCorpusMatchesReference runs the AUTHOR_CORPUS data of corpus.py the
// way the Python frontend tests do.
func TestAuthorCorpusMatchesReference(t *testing.T) {
	corpus := AuthorCorpus()
	if len(corpus) != 18 {
		t.Fatalf("%d examples, want 18", len(corpus))
	}
	inScope := map[string]bool{"EX-01": true, "EX-02": true, "EX-03": true, "EX-04": true, "EX-05": true, "EX-06": true}
	for i, ex := range corpus {
		if want := fmt.Sprintf("EX-%02d", i+1); ex.ID != want {
			t.Fatalf("example %d has id %s, want %s", i, ex.ID, want)
		}
		if ex.InSourceScope != inScope[ex.ID] {
			t.Errorf("%s: in_source_scope %v", ex.ID, ex.InSourceScope)
		}
		if len(ex.SourceRefs) == 0 || strings.TrimSpace(ex.SourceBoundaryNote) == "" {
			t.Errorf("%s: missing source attribution", ex.ID)
		}
		prog, err := Parse(ex.SourceText, DefaultConfig())
		switch ex.ExpectedStatus {
		case "ok":
			if err != nil || len(prog.Diagnostics) != 0 || len(prog.Items) != 1 || prog.Items[0].CSTName() != ex.ExpectedCSTKind {
				t.Errorf("%s: err=%v items=%v, want root %s", ex.ID, err, prog, ex.ExpectedCSTKind)
			}
		case "fail-closed":
			var found bool
			for _, code := range ex.ExpectedDiagnostics {
				found = found || firstCode(err) == code
			}
			if !found {
				t.Errorf("%s: code %q not in %v", ex.ID, firstCode(err), ex.ExpectedDiagnostics)
			}
		default:
			t.Errorf("%s: unexpected status %q", ex.ID, ex.ExpectedStatus)
		}
	}
}

// TestAnnexA2 checks the lowering vectors of Annex A.2: code_o, the SHA-256 of
// the image and the CID 0/1 slots of the third vector.
func TestAnnexA2(t *testing.T) {
	cases := []struct {
		src, codeO, sha string
	}{
		{
			"Concept(A, 0) Concept(B, 0) A • Assign(B, A + 1)",
			"12000000 30000001 20000000 11000001 50000000",
			"5c75d766ae52b14df31920670333ac174bbc29c993bcee7b89e6d1fa7e4c0f02",
		},
		{
			"Concept(A, 0) Concept(B, 0) Concept(C, 0) A • Assign(B, 1) B • Assign(C, 1)",
			"30000001 11000001 50000000 30000001 11000002 50000000",
			"58f63cc7c8b7eaccc2aed943c2aee16fddd0a457cd6cc3931884cd914f3c2e19",
		},
		{
			"Concept(T, 20) Concept(H, 10, Lower=10, Upper=80) Concept(F, 0) Concept(Al, 0) " +
				"T • Assign(H, 25 + ((T - 20) * 5)) OnPositive(H) • Assign(F, H) " +
				"OnAbort(H) • Assign(Al, 1) OnAbort(H) • Assign(F, 100)",
			"30000019 12000000 30000014 21000000 30000005 22000000 20000000 11000001 50000000 " +
				"12000001 11000002 50000000 30000001 11000003 50000000 30000064 11000002 50000000",
			"6ef255e19b367c8540e4bd8f785b8c5127bfc12208b147406a5e76fb90d39543",
		},
	}
	for i, c := range cases {
		art := mustLower(t, c.src)
		if got := wordsHex(art.CodeO()); got != c.codeO {
			t.Errorf("vector %d: code_o\n got %s\nwant %s", i+1, got, c.codeO)
		}
		img := art.BRAMImage()
		if len(img) != 1024 {
			t.Fatalf("vector %d: image has %d bytes", i+1, len(img))
		}
		if got := shaHex(img); got != c.sha {
			t.Errorf("vector %d: image sha %s, want %s", i+1, got, c.sha)
		}
		if i == 2 {
			if got := hex.EncodeToString(img[0:16]); got != "14000000000000000010000001000000" {
				t.Errorf("CID 0 slot %s", got)
			}
			if got := hex.EncodeToString(img[16:32]); got != "0a000000000000000012000002000000" {
				t.Errorf("CID 1 slot %s", got)
			}
		}
	}
}

// TestAnnexA2NegativeVectors checks the negative vectors of Annex A.2.
func TestAnnexA2NegativeVectors(t *testing.T) {
	cases := []struct{ src, code string }{
		{"Concept(A, 0) A • Assign(A, 1)", "KPOL-LOWER-CYCLE"},
		{"Concept(A, 0) Concept(B, 0) Concept(C, 0) A • {Assign(B, 1), Assign(C, 2)}", "KPOL-LOWER-FANOUT"},
		{"Concept(A, 0) Concept(B, 0) A • Assign(B, A / 2)", "KPOL-LOWER-UNSUPPORTED-OP"},
		{"Concept(A, 0, Lower=-1)", "KPOL-AUTH-SYNTAX-01"},
	}
	for _, c := range cases {
		if _, err := LowerSource(c.src); firstCode(err) != c.code {
			t.Errorf("%q: code %q, want %q (%v)", c.src, firstCode(err), c.code, err)
		}
	}
}

// TestErrorBridgesToKpolError checks errors.As for both *Error and *kpol.Error.
func TestErrorBridgesToKpolError(t *testing.T) {
	_, err := Parse("#x", DefaultConfig())
	var e *Error
	if !errors.As(err, &e) || e.Code != "KPOL-AUTH-U05" || e.Span == nil || e.Diagnostic == nil {
		t.Fatalf("errors.As(*Error) failed: %v", err)
	}
	if !strings.HasPrefix(err.Error(), "KPOL-AUTH-U05: ") {
		t.Errorf("Error() = %q", err.Error())
	}
	var ke interface{ Error() string }
	if !errors.As(err, &ke) {
		t.Fatal("errors.As(error) failed")
	}
	if got := asKpolCode(err); got != "KPOL-AUTH-U05" {
		t.Errorf("kpol.Error bridge: code %q", got)
	}
}
