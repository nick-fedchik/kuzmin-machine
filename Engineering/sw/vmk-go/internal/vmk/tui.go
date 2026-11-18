package vmk

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"
)

// RenderASCIITable formats headers and rows into a clean bordered ASCII table.
func RenderASCIITable(headers []string, rows [][]string) string {
	widths := make([]int, len(headers))
	for i, h := range headers {
		widths[i] = len(h)
	}
	for _, r := range rows {
		for i := 0; i < len(headers) && i < len(r); i++ {
			if len(r[i]) > widths[i] {
				widths[i] = len(r[i])
			}
		}
	}
	var sepParts []string
	var hdrParts []string
	for i, w := range widths {
		sepParts = append(sepParts, strings.Repeat("-", w))
		hdrParts = append(hdrParts, padRight(headers[i], w))
	}
	sep := "+-" + strings.Join(sepParts, "-+-") + "-+"
	hdrLine := "| " + strings.Join(hdrParts, " | ") + " |"

	out := []string{sep, hdrLine, sep}
	for _, r := range rows {
		var rowParts []string
		for i, w := range widths {
			cell := ""
			if i < len(r) {
				cell = r[i]
			}
			rowParts = append(rowParts, padRight(cell, w))
		}
		out = append(out, "| "+strings.Join(rowParts, " | ")+" |")
	}
	out = append(out, sep)
	return strings.Join(out, "\n")
}

func padRight(s string, width int) string {
	if len(s) >= width {
		return s
	}
	return s + strings.Repeat(" ", width-len(s))
}

// FormatSourceBlock renders Block 1: Source Code / Program Specification.
func (e *BRAM64Engine) FormatSourceBlock() string {
	lines := []string{
		fmt.Sprintf("=== [BLOCK 1] SOURCE CODE / PROGRAM SPECIFICATION (%s, %s) ===", e.ModuleName, e.Profile),
	}
	if e.SourceCode != "" {
		for idx, line := range strings.Split(e.SourceCode, "\n") {
			r := strings.TrimRight(line, " \t\r")
			if r == "" {
				lines = append(lines, fmt.Sprintf("  %02d |", idx+1))
			} else {
				lines = append(lines, fmt.Sprintf("  %02d | %s", idx+1, r))
			}
		}
	} else {
		lines = append(lines, fmt.Sprintf("  Active Concepts (%d): %v", len(e.ActiveCIDs), e.ActiveCIDs))
		lines = append(lines, fmt.Sprintf("  Topological Order: %v", e.TopologicalOrder))
	}
	return strings.Join(lines, "\n")
}

// FormatConceptsTable renders Block 2 (`--dump-concepts`): BRAM Descriptor Table.
func (e *BRAM64Engine) FormatConceptsTable(includeUnconfigured bool) string {
	descs := *e.Descriptors()
	var cids []int
	if includeUnconfigured {
		for i := 0; i < 64; i++ {
			cids = append(cids, i)
		}
	} else {
		cids = append(cids, e.ActiveCIDs...)
	}

	headers := []string{
		"CID",
		"Name",
		"W0 (Init State)",
		"Valid (_)",
		"W1 (Operand)",
		"W2 (Hex & Decoded: Predicate ::, Action, Invariant •)",
		"W3 (Subscriber -> CID)",
	}
	var rows [][]string
	for _, cid := range cids {
		d := descs[cid]
		w0I32 := e.InitialState[cid]
		w0Str := fmt.Sprintf("%d (0x%08X)", w0I32, uint32(w0I32))
		valOK := ((e.ValidMask >> uint(cid)) & 1) != 0
		valStr := "_ (invalid)"
		if valOK {
			valStr = "1 (valid)"
		}
		w1I32 := int32(d.OperandVal)
		w1Str := fmt.Sprintf("%d (0x%08X)", w1I32, d.OperandVal)
		w2U32, w2Dec := DecodeW2Summary(d)
		w2Str := fmt.Sprintf("0x%08X [%s]", w2U32, w2Dec)
		w3Str := fmt.Sprintf("%d (%s)", d.SubscriberCID, DecodeW3Subscriber(d, descs))
		rows = append(rows, []string{
			fmt.Sprintf("C%02d", cid),
			d.Name,
			w0Str,
			valStr,
			w1Str,
			w2Str,
			w3Str,
		})
	}
	return fmt.Sprintf("=== [BLOCK 2] BRAM DESCRIPTOR TABLE (--dump-concepts, %d active of 64 slots) ===\n%s",
		len(cids), RenderASCIITable(headers, rows))
}

