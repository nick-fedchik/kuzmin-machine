package vmk

import (
	"fmt"
	"io"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"unicode/utf8"
)

// ANSI escape codes for alternate screen, cursor visibility, and colors.
const (
	ANSIEnterAltScreen = "\x1b[?1049h\x1b[?25l"
	ANSIExitAltScreen  = "\x1b[?25h\x1b[?1049l\x1b[0m"
	ANSIClearHome      = "\x1b[2J\x1b[H"

	ANSIReset     = "\x1b[0m"
	ANSIBold      = "\x1b[1m"
	ANSIHeaderInv = "\x1b[1;37;44m"
	ANSISubHdrInv = "\x1b[0;30;47m"
	ANSIGreen     = "\x1b[1;32m"
	ANSIYellow    = "\x1b[1;33m"
	ANSIRed       = "\x1b[1;31m"
	ANSICyan      = "\x1b[1;36m"
	ANSIDim       = "\x1b[2m"
)

// Default full-screen TUI geometry when running on non-TTY or uninitialized winsize.
const (
	DefaultTUIRows = 36
	DefaultTUICols = 124
)

// KeyKind identifies a decoded terminal keystroke or escape sequence.
type KeyKind string

const (
	KeyEOF       KeyKind = "EOF"
	KeyRune      KeyKind = "RUNE"
	KeyUp        KeyKind = "UP"
	KeyDown      KeyKind = "DOWN"
	KeyLeft      KeyKind = "LEFT"
	KeyRight     KeyKind = "RIGHT"
	KeyPageUp    KeyKind = "PGUP"
	KeyPageDown  KeyKind = "PGDN"
	KeyTab       KeyKind = "TAB"
	KeyEnter     KeyKind = "ENTER"
	KeySpace     KeyKind = "SPACE"
	KeyBackspace KeyKind = "BACKSPACE"
	KeyEsc       KeyKind = "ESC"
)

// KeyEvent represents a single decoded key press from raw terminal or test stream.
type KeyEvent struct {
	Kind KeyKind
	Ch   rune
}

// ReadNextKeyEvent decodes one keystroke (including ANSI CSI arrow / PageUp / PageDown sequences) from r.
func ReadNextKeyEvent(r io.Reader) (KeyEvent, error) {
	var b [1]byte
	n, err := r.Read(b[:])
	if n == 0 {
		if err != nil {
			return KeyEvent{Kind: KeyEOF}, err
		}
		return KeyEvent{Kind: KeyEOF}, io.EOF
	}
	c := b[0]
	switch c {
	case 0x03, 0x04: // Ctrl+C, Ctrl+D
		return KeyEvent{Kind: KeyRune, Ch: 'q'}, nil
	case '\t':
		return KeyEvent{Kind: KeyTab}, nil
	case '\r', '\n':
		return KeyEvent{Kind: KeyEnter}, nil
	case ' ':
		return KeyEvent{Kind: KeySpace, Ch: ' '}, nil
	case 0x7f, 0x08:
		return KeyEvent{Kind: KeyBackspace}, nil
	case 0x1b: // ESC or CSI sequence
		var seq [2]byte
		n1, _ := r.Read(seq[0:1])
		if n1 == 0 {
			return KeyEvent{Kind: KeyEsc}, nil
		}
		if seq[0] == '[' || seq[0] == 'O' {
			n2, _ := r.Read(seq[1:2])
			if n2 == 0 {
				return KeyEvent{Kind: KeyEsc}, nil
			}
			switch seq[1] {
			case 'A':
				return KeyEvent{Kind: KeyUp}, nil
			case 'B':
				return KeyEvent{Kind: KeyDown}, nil
			case 'C':
				return KeyEvent{Kind: KeyRight}, nil
			case 'D':
				return KeyEvent{Kind: KeyLeft}, nil
			case '5':
				_, _ = r.Read(b[:]) // consume '~'
				return KeyEvent{Kind: KeyPageUp}, nil
			case '6':
				_, _ = r.Read(b[:]) // consume '~'
				return KeyEvent{Kind: KeyPageDown}, nil
			}
		}
		return KeyEvent{Kind: KeyEsc}, nil
	default:
		return KeyEvent{Kind: KeyRune, Ch: rune(c)}, nil
	}
}

// InspectorViewMode controls what Panel [2] displays: Inspector card, Source Code, or Pre/Post-Load Diff.
type InspectorViewMode int

const (
	ViewConceptInspector InspectorViewMode = iota
	ViewSourceCode
	ViewPrePostDiff
)

func (m InspectorViewMode) String() string {
	switch m {
	case ViewSourceCode:
		return "SOURCE CODE (.ekpol / .kpol)"
	case ViewPrePostDiff:
		return "PRE-LOAD vs POST-LOAD DIFF"
	default:
		return "CONCEPT INSPECTOR"
	}
}

// ModalDialogKind identifies the active modal dialog in the TUI.
type ModalDialogKind int

const (
	ModalNone ModalDialogKind = iota
	ModalEventCreator
	ModalModifyState
	ModalHelp
)

// ManualEventOp identifies the operation type in the Manual Event Creator dialog.
type ManualEventOp int

const (
	OpWriteStimulus ManualEventOp = iota // 1: Write / Stimulus (<-)
	OpInjectFault                        // 2: Inject Undefined / Sensor Fault (_)
	OpReadConcept                        // 3: Read (->)
	OpCallConcept                        // 4: Call (|)
)

func (op ManualEventOp) Label() string {
	switch op {
	case OpWriteStimulus:
		return "1:Write/Stimulus(<-)"
	case OpInjectFault:
		return "2:Fault/Undef(_)"
	case OpReadConcept:
		return "3:Read(->)"
	case OpCallConcept:
		return "4:Call(|)"
	default:
		return "1:Write(<-)"
	}
}

// FullScreenTUIState holds the complete state of the interactive full-screen TUI debugger (`VMK v0.3.1`).
type FullScreenTUIState struct {
	Mode              string
	Engine            *BRAM64Engine
	Conceptual        *ConceptualVM
	Conn              *MachineConnection
	InitialQueue      []QueuedEvent
	PendingQueue      []QueuedEvent
	StdioRes          *StdioExecutionResult
	StdinLines        []string
	StdoutLines       []string
	StderrLines       []string
	ConceptualWatch   map[int]bool
	SelectedIdx       int
	ShowAll64Slots    bool
	FocusPanel        int // 0=[1] Concepts, 1=[2] Inspector/Source/Diff, 2=[3] Wave Trace, 3=[4] STDIO
	Panel2Mode        InspectorViewMode
	TraceScroll       int
	SourceScroll      int
	StdioScroll       int
	Modal             ModalDialogKind
	EventTargetCID    int
	EventOp           ManualEventOp
	EventInputBuf     string
	ModifyInputBuf    string
	ModifyValidToggle bool
	StatusBanner      string
	Phase             string
	UseColor          bool
	Rows              int
	Cols              int
}

// NewBRAM64FullScreenTUI creates a FullScreenTUIState for a BRAM64Engine session.
func NewBRAM64FullScreenTUI(
	eng *BRAM64Engine,
	conn *MachineConnection,
	pending []QueuedEvent,
	stdioRes *StdioExecutionResult,
) *FullScreenTUIState {
	st := &FullScreenTUIState{
		Mode:              ModeBRAM64,
		Engine:            eng,
		Conn:              conn,
		InitialQueue:      append([]QueuedEvent(nil), pending...),
		PendingQueue:      append([]QueuedEvent(nil), pending...),
		StdioRes:          stdioRes,
		ConceptualWatch:   make(map[int]bool),
		SelectedIdx:       0,
		FocusPanel:        0,
		Panel2Mode:        ViewConceptInspector,
		EventOp:           OpWriteStimulus,
		ModifyValidToggle: true,
		StatusBanner:      "Ready. Use Up/Down to select concept, [e] New Event, [n/Space] 1-Hop, [s] Full Step, [d] Inspector/Source/Diff, [q] Quit.",
		Phase:             "INTERACTIVE",
		Rows:              DefaultTUIRows,
		Cols:              DefaultTUICols,
	}
	if stdioRes != nil {
		for _, r := range stdioRes.StdinRecords {
			st.StdinLines = append(st.StdinLines, fmt.Sprintf("C%02d <- param=%d, valid=%s", r.CID, r.Param, ValidSymbol(r.ParamValid)))
		}
		st.StdoutLines = append(st.StdoutLines, stdioRes.StdoutLines...)
		st.StderrLines = append(st.StderrLines, stdioRes.StderrLines...)
	} else {
		st.syncBRAMStdioFromSteps()
	}
	return st
}

// NewConceptualFullScreenTUI creates a FullScreenTUIState for a ConceptualVM session.
func NewConceptualFullScreenTUI(vm *ConceptualVM, pendingCmds []string) *FullScreenTUIState {
	var q []QueuedEvent
	for _, cmd := range pendingCmds {
		c := strings.TrimSpace(cmd)
		if c == "" {
			continue
		}
		q = append(q, parseConceptualCommandToQueuedEvent(vm, c))
	}
	st := &FullScreenTUIState{
		Mode:              ModeConceptual,
		Conceptual:        vm,
		InitialQueue:      append([]QueuedEvent(nil), q...),
		PendingQueue:      append([]QueuedEvent(nil), q...),
		ConceptualWatch:   make(map[int]bool),
		SelectedIdx:       0,
		FocusPanel:        0,
		Panel2Mode:        ViewConceptInspector,
		EventOp:           OpWriteStimulus,
		ModifyValidToggle: true,
		StatusBanner:      "Ready (Conceptual VM). Use Up/Down to select concept, [e] New Event, [n/Space] Step, [m] Modify, [d] Diff/Source, [q] Quit.",
		Phase:             "INTERACTIVE",
		Rows:              DefaultTUIRows,
		Cols:              DefaultTUICols,
	}
	st.StdinLines = append(st.StdinLines, vm.StdinHistory...)
	st.StdoutLines = append(st.StdoutLines, vm.StdoutHistory...)
	st.StderrLines = append(st.StderrLines, vm.StderrHistory...)
	return st
}

