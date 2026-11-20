package kpol

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"
	"strings"
	"testing"
)

// exampleKPOL returns the text of an example program: the repository file if
// it is reachable, otherwise the copy stored in the golden file. When both
// exist they must agree, so that a stale golden file is noticed.
func exampleKPOL(t *testing.T, name string) string {
	t.Helper()
	g := loadCMEGolden(t)
	var stored string
	for _, c := range g.Cases {
		if strings.HasPrefix(c.ID, "file:Engineering/sw/vmk-go/examples/"+name+".kpol@") {
			stored = g.Sources[c.Src]
			break
		}
	}
	data, err := os.ReadFile("../../vmk-go/examples/" + name + ".kpol")
	switch {
	case err == nil && stored != "" && string(data) != stored:
		t.Fatalf("%s.kpol differs from the copy in cme_golden.json; rerun testdata/gen_cme_golden.py", name)
	case err == nil:
		return string(data)
	case stored != "":
		return stored
	}
	t.Fatalf("example %s.kpol is not available", name)
	return ""
}

func mustParseUnchecked(t *testing.T, src string) *Module {
	t.Helper()
	m, err := ParseUnchecked(src)
	if err != nil {
		t.Fatalf("parse: %v", err)
	}
	return m
}

// TestCMEAnnexA checks the reference vectors of Appendix A of the
// specification: the SHA-256 of the 1024-byte image and the programmed slots.
func TestCMEAnnexA(t *testing.T) {
	vectors := []struct {
		file, profile, sha string
		slots              []string // hex of CID 0, 1, ... ; every other slot is zero
	}{
		{"increase", ProfileCME1, "4df05b189b9bf12052d98ab6084e0256454c60cae4afd4449469c060ba8dcc5d",
			[]string{"0a000000140000000403000100000000"}},
		{"decrease", ProfileCME1, "00ba66e57e21d14913c95d7d2fc8c45c3c450548510ca3155721d7eec67b78c3",
			[]string{"0a000000140000000403000200000000"}},
		{"cascade_4concept", ProfileCME2, "032c4705c91cea6ddddb7d449cd0dcbd6ba62359af1f9e7a846f33c341a7ef38",
			[]string{
				"0a000000320000000413000101000000",
				"000000000a0000000313000102000000",
				"0200000001000000041b000203000000",
				"0000000002000000010b000000000000",
			}},
		{"bms_safety_cascade", ProfileCME2, "de03442454424b5cf64478506f118c13f095ae24ba58db8894583c43567ea3ee",
			[]string{
				"00000000320088130513000101000000",
				"0000000001000000041b000102000000",
				"0200000001000000041b000203000000",
				"0a00000002000000010b000000000000",
			}},
	}
	for _, v := range vectors {
		t.Run(v.file+"/"+v.profile, func(t *testing.T) {
			m := mustParseUnchecked(t, exampleKPOL(t, v.file))
			img, err := CompileProfile(m, v.profile)
			if err != nil {
				t.Fatal(err)
			}
			if len(img) != 1024 {
				t.Fatalf("image has %d bytes", len(img))
			}
			if sum := sha256.Sum256(img); hex.EncodeToString(sum[:]) != v.sha {
				t.Errorf("sha256 = %x, want %s", sum, v.sha)
			}
			for cid := 0; cid < 64; cid++ {
				want := strings.Repeat("00", 16)
				if cid < len(v.slots) {
					want = v.slots[cid]
				}
				if got := hex.EncodeToString(img[cid*16 : cid*16+16]); got != want {
					t.Errorf("slot %d = %s, want %s", cid, got, want)
				}
			}
			// The parsed-and-checked module gives the same image.
			checked, err := Parse(exampleKPOL(t, v.file))
			if err != nil {
				t.Fatal(err)
			}
			if again, err := CompileProfile(checked, v.profile); err != nil || string(again) != string(img) {
				t.Errorf("Parse and ParseUnchecked modules give different images (%v)", err)
			}
		})
	}
}

// TestCMEAnnexANegative checks the negative vectors of Appendix A.
func TestCMEAnnexANegative(t *testing.T) {
	for _, v := range []struct{ file, profile, code, msg string }{
		{"bms_safety_cascade", ProfileCME1, "B3-SHAPE",
			"B3-SHAPE: module BmsSafetyCascade: expected exactly one state, event and rule"},
		{"increase", ProfileCME2, "CME2-PROOF",
			"CME2-PROOF: module Increase: KPOL-CME-2 requires a non-empty Proof block"},
	} {
		m := mustParseUnchecked(t, exampleKPOL(t, v.file))
		img, err := CompileProfile(m, v.profile)
		var e *Error
		if img != nil || err == nil {
			t.Fatalf("%s under %s was accepted", v.file, v.profile)
		}
		if ok := errors.As(err, &e); !ok || e.Code != v.code || err.Error() != v.msg {
			t.Errorf("%s under %s: %q, want %q", v.file, v.profile, err, v.msg)
		}
	}
}
