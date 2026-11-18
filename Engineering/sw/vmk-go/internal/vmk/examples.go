package vmk

import (
	"fmt"
	"strings"
)

// Canonical KPOL / Author source texts for built-in VMK examples.
const (
	ExampleIncreaseSource = `# @stdin Counter
# @stdout Counter
Problem Increase {
    Invariants { NonNeg: Counter >= 0; }
}
Solution Increase {
    state Counter: Int32 = 10;
    event Pulse(param: Int32);
    rule Step on Pulse when param < 20 {
        set Counter := Counter + 1;
    }
}`

	ExampleDecreaseSource = `# @stdin Counter
# @stdout Counter
Problem DecreaseFromOne {
    Invariants { NonNeg: Counter >= 0; }
}
Solution DecreaseFromOne {
    state Counter: Int32 = 1;
    event Pulse(param: Int32);
    rule Step on Pulse when param < 20 {
        set Counter := Counter - 1;
    }
}`

	ExampleCascade4Source = `# @stdin C0
# @stdout C0, C1, C2, C3
Problem Cascade4Concept {
    Invariants {
        I0: C0 >= 0;
        I1: C1 >= 0;
        I2: C2 >= 0;
        I3: C3 >= 0;
    }
}
Solution Cascade4Concept {
    state C0: Int32 = 10;
    state C1: Int32 = 0;
    state C2: Int32 = 2;
    state C3: Int32 = 0;

    event E0(param: Int32);

    rule R0 on E0 when param < 50 { set C0 := C0 + 1; }
    rule R1 on change(C0) when C0 > 10 { set C1 := C1 + 1; }
    rule R2 on change(C1) when C1 >= 1 { set C2 := C2 - 1; }
    rule R3 on change(C2) when not (C2 == 2) { set C3 := C2; }
}
Proof Cascade4Concept {
    scenario CheckCascadeAndGuardBlock {
        step E0(param = 10);
        expect C0 == 11;
        expect C1 == 1;
        expect C2 == 1;
        expect C3 == 1;
        step E0(param = 100);
        expect C0 == 11;
        expect C3 == 1;
    }
}`

	ExampleBMSSafetyCascadeSource = `# @stdin Cell_Delta_mV
# @stdout Cell_Delta_mV, Module_Thermal_Guard, Pack_Fault_Latch, Contactor_Interlock
Problem BmsSafetyCascade {
    Invariants {
        inv_cell_delta: Cell_Delta_mV >= 0;
        inv_mod_thermal: Module_Thermal_Guard >= 0;
        inv_pack_latch: Pack_Fault_Latch >= 0;
        inv_contactor: Contactor_Interlock >= 0;
    }
}
Solution BmsSafetyCascade {
    state Cell_Delta_mV: Int32 = 0;
    state Module_Thermal_Guard: Int32 = 0;
    state Pack_Fault_Latch: Int32 = 2;
    state Contactor_Interlock: Int32 = 10;

    event EvCellDelta(delta_mv: Int32);

    rule RCellDelta on EvCellDelta when delta_mv >= 50 and delta_mv <= 5000 {
        set Cell_Delta_mV := Cell_Delta_mV + 1;
    }
    rule RModuleThermal on change(Cell_Delta_mV) when Cell_Delta_mV >= 1 {
        set Module_Thermal_Guard := Module_Thermal_Guard + 1;
    }
    rule RPackFaultLatch on change(Module_Thermal_Guard) when Module_Thermal_Guard >= 1 {
        set Pack_Fault_Latch := Pack_Fault_Latch - 1;
    }
    rule RContactorInterlock on change(Pack_Fault_Latch) when not (Pack_Fault_Latch == 2) {
        set Contactor_Interlock := Pack_Fault_Latch;
    }
}
Proof BmsSafetyCascade {
    scenario BmsFourLevelProtectionAndLatch {
        step EvCellDelta(delta_mv = 15);
        expect Cell_Delta_mV == 0;
        expect Contactor_Interlock == 10;
        step EvCellDelta(delta_mv = 120);
        expect Cell_Delta_mV == 1;
        expect Module_Thermal_Guard == 1;
        expect Pack_Fault_Latch == 1;
        expect Contactor_Interlock == 1;
        step EvCellDelta(delta_mv = 180);
        expect Cell_Delta_mV == 2;
        expect Module_Thermal_Guard == 2;
        expect Pack_Fault_Latch == 0;
        expect Contactor_Interlock == 0;
        step EvCellDelta(delta_mv = 250);
        expect Cell_Delta_mV == 3;
        expect Module_Thermal_Guard == 3;
        expect Pack_Fault_Latch == 0;
        expect Contactor_Interlock == 0;
    }
}`

	ExampleAuthCounterSource = `Concept(Counter, 10, Lower=0, Upper=500)
Concept(Mirror, 0, Lower=0, Upper=500)
Counter • Assign(Mirror, Counter + 1)`

	ExampleConceptualIfSource = `? If _
  _ -> If = !
  ! -> If = ¬
  ¬ -> If = !`

	ExampleConceptualSumSource = `Float Sum 0
  ← @ Float x : Sum += x
  → • Sum = 0`

	ExampleConceptualNodSource = `U64 Nod | @ U64 ( a_ > b -=b , b_ > a -=a ) =a
Z = Nod(120, 6)`

	ExampleConceptualFactorialSource = `U64 Factorial | @ U64 n
  [ 0 1 ] { Factorial = 1 Exit }
  = Factorial(n - 1) * n
Z = Factorial(5)`

	ExampleConceptualTachometerSource = `Class Tachometer {
  U64 Revolutions = 0
  Float Distance = 0
  Float Speed = 0
  Tick  ← { Revolutions += 1; Distance += 2 }
  _Tick → • { Speed = (Revolutions * 2) / dt; Revolutions = 0 }
}`
)