func parseConceptualCommandToQueuedEvent(vm *ConceptualVM, cmdLine string) QueuedEvent {
	parts := strings.Fields(cmdLine)
	if len(parts) == 0 {
		return QueuedEvent{CID: 0, Param: 0, ParamValid: true, OpKind: "write", CmdLine: cmdLine}
	}
	verb := strings.ToLower(parts[0])
	targetCID := 0
	if len(parts) >= 2 {
		if cid, ok := vm.NameToCID[strings.ToLower(parts[1])]; ok {
			targetCID = cid
		}
	}
	var param int32
	valid := true
	if len(parts) >= 3 {
		if parts[2] == "_" || strings.EqualFold(parts[2], "invalid") {
			valid = false
		} else if iv, err := strconv.ParseInt(parts[2], 0, 32); err == nil {
			param = int32(iv)
		}
	}
	return QueuedEvent{
		CID:        targetCID,
		Param:      param,
		ParamValid: valid,
		OpKind:     verb,
		CmdLine:    cmdLine,
	}
}

func (s *FullScreenTUIState) syncBRAMStdioFromSteps() {
	if s.Engine == nil {
		return
	}
	s.StdinLines = nil
	s.StdoutLines = nil
	s.StderrLines = nil
	for _, st := range s.Engine.Steps {
		if st.Depth == 0 {
			s.StdinLines = append(s.StdinLines, fmt.Sprintf("E%d: C%02d(%s) <- param=%d, valid=%s",
				st.EventID, st.CID, st.ConceptName, st.Param, ValidSymbol(st.ParamValid)))
		}
		if st.Verdict == VerdictCommit || st.Verdict == VerdictSuppressedSelf {
			s.StdoutLines = append(s.StdoutLines, fmt.Sprintf("COMMIT: %s[cid=%d] = %d (pre=%d, depth=%d, param=%d)",
				st.ConceptName, st.CID, st.PostW0, st.PreW0, st.Depth, st.Param))
		} else {
			s.StderrLines = append(s.StderrLines, fmt.Sprintf("%s: %s[cid=%d] kept W0=%d (depth=%d, param=%d, valid=%s)",
				st.Verdict, st.ConceptName, st.CID, st.PostW0, st.Depth, st.Param, ValidSymbol(st.ParamValid)))
		}
	}
}

func (s *FullScreenTUIState) visibleCIDs() []int {
	if s.Engine != nil {
		if s.ShowAll64Slots {
			cids := make([]int, 64)
			for i := 0; i < 64; i++ {
				cids[i] = i
			}
			return cids
		}
		if len(s.Engine.ActiveCIDs) > 0 {
			return s.Engine.ActiveCIDs
		}
		return []int{0}
	}
	if s.Conceptual != nil {
		cids := make([]int, len(s.Conceptual.Slots))
		for i := range s.Conceptual.Slots {
			cids[i] = s.Conceptual.Slots[i].CID
		}
		return cids
	}
	return []int{0}
}

// SelectedCID returns the currently highlighted concept CID in Panel [1].
func (s *FullScreenTUIState) SelectedCID() int {
	cids := s.visibleCIDs()
	if len(cids) == 0 {
		return 0
	}
	if s.SelectedIdx < 0 {
		s.SelectedIdx = 0
	}
	if s.SelectedIdx >= len(cids) {
		s.SelectedIdx = len(cids) - 1
	}
	return cids[s.SelectedIdx]
}

func (s *FullScreenTUIState) selectCID(cid int) {
	cids := s.visibleCIDs()
	for i, c := range cids {
		if c == cid {
			s.SelectedIdx = i
			return
		}
	}
}

// ExecuteSingleMicroStep executes [n] / [Space]: 1 single cascade hop (C0 -> enqueues C1 into PendingQueue).
func (s *FullScreenTUIState) ExecuteSingleMicroStep() {
	if s.Engine != nil {
		if len(s.PendingQueue) == 0 {
			cid := s.SelectedCID()
			s.PendingQueue = append(s.PendingQueue, QueuedEvent{
				CID:        cid,
				Param:      1,
				ParamValid: true,
				Depth:      0,
				OpKind:     "write",
			})
		}
		ev := s.PendingQueue[0]
		s.PendingQueue = s.PendingQueue[1:]
		step, nextHop := s.Engine.StepSingleHop(ev)
		if nextHop != nil {
			// Prepend the immediate cascade subscriber hop to the front of PendingQueue so the wave hops C0 -> C1 -> C2 -> C3!
			s.PendingQueue = append([]QueuedEvent{*nextHop}, s.PendingQueue...)
		}
		s.syncBRAMStdioFromSteps()
		s.selectCID(step.CID)
		nextInfo := "Wave settled"
		if nextHop != nil {
			nextInfo = fmt.Sprintf("Next hop queued -> C%02d (param=%d)", nextHop.CID, nextHop.Param)
		}
		s.StatusBanner = fmt.Sprintf("Micro-Hop E%d.%d: C%02d (%s) param=%d, valid=%s => %s (W0: %d -> %d) | %s",
			step.EventID, step.Depth, step.CID, step.ConceptName, step.Param, ValidSymbol(step.ParamValid),
			step.Verdict, step.PreW0, step.PostW0, nextInfo)
		return
	}

	if s.Conceptual != nil {
		if len(s.PendingQueue) > 0 {
			ev := s.PendingQueue[0]
			s.PendingQueue = s.PendingQueue[1:]
			s.executeConceptualEvent(ev)
			return
		}
		cid := s.SelectedCID()
		st := s.Conceptual.ExecuteGenericWrite(cid, 1, true)
		s.StdinLines = append(s.StdinLines, st.EventDisplay)
		s.StdoutLines = append([]string(nil), s.Conceptual.StdoutHistory...)
		s.StderrLines = append([]string(nil), s.Conceptual.StderrHistory...)
		s.StatusBanner = fmt.Sprintf("Conceptual Hop: C%02d (%s) => %s (%s -> %s)",
			st.CID, st.ConceptName, st.Verdict, st.PreDisplay, st.PostDisplay)
	}
}

// ExecuteFullEventStep executes [s]: pops the next event (and any remaining hops of the current wave) and runs until cascade stabilization.
func (s *FullScreenTUIState) ExecuteFullEventStep() {
	if s.Engine != nil {
		if len(s.PendingQueue) == 0 {
			cid := s.SelectedCID()
			s.PendingQueue = append(s.PendingQueue, QueuedEvent{
				CID:        cid,
				Param:      1,
				ParamValid: true,
			})
		}
		ev := s.PendingQueue[0]
		s.PendingQueue = s.PendingQueue[1:]
		if ev.IsHop {
			var hops int
			var lastStep CascadeTraceStep
			cur := &ev
			for cur != nil {
				hops++
				st, next := s.Engine.StepSingleHop(*cur)
				lastStep = st
				cur = next
			}
			s.syncBRAMStdioFromSteps()
			s.selectCID(lastStep.CID)
			s.StatusBanner = fmt.Sprintf("Completed active wave (%d hop(s)): last C%02d (%s) => %s (W0=%d)",
				hops, lastStep.CID, lastStep.ConceptName, lastStep.Verdict, lastStep.PostW0)
			return
		}
		wave := s.Engine.StepEvent(ev.CID, ev.Param, ev.ParamValid)
		s.syncBRAMStdioFromSteps()
		if len(wave) > 0 {
			last := wave[len(wave)-1]
			s.selectCID(last.CID)
			s.StatusBanner = fmt.Sprintf("Full Event E%d on C%02d: %d cascade step(s), final C%02d (%s) => %s (W0=%d)",
				last.EventID, ev.CID, len(wave), last.CID, last.ConceptName, last.Verdict, last.PostW0)
		}
		return
	}

	if s.Conceptual != nil {
		if len(s.PendingQueue) > 0 {
			ev := s.PendingQueue[0]
			s.PendingQueue = s.PendingQueue[1:]
			s.executeConceptualEvent(ev)
			return
		}
		s.ExecuteSingleMicroStep()
	}
}

func (s *FullScreenTUIState) executeConceptualEvent(ev QueuedEvent) {
	if s.Conceptual == nil {
		return
	}
	if ev.CmdLine != "" {
		_, err := RunConceptualStdioStream(s.Conceptual, []string{ev.CmdLine}, nil, nil)
		s.StdinLines = append([]string(nil), s.Conceptual.StdinHistory...)
		s.StdoutLines = append([]string(nil), s.Conceptual.StdoutHistory...)
		s.StderrLines = append([]string(nil), s.Conceptual.StderrHistory...)
		if err != nil {
			s.StatusBanner = fmt.Sprintf("Event Error: %v", err)
		} else {
			s.StatusBanner = fmt.Sprintf("Executed Conceptual Command: %s", ev.CmdLine)
		}
		return
	}
	st := s.Conceptual.ExecuteGenericWrite(ev.CID, ev.Param, ev.ParamValid)
	s.StdinLines = append(s.StdinLines, st.EventDisplay)
	s.StdoutLines = append([]string(nil), s.Conceptual.StdoutHistory...)
	s.StderrLines = append([]string(nil), s.Conceptual.StderrHistory...)
	s.StatusBanner = fmt.Sprintf("Executed C%02d (%s): %s -> %s (%s)",
		st.CID, st.ConceptName, st.PreDisplay, st.PostDisplay, st.Verdict)
}

