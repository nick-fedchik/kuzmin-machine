package kpolauth

import (
	"errors"
	"fmt"
	"strings"
	"testing"
)

func TestPackInstr(t *testing.T) {
	cases := []struct {
		opc, sub, flags, operand, want uint32
	}{
		{OpcImm, 0, 0, 1, 0x30000001},
		{OpcGo, GoRead, 0, 7, 0x12000007},
		{OpcGo, GoWrite, 0, 3, 0x11000003},
		{OpcDo, DoSub, 0, 0, 0x21000000},
		{OpcExit, 0, 0, 0, 0x50000000},
		{0x1F, 0x1F, 0x1FF, 0x1FFFF, 0xFFFFFFFF}, // every field truncated to its width
		{OpcImm, 0, 0, 0xFFFF, 0x3000FFFF},
		{OpcNop, 0, 0xAB, 0, 0x00AB0000},
	}
	for _, c := range cases {
		if got := PackInstr(c.opc, c.sub, c.flags, c.operand); got != c.want {
			t.Errorf("PackInstr(%x,%x,%x,%x) = %08x, want %08x", c.opc, c.sub, c.flags, c.operand, got, c.want)
		}
	}
}

func TestLoweringTables(t *testing.T) {
	// Subscriptions are grouped by owner in CID order, text order inside an owner.
	art := mustLower(t, `
Concept(A, 1)
Concept(B, 2, Lower=0)
Concept(C, 3, Upper=9)
Concept(D, 4)
OnAbort(C) • Assign(D, 7)
B • Assign(C, B + 1)
OnAbort(B) • {Assign(A, 5), Assign(D, 6)}
`)
	wantConcepts := []LoweredConcept{
		{CID: 0, Name: "A", InitVal: 1},
		{CID: 1, Name: "B", InitVal: 2, Flags: FlagHWProtected, LowerBound: ptr(0), FirstSubIdx: 0, SubCount: 3},
		{CID: 2, Name: "C", InitVal: 3, Flags: FlagHWProtected, UpperBound: ptr(9), FirstSubIdx: 3, SubCount: 1},
		{CID: 3, Name: "D", InitVal: 4},
	}
	for i, w := range wantConcepts {
		g := art.Concepts[i]
		if g.CID != w.CID || g.Name != w.Name || g.InitVal != w.InitVal || g.Flags != w.Flags ||
			g.FirstSubIdx != w.FirstSubIdx || g.SubCount != w.SubCount ||
			!equalPtr(g.LowerBound, w.LowerBound) || !equalPtr(g.UpperBound, w.UpperBound) {
			t.Errorf("concept %d = %+v, want %+v", i, g, w)
		}
	}
	// Owner B has the POST_CHANGE line (text line 2) first? No: text order inside the owner.
	wantSubs := []LoweredSubscription{
		{0, 1, 2, PhasePostChange, EvChanged, 0, 5},
		{1, 1, 0, PhaseOnAbort, EvAlways, 5, 3},
		{2, 1, 3, PhaseOnAbort, EvAlways, 8, 3},
		{3, 2, 3, PhaseOnAbort, EvAlways, 11, 3},
	}
	if len(art.Subscriptions) != len(wantSubs) {
		t.Fatalf("%d subscriptions", len(art.Subscriptions))
	}
	for i, w := range wantSubs {
		if art.Subscriptions[i] != w {
			t.Errorf("subscription %d = %+v, want %+v", i, art.Subscriptions[i], w)
		}
	}
	if got := art.CodeO(); len(got) != 14 {
		t.Errorf("%d words", len(got))
	}

	// Accessors return copies.
	art.CodeO()[0] = 0
	art.BRAMImage()[0] = 0xFF
	if art.CodeO()[0] == 0 || art.BRAMImage()[0] == 0xFF {
		t.Error("accessors must copy")
	}
}

func ptr(v int64) *int64 { return &v }

func equalPtr(a, b *int64) bool {
	if a == nil || b == nil {
		return a == b
	}
	return *a == *b
}

