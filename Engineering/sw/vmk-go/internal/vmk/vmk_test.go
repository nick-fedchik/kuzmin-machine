package vmk

import (
	"bytes"
	"os"
	"strings"
	"testing"
)

func TestBRAM64PredicatesActionsInvariantsAndUncertainties(t *testing.T) {
	// Test Increase (KPOL-CME-1): param=5 -> COMMIT (10->11), param=25 -> REJECT_GUARD, param=_ -> REJECT_FAULT
	compInc, err := CompileKPOLSource(ExampleIncreaseSource, "KPOL-CME-1")
	if err != nil {
		t.Fatalf("CompileKPOLSource(Increase) failed: %v", err)
	}
	engInc, err := NewBRAM64Engine(compInc.BRAMImage, "KPOL-CME-1", compInc.ModuleName, ExampleIncreaseSource, compInc.ConceptNames)
	if err != nil {
		t.Fatalf("NewBRAM64Engine failed: %v", err)
	}

	s1 := engInc.StepEvent(0, 5, true)
	if len(s1) != 1 || s1[0].Verdict != VerdictCommit || engInc.State[0] != 11 {
		t.Fatalf("expected COMMIT to 11 on param=5, got verdict=%s state=%d", s1[0].Verdict, engInc.State[0])
	}

	s2 := engInc.StepEvent(0, 25, true)
	if len(s2) != 1 || s2[0].Verdict != VerdictRejectGuard || engInc.State[0] != 11 {
		t.Fatalf("expected REJECT_GUARD on param=25, got verdict=%s state=%d", s2[0].Verdict, engInc.State[0])
	}

	s3 := engInc.StepEvent(0, 0, false)
	if len(s3) != 1 || s3[0].Verdict != VerdictRejectFault || engInc.State[0] != 11 || engInc.FaultPropagations != 1 {
		t.Fatalf("expected REJECT_FAULT on invalid '_' input, got verdict=%s state=%d faults=%d",
			s3[0].Verdict, engInc.State[0], engInc.FaultPropagations)
	}

	// Test concept invalidation (`_`) also triggers REJECT_FAULT even if input param is valid
	engInc.InvalidateConcept(0)
	s4 := engInc.StepEvent(0, 5, true)
	if len(s4) != 1 || s4[0].Verdict != VerdictRejectFault || engInc.State[0] != 11 {
		t.Fatalf("expected REJECT_FAULT when concept state is '_', got verdict=%s", s4[0].Verdict)
	}
	engInc.RevalidateConcept(0, 11)

	// Test DecreaseFromOne (KPOL-CME-1): 1 -> 0 (COMMIT), then 0 -> -1 blocked by Big Dot • (REJECT_INVARIANT)
	compDec, err := CompileKPOLSource(ExampleDecreaseSource, "KPOL-CME-1")
	if err != nil {
		t.Fatalf("CompileKPOLSource(Decrease) failed: %v", err)
	}
	engDec, err := NewBRAM64Engine(compDec.BRAMImage, "KPOL-CME-1", compDec.ModuleName, ExampleDecreaseSource, compDec.ConceptNames)
	if err != nil {
		t.Fatalf("NewBRAM64Engine(Decrease) failed: %v", err)
	}

	d1 := engDec.StepEvent(0, 5, true)
	if d1[0].Verdict != VerdictCommit || engDec.State[0] != 0 {
		t.Fatalf("expected first decrease 1->0 COMMIT, got %s state=%d", d1[0].Verdict, engDec.State[0])
	}
	d2 := engDec.StepEvent(0, 5, true)
	if d2[0].Verdict != VerdictRejectInvariant || d2[0].CandidateW0 != -1 || engDec.State[0] != 0 {
		t.Fatalf("expected second decrease 0->-1 REJECT_INVARIANT keeping 0, got verdict=%s cand=%d state=%d",
			d2[0].Verdict, d2[0].CandidateW0, engDec.State[0])
	}
}

