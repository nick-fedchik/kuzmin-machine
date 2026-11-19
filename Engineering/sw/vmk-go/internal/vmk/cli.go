package vmk

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// RunCLI executes the VMK CLI and returns the process exit code (0 = OK, 1 = rejected with --fail-on-reject, 2 = IO/usage error).
func RunCLI(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	if len(args) > 0 {
		switch args[0] {
		case "version", "--version", "-v":
			_, _ = fmt.Fprintf(stdout, "VMK (Virtual Machine of Kuzmin) v%s\n", Version)
			return 0
		case "run", "trace":
			args = args[1:]
		case "tui":
			args = append([]string{"--tui"}, args[1:]...)
		}
	}

	fs := flag.NewFlagSet("vmk", flag.ContinueOnError)
	fs.SetOutput(stderr)

	var (
		mode                string
		example             string
		programPath         string
		profile             string
		target              string
		connectAlias        string
		traceEvents         string
		dumpConcepts        bool
		stdioMode           bool
		failOnReject        bool
		exitOnReject        bool
		tuiMode             bool
		tuiCanvas           bool
		renderTUIFrame      bool
		renderFullScreenTUI bool
		watchCIDsStr        string
		breakOnReject       bool
		stopOnBreakpoint    bool
		jsonOutPath         string
		toKPOL              bool
		toEKPOL             bool
		ekpolStyle          string
		showVersion         bool
	)

	fs.StringVar(&mode, "mode", "", "execution mode: 'bram64' or 'conceptual'")
	fs.StringVar(&example, "example", "", "built-in example: if|sum|nod|factorial|tachometer|bms|increase|decrease|cascade|auth|all")
	fs.StringVar(&programPath, "program", "", "path to .kpol / .ekpol source file or 1024-byte .bin BRAM image")
	fs.StringVar(&profile, "profile", "KPOL-CME-2", "compiler profile: KPOL-CME-1, KPOL-CME-2, KPOL-AUTH, or EKPOL")
	fs.StringVar(&target, "target", "sim", targetFlagUsage())
	fs.StringVar(&connectAlias, "connect", "", "alias for --target")
	fs.StringVar(&traceEvents, "trace-events", "", "comma-separated event spec, e.g. '0:10,0:100,0:invalid'")
	fs.BoolVar(&dumpConcepts, "dump-concepts", false, "display the BRAM concept descriptor table")
	fs.BoolVar(&stdioMode, "stdio", false, "stream events/commands from stdin, emit COMMIT/READ to stdout and REJECT_* to stderr")
	fs.BoolVar(&failOnReject, "fail-on-reject", false, "return exit code 1 if any event/step was rejected")
	fs.BoolVar(&exitOnReject, "exit-on-reject", false, "alias for --fail-on-reject")
	fs.BoolVar(&tuiMode, "tui", false, "launch full-screen interactive TUI debugger")
	fs.BoolVar(&tuiCanvas, "tui-canvas", false, "launch full-screen interactive TUI canvas")
	fs.BoolVar(&tuiCanvas, "tui-Canvas", false, "alias for --tui-canvas")
	fs.BoolVar(&renderTUIFrame, "render-tui-frame", false, "render deterministic 4-panel ASCII TUI frame")
	fs.BoolVar(&renderFullScreenTUI, "render-fullscreen-tui", false, "render non-blocking full-screen UTF-8 TUI canvas frame")
	fs.StringVar(&watchCIDsStr, "watch-cid", "", "comma-separated CIDs to watch (e.g. '0,2,3')")
	fs.BoolVar(&breakOnReject, "break-on-reject", false, "trigger watchpoint/breakpoint on REJECT_*")
	fs.BoolVar(&stopOnBreakpoint, "stop-on-breakpoint", false, "halt execution when a watchpoint/breakpoint fires")
	fs.StringVar(&jsonOutPath, "json-out", "", "optional path to write structured JSON report")
	fs.BoolVar(&toKPOL, "to-kpol", false, "transpile input .ekpol program to classic .kpol and print to stdout")
	fs.BoolVar(&toEKPOL, "to-ekpol", false, "transpile input .kpol program or built-in example to .ekpol and print to stdout")
	fs.StringVar(&ekpolStyle, "ekpol-style", "symbolic", "EKPOL formatting style for --to-ekpol: 'symbolic' or 'keyword'")
	fs.BoolVar(&showVersion, "version", false, "print VMK SemVer version and exit")

	if err := fs.Parse(args); err != nil {
		return 2
	}
	if showVersion {
		_, _ = fmt.Fprintf(stdout, "VMK (Virtual Machine of Kuzmin) v%s\n", Version)
		return 0
	}
	if connectAlias != "" {
		target = connectAlias
	}
	if exitOnReject {
		failOnReject = true
	}
	if tuiCanvas {
		tuiMode = true
	}
	target = strings.TrimSpace(target)
	if target == "" {
		target = "sim"
	}
	if err := validateTarget(target); err != nil {
		_, _ = fmt.Fprintln(stderr, err)
		return 2
	}

	exLower := strings.ToLower(strings.TrimSpace(example))

	// Handle --to-kpol and --to-ekpol transpilation flags
	if toKPOL || toEKPOL {
		var src string
		modStem := "EkpolModule"
		if programPath != "" {
			rawBytes, err := os.ReadFile(programPath)
			if err != nil {
				_, _ = fmt.Fprintf(stderr, "VMK-IO: %s: %v\n", programPath, err)
				return 2
			}
			src = string(rawBytes)
			modStem = strings.TrimSuffix(filepath.Base(programPath), filepath.Ext(programPath))
		} else if exLower != "" {
			switch exLower {
			case "increase":
				src = ExampleIncreaseSource
			case "decrease":
				src = ExampleDecreaseSource
			case "cascade":
				src = ExampleCascade4Source
			case "bms":
				src = ExampleBMSSafetyCascadeSource
			default:
				_, _ = fmt.Fprintf(stderr, "VMK-CLI: --to-ekpol/--to-kpol supports examples increase|decrease|cascade|bms or --program\n")
				return 2
			}
		} else {
			_, _ = fmt.Fprintln(stderr, "VMK-CLI: --to-kpol / --to-ekpol requires --program or --example")
			return 2
		}

		if toKPOL {
			outTxt, err := TranspileEKPOLToKPOL(src, modStem)
			if err != nil {
				_, _ = fmt.Fprintf(stderr, "%v\n", err)
				return 2
			}
			_, _ = fmt.Fprint(stdout, outTxt)
			return 0
		}
		// toEKPOL: if input is already .ekpol, transpile to KPOL first then format in requested ekpolStyle
		if strings.EqualFold(filepath.Ext(programPath), ".ekpol") || profile == "EKPOL" {
			kpolTmp, err := TranspileEKPOLToKPOL(src, modStem)
			if err != nil {
				_, _ = fmt.Fprintf(stderr, "%v\n", err)
				return 2
			}
			src = kpolTmp
		}
		outTxt, err := TranspileKPOLToEKPOL(src, ekpolStyle)
		if err != nil {
			_, _ = fmt.Fprintf(stderr, "%v\n", err)
			return 2
		}
		_, _ = fmt.Fprint(stdout, outTxt)
		return 0
	}

	// Check if --program is a conceptual .ekpol program
	var parsedEKPOL *EKPOLProgram
	var rawProgramText string
	if programPath != "" && (strings.EqualFold(filepath.Ext(programPath), ".ekpol") || profile == "EKPOL") {
		rawBytes, err := os.ReadFile(programPath)
		if err != nil {
			_, _ = fmt.Fprintf(stderr, "VMK-IO: %s: %v\n", programPath, err)
			return 2
		}
		rawProgramText = string(rawBytes)
		modStem := strings.TrimSuffix(filepath.Base(programPath), filepath.Ext(programPath))
		parsedEKPOL, err = ParseEKPOL(rawProgramText, modStem)
		if err != nil {
			_, _ = fmt.Fprintf(stderr, "%v\n", err)
			return 2
		}
	}

	if mode == "" {
		if parsedEKPOL != nil && parsedEKPOL.IsConceptualOnly() {
			mode = ModeConceptual
		} else {
			switch exLower {
			case "if", "sum", "nod", "factorial", "tachometer":
				mode = ModeConceptual
			default:
				mode = ModeBRAM64
			}
		}
	}
	if mode != ModeBRAM64 && mode != ModeConceptual {
		_, _ = fmt.Fprintf(stderr, "VMK-CLI: invalid --mode %q (expected 'bram64' or 'conceptual')\n", mode)
		return 2
	}

	// Pure Conceptual mode for conceptual .ekpol file
	if parsedEKPOL != nil && parsedEKPOL.IsConceptualOnly() && mode == ModeConceptual {
		vm, defaultCmds, err := NewConceptualVMFromEKPOL(parsedEKPOL, rawProgramText)
		if err != nil {
			_, _ = fmt.Fprintf(stderr, "%v\n", err)
			return 2
		}
		if tuiMode && !stdioMode && !renderTUIFrame {
			isInteractive := IsCharDeviceTTY(stdin, stdout) || tuiCanvas
			st := NewConceptualFullScreenTUI(vm, defaultCmds)
			frame := RunFullScreenTUI(st, stdin, stdout, isInteractive)
			_, _ = fmt.Fprintln(stdout, frame)
		} else {
			if stdioMode {
				rawIn, err := io.ReadAll(stdin)
				if err != nil {
					_, _ = fmt.Fprintf(stderr, "VMK-IO: %v\n", err)
					return 2
				}
				lines := strings.Split(string(rawIn), "\n")
				var outW, errW io.Writer
				if !tuiMode && !renderTUIFrame && !renderFullScreenTUI {
					outW = stdout
					errW = stderr
				}
				_, err = RunConceptualStdioStream(vm, lines, outW, errW)
				if err != nil {
					_, _ = fmt.Fprintf(stderr, "%v\n", err)
					return 2
				}
			} else if len(defaultCmds) > 0 {
				_, err = RunConceptualStdioStream(vm, defaultCmds, nil, nil)
				if err != nil {
					_, _ = fmt.Fprintf(stderr, "%v\n", err)
					return 2
				}
			}
			statusLbl := "COMPLETED"
			if stdioMode {
				statusLbl = "RUNNING"
			}
			if renderFullScreenTUI {
				_, _ = fmt.Fprintln(stdout, RenderConceptualFullScreenTUI(vm, nil, statusLbl))
			} else if tuiMode || renderTUIFrame || !stdioMode {
				_, _ = fmt.Fprintln(stdout, RenderConceptualTUIFrame(vm, statusLbl))
			}
		}
		if jsonOutPath != "" {
			payload := map[string]any{
				"mode":             ModeConceptual,
				"profile":          "EKPOL",
				"program":          vm.ProgramName,
				"events_processed": vm.EventsProcessed,
				"commits":          vm.Commits,
				"rejects":          vm.Rejects,
				"steps":            vm.Steps,
				"stdout":           vm.StdoutHistory,
				"stderr":           vm.StderrHistory,
			}
			if err := writeJSONFile(jsonOutPath, payload); err != nil {
				_, _ = fmt.Fprintf(stderr, "VMK-IO: %v\n", err)
				return 2
			}
		}
		if failOnReject && vm.Rejects > 0 {
			return 1
		}
		return 0
	}

	isPureConceptualExample := func(name string) bool {
		switch name {
		case "if", "sum", "nod", "factorial", "tachometer":
			return true
		default:
			return false
		}
	}

	// Built-in examples without custom --stdio stream (unless --tui or --render-fullscreen-tui is requested)
	if exLower != "" && !stdioMode && programPath == "" && !tuiMode && !renderFullScreenTUI {
		if exLower == "all" {
			txt, data, err := RunAllExamples()
			if err != nil {
				_, _ = fmt.Fprintf(stderr, "%v\n", err)
				return 2
			}
			_, _ = fmt.Fprintln(stdout, txt)
			if jsonOutPath != "" {
				if err := writeJSONFile(jsonOutPath, data); err != nil {
					_, _ = fmt.Fprintf(stderr, "VMK-IO: %v\n", err)
					return 2
				}
			}
			return 0
		}
		txt, data, err := RunSingleExampleDemo(exLower)
		if err != nil {
			_, _ = fmt.Fprintf(stderr, "%v\n", err)
			return 2
		}
		if mode == ModeConceptual && !isPureConceptualExample(exLower) {
			txt = strings.ReplaceAll(txt, "Mode: bram64", "Mode: conceptual (descriptor-backed)")
			data["mode"] = "conceptual (descriptor-backed)"
		}
		_, _ = fmt.Fprintln(stdout, txt)
		if jsonOutPath != "" {
			if err := writeJSONFile(jsonOutPath, data); err != nil {
				_, _ = fmt.Fprintf(stderr, "VMK-IO: %v\n", err)
				return 2
			}
		}
		if failOnReject && exampleHasRejects(data) {
			return 1
		}
		return 0
	}

	// Pure Conceptual mode (if, sum, nod, factorial, tachometer) with --stdio, --tui, or --render-fullscreen-tui
	if mode == ModeConceptual && programPath == "" && (exLower == "" || isPureConceptualExample(exLower)) {
		exName := exLower
		if exName == "" {
			exName = "sum"
		}
		vm, err := NewConceptualVMForExample(exName)
		if err != nil {
			_, _ = fmt.Fprintf(stderr, "%v\n", err)
			return 2
		}
		defaultExCmds := defaultConceptualCmdsForExample(exName)
		if tuiMode && !stdioMode && !renderTUIFrame {
			isInteractive := IsCharDeviceTTY(stdin, stdout) || tuiCanvas
			st := NewConceptualFullScreenTUI(vm, defaultExCmds)
			frame := RunFullScreenTUI(st, stdin, stdout, isInteractive)
			_, _ = fmt.Fprintln(stdout, frame)
		} else {
			if stdioMode {
				rawIn, err := io.ReadAll(stdin)
				if err != nil {
					_, _ = fmt.Fprintf(stderr, "VMK-IO: %v\n", err)
					return 2
				}
				lines := strings.Split(string(rawIn), "\n")
				var outW, errW io.Writer
				if !tuiMode && !renderTUIFrame && !renderFullScreenTUI {
					outW = stdout
					errW = stderr
				}
				_, err = RunConceptualStdioStream(vm, lines, outW, errW)
				if err != nil {
					_, _ = fmt.Fprintf(stderr, "%v\n", err)
					return 2
				}
			} else if len(defaultExCmds) > 0 {
				_, _ = RunConceptualStdioStream(vm, defaultExCmds, nil, nil)
			}
			if renderFullScreenTUI {
				_, _ = fmt.Fprintln(stdout, RenderConceptualFullScreenTUI(vm, nil, "RUNNING"))
			} else if tuiMode || renderTUIFrame || !stdioMode {
				_, _ = fmt.Fprintln(stdout, RenderConceptualTUIFrame(vm, "RUNNING"))
			}
		}
		if jsonOutPath != "" {
			payload := map[string]any{
				"mode":             ModeConceptual,
				"program":          vm.ProgramName,
				"events_processed": vm.EventsProcessed,
				"commits":          vm.Commits,
				"rejects":          vm.Rejects,
				"steps":            vm.Steps,
				"stdout":           vm.StdoutHistory,
				"stderr":           vm.StderrHistory,
			}
			if err := writeJSONFile(jsonOutPath, payload); err != nil {
				_, _ = fmt.Fprintf(stderr, "VMK-IO: %v\n", err)
				return 2
			}
		}
		if failOnReject && vm.Rejects > 0 {
			return 1
		}
		return 0
	}

	// BRAM64 mode (--program or --example with --stdio)
	var bramImage []byte
	var sourceText string
	var conceptNames []string
	var modName string

	if programPath != "" {
		rawBytes, err := os.ReadFile(programPath)
		if err != nil {
			_, _ = fmt.Fprintf(stderr, "VMK-IO: %s: %v\n", programPath, err)
			return 2
		}
		modName = strings.TrimSuffix(filepath.Base(programPath), filepath.Ext(programPath))
		if len(rawBytes) == 1024 && strings.EqualFold(filepath.Ext(programPath), ".bin") {
			bramImage = rawBytes
		} else {
			sourceText = string(rawBytes)
			if strings.EqualFold(filepath.Ext(programPath), ".ekpol") {
				profile = "EKPOL"
			}
			var comp *CompiledKPOL
			if profile == "EKPOL" {
				comp, err = CompileEKPOLSource(sourceText, modName)
			} else {
				comp, err = CompileKPOLSource(sourceText, profile)
			}
			if err != nil {
				_, _ = fmt.Fprintf(stderr, "%v\n", err)
				return 2
			}
			modName = comp.ModuleName
			conceptNames = comp.ConceptNames
			if comp.ExecDescriptors != nil {
				bramImage = PackBRAM(*comp.ExecDescriptors)
			} else {
				bramImage = comp.BRAMImage
			}
		}
	} else if exLower != "" {
		var src string
		prof := "KPOL-CME-2"
		switch exLower {
		case "increase":
			src = ExampleIncreaseSource
			prof = "KPOL-CME-1"
		case "decrease":
			src = ExampleDecreaseSource
			prof = "KPOL-CME-1"
		case "cascade":
			src = ExampleCascade4Source
		case "bms":
			src = ExampleBMSSafetyCascadeSource
		case "auth":
			src = ExampleAuthCounterSource
			prof = "KPOL-AUTH"
		default:
			_, _ = fmt.Fprintf(stderr, "VMK-CLI: unsupported bram64 example %q\n", exLower)
			return 2
		}
		comp, err := CompileKPOLSource(src, prof)
		if err != nil {
			_, _ = fmt.Fprintf(stderr, "%v\n", err)
			return 2
		}
		profile = prof
		sourceText = src
		modName = comp.ModuleName
		conceptNames = comp.ConceptNames
		if comp.ExecDescriptors != nil {
			bramImage = PackBRAM(*comp.ExecDescriptors)
		} else {
			bramImage = comp.BRAMImage
		}
	} else {
		_, _ = fmt.Fprintln(stderr, "VMK-CLI: either --example or --program is required")
		return 2
	}

	eng, err := NewBRAM64Engine(bramImage, profile, modName, sourceText, conceptNames)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "%v\n", err)
		return 2
	}
	if mode == ModeConceptual {
		eng.ModeLabel = "conceptual (descriptor-backed)"
	}
	eng.BreakOnReject = breakOnReject
	eng.StopOnBreakpoint = stopOnBreakpoint
	if watchCIDsStr != "" {
		for _, tok := range strings.Split(watchCIDsStr, ",") {
			t := strings.TrimSpace(tok)
			if t == "" {
				continue
			}
			cid, err := strconv.ParseInt(t, 0, 32)
			if err != nil {
				_, _ = fmt.Fprintf(stderr, "VMK-CLI: invalid watch CID %q\n", t)
				return 2
			}
			eng.WatchCIDs[int(cid)] = true
		}
	}

	conn, err := NewMachineConnection(target, nil)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "%v\n", err)
		return 2
	}

	var queuedEvents []QueuedEvent
	if traceEvents != "" {
		queuedEvents, err = ParseTraceEventsSpec(traceEvents, eng.Descriptors())
		if err != nil {
			_, _ = fmt.Fprintf(stderr, "%v\n", err)
			return 2
		}
	}

	var stdioRes *StdioExecutionResult
	if stdioMode {
		rawIn, err := io.ReadAll(stdin)
		if err != nil {
			_, _ = fmt.Fprintf(stderr, "VMK-IO: %v\n", err)
			return 2
		}
		lines := strings.Split(string(rawIn), "\n")
		var outW, errW io.Writer
		if !tuiMode && !renderTUIFrame && !renderFullScreenTUI {
			outW = stdout
			errW = stderr
		}
		stdioRes, err = RunStdioStream(eng, lines, nil, outW, errW)
		if err != nil {
			_, _ = fmt.Fprintf(stderr, "%v\n", err)
			return 2
		}
		queuedEvents = stdioRes.StdinRecords
	} else if len(queuedEvents) == 0 && exLower != "" {
		queuedEvents = defaultBRAMEventsForExample(exLower, eng.Descriptors())
	}
	if !stdioMode && len(queuedEvents) > 0 && !tuiMode {
		for _, ev := range queuedEvents {
			eng.StepEvent(ev.CID, ev.Param, ev.ParamValid)
		}
	}

	var pynqHWReport map[string]any
	if target == "sim" {
		var preInitBRAM []byte
		var preNames []string
		if exLower == "bms" {
			if incComp, err := CompileKPOLSource(ExampleIncreaseSource, "KPOL-CME-1"); err == nil {
				preInitBRAM = incComp.BRAMImage
				preNames = incComp.ConceptNames
				conn, _ = NewMachineConnection(target, preInitBRAM)
			}
		}
		if err := conn.LoadProgramIntoSim(bramImage, conceptNames, preNames); err != nil {
			_, _ = fmt.Fprintf(stderr, "%v\n", err)
			return 2
		}
	} else {
		var hwParams []int32
		for _, ev := range queuedEvents {
			if ev.ParamValid {
				hwParams = append(hwParams, ev.Param)
			}
		}
		pynqHWReport, err = conn.ExecutePYNQSession(bramImage, hwParams, conceptNames, nil)
		if err != nil {
			_, _ = fmt.Fprintf(stderr, "%v\n", err)
			return 2
		}
	}

	if tuiMode {
		var pending []QueuedEvent
		if !stdioMode {
			pending = queuedEvents
		}
		isInteractive := (IsCharDeviceTTY(stdin, stdout) || tuiCanvas) && !renderTUIFrame && !stdioMode
		st := NewBRAM64FullScreenTUI(eng, conn, pending, stdioRes)
		frame := RunFullScreenTUI(st, stdin, stdout, isInteractive)
		_, _ = fmt.Fprintln(stdout, frame)
	} else if renderFullScreenTUI {
		_, _ = fmt.Fprintln(stdout, RenderBRAM64FullScreenTUI(eng, conn, nil, stdioRes, "RUNNING"))
	} else if renderTUIFrame {
		_, _ = fmt.Fprintln(stdout, conn.FormatPrePostLoadSummary())
		_, _ = fmt.Fprintln(stdout)
		_, _ = fmt.Fprintln(stdout, RenderBRAM64TUIFrame(eng, conn, stdioRes, "RUNNING"))
	} else if !stdioMode {
		_, _ = fmt.Fprintln(stdout, conn.FormatPrePostLoadSummary())
		_, _ = fmt.Fprintln(stdout)
		if dumpConcepts && len(queuedEvents) == 0 {
			_, _ = fmt.Fprintln(stdout, eng.FormatConceptsTable(false))
		} else {
			_, _ = fmt.Fprintln(stdout, eng.FormatFull4BlockReport())
		}
	}

	if jsonOutPath != "" {
		finalStates := make([]int32, len(eng.ActiveCIDs))
		for i, cid := range eng.ActiveCIDs {
			finalStates[i] = eng.State[cid]
		}
		payload := map[string]any{
			"version": Version,
			"mode":    ModeBRAM64,
			"module":  eng.ModuleName,
			"profile": eng.Profile,
			"target":  target,
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
		}
		if !IsPublicBuild {
			payload["pynq_hw_report"] = pynqHWReport
		}
		if stdioRes != nil {
			payload["stdio"] = map[string]any{
				"stdout": stdioRes.StdoutLines,
				"stderr": stdioRes.StderrLines,
			}
		}
		if err := writeJSONFile(jsonOutPath, payload); err != nil {
			_, _ = fmt.Fprintf(stderr, "VMK-IO: %v\n", err)
			return 2
		}
	}

	if failOnReject && eng.Rejects > 0 {
		return 1
	}
	return 0
}

