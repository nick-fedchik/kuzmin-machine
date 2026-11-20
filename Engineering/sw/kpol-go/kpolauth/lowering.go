package kpolauth

import (
	"encoding/binary"
	"fmt"
	"math/big"
	"sort"
)

// Limits of the C99 runtime and of the CME-RAW-1 image (KPA-L-4, KPA-L-10).
const (
	MaxConcepts      = 64
	MaxSubscriptions = 128
	MaxInstructions  = 512
)

// Do/Go opcodes (km_mcu_fpga_bridge.c).
const (
	OpcNop  = 0x0
	OpcGo   = 0x1
	OpcDo   = 0x2
	OpcImm  = 0x3
	OpcExit = 0x5
)

// Go sub-operations (kind of addressing).
const (
	GoExec  = 0x0
	GoWrite = 0x1
	GoRead  = 0x2
)

// Concept flags.
const (
	FlagSelfSuppress = 0x01
	FlagHWProtected  = 0x08
)

// Do sub-operations.
const (
	DoAdd = 0
	DoSub = 1
	DoMul = 2
)

// Event mask bits (KM_EV_*; the bit number equals the AuthDataEvent code).
const (
	EvNull     = 1 << 1
	EvPositive = 1 << 2
	EvNegative = 1 << 3
	EvEven     = 1 << 4
	EvUneven   = 1 << 5
	EvChanged  = 1 << 6
	EvAlways   = 1 << 7
)

// Subscription phases (KM_PHASE_*).
const (
	PhasePreWrite   = 0
	PhasePostChange = 1
	PhaseOnRead     = 2
	PhaseOnExec     = 3
	PhaseOnAbort    = 4
)

// CME-RAW-1 image constants (KPOL-P0-1).
const (
	CMESlotCount         = 64
	CMEImageBytes        = 1024
	CMEGuardInvariantEN  = 0x02
	CMEGuardSubscriberEN = 0x10
)

// PackInstr packs a 32-bit Do/Go instruction word like km_pack_instr of
// km_mcu_fpga_bridge.c (KPA-L-13): each field is truncated to its width.
func PackInstr(opc, subOp, flags, operand uint32) uint32 {
	return (opc&0x0F)<<28 | (subOp&0x0F)<<24 | (flags&0xFF)<<16 | operand&0xFFFF
}

// LoweredConcept is a row of the concept table.
type LoweredConcept struct {
	CID         int
	Name        string
	InitVal     int64
	Flags       int
	LowerBound  *int64
	UpperBound  *int64
	FirstSubIdx int
	SubCount    int
}

// LoweredSubscription is a row of the subscription table.
type LoweredSubscription struct {
	SubIdx      int
	OwnerCID    int
	TargetCID   int
	Phase       int
	TriggerMask int
	LineStartPC int
	LineLen     int
}

// Artifact is the result of the KPOL-AUTH-L1 lowering (LoweredArtifact): the
// concept and subscription tables, the Do/Go bytecode and the CME-RAW-1 image.
type Artifact struct {
	Concepts      []LoweredConcept
	Subscriptions []LoweredSubscription
	codeO         []uint32
	bram          []byte
}

// CodeO returns a copy of the Do/Go bytecode words.
func (a *Artifact) CodeO() []uint32 { return append([]uint32(nil), a.codeO...) }

// BRAMImage returns a copy of the 1024-byte CME-RAW-1 routing image.
func (a *Artifact) BRAMImage() []byte { return append([]byte(nil), a.bram...) }

// DoGoBinary returns the code words as uint32 little-endian bytes, the content
// of "--emit-dogo OUT.bin".
func (a *Artifact) DoGoBinary() []byte {
	out := make([]byte, 0, 4*len(a.codeO))
	for _, w := range a.codeO {
		out = binary.LittleEndian.AppendUint32(out, w)
	}
	return out
}

func spanOf(n Node) *Span {
	s := n.Span()
	return &s
}

func lowerFail(code, msg string, span *Span) bailout {
	return bailout{&Error{Code: code, Msg: msg, Span: span}}
}

// int32Literal is _parse_int32.
func int32Literal(n Node) int64 {
	lit, ok := intLiteral(n)
	if !ok {
		panic(lowerFail("KPOL-LOWER-LITERAL", "Очікувався цілочисельний літерал.", spanOf(n)))
	}
	val := lowerInt(lit)
	if val.Cmp(big.NewInt(-2147483648)) < 0 || val.Cmp(big.NewInt(2147483647)) > 0 {
		panic(lowerFail("KPOL-LOWER-RANGE", fmt.Sprintf("Значення %s виходить за межі Int32.", val), spanOf(n)))
	}
	return val.Int64()
}