// FormatTraceTableSteps renders the 10-column step-by-step cascade trace table for any slice of steps.
func FormatTraceTableSteps(steps []CascadeTraceStep, triggers []WatchpointTrigger) string {
	headers := []string{
		"Step",
		"Depth",
		"CID (Name)",
		"Event(param, valid)",
		"Pre-State",
		"Predicate ::",
		"Candidate",
		"Gate •",
		"Verdict",
		"Post-State",
		"Next Subscriber",
	}
	var rows [][]string
	for _, s := range steps {
		stepLbl := fmt.Sprintf("E%d.%d (#%d)", s.EventID, s.CascadeStep, s.StepIndex)
		depthLbl := strconv.Itoa(s.Depth)
		cidLbl := fmt.Sprintf("C%02d (%s)", s.CID, s.ConceptName)
		if s.CID < 0 || s.CID >= 64 {
			cidLbl = fmt.Sprintf("C%d (%s)", s.CID, s.ConceptName)
		}
		evLbl := s.EventDisplay
		if evLbl == "" {
			evLbl = fmt.Sprintf("param=%d, valid=%s", s.Param, ValidSymbol(s.ParamValid))
		}
		preLbl := s.PreDisplay
		if preLbl == "" {
			preLbl = fmt.Sprintf("W0=%d, valid=%s", s.PreW0, ValidSymbol(s.PreValid))
		}
		predLbl := fmt.Sprintf("%s => %v", s.PredFormula, s.PredMatch)
		ovfTag := ""
		if s.ArithOverflow {
			ovfTag = " [OVF!]"
		}
		candLbl := fmt.Sprintf("%s => %d%s", s.ActionFormula, s.CandidateW0, ovfTag)
		gateLbl := fmt.Sprintf("%s => %v", s.InvFormula, s.InvOK)
		verdictLbl := s.Verdict
		if len(s.WatchpointsHit) > 0 {
			verdictLbl += " *" + strings.Join(s.WatchpointsHit, ",")
		}
		postLbl := s.PostDisplay
		if postLbl == "" {
			postLbl = fmt.Sprintf("W0=%d, valid=%s", s.PostW0, ValidSymbol(s.PostValid))
		}
		nextLbl := "None"
		if s.EnqueuedSubscriberCID != nil && s.EnqueuedSubscriberName != nil {
			nextLbl = fmt.Sprintf("C%02d (%s)", *s.EnqueuedSubscriberCID, *s.EnqueuedSubscriberName)
		}
		rows = append(rows, []string{
			stepLbl,
			depthLbl,
			cidLbl,
			evLbl,
			preLbl,
			predLbl,
			candLbl,
			gateLbl,
			verdictLbl,
			postLbl,
			nextLbl,
		})
	}
	out := []string{
		fmt.Sprintf("=== [BLOCK 3] STEP-BY-STEP EVENT & CASCADE TRACE (--trace-events, %d steps) ===", len(steps)),
		RenderASCIITable(headers, rows),
	}
	if len(triggers) > 0 {
		out = append(out, "Watchpoints / Breakpoints Triggered:")
		for _, wp := range triggers {
			out = append(out, fmt.Sprintf(
				"  * [Step #%d | E%d.%d] C%02d (%s): %s -> %s (W0: %d -> %d, param=%d, valid=%s)",
				wp.StepIndex, wp.EventID, wp.CascadeDepth, wp.CID, wp.ConceptName,
				wp.Reason, wp.Verdict, wp.PreW0, wp.PostW0, wp.Param, ValidSymbol(wp.ParamValid),
			))
		}
	}
	return strings.Join(out, "\n")
}

// FormatTraceTable renders Block 3 (`--trace-events`) for BRAM64Engine.
func (e *BRAM64Engine) FormatTraceTable() string {
	return FormatTraceTableSteps(e.Steps, e.WatchpointTriggers)
}