// TestImageLayout checks KPA-L-15 and D-A8: W2/W3, no bounds, triggers or code in the image.
func TestImageLayout(t *testing.T) {
	art := mustLower(t, `
Concept(A, 7)
Concept(B, 0, Lower=1)
Concept(C, 0)
A • Assign(B, A)
OnPositive(B) • Assign(C, B)
OnAbort(B) • Assign(A, 1)
`)
	img := art.BRAMImage()
	word := func(slot, w int) uint32 {
		o := slot*16 + w*4
		return uint32(img[o]) | uint32(img[o+1])<<8 | uint32(img[o+2])<<16 | uint32(img[o+3])<<24
	}
	want := [][4]uint32{
		{7, 0, 0x1000, 1}, // A: subscriber guard, edge A -> B
		{0, 0, 0x1200, 2}, // B: HW_PROTECTED | subscriber, edge B -> C (OnPositive); ON_ABORT is not in the image
		{0, 0, 0, 0},      // C: leaf
	}
	for slot, w := range want {
		for i := range w {
			if got := word(slot, i); got != w[i] {
				t.Errorf("slot %d W%d = %#x, want %#x", slot, i, got, w[i])
			}
		}
	}
	for slot := 3; slot < CMESlotCount; slot++ {
		for i := 0; i < 4; i++ {
			if word(slot, i) != 0 {
				t.Fatalf("slot %d must be zero", slot)
			}
		}
	}
	// A guard bound changes nothing in the image.
	other := mustLower(t, "Concept(A, 7)\nConcept(B, 0, Lower=5, Upper=6)\nConcept(C, 0)\nA • Assign(B, A)\nOnPositive(B) • Assign(C, B)\nOnAbort(B) • Assign(A, 1)")
	if string(other.BRAMImage()) != string(img) {
		t.Error("Lower/Upper values must not reach the image (D-A8)")
	}
}

func TestBuildBRAMRoutingImageDirect(t *testing.T) {
	c0 := LoweredConcept{CID: 0, Name: "C0", InitVal: 7, SubCount: 1}
	c1 := LoweredConcept{CID: 1, Name: "C1", InitVal: -1}
	post := LoweredSubscription{SubIdx: 0, OwnerCID: 0, TargetCID: 1, Phase: PhasePostChange, TriggerMask: EvChanged, LineLen: 3}
	abortSelf := LoweredSubscription{SubIdx: 1, OwnerCID: 0, TargetCID: 0, Phase: PhaseOnAbort, TriggerMask: EvAlways, LineStartPC: 3, LineLen: 3}

	img, err := BuildBRAMRoutingImage([]LoweredConcept{c0, c1}, []LoweredSubscription{post, abortSelf})
	if err != nil || len(img) != CMEImageBytes {
		t.Fatalf("positive control: %v (%d bytes)", err, len(img))
	}
	if img[0] != 7 || img[9] != 0x10 || img[12] != 1 {
		t.Errorf("slot 0 = % x", img[0:16])
	}
	if got := img[16:20]; got[0] != 0xFF || got[3] != 0xFF { // init -1 is two's complement
		t.Errorf("slot 1 W0 = % x", got)
	}

	for _, cid := range []int{0, 1} {
		self := LoweredSubscription{OwnerCID: cid, TargetCID: cid, Phase: PhasePostChange, TriggerMask: EvChanged, LineLen: 3}
		if _, err := BuildBRAMRoutingImage([]LoweredConcept{c0, c1}, []LoweredSubscription{self}); firstCode(err) != "KPOL-LOWER-CYCLE" {
			t.Errorf("self-loop on %d: %v", cid, err)
		}
	}
	if _, err := BuildBRAMRoutingImage([]LoweredConcept{c0, c1},
		[]LoweredSubscription{{OwnerCID: 5, TargetCID: 0, Phase: PhasePostChange}}); firstCode(err) != "KPOL-LOWER-UNKNOWN-CONCEPT" ||
		!strings.Contains(err.Error(), "owner_cid (5)") {
		t.Errorf("unknown owner: %v", err)
	}
	if _, err := BuildBRAMRoutingImage([]LoweredConcept{c0, c1},
		[]LoweredSubscription{{OwnerCID: 0, TargetCID: -1, Phase: PhasePostChange}}); firstCode(err) != "KPOL-LOWER-UNKNOWN-CONCEPT" ||
		!strings.Contains(err.Error(), "target_cid (-1)") {
		t.Errorf("unknown target: %v", err)
	}
	if _, err := BuildBRAMRoutingImage(make([]LoweredConcept, 65), nil); firstCode(err) != "KPOL-LOWER-LIMIT" {
		t.Errorf("65 concepts: %v", err)
	}
	two := []LoweredSubscription{post, {SubIdx: 1, OwnerCID: 0, TargetCID: 1, Phase: PhasePostChange}}
	if _, err := BuildBRAMRoutingImage([]LoweredConcept{c0, c1}, two); firstCode(err) != "KPOL-LOWER-FANOUT" {
		t.Errorf("fan-out: %v", err)
	}
	// Two-node cycle: the rank check (and the DFS) reject it.
	back := LoweredSubscription{SubIdx: 1, OwnerCID: 1, TargetCID: 0, Phase: PhasePostChange}
	if _, err := BuildBRAMRoutingImage([]LoweredConcept{c0, c1}, []LoweredSubscription{post, back}); firstCode(err) != "KPOL-LOWER-CYCLE" {
		t.Errorf("2-cycle: %v", err)
	}
}