// lowerInt is int(token.value) in the lowering stage.
func lowerInt(lit *Literal) *big.Int {
	v, err := decimalValue(lit.Token)
	if err != nil {
		err.Code = CodeLowerNonDecimalDigit
		panic(bailout{err})
	}
	return v
}

func binopToDo(k TokenKind) (uint32, bool) {
	switch k {
	case TokPlus:
		return DoAdd, true
	case TokMinus:
		return DoSub, true
	case TokStar:
		return DoMul, true
	}
	return 0, false
}

// emitExpr is _emit_expr (KPA-L-14). The reference fails with RecursionError on
// expressions nested deeper than about 990 levels, long before the 512-word
// limit can be met; here the depth is bounded by MaxNesting.
func emitExpr(n Node, conceptByName map[string]int, out *[]uint32, depth int) {
	if depth > MaxNesting {
		panic(lowerFail("KPOL-LOWER-LIMIT", fmt.Sprintf("Перевищено глибину вкладення виразу (%d).", MaxNesting), spanOf(n)))
	}
	switch n := n.(type) {
	case *BracketGroup:
		if n.Kind == CollectionParen {
			if len(n.Elements) != 1 {
				panic(lowerFail("KPOL-LOWER-EXPR", "Дужковий вираз повинен містити рівно один елемент.", spanOf(n)))
			}
			emitExpr(n.Elements[0], conceptByName, out, depth+1)
			return
		}
	case *Literal:
		if n.Token.Kind == TokInt {
			val := lowerInt(n)
			if val.Cmp(big.NewInt(-32768)) < 0 || val.Cmp(big.NewInt(32767)) > 0 {
				panic(lowerFail("KPOL-LOWER-RANGE",
					fmt.Sprintf("Константа %s не вміщується у 16-бітний знаковий операнд KM_OPC_IMM.", val), spanOf(n)))
			}
			*out = append(*out, PackInstr(OpcImm, 0, 0, uint32(val.Int64())&0xFFFF))
			return
		}
	case *Identifier:
		cid, ok := conceptByName[n.Token.Value]
		if !ok {
			panic(lowerFail("KPOL-LOWER-UNKNOWN-CONCEPT",
				fmt.Sprintf("Невідомий концепт '%s' у виразі.", n.Token.Value), spanOf(n)))
		}
		*out = append(*out, PackInstr(OpcGo, GoRead, 0, uint32(cid)))
		return
	case *BinaryExpr:
		subOp, ok := binopToDo(n.OpToken.Kind)
		if !ok {
			sp := n.OpToken.Span
			panic(lowerFail("KPOL-LOWER-UNSUPPORTED-OP",
				fmt.Sprintf("Оператор '%s' не підтримується в Do/Go lowering.", n.OpToken.Value), &sp))
		}
		emitExpr(n.Left, conceptByName, out, depth+1)
		emitExpr(n.Right, conceptByName, out, depth+1)
		*out = append(*out, PackInstr(OpcDo, subOp, 0, 0))
		return
	}
	panic(lowerFail("KPOL-LOWER-UNSUPPORTED-CST",
		fmt.Sprintf("Конструкція '%s' поза детермінованою підмножиною виразів.", n.CSTName()), spanOf(n)))
}

func isAssign(n Node) (*Construct, bool) {
	c, ok := n.(*Construct)
	return c, ok && c.Name.Token.Value == "Assign"
}

// extractAssigns is _extract_assigns (KPA-L-7).
func extractAssigns(n Node) []*Construct {
	if c, ok := isAssign(n); ok {
		return []*Construct{c}
	}
	if g, ok := n.(*BracketGroup); ok {
		assigns := []*Construct{}
		for _, el := range g.Elements {
			c, ok := isAssign(el)
			if !ok {
				panic(lowerFail("KPOL-LOWER-UNSUPPORTED-CST",
					"Очікувався виклик Assign(Dst, Expr) у блоці підписки.", spanOf(el)))
			}
			assigns = append(assigns, c)
		}
		if len(assigns) == 0 {
			panic(lowerFail("KPOL-LOWER-EMPTY-SUB", "Порожній блок підписки не допускається.", spanOf(n)))
		}
		return assigns
	}
	panic(lowerFail("KPOL-LOWER-UNSUPPORTED-CST",
		"Права частина підписки повинна мати вигляд Assign(Dst, Expr).", spanOf(n)))
}

type rawConcept struct {
	name  string
	init  int64
	flags int
	lower *int64
	upper *int64
}