// InjectFaultOnSelected executes [f]: immediately injects an undefined / sensor fault '_' event on the selected concept.
func (s *FullScreenTUIState) InjectFaultOnSelected() {
	cid := s.SelectedCID()
	if s.Engine != nil {
		st, _ := s.Engine.StepSingleHop(QueuedEvent{
			CID:        cid,
			Param:      0,
			ParamValid: false,
			Depth:      0,
			OpKind:     "fault",
		})
		s.syncBRAMStdioFromSteps()
		s.StatusBanner = fmt.Sprintf("Injected Fault '_' on C%02d (%s) => %s (kept W0=%d, Faults=%d)",
			cid, st.ConceptName, st.Verdict, st.PostW0, s.Engine.FaultPropagations)
		return
	}
	if s.Conceptual != nil {
		st := s.Conceptual.ExecuteGenericWrite(cid, 0, false)
		s.StdinLines = append(s.StdinLines, st.EventDisplay)
		s.StdoutLines = append([]string(nil), s.Conceptual.StdoutHistory...)
		s.StderrLines = append([]string(nil), s.Conceptual.StderrHistory...)
		s.StatusBanner = fmt.Sprintf("Injected Fault '_' on C%02d (%s) => %s (kept %s, Faults=%d)",
			cid, st.ConceptName, st.Verdict, st.PostDisplay, s.Conceptual.FaultPropagations)
	}
}

// ToggleWatchpointOnSelected executes [w]: toggles watchpoint on the currently selected concept.
func (s *FullScreenTUIState) ToggleWatchpointOnSelected() {
	cid := s.SelectedCID()
	if s.Engine != nil {
		if s.Engine.WatchCIDs[cid] {
			delete(s.Engine.WatchCIDs, cid)
			s.StatusBanner = fmt.Sprintf("Watchpoint removed from C%02d (%s)", cid, s.Engine.Descriptors()[cid].Name)
		} else {
			s.Engine.WatchCIDs[cid] = true
			s.StatusBanner = fmt.Sprintf("Watchpoint (*) set on C%02d (%s)", cid, s.Engine.Descriptors()[cid].Name)
		}
		return
	}
	if s.Conceptual != nil {
		if s.ConceptualWatch[cid] {
			delete(s.ConceptualWatch, cid)
			s.StatusBanner = fmt.Sprintf("Watchpoint removed from C%02d", cid)
		} else {
			s.ConceptualWatch[cid] = true
			s.StatusBanner = fmt.Sprintf("Watchpoint (*) set on C%02d", cid)
		}
	}
}

// ResetToPostLoad executes [r]: resets all concept states, counters, and queues back to POST-LOAD state.
func (s *FullScreenTUIState) ResetToPostLoad() {
	s.PendingQueue = append([]QueuedEvent(nil), s.InitialQueue...)
	s.TraceScroll = 0
	s.StdioScroll = 0
	if s.Engine != nil {
		s.Engine.Reset()
		s.syncBRAMStdioFromSteps()
		s.StatusBanner = "Reset to POST-LOAD state (all W0 states, ValidMask, and counters restored)."
		return
	}
	if s.Conceptual != nil {
		s.Conceptual.Reset()
		s.StdinLines = nil
		s.StdoutLines = nil
		s.StderrLines = nil
		s.StatusBanner = "Reset Conceptual VM to POST-LOAD state."
	}
}

func (s *FullScreenTUIState) commitManualEventDialog(enqueueOnly bool) {
	cid := s.EventTargetCID
	raw := strings.TrimSpace(s.EventInputBuf)

	if s.Engine != nil {
		descs := s.Engine.Descriptors()
		name := descs[cid].Name
		switch s.EventOp {
		case OpInjectFault:
			ev := QueuedEvent{CID: cid, Param: 0, ParamValid: false, OpKind: "fault"}
			if enqueueOnly {
				s.PendingQueue = append(s.PendingQueue, ev)
				s.StatusBanner = fmt.Sprintf("Queued Fault '_' on C%02d (%s) into Pending Queue (len=%d)", cid, name, len(s.PendingQueue))
			} else {
				wave := s.Engine.StepEvent(cid, 0, false)
				s.syncBRAMStdioFromSteps()
				s.StatusBanner = fmt.Sprintf("Created & executed Fault '_' on C%02d (%s) => %s", cid, name, wave[0].Verdict)
			}
		case OpReadConcept:
			valOK := ((s.Engine.ValidMask >> uint(cid)) & 1) != 0
			msg := fmt.Sprintf("READ: %s[cid=%d] = %d (valid=%s)", name, cid, s.Engine.State[cid], ValidSymbol(valOK))
			s.StdoutLines = append(s.StdoutLines, msg)
			s.StatusBanner = msg
		default: // OpWriteStimulus or OpCallConcept
			if raw == "_" || strings.EqualFold(raw, "invalid") || strings.EqualFold(raw, "fault") {
				ev := QueuedEvent{CID: cid, Param: 0, ParamValid: false, OpKind: "fault"}
				if enqueueOnly {
					s.PendingQueue = append(s.PendingQueue, ev)
					s.StatusBanner = fmt.Sprintf("Queued Fault '_' on C%02d (%s) into Pending Queue (len=%d)", cid, name, len(s.PendingQueue))
				} else {
					wave := s.Engine.StepEvent(cid, 0, false)
					s.syncBRAMStdioFromSteps()
					s.StatusBanner = fmt.Sprintf("Created & executed Fault '_' on C%02d (%s) => %s", cid, name, wave[0].Verdict)
				}
				break
			}
			if raw == "" {
				raw = "0"
			}
			val, err := strconv.ParseInt(raw, 0, 32)
			if err != nil {
				s.StatusBanner = fmt.Sprintf("Event Creator Error: invalid integer parameter %q", raw)
				break
			}
			ev := QueuedEvent{CID: cid, Param: int32(val), ParamValid: true, OpKind: "write"}
			if enqueueOnly {
				s.PendingQueue = append(s.PendingQueue, ev)
				s.StatusBanner = fmt.Sprintf("Queued Event C%02d (%s) <- param=%d into Pending Queue (len=%d). Press [n/Space] to step!",
					cid, name, val, len(s.PendingQueue))
			} else {
				wave := s.Engine.StepEvent(cid, int32(val), true)
				s.syncBRAMStdioFromSteps()
				last := wave[len(wave)-1]
				s.StatusBanner = fmt.Sprintf("Created & executed Event C%02d (%s) <- param=%d: %d hop(s), final %s (W0=%d)",
					cid, name, val, len(wave), last.Verdict, last.PostW0)
			}
		}
		s.Modal = ModalNone
		return
	}

	if s.Conceptual != nil {
		if cid < 0 || cid >= len(s.Conceptual.Slots) {
			cid = 0
		}
		slot := s.Conceptual.Slots[cid]
		var cmdLine string
		switch s.EventOp {
		case OpInjectFault:
			cmdLine = fmt.Sprintf("write %s _", slot.Name)
		case OpReadConcept:
			cmdLine = fmt.Sprintf("read %s", slot.Name)
		case OpCallConcept:
			args := strings.ReplaceAll(raw, ",", " ")
			if strings.TrimSpace(args) == "" {
				args = "5"
			}
			cmdLine = fmt.Sprintf("call %s %s", slot.Name, strings.TrimSpace(args))
		default:
			if raw == "" {
				raw = "1"
			}
			cmdLine = fmt.Sprintf("write %s %s", slot.Name, raw)
		}
		ev := parseConceptualCommandToQueuedEvent(s.Conceptual, cmdLine)
		if enqueueOnly {
			s.PendingQueue = append(s.PendingQueue, ev)
			s.StatusBanner = fmt.Sprintf("Queued Conceptual Event %q (len=%d)", cmdLine, len(s.PendingQueue))
		} else {
			s.executeConceptualEvent(ev)
		}
		s.Modal = ModalNone
	}
}

func (s *FullScreenTUIState) commitModifyStateDialog() {
	cid := s.SelectedCID()
	raw := strings.TrimSpace(s.ModifyInputBuf)

	if s.Engine != nil {
		name := s.Engine.Descriptors()[cid].Name
		if !s.ModifyValidToggle || raw == "_" || strings.EqualFold(raw, "undef") || strings.EqualFold(raw, "invalid") {
			_ = s.Engine.ModifyConceptState(cid, s.Engine.State[cid], false)
			s.StatusBanner = fmt.Sprintf("Modified C%02d (%s): Valid set to '_' (UNDEFINED / FAULT)", cid, name)
			s.Modal = ModalNone
			return
		}
		if raw == "" {
			raw = strconv.FormatInt(int64(s.Engine.State[cid]), 10)
		}
		val, err := strconv.ParseInt(raw, 0, 32)
		if err != nil {
			s.StatusBanner = fmt.Sprintf("Modify State Error: invalid int32 %q", raw)
			s.Modal = ModalNone
			return
		}
		_ = s.Engine.ModifyConceptState(cid, int32(val), true)
		s.StatusBanner = fmt.Sprintf("Modified C%02d (%s): W0 := %d (0x%08X), Valid := 1", cid, name, int32(val), uint32(int32(val)))
		s.Modal = ModalNone
		return
	}

	if s.Conceptual != nil {
		slot := s.Conceptual.Slots[cid]
		if err := s.Conceptual.ModifySlotState(cid, raw, s.ModifyValidToggle); err != nil {
			s.StatusBanner = fmt.Sprintf("Modify Error: %v", err)
		} else {
			s.StatusBanner = fmt.Sprintf("Modified C%02d (%s): state := %s (valid=%s)",
				cid, slot.Name, s.Conceptual.Slots[cid].FormatValue(), ValidSymbol(s.Conceptual.Slots[cid].Valid))
		}
		s.Modal = ModalNone
	}
}

