package ekpol

import (
	"math"
	"testing"
)

// Expected values come from CPython 3.14 (repr, int(s, 0), float(s)).

func TestPyRepr(t *testing.T) {
	cases := map[string]string{
		"a'b":          `"a'b"`,
		"a\"b'c":       `'a"b\'c'`,
		"\n":           `'\n'`,
		"é":            `'é'`,
		"\u00a0":       `'\xa0'`,
		"\u200b":       `'\u200b'`,
		"\x7f":         `'\x7f'`,
		"\\":           `'\\'`,
		"\U0001F600":   "'😀'",
		"\x00":         `'\x00'`,
		"\u0085":       `'\x85'`,
		"\ufeff":       `'\ufeff'`,
		"\U000e0001":   `'\U000e0001'`,
		"plain_ident1": `'plain_ident1'`,
	}
	for in, want := range cases {
		if got := pyRepr(in); got != want {
			t.Errorf("pyRepr(%q) = %s, want %s", in, got, want)
		}
	}
	if got := pyReprList([]string{"@stdin", "@stdout"}); got != "['@stdin', '@stdout']" {
		t.Errorf("pyReprList = %s", got)
	}
}

func TestPyInt0(t *testing.T) {
	valid := map[string]int64{
		"0x1F": 31, "-0b11": -3, "0o17": 15, "1_000": 1000, "00": 0, "0_0": 0, " 5 ": 5, "+5": 5,
		"٣": 3, "0x_1f": 31, "0X1f": 31, "-0": 0, "0x1_f": 31, "\u3000 7": 7,
	}
	for in, want := range valid {
		got, ok := pyInt0(in)
		if !ok || got.Int64() != want {
			t.Errorf("pyInt0(%q) = %v, %v; want %d", in, got, ok, want)
		}
	}
	for _, in := range []string{"010", "0_1", "1__0", "_1", "1_", "0x", "", "- 5", "0b102", "1e3", "5 5", "0xg"} {
		if v, ok := pyInt0(in); ok {
			t.Errorf("pyInt0(%q) = %v, want failure", in, v)
		}
	}
}

func TestPyFloat(t *testing.T) {
	valid := map[string]float64{
		"1.5": 1.5, "1e3": 1000, "1_0.5": 10.5, ".5": 0.5, "5.": 5, " 2.5 ": 2.5, "+.5e-3": 0.0005,
		"1e1_0": 1e10, "+inf": math.Inf(1), "-Infinity": math.Inf(-1), "1e400": math.Inf(1),
	}
	for in, want := range valid {
		got, ok := pyFloat(in)
		if !ok || got != want {
			t.Errorf("pyFloat(%q) = %v, %v; want %v", in, got, ok, want)
		}
	}
	if v, ok := pyFloat("nan"); !ok || !math.IsNaN(v) {
		t.Errorf("pyFloat(nan) = %v, %v", v, ok)
	}
	for _, in := range []string{".", " e5", "1e", "0x1p3", "1__0", "1_e3", "infinit", "", "1.5.2"} {
		if v, ok := pyFloat(in); ok {
			t.Errorf("pyFloat(%q) = %v, want failure", in, v)
		}
	}
}

func TestPyFloatRepr(t *testing.T) {
	cases := map[float64]string{
		1.5: "1.5", 100000: "100000.0", 1e16: "1e+16", 1e15: "1000000000000000.0", 1e-5: "1e-05",
		0.0001: "0.0001", 123456789012345678.5: "1.2345678901234568e+17", 1.5e300: "1.5e+300", 0.1: "0.1",
		5e-324: "5e-324", 1.7976931348623157e308: "1.7976931348623157e+308", 12345678901234567.0: "1.2345678901234568e+16",
		0.00001234: "1.234e-05",
	}
	for in, want := range cases {
		if got := pyFloatRepr(in); got != want {
			t.Errorf("pyFloatRepr(%v) = %s, want %s", in, got, want)
		}
	}
	if got := pyFloatRepr(math.Copysign(0, -1)); got != "-0.0" {
		t.Errorf("pyFloatRepr(-0) = %s", got)
	}
}

func TestPyStripAndSplit(t *testing.T) {
	if got := pyStrip("\x1c\u3000 x y\u2028\u0085"); got != "x y" {
		t.Errorf("pyStrip = %q", got)
	}
	lines := pySplitLines("a\r\nb\rc\u2028d\x0be\n")
	if len(lines) != 5 || lines[0] != "a" || lines[4] != "e" {
		t.Errorf("pySplitLines = %q", lines)
	}
	if got := pyFields("a, b\u00a0c,d"); len(got) != 3 {
		// "a," "b" "c,d" (comma is not a separator here)
		t.Errorf("pyFields = %q", got)
	}
}
