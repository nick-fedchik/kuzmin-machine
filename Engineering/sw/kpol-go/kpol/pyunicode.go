package kpol

import (
	"fmt"
	"sort"
	"strings"
)

// The reference lexer classifies characters with Python's str.isspace,
// isalpha, isdigit and isalnum (decision D-K1 of the specification). The
// helpers below reproduce those classes from frozen tables so that the port
// does not depend on the Unicode version of the Go toolchain.

func inRanges(table []runeRange, r rune) bool {
	i := sort.Search(len(table), func(i int) bool { return table[i].hi >= r })
	return i < len(table) && table[i].lo <= r
}

func pyIsSpace(r rune) bool     { return inRanges(pySpaceTable, r) }
func pyIsAlpha(r rune) bool     { return inRanges(pyAlphaTable, r) }
func pyIsDigit(r rune) bool     { return inRanges(pyDigitTable, r) }
func pyIsDecimal(r rune) bool   { return inRanges(pyDecimalTable, r) }
func pyIsAlnum(r rune) bool     { return inRanges(pyAlnumTable, r) }
func pyIsPrintable(r rune) bool { return inRanges(pyPrintableTable, r) }

// pyDecimalValue returns the decimal digit value of a code point for which
// pyIsDecimal holds.
func pyDecimalValue(r rune) int {
	i := sort.Search(len(pyDecimalZeros), func(i int) bool { return pyDecimalZeros[i] > r })
	return int(r - pyDecimalZeros[i-1])
}

// pyRepr renders s like Python's repr(str).
func pyRepr(s string) string {
	quote := '\''
	if strings.ContainsRune(s, '\'') && !strings.ContainsRune(s, '"') {
		quote = '"'
	}
	var b strings.Builder
	b.WriteRune(quote)
	for _, r := range s {
		switch {
		case r == quote || r == '\\':
			b.WriteByte('\\')
			b.WriteRune(r)
		case r == '\t':
			b.WriteString(`\t`)
		case r == '\n':
			b.WriteString(`\n`)
		case r == '\r':
			b.WriteString(`\r`)
		case r < ' ' || r == 0x7f:
			fmt.Fprintf(&b, `\x%02x`, r)
		case r < 0x7f:
			b.WriteRune(r)
		case pyIsPrintable(r):
			b.WriteRune(r)
		case r <= 0xff:
			fmt.Fprintf(&b, `\x%02x`, r)
		case r <= 0xffff:
			fmt.Fprintf(&b, `\u%04x`, r)
		default:
			fmt.Fprintf(&b, `\U%08x`, r)
		}
	}
	b.WriteRune(quote)
	return b.String()
}

// pyStrip removes leading and trailing Python whitespace.
func pyStrip(s string) string {
	return strings.TrimFunc(s, pyIsSpace)
}

// pySplitLines splits like Python's str.splitlines() without keepends.
func pySplitLines(s string) []string {
	var lines []string
	rs := []rune(s)
	var cur []rune
	for i := 0; i < len(rs); i++ {
		r := rs[i]
		switch r {
		case '\r':
			lines = append(lines, string(cur))
			cur = cur[:0]
			if i+1 < len(rs) && rs[i+1] == '\n' {
				i++
			}
		case '\n', '\v', '\f', 0x1c, 0x1d, 0x1e, 0x85, 0x2028, 0x2029:
			lines = append(lines, string(cur))
			cur = cur[:0]
		default:
			cur = append(cur, r)
		}
	}
	if len(cur) > 0 {
		lines = append(lines, string(cur))
	}
	return lines
}