type pendingSub struct {
	owner, dst, phase, mask int
	words                   []uint32
}

// LowerSource parses src with the default configuration and lowers it
// (lower_document on text).
func LowerSource(src string) (*Artifact, error) {
	return LowerSourceWithConfig(src, DefaultConfig())
}

// LowerSourceWithConfig is LowerSource with an explicit configuration; under
// record-diagnostic policies the lowering fails with KPOL-LOWER-UNCERTAINTY.
func LowerSourceWithConfig(src string, cfg Config) (*Artifact, error) {
	prog, err := Parse(src, cfg)
	if err != nil {
		return nil, err
	}
	return Lower(prog)
}

// Lower lowers a deterministic KPOL-AUTH CST into Do/Go bytecode and a
// CME-RAW-1 BRAM image (lower_kpol_auth, KPA-L-1..15). The error is an *Error
// with a KPOL-LOWER-* code.
func Lower(p *Program) (art *Artifact, err error) {
	defer recoverBailout(&err)
	if p == nil {
		return nil, &Error{Code: "KPOL-LOWER-UNSUPPORTED-CST", Msg: "Програма відсутня (nil)."}
	}
	if len(p.Diagnostics) > 0 {
		first := p.Diagnostics[0]
		panic(lowerFail("KPOL-LOWER-UNCERTAINTY",
			fmt.Sprintf("Присутня незакрита точка невизначеності/діагностика: %s.", first.Code), first.Span))
	}

	var concepts []rawConcept
	conceptByName := map[string]int{}
	var pending []pendingSub

	for _, item := range p.Items {
		switch it := item.(type) {
		case *Construct:
			if it.Name.Token.Value == "Concept" {
				concepts = append(concepts, lowerConcept(it, concepts, conceptByName))
				conceptByName[concepts[len(concepts)-1].name] = len(concepts) - 1
				continue
			}
		case *SubscriptionSeq:
			pending = append(pending, lowerSubscription(it, conceptByName)...)
			continue
		}
		panic(lowerFail("KPOL-LOWER-UNSUPPORTED-CST",
			fmt.Sprintf("Конструкція '%s' не підтримується в lowering.", item.CSTName()), spanOf(item)))
	}

	if len(pending) > MaxSubscriptions {
		panic(lowerFail("KPOL-LOWER-LIMIT", fmt.Sprintf("Перевищено ліміт підписок (%d).", MaxSubscriptions), nil))
	}

	subsByOwner := make([][]pendingSub, len(concepts))
	for _, s := range pending {
		subsByOwner[s.owner] = append(subsByOwner[s.owner], s)
	}

	var code []uint32
	var subs []LoweredSubscription
	lowered := make([]LoweredConcept, 0, len(concepts))
	for cid, c := range concepts {
		owned := subsByOwner[cid]
		first := 0
		if len(owned) > 0 {
			first = len(subs)
		}
		lowered = append(lowered, LoweredConcept{
			CID: cid, Name: c.name, InitVal: c.init, Flags: c.flags,
			LowerBound: c.lower, UpperBound: c.upper,
			FirstSubIdx: first, SubCount: len(owned),
		})
		for _, s := range owned {
			start := len(code)
			code = append(code, s.words...)
			if len(code) > MaxInstructions {
				panic(lowerFail("KPOL-LOWER-LIMIT",
					fmt.Sprintf("Перевищено ліміт інструкцій code_o (%d).", MaxInstructions), nil))
			}
			subs = append(subs, LoweredSubscription{
				SubIdx: len(subs), OwnerCID: s.owner, TargetCID: s.dst,
				Phase: s.phase, TriggerMask: s.mask, LineStartPC: start, LineLen: len(s.words),
			})
		}
	}

	image, err := BuildBRAMRoutingImage(lowered, subs)
	if err != nil {
		return nil, err
	}
	return &Artifact{Concepts: lowered, Subscriptions: subs, codeO: code, bram: image}, nil
}

