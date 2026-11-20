package ekpol

import (
	"math"
	"math/big"
	"regexp"
	"strconv"
	"strings"
	"unicode"
	"unicode/utf8"
)

// This file reproduces the few CPython text primitives the reference front end
// relies on (str.strip, str.splitlines, repr(str), int(s, 0), float(s),
// repr(float), the Unicode flavour of \s and \b), so that acceptance and
// diagnostics match the oracle on arbitrary input.

// pyIsSpace reports whether r is whitespace for str.isspace / str.strip / \s.
func pyIsSpace(r rune) bool {
	switch {
	case r >= 0x09 && r <= 0x0D, r >= 0x1C && r <= 0x20:
		return true
	case r == 0x85, r == 0xA0, r == 0x1680:
		return true
	case r >= 0x2000 && r <= 0x200A:
		return true
	case r == 0x2028, r == 0x2029, r == 0x202F, r == 0x205F, r == 0x3000:
		return true
	}
	return false
}

// pyStrip is str.strip() without arguments.
func pyStrip(s string) string { return strings.TrimFunc(s, pyIsSpace) }

// pyFields is str.split() without arguments.
func pyFields(s string) []string { return strings.FieldsFunc(s, pyIsSpace) }

// pySplitLines is str.splitlines() (line boundaries removed).
func pySplitLines(s string) []string {
	var out []string
	start := 0
	i := 0
	for i < len(s) {
		r, w := utf8.DecodeRuneInString(s[i:])
		isBreak := false
		bw := w
		switch {
		case r == '\n', r == 0x0B, r == 0x0C, r == 0x1C, r == 0x1D, r == 0x1E, r == 0x85, r == 0x2028, r == 0x2029:
			isBreak = true
		case r == '\r':
			isBreak = true
			if i+1 < len(s) && s[i+1] == '\n' {
				bw = 2
			}
		}
		if isBreak {
			out = append(out, s[start:i])
			i += bw
			start = i
			continue
		}
		i += w
	}
	if start < len(s) {
		out = append(out, s[start:])
	}
	return out
}

func isWordRune(r rune) bool {
	return r == '_' || unicode.IsLetter(r) || unicode.IsNumber(r)
}

// atWordEnd reports whether s[i:] does not continue a word (the regex \b after a word character).
func atWordEnd(s string, i int) bool {
	if i >= len(s) {
		return true
	}
	r, _ := utf8.DecodeRuneInString(s[i:])
	return !isWordRune(r)
}

// pyRepr is repr(str).
func pyRepr(s string) string {
	quote := byte('\'')
	if strings.Contains(s, "'") && !strings.Contains(s, "\"") {
		quote = '"'
	}
	var b strings.Builder
	b.WriteByte(quote)
	for _, r := range s {
		switch {
		case r == rune(quote), r == '\\':
			b.WriteByte('\\')
			b.WriteRune(r)
		case r == '\t':
			b.WriteString(`\t`)
		case r == '\n':
			b.WriteString(`\n`)
		case r == '\r':
			b.WriteString(`\r`)
		case r < 0x20 || r == 0x7F:
			b.WriteString(`\x`)
			b.WriteString(hex2(int(r)))
		case r < 0x7F:
			b.WriteRune(r)
		case unicode.IsPrint(r):
			b.WriteRune(r)
		case r <= 0xFF:
			b.WriteString(`\x`)
			b.WriteString(hex2(int(r)))
		case r <= 0xFFFF:
			b.WriteString(`\u`)
			b.WriteString(leftPad(strconv.FormatInt(int64(r), 16), 4))
		default:
			b.WriteString(`\U`)
			b.WriteString(leftPad(strconv.FormatInt(int64(r), 16), 8))
		}
	}
	b.WriteByte(quote)
	return b.String()
}

func hex2(v int) string { return leftPad(strconv.FormatInt(int64(v), 16), 2) }