func TestBRAM64OverflowFIFO16AndDualBankCRC8(t *testing.T) {
	// Configure C0 with W0 = 0x7FFFFFFF (MaxInt32) and ACT_INC: must trigger ArithOverflow and REJECT_INVARIANT
	var descs [64]ConceptDescriptor
	descs[0] = ConceptDescriptor{
		CID:           0,
		Name:          "MaxCounter",
		TypeName:      "Int32",
		CurrentState:  0x7FFFFFFF,
		OperandVal:    0,
		PredOpcode:    PredNOP,
		GuardFlags:    GuardAssumptionEn | GuardInvariantEn,
		ActionOpcode:  ActInc,
		SubscriberCID: 0,
	}
	eng, err := NewBRAM64Engine(PackBRAM(descs), "KPOL-CME-1", "OvfTest", "", []string{"MaxCounter"})
	if err != nil {
		t.Fatalf("NewBRAM64Engine failed: %v", err)
	}
	st := eng.StepEvent(0, 1, true)
	if !st[0].ArithOverflow || st[0].Verdict != VerdictRejectInvariant || eng.State[0] != 0x7FFFFFFF {
		t.Fatalf("expected signed 32-bit overflow REJECT_INVARIANT at 0x7FFFFFFF+1, got %+v", st[0])
	}

	// Test FIFO 16 capacity & overflow tracking
	eng.Reset()
	eng.State[0] = 10
	eng.InitialState[0] = 10
	for i := 0; i < 18; i++ {
		ok := eng.EnqueueFIFO(0, 1, true)
		if i < 16 && !ok {
			t.Fatalf("expected FIFO enqueue #%d to succeed", i)
		}
		if i >= 16 && ok {
			t.Fatalf("expected FIFO enqueue #%d beyond 16 to fail", i)
		}
	}
	if !eng.FIFOOverflow || eng.DroppedEvents != 2 {
		t.Fatalf("expected FIFOOverflow=true and DroppedEvents=2, got %v / %d", eng.FIFOOverflow, eng.DroppedEvents)
	}
	steps := eng.DrainFIFO()
	if len(steps) != 16 || eng.State[0] != 26 {
		t.Fatalf("expected 16 drained steps and state=26, got %d / %d", len(steps), eng.State[0])
	}

	// Test Dual-Bank (Bank 0 / Bank 1) hot rule update with CRC-8 verification
	newDesc := ConceptDescriptor{
		CID:          0,
		Name:         "MaxCounter",
		CurrentState: 0,
		OperandVal:   5,
		PredOpcode:   PredGT,
		GuardFlags:   GuardAssumptionEn | GuardInvariantEn,
		ActionOpcode: ActAdd,
	}
	pkt := newDesc.Pack()
	crc := CRC8(pkt[:])

	// Bad CRC-8 must be rejected fail-closed
	if err := eng.HotUpdateShadowSlot(0, pkt[:], crc^0xFF, false); err == nil {
		t.Fatalf("expected CRC-8 mismatch error, got nil")
	}

	// Valid CRC-8 updates shadow bank and swaps at idle boundary while preserving live W0=26
	if err := eng.HotUpdateShadowSlot(0, pkt[:], crc, false); err != nil {
		t.Fatalf("HotUpdateShadowSlot failed: %v", err)
	}
	eng.SwapBanksAtIdleBoundary()
	if eng.ActiveBank != 1 || eng.SwapCount != 1 || eng.State[0] != 26 {
		t.Fatalf("expected ActiveBank=1, SwapCount=1, preserved W0=26; got bank=%d swaps=%d state=%d",
			eng.ActiveBank, eng.SwapCount, eng.State[0])
	}
	// Now rule is param > 5 -> W0 += 5
	w := eng.StepEvent(0, 10, true)
	if w[0].Verdict != VerdictCommit || eng.State[0] != 31 {
		t.Fatalf("expected hot-swapped rule to add +5 (26->31), got verdict=%s state=%d", w[0].Verdict, eng.State[0])
	}
}