// TestValidateBRAMAcyclic isolates the three checks of KPA-L-12 and their order.
func TestValidateBRAMAcyclic(t *testing.T) {
	check := func(edges [][2]int) (msg string) {
		defer func() {
			if r := recover(); r != nil {
				msg = r.(bailout).err.Msg
			}
		}()
		validateBRAMAcyclic(edges)
		return ""
	}
	if got := check([][2]int{{0, 1}, {1, 2}, {3, 5}}); got != "" {
		t.Errorf("acyclic graph rejected: %s", got)
	}
	if got := check([][2]int{{0, 1}, {1, 2}, {2, 0}}); got != "Цикл у графі каскадів BRAM через концепт C0 (C2 -> C0)." {
		t.Errorf("3-cycle: %q", got)
	}
	if got := check([][2]int{{1, 0}}); got != "Порушення ациклічності каскаду BRAM: dst_cid (0) <= src_cid (1)." {
		t.Errorf("rank: %q", got)
	}
	// Self-loops are reported before any cycle or rank violation.
	if got := check([][2]int{{2, 1}, {1, 2}, {4, 4}}); got != "Самопетля каскаду BRAM не допускається: dst_cid (4) == src_cid (4)." {
		t.Errorf("self-loop first: %q", got)
	}
}

// TestLoweringDiagnostics: a negative control for every KPOL-LOWER-* code, with
// the message text of the reference.
func TestLoweringDiagnostics(t *testing.T) {
	pre := "Concept(A, 0)\nConcept(B, 0)\n"
	manyAborts := func(n int, expr string) string {
		return pre + strings.Repeat("OnAbort(A) • Assign(B, "+expr+")\n", n)
	}
	var sixtyFive strings.Builder
	for i := 0; i < 65; i++ {
		fmt.Fprintf(&sixtyFive, "Concept(C%d, 0)\n", i)
	}
	cases := []struct {
		name, src, code, msg string
	}{
		{"uncertainty (via record)", "", "KPOL-LOWER-UNCERTAINTY", ""}, // see TestLowerUncertainty
		{"unsupported toplevel", `A`, "KPOL-LOWER-UNSUPPORTED-CST", "Конструкція 'IdentifierCST' не підтримується в lowering."},
		{"def layout", `Def(1, 0, 1, 0, 0, 0, 0)`, "KPOL-LOWER-UNSUPPORTED-CST", "Конструкція 'DefLayoutCST' не підтримується в lowering."},
		{"other construct", `Foo(A)`, "KPOL-LOWER-UNSUPPORTED-CST", "Конструкція 'CallOrConstructCST' не підтримується в lowering."},
		{"bounded concept", `Concept(A, 0)[Min=1]`, "KPOL-LOWER-UNSUPPORTED-CST", "Конструкція 'GroupBoundsCST' не підтримується в lowering."},
		{"assignment item", `A := 1`, "KPOL-LOWER-UNSUPPORTED-CST", "Конструкція 'AssignmentCST' не підтримується в lowering."},
		{"left is subscription", pre + `A • B • Assign(A, 1)`, "KPOL-LOWER-UNSUPPORTED-CST", subscriptionLeftMsg},
		{"left unknown construct", pre + `Foo(A) • Assign(B, 1)`, "KPOL-LOWER-UNSUPPORTED-CST", subscriptionLeftMsg},
		{"left two args", pre + `OnAbort(A, B) • Assign(B, 1)`, "KPOL-LOWER-UNSUPPORTED-CST", subscriptionLeftMsg},
		{"left literal arg", pre + `OnAbort(1) • Assign(B, 1)`, "KPOL-LOWER-UNSUPPORTED-CST", subscriptionLeftMsg},
		{"left literal", pre + `1 • Assign(B, 1)`, "KPOL-LOWER-UNSUPPORTED-CST", subscriptionLeftMsg},
		{"right not assign", pre + `A • B`, "KPOL-LOWER-UNSUPPORTED-CST", "Права частина підписки повинна мати вигляд Assign(Dst, Expr)."},
		{"right other call", pre + `A • Foo(B, 1)`, "KPOL-LOWER-UNSUPPORTED-CST", "Права частина підписки повинна мати вигляд Assign(Dst, Expr)."},
		{"right binary", pre + `A • Assign(B, 1) + 1`, "KPOL-LOWER-UNSUPPORTED-CST", "Права частина підписки повинна мати вигляд Assign(Dst, Expr)."},
		{"group with non-assign", pre + `OnAbort(A) • {Assign(B, 1), B}`, "KPOL-LOWER-UNSUPPORTED-CST", "Очікувався виклик Assign(Dst, Expr) у блоці підписки."},
		{"expression string", pre + `A • Assign(B, "x")`, "KPOL-LOWER-UNSUPPORTED-CST", "Конструкція 'LiteralCST' поза детермінованою підмножиною виразів."},
		{"expression brace group", pre + `A • Assign(B, {A})`, "KPOL-LOWER-UNSUPPORTED-CST", "Конструкція 'BracketGroupCST' поза детермінованою підмножиною виразів."},
		{"expression uninit", pre + `A • Assign(B, _)`, "KPOL-LOWER-UNSUPPORTED-CST", "Конструкція 'UninitCST' поза детермінованою підмножиною виразів."},
		{"expression call", pre + `A • Assign(B, F(1))`, "KPOL-LOWER-UNSUPPORTED-CST", "Конструкція 'CallOrConstructCST' поза детермінованою підмножиною виразів."},
		{"concept short", `Concept(A)`, "KPOL-LOWER-CONCEPT", "Concept(...) вимагає (Name, Init[, Lower=..., Upper=...])."},
		{"concept bare", `Concept()`, "KPOL-LOWER-CONCEPT", "Concept(...) вимагає (Name, Init[, Lower=..., Upper=...])."},
		{"concept name literal", `Concept(1, 2)`, "KPOL-LOWER-CONCEPT", "Concept(...) вимагає (Name, Init[, Lower=..., Upper=...])."},
		{"concept bad option", `Concept(A, 0, 5)`, "KPOL-LOWER-CONCEPT", "Непідтримуваний параметр Concept(...)."},
		{"concept option op", `Concept(A, 0, Lower<1)`, "KPOL-LOWER-CONCEPT", "Непідтримуваний параметр Concept(...)."},
		{"concept option key", `Concept(A, 0, "x"=1)`, "KPOL-LOWER-CONCEPT", "Непідтримуваний параметр Concept(...)."},
		{"concept unknown option", `Concept(A, 0, Step=1)`, "KPOL-LOWER-CONCEPT", "Невідомий параметр Concept 'Step'."},
		{"literal init", `Concept(A, B)`, "KPOL-LOWER-LITERAL", "Очікувався цілочисельний літерал."},
		{"literal text init", `Concept(A, "0")`, "KPOL-LOWER-LITERAL", "Очікувався цілочисельний літерал."},
		{"literal bound", `Concept(A, 0, Lower=X)`, "KPOL-LOWER-LITERAL", "Очікувався цілочисельний літерал."},
		{"duplicate", `Concept(A, 0) Concept(A, 1)`, "KPOL-LOWER-DUPLICATE-CONCEPT", "Повторне оголошення концепту 'A'."},
		{"too many concepts", sixtyFive.String(), "KPOL-LOWER-LIMIT", "Перевищено ліміт концептів (64)."},
		{"too many subscriptions", manyAborts(129, "1"), "KPOL-LOWER-LIMIT", "Перевищено ліміт підписок (128)."},
		{"too many words", manyAborts(47, "1 + 1 + 1 + 1 + 1"), "KPOL-LOWER-LIMIT", "Перевищено ліміт інструкцій code_o (512)."},
		{"init range", `Concept(A, 2147483648)`, "KPOL-LOWER-RANGE", "Значення 2147483648 виходить за межі Int32."},
		{"bound range", `Concept(A, 0, Upper=99999999999)`, "KPOL-LOWER-RANGE", "Значення 99999999999 виходить за межі Int32."},
		{"lower above upper", `Concept(A, 0, Lower=5, Upper=4)`, "KPOL-LOWER-RANGE", "Нижня межа (5) більша за верхню (4)."},
		{"imm range", pre + `A • Assign(B, 32768)`, "KPOL-LOWER-RANGE", "Константа 32768 не вміщується у 16-бітний знаковий операнд KM_OPC_IMM."},
		{"unknown source", `Concept(A, 0) X • Assign(A, 1)`, "KPOL-LOWER-UNKNOWN-CONCEPT", "Невідомий концепт-джерело 'X'."},
		{"unknown target", pre + `A • Assign(X, 1)`, "KPOL-LOWER-UNKNOWN-CONCEPT", "Невідомий цільовий концепт 'X'."},
		{"unknown in expr", pre + `A • Assign(B, X + 1)`, "KPOL-LOWER-UNKNOWN-CONCEPT", "Невідомий концепт 'X' у виразі."},
		{"declared later", `Concept(A, 0) A • Assign(B, 1) Concept(B, 0)`, "KPOL-LOWER-UNKNOWN-CONCEPT", "Невідомий цільовий концепт 'B'."},
		{"empty block", pre + `A • {}`, "KPOL-LOWER-EMPTY-SUB", "Порожній блок підписки не допускається."},
		{"assign one arg", pre + `A • Assign(B)`, "KPOL-LOWER-ASSIGN", "Assign вимагає рівно 2 аргументи: (DstConcept, Expr)."},
		{"assign three args", pre + `A • Assign(B, 1, 2)`, "KPOL-LOWER-ASSIGN", "Assign вимагає рівно 2 аргументи: (DstConcept, Expr)."},
		{"assign literal target", pre + `A • Assign(1, 2)`, "KPOL-LOWER-ASSIGN", "Assign вимагає рівно 2 аргументи: (DstConcept, Expr)."},
		{"paren two elements", pre + `A • Assign(B, (1, 2))`, "KPOL-LOWER-EXPR", "Дужковий вираз повинен містити рівно один елемент."},
		{"paren empty", pre + `A • Assign(B, ())`, "KPOL-LOWER-EXPR", "Дужковий вираз повинен містити рівно один елемент."},
		{"division", pre + `A • Assign(B, A / 2)`, "KPOL-LOWER-UNSUPPORTED-OP", "Оператор '/' не підтримується в Do/Go lowering."},
		{"operator before operands", pre + `A • Assign(B, X / Y)`, "KPOL-LOWER-UNSUPPORTED-OP", "Оператор '/' не підтримується в Do/Go lowering."},
		{"comparison", pre + `A • Assign(B, A < 2)`, "KPOL-LOWER-UNSUPPORTED-OP", "Оператор '<' не підтримується в Do/Go lowering."},
		{"colon", pre + `A • Assign(B, A : 2)`, "KPOL-LOWER-UNSUPPORTED-OP", "Оператор ':' не підтримується в Do/Go lowering."},
		{"fanout", pre + `Concept(C, 0)` + "\nA • Assign(B, 1)\nA • Assign(C, 2)", "KPOL-LOWER-FANOUT", "Концепт C0 ('A') має 2 POST_CHANGE підписок; CME-RAW-1 підтримує fan-out <= 1."},
		{"fanout via OnPositive", pre + "Concept(C, 0)\nA • Assign(B, 1)\nOnPositive(A) • Assign(C, 1)", "KPOL-LOWER-FANOUT", ""},
		{"group fanout", pre + "Concept(C, 0)\nA • {Assign(B, 1), Assign(C, 2)}", "KPOL-LOWER-FANOUT", ""},
		{"self loop", `Concept(A, 0) A • Assign(A, 1)`, "KPOL-LOWER-CYCLE", "Самопетля каскаду BRAM не допускається: dst_cid (0) == src_cid (0)."},
		{"backwards edge", pre + `B • Assign(A, 1)`, "KPOL-LOWER-CYCLE", "Порушення ациклічності каскаду BRAM: dst_cid (0) <= src_cid (1)."},
		{"three cycle", pre + "Concept(C, 0)\nA • Assign(B, 1)\nB • Assign(C, 1)\nC • Assign(A, 1)", "KPOL-LOWER-CYCLE", "Цикл у графі каскадів BRAM через концепт C0 (C2 -> C0)."},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if c.code == "KPOL-LOWER-UNCERTAINTY" {
				t.Skip("covered by TestLowerUncertainty")
			}
			_, err := LowerSource(c.src)
			var e *Error
			if !errors.As(err, &e) || e.Code != c.code {
				t.Fatalf("got %v, want %s", err, c.code)
			}
			if c.msg != "" && e.Msg != c.msg {
				t.Errorf("message %q, want %q", e.Msg, c.msg)
			}
		})
	}
}