// HandleKey processes one KeyEvent and returns true if the user requested to quit (`q`).
func (s *FullScreenTUIState) HandleKey(ev KeyEvent) bool {
	if ev.Kind == KeyEOF {
		return true
	}

	// 1. Help Modal
	if s.Modal == ModalHelp {
		if ev.Kind == KeyEsc || ev.Kind == KeyEnter || ev.Kind == KeySpace || (ev.Kind == KeyRune && (ev.Ch == 'q' || ev.Ch == '?' || ev.Ch == 'h')) {
			s.Modal = ModalNone
			s.StatusBanner = "Closed Help overlay."
		}
		return false
	}

	// 2. Manual Event Creator Modal (`[e]`)
	if s.Modal == ModalEventCreator {
		cids := s.visibleCIDs()
		switch ev.Kind {
		case KeyEsc:
			s.Modal = ModalNone
			s.StatusBanner = "Event Creator cancelled."
		case KeyLeft:
			for i, c := range cids {
				if c == s.EventTargetCID && i > 0 {
					s.EventTargetCID = cids[i-1]
					break
				}
			}
		case KeyRight:
			for i, c := range cids {
				if c == s.EventTargetCID && i+1 < len(cids) {
					s.EventTargetCID = cids[i+1]
					break
				}
			}
		case KeyTab:
			s.EventOp = (s.EventOp + 1) % 4
		case KeyBackspace:
			if len(s.EventInputBuf) > 0 {
				s.EventInputBuf = s.EventInputBuf[:len(s.EventInputBuf)-1]
			}
		case KeyEnter:
			s.commitManualEventDialog(false)
		case KeyRune:
			switch ev.Ch {
			case '+':
				s.commitManualEventDialog(true)
			case '!':
				s.EventOp = OpWriteStimulus
			case '@':
				s.EventOp = OpInjectFault
			case '#':
				s.EventOp = OpReadConcept
			case '$':
				s.EventOp = OpCallConcept
			default:
				if (ev.Ch >= '0' && ev.Ch <= '9') || ev.Ch == '-' || ev.Ch == '_' || ev.Ch == ',' || ev.Ch == '.' ||
					(ev.Ch >= 'a' && ev.Ch <= 'z') || (ev.Ch >= 'A' && ev.Ch <= 'Z') {
					s.EventInputBuf += string(ev.Ch)
				}
			}
		case KeySpace:
			s.EventInputBuf += " "
		}
		return false
	}

	// 3. Modify Concept State Modal (`[m]`)
	if s.Modal == ModalModifyState {
		switch ev.Kind {
		case KeyEsc:
			s.Modal = ModalNone
			s.StatusBanner = "Modify Concept State cancelled."
		case KeyTab:
			s.ModifyValidToggle = !s.ModifyValidToggle
		case KeyBackspace:
			if len(s.ModifyInputBuf) > 0 {
				s.ModifyInputBuf = s.ModifyInputBuf[:len(s.ModifyInputBuf)-1]
			}
		case KeyEnter:
			s.commitModifyStateDialog()
		case KeyRune:
			if ev.Ch == '_' {
				s.ModifyValidToggle = !s.ModifyValidToggle
			} else if (ev.Ch >= '0' && ev.Ch <= '9') || ev.Ch == '-' || ev.Ch == '.' || ev.Ch == '!' || ev.Ch == 'x' || ev.Ch == 'X' ||
				(ev.Ch >= 'a' && ev.Ch <= 'f') || (ev.Ch >= 'A' && ev.Ch <= 'F') {
				s.ModifyInputBuf += string(ev.Ch)
			}
		}
		return false
	}

	// 4. Normal Full-Screen Navigation & Debugger Hotkeys
	cids := s.visibleCIDs()
	switch ev.Kind {
	case KeyTab:
		s.FocusPanel = (s.FocusPanel + 1) % 4
		panelNames := []string{"[1] CONCEPTS", "[2] INSPECTOR / SOURCE / DIFF", "[3] CASCADE WAVE TRACE", "[4] STDIO & EVENT BAR"}
		s.StatusBanner = fmt.Sprintf("Focus switched to %s", panelNames[s.FocusPanel])
	case KeyUp:
		switch s.FocusPanel {
		case 1:
			if s.SourceScroll > 0 {
				s.SourceScroll--
			}
		case 2:
			if s.TraceScroll > 0 {
				s.TraceScroll--
			}
		case 3:
			if s.StdioScroll > 0 {
				s.StdioScroll--
			}
		default:
			if s.SelectedIdx > 0 {
				s.SelectedIdx--
			}
		}
	case KeyDown:
		switch s.FocusPanel {
		case 1:
			s.SourceScroll++
		case 2:
			s.TraceScroll++
		case 3:
			s.StdioScroll++
		default:
			if s.SelectedIdx+1 < len(cids) {
				s.SelectedIdx++
			}
		}
	case KeyPageUp:
		if s.FocusPanel == 2 {
			s.TraceScroll -= 5
			if s.TraceScroll < 0 {
				s.TraceScroll = 0
			}
		} else if s.SelectedIdx >= 5 {
			s.SelectedIdx -= 5
		} else {
			s.SelectedIdx = 0
		}
	case KeyPageDown:
		if s.FocusPanel == 2 {
			s.TraceScroll += 5
		} else if s.SelectedIdx+5 < len(cids) {
			s.SelectedIdx += 5
		} else if len(cids) > 0 {
			s.SelectedIdx = len(cids) - 1
		}
	case KeySpace:
		s.ExecuteSingleMicroStep()
	case KeyEnter:
		s.openManualEventCreator()
	case KeyRune:
		switch ev.Ch {
		case 'q', 'Q':
			s.Phase = "COMPLETED"
			return true
		case 'j':
			if s.SelectedIdx+1 < len(cids) {
				s.SelectedIdx++
			}
		case 'k':
			if s.SelectedIdx > 0 {
				s.SelectedIdx--
			}
		case 'a', 'A':
			if s.Engine != nil {
				s.ShowAll64Slots = !s.ShowAll64Slots
				s.SelectedIdx = 0
				if s.ShowAll64Slots {
					s.StatusBanner = "Showing all 64 BRAM slots (C00..C63)."
				} else {
					s.StatusBanner = fmt.Sprintf("Showing %d active BRAM concept(s).", len(s.Engine.ActiveCIDs))
				}
			}
		case 'd', 'D':
			s.Panel2Mode = (s.Panel2Mode + 1) % 3
			s.SourceScroll = 0
			s.StatusBanner = fmt.Sprintf("Switched Panel [2] view to: %s", s.Panel2Mode.String())
		case 'e', 'E', 'i', 'I':
			s.openManualEventCreator()
		case 'n', 'N':
			s.ExecuteSingleMicroStep()
		case 's', 'S':
			s.ExecuteFullEventStep()
		case 'f', 'F':
			s.InjectFaultOnSelected()
		case 'm', 'M':
			s.openModifyStateDialog()
		case 'w', 'W':
			s.ToggleWatchpointOnSelected()
		case 'r', 'R':
			s.ResetToPostLoad()
		case '?', 'h', 'H':
			s.Modal = ModalHelp
		}
	}
	return false
}

func (s *FullScreenTUIState) openManualEventCreator() {
	s.Modal = ModalEventCreator
	s.EventTargetCID = s.SelectedCID()
	s.EventOp = OpWriteStimulus
	s.EventInputBuf = ""
	s.StatusBanner = "Manual Event Creator: Type parameter, [Left/Right] Target Concept, [Tab] Operation, [Enter] Execute Now, [+] Add to Queue, [Esc] Cancel."
}

func (s *FullScreenTUIState) openModifyStateDialog() {
	cid := s.SelectedCID()
	s.Modal = ModalModifyState
	s.ModifyInputBuf = ""
	if s.Engine != nil {
		s.ModifyValidToggle = ((s.Engine.ValidMask >> uint(cid)) & 1) != 0
	} else if s.Conceptual != nil && cid < len(s.Conceptual.Slots) {
		s.ModifyValidToggle = s.Conceptual.Slots[cid].Valid
	} else {
		s.ModifyValidToggle = true
	}
	s.StatusBanner = fmt.Sprintf("Modify State (What-If) for C%02d: Type new W0 value, [Tab or _] Toggle Valid (1 <-> _), [Enter] Apply, [Esc] Cancel.", cid)
}

// String helper functions for UTF-8 box drawing and exact rune-width padding/truncation.
func clipOrPadRunes(str string, width int) string {
	if width <= 0 {
		return ""
	}
	runes := []rune(str)
	if len(runes) > width {
		if width > 1 {
			return string(runes[:width-1]) + "…"
		}
		return string(runes[:width])
	}
	if len(runes) < width {
		return str + strings.Repeat(" ", width-len(runes))
	}
	return str
}

func drawBoxTop(leftW, rightW int, titleLeft, titleRight string) string {
	lBar := "─ " + titleLeft + " "
	lRem := leftW - utf8.RuneCountInString(lBar)
	if lRem < 0 {
		lBar = clipOrPadRunes(lBar, leftW)
	} else {
		lBar += strings.Repeat("─", lRem)
	}

	rBar := "─ " + titleRight + " "
	rRem := rightW - utf8.RuneCountInString(rBar)
	if rRem < 0 {
		rBar = clipOrPadRunes(rBar, rightW)
	} else {
		rBar += strings.Repeat("─", rRem)
	}
	return "┌" + lBar + "┬" + rBar + "┐"
}