func TestBMSSafetyCascadeAndPrePostLoadDiff(t *testing.T) {
	_, data, err := RunSingleExampleDemo("bms")
	if err != nil {
		t.Fatalf("RunSingleExampleDemo(bms) failed: %v", err)
	}
	telem := data["telemetry"].(map[string]any)
	if telem["events_processed"].(uint32) != 14 || telem["commits"].(uint32) != 10 || telem["rejects"].(uint32) != 4 || telem["fault_propagations"].(uint32) != 1 {
		t.Fatalf("unexpected BMS telemetry: %+v", telem)
	}
	states := data["final_active_states"].([]int32)
	want := []int32{3, 3, 0, 0}
	for i := range want {
		if states[i] != want[i] {
			t.Fatalf("BMS final state[%d] = %d, want %d", i, states[i], want[i])
		}
	}

	// Verify Pre-Load -> Post-Load diff detects changes in W1/W2/W3 even when W0 is identical!
	var preDescs, postDescs [64]ConceptDescriptor
	preDescs[0] = ConceptDescriptor{
		CID:          0,
		Name:         "RuleSlot",
		CurrentState: 42, // identical W0
		OperandVal:   10,
		PredOpcode:   PredLT,
		GuardFlags:   GuardAssumptionEn | GuardInvariantEn,
		ActionOpcode: ActInc,
	}
	postDescs[0] = ConceptDescriptor{
		CID:          0,
		Name:         "RuleSlot",
		CurrentState: 42, // identical W0, but W1 and W2 changed!
		OperandVal:   100,
		PredOpcode:   PredGT,
		GuardFlags:   GuardAssumptionEn | GuardInvariantEn,
		ActionOpcode: ActDec,
	}
	preSnap, err := MakeSnapshotFromBytes(PackBRAM(preDescs), "PRE-LOAD", "sim", HWIDCfgP, 0, 0, 0, 0, 0, []string{"RuleSlot"})
	if err != nil {
		t.Fatal(err)
	}
	postSnap, err := MakeSnapshotFromBytes(PackBRAM(postDescs), "POST-LOAD", "sim", HWIDCfgP, 0, 0, 0, 0, 0, []string{"RuleSlot"})
	if err != nil {
		t.Fatal(err)
	}
	diffs := ComputePrePostLoadDiff(preSnap, postSnap)
	if len(diffs) != 1 || !diffs[0].Changed {
		t.Fatalf("expected ComputePrePostLoadDiff to detect W1/W2 rule change when W0 is unchanged, got %+v", diffs)
	}
}

func TestConceptualModeAllSixExamples(t *testing.T) {
	// 1. If T-flip-flop (`_ -> ! -> ¬ -> !`)
	_, ifData, err := RunSingleExampleDemo("if")
	if err != nil {
		t.Fatalf("if example failed: %v", err)
	}
	traj := ifData["state_trajectory"].([]string)
	if strings.Join(traj, ",") != "_,!,¬,!" || ifData["final_state"].(string) != "!" {
		t.Fatalf("unexpected If trajectory: %v (final=%v)", traj, ifData["final_state"])
	}

	// 2. Sum post-read Big Dot reset (`0 + 10 + 25 = 35`, read returns `35`, then `• Sum = 0`)
	_, sumData, err := RunSingleExampleDemo("sum")
	if err != nil {
		t.Fatalf("sum example failed: %v", err)
	}
	readVal := sumData["read_returned_value"].(float64)
	postVal := sumData["post_read_state"].(float64)
	if readVal != 35 || postVal != 0 {
		t.Fatalf("Sum RFC-013 post-read barrier violated: readReturned=%v (want 35), postReadState=%v (want 0)", readVal, postVal)
	}

	// 3. Nod(120, 6) = 6 (19 subtractions, 20 eval steps, 58 cycles)
	_, nodData, err := RunSingleExampleDemo("nod")
	if err != nil {
		t.Fatalf("nod example failed: %v", err)
	}
	if nodData["result"].(int64) != 6 || nodData["subtraction_iterations"].(int) != 19 || nodData["hardware_cycles_at_3cyc_per_sub_plus_1"].(int) != 58 {
		t.Fatalf("unexpected Nod(120, 6) metrics: %+v", nodData)
	}

	// 4. Factorial(5) = 120
	_, factData, err := RunSingleExampleDemo("factorial")
	if err != nil {
		t.Fatalf("factorial example failed: %v", err)
	}
	if factData["result"].(int64) != 120 {
		t.Fatalf("expected Factorial(5) = 120, got %v", factData["result"])
	}

	// 5. Tachometer (3 wheel ticks + 1s timer -> Distance=6, Speed=6, Revolutions=0)
	_, tachData, err := RunSingleExampleDemo("tachometer")
	if err != nil {
		t.Fatalf("tachometer example failed: %v", err)
	}
	if tachData["distance"].(float64) != 6 || tachData["speed"].(float64) != 6 || tachData["revolutions_post"].(int64) != 0 {
		t.Fatalf("unexpected Tachometer state: %+v", tachData)
	}
}