// FormatStateDiffBlock renders Block 4: State Diff (Before -> After) & Telemetry Counters.
func (e *BRAM64Engine) FormatStateDiffBlock() string {
	descs := *e.Descriptors()
	headers := []string{"CID", "Name", "Before (W0, valid)", "After (W0, valid)", "Delta", "Status"}
	var rows [][]string
	for _, cid := range e.ActiveCIDs {
		d := descs[cid]
		bW0 := e.InitialState[cid]
		aW0 := e.State[cid]
		bOK := ((e.InitialValidMask >> uint(cid)) & 1) != 0
		aOK := ((e.ValidMask >> uint(cid)) & 1) != 0
		delta := aW0 - bW0
		deltaStr := "0"
		if delta != 0 {
			deltaStr = fmt.Sprintf("%+d", delta)
		}
		status := "UNCHANGED"
		if bW0 != aW0 || bOK != aOK {
			status = "CHANGED"
		}
		rows = append(rows, []string{
			fmt.Sprintf("C%02d", cid),
			d.Name,
			fmt.Sprintf("W0=%d, valid=%s", bW0, ValidSymbol(bOK)),
			fmt.Sprintf("W0=%d, valid=%s", aW0, ValidSymbol(aOK)),
			deltaStr,
			status,
		})
	}
	out := []string{
		"=== [BLOCK 4] STATE DIFF (Before -> After) & TELEMETRY COUNTERS ===",
		RenderASCIITable(headers, rows),
		fmt.Sprintf(
			"Telemetry Summary: events_processed=%d, commits=%d, rejects=%d, fault_propagations=%d, last_committed_state=%d",
			e.EventsProcessed, e.Commits, e.Rejects, e.FaultPropagations, e.LastCommittedState,
		),
	}
	return strings.Join(out, "\n")
}

// FormatFull4BlockReport renders all 4 visual blocks for BRAM64Engine.
func (e *BRAM64Engine) FormatFull4BlockReport() string {
	return strings.Join([]string{
		e.FormatSourceBlock(),
		e.FormatConceptsTable(false),
		e.FormatTraceTable(),
		e.FormatStateDiffBlock(),
	}, "\n\n")
}