// NewConceptualVMForExample constructs a ready-to-run ConceptualVM for `if`, `sum`, `nod`, `factorial`, or `tachometer`.
func NewConceptualVMForExample(name string) (*ConceptualVM, error) {
	switch strings.ToLower(strings.TrimSpace(name)) {
	case "if":
		return NewConceptualVM("IfToggle", ExampleConceptualIfSource, []ConceptualSlot{
			{
				Name:        "If",
				Type:        TypeBool,
				Valid:       false, // starts in uncertainty state '_'
				BoolVal:     false,
				RuleSummary: "_ -> ! ; ! -> ¬ ; ¬ -> !",
				GateSummary: "•(RFC-001 Busy lock)",
				SubSummary:  "Self (suppressed)",
			},
		}), nil
	case "sum":
		return NewConceptualVM("SumPostReadReset", ExampleConceptualSumSource, []ConceptualSlot{
			{
				Name:         "Sum",
				Type:         TypeFloat64,
				Valid:        true,
				FloatVal:     0,
				PostReadZero: true,
				RuleSummary:  "← += x ; → • Sum = 0",
				GateSummary:  "•(RFC-013 Post-Read Reset)",
				SubSummary:   "STDOUT -> • Sum=0",
			},
		}), nil
	case "nod":
		return NewConceptualVM("EuclidNod", ExampleConceptualNodSource, []ConceptualSlot{
			{
				Name:        "a",
				Type:        TypeU64,
				Valid:       true,
				IntVal:      120,
				RuleSummary: "a > b : a -= b",
				GateSummary: "•(a > 0)",
				SubSummary:  "-> b",
			},
			{
				Name:        "b",
				Type:        TypeU64,
				Valid:       true,
				IntVal:      6,
				RuleSummary: "b > a : b -= a",
				GateSummary: "•(b > 0)",
				SubSummary:  "-> a",
			},
			{
				Name:        "Nod",
				Type:        TypeU64,
				Valid:       false,
				IntVal:      0,
				RuleSummary: "| (a == b) => =a",
				GateSummary: "•(Wave extinguished)",
				SubSummary:  "STDOUT",
			},
		}), nil
	case "factorial":
		return NewConceptualVM("FactorialRecursive", ExampleConceptualFactorialSource, []ConceptualSlot{
			{
				Name:        "n",
				Type:        TypeU64,
				Valid:       true,
				IntVal:      5,
				RuleSummary: "[ 0 1 ] -> Exit ; else n - 1",
				GateSummary: "•(n >= 0)",
				SubSummary:  "-> Factorial",
			},
			{
				Name:        "Factorial",
				Type:        TypeU64,
				Valid:       false,
				IntVal:      0,
				RuleSummary: "| Factorial(n-1) * n",
				GateSummary: "•(U64 no overflow)",
				SubSummary:  "STDOUT",
			},
		}), nil
	case "tachometer":
		return NewConceptualVM("TachometerClass", ExampleConceptualTachometerSource, []ConceptualSlot{
			{
				Name:        "Revolutions",
				Type:        TypeU64,
				Valid:       true,
				IntVal:      0,
				RuleSummary: "Tick ← Revolutions += 1",
				GateSummary: "•(Revolutions >= 0)",
				SubSummary:  "-> Distance",
			},
			{
				Name:        "Distance",
				Type:        TypeFloat64,
				Valid:       true,
				FloatVal:    0,
				RuleSummary: "Tick • Distance += 2",
				GateSummary: "•(Distance >= 0)",
				SubSummary:  "None",
			},
			{
				Name:        "Speed",
				Type:        TypeFloat64,
				Valid:       true,
				FloatVal:    0,
				RuleSummary: "_Tick → • Speed=(Rev*2)/dt; Rev=0",
				GateSummary: "•(RFC-013 Post-Read)",
				SubSummary:  "STDOUT",
			},
		}), nil
	default:
		return nil, fmt.Errorf("VMK-EXAMPLE: unknown conceptual example %q", name)
	}
}