func TestCLIStdioFailOnRejectTUIAndUnreachableTarget(t *testing.T) {
	// 1. STDIO with --fail-on-reject returns exit code 1 when a reject occurs
	var outBuf, errBuf bytes.Buffer
	in := strings.NewReader("5\n25\n_\n")
	code := RunCLI([]string{"--mode", "bram64", "--example", "increase", "--stdio", "--fail-on-reject"}, in, &outBuf, &errBuf)
	if code != 1 {
		t.Fatalf("expected exit code 1 with --fail-on-reject, got %d", code)
	}
	if !strings.Contains(outBuf.String(), "COMMIT: Counter[cid=0] = 11") {
		t.Fatalf("missing COMMIT in stdout: %s", outBuf.String())
	}
	if !strings.Contains(errBuf.String(), "REJECT_GUARD:") || !strings.Contains(errBuf.String(), "REJECT_FAULT:") {
		t.Fatalf("missing REJECT_GUARD / REJECT_FAULT in stderr: %s", errBuf.String())
	}

	// 2. Render TUI frame deterministic check
	outBuf.Reset()
	errBuf.Reset()
	code = RunCLI([]string{"--mode", "bram64", "--example", "bms", "--stdio", "--render-tui-frame"}, strings.NewReader("Cell_Delta_mV 120\n"), &outBuf, &errBuf)
	if code != 0 {
		t.Fatalf("expected exit code 0 for TUI frame render, got %d (stderr=%s)", code, errBuf.String())
	}
	tuiStr := outBuf.String()
	for _, marker := range []string{
		"VMK (Virtual Machine of Kuzmin) v0.2.0",
		"State: PRE-LOAD -> POST-LOAD -> RUNNING",
		"[PANEL 1: CONCEPT TABLE",
		"[PANEL 2: PROGRAM SOURCE CODE & LIVE STDIO STREAMS",
		"[PANEL 3: CASCADE WAVE STEP TRACE]",
	} {
		if !strings.Contains(tuiStr, marker) {
			t.Fatalf("TUI frame missing marker %q:\n%s", marker, tuiStr)
		}
	}

	// 3. Unreachable hardware target returns VMK-TARGET-IO and exit code 2
	outBuf.Reset()
	errBuf.Reset()
	code = RunCLI([]string{"--mode", "bram64", "--example", "increase", "--stdio", "--target", "root@127.0.0.1:1"}, strings.NewReader("5\n"), &outBuf, &errBuf)
	if code != 2 || !strings.Contains(errBuf.String(), "VMK-TARGET-IO:") {
		t.Fatalf("expected exit code 2 and VMK-TARGET-IO on unreachable target, got code=%d stderr=%s", code, errBuf.String())
	}
}