// RenderBRAM64TUIFrame renders the 4-panel deterministic TUI frame for BRAM64 mode.
func RenderBRAM64TUIFrame(
	eng *BRAM64Engine,
	conn *MachineConnection,
	stdioRes *StdioExecutionResult,
	phaseStatus string,
) string {
	if phaseStatus == "" {
		phaseStatus = "RUNNING"
	}
	descs := *eng.Descriptors()
	topo := AnalyzeConceptTopology(descs)

	targetLbl := "SIM (0x4B504D43 'KPMC')"
	preActive := 0
	postActive := len(eng.ActiveCIDs)
	changedOnLoad := postActive
	preW0Map := make(map[int]string)

	if conn != nil && conn.PreLoadSnapshot != nil {
		preS := conn.PreLoadSnapshot
		preActive = preS.Topology.ActiveConcepts
		targetLbl = fmt.Sprintf("%s (%s '%s')", strings.ToUpper(preS.Target), preS.HWIDHex, preS.HWIDASCII)
		for cid := 0; cid < 64; cid++ {
			d0 := preS.Descriptors[cid]
			if d0.IsConfigured() {
				preW0Map[cid] = strconv.FormatInt(int64(int32(d0.CurrentState)), 10)
			} else {
				preW0Map[cid] = "_ (empty)"
			}
		}
	}
	if conn != nil && conn.PostLoadSnapshot != nil {
		postActive = conn.PostLoadSnapshot.Topology.ActiveConcepts
		changedOnLoad = 0
		for _, d := range conn.LoadDiffs {
			if d.Changed {
				changedOnLoad++
			}
		}
	}

	border := strings.Repeat("=", 118)
	thin := strings.Repeat("-", 118)
	modeLbl := ModeBRAM64
	if eng.ModeLabel != "" {
		modeLbl = eng.ModeLabel
	}

	lines := []string{
		border,
		fmt.Sprintf(" VMK (Virtual Machine of Kuzmin) v%s | Target: %s | Mode: %s | State: PRE-LOAD -> POST-LOAD -> %s",
			Version, targetLbl, modeLbl, phaseStatus),
		fmt.Sprintf(" Concepts: Active: %d / %d (Pre-load: %d / %d, Changed on load: %d, Free: %d) | Entry: %v Internal: %v Leaf: %v",
			postActive, topo.TotalSlots, preActive, topo.TotalSlots, changedOnLoad, topo.FreeSlots,
			topo.EntryConcepts, topo.InternalCascadeConcepts, topo.LeafConcepts),
		fmt.Sprintf(" Counters: Events=%d | Commits=%d | Rejects=%d | Faults(_)=%d | Dropped=%d | Bank=%d | LastState=%d",
			eng.EventsProcessed, eng.Commits, eng.Rejects, eng.FaultPropagations, eng.DroppedEvents, eng.ActiveBank, eng.LastCommittedState),
		border,
		" [PANEL 1: CONCEPT TABLE (PRE-LOAD vs POST-LOAD vs CURRENT STATE)]",
	}

	cHeaders := []string{
		"CID",
		"Name",
		"Type",
		"Pre-Load W0",
		"Post-Load W0",
		"Current W0 (Δ)",
		"Valid(_)",
		"Predicate ::",
		"Action",
		"Gate •",
		"Subscriber",
	}
	var cRows [][]string
	for _, cid := range eng.ActiveCIDs {
		d := descs[cid]
		preW0 := "_ (n/a)"
		if v, ok := preW0Map[cid]; ok {
			preW0 = v
		}
		postW0 := strconv.FormatInt(int64(eng.InitialState[cid]), 10)
		curW0 := strconv.FormatInt(int64(eng.State[cid]), 10)
		if eng.State[cid] != eng.InitialState[cid] {
			curW0 += fmt.Sprintf(" (%+d)", eng.State[cid]-eng.InitialState[cid])
		}
		valOK := ((eng.ValidMask >> uint(cid)) & 1) != 0
		cRows = append(cRows, []string{
			fmt.Sprintf("C%02d", cid),
			d.Name,
			d.TypeName,
			preW0,
			postW0,
			curW0,
			ValidSymbol(valOK),
			DecodePredicateFormula(d),
			DecodeActionFormula(d),
			DecodeInvariantFormula(d),
			DecodeW3Subscriber(d, descs),
		})
	}
	lines = append(lines, RenderASCIITable(cHeaders, cRows))

	lines = append(lines, thin)
	lines = append(lines, " [PANEL 2: PROGRAM SOURCE CODE & LIVE STDIO STREAMS (STDIN / STDOUT / STDERR)]")
	if eng.SourceCode != "" {
		srcLines := strings.Split(eng.SourceCode, "\n")
		if len(srcLines) > 12 {
			srcLines = srcLines[:12]
		}
		for idx, sl := range srcLines {
			r := strings.TrimRight(sl, " \t\r")
			if r == "" {
				lines = append(lines, fmt.Sprintf("   SRC %02d |", idx+1))
			} else {
				lines = append(lines, fmt.Sprintf("   SRC %02d | %s", idx+1, r))
			}
		}
	}
	if stdioRes != nil {
		var inParts []string
		for _, rec := range stdioRes.StdinRecords {
			inParts = append(inParts, fmt.Sprintf("(C%d:%d,valid=%s)", rec.CID, rec.Param, ValidSymbol(rec.ParamValid)))
		}
		inStr := "(empty)"
		if len(inParts) > 0 {
			inStr = strings.Join(inParts, ", ")
		}
		lines = append(lines, fmt.Sprintf("   STDIN  (%d events) : %s", len(stdioRes.StdinRecords), inStr))
		for _, outL := range stdioRes.StdoutLines {
			lines = append(lines, fmt.Sprintf("   STDOUT -> %s", outL))
		}
		for _, errL := range stdioRes.StderrLines {
			lines = append(lines, fmt.Sprintf("   STDERR -> %s", errL))
		}
	} else {
		var rootEvs []string
		for _, s := range eng.Steps {
			if s.Depth == 0 {
				rootEvs = append(rootEvs, fmt.Sprintf("(C%d:%d,valid=%s)", s.CID, s.Param, ValidSymbol(s.ParamValid)))
			}
		}
		inStr := "(empty)"
		if len(rootEvs) > 0 {
			inStr = strings.Join(rootEvs, ", ")
		}
		lines = append(lines, fmt.Sprintf("   STDIN  (%d root events): %s", len(rootEvs), inStr))
		for _, s := range eng.Steps {
			if s.Verdict == VerdictCommit || s.Verdict == VerdictSuppressedSelf {
				lines = append(lines, fmt.Sprintf("   STDOUT -> COMMIT: %s[cid=%d] = %d (depth=%d)", s.ConceptName, s.CID, s.PostW0, s.Depth))
			} else {
				lines = append(lines, fmt.Sprintf("   STDERR -> %s: %s[cid=%d] kept W0=%d (depth=%d)", s.Verdict, s.ConceptName, s.CID, s.PostW0, s.Depth))
			}
		}
	}

	lines = append(lines, thin)
	lines = append(lines, " [PANEL 3: CASCADE WAVE STEP TRACE]")
	lines = append(lines, eng.FormatTraceTable())
	lines = append(lines, border)
	lines = append(lines, " KEYS: [s] Step Next Event | [i] Input STDIN | [f] Inject Fault (_) | [r] Reload BRAM | [q] Quit")
	lines = append(lines, border)
	return strings.Join(lines, "\n")
}