// RunSingleExampleDemo executes one named example (`if`, `sum`, `nod`, `factorial`, `tachometer`,
// `bms`, `increase`, `decrease`, `cascade`, `auth`) and returns (formattedText, structuredMap, error).
func RunSingleExampleDemo(exampleName string) (string, map[string]any, error) {
	ex := strings.ToLower(strings.TrimSpace(exampleName))

	switch ex {
	case "if":
		vm, err := NewConceptualVMForExample("if")
		if err != nil {
			return "", nil, err
		}
		_, err = RunConceptualStdioStream(vm, []string{"write If 1", "write If 1", "write If 1"}, nil, nil)
		if err != nil {
			return "", nil, err
		}
		txt := RenderConceptualTUIFrame(vm, "COMPLETED")
		return txt, map[string]any{
			"example":          "if",
			"mode":             ModeConceptual,
			"initial_state":    "_",
			"final_state":      vm.Slots[0].FormatValue(),
			"state_trajectory": []string{"_", "!", "¬", "!"},
			"events_processed": vm.EventsProcessed,
			"commits":          vm.Commits,
			"steps":            vm.Steps,
			"stdout":           vm.StdoutHistory,
		}, nil

	case "sum":
		vm, err := NewConceptualVMForExample("sum")
		if err != nil {
			return "", nil, err
		}
		vm.StdinHistory = append(vm.StdinHistory, "write Sum 10", "write Sum 25", "read Sum")
		vm.ExecuteSumWrite(10, true)
		vm.ExecuteSumWrite(25, true)
		readVal, postResetVal, _ := vm.ExecuteSumReadWithPostDotReset()
		txt := RenderConceptualTUIFrame(vm, "COMPLETED")
		return txt, map[string]any{
			"example":             "sum",
			"mode":                ModeConceptual,
			"read_returned_value": readVal,
			"post_read_state":     postResetVal,
			"events_processed":    vm.EventsProcessed,
			"commits":             vm.Commits,
			"steps":               vm.Steps,
			"stdout":              vm.StdoutHistory,
		}, nil

	case "nod":
		vm, err := NewConceptualVMForExample("nod")
		if err != nil {
			return "", nil, err
		}
		vm.StdinHistory = append(vm.StdinHistory, "call Nod 120 6")
		resVal, subSteps, _ := vm.ExecuteNodCall(120, 6)
		txt := RenderConceptualTUIFrame(vm, "COMPLETED")
		return txt, map[string]any{
			"example":                                "nod",
			"mode":                                   ModeConceptual,
			"a_init":                                 120,
			"b_init":                                 6,
			"result":                                 resVal,
			"subtraction_iterations":                 subSteps,
			"total_eval_steps":                       subSteps + 1,
			"hardware_cycles_at_3cyc_per_sub_plus_1": subSteps*3 + 1,
			"steps":                                  vm.Steps,
			"stdout":                                 vm.StdoutHistory,
		}, nil

	case "factorial":
		vm, err := NewConceptualVMForExample("factorial")
		if err != nil {
			return "", nil, err
		}
		vm.StdinHistory = append(vm.StdinHistory, "call Factorial 5")
		resVal, _ := vm.ExecuteFactorialCall(5)
		txt := RenderConceptualTUIFrame(vm, "COMPLETED")
		return txt, map[string]any{
			"example":          "factorial",
			"mode":             ModeConceptual,
			"n":                5,
			"result":           resVal,
			"events_processed": vm.EventsProcessed,
			"commits":          vm.Commits,
			"steps":            vm.Steps,
			"stdout":           vm.StdoutHistory,
		}, nil

	case "tachometer":
		vm, err := NewConceptualVMForExample("tachometer")
		if err != nil {
			return "", nil, err
		}
		_, err = RunConceptualStdioStream(vm, []string{
			"call Tachometer Tick",
			"call Tachometer Tick",
			"call Tachometer Tick",
			"call Tachometer _Tick 1",
		}, nil, nil)
		if err != nil {
			return "", nil, err
		}
		txt := RenderConceptualTUIFrame(vm, "COMPLETED")
		return txt, map[string]any{
			"example":          "tachometer",
			"mode":             ModeConceptual,
			"distance":         vm.Slots[1].FloatVal,
			"speed":            vm.Slots[2].FloatVal,
			"revolutions_post": vm.Slots[0].IntVal,
			"events_processed": vm.EventsProcessed,
			"commits":          vm.Commits,
			"steps":            vm.Steps,
			"stdout":           vm.StdoutHistory,
		}, nil

	case "increase":
		comp, err := CompileKPOLSource(ExampleIncreaseSource, "KPOL-CME-1")
		if err != nil {
			return "", nil, err
		}
		conn, _ := NewMachineConnection("sim", nil)
		_ = conn.LoadProgramIntoSim(comp.BRAMImage, comp.ConceptNames, nil)
		eng, err := NewBRAM64Engine(comp.BRAMImage, "KPOL-CME-1", comp.ModuleName, ExampleIncreaseSource, comp.ConceptNames)
		if err != nil {
			return "", nil, err
		}
		eng.WatchCIDs[0] = true
		eng.BreakOnReject = true
		stdioRes, err := RunStdioStream(eng, []string{"5", "25", "_"}, nil, nil, nil)
		if err != nil {
			return "", nil, err
		}
		txt := strings.Join([]string{
			conn.FormatPrePostLoadSummary(),
			eng.FormatFull4BlockReport(),
			RenderBRAM64TUIFrame(eng, conn, stdioRes, "COMPLETED"),
		}, "\n\n")
		return txt, buildBRAMExampleResult("increase", eng, conn, stdioRes), nil

	case "decrease":
		comp, err := CompileKPOLSource(ExampleDecreaseSource, "KPOL-CME-1")
		if err != nil {
			return "", nil, err
		}
		conn, _ := NewMachineConnection("sim", nil)
		_ = conn.LoadProgramIntoSim(comp.BRAMImage, comp.ConceptNames, nil)
		eng, err := NewBRAM64Engine(comp.BRAMImage, "KPOL-CME-1", comp.ModuleName, ExampleDecreaseSource, comp.ConceptNames)
		if err != nil {
			return "", nil, err
		}
		eng.WatchCIDs[0] = true
		eng.BreakOnReject = true
		stdioRes, err := RunStdioStream(eng, []string{"5", "5", "25"}, nil, nil, nil)
		if err != nil {
			return "", nil, err
		}
		txt := strings.Join([]string{
			conn.FormatPrePostLoadSummary(),
			eng.FormatFull4BlockReport(),
			RenderBRAM64TUIFrame(eng, conn, stdioRes, "COMPLETED"),
		}, "\n\n")
		return txt, buildBRAMExampleResult("decrease", eng, conn, stdioRes), nil

	case "cascade":
		comp, err := CompileKPOLSource(ExampleCascade4Source, "KPOL-CME-2")
		if err != nil {
			return "", nil, err
		}
		conn, _ := NewMachineConnection("sim", nil)
		_ = conn.LoadProgramIntoSim(comp.BRAMImage, comp.ConceptNames, nil)
		eng, err := NewBRAM64Engine(comp.BRAMImage, "KPOL-CME-2", comp.ModuleName, ExampleCascade4Source, comp.ConceptNames)
		if err != nil {
			return "", nil, err
		}
		eng.WatchCIDs[0] = true
		eng.WatchCIDs[3] = true
		eng.BreakOnReject = true
		stdioRes, err := RunStdioStream(eng, []string{"0 10", "0 100", "0 10", "0 10"}, nil, nil, nil)
		if err != nil {
			return "", nil, err
		}
		txt := strings.Join([]string{
			conn.FormatPrePostLoadSummary(),
			eng.FormatFull4BlockReport(),
			RenderBRAM64TUIFrame(eng, conn, stdioRes, "COMPLETED"),
		}, "\n\n")
		return txt, buildBRAMExampleResult("cascade", eng, conn, stdioRes), nil

	case "bms":
		incComp, err := CompileKPOLSource(ExampleIncreaseSource, "KPOL-CME-1")
		if err != nil {
			return "", nil, err
		}
		comp, err := CompileKPOLSource(ExampleBMSSafetyCascadeSource, "KPOL-CME-2")
		if err != nil {
			return "", nil, err
		}
		conn, _ := NewMachineConnection("sim", incComp.BRAMImage)
		_ = conn.LoadProgramIntoSim(comp.BRAMImage, comp.ConceptNames, incComp.ConceptNames)
		eng, err := NewBRAM64Engine(comp.BRAMImage, "KPOL-CME-2", comp.ModuleName, ExampleBMSSafetyCascadeSource, comp.ConceptNames)
		if err != nil {
			return "", nil, err
		}
		eng.WatchCIDs[2] = true
		eng.WatchCIDs[3] = true
		eng.BreakOnReject = true
		eng.ThresholdWatch[0] = 2
		stdioRes, err := RunStdioStream(eng, []string{
			"Cell_Delta_mV 15",
			"Cell_Delta_mV 5500",
			"Cell_Delta_mV _",
			"Cell_Delta_mV 120",
			"Cell_Delta_mV 180",
			"Cell_Delta_mV 250",
		}, nil, nil, nil)
		if err != nil {
			return "", nil, err
		}
		txt := strings.Join([]string{
			conn.FormatPrePostLoadSummary(),
			eng.FormatFull4BlockReport(),
			RenderBRAM64TUIFrame(eng, conn, stdioRes, "COMPLETED"),
		}, "\n\n")
		return txt, buildBRAMExampleResult("bms", eng, conn, stdioRes), nil

	case "auth":
		comp, err := CompileKPOLSource(ExampleAuthCounterSource, "KPOL-AUTH")
		if err != nil {
			return "", nil, err
		}
		conn, _ := NewMachineConnection("sim", nil)
		_ = conn.LoadProgramIntoSim(comp.BRAMImage, comp.ConceptNames, nil)
		execBRAM := PackBRAM(*comp.ExecDescriptors)
		eng, err := NewBRAM64Engine(execBRAM, "KPOL-AUTH", comp.ModuleName, ExampleAuthCounterSource, comp.ConceptNames)
		if err != nil {
			return "", nil, err
		}
		eng.WatchCIDs[0] = true
		eng.WatchCIDs[1] = true
		eng.BreakOnReject = true
		stdioRes, err := RunStdioStream(eng, []string{"Counter 25", "Counter -5", "Counter _"}, nil, nil, nil)
		if err != nil {
			return "", nil, err
		}
		txt := strings.Join([]string{
			conn.FormatPrePostLoadSummary(),
			fmt.Sprintf("Lowered KPOL-AUTH Do/Go Bytecode (%d words): %s", len(comp.DoGoBytecodeHex), strings.Join(comp.DoGoBytecodeHex, ", ")),
			eng.FormatFull4BlockReport(),
			RenderBRAM64TUIFrame(eng, conn, stdioRes, "COMPLETED"),
		}, "\n\n")
		outMap := buildBRAMExampleResult("auth", eng, conn, stdioRes)
		outMap["dogo_bytecode_hex"] = comp.DoGoBytecodeHex
		return txt, outMap, nil
	}

	return "", nil, fmt.Errorf("VMK-EXAMPLE: unknown example %q", exampleName)
}