// lowerConcept checks one Concept(...) declaration (KPA-L-3..5).
func lowerConcept(it *Construct, declared []rawConcept, byName map[string]int) rawConcept {
	els := it.Group.Elements
	var id *Identifier
	if len(els) >= 2 {
		id, _ = els[0].(*Identifier)
	}
	if id == nil {
		panic(lowerFail("KPOL-LOWER-CONCEPT",
			"Concept(...) вимагає (Name, Init[, Lower=..., Upper=...]).", spanOf(it)))
	}
	name := id.Token.Value
	if _, dup := byName[name]; dup {
		panic(lowerFail("KPOL-LOWER-DUPLICATE-CONCEPT", fmt.Sprintf("Повторне оголошення концепту '%s'.", name), spanOf(id)))
	}
	if len(declared) >= MaxConcepts {
		panic(lowerFail("KPOL-LOWER-LIMIT", fmt.Sprintf("Перевищено ліміт концептів (%d).", MaxConcepts), spanOf(it)))
	}
	initVal := int32Literal(els[1])
	var lower, upper *int64
	for _, opt := range els[2:] {
		bin, ok := opt.(*BinaryExpr)
		if !ok || bin.OpToken.Kind != TokEq {
			panic(lowerFail("KPOL-LOWER-CONCEPT", "Непідтримуваний параметр Concept(...).", spanOf(opt)))
		}
		key, ok := bin.Left.(*Identifier)
		if !ok {
			panic(lowerFail("KPOL-LOWER-CONCEPT", "Непідтримуваний параметр Concept(...).", spanOf(opt)))
		}
		switch key.Token.Value {
		case "Lower":
			v := int32Literal(bin.Right)
			lower = &v
		case "Upper":
			v := int32Literal(bin.Right)
			upper = &v
		default:
			panic(lowerFail("KPOL-LOWER-CONCEPT",
				fmt.Sprintf("Невідомий параметр Concept '%s'.", key.Token.Value), spanOf(opt)))
		}
	}
	flags := 0
	if lower != nil || upper != nil {
		flags = FlagHWProtected
	}
	if lower != nil && upper != nil && *lower > *upper {
		panic(lowerFail("KPOL-LOWER-RANGE",
			fmt.Sprintf("Нижня межа (%d) більша за верхню (%d).", *lower, *upper), spanOf(it)))
	}
	return rawConcept{name: name, init: initVal, flags: flags, lower: lower, upper: upper}
}

// lowerSubscription lowers one "S • Assign(...)" item (KPA-L-6..9).
func lowerSubscription(it *SubscriptionSeq, byName map[string]int) []pendingSub {
	var srcName string
	phase, mask := PhasePostChange, EvChanged
	switch left := it.Left.(type) {
	case *Identifier:
		srcName = left.Token.Value
	case *Construct:
		kind := left.Name.Token.Value
		if (kind != "OnAbort" && kind != "OnPositive") || len(left.Group.Elements) != 1 {
			panic(lowerFail("KPOL-LOWER-UNSUPPORTED-CST", subscriptionLeftMsg, spanOf(it.Left)))
		}
		arg, ok := left.Group.Elements[0].(*Identifier)
		if !ok {
			panic(lowerFail("KPOL-LOWER-UNSUPPORTED-CST", subscriptionLeftMsg, spanOf(it.Left)))
		}
		srcName = arg.Token.Value
		if kind == "OnAbort" {
			phase, mask = PhaseOnAbort, EvAlways
		} else {
			mask = EvPositive
		}
	default:
		panic(lowerFail("KPOL-LOWER-UNSUPPORTED-CST", subscriptionLeftMsg, spanOf(it.Left)))
	}

	owner, ok := byName[srcName]
	if !ok {
		panic(lowerFail("KPOL-LOWER-UNKNOWN-CONCEPT",
			fmt.Sprintf("Невідомий концепт-джерело '%s'.", srcName), spanOf(it.Left)))
	}

	var out []pendingSub
	for _, assign := range extractAssigns(it.Right) {
		args := assign.Group.Elements
		var dstID *Identifier
		if len(args) == 2 {
			dstID, _ = args[0].(*Identifier)
		}
		if dstID == nil {
			panic(lowerFail("KPOL-LOWER-ASSIGN",
				"Assign вимагає рівно 2 аргументи: (DstConcept, Expr).", spanOf(assign)))
		}
		dst, ok := byName[dstID.Token.Value]
		if !ok {
			panic(lowerFail("KPOL-LOWER-UNKNOWN-CONCEPT",
				fmt.Sprintf("Невідомий цільовий концепт '%s'.", dstID.Token.Value), spanOf(dstID)))
		}
		var words []uint32
		emitExpr(args[1], byName, &words, 0)
		words = append(words, PackInstr(OpcGo, GoWrite, 0, uint32(dst)), PackInstr(OpcExit, 0, 0, 0))
		out = append(out, pendingSub{owner: owner, dst: dst, phase: phase, mask: mask, words: words})
	}
	return out
}

const subscriptionLeftMsg = "Ліва частина підписки повинна бути Concept, OnPositive(Concept) або OnAbort(Concept)."