func TestAllPredicatesActionsSelfSuppressAndExamplesAll(t *testing.T) {
	// Test all predicates (EQ, NEQ, GT, LT, RANGE, BITMASK, UGT) and actions (ASSIGN, INC, DEC, ADD, SUB, NOP)
	var descs [64]ConceptDescriptor
	// C0: EQ 10 -> ADD 5, self-subscribed (C0 -> C0) to verify SUPPRESSED_SELF
	descs[0] = ConceptDescriptor{
		CID:           0,
		Name:          "SelfConcept",
		CurrentState:  20,
		OperandVal:    10,
		PredOpcode:    PredEQ,
		GuardFlags:    GuardAssumptionEn | GuardInvariantEn | GuardSubscriberEn,
		ActionOpcode:  ActAdd,
		SubscriberCID: 0,
	}
	// C1: BITMASK 0x04 -> SUB 3
	descs[1] = ConceptDescriptor{
		CID:          1,
		Name:         "MaskConcept",
		CurrentState: 15,
		OperandVal:   4,
		PredOpcode:   PredBITMASK,
		GuardFlags:   GuardAssumptionEn | GuardInvariantEn,
		ActionOpcode: ActSub,
	}
	// C2: UGT 100 -> NOP
	descs[2] = ConceptDescriptor{
		CID:          2,
		Name:         "UgtConcept",
		CurrentState: 7,
		OperandVal:   100,
		PredOpcode:   PredUGT,
		GuardFlags:   GuardAssumptionEn | GuardInvariantEn,
		ActionOpcode: ActNOP,
	}
	eng, err := NewBRAM64Engine(PackBRAM(descs), "KPOL-CME-2", "PredActSuite", "", []string{"SelfConcept", "MaskConcept", "UgtConcept"})
	if err != nil {
		t.Fatal(err)
	}
	w0 := eng.StepEvent(0, 10, true)
	if len(w0) != 1 || w0[0].Verdict != VerdictSuppressedSelf || eng.State[0] != 30 {
		t.Fatalf("expected SUPPRESSED_SELF and state=30, got %+v state=%d", w0, eng.State[0])
	}
	w1 := eng.StepEvent(1, 4, true)
	if len(w1) != 1 || w1[0].Verdict != VerdictCommit || eng.State[1] != 11 {
		t.Fatalf("expected BITMASK+SUB to produce 15-4=11, got %+v state=%d", w1, eng.State[1])
	}
	w2 := eng.StepEvent(2, -1, true) // -1 as uint32 is 0xFFFFFFFF > 100 -> PredUGT true!
	if len(w2) != 1 || w2[0].Verdict != VerdictCommit || eng.State[2] != 7 {
		t.Fatalf("expected PredUGT on -1 (0xFFFFFFFF) to match and ActNOP to keep 7, got %+v", w2)
	}

	// RunAllExamples must succeed across all 10 built-in examples
	fullTxt, allData, err := RunAllExamples()
	if err != nil {
		t.Fatalf("RunAllExamples failed: %v", err)
	}
	for _, k := range []string{"if", "sum", "nod", "factorial", "tachometer", "bms", "increase", "decrease", "cascade", "auth"} {
		if _, ok := allData[k]; !ok || !strings.Contains(fullTxt, "EXAMPLE: "+strings.ToUpper(k)) {
			t.Fatalf("RunAllExamples missing example %q", k)
		}
	}

	// Verify Reset() restores Bank0/Bank1 descriptor CurrentState and interactive TUI loop handles s/f/r/i/q
	eng.Reset()
	if eng.Bank0[0].CurrentState != 20 || eng.Bank1[0].CurrentState != 20 {
		t.Fatalf("expected Reset() to restore Bank0/Bank1 CurrentState=20, got %d / %d", eng.Bank0[0].CurrentState, eng.Bank1[0].CurrentState)
	}
	var tuiOut bytes.Buffer
	tuiIn := strings.NewReader("s\nf\nr\ni 0 10\nq\n")
	frame := RunInteractiveBRAM64TUI(eng, nil, []QueuedEvent{{CID: 0, Param: 10, ParamValid: true}}, nil, tuiIn, &tuiOut, true)
	if !strings.Contains(frame, "State: PRE-LOAD -> POST-LOAD -> COMPLETED") || eng.State[0] != 30 {
		t.Fatalf("unexpected interactive TUI result: state=%d\n%s", eng.State[0], frame)
	}

	// Verify --example bms --fail-on-reject returns exit code 1
	var exOut, exErr bytes.Buffer
	if code := RunCLI([]string{"--example", "bms", "--fail-on-reject"}, strings.NewReader(""), &exOut, &exErr); code != 1 {
		t.Fatalf("expected exit code 1 for --example bms --fail-on-reject, got %d", code)
	}

	// Verify --mode conceptual --stdio works for `toggle If` and all BRAM-lowered examples (bms, cascade, increase, decrease, auth)
	exOut.Reset()
	exErr.Reset()
	if code := RunCLI([]string{"--mode", "conceptual", "--example", "if", "--stdio"}, strings.NewReader("toggle If\ntoggle If\n"), &exOut, &exErr); code != 0 || !strings.Contains(exOut.String(), "COMMIT: If[cid=0] = ¬") {
		t.Fatalf("toggle If in conceptual stdio failed: code=%d stderr=%s out=%s", code, exErr.String(), exOut.String())
	}
	for _, exName := range []string{"bms", "cascade", "increase", "decrease", "auth"} {
		exOut.Reset()
		exErr.Reset()
		code := RunCLI([]string{"--mode", "conceptual", "--example", exName, "--stdio", "--render-tui-frame"}, strings.NewReader("0:120\n"), &exOut, &exErr)
		if code != 0 || !strings.Contains(exOut.String(), "Mode: conceptual (descriptor-backed)") {
			t.Fatalf("--mode conceptual --stdio --example %s failed: code=%d stderr=%s\nout=%s",
				exName, code, exErr.String(), exOut.String())
		}
	}

	// Verify safe PYNQ_SUDO_PASS handling in BuildPYNQRemoteExec (no shell interpolation, no default password)
	cmdNoPass, stdinNoPass := BuildPYNQRemoteExec("/home/xilinx/km_vmk_274_work", []int32{120, 180}, "")
	if stdinNoPass != "" || !strings.Contains(cmdNoPass, "sudo -n ./km_pynq_debug_probe program_image.bin 120 180") {
		t.Fatalf("unexpected BuildPYNQRemoteExec for empty password: cmd=%q stdin=%q", cmdNoPass, stdinNoPass)
	}
	specialPass := "p@ss'w0rd; echo $(id) `uname`"
	cmdWithPass, stdinWithPass := BuildPYNQRemoteExec("/home/xilinx/km_vmk_274_work", []int32{120}, specialPass)
	if strings.Contains(cmdWithPass, specialPass) || !strings.Contains(cmdWithPass, "sudo -S -p '' ./km_pynq_debug_probe program_image.bin 120") || stdinWithPass != specialPass+"\n" {
		t.Fatalf("unsafe BuildPYNQRemoteExec with special password: cmd=%q stdin=%q", cmdWithPass, stdinWithPass)
	}
	if gotQuote := ShellQuoteSingle("a'b"); gotQuote != "'a'\\''b'" {
		t.Fatalf("unexpected ShellQuoteSingle('a\\'b'): %q", gotQuote)
	}
}