func defaultConceptualCmdsForExample(name string) []string {
	switch strings.ToLower(strings.TrimSpace(name)) {
	case "if":
		return []string{"write If 1", "write If 1", "write If 1"}
	case "sum":
		return []string{"write Sum 10", "write Sum 25", "read Sum"}
	case "nod":
		return []string{"call Nod 120 6"}
	case "factorial":
		return []string{"call Factorial 5"}
	case "tachometer":
		return []string{"call Tachometer Tick", "call Tachometer Tick", "call Tachometer Tick", "call Tachometer _Tick 1"}
	default:
		return nil
	}
}

func defaultBRAMEventsForExample(name string, descs *[64]ConceptDescriptor) []QueuedEvent {
	var spec string
	switch strings.ToLower(strings.TrimSpace(name)) {
	case "increase":
		spec = "0:5,0:25,0:_"
	case "decrease":
		spec = "0:5,0:5,0:25"
	case "cascade":
		spec = "0:10,0:100,0:10,0:10"
	case "bms":
		spec = "0:15,0:5500,0:_,0:120,0:180,0:250"
	case "auth":
		spec = "0:25,0:-5,0:_"
	default:
		return nil
	}
	evs, _ := ParseTraceEventsSpec(spec, descs)
	return evs
}

func exampleHasRejects(data map[string]any) bool {
	if telem, ok := data["telemetry"].(map[string]any); ok {
		if r, ok := telem["rejects"].(uint32); ok && r > 0 {
			return true
		}
	}
	if r, ok := data["rejects"].(uint32); ok && r > 0 {
		return true
	}
	return false
}

func writeJSONFile(path string, data any) error {
	b, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	return os.WriteFile(path, b, 0644)
}
