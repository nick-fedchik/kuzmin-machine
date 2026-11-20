package kpolauth

import (
	"fmt"
	"math/big"
	"unicode/utf8"
)

// GroupKind is the kind of a bracket group, set by its opening bracket
// (KPA-CST-3).
type GroupKind string

// Group kinds.
const (
	CollectionBrace GroupKind = "collection_brace"
	CollectionParen GroupKind = "collection_paren"
	ArrayBracket    GroupKind = "array_bracket"
)

// BitOrderLSBLeft is the only bit order of Def: the lowest bit is written on
// the left (RFC-018).
const BitOrderLSBLeft = "lsb_left_msb_right"

// MaxNesting bounds the nesting of bracket groups, parameters and ":=" chains.
// The reference fails with RecursionError at roughly 160 levels; the Go port
// accepts every input the reference accepts and refuses pathological depth with
// CodeNestingLimit instead of exhausting the stack.
const MaxNesting = 1000

// Node is a CST node (ASN.1 type Node of KPA-CST-1).
type Node interface {
	// Span is the source range of the node (KPA-CST-2).
	Span() Span
	// CSTName is the class name used by the reference ("GroupBoundsCST",
	// "CallOrConstructCST", ...), which also appears in diagnostics.
	CSTName() string
	isNode()
}

type nodeBase struct{ span Span }

// Span returns the source range.
func (b nodeBase) Span() Span { return b.span }
func (nodeBase) isNode()      {}

// Identifier is a name; Token.Kind is TokIdent.
type Identifier struct {
	nodeBase
	Token Token
}

// Literal is an INT, TEXT, "!", "¬" or (record-diagnostic mode) "#" literal.
type Literal struct {
	nodeBase
	Token Token
}

// Uninit is the uninitialized-state sign "_".
type Uninit struct {
	nodeBase
	Token Token
}

// Param is "@" followed by its target.
type Param struct {
	nodeBase
	AtToken Token
	Target  Node
}

// BracketGroup is a paired-bracket group with its elements.
type BracketGroup struct {
	nodeBase
	OpenToken  Token
	CloseToken Token
	Kind       GroupKind
	Elements   []Node
	// CommaTokens are the commas that directly follow elements.
	CommaTokens []Token
	// HasStubBrackets is true if an element is the identifier OpenBracket or
	// CloseBracket (KPA-CST-3).
	HasStubBrackets bool
}

// Construct is an identifier directly followed by a "(…)" or "{…}" group
// (CallOrConstructCST). The reference never fills the bounds of the descriptive
// model; bounds always wrap the construct as a GroupBounds node.
type Construct struct {
	nodeBase
	Name  *Identifier
	Group *BracketGroup
}

// GroupBounds is a target followed by a "[…]" bounds group (KPA-CST-4). MinRaw
// and MaxRaw hold the defaulted Min and Max values, MaxEffective is Max+1.
type GroupBounds struct {
	nodeBase
	Target       Node
	Group        *BracketGroup
	MinRaw       *big.Int
	MaxRaw       *big.Int
	MinEffective *big.Int
	MaxEffective *big.Int
}

// DefLayout is Def(…) or Def{…} with 7 (or, under U11 record-diagnostic, 8)
// elements; Bits are the integer literals in textual order (KPA-CST-5).
type DefLayout struct {
	nodeBase
	Keyword  *Identifier
	Group    *BracketGroup
	Bits     []*big.Int
	BitOrder string
}

// SubscriptionSeq is "left • right".
type SubscriptionSeq struct {
	nodeBase
	Left     Node
	DotToken Token
	Right    Node
}

// Assignment is "target := value".
type Assignment struct {
	nodeBase
	Target  Node
	OpToken Token
	Value   Node
}

// BinaryExpr is "left op right" for + - * / = < > :.
type BinaryExpr struct {
	nodeBase
	Left    Node
	OpToken Token
	Right   Node
}

// CSTName implementations.
func (*Identifier) CSTName() string      { return "IdentifierCST" }
func (*Literal) CSTName() string         { return "LiteralCST" }
func (*Uninit) CSTName() string          { return "UninitCST" }
func (*Param) CSTName() string           { return "ParamCST" }
func (*BracketGroup) CSTName() string    { return "BracketGroupCST" }
func (*Construct) CSTName() string       { return "CallOrConstructCST" }
func (*GroupBounds) CSTName() string     { return "GroupBoundsCST" }
func (*DefLayout) CSTName() string       { return "DefLayoutCST" }
func (*SubscriptionSeq) CSTName() string { return "SubscriptionSeqCST" }
func (*Assignment) CSTName() string      { return "AssignmentCST" }
func (*BinaryExpr) CSTName() string      { return "BinaryExprCST" }