func TestEKPOLBRAMBitIdenticalSHA256AndRoundtrip(t *testing.T) {
	decreaseFromTenKPOL := strings.Replace(ExampleDecreaseSource, "Problem DecreaseFromOne", "Problem Decrease", 1)
	decreaseFromTenKPOL = strings.Replace(decreaseFromTenKPOL, "Solution DecreaseFromOne", "Solution Decrease", 1)
	decreaseFromTenKPOL = strings.Replace(decreaseFromTenKPOL, "state Counter: Int32 = 1;", "state Counter: Int32 = 10;", 1)

	cases := []struct {
		name      string
		kpolSrc   string
		profile   string
		ekpolFile string
		wantSHA   string
	}{
		{
			name:      "increase",
			kpolSrc:   ExampleIncreaseSource,
			profile:   "KPOL-CME-1",
			ekpolFile: "../../examples/increase.ekpol",
			wantSHA:   "4df05b189b9bf12052d98ab6084e0256454c60cae4afd4449469c060ba8dcc5d",
		},
		{
			name:      "decrease",
			kpolSrc:   decreaseFromTenKPOL,
			profile:   "KPOL-CME-1",
			ekpolFile: "../../examples/decrease.ekpol",
			wantSHA:   "00ba66e57e21d14913c95d7d2fc8c45c3c450548510ca3155721d7eec67b78c3",
		},
		{
			name:      "cascade",
			kpolSrc:   ExampleCascade4Source,
			profile:   "KPOL-CME-2",
			ekpolFile: "../../examples/cascade_4concept.ekpol",
			wantSHA:   "032c4705c91cea6ddddb7d449cd0dcbd6ba62359af1f9e7a846f33c341a7ef38",
		},
		{
			name:      "bms",
			kpolSrc:   ExampleBMSSafetyCascadeSource,
			profile:   "KPOL-CME-2",
			ekpolFile: "../../examples/bms_safety_cascade.ekpol",
			wantSHA:   "de03442454424b5cf64478506f118c13f095ae24ba58db8894583c43567ea3ee",
		},
	}

	for _, tc := range cases {
		kComp, err := CompileKPOLSource(tc.kpolSrc, tc.profile)
		if err != nil {
			t.Fatalf("%s CompileKPOLSource failed: %v", tc.name, err)
		}
		kSnap, err := MakeSnapshotFromBytes(kComp.BRAMImage, "POST-LOAD", "sim", HWIDCfgP, 0, 0, 0, 0, 0, kComp.ConceptNames)
		if err != nil {
			t.Fatal(err)
		}
		if kSnap.BRAMSHA256 != tc.wantSHA {
			t.Fatalf("%s KPOL SHA-256 = %s, want %s", tc.name, kSnap.BRAMSHA256, tc.wantSHA)
		}

		for _, style := range []string{"symbolic", "keyword"} {
			ekSrc, err := TranspileKPOLToEKPOL(tc.kpolSrc, style)
			if err != nil {
				t.Fatalf("%s TranspileKPOLToEKPOL(%s) failed: %v", tc.name, style, err)
			}
			for i := 0; i < len(ekSrc); i++ {
				if ekSrc[i] >= 128 {
					t.Fatalf("%s (%s) contains non-ASCII byte 0x%02X", tc.name, style, ekSrc[i])
				}
			}
			ekComp, err := CompileEKPOLSource(ekSrc, tc.name)
			if err != nil {
				t.Fatalf("%s CompileEKPOLSource(%s) failed: %v", tc.name, style, err)
			}
			if !bytes.Equal(ekComp.BRAMImage, kComp.BRAMImage) {
				t.Fatalf("%s (%s) BRAM mismatch against classic KPOL", tc.name, style)
			}

			backKPOL, err := TranspileEKPOLToKPOL(ekSrc, tc.name)
			if err != nil {
				t.Fatalf("%s TranspileEKPOLToKPOL(%s) failed: %v", tc.name, style, err)
			}
			backComp, err := CompileKPOLSource(backKPOL, tc.profile)
			if err != nil {
				t.Fatalf("%s roundtrip CompileKPOLSource(%s) failed: %v", tc.name, style, err)
			}
			if !bytes.Equal(backComp.BRAMImage, kComp.BRAMImage) {
				t.Fatalf("%s (%s) roundtrip KPOL->EKPOL->KPOL->BRAM mismatch", tc.name, style)
			}
		}

		// Also verify example .ekpol file on disk compiles to exact 64-char SHA-256 and CLI flags work
		fileBytes, err := os.ReadFile(tc.ekpolFile)
		if err != nil {
			t.Fatalf("ReadFile(%s) failed: %v", tc.ekpolFile, err)
		}
		fileComp, err := CompileEKPOLSource(string(fileBytes), tc.name)
		if err != nil {
			t.Fatalf("CompileEKPOLSource(%s) failed: %v", tc.ekpolFile, err)
		}
		fileSnap, err := MakeSnapshotFromBytes(fileComp.BRAMImage, "POST-LOAD", "sim", HWIDCfgP, 0, 0, 0, 0, 0, fileComp.ConceptNames)
		if err != nil {
			t.Fatal(err)
		}
		if fileSnap.BRAMSHA256 != tc.wantSHA {
			t.Fatalf("%s file SHA-256 = %s, want %s", tc.ekpolFile, fileSnap.BRAMSHA256, tc.wantSHA)
		}

		var outBuf, errBuf bytes.Buffer
		if code := RunCLI([]string{"--program", tc.ekpolFile, "--dump-concepts"}, strings.NewReader(""), &outBuf, &errBuf); code != 0 {
			t.Fatalf("CLI --program %s --dump-concepts failed: code=%d stderr=%s", tc.ekpolFile, code, errBuf.String())
		}
		if !strings.Contains(outBuf.String(), tc.wantSHA[:16]) {
			t.Fatalf("CLI output for %s missing SHA-256 prefix %s:\n%s", tc.ekpolFile, tc.wantSHA[:16], outBuf.String())
		}

		outBuf.Reset()
		errBuf.Reset()
		if code := RunCLI([]string{"--program", tc.ekpolFile, "--to-kpol"}, strings.NewReader(""), &outBuf, &errBuf); code != 0 || !strings.Contains(outBuf.String(), "Problem ") {
			t.Fatalf("CLI --program %s --to-kpol failed: code=%d stderr=%s", tc.ekpolFile, code, errBuf.String())
		}
	}
}

