package kpolauth

import "sort"

func inTable(table []runeRange, r rune) bool {
	i := sort.Search(len(table), func(i int) bool { return table[i].hi >= r })
	return i < len(table) && table[i].lo <= r
}

// pyIsAlpha reports str.isalpha() for a single character.
func pyIsAlpha(r rune) bool { return inTable(pyAlphaTable, r) }

// pyIsDigit reports str.isdigit() for a single character.
func pyIsDigit(r rune) bool { return inTable(pyDigitTable, r) }

// pyIsAlnum reports str.isalnum() for a single character: isalpha, isdecimal,
// isdigit or isnumeric (isnumeric covers the other two).
func pyIsAlnum(r rune) bool { return inTable(pyAlphaTable, r) || inTable(pyNumericTable, r) }

// pyDecimalValue returns the value of a character accepted by int(); ok is
// false for characters outside the Unicode decimal digit class.
func pyDecimalValue(r rune) (value int, ok bool) {
	i := sort.Search(len(pyDecimalTable), func(i int) bool { return pyDecimalTable[i].hi >= r })
	if i == len(pyDecimalTable) || pyDecimalTable[i].lo > r {
		return 0, false
	}
	return int(r-pyDecimalTable[i].lo) % 10, true
}
