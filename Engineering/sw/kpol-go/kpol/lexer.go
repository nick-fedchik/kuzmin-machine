package kpol

import "fmt"

// Token kinds produced by Tokenize (reference: tokenize).
const (
	TokID         = "ID"
	TokNumber     = "NUMBER"
	TokOp         = "OP"
	TokPunct      = "PUNCT"
	TokAliasWrite = "ALIAS_WRITE"
	TokAliasRead  = "ALIAS_READ"
	TokAliasPhase = "ALIAS_PHASE"
	TokEOF        = "EOF"
)

// Token is a lexeme with its 1-based position. Line and Column count code
// points; alias tokens carry their kind name as Value, as in the reference.
type Token struct {
	Kind   string
	Value  string
	Line   int
	Column int
}

type aliasSpec struct {
	text []rune
	kind string
}

// Alias lexemes in the order the reference lexer tries them (KPOL-LEX-3).
var aliasSpecs = []aliasSpec{
	{[]rune("(*)"), TokAliasPhase},
	{[]rune("<-"), TokAliasWrite},
	{[]rune("->"), TokAliasRead},
	{[]rune("←"), TokAliasWrite},
	{[]rune("→"), TokAliasRead},
	{[]rune("•"), TokAliasPhase},
}

var twoCharOps = [...]string{"==", "!=", "<=", ">=", ":="}

// hasASCIIAt reports whether the ASCII string p occurs in src at position i.
func hasASCIIAt(src []rune, i int, p string) bool {
	if i+len(p) > len(src) {
		return false
	}
	for k := 0; k < len(p); k++ {
		if src[i+k] != rune(p[k]) {
			return false
		}
	}
	return true
}

func hasPrefixAt(src []rune, i int, p []rune) bool {
	if i+len(p) > len(src) {
		return false
	}
	for k, r := range p {
		if src[i+k] != r {
			return false
		}
	}
	return true
}

// Tokenize splits KPOL source text into tokens (KPOL-LEX-1..6). Characters
// are classified like the reference lexer, which uses Python's Unicode
// classes (D-K1). The result always ends with an EOF token.
func Tokenize(src string) ([]Token, error) {
	rs := []rune(src)
	var toks []Token
	i, line, col := 0, 1, 1

	advance := func(n int) {
		for k := 0; k < n; k++ {
			if rs[i+k] == '\n' {
				line++
				col = 1
			} else {
				col++
			}
		}
		i += n
	}

	for i < len(rs) {
		ch := rs[i]
		if pyIsSpace(ch) {
			advance(1)
			continue
		}
		if ch == '#' || hasASCIIAt(rs, i, "//") {
			end := i
			for end < len(rs) && rs[end] != '\n' {
				end++
			}
			advance(end - i)
			continue
		}
		if hasASCIIAt(rs, i, "/*") {
			end := -1
			for k := i + 2; k+1 < len(rs); k++ {
				if rs[k] == '*' && rs[k+1] == '/' {
					end = k
					break
				}
			}
			if end < 0 {
				return nil, &Error{Msg: fmt.Sprintf("%d:%d: unterminated block comment", line, col)}
			}
			advance(end + 2 - i)
			continue
		}
		matched := false
		for _, a := range aliasSpecs {
			if hasPrefixAt(rs, i, a.text) {
				toks = append(toks, Token{a.kind, a.kind, line, col})
				advance(len(a.text))
				matched = true
				break
			}
		}
		if matched {
			continue
		}
		for _, op := range twoCharOps {
			if hasASCIIAt(rs, i, op) {
				toks = append(toks, Token{TokOp, op, line, col})
				advance(2)
				matched = true
				break
			}
		}
		if matched {
			continue
		}
		switch ch {
		case '{', '}', '(', ')', ':', ',', ';', '=':
			toks = append(toks, Token{TokPunct, string(ch), line, col})
			advance(1)
			continue
		case '<', '>', '+', '-', '*', '/':
			toks = append(toks, Token{TokOp, string(ch), line, col})
			advance(1)
			continue
		}
		if pyIsDigit(ch) {
			start := i
			j := i
			for j < len(rs) && pyIsDigit(rs[j]) {
				j++
			}
			if j < len(rs) && rs[j] == '.' {
				j++
				if j == len(rs) || !pyIsDigit(rs[j]) {
					return nil, &Error{Msg: fmt.Sprintf("%d:%d: malformed numeric literal", line, col)}
				}
				for j < len(rs) && pyIsDigit(rs[j]) {
					j++
				}
			}
			toks = append(toks, Token{TokNumber, string(rs[start:j]), line, col})
			advance(j - start)
			continue
		}
		if ch == '_' || pyIsAlpha(ch) {
			start := i
			j := i
			for j < len(rs) && (rs[j] == '_' || pyIsAlnum(rs[j])) {
				j++
			}
			toks = append(toks, Token{TokID, string(rs[start:j]), line, col})
			advance(j - start)
			continue
		}
		return nil, &Error{Msg: fmt.Sprintf("%d:%d: unexpected character %s", line, col, pyRepr(string(ch)))}
	}
	toks = append(toks, Token{TokEOF, "", line, col})
	return toks, nil
}