func leftPad(s string, n int) string {
	for len(s) < n {
		s = "0" + s
	}
	return s
}

// pyReprList is repr(list[str]).
func pyReprList(items []string) string {
	parts := make([]string, len(items))
	for i, it := range items {
		parts[i] = pyRepr(it)
	}
	return "[" + strings.Join(parts, ", ") + "]"
}

// asciiDigits converts Unicode decimal digits to ASCII and Unicode spaces to ' ',
// like _PyUnicode_TransformDecimalAndSpaceToASCII; any other non-ASCII rune
// becomes '?'.
func asciiDigits(s string) string {
	var b strings.Builder
	for _, r := range s {
		switch {
		case r < 0x80 && !pyIsSpace(r):
			b.WriteRune(r)
		case pyIsSpace(r):
			b.WriteByte(' ')
		default:
			if v, ok := decimalDigitValue(r); ok {
				b.WriteByte(byte('0' + v))
			} else {
				b.WriteByte('?')
			}
		}
	}
	return b.String()
}

// decimalDigitValue returns the value of a Unicode decimal digit (category Nd).
func decimalDigitValue(r rune) (int, bool) {
	if !unicode.IsDigit(r) {
		return 0, false
	}
	if r < 0x10000 {
		for _, rg := range unicode.Nd.R16 {
			if uint16(r) >= rg.Lo && uint16(r) <= rg.Hi {
				return int(uint16(r)-rg.Lo) / int(rg.Stride) % 10, true
			}
		}
		return 0, false
	}
	for _, rg := range unicode.Nd.R32 {
		if uint32(r) >= rg.Lo && uint32(r) <= rg.Hi {
			return int(uint32(r)-rg.Lo) / int(rg.Stride) % 10, true
		}
	}
	return 0, false
}

func isASCIIDigit(c byte) bool { return c >= '0' && c <= '9' }

func isHexDigit(c byte) bool {
	return isASCIIDigit(c) || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')
}

// pyInt0 is int(s, 0): optional sign, 0x/0o/0b prefixes, single underscores
// between digits, no leading zeros in decimal, surrounding whitespace ignored.
func pyInt0(s string) (*big.Int, bool) {
	t := strings.Trim(asciiDigits(s), " \t\n\v\f\r")
	if t == "" {
		return nil, false
	}
	neg := false
	if t[0] == '+' || t[0] == '-' {
		neg = t[0] == '-'
		t = t[1:]
	}
	if t == "" {
		return nil, false
	}
	base := 10
	prefixed := false
	if len(t) >= 2 && t[0] == '0' {
		switch t[1] {
		case 'x', 'X':
			base, prefixed = 16, true
		case 'o', 'O':
			base, prefixed = 8, true
		case 'b', 'B':
			base, prefixed = 2, true
		}
	}
	if prefixed {
		t = t[2:]
		if strings.HasPrefix(t, "_") {
			t = t[1:]
		}
	}
	if t == "" || t[0] == '_' || t[len(t)-1] == '_' || strings.Contains(t, "__") {
		return nil, false
	}
	digits := strings.ReplaceAll(t, "_", "")
	for i := 0; i < len(digits); i++ {
		c := digits[i]
		ok := false
		switch base {
		case 16:
			ok = isHexDigit(c)
		case 10:
			ok = isASCIIDigit(c)
		case 8:
			ok = c >= '0' && c <= '7'
		case 2:
			ok = c == '0' || c == '1'
		}
		if !ok {
			return nil, false
		}
	}
	v, ok := new(big.Int).SetString(digits, base)
	if !ok {
		return nil, false
	}
	if !prefixed && len(digits) > 1 && digits[0] == '0' && v.Sign() != 0 {
		return nil, false
	}
	if neg {
		v.Neg(v)
	}
	return v, true
}