func drawSingleBoxTop(innerW int, title string) string {
	bar := "─ " + title + " "
	rem := innerW - utf8.RuneCountInString(bar)
	if rem < 0 {
		bar = clipOrPadRunes(bar, innerW)
	} else {
		bar += strings.Repeat("─", rem)
	}
	return "┌" + bar + "┐"
}

func drawSingleBoxDivider(innerW int, title string) string {
	bar := "─ " + title + " "
	rem := innerW - utf8.RuneCountInString(bar)
	if rem < 0 {
		bar = clipOrPadRunes(bar, innerW)
	} else {
		bar += strings.Repeat("─", rem)
	}
	return "├" + bar + "┤"
}

func drawSplitToSingleDivider(leftW, rightW int, title string) string {
	totalInner := leftW + 1 + rightW
	out := make([]rune, totalInner)
	for i := 0; i < totalInner; i++ {
		if i == leftW {
			out[i] = '┴'
		} else {
			out[i] = '─'
		}
	}
	bar := []rune(" " + title + " ")
	start := 1
	if start+len(bar) >= leftW {
		start = leftW + 2
	}
	for i := 0; i < len(bar) && start+i < totalInner; i++ {
		if start+i != leftW {
			out[start+i] = bar[i]
		}
	}
	return "├" + string(out) + "┤"
}

func drawSingleBoxBottom(innerW int) string {
	return "└" + strings.Repeat("─", innerW) + "┘"
}

// RenderFrame renders the complete full-screen multi-pane UTF-8 TUI canvas (`rows × cols`).
func (s *FullScreenTUIState) RenderFrame() string {
	rows := s.Rows
	cols := s.Cols
	if rows < 24 {
		rows = DefaultTUIRows
	}
	if cols < 96 {
		cols = DefaultTUICols
	}
	innerW := cols - 2
	leftW := (innerW * 42) / 100
	if leftW < 38 {
		leftW = 38
	}
	rightW := innerW - 1 - leftW

	// Compute vertical heights for the 3 boxed regions so total lines fit rows
	// Header = 2 lines, TopSplit = 1 + topH, Mid = 1 + midH, Bot = 1 + botH + 1
	availBody := rows - 6
	topH := 10
	if availBody >= 26 {
		topH = 11
	}
	botH := 6
	if s.Modal != ModalNone {
		botH = 8
	}
	midH := availBody - topH - botH
	if midH < 6 {
		midH = 6
	}

	var outLines []string

	// 1. Top 2-line Inverse Status Bar
	hdr1, hdr2 := s.formatHeaderBars(cols)
	if s.UseColor {
		outLines = append(outLines, ANSIHeaderInv+hdr1+ANSIReset)
		outLines = append(outLines, ANSISubHdrInv+hdr2+ANSIReset)
	} else {
		outLines = append(outLines, hdr1)
		outLines = append(outLines, hdr2)
	}

	// 2. Top Split Panels: [1] CONCEPTS (Left) | [2] CONCEPT INSPECTOR / SOURCE / DIFF (Right)
	focus1 := ""
	if s.FocusPanel == 0 {
		focus1 = "*FOCUS* "
	}
	focus2 := ""
	if s.FocusPanel == 1 {
		focus2 = "*FOCUS* "
	}
	title1 := fmt.Sprintf("%s[1] CONCEPTS (↑/↓ Select, a:All/Act, w:Watch)", focus1)
	title2 := fmt.Sprintf("%s[2] %s (d:Toggle View)", focus2, s.Panel2Mode.String())
	outLines = append(outLines, drawBoxTop(leftW, rightW, title1, title2))

	leftLines := s.renderPanel1Concepts(leftW, topH)
	rightLines := s.renderPanel2InspectorOrSourceOrDiff(rightW, topH)
	for i := 0; i < topH; i++ {
		lCell := clipOrPadRunes(leftLines[i], leftW)
		rCell := clipOrPadRunes(rightLines[i], rightW)
		if s.UseColor {
			lCell = s.colorizeConceptListRow(lCell, i)
		}
		outLines = append(outLines, "│"+lCell+"│"+rCell+"│")
	}

	// 3. Middle Panel: [3] CASCADE WAVE TRACE & PENDING EVENT QUEUE
	focus3 := ""
	if s.FocusPanel == 2 {
		focus3 = "*FOCUS* "
	}
	title3 := fmt.Sprintf("%s[3] CASCADE WAVE TRACE & PENDING EVENT QUEUE (n/Space: 1-Hop | s: Full Event)", focus3)
	outLines = append(outLines, drawSplitToSingleDivider(leftW, rightW, title3))

	midLines := s.renderPanel3WaveTraceAndQueue(innerW, midH)
	for i := 0; i < midH; i++ {
		mCell := clipOrPadRunes(midLines[i], innerW)
		if s.UseColor {
			mCell = s.colorizeTraceRow(mCell)
		}
		outLines = append(outLines, "│"+mCell+"│")
	}

	// 4. Bottom Panel: [4] STDIO STREAMS (STDIN / STDOUT / STDERR) & INTERACTIVE COMMAND / EVENT BAR
	focus4 := ""
	if s.FocusPanel == 3 {
		focus4 = "*FOCUS* "
	}
	title4 := fmt.Sprintf("%s[4] STDIO STREAMS (STDIN / STDOUT / STDERR) & INTERACTIVE EVENT CREATOR", focus4)
	outLines = append(outLines, drawSingleBoxDivider(innerW, title4))

	botLines := s.renderPanel4StdioAndCommandBar(innerW, botH)
	for i := 0; i < botH; i++ {
		bCell := clipOrPadRunes(botLines[i], innerW)
		if s.UseColor {
			bCell = s.colorizeStdioRow(bCell)
		}
		outLines = append(outLines, "│"+bCell+"│")
	}
	outLines = append(outLines, drawSingleBoxBottom(innerW))

	return strings.Join(outLines, "\n")
}

func (s *FullScreenTUIState) formatHeaderBars(cols int) (string, string) {
	phase := s.Phase
	if phase == "" {
		phase = "INTERACTIVE"
	}
	if s.Engine != nil {
		eng := s.Engine
		descs := *eng.Descriptors()
		topo := AnalyzeConceptTopology(descs)
		targetLbl := "SIM (0x4B504D43 'KPMC')"
		preActive := 0
		postActive := len(eng.ActiveCIDs)
		changedOnLoad := postActive
		if s.Conn != nil && s.Conn.PreLoadSnapshot != nil {
			preS := s.Conn.PreLoadSnapshot
			preActive = preS.Topology.ActiveConcepts
			targetLbl = fmt.Sprintf("%s (%s '%s')", strings.ToUpper(preS.Target), preS.HWIDHex, preS.HWIDASCII)
		}
		if s.Conn != nil && s.Conn.PostLoadSnapshot != nil {
			postActive = s.Conn.PostLoadSnapshot.Topology.ActiveConcepts
			changedOnLoad = 0
			for _, d := range s.Conn.LoadDiffs {
				if d.Changed {
					changedOnLoad++
				}
			}
		}
		modeLbl := ModeBRAM64
		if eng.ModeLabel != "" {
			modeLbl = eng.ModeLabel
		}
		line1 := fmt.Sprintf(" VMK v%s FULL-SCREEN DEBUGGER | Target: %s | Mode: %s (%s) | Phase: PRE-LOAD -> POST-LOAD -> %s",
			Version, targetLbl, modeLbl, eng.ModuleName, phase)
		line2 := fmt.Sprintf(" Concepts: Active %d/%d (Pre-load: %d/%d, Changed: %d, Free: %d) | Entry:%v Internal:%v Leaf:%v | Queue:%d pending | Events:%d | Commits:%d | Rejects:%d | Faults(_):%d",
			postActive, topo.TotalSlots, preActive, topo.TotalSlots, changedOnLoad, topo.FreeSlots,
			topo.EntryConcepts, topo.InternalCascadeConcepts, topo.LeafConcepts,
			len(s.PendingQueue), eng.EventsProcessed, eng.Commits, eng.Rejects, eng.FaultPropagations)
		return clipOrPadRunes(line1, cols), clipOrPadRunes(line2, cols)
	}

	vm := s.Conceptual
	activeCount := len(vm.Slots)
	changedOnLoad := activeCount - vm.PreLoadActive
	if changedOnLoad < 0 {
		changedOnLoad = activeCount
	}
	freeSlots := vm.Capacity - activeCount
	line1 := fmt.Sprintf(" VMK v%s FULL-SCREEN DEBUGGER | Target: SIM (RFC-001..018) | Mode: %s (%s) | Phase: PRE-LOAD -> POST-LOAD -> %s",
		Version, ModeConceptual, vm.ProgramName, phase)
	line2 := fmt.Sprintf(" Concepts: Active %d/%d (Pre-load: %d/%d, Changed: %d, Free: %d) | Queue:%d pending | Events:%d | Commits:%d | Rejects:%d | Faults(_):%d",
		activeCount, vm.Capacity, vm.PreLoadActive, vm.Capacity, changedOnLoad, freeSlots,
		len(s.PendingQueue), vm.EventsProcessed, vm.Commits, vm.Rejects, vm.FaultPropagations)
	return clipOrPadRunes(line1, cols), clipOrPadRunes(line2, cols)
}