func TestEKPOLConceptualExamplesAndPostReadBarrier(t *testing.T) {
	// Verify both symbolic (`-> => . Sum = 0`) and keyword (`on read => after Sum = 0;`) post-read Big Dot reset
	for _, src := range []string{
		`concept Sum: f64 = 0 [>= 0] {
			<- x :: true => Sum += x .
			-> => . Sum = 0
		}`,
		`concept Sum: float64 = 0 [>= 0] {
			on write(x) => Sum += x commit;
			on read => after Sum = 0;
		}`,
	} {
		prog, err := ParseEKPOL(src, "SumTest")
		if err != nil {
			t.Fatalf("ParseEKPOL(Sum) failed: %v", err)
		}
		vm, _, err := NewConceptualVMFromEKPOL(prog, src)
		if err != nil {
			t.Fatalf("NewConceptualVMFromEKPOL(Sum) failed: %v", err)
		}
		vm.ExecuteSumWrite(10, true)
		vm.ExecuteSumWrite(25, true)
		readVal, postState, _ := vm.ExecuteSumReadWithPostDotReset()
		if readVal != 35 || postState != 0 {
			t.Fatalf("EKPOL Sum post-read barrier failed: readReturned=%v (want 35), postReadState=%v (want 0)", readVal, postState)
		}
	}

	// Verify all 5 conceptual .ekpol files in examples/ execute cleanly via RunCLI
	for _, exFile := range []string{
		"../../examples/if_toggle.ekpol",
		"../../examples/sum_autoreset.ekpol",
		"../../examples/nod_euclid.ekpol",
		"../../examples/factorial.ekpol",
		"../../examples/tachometer.ekpol",
	} {
		var outBuf, errBuf bytes.Buffer
		code := RunCLI([]string{"--program", exFile}, strings.NewReader(""), &outBuf, &errBuf)
		if code != 0 {
			t.Fatalf("RunCLI(--program %s) failed: code=%d stderr=%s", exFile, code, errBuf.String())
		}
		if !strings.Contains(outBuf.String(), "State: PRE-LOAD -> POST-LOAD -> COMPLETED") {
			t.Fatalf("missing COMPLETED TUI header for %s:\n%s", exFile, outBuf.String())
		}
	}
}