// RenderConceptualTUIFrame renders the 4-panel deterministic TUI frame for Conceptual mode (RFC-001..018).
func RenderConceptualTUIFrame(vm *ConceptualVM, phaseStatus string) string {
	if phaseStatus == "" {
		phaseStatus = "RUNNING"
	}
	activeCount := len(vm.Slots)
	changedOnLoad := activeCount - vm.PreLoadActive
	if changedOnLoad < 0 {
		changedOnLoad = activeCount
	}
	freeSlots := vm.Capacity - activeCount

	border := strings.Repeat("=", 118)
	thin := strings.Repeat("-", 118)

	lines := []string{
		border,
		fmt.Sprintf(" VMK (Virtual Machine of Kuzmin) v%s | Target: SIM (RFC-001..018) | Mode: %s | State: PRE-LOAD -> POST-LOAD -> %s",
			Version, ModeConceptual, phaseStatus),
		fmt.Sprintf(" Concepts: Active: %d / %d (Pre-load: %d / %d, Changed on load: %d, Free: %d) | Program: %s",
			activeCount, vm.Capacity, vm.PreLoadActive, vm.Capacity, changedOnLoad, freeSlots, vm.ProgramName),
		fmt.Sprintf(" Counters: Events=%d | Commits=%d | Rejects=%d | Faults(_)=%d | LastState=%d",
			vm.EventsProcessed, vm.Commits, vm.Rejects, vm.FaultPropagations, vm.LastCommittedState),
		border,
		" [PANEL 1: CONCEPT TABLE (PRE-LOAD vs POST-LOAD vs CURRENT STATE)]",
	}

	cHeaders := []string{
		"CID",
		"Name",
		"Type",
		"Pre-Load W0",
		"Post-Load W0",
		"Current W0 (Δ)",
		"Valid(_)",
		"Predicate ::",
		"Action",
		"Gate •",
		"Subscriber",
	}
	var cRows [][]string
	for _, s := range vm.Slots {
		preW0 := "_ (empty)"
		if s.Type == TypeStream {
			preW0 = "0 (stream)"
		}
		postW0 := s.FormatInitValue()
		curW0 := s.FormatValue()
		cRows = append(cRows, []string{
			fmt.Sprintf("C%02d", s.CID),
			s.Name,
			string(s.Type),
			preW0,
			postW0,
			curW0,
			ValidSymbol(s.Valid),
			s.RuleSummary,
			s.RuleSummary,
			s.GateSummary,
			s.SubSummary,
		})
	}
	lines = append(lines, RenderASCIITable(cHeaders, cRows))

	lines = append(lines, thin)
	lines = append(lines, " [PANEL 2: PROGRAM SOURCE CODE & LIVE STDIO STREAMS (STDIN / STDOUT / STDERR)]")
	for idx, sl := range strings.Split(vm.SourceCode, "\n") {
		r := strings.TrimRight(sl, " \t\r")
		if r == "" {
			lines = append(lines, fmt.Sprintf("   SRC %02d |", idx+1))
		} else {
			lines = append(lines, fmt.Sprintf("   SRC %02d | %s", idx+1, r))
		}
	}
	inStr := "(empty)"
	if len(vm.StdinHistory) > 0 {
		inStr = strings.Join(vm.StdinHistory, " ; ")
	}
	lines = append(lines, fmt.Sprintf("   STDIN  (%d cmds) : %s", len(vm.StdinHistory), inStr))
	for _, outL := range vm.StdoutHistory {
		lines = append(lines, fmt.Sprintf("   STDOUT -> %s", outL))
	}
	for _, errL := range vm.StderrHistory {
		lines = append(lines, fmt.Sprintf("   STDERR -> %s", errL))
	}

	lines = append(lines, thin)
	lines = append(lines, " [PANEL 3: CASCADE WAVE STEP TRACE]")
	lines = append(lines, FormatTraceTableSteps(vm.Steps, nil))
	lines = append(lines, border)
	lines = append(lines, " KEYS: [s] Step Next Event | [i] Input STDIN | [f] Inject Fault (_) | [r] Reload BRAM | [q] Quit")
	lines = append(lines, border)
	return strings.Join(lines, "\n")
}

