package kpolauth

import (
	"errors"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

// Programs of the KPOL-AUTH programming guide (```kpol-auth blocks).
const (
	guidePages = "Concept(Page, 0)\nConcept(Next, 0)\nPage • Assign(Next, Page + 1)\n"

	guideMarks = `Concept(Mark, 0, Lower=0, Upper=5)
Concept(Count, 0)
Concept(Points, 0)
Concept(Errors, 0)
Concept(Review, 0)

OnPositive(Mark) • Assign(Count, Count + 1)
Count • Assign(Points, Count * 2)
OnAbort(Mark) • {Assign(Errors, Errors + 1), Assign(Review, 1)}
`

	guideSheets = `Concept(Sheet, 0)
Concept(LastPage, 0)
Concept(NextPage, 0)
Sheet • Assign(LastPage, Sheet * 2)
LastPage • Assign(NextPage, LastPage + 1)
`

	thermalGraph = `
Concept(Temp, 20)
Concept(Heater, 10, Lower=10, Upper=80)
Concept(Fan, 0)
Concept(Alarm, 0)
Temp • Assign(Heater, 25 + ((Temp - 20) * 5))
OnPositive(Heater) • Assign(Fan, Heater)
OnAbort(Heater) • Assign(Alarm, 1)
OnAbort(Heater) • Assign(Fan, 100)
`
)

type vmStep struct {
	cid    int
	value  int64
	values []int64
	bigDot []int
}

func runSteps(t *testing.T, src string, steps []vmStep) *Machine {
	t.Helper()
	m := NewMachine(mustLower(t, src))
	for i, s := range steps {
		if err := m.TriggerExternal(s.cid, s.value); err != nil {
			t.Fatalf("step %d: %v", i, err)
		}
		if !equalInts64(m.Values(), s.values) {
			t.Errorf("step %d (%d <- %d): values %v, want %v", i, s.cid, s.value, m.Values(), s.values)
		}
		if s.bigDot != nil && !equalInts(m.BigDotOK(), s.bigDot) {
			t.Errorf("step %d: big dot %v, want %v", i, m.BigDotOK(), s.bigDot)
		}
	}
	return m
}

func TestVMGuidePrograms(t *testing.T) {
	t.Run("pages", func(t *testing.T) {
		runSteps(t, guidePages, []vmStep{{0, 4, []int64{4, 5}, nil}})
	})
	t.Run("marks", func(t *testing.T) {
		runSteps(t, guideMarks, []vmStep{
			{0, 4, []int64{4, 1, 2, 0, 0}, nil},
			{0, 4, []int64{4, 2, 4, 0, 0}, nil},
			{0, 0, []int64{0, 2, 4, 0, 0}, nil},
			{0, 6, []int64{0, 2, 4, 1, 1}, []int{1, 0, 0, 0, 0}},
		})
	})
	t.Run("sheets", func(t *testing.T) {
		runSteps(t, guideSheets, []vmStep{
			{0, 3, []int64{3, 6, 7}, nil},
			{0, 5, []int64{5, 10, 11}, nil},
		})
	})
	t.Run("marks with change trigger", func(t *testing.T) {
		// Guide §7.1: replacing OnPositive(Mark) by Mark makes the repeated 4 a non-event.
		src := strings.Replace(guideMarks, "OnPositive(Mark)", "Mark", 1)
		runSteps(t, src, []vmStep{
			{0, 4, []int64{4, 1, 2, 0, 0}, nil},
			{0, 4, []int64{4, 1, 2, 0, 0}, nil},
			{0, 0, []int64{0, 2, 4, 0, 0}, nil},
		})
	})
	t.Run("guide file blocks", func(t *testing.T) {
		data, err := os.ReadFile(filepath.Join("..", "..", "..", "guides", "kpol-auth-programming-guide.md"))
		if err != nil {
			t.Skipf("guide not available: %v", err)
		}
		blocks := regexp.MustCompile("(?s)```kpol-auth\n(.*?)```").FindAllStringSubmatch(string(data), -1)
		want := []string{guidePages, guideMarks, guideSheets}
		if len(blocks) != len(want) {
			t.Fatalf("guide has %d kpol-auth blocks, want %d", len(blocks), len(want))
		}
		for i, b := range blocks {
			if b[1] != want[i] {
				t.Errorf("block %d differs from the program used in this test", i+1)
			}
			if _, err := LowerSource(b[1]); err != nil {
				t.Errorf("block %d: %v", i+1, err)
			}
		}
	})
}

func TestVMThermalGraph(t *testing.T) {
	m := runSteps(t, thermalGraph, []vmStep{
		{0, 25, []int64{25, 50, 50, 0}, []int{0, 0, 0, 0}},
		{0, 45, []int64{45, 50, 100, 1}, []int{0, 1, 0, 0}},
	})
	if got := m.Previous(); got[0] != 25 {
		t.Errorf("previous values %v", got)
	}
	if len(m.Queue()) != 0 {
		t.Errorf("queue %v", m.Queue())
	}
}

func TestVMEventVector(t *testing.T) {
	art := mustLower(t, "Concept(A, 0)")
	m := NewMachine(art)
	for _, c := range []struct {
		prev, cur int64
		want      int
	}{
		{0, 0, EvAlways | EvNull | EvEven},
		{0, 3, EvAlways | EvPositive | EvUneven | EvChanged},
		{3, 3, EvAlways | EvPositive | EvUneven},
		{3, -4, EvAlways | EvNegative | EvEven | EvChanged},
		{0, -1, EvAlways | EvNegative | EvUneven | EvChanged},
	} {
		m.valPrev[0], m.valCur[0] = c.prev, c.cur
		if got := m.eventVector(0); got != c.want {
			t.Errorf("prev %d cur %d: %#x, want %#x", c.prev, c.cur, got, c.want)
		}
	}
}

func TestVMQueueIntrospectionAndOrder(t *testing.T) {
	m := NewMachine(mustLower(t, guideMarks))
	if err := m.WriteConcept(0, 4); err != nil {
		t.Fatal(err)
	}
	if q := m.Queue(); len(q) != 1 || q[0] != 0 {
		t.Fatalf("queue after write %v", q)
	}
	if got := m.Values(); got[0] != 4 || got[1] != 0 {
		t.Errorf("write alone must not run the cascade: %v", got)
	}
	if err := m.Run(); err != nil {
		t.Fatal(err)
	}
	if got := m.Values(); got[1] != 1 || got[2] != 2 {
		t.Errorf("after Run: %v", got)
	}
	// A rejected write queues the ON_ABORT lines of the owner in sub_idx order.
	if err := m.WriteConcept(0, 6); err != nil {
		t.Fatal(err)
	}
	if q := m.Queue(); len(q) != 2 || q[0] != 1 || q[1] != 2 {
		t.Errorf("abort queue %v", q)
	}
	if bd := m.BigDotOK(); bd[0] != 1 {
		t.Errorf("big dot %v", bd)
	}
}

// TestVMMutantControls mirrors the mutant controls of the reference tests: a
// corrupted opcode or a missing EXIT must be caught.
func TestVMMutantControls(t *testing.T) {
	art := mustLower(t, thermalGraph)
	verify := func(a *Artifact) error {
		m := NewMachine(a)
		if err := m.TriggerExternal(0, 25); err != nil {
			return err
		}
		if got := m.Values(); !equalInts64(got, []int64{25, 50, 50, 0}) {
			return errors.New("wrong state")
		}
		if err := m.TriggerExternal(0, 45); err != nil {
			return err
		}
		if got := m.Values(); !equalInts64(got, []int64{45, 50, 100, 1}) {
			return errors.New("wrong state")
		}
		return nil
	}
	if err := verify(art); err != nil {
		t.Fatalf("unmutated artifact: %v", err)
	}

	index := func(word uint32) int {
		for i, w := range art.codeO {
			if w == word {
				return i
			}
		}
		t.Fatalf("word %08x not found", word)
		return -1
	}
	mutate := func(i int, w uint32) *Artifact {
		c := *art
		c.codeO = append([]uint32(nil), art.codeO...)
		c.codeO[i] = w
		return &c
	}
	if err := verify(mutate(index(PackInstr(OpcDo, DoAdd, 0, 0)), PackInstr(OpcDo, DoSub, 0, 0))); err == nil {
		t.Error("ADD -> SUB mutant survived")
	}
	exit := PackInstr(OpcExit, 0, 0, 0)
	err := verify(mutate(index(exit), PackInstr(OpcNop, 0, 0, 0)))
	var e *Error
	if !errors.As(err, &e) || e.Code != CodeVMOpcode {
		t.Errorf("EXIT -> NOP mutant: %v", err)
	}
	// A line that ends without EXIT is an error, not a silent stop.
	c := *art
	c.Subscriptions = append([]LoweredSubscription(nil), art.Subscriptions...)
	c.Subscriptions[0].LineLen--
	if err := verify(&c); !errors.As(err, &e) || e.Code != CodeVMExit {
		t.Errorf("truncated line: %v", err)
	}
}

func TestVMErrors(t *testing.T) {
	var e *Error

	// D-A10: an abort handler that re-triggers its own abort never terminates in the reference.
	m := NewMachine(mustLower(t, "Concept(A, 5, Lower=10, Upper=20)\nOnAbort(A) • Assign(A, 1)"))
	if err := m.TriggerExternal(0, 3); !errors.As(err, &e) || e.Code != CodeVMSteps {
		t.Errorf("endless cascade: %v", err)
	}
	if len(m.Queue()) != 0 {
		t.Error("the queue must be empty after an error")
	}
	m.StepLimit = 5
	if err := m.TriggerExternal(0, 3); !errors.As(err, &e) || !strings.Contains(e.Msg, "more than 5") {
		t.Errorf("custom step limit: %v", err)
	}
	// A terminating cascade within the limit is unaffected.
	m = NewMachine(mustLower(t, "Concept(A, 5, Lower=10, Upper=20)\nConcept(B, 0)\nOnAbort(A) • Assign(B, 1)"))
	m.StepLimit = 1
	if err := m.TriggerExternal(0, 3); err != nil || m.Values()[1] != 1 {
		t.Errorf("single abort line: %v %v", err, m.Values())
	}

	// Stored values are int64; the arithmetic itself is exact (an intermediate may exceed int64).
	src := "Concept(A, 2147483647)\nConcept(B, 0)\nConcept(C, 0)\nConcept(D, 0)\nConcept(E, 0)\n" +
		"A • Assign(B, A * A)\nB • Assign(C, B * B)\nC • Assign(D, C * C)\nD • Assign(E, D * D)"
	m = NewMachine(mustLower(t, src))
	if err := m.TriggerExternal(0, 2147483646); !errors.As(err, &e) || e.Code != CodeVMOverflow {
		t.Errorf("overflow: %v", err)
	}
	exact := "Concept(A, 2147483647)\nConcept(B, 0)\nA • Assign(B, (A * A * A) - (A * A * A) + 7)"
	m = NewMachine(mustLower(t, exact))
	if err := m.TriggerExternal(0, 2147483646); err != nil || m.Values()[1] != 7 {
		t.Errorf("exact intermediate arithmetic: %v %v", err, m.Values())
	}
	// A value rejected by the guard is never stored, so it cannot overflow.
	m = NewMachine(mustLower(t, "Concept(A, 0, Lower=0, Upper=5)"))
	if err := m.TriggerExternal(0, 1<<62); err != nil || m.BigDotOK()[0] != 1 {
		t.Errorf("rejected huge value: %v", err)
	}

	// Index errors.
	m = NewMachine(mustLower(t, "Concept(A, 0)"))
	for _, cid := range []int{-1, 1, 64} {
		if err := m.TriggerExternal(cid, 1); !errors.As(err, &e) || e.Code != CodeVMIndex {
			t.Errorf("cid %d: %v", cid, err)
		}
	}
	if err := NewMachine(mustLower(t, "")).TriggerExternal(0, 1); !errors.As(err, &e) || e.Code != CodeVMIndex {
		t.Errorf("empty machine: %v", err)
	}
}

func TestVMCorruptArtifacts(t *testing.T) {
	art := mustLower(t, guidePages)
	var e *Error
	corrupt := func(mod func(a *Artifact)) error {
		c := *art
		c.codeO = append([]uint32(nil), art.codeO...)
		c.Subscriptions = append([]LoweredSubscription(nil), art.Subscriptions...)
		c.Concepts = append([]LoweredConcept(nil), art.Concepts...)
		mod(&c)
		return NewMachine(&c).TriggerExternal(0, 1)
	}
	for name, tc := range map[string]struct {
		mod  func(a *Artifact)
		code string
	}{
		"stack underflow":     {func(a *Artifact) { a.codeO[0] = PackInstr(OpcDo, DoAdd, 0, 0) }, CodeVMStack},
		"write underflow":     {func(a *Artifact) { a.codeO[0] = PackInstr(OpcGo, GoWrite, 0, 1) }, CodeVMStack},
		"bad do sub-op":       {func(a *Artifact) { a.codeO[2] = PackInstr(OpcDo, 9, 0, 0) }, CodeVMOpcode},
		"bad go sub-op":       {func(a *Artifact) { a.codeO[0] = PackInstr(OpcGo, GoExec, 0, 0) }, CodeVMOpcode},
		"bad opcode":          {func(a *Artifact) { a.codeO[0] = PackInstr(0xF, 0, 0, 0) }, CodeVMOpcode},
		"read out of range":   {func(a *Artifact) { a.codeO[0] = PackInstr(OpcGo, GoRead, 0, 9) }, CodeVMIndex},
		"write out of range":  {func(a *Artifact) { a.codeO[3] = PackInstr(OpcGo, GoWrite, 0, 9) }, CodeVMIndex},
		"pc out of range":     {func(a *Artifact) { a.Subscriptions[0].LineStartPC = 100 }, CodeVMIndex},
		"sub range":           {func(a *Artifact) { a.Concepts[0].SubCount = 9 }, CodeVMIndex},
		"negative first":      {func(a *Artifact) { a.Concepts[0].FirstSubIdx = -1 }, CodeVMIndex},
		"truncated line":      {func(a *Artifact) { a.Subscriptions[0].LineLen = 2 }, CodeVMExit},
		"zero length line":    {func(a *Artifact) { a.Subscriptions[0].LineLen = 0 }, CodeVMExit},
		"imm sign extension":  {func(a *Artifact) { a.codeO[1] = PackInstr(OpcImm, 0, 0, 0x8000) }, ""},
		"exit stops the line": {func(a *Artifact) { a.codeO[1] = PackInstr(OpcExit, 0, 0, 0) }, ""},
	} {
		err := corrupt(tc.mod)
		if tc.code == "" {
			if err != nil {
				t.Errorf("%s: %v", name, err)
			}
			continue
		}
		if !errors.As(err, &e) || e.Code != tc.code {
			t.Errorf("%s: %v, want %s", name, err, tc.code)
		}
	}
	// IMM operands are sign-extended 16-bit values.
	m := NewMachine(mustLower(t, "Concept(A, 0)\nConcept(B, 0)\nA • Assign(B, 0 - 5 + A)"))
	if err := m.TriggerExternal(0, 1); err != nil || m.Values()[1] != -4 {
		t.Errorf("0 - 5 + A: %v %v", err, m.Values())
	}
	art2 := mustLower(t, "Concept(A, 0)\nConcept(B, 0)\nA • Assign(B, 32767)")
	art2.codeO[0] = PackInstr(OpcImm, 0, 0, 0xFFFF)
	m = NewMachine(art2)
	if err := m.TriggerExternal(0, 1); err != nil || m.Values()[1] != -1 {
		t.Errorf("IMM 0xFFFF: %v %v", err, m.Values())
	}
}