func TestLowerUncertainty(t *testing.T) {
	prog, err := Parse("#legacy", RecordAllConfig())
	if err != nil {
		t.Fatal(err)
	}
	_, err = Lower(prog)
	var e *Error
	if !errors.As(err, &e) || e.Code != "KPOL-LOWER-UNCERTAINTY" ||
		e.Msg != "Присутня незакрита точка невизначеності/діагностика: KPOL-AUTH-U05." || e.Span == nil {
		t.Errorf("Lower: %v", err)
	}
	if _, err := LowerSourceWithConfig("Concept(A, 0)", RecordAllConfig()); err != nil {
		t.Errorf("clean program under record-diagnostic must lower: %v", err)
	}
	if _, err := Lower(nil); err == nil {
		t.Error("Lower(nil) must fail")
	}
}

// TestLoweringAcceptedForms documents behaviour of the reference that the
// specification lists as decisions (D-A5, D-A7, D-A10, D-A14) and valid limits.
func TestLoweringAcceptedForms(t *testing.T) {
	for name, src := range map[string]string{
		"D-A7 braces and commas":        `Concept{A, 0} Concept(B 0) Concept{C 1, Lower=0}`,
		"D-A10 abort self-assign":       `Concept(A, 0, Lower=1) OnAbort(A) • Assign(A, 1)`,
		"D-A10 abort cycle":             "Concept(A, 0)\nConcept(B, 0)\nOnAbort(A) • Assign(B, 1)\nOnAbort(B) • Assign(A, 1)",
		"array group of assigns":        "Concept(A, 0)\nConcept(B, 0)\nOnAbort(A) • [Assign(B, 1)]",
		"nested parentheses":            "Concept(A, 0)\nConcept(B, 0)\nA • Assign(B, (((A))))",
		"int32 bounds":                  `Concept(A, 2147483647, Lower=2147483647, Upper=2147483647)`,
		"imm bounds":                    "Concept(A, 0)\nConcept(B, 0)\nA • Assign(B, 32767)",
		"64 concepts":                   manyConcepts(64),
		"128 subscriptions":             "Concept(A, 0)\nConcept(B, 0)\n" + strings.Repeat("OnAbort(A) • Assign(B, 1)\n", 128),
		"unicode decimal digits":        "Concept(A, ٣)\nConcept(B, 0)\nA • Assign(B, ٣٣ + A)",
		"one-sided bounds":              `Concept(A, 0, Upper=5) Concept(B, 0, Lower=0)`,
		"repeated bound last one wins":  `Concept(A, 0, Lower=9, Lower=1, Upper=3)`,
		"empty program":                 ``,
		"whitespace only":               " \n\t",
		"same-name subscription target": "Concept(A, 0)\nConcept(B, 0)\nA • Assign(B, B + A)",
	} {
		if _, err := LowerSource(src); err != nil {
			t.Errorf("%s: %v", name, err)
		}
	}
	// 512 words exactly (46 lines of 11 words, 2 of 3), 513 is rejected (Annex limit KPA-L-10).
	line := func(expr string) string { return "OnAbort(A) • Assign(B, " + expr + ")\n" }
	base := "Concept(A, 0)\nConcept(B, 0)\n"
	src512 := base + strings.Repeat(line("1 + 1 + 1 + 1 + 1"), 46) + line("1") + line("1")
	if art := mustLower(t, src512); len(art.CodeO()) != MaxInstructions {
		t.Errorf("%d words", len(art.CodeO()))
	}
	if _, err := LowerSource(base + strings.Repeat(line("1 + 1 + 1 + 1 + 1"), 46) + line("1 + 1 + 1")); firstCode(err) != "KPOL-LOWER-LIMIT" {
		t.Errorf("513 words: %v", err)
	}
	// Parenthesised expressions flatten, the translation is left-to-right (KPA-SYN-3, KPA-L-14).
	art := mustLower(t, "Concept(A, 4)\nConcept(B, 0)\nA • Assign(B, A + 1 * 2)")
	if got := wordsHex(art.CodeO()); got != "12000000 30000001 20000000 30000002 22000000 11000001 50000000" {
		t.Errorf("A + 1 * 2 = %s", got)
	}
}