// RunInteractiveBRAM64TUI runs an interactive terminal loop if stdin/stdout is a TTY, or renders a deterministic frame.
func RunInteractiveBRAM64TUI(
	eng *BRAM64Engine,
	conn *MachineConnection,
	pendingEvents []QueuedEvent,
	stdioRes *StdioExecutionResult,
	in io.Reader,
	out io.Writer,
	interactive bool,
) string {
	queue := append([]QueuedEvent(nil), pendingEvents...)
	if !interactive {
		for _, ev := range queue {
			eng.StepEvent(ev.CID, ev.Param, ev.ParamValid)
		}
		return RenderBRAM64TUIFrame(eng, conn, stdioRes, "RUNNING")
	}

	scanner := bufio.NewScanner(in)
	for {
		frame := RenderBRAM64TUIFrame(eng, conn, stdioRes, "INTERACTIVE")
		_, _ = fmt.Fprintln(out, "\033[2J\033[H"+frame)
		_, _ = fmt.Fprint(out, "vmk-tui [s/i/f/r/q]> ")
		if !scanner.Scan() {
			break
		}
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			line = "s"
		}
		cmd := strings.ToLower(line[:1])
		if cmd == "q" {
			break
		}
		switch cmd {
		case "s":
			if len(queue) > 0 {
				ev := queue[0]
				queue = queue[1:]
				eng.StepEvent(ev.CID, ev.Param, ev.ParamValid)
			}
		case "f":
			rootCID := 0
			if len(eng.ActiveCIDs) > 0 {
				rootCID = eng.ActiveCIDs[0]
			}
			eng.StepEvent(rootCID, 0, false)
		case "r":
			eng.Reset()
			queue = append([]QueuedEvent(nil), pendingEvents...)
		case "i":
			arg := strings.TrimSpace(line[1:])
			if arg != "" {
				if ev, err := ParseStdioInputLine(arg, *eng.Descriptors(), 0); err == nil && ev != nil {
					eng.StepEvent(ev.CID, ev.Param, ev.ParamValid)
				}
			}
		}
	}
	return RenderBRAM64TUIFrame(eng, conn, stdioRes, "COMPLETED")
}

// IsCharDeviceTTY returns true if both in and out are *os.File character devices (interactive terminal).
func IsCharDeviceTTY(in io.Reader, out io.Writer) bool {
	inFile, okIn := in.(*os.File)
	outFile, okOut := out.(*os.File)
	if !okIn || !okOut {
		return false
	}
	inInfo, errIn := inFile.Stat()
	outInfo, errOut := outFile.Stat()
	if errIn != nil || errOut != nil {
		return false
	}
	return (inInfo.Mode()&os.ModeCharDevice) != 0 && (outInfo.Mode()&os.ModeCharDevice) != 0
}