// Program is the result of parsing (ProgramCST). Diagnostics holds the
// warnings recorded under the record-diagnostic policy.
type Program struct {
	Items       []Node
	Diagnostics []Diagnostic
}

func mergeSpans(start, end Span) Span {
	return Span{
		Line:       start.Line,
		Column:     start.Column,
		Offset:     start.Offset,
		Length:     end.Offset + end.Length - start.Offset,
		EndLine:    end.EndLine,
		EndColumn:  end.EndColumn,
		ByteOffset: start.ByteOffset,
		ByteEnd:    end.ByteEnd,
	}
}

// Parse tokenizes and parses KPOL-AUTH source text into a CST (KPA-SYN-1..8,
// KPA-CTX, KPA-CST). On failure the returned error is an *Error.
func Parse(src string, cfg Config) (*Program, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	f := &frontend{cfg: cfg}
	toks, err := tokenize(f, src)
	if err != nil {
		return nil, err
	}
	return parseTokens(f, toks)
}

func parseTokens(f *frontend, toks []Token) (prog *Program, err error) {
	defer recoverBailout(&err)
	p := &parser{f: f, toks: toks}
	items := []Node{}
	for p.peek() != nil {
		items = append(items, p.parseStatement())
	}
	return &Program{Items: items, Diagnostics: f.diags}, nil
}

type parser struct {
	f     *frontend
	toks  []Token
	pos   int
	depth int
}

func (p *parser) peek() *Token {
	if p.pos < len(p.toks) {
		return &p.toks[p.pos]
	}
	return nil
}

func (p *parser) advance() Token {
	t := p.toks[p.pos]
	p.pos++
	return t
}

func (p *parser) enter() {
	p.depth++
	if p.depth > MaxNesting {
		panic(bailout{&Error{
			Code: CodeNestingLimit,
			Msg:  fmt.Sprintf("Перевищено глибину вкладення (%d).", MaxNesting),
		}})
	}
}

func (p *parser) leave() { p.depth-- }

// parseStatement is parse_subscription_or_assign (KPA-SYN-4).
func (p *parser) parseStatement() Node {
	left := p.parseExpr()
	tok := p.peek()
	if tok != nil && tok.Kind == TokAssign {
		op := p.advance()
		p.enter()
		right := p.parseStatement()
		p.leave()
		if containsSubscriptionSeq(right) {
			sp := right.Span()
			p.f.emit("KPOL-AUTH-U08",
				"Використання булевого значення '•' у присвоєнні не визначено автором (RFC-017 п. 2).", &sp)
		}
		return &Assignment{nodeBase{mergeSpans(left.Span(), right.Span())}, left, op, right}
	}

	for tok != nil && tok.Kind == TokSubscriptionSeq {
		dot := p.advance()
		right := p.parseExpr()
		if containsBusyProbe(right) {
			sp := right.Span()
			p.f.emit("KPOL-AUTH-U09",
				"Стан busy між читанням і записом в 'A • B' не визначено автором (RFC-017 п. 1).", &sp)
		}
		left = &SubscriptionSeq{nodeBase{mergeSpans(left.Span(), right.Span())}, left, dot, right}
		tok = p.peek()
	}
	return left
}

func containsSubscriptionSeq(n Node) bool {
	switch n := n.(type) {
	case *SubscriptionSeq:
		return true
	case *BracketGroup:
		for _, el := range n.Elements {
			if containsSubscriptionSeq(el) {
				return true
			}
		}
	}
	return false
}

// isBusy reports name.lower() == "busy"; only ASCII letters lower-case to it.
func isBusy(name string) bool {
	if len(name) != 4 {
		return false
	}
	for i, want := range "busy" {
		c := rune(name[i])
		if c >= 'A' && c <= 'Z' {
			c += 'a' - 'A'
		}
		if c != want {
			return false
		}
	}
	return true
}

func containsBusyProbe(n Node) bool {
	switch n := n.(type) {
	case *Identifier:
		return isBusy(n.Token.Value)
	case *Construct:
		if isBusy(n.Name.Token.Value) {
			return true
		}
		for _, el := range n.Group.Elements {
			if containsBusyProbe(el) {
				return true
			}
		}
	case *BracketGroup:
		for _, el := range n.Elements {
			if containsBusyProbe(el) {
				return true
			}
		}
	}
	return false
}