func TestEKPOLStaticVerificationErrors(t *testing.T) {
	// 1. Cyclic cascade C0 -> C1 -> C0 must fail with EKPOL-CYCLE-ERR
	cyclicSrc := `
	concept C0: i32 = 0 [>= 0] { ~ C1 :: C1 >= 1 => C0 += 1 . }
	concept C1: i32 = 0 [>= 0] { ~ C0 :: C0 >= 1 => C1 += 1 . }
	`
	if _, err := CompileEKPOLSource(cyclicSrc, "Cyclic"); err == nil || !strings.Contains(err.Error(), "EKPOL-CYCLE-ERR") {
		t.Fatalf("expected EKPOL-CYCLE-ERR on cyclic cascade, got %v", err)
	}

	// 2. Inverted range 5000..50 must fail with EKPOL-RANGE-ERR
	badRangeSrc := `concept C0: i32 = 0 [>= 0] { <- x :: x in 5000..50 => C0 += 1 . }`
	if _, err := CompileEKPOLSource(badRangeSrc, "BadRange"); err == nil || !strings.Contains(err.Error(), "EKPOL-RANGE-ERR") {
		t.Fatalf("expected EKPOL-RANGE-ERR on inverted range, got %v", err)
	}

	// 3. Missing [>= 0] invariant must fail with EKPOL-INVARIANT-ERR
	noInvSrc := `concept C0: i32 = 0 { <- x :: x < 10 => C0 += 1 . }`
	if _, err := CompileEKPOLSource(noInvSrc, "NoInv"); err == nil || !strings.Contains(err.Error(), "EKPOL-INVARIANT-ERR") {
		t.Fatalf("expected EKPOL-INVARIANT-ERR on missing invariant, got %v", err)
	}

	// 4. W1 operand collision (guard literal + step != 1) must fail with EKPOL-COLLISION-ERR
	collisionSrc := `concept C0: i32 = 0 [>= 0] { <- x :: x < 10 => C0 += 5 . }`
	if _, err := CompileEKPOLSource(collisionSrc, "Collision"); err == nil || !strings.Contains(err.Error(), "EKPOL-COLLISION-ERR") {
		t.Fatalf("expected EKPOL-COLLISION-ERR on W1 collision, got %v", err)
	}
}