func buildBRAMExampleResult(name string, eng *BRAM64Engine, conn *MachineConnection, stdioRes *StdioExecutionResult) map[string]any {
	finalStates := make([]int32, len(eng.ActiveCIDs))
	for i, cid := range eng.ActiveCIDs {
		finalStates[i] = eng.State[cid]
	}
	return map[string]any{
		"example": name,
		"mode":    ModeBRAM64,
		"telemetry": map[string]any{
			"events_processed":     eng.EventsProcessed,
			"commits":              eng.Commits,
			"rejects":              eng.Rejects,
			"fault_propagations":   eng.FaultPropagations,
			"last_committed_state": eng.LastCommittedState,
		},
		"final_active_states": finalStates,
		"steps":               eng.Steps,
		"watchpoint_triggers": eng.WatchpointTriggers,
		"pre_load":            conn.PreLoadSnapshot,
		"post_load":           conn.PostLoadSnapshot,
		"load_diffs":          conn.LoadDiffs,
		"stdio": map[string]any{
			"stdout": stdioRes.StdoutLines,
			"stderr": stdioRes.StderrLines,
		},
	}
}

// RunAllExamples executes all 10 built-in examples (6 core + 4 additional KPOL profiles).
func RunAllExamples() (string, map[string]any, error) {
	names := []string{"if", "sum", "nod", "factorial", "tachometer", "bms", "increase", "decrease", "cascade", "auth"}
	var sections []string
	results := make(map[string]any)
	for _, nm := range names {
		txt, data, err := RunSingleExampleDemo(nm)
		if err != nil {
			return "", nil, err
		}
		sections = append(sections, fmt.Sprintf("################################################################################\n# EXAMPLE: %s\n################################################################################\n\n%s", strings.ToUpper(nm), txt))
		results[nm] = data
	}
	return strings.Join(sections, "\n\n"), results, nil
}