func isBinop(k TokenKind) bool {
	switch k {
	case TokPlus, TokMinus, TokStar, TokSlash, TokEq, TokLt, TokGt, TokColon:
		return true
	}
	return false
}

func isArithmetic(k TokenKind) bool {
	switch k {
	case TokPlus, TokMinus, TokStar, TokSlash:
		return true
	}
	return false
}

// parseExpr is the single-level left-associative binary expression (KPA-SYN-3).
func (p *parser) parseExpr() Node {
	left := p.parsePostfix()
	for {
		tok := p.peek()
		if tok == nil || !isBinop(tok.Kind) {
			return left
		}
		op := p.advance()
		right := p.parsePostfix()
		if isArithmetic(op.Kind) {
			_, leftUninit := left.(*Uninit)
			_, rightUninit := right.(*Uninit)
			if leftUninit || rightUninit {
				sp := op.Span
				p.f.emit("KPOL-AUTH-U10",
					"Читання неініціалізованого стану '_' в арифметичному виразі не визначено автором (RFC-017 п. 3).", &sp)
			}
		}
		left = &BinaryExpr{nodeBase{mergeSpans(left.Span(), right.Span())}, left, op, right}
	}
}

func (p *parser) parsePostfix() Node {
	node := p.parsePrimary()
	for {
		tok := p.peek()
		if tok == nil || tok.Kind != TokLBracket {
			return node
		}
		group := p.parseBracketGroup()
		node = p.attachBounds(node, group)
	}
}

// intLiteral returns the literal if n is an INT literal.
func intLiteral(n Node) (*Literal, bool) {
	lit, ok := n.(*Literal)
	return lit, ok && lit.Token.Kind == TokInt
}

// decimalValue is int(token.value) of the reference: ASCII and other Unicode
// decimal digits are accepted; a character that is only str.isdigit (for
// example "²") makes the reference raise ValueError (D-A1).
func decimalValue(tok Token) (*big.Int, *Error) {
	digits := make([]byte, 0, len(tok.Value))
	for _, r := range tok.Value {
		v, ok := pyDecimalValue(r)
		if !ok {
			sp := tok.Span
			return nil, &Error{
				Code: CodeNonDecimalDigit,
				Msg:  fmt.Sprintf("Символ '%c' у цілому літералі є цифрою за str.isdigit, але не десятковою цифрою (D-A1).", r),
				Span: &sp,
			}
		}
		digits = append(digits, byte('0'+v))
	}
	n, ok := new(big.Int).SetString(string(digits), 10)
	if !ok {
		sp := tok.Span
		return nil, &Error{Code: CodeNonDecimalDigit, Msg: "Порожній цілий літерал.", Span: &sp}
	}
	return n, nil
}

func (p *parser) intValue(lit *Literal) *big.Int {
	v, err := decimalValue(lit.Token)
	if err != nil {
		panic(bailout{err})
	}
	return v
}

// attachBounds builds GroupBounds from the "[…]" group (KPA-CST-4, KPA-CTX-2).
func (p *parser) attachBounds(target Node, bounds *BracketGroup) *GroupBounds {
	var minVal, maxVal *big.Int
	one := big.NewInt(1)
	for _, el := range bounds.Elements {
		bin, ok := el.(*BinaryExpr)
		if !ok || bin.OpToken.Kind != TokEq {
			continue
		}
		id, ok := bin.Left.(*Identifier)
		if !ok {
			continue
		}
		switch key := id.Token.Value; key {
		case "Logic", "Op":
			sp := bin.Span()
			p.f.emit("KPOL-AUTH-U01",
				"Зв'язок семантики И/ИЛИ з межами Min/Max не визначено автором (RFC-009 п. 2).", &sp)
		case "Min", "Max":
			lit, isInt := intLiteral(bin.Right)
			if !isInt {
				sp := bin.Right.Span()
				p.f.emit("KPOL-AUTH-U02",
					fmt.Sprintf("Не-Token індекс для %s не визначено автором (RFC-009 п. 3).", key), &sp)
				continue
			}
			val := p.intValue(lit)
			if key == "Min" {
				minVal = val
			} else {
				maxVal = val
			}
		case "Count":
			lit, isInt := intLiteral(bin.Right)
			if !isInt {
				continue
			}
			cnt := p.intValue(lit)
			effMin, effMax := one, one
			if minVal != nil {
				effMin = minVal
			}
			if maxVal != nil {
				effMax = new(big.Int).Add(maxVal, one)
			}
			if cnt.Cmp(effMin) < 0 || cnt.Cmp(effMax) > 0 {
				sp := bin.Span()
				p.f.emit("KPOL-AUTH-U02",
					fmt.Sprintf("Вихід за межі Count=%s поза [%s, %s] не визначено автором (RFC-009 п. 3).",
						cnt, effMin, effMax), &sp)
			}
		}
	}

	effMin, effMax, rawMax := big.NewInt(1), big.NewInt(1), big.NewInt(0)
	if minVal != nil {
		effMin = new(big.Int).Set(minVal)
	}
	if maxVal != nil {
		effMax = new(big.Int).Add(maxVal, one)
		rawMax = new(big.Int).Set(maxVal)
	}
	return &GroupBounds{
		nodeBase:     nodeBase{mergeSpans(target.Span(), bounds.Span())},
		Target:       target,
		Group:        bounds,
		MinRaw:       new(big.Int).Set(effMin),
		MaxRaw:       rawMax,
		MinEffective: effMin,
		MaxEffective: effMax,
	}
}