// validateBRAMAcyclic is _validate_bram_acyclic (KPA-L-12): no self-loops, no
// cycles (DFS) and the rank order dst > src.
func validateBRAMAcyclic(edges [][2]int) {
	for _, e := range edges {
		src, dst := e[0], e[1]
		if dst == src {
			panic(lowerFail("KPOL-LOWER-CYCLE",
				fmt.Sprintf("Самопетля каскаду BRAM не допускається: dst_cid (%d) == src_cid (%d).", dst, src), nil))
		}
	}

	adj := map[int][]int{}
	nodeSet := map[int]bool{}
	for _, e := range edges {
		adj[e[0]] = append(adj[e[0]], e[1])
		nodeSet[e[0]], nodeSet[e[1]] = true, true
	}
	nodes := make([]int, 0, len(nodeSet))
	for n := range nodeSet {
		nodes = append(nodes, n)
	}
	sort.Ints(nodes)

	state := map[int]int{}
	var dfs func(node int)
	dfs = func(node int) {
		state[node] = 1
		for _, nxt := range adj[node] {
			switch state[nxt] {
			case 1:
				panic(lowerFail("KPOL-LOWER-CYCLE",
					fmt.Sprintf("Цикл у графі каскадів BRAM через концепт C%d (C%d -> C%d).", nxt, node, nxt), nil))
			case 0:
				dfs(nxt)
			}
		}
		state[node] = 2
	}
	for _, n := range nodes {
		if state[n] == 0 {
			dfs(n)
		}
	}

	for _, e := range edges {
		src, dst := e[0], e[1]
		if dst <= src {
			panic(lowerFail("KPOL-LOWER-CYCLE",
				fmt.Sprintf("Порушення ациклічності каскаду BRAM: dst_cid (%d) <= src_cid (%d).", dst, src), nil))
		}
	}
}

// BuildBRAMRoutingImage packs the 1024-byte CME-RAW-1 BRAM routing image after
// the fan-out and acyclicity checks (build_bram_routing_image, KPA-L-11, 12,
// 15). The error is an *Error with a KPOL-LOWER-* code.
func BuildBRAMRoutingImage(concepts []LoweredConcept, subscriptions []LoweredSubscription) (image []byte, err error) {
	defer recoverBailout(&err)
	if len(concepts) > CMESlotCount {
		panic(lowerFail("KPOL-LOWER-LIMIT", fmt.Sprintf("Перевищено ліміт концептів BRAM (%d).", CMESlotCount), nil))
	}
	for _, s := range subscriptions {
		if s.OwnerCID < 0 || s.OwnerCID >= len(concepts) {
			panic(lowerFail("KPOL-LOWER-UNKNOWN-CONCEPT",
				fmt.Sprintf("Невідомий owner_cid (%d) у таблиці підписок.", s.OwnerCID), nil))
		}
		if s.TargetCID < 0 || s.TargetCID >= len(concepts) {
			panic(lowerFail("KPOL-LOWER-UNKNOWN-CONCEPT",
				fmt.Sprintf("Невідомий target_cid (%d) у таблиці підписок.", s.TargetCID), nil))
		}
	}

	var edges [][2]int
	postTarget := map[int]int{}
	for cid, c := range concepts {
		var post []LoweredSubscription
		for _, s := range subscriptions {
			if s.OwnerCID == cid && s.Phase == PhasePostChange {
				post = append(post, s)
			}
		}
		if len(post) > 1 {
			panic(lowerFail("KPOL-LOWER-FANOUT",
				fmt.Sprintf("Концепт C%d ('%s') має %d POST_CHANGE підписок; CME-RAW-1 підтримує fan-out <= 1.",
					cid, c.Name, len(post)), nil))
		}
		if len(post) == 1 {
			edges = append(edges, [2]int{cid, post[0].TargetCID})
			postTarget[cid] = post[0].TargetCID
		}
	}
	validateBRAMAcyclic(edges)

	image = make([]byte, 0, CMEImageBytes)
	for cid := 0; cid < CMESlotCount; cid++ {
		var w [4]uint32
		if cid < len(concepts) {
			c := concepts[cid]
			guard := 0
			if c.Flags&FlagHWProtected != 0 {
				guard = CMEGuardInvariantEN
			}
			if target, ok := postTarget[cid]; ok {
				guard |= CMEGuardSubscriberEN
				w[3] = uint32(target)
			}
			w[0] = uint32(c.InitVal)
			w[2] = uint32(guard&0xFF) << 8
		}
		for _, word := range w {
			image = binary.LittleEndian.AppendUint32(image, word)
		}
	}
	return image, nil
}