func (s *FullScreenTUIState) renderPanel1Concepts(width, height int) []string {
	lines := make([]string, 0, height)
	lines = append(lines, " Sel W CID  Name                State (Δ)   Valid  Sub")

	cids := s.visibleCIDs()
	if s.SelectedIdx >= len(cids) {
		s.SelectedIdx = 0
	}
	listRows := height - 1
	startIdx := 0
	if s.SelectedIdx >= listRows {
		startIdx = s.SelectedIdx - listRows + 1
	}

	if s.Engine != nil {
		eng := s.Engine
		descs := *eng.Descriptors()
		for i := 0; i < listRows; i++ {
			idx := startIdx + i
			if idx >= len(cids) {
				lines = append(lines, "")
				continue
			}
			cid := cids[idx]
			d := descs[cid]
			sel := "  "
			if idx == s.SelectedIdx {
				sel = "> "
			}
			wp := " "
			if eng.WatchCIDs[cid] {
				wp = "*"
			}
			w0 := eng.State[cid]
			initW0 := eng.InitialState[cid]
			w0Str := fmt.Sprintf("W0=%d", w0)
			if w0 != initW0 {
				w0Str = fmt.Sprintf("W0=%d(%+d)", w0, w0-initW0)
			}
			valOK := ((eng.ValidMask >> uint(cid)) & 1) != 0
			valTag := "[VALID]"
			if !valOK {
				valTag = "[_ FLT]"
			} else if w0 != initW0 {
				valTag = "[CHGD] "
			}
			subTag := "None"
			if d.HasSubscriptionEdge() {
				subTag = fmt.Sprintf("->C%02d", d.SubscriberCID)
			}
			row := fmt.Sprintf(" %s%s C%02d %-18s %-11s %-7s %s",
				sel, wp, cid, clipOrPadRunes(d.Name, 18), clipOrPadRunes(w0Str, 11), valTag, subTag)
			lines = append(lines, clipOrPadRunes(row, width))
		}
		return lines
	}

	vm := s.Conceptual
	for i := 0; i < listRows; i++ {
		idx := startIdx + i
		if idx >= len(cids) {
			lines = append(lines, "")
			continue
		}
		cid := cids[idx]
		slot := vm.Slots[cid]
		sel := "  "
		if idx == s.SelectedIdx {
			sel = "> "
		}
		wp := " "
		if s.ConceptualWatch[cid] {
			wp = "*"
		}
		valStr := fmt.Sprintf("Val=%s", slot.FormatValue())
		valTag := "[VALID]"
		if !slot.Valid {
			valTag = "[_ UDF]"
		} else if slot.FormatValue() != slot.FormatInitValue() {
			valTag = "[CHGD] "
		}
		row := fmt.Sprintf(" %s%s C%02d %-18s %-11s %-7s %s",
			sel, wp, cid, clipOrPadRunes(slot.Name, 18), clipOrPadRunes(valStr, 11), valTag, slot.SubSummary)
		lines = append(lines, clipOrPadRunes(row, width))
	}
	return lines
}

func (s *FullScreenTUIState) renderPanel2InspectorOrSourceOrDiff(width, height int) []string {
	switch s.Panel2Mode {
	case ViewSourceCode:
		return s.renderPanel2SourceCode(width, height)
	case ViewPrePostDiff:
		return s.renderPanel2PrePostDiff(width, height)
	default:
		return s.renderPanel2ConceptInspector(width, height)
	}
}

func (s *FullScreenTUIState) renderPanel2ConceptInspector(width, height int) []string {
	cid := s.SelectedCID()
	var lines []string

	if s.Engine != nil {
		eng := s.Engine
		descs := *eng.Descriptors()
		d := descs[cid]
		topo := AnalyzeConceptTopology(descs)
		scfg := ParseStdioDirectives(eng.SourceCode, descs, eng.ActiveCIDs)

		role := "ISOLATED / FREE"
		for _, c := range topo.EntryConcepts {
			if c == cid {
				role = "ENTRY"
				break
			}
		}
		for _, c := range topo.InternalCascadeConcepts {
			if c == cid {
				role = "INTERNAL CASCADE"
				break
			}
		}
		for _, c := range topo.LeafConcepts {
			if c == cid {
				role = "LEAF"
				break
			}
		}
		var ioTags []string
		for _, inName := range scfg.StdinConcepts {
			if inName == d.Name {
				ioTags = append(ioTags, "@stdin")
			}
		}
		for _, outName := range scfg.StdoutConcepts {
			if outName == d.Name {
				ioTags = append(ioTags, "@stdout")
			}
		}
		if len(ioTags) > 0 {
			role += " (" + strings.Join(ioTags, ", ") + ")"
		}

		preLoadW0 := "_ (empty)"
		if s.Conn != nil && s.Conn.PreLoadSnapshot != nil {
			d0 := s.Conn.PreLoadSnapshot.Descriptors[cid]
			if d0.IsConfigured() {
				preLoadW0 = strconv.FormatInt(int64(int32(d0.CurrentState)), 10)
			}
		}
		postLoadW0 := eng.InitialState[cid]
		curW0 := eng.State[cid]
		delta := curW0 - postLoadW0
		valOK := ((eng.ValidMask >> uint(cid)) & 1) != 0
		valDesc := "1 (VALID)"
		if !valOK {
			valDesc = "_ (UNDEFINED / FAULT)"
		}
		wpDesc := "OFF"
		if eng.WatchCIDs[cid] {
			wpDesc = "ON (*)"
		}

		w0Hex := uint32(curW0)
		w1Hex := d.OperandVal
		w2Hex := d.W2Word()
		w3Hex := d.SubscriberCID

		lastAct := "None (no steps executed on this concept yet)"
		for i := len(eng.Steps) - 1; i >= 0; i-- {
			st := eng.Steps[i]
			if st.CID == cid {
				lastAct = fmt.Sprintf("Step #%d (E%d.%d): param=%d, valid=%s => %s (W0: %d -> %d)",
					st.StepIndex, st.EventID, st.Depth, st.Param, ValidSymbol(st.ParamValid), st.Verdict, st.PreW0, st.PostW0)
				break
			}
		}

		invEn := (d.GuardFlags & GuardInvariantEn) != 0
		assumpEn := (d.GuardFlags & GuardAssumptionEn) != 0

		lines = []string{
			fmt.Sprintf(" Concept ID & Name : C%02d (%s) | Type: %s | Watch: %s", cid, d.Name, d.TypeName, wpDesc),
			fmt.Sprintf(" Topology & Role   : %s | Bank: %d", role, eng.ActiveBank),
			fmt.Sprintf(" State Evolution   : Pre-Load W0: %s -> Post-Load W0: %d -> Current W0: %d (Δ = %+d)", preLoadW0, postLoadW0, curW0, delta),
			fmt.Sprintf(" Validity Bit (_)  : %s", valDesc),
			fmt.Sprintf(" BRAM Words (Hex)  : W0=0x%08X  W1=0x%08X  W2=0x%08X  W3=0x%08X", w0Hex, w1Hex, w2Hex, w3Hex),
			fmt.Sprintf(" Predicate (::)    : %s (assump_en=%v, op=0x%02X)", DecodePredicateFormula(d), assumpEn, d.PredOpcode),
			fmt.Sprintf(" Action (=>)       : %s (act_op=0x%02X, W1_i32=%d)", DecodeActionFormula(d), d.ActionOpcode, int32(d.OperandVal)),
			fmt.Sprintf(" Big Dot Gate (•)  : %s (inv_en=%v, hazard=%d)", DecodeInvariantFormula(d), invEn, d.HazardLimit),
			fmt.Sprintf(" Subscription (W3) : %s", DecodeW3Subscriber(d, descs)),
			fmt.Sprintf(" Last Activity     : %s", lastAct),
		}
	} else if s.Conceptual != nil {
		vm := s.Conceptual
		slot := vm.Slots[cid]
		preLoadStr := "_ (empty)"
		if slot.Type == TypeStream {
			preLoadStr = "0 (stream)"
		}
		valDesc := "1 (VALID)"
		if !slot.Valid {
			valDesc = "_ (UNDEFINED / FAULT)"
		}
		lastAct := "None (no steps executed on this concept yet)"
		for i := len(vm.Steps) - 1; i >= 0; i-- {
			st := vm.Steps[i]
			if st.CID == cid {
				lastAct = fmt.Sprintf("Step #%d (E%d.%d): %s => %s (%s -> %s)",
					st.StepIndex, st.EventID, st.Depth, st.EventDisplay, st.Verdict, st.PreDisplay, st.PostDisplay)
				break
			}
		}
		lines = []string{
			fmt.Sprintf(" Concept ID & Name : C%02d (%s) | Type: %s", slot.CID, slot.Name, slot.Type),
			fmt.Sprintf(" State Evolution   : Pre-Load: %s -> Post-Load: %s -> Current: %s", preLoadStr, slot.FormatInitValue(), slot.FormatValue()),
			fmt.Sprintf(" Validity Bit (_)  : %s | RFC-001 Busy Lock: %v", valDesc, slot.Busy),
			fmt.Sprintf(" Predicate & Rule  : %s", slot.RuleSummary),
			fmt.Sprintf(" Big Dot Gate (•)  : %s (PostReadZero=%v)", slot.GateSummary, slot.PostReadZero),
			fmt.Sprintf(" Subscription      : %s", slot.SubSummary),
			fmt.Sprintf(" Last Activity     : %s", lastAct),
		}
	}

	for len(lines) < height {
		lines = append(lines, "")
	}
	return lines[:height]
}

func (s *FullScreenTUIState) renderPanel2SourceCode(width, height int) []string {
	src := ""
	if s.Engine != nil {
		src = s.Engine.SourceCode
	} else if s.Conceptual != nil {
		src = s.Conceptual.SourceCode
	}
	rawLines := strings.Split(src, "\n")
	if s.SourceScroll >= len(rawLines) {
		s.SourceScroll = 0
	}
	var out []string
	out = append(out, " [SOURCE CODE (.ekpol / .kpol) — press 'd' for Pre-Load vs Post-Load Diff]")
	for i := 0; i < height-1; i++ {
		idx := s.SourceScroll + i
		if idx >= len(rawLines) {
			out = append(out, "")
			continue
		}
		out = append(out, fmt.Sprintf(" %02d │ %s", idx+1, strings.TrimRight(rawLines[idx], "\r\t ")))
	}
	return out
}