func (p *parser) parsePrimary() Node {
	tok := p.peek()
	if tok == nil {
		panic(p.f.syntaxError("KPOL-AUTH-SYNTAX-01", "Несподіваний кінець файлу.", nil))
	}

	switch tok.Kind {
	case TokSubscriptionSeq:
		p.advance()
		sp := tok.Span
		panic(p.f.syntaxError("KPOL-AUTH-SYNTAX-03",
			"У діалекті KPOL-AUTH символ '•' позначає подію/послідовність підписки (A • B), а не унарний 'not'.", &sp))

	case TokAt:
		atTok := p.advance()
		p.enter()
		target := p.parsePrimary()
		p.leave()
		if id, ok := target.(*Identifier); ok && id.Token.Value == "runtime" {
			sp := atTok.Span
			p.f.emit("KPOL-AUTH-U04",
				"Момент виконання OpenBracket/CloseBracket (рантайм vs транслятор) не визначено автором (RFC-015).", &sp)
		}
		return &Param{nodeBase{mergeSpans(atTok.Span, target.Span())}, atTok, target}

	case TokLBrace, TokLParen, TokLBracket:
		return p.parseBracketGroup()

	case TokRBrace, TokRParen, TokRBracket:
		sp := tok.Span
		panic(p.f.syntaxError("KPOL-AUTH-SYNTAX-02",
			fmt.Sprintf("Зайва закривальна дужка '%s' без відповідної відкривальної.", tok.Value), &sp))

	case TokIdent:
		identTok := p.advance()
		if identTok.Value == "CloseBracked" {
			sp := identTok.Span
			p.f.emit("KPOL-AUTH-U03",
				"Написання 'CloseBracked' конфліктує з 'CloseBracket' (RFC-015).", &sp)
		}
		if identTok.Value == "Child" {
			sp := identTok.Span
			p.f.emit("KPOL-AUTH-U11",
				"Роль елемента 'Child' («один лишний») у байті Def не визначена автором (RFC-018).", &sp)
		}
		ident := &Identifier{nodeBase{identTok.Span}, identTok}
		if nxt := p.peek(); nxt != nil && (nxt.Kind == TokLParen || nxt.Kind == TokLBrace) {
			group := p.parseBracketGroup()
			return p.buildConstruct(ident, group)
		}
		return ident

	case TokInt, TokText, TokBoolBang, TokBoolNotSign, TokHashLegacy:
		lit := p.advance()
		return &Literal{nodeBase{lit.Span}, lit}

	case TokUninit:
		u := p.advance()
		return &Uninit{nodeBase{u.Span}, u}
	}

	sp := tok.Span
	panic(p.f.syntaxError("KPOL-AUTH-SYNTAX-01",
		fmt.Sprintf("Несподіваний токен %s ('%s').", tok.Kind, tok.Value), &sp))
}