var floatGrammar = regexp.MustCompile(`^[+-]?(?:[0-9]+(?:_[0-9]+)*(?:\.(?:[0-9]+(?:_[0-9]+)*)?)?|\.[0-9]+(?:_[0-9]+)*)(?:[eE][+-]?[0-9]+(?:_[0-9]+)*)?$`)

// pyFloat is float(s).
func pyFloat(s string) (float64, bool) {
	t := strings.Trim(asciiDigits(s), " \t\n\v\f\r")
	if t == "" {
		return 0, false
	}
	low := strings.ToLower(t)
	sign := 1.0
	body := low
	if body[0] == '+' || body[0] == '-' {
		if body[0] == '-' {
			sign = -1
		}
		body = body[1:]
	}
	switch body {
	case "inf", "infinity":
		return math.Inf(int(sign)), true
	case "nan":
		return math.NaN(), true
	}
	if !floatGrammar.MatchString(t) {
		return 0, false
	}
	v, err := strconv.ParseFloat(strings.ReplaceAll(t, "_", ""), 64)
	if err != nil {
		if ne, ok := err.(*strconv.NumError); ok && ne.Err == strconv.ErrRange {
			return v, true
		}
		return 0, false
	}
	return v, true
}

// pyFloatRepr is repr(float).
func pyFloatRepr(f float64) string {
	switch {
	case math.IsNaN(f):
		return "nan"
	case math.IsInf(f, 1):
		return "inf"
	case math.IsInf(f, -1):
		return "-inf"
	}
	if f == 0 {
		if math.Signbit(f) {
			return "-0.0"
		}
		return "0.0"
	}
	e := strconv.FormatFloat(f, 'e', -1, 64) // d.ddde±XX
	neg := strings.HasPrefix(e, "-")
	e = strings.TrimPrefix(e, "-")
	mant, expStr, _ := strings.Cut(e, "e")
	exp, _ := strconv.Atoi(expStr)
	digits := strings.Replace(mant, ".", "", 1)
	decpt := exp + 1
	var out string
	if decpt <= -4 || decpt > 16 {
		out = digits[:1]
		if len(digits) > 1 {
			out += "." + digits[1:]
		}
		sign := "+"
		if exp < 0 {
			sign = "-"
			exp = -exp
		}
		out += "e" + sign + leftPad(strconv.Itoa(exp), 2)
	} else if decpt <= 0 {
		out = "0." + strings.Repeat("0", -decpt) + digits
	} else if decpt >= len(digits) {
		out = digits + strings.Repeat("0", decpt-len(digits)) + ".0"
	} else {
		out = digits[:decpt] + "." + digits[decpt:]
	}
	if neg {
		out = "-" + out
	}
	return out
}

const wsClass = `\t\n\v\f\r \x1c-\x1f\x85\xa0\x{1680}\x{2000}-\x{200a}\x{2028}\x{2029}\x{202f}\x{205f}\x{3000}`

// pyRe compiles a Python-style pattern, mapping \s to CPython's Unicode whitespace set.
func pyRe(pattern string) *regexp.Regexp {
	return regexp.MustCompile(strings.ReplaceAll(pattern, `\s`, "["+wsClass+"]"))
}

// reMatch is the result of a successful anchored match.
type reMatch struct {
	s   string
	loc []int
}

// find runs re against s and returns nil when there is no match.
func find(re *regexp.Regexp, s string) *reMatch {
	loc := re.FindStringSubmatchIndex(s)
	if loc == nil {
		return nil
	}
	return &reMatch{s: s, loc: loc}
}

// group returns the text of group i ("" when it did not participate).
func (m *reMatch) group(i int) string {
	if m.loc[2*i] < 0 {
		return ""
	}
	return m.s[m.loc[2*i]:m.loc[2*i+1]]
}

// has reports whether group i participated in the match.
func (m *reMatch) has(i int) bool { return m.loc[2*i] >= 0 }

// end is the byte offset of the end of the whole match.
func (m *reMatch) end() int { return m.loc[1] }