func (s *FullScreenTUIState) renderPanel2PrePostDiff(width, height int) []string {
	var out []string
	out = append(out, " CID  Name                 Chg  Pre-Load W0  Post-Load W0  Current W0   Post-Load Rule -> Sub")
	if s.Engine != nil {
		descs := *s.Engine.Descriptors()
		var diffs []SlotLoadDiff
		if s.Conn != nil && len(s.Conn.LoadDiffs) > 0 {
			diffs = s.Conn.LoadDiffs
		} else {
			for _, cid := range s.Engine.ActiveCIDs {
				d := descs[cid]
				_, dec := DecodeW2Summary(d)
				diffs = append(diffs, SlotLoadDiff{
					CID:        cid,
					Name:       d.Name,
					Changed:    true,
					PreActive:  false,
					PostActive: true,
					PostW0:     s.Engine.InitialState[cid],
					PostRule:   dec,
					PostSub:    DecodeW3Subscriber(d, descs),
				})
			}
		}
		for i := 0; i < height-1; i++ {
			if i >= len(diffs) {
				out = append(out, "")
				continue
			}
			df := diffs[i]
			chg := "NO "
			if df.Changed {
				chg = "YES"
			}
			preStr := "_ (empty)"
			if df.PreActive {
				preStr = strconv.FormatInt(int64(df.PreW0), 10)
			}
			postStr := strconv.FormatInt(int64(df.PostW0), 10)
			curStr := fmt.Sprintf("%d", s.Engine.State[df.CID])
			row := fmt.Sprintf(" C%02d  %-19s  %s  %-11s  %-12s  %-11s  %s (%s)",
				df.CID, clipOrPadRunes(df.Name, 19), chg, preStr, postStr, curStr, df.PostRule, df.PostSub)
			out = append(out, clipOrPadRunes(row, width))
		}
		return out
	}

	if s.Conceptual != nil {
		for i := 0; i < height-1; i++ {
			if i >= len(s.Conceptual.Slots) {
				out = append(out, "")
				continue
			}
			sl := s.Conceptual.Slots[i]
			pre := "_ (empty)"
			if sl.Type == TypeStream {
				pre = "0 (stream)"
			}
			row := fmt.Sprintf(" C%02d  %-19s  YES  %-11s  %-12s  %-11s  %s -> %s",
				sl.CID, clipOrPadRunes(sl.Name, 19), pre, sl.FormatInitValue(), sl.FormatValue(), sl.RuleSummary, sl.SubSummary)
			out = append(out, clipOrPadRunes(row, width))
		}
	}
	return out
}

func (s *FullScreenTUIState) renderPanel3WaveTraceAndQueue(width, height int) []string {
	var lines []string

	// Row 1: Pending Event Queue (shows queued external events & intermediate cascade hops!)
	if len(s.PendingQueue) == 0 {
		lines = append(lines, " Pending Queue (0): (empty — press [e] to create/queue an event, or [n/Space] to pulse selected concept)")
	} else {
		var qParts []string
		for idx, ev := range s.PendingQueue {
			if idx >= 6 {
				qParts = append(qParts, fmt.Sprintf("...(+%d more)", len(s.PendingQueue)-idx))
				break
			}
			hopTag := ""
			if ev.IsHop {
				hopTag = fmt.Sprintf("HOP d=%d ", ev.Depth)
			}
			if ev.CmdLine != "" {
				qParts = append(qParts, fmt.Sprintf("[%d] %s", idx+1, ev.CmdLine))
			} else {
				qParts = append(qParts, fmt.Sprintf("[%d] %sC%02d(param=%d,valid=%s)",
					idx+1, hopTag, ev.CID, ev.Param, ValidSymbol(ev.ParamValid)))
			}
		}
		lines = append(lines, fmt.Sprintf(" Pending Queue (%d): %s", len(s.PendingQueue), strings.Join(qParts, " -> ")))
	}

	// 2. Row 2: Trace Table Header (11 columns aligned to fit 122 inner chars)
	lines = append(lines, " Step    │Dp│Concept        │Event     │Pre    │Predicate ::    │Candidate │Gate •       │Verdict         │Post   │Next")

	var steps []CascadeTraceStep
	if s.Engine != nil {
		steps = s.Engine.Steps
	} else if s.Conceptual != nil {
		steps = s.Conceptual.Steps
	}

	traceRows := height - 2
	startIdx := 0
	if len(steps) > traceRows {
		startIdx = len(steps) - traceRows - s.TraceScroll
		if startIdx < 0 {
			startIdx = 0
		}
	}

	for i := 0; i < traceRows; i++ {
		idx := startIdx + i
		if idx >= len(steps) {
			lines = append(lines, "")
			continue
		}
		st := steps[idx]
		stepLbl := fmt.Sprintf("E%d.%d#%d", st.EventID, st.CascadeStep, st.StepIndex)
		cidLbl := fmt.Sprintf("C%02d %s", st.CID, st.ConceptName)
		evLbl := st.EventDisplay
		if evLbl == "" {
			evLbl = fmt.Sprintf("p=%d,v=%s", st.Param, ValidSymbol(st.ParamValid))
		}
		preLbl := st.PreDisplay
		if preLbl == "" {
			preLbl = fmt.Sprintf("W0=%d,v=%s", st.PreW0, ValidSymbol(st.PreValid))
		}
		predLbl := fmt.Sprintf("%s=>%v", st.PredFormula, st.PredMatch)
		candLbl := fmt.Sprintf("%s=>%d", st.ActionFormula, st.CandidateW0)
		if st.ArithOverflow {
			candLbl += "[OVF]"
		}
		gateLbl := fmt.Sprintf("%s=>%v", st.InvFormula, st.InvOK)
		verdictLbl := st.Verdict
		if len(st.WatchpointsHit) > 0 {
			verdictLbl += "*"
		}
		postLbl := st.PostDisplay
		if postLbl == "" {
			postLbl = fmt.Sprintf("W0=%d,v=%s", st.PostW0, ValidSymbol(st.PostValid))
		}
		nextLbl := "None"
		if st.EnqueuedSubscriberCID != nil {
			nextLbl = fmt.Sprintf("->C%02d", *st.EnqueuedSubscriberCID)
		}

		row := fmt.Sprintf(" %-7s │%-2d│%-15s│%-10s│%-7s│%-16s│%-10s│%-13s│%-16s│%-7s│%s",
			clipOrPadRunes(stepLbl, 7),
			st.Depth,
			clipOrPadRunes(cidLbl, 15),
			clipOrPadRunes(evLbl, 10),
			clipOrPadRunes(preLbl, 7),
			clipOrPadRunes(predLbl, 16),
			clipOrPadRunes(candLbl, 10),
			clipOrPadRunes(gateLbl, 13),
			clipOrPadRunes(verdictLbl, 16),
			clipOrPadRunes(postLbl, 7),
			nextLbl,
		)
		lines = append(lines, clipOrPadRunes(row, width))
	}
	return lines
}