// buildConstruct builds DefLayout or Construct and applies the Def, Name and
// Property gates (KPA-SYN-8, U07, U11, U12).
func (p *parser) buildConstruct(ident *Identifier, group *BracketGroup) Node {
	switch ident.Token.Value {
	case "Def":
		width := len(group.Elements)
		if width == 8 {
			sp := group.Span()
			p.f.emit("KPOL-AUTH-U11",
				"8-бітний запис Def включає елемент Child, який Автор назвав «лишний» (RFC-018).", &sp)
		} else if width != 7 {
			sp := group.Span()
			panic(p.f.syntaxError("KPOL-AUTH-SYNTAX-04",
				fmt.Sprintf("Непідтримувана ширина Def(%d бітів): підтверджено лише 7-бітний запис (8-бітний із Child підпадає під KPOL-AUTH-U11).", width), &sp))
		}
		bits := []*big.Int{}
		for _, el := range group.Elements {
			if lit, ok := intLiteral(el); ok {
				bits = append(bits, p.intValue(lit))
			}
		}
		return &DefLayout{
			nodeBase: nodeBase{mergeSpans(ident.Span(), group.Span())},
			Keyword:  ident,
			Group:    group,
			Bits:     bits,
			BitOrder: BitOrderLSBLeft,
		}

	case "Name":
		if len(group.Elements) == 1 {
			if lit, ok := group.Elements[0].(*Literal); ok {
				val := lit.Token.Value
				cpLen := utf8.RuneCountInString(val)
				byteLen := len(val)
				unit := p.f.cfg.unit()
				exceeds := byteLen > 16
				if unit == Codepoints {
					exceeds = cpLen > 16
				}
				if exceeds {
					sp := lit.Span()
					p.f.emit("KPOL-AUTH-U07",
						fmt.Sprintf("Одиниця довжини Name (одиниця '%s': codepoints=%d, utf8_bytes=%d, межа 16) не визначена автором (RFC-016 п. 3).",
							unit, cpLen, byteLen), &sp)
				}
			}
		}

	case "Property":
		hasDefBit, hasUninit := false, false
		for _, el := range group.Elements {
			bin, ok := el.(*BinaryExpr)
			if !ok || bin.OpToken.Kind != TokEq {
				continue
			}
			id, ok := bin.Left.(*Identifier)
			if !ok {
				continue
			}
			if id.Token.Value == "DefBit" {
				hasDefBit = true
			}
			if _, isUninit := bin.Right.(*Uninit); id.Token.Value == "Value" && isUninit {
				hasUninit = true
			}
		}
		if hasDefBit && hasUninit {
			sp := group.Span()
			p.f.emit("KPOL-AUTH-U12",
				"Розмежування Def[i]=0 та елемента зі станом '_' не визначено автором (RFC-018 / RFC-010 п. 3).", &sp)
		}
	}

	return &Construct{nodeBase{mergeSpans(ident.Span(), group.Span())}, ident, group}
}

func (p *parser) parseBracketGroup() *BracketGroup {
	openTok := p.advance()
	openRune, _ := utf8.DecodeRuneInString(openTok.Value)
	expectedClose := string(closingBracket(openRune))
	p.enter()
	defer p.leave()
	elements := []Node{}
	var commas []Token

	for {
		tok := p.peek()
		if tok == nil {
			break
		}
		if tok.Kind == TokRBrace || tok.Kind == TokRParen || tok.Kind == TokRBracket {
			if tok.Value != expectedClose {
				sp := tok.Span
				panic(p.f.syntaxError("KPOL-AUTH-SYNTAX-02",
					fmt.Sprintf("Закривальна дужка '%s' не відповідає відкривальній '%s' (RFC-011).", tok.Value, openTok.Value), &sp))
			}
			closeTok := p.advance()
			hasStubs := false
			for _, el := range elements {
				if id, ok := el.(*Identifier); ok && (id.Token.Value == "OpenBracket" || id.Token.Value == "CloseBracket") {
					hasStubs = true
					break
				}
			}
			return &BracketGroup{
				nodeBase:        nodeBase{mergeSpans(openTok.Span, closeTok.Span)},
				OpenToken:       openTok,
				CloseToken:      closeTok,
				Kind:            groupKind(openRune),
				Elements:        elements,
				CommaTokens:     commas,
				HasStubBrackets: hasStubs,
			}
		}

		elements = append(elements, p.parseStatement())
		if nxt := p.peek(); nxt != nil && nxt.Kind == TokComma {
			commas = append(commas, p.advance())
		}
	}

	sp := openTok.Span
	panic(p.f.syntaxError("KPOL-AUTH-SYNTAX-02",
		fmt.Sprintf("Незакрита дужка '%s' (очікувалась '%s').", openTok.Value, expectedClose), &sp))
}

func groupKind(open rune) GroupKind {
	switch open {
	case '{':
		return CollectionBrace
	case '(':
		return CollectionParen
	}
	return ArrayBracket
}