func manyConcepts(n int) string {
	var b strings.Builder
	for i := 0; i < n; i++ {
		fmt.Fprintf(&b, "Concept(C%d, %d)\n", i, i)
	}
	return b.String()
}

func TestLoweringNonDecimalDigit(t *testing.T) {
	// D-A1: the reference raises ValueError here; the Go port returns an error.
	for _, src := range []string{
		"Concept(A, ²)",
		"Concept(A, 0)\nConcept(B, 0)\nA • Assign(B, ²)",
		"Concept(A, 0, Lower=①)",
	} {
		_, err := LowerSource(src)
		var e *Error
		if !errors.As(err, &e) || e.Code != CodeLowerNonDecimalDigit {
			t.Errorf("%q: %v", src, err)
		}
	}
}

func TestDoGoJSONLayout(t *testing.T) {
	art := mustLower(t, "Concept(A, 0)\nConcept(B, 0, Upper=9)\nA • Assign(B, A + 1)")
	got, err := art.DoGoJSON()
	if err != nil {
		t.Fatal(err)
	}
	want := `{
  "format": "kpol-auth-dogo-0.1.0",
  "concepts": [
    {
      "cid": 0,
      "name": "A",
      "init_val": 0,
      "flags": 0,
      "lower_bound": null,
      "upper_bound": null,
      "first_sub_idx": 0,
      "sub_count": 1
    },
    {
      "cid": 1,
      "name": "B",
      "init_val": 0,
      "flags": 8,
      "lower_bound": null,
      "upper_bound": 9,
      "first_sub_idx": 0,
      "sub_count": 0
    }
  ],
  "subscriptions": [
    {
      "sub_idx": 0,
      "owner_cid": 0,
      "target_cid": 1,
      "phase": 1,
      "trigger_mask": 64,
      "line_start_pc": 0,
      "line_len": 5
    }
  ],
  "code_o": [
    301989888,
    805306369,
    536870912,
    285212673,
    1342177280
  ],
  "code_o_hex": [
    "0x12000000",
    "0x30000001",
    "0x20000000",
    "0x11000001",
    "0x50000000"
  ]
}
`
	if string(got) != want {
		t.Errorf("DoGoJSON\n got: %s\nwant: %s", got, want)
	}

	empty := mustLower(t, "")
	doc, _ := empty.DoGoJSON()
	wantEmpty := "{\n  \"format\": \"kpol-auth-dogo-0.1.0\",\n  \"concepts\": [],\n  \"subscriptions\": [],\n  \"code_o\": [],\n  \"code_o_hex\": []\n}\n"
	if string(doc) != wantEmpty {
		t.Errorf("empty artifact: %q", doc)
	}
	var nilArt *Artifact
	if _, err := nilArt.DoGoJSON(); err == nil {
		t.Error("nil artifact must fail")
	}
	if got := wordsHex(mustLower(t, "Concept(A, 0)\nConcept(B, 0)\nA • Assign(B, A + 1)").CodeO()); got != "12000000 30000001 20000000 11000001 50000000" {
		t.Errorf("words %s", got)
	}
	bin := art.DoGoBinary()
	if len(bin) != 20 || bin[0] != 0x00 || bin[3] != 0x12 {
		t.Errorf("binary form % x", bin)
	}
}

func TestLoweringDeepExpression(t *testing.T) {
	chain := func(terms int) string {
		return "Concept(A, 0)\nConcept(B, 0)\nA • Assign(B, " + strings.Repeat("1 + ", terms-1) + "1)"
	}
	// 255 operators need 511+2 words: over the word limit, but not "deep".
	_, err := LowerSource(chain(256))
	var e *Error
	if !errors.As(err, &e) || e.Code != "KPOL-LOWER-LIMIT" || !strings.Contains(e.Msg, "code_o") {
		t.Errorf("256 terms: %v", err)
	}
	if _, err := LowerSource(chain(255)); err != nil {
		t.Errorf("255 terms (511 words + 2): %v", err)
	}
	// Absurd depth is an error, not a stack overflow.
	_, err = LowerSource(chain(200000))
	if !errors.As(err, &e) || e.Code != "KPOL-LOWER-LIMIT" || !strings.Contains(e.Msg, "глибину") {
		t.Errorf("200000 terms: %v", err)
	}
}