func (s *FullScreenTUIState) renderPanel4StdioAndCommandBar(width, height int) []string {
	var lines []string

	// If a Modal Dialog is open, render the interactive modal box inside Panel [4]
	switch s.Modal {
	case ModalEventCreator:
		targetName := fmt.Sprintf("C%02d", s.EventTargetCID)
		if s.Engine != nil && s.EventTargetCID >= 0 && s.EventTargetCID < 64 {
			targetName = fmt.Sprintf("C%02d (%s)", s.EventTargetCID, s.Engine.Descriptors()[s.EventTargetCID].Name)
		} else if s.Conceptual != nil && s.EventTargetCID >= 0 && s.EventTargetCID < len(s.Conceptual.Slots) {
			targetName = fmt.Sprintf("C%02d (%s)", s.EventTargetCID, s.Conceptual.Slots[s.EventTargetCID].Name)
		}
		var ops []string
		for op := OpWriteStimulus; op <= OpCallConcept; op++ {
			if op == s.EventOp {
				ops = append(ops, "["+op.Label()+"]")
			} else {
				ops = append(ops, " "+op.Label()+" ")
			}
		}
		lines = append(lines, " ╔══ MANUAL EVENT CREATOR DIALOG ([e] / [Enter]) ═════════════════════════════════════════════════════════════════════╗")
		lines = append(lines, fmt.Sprintf(" ║ Target Concept (←/→) : %-90s ║", targetName))
		lines = append(lines, fmt.Sprintf(" ║ Operation (Tab)      : %-90s ║", strings.Join(ops, " ")))
		lines = append(lines, fmt.Sprintf(" ║ Parameter / Args     : %s_ (type number e.g. 120, -10, 250 or _ for fault)", s.EventInputBuf))
		lines = append(lines, " ║ Action Keys          : [Enter] Execute Immediately  |  [+] Add to Pending Queue (Step-by-Step)  |  [Esc] Cancel   ║")
		lines = append(lines, " ╚════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝")
		for len(lines) < height {
			lines = append(lines, " "+s.StatusBanner)
		}
		return lines[:height]

	case ModalModifyState:
		cid := s.SelectedCID()
		targetName := fmt.Sprintf("C%02d", cid)
		curVal := "0"
		if s.Engine != nil {
			targetName = fmt.Sprintf("C%02d (%s)", cid, s.Engine.Descriptors()[cid].Name)
			curVal = strconv.FormatInt(int64(s.Engine.State[cid]), 10)
		} else if s.Conceptual != nil && cid < len(s.Conceptual.Slots) {
			targetName = fmt.Sprintf("C%02d (%s)", cid, s.Conceptual.Slots[cid].Name)
			curVal = s.Conceptual.Slots[cid].FormatValue()
		}
		valMode := "1 (VALID)"
		if !s.ModifyValidToggle {
			valMode = "_ (UNDEFINED / FAULT)"
		}
		lines = append(lines, " ╔══ MODIFY CONCEPT STATE ('WHAT-IF' EDITOR [m]) ═════════════════════════════════════════════════════════════════════╗")
		lines = append(lines, fmt.Sprintf(" ║ Selected Concept     : %-35s (Current State: %s)", targetName, curVal))
		lines = append(lines, fmt.Sprintf(" ║ Validity Bit (Tab/_) : %-35s", valMode))
		lines = append(lines, fmt.Sprintf(" ║ New W0 / Value       : %s_ (leave empty to keep current W0 and only toggle Valid/_)", s.ModifyInputBuf))
		lines = append(lines, " ║ Action Keys          : [Enter] Apply State Change  |  [Tab or _] Toggle Valid (1 <-> _)  |  [Esc] Cancel          ║")
		lines = append(lines, " ╚════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝")
		for len(lines) < height {
			lines = append(lines, " "+s.StatusBanner)
		}
		return lines[:height]

	case ModalHelp:
		lines = append(lines, fmt.Sprintf(" ╔══ VMK v%s FULL-SCREEN DEBUGGER — KEYBOARD SHORTCUTS HELP ([?] / [h]) ═══════════════════════════════════════════╗", Version))
		lines = append(lines, " ║  [↑/↓] or [j/k] : Select concept in [1] / Scroll active panel    [Tab]       : Cycle panel focus [1]->[2]->[3]->[4]║")
		lines = append(lines, " ║  [e] or [Enter] : Open Manual Event Creator Dialog (<-, _, ->, |) [+] in [e] : Enqueue event into Pending Queue     ║")
		lines = append(lines, " ║  [n] or [Space] : Single Micro-Step (1 Hop of Cascade Wave!)     [s]         : Full Event Step (entire cascade)     ║")
		lines = append(lines, " ║  [f]            : Quick Fault '_' on selected concept            [m]         : Modify Concept State (What-If W0/_) ║")
		lines = append(lines, " ║  [d]            : Cycle Panel [2] (Inspector/Source/Load Diff)   [a]         : Toggle Active (K) vs All 64 Slots    ║")
		lines = append(lines, " ║  [w]            : Toggle Watchpoint (*) on selected concept      [r]         : Reset to Post-Load  |  [q] : Quit    ║")
		lines = append(lines, " ╚════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝")
		for len(lines) < height {
			lines = append(lines, "")
		}
		return lines[:height]
	}

	// Standard STDIO + Status + Hotkey Bar
	inSummary := "(empty)"
	if len(s.StdinLines) > 0 {
		start := 0
		if len(s.StdinLines) > 4 {
			start = len(s.StdinLines) - 4
		}
		inSummary = strings.Join(s.StdinLines[start:], " ; ")
	}
	outSummary := "(none)"
	if len(s.StdoutLines) > 0 {
		outSummary = s.StdoutLines[len(s.StdoutLines)-1]
	}
	errSummary := "(none)"
	if len(s.StderrLines) > 0 {
		errSummary = s.StderrLines[len(s.StderrLines)-1]
	}

	lines = append(lines, fmt.Sprintf(" STDIN  (%02d) : %s", len(s.StdinLines), inSummary))
	lines = append(lines, fmt.Sprintf(" STDOUT (%02d) -> %s", len(s.StdoutLines), outSummary))
	if len(s.StdoutLines) >= 2 && height >= 7 {
		lines = append(lines, fmt.Sprintf(" STDOUT prev -> %s", s.StdoutLines[len(s.StdoutLines)-2]))
	}
	lines = append(lines, fmt.Sprintf(" STDERR (%02d) -> %s", len(s.StderrLines), errSummary))
	lines = append(lines, fmt.Sprintf(" STATUS      : %s", s.StatusBanner))
	lines = append(lines, " KEYS: [↑/↓] Select Concept │ [e/Enter] New Event │ [n/Space] 1-Hop Wave │ [s] Full Step │ [f] Fault(_) │ [m] Modify W0/_ │ [d] Diff/Src │ [w] Watch │ [r] Reset │ [?] Help │ [q] Quit")

	for len(lines) < height {
		lines = append(lines, "")
	}
	return lines[:height]
}

func (s *FullScreenTUIState) colorizeConceptListRow(cell string, rowIdx int) string {
	if rowIdx == 0 {
		return ANSIBold + cell + ANSIReset
	}
	if strings.Contains(cell, "[_ FLT]") || strings.Contains(cell, "[_ UDF]") {
		return ANSIRed + cell + ANSIReset
	}
	if strings.HasPrefix(strings.TrimLeft(cell, " "), ">") {
		return ANSICyan + cell + ANSIReset
	}
	if strings.Contains(cell, "[CHGD]") {
		return ANSIGreen + cell + ANSIReset
	}
	return cell
}

func (s *FullScreenTUIState) colorizeTraceRow(cell string) string {
	if strings.HasPrefix(cell, " Pending Queue") {
		return ANSICyan + cell + ANSIReset
	}
	if strings.HasPrefix(cell, " Step ") {
		return ANSIBold + cell + ANSIReset
	}
	if strings.Contains(cell, VerdictRejectFault) || strings.Contains(cell, VerdictRejectInvariant) {
		return ANSIRed + cell + ANSIReset
	}
	if strings.Contains(cell, VerdictRejectGuard) {
		return ANSIYellow + cell + ANSIReset
	}
	if strings.Contains(cell, VerdictCommit) || strings.Contains(cell, VerdictSuppressedSelf) {
		return ANSIGreen + cell + ANSIReset
	}
	return cell
}

func (s *FullScreenTUIState) colorizeStdioRow(cell string) string {
	if strings.HasPrefix(cell, " STDOUT") && !strings.Contains(cell, "(none)") {
		return ANSIGreen + cell + ANSIReset
	}
	if strings.HasPrefix(cell, " STDERR") && !strings.Contains(cell, "(none)") {
		return ANSIRed + cell + ANSIReset
	}
	if strings.HasPrefix(cell, " KEYS:") {
		return ANSISubHdrInv + cell + ANSIReset
	}
	return cell
}

// RenderBRAM64FullScreenTUI renders a single non-blocking full-screen TUI frame (`--render-fullscreen-tui`) for BRAM64Engine.
func RenderBRAM64FullScreenTUI(
	eng *BRAM64Engine,
	conn *MachineConnection,
	pending []QueuedEvent,
	stdioRes *StdioExecutionResult,
	phase string,
) string {
	st := NewBRAM64FullScreenTUI(eng, conn, pending, stdioRes)
	if phase != "" {
		st.Phase = phase
	}
	return st.RenderFrame()
}

// RenderConceptualFullScreenTUI renders a single non-blocking full-screen TUI frame (`--render-fullscreen-tui`) for ConceptualVM.
func RenderConceptualFullScreenTUI(vm *ConceptualVM, pendingCmds []string, phase string) string {
	st := NewConceptualFullScreenTUI(vm, pendingCmds)
	if phase != "" {
		st.Phase = phase
	}
	return st.RenderFrame()
}

// RunFullScreenTUI runs the interactive full-screen TUI loop on (in, out).
// If in/out is a real character-device TTY, it enables raw mode via platform terminal helpers
// (term_linux.go, term_darwin.go, term_other.go), switches to the alternate screen buffer
// (\x1b[?1049h\x1b[?25l), queries terminal size, and restores the terminal on exit or interrupt.
// When driven by an io.Reader in tests, it processes the keystroke stream deterministically and returns the final frame.
func RunFullScreenTUI(state *FullScreenTUIState, in io.Reader, out io.Writer, interactive bool) string {
	if !interactive {
		// In non-interactive batch mode, drain any initial pending queue and render one full-screen frame
		for len(state.PendingQueue) > 0 {
			state.ExecuteFullEventStep()
		}
		state.Phase = "RUNNING"
		return state.RenderFrame()
	}

	isTTY := IsCharDeviceTTY(in, out)
	state.UseColor = isTTY
	state.Rows, state.Cols = GetTerminalSize(out)

	var restoreTerm func()
	var sigChan chan os.Signal
	if isTTY {
		if inFile, ok := in.(*os.File); ok {
			if rest, err := EnableRawTerminal(inFile.Fd()); err == nil {
				restoreTerm = rest
			}
		}
		_, _ = fmt.Fprint(out, ANSIEnterAltScreen)
		sigChan = make(chan os.Signal, 1)
		notifyTermSignals(sigChan)
		go func() {
			if _, ok := <-sigChan; ok {
				if restoreTerm != nil {
					restoreTerm()
				}
				_, _ = fmt.Fprint(out, ANSIExitAltScreen)
				os.Exit(0)
			}
		}()
		defer func() {
			signal.Stop(sigChan)
			close(sigChan)
			if restoreTerm != nil {
				restoreTerm()
			}
			_, _ = fmt.Fprint(out, ANSIExitAltScreen)
		}()
	}

	for {
		if isTTY {
			state.Rows, state.Cols = GetTerminalSize(out)
		}
		frame := state.RenderFrame()
		_, _ = fmt.Fprint(out, ANSIClearHome+frame+"\n")

		ev, err := ReadNextKeyEvent(in)
		if err != nil || ev.Kind == KeyEOF {
			state.Phase = "COMPLETED"
			break
		}
		if state.HandleKey(ev) {
			break
		}
	}

	state.UseColor = false
	return state.RenderFrame()
}
