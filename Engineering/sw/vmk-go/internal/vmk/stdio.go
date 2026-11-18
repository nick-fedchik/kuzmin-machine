package vmk

import (
	"encoding/json"
	"fmt"
	"io"
	"strconv"
	"strings"
)

// StdioConfig holds the parsed `# @stdin` and `# @stdout` pragmas for a program.
type StdioConfig struct {
	StdinConcepts   []string `json:"stdin_concepts"`
	StdoutConcepts  []string `json:"stdout_concepts"`
	DefaultStdinCID int      `json:"default_stdin_cid"`
}

// ParseStdioDirectives extracts `# @stdin <Concept>` / `# @stdout <Concept>` pragmas or infers defaults.
func ParseStdioDirectives(sourceCode string, descs [64]ConceptDescriptor, activeCIDs []int) StdioConfig {
	nameToCID := make(map[string]int)
	for cid := 0; cid < 64; cid++ {
		if descs[cid].IsConfigured() {
			nameToCID[descs[cid].Name] = cid
		}
	}
	for _, cid := range activeCIDs {
		nameToCID[descs[cid].Name] = cid
	}

	var stdinNames []string
	var stdoutNames []string
	for _, line := range strings.Split(sourceCode, "\n") {
		s := strings.TrimSpace(line)
		var body string
		if strings.HasPrefix(s, "#") {
			body = strings.TrimSpace(s[1:])
		} else if strings.HasPrefix(s, "//") {
			body = strings.TrimSpace(s[2:])
		} else {
			continue
		}
		if strings.HasPrefix(body, "@stdin") {
			rest := strings.ReplaceAll(body[len("@stdin"):], ",", " ")
			stdinNames = append(stdinNames, strings.Fields(rest)...)
		} else if strings.HasPrefix(body, "@stdout") {
			rest := strings.ReplaceAll(body[len("@stdout"):], ",", " ")
			stdoutNames = append(stdoutNames, strings.Fields(rest)...)
		}
	}

	if len(stdinNames) == 0 && len(activeCIDs) > 0 {
		stdinNames = []string{descs[activeCIDs[0]].Name}
	}
	if len(stdoutNames) == 0 && len(activeCIDs) > 0 {
		for _, cid := range activeCIDs {
			stdoutNames = append(stdoutNames, descs[cid].Name)
		}
	}

	defaultCID := 0
	if len(activeCIDs) > 0 {
		defaultCID = activeCIDs[0]
	}
	if len(stdinNames) > 0 {
		if cid, ok := nameToCID[stdinNames[0]]; ok {
			defaultCID = cid
		}
	}

	return StdioConfig{
		StdinConcepts:   stdinNames,
		StdoutConcepts:  stdoutNames,
		DefaultStdinCID: defaultCID,
	}
}

// ParseTraceEventsSpec parses `--trace-events` strings like `0:10,0:100,0:invalid,C0:_`.
func ParseTraceEventsSpec(spec string, descs *[64]ConceptDescriptor) ([]QueuedEvent, error) {
	cleaned := strings.TrimSpace(spec)
	if cleaned == "" {
		return nil, fmt.Errorf("TRACE-SPEC: empty --trace-events specification")
	}

	nameToCID := make(map[string]int)
	if descs != nil {
		for cid := 0; cid < 64; cid++ {
			nameToCID[strings.ToLower(descs[cid].Name)] = cid
			nameToCID[fmt.Sprintf("c%d", cid)] = cid
			nameToCID[fmt.Sprintf("c%02d", cid)] = cid
			nameToCID[fmt.Sprintf("cid%d", cid)] = cid
		}
	} else {
		for cid := 0; cid < 64; cid++ {
			nameToCID[fmt.Sprintf("c%d", cid)] = cid
			nameToCID[fmt.Sprintf("c%02d", cid)] = cid
			nameToCID[fmt.Sprintf("cid%d", cid)] = cid
		}
	}

	resolveCID := func(tok string) (int, error) {
		tl := strings.ToLower(strings.TrimSpace(tok))
		if cid, ok := nameToCID[tl]; ok {
			return cid, nil
		}
		v, err := strconv.ParseInt(strings.TrimSpace(tok), 0, 32)
		if err != nil {
			return 0, fmt.Errorf("TRACE-SPEC: invalid CID %q", tok)
		}
		return int(v), nil
	}

	var events []QueuedEvent
	normalized := strings.ReplaceAll(cleaned, ";", ",")
	for _, rawTok := range strings.Split(normalized, ",") {
		tok := strings.TrimSpace(rawTok)
		if tok == "" {
			continue
		}
		parts := strings.Split(tok, ":")
		if len(parts) < 2 || len(parts) > 3 {
			return nil, fmt.Errorf("TRACE-SPEC: invalid event token %q", tok)
		}
		cid, err := resolveCID(parts[0])
		if err != nil {
			return nil, err
		}
		pStr := strings.ToLower(strings.TrimSpace(parts[1]))
		if len(parts) == 2 {
			if pStr == "invalid" || pStr == "_" || pStr == "fault" || pStr == "null_frame" {
				events = append(events, QueuedEvent{CID: cid, Param: 0, ParamValid: false})
			} else {
				pv, err := strconv.ParseInt(strings.TrimSpace(parts[1]), 0, 32)
				if err != nil {
					return nil, fmt.Errorf("TRACE-SPEC: invalid parameter in token %q", tok)
				}
				events = append(events, QueuedEvent{CID: cid, Param: int32(pv), ParamValid: true})
			}
		} else {
			pv := int64(0)
			if pStr != "invalid" && pStr != "_" {
				var err error
				pv, err = strconv.ParseInt(strings.TrimSpace(parts[1]), 0, 32)
				if err != nil {
					return nil, fmt.Errorf("TRACE-SPEC: invalid parameter in token %q", tok)
				}
			}
			vStr := strings.ToLower(strings.TrimSpace(parts[2]))
			switch vStr {
			case "invalid", "_", "0", "false", "fault":
				events = append(events, QueuedEvent{CID: cid, Param: int32(pv), ParamValid: false})
			case "valid", "1", "true", "ok":
				events = append(events, QueuedEvent{CID: cid, Param: int32(pv), ParamValid: true})
			default:
				return nil, fmt.Errorf("TRACE-SPEC: invalid validity flag %q in token %q", parts[2], tok)
			}
		}
	}
	if len(events) == 0 {
		return nil, fmt.Errorf("TRACE-SPEC: no events found in --trace-events specification")
	}
	return events, nil
}

// ParseStdioInputLine parses one STDIN line for BRAM64 mode into a QueuedEvent.
func ParseStdioInputLine(line string, descs [64]ConceptDescriptor, defaultCID int) (*QueuedEvent, error) {
	s := strings.TrimSpace(line)
	if s == "" || strings.HasPrefix(s, "#") || strings.HasPrefix(s, "//") {
		return nil, nil
	}

	nameToCID := make(map[string]int)
	for cid := 0; cid < 64; cid++ {
		nameToCID[strings.ToLower(descs[cid].Name)] = cid
		nameToCID[fmt.Sprintf("c%d", cid)] = cid
		nameToCID[fmt.Sprintf("c%02d", cid)] = cid
		nameToCID[fmt.Sprintf("cid%d", cid)] = cid
	}

	resolveTarget := func(tok string) (int, error) {
		tl := strings.ToLower(strings.TrimSpace(tok))
		if cid, ok := nameToCID[tl]; ok {
			return cid, nil
		}
		v, err := strconv.ParseInt(strings.TrimSpace(tok), 0, 32)
		if err != nil {
			return 0, fmt.Errorf("STDIO-PARSE: unknown concept or CID %q", tok)
		}
		return int(v), nil
	}

	resolveParam := func(tok string) (int32, bool, error) {
		tl := strings.ToLower(strings.TrimSpace(tok))
		if tl == "_" || tl == "invalid" || tl == "fault" || tl == "null" || tl == "nan" {
			return 0, false, nil
		}
		v, err := strconv.ParseInt(strings.TrimSpace(tok), 0, 32)
		if err != nil {
			return 0, false, fmt.Errorf("STDIO-PARSE: invalid integer parameter %q", tok)
		}
		return int32(v), true, nil
	}

	if strings.HasPrefix(s, "{") && strings.HasSuffix(s, "}") {
		var obj map[string]any
		if err := json.Unmarshal([]byte(s), &obj); err != nil {
			return nil, fmt.Errorf("STDIO-PARSE: malformed JSONL %q", s)
		}
		cid := defaultCID
		if v, ok := obj["cid"]; ok {
			if vf, ok := v.(float64); ok {
				cid = int(vf)
			}
		} else if v, ok := obj["concept"]; ok {
			var err error
			cid, err = resolveTarget(fmt.Sprint(v))
			if err != nil {
				return nil, err
			}
		}
		valid := true
		if v, ok := obj["valid"].(bool); ok && !v {
			valid = false
		}
		var param int32
		if rawP, ok := obj["param"]; ok {
			switch pv := rawP.(type) {
			case string:
				pVal, pOk, err := resolveParam(pv)
				if err != nil {
					return nil, err
				}
				param = pVal
				if !pOk {
					valid = false
				}
			case float64:
				param = int32(pv)
			}
		}
		return &QueuedEvent{CID: cid, Param: param, ParamValid: valid}, nil
	}

	if strings.Contains(s, ":") && !strings.Contains(s, " ") {
		evs, err := ParseTraceEventsSpec(s, &descs)
		if err != nil {
			return nil, err
		}
		return &evs[0], nil
	}

	parts := strings.Fields(s)
	if len(parts) > 0 && strings.EqualFold(parts[0], "write") {
		parts = parts[1:]
	}
	switch len(parts) {
	case 1:
		p, v, err := resolveParam(parts[0])
		if err != nil {
			return nil, err
		}
		return &QueuedEvent{CID: defaultCID, Param: p, ParamValid: v}, nil
	case 2:
		cid, err := resolveTarget(parts[0])
		if err != nil {
			return nil, err
		}
		p, v, err := resolveParam(parts[1])
		if err != nil {
			return nil, err
		}
		return &QueuedEvent{CID: cid, Param: p, ParamValid: v}, nil
	case 3:
		cid, err := resolveTarget(parts[0])
		if err != nil {
			return nil, err
		}
		p, _, err := resolveParam(parts[1])
		if err != nil {
			return nil, err
		}
		vTok := strings.ToLower(strings.TrimSpace(parts[2]))
		valid := !(vTok == "_" || vTok == "0" || vTok == "false" || vTok == "invalid" || vTok == "fault")
		return &QueuedEvent{CID: cid, Param: p, ParamValid: valid}, nil
	default:
		return nil, fmt.Errorf("STDIO-PARSE: unsupported STDIN line format %q", s)
	}
}

// StdioExecutionResult captures the streams from a STDIO execution session.
type StdioExecutionResult struct {
	StdinRecords []QueuedEvent `json:"stdin_records"`
	StdoutLines  []string      `json:"stdout_lines"`
	StderrLines  []string      `json:"stderr_lines"`
}

// RunStdioStream processes STDIN lines on a BRAM64Engine, routing COMMITs to stdoutWriter and REJECTs to stderrWriter.
func RunStdioStream(
	eng *BRAM64Engine,
	lines []string,
	cfg *StdioConfig,
	stdoutWriter, stderrWriter io.Writer,
) (*StdioExecutionResult, error) {
	descs := *eng.Descriptors()
	var scfg StdioConfig
	if cfg != nil {
		scfg = *cfg
	} else {
		scfg = ParseStdioDirectives(eng.SourceCode, descs, eng.ActiveCIDs)
	}
	stdoutSet := make(map[string]bool)
	for _, nm := range scfg.StdoutConcepts {
		stdoutSet[nm] = true
	}

	res := &StdioExecutionResult{
		StdinRecords: []QueuedEvent{},
		StdoutLines:  []string{},
		StderrLines:  []string{},
	}

	for _, rawLine := range lines {
		ev, err := ParseStdioInputLine(rawLine, descs, scfg.DefaultStdinCID)
		if err != nil {
			return nil, err
		}
		if ev == nil {
			continue
		}
		res.StdinRecords = append(res.StdinRecords, *ev)
		waveSteps := eng.StepEvent(ev.CID, ev.Param, ev.ParamValid)
		for _, st := range waveSteps {
			if st.Verdict == VerdictCommit || st.Verdict == VerdictSuppressedSelf {
				if len(stdoutSet) == 0 || stdoutSet[st.ConceptName] {
					msg := fmt.Sprintf(
						"COMMIT: %s[cid=%d] = %d (pre=%d, depth=%d, param=%d, valid=%s)",
						st.ConceptName, st.CID, st.PostW0, st.PreW0, st.Depth, st.Param, ValidSymbol(st.ParamValid),
					)
					res.StdoutLines = append(res.StdoutLines, msg)
					if stdoutWriter != nil {
						_, _ = fmt.Fprintln(stdoutWriter, msg)
					}
				}
			} else {
				errMsg := fmt.Sprintf(
					"%s: %s[cid=%d] kept W0=%d (depth=%d, param=%d, valid=%s, pred=(%s)=>%v, cand=%d, gate=(%s)=>%v)",
					st.Verdict, st.ConceptName, st.CID, st.PostW0, st.Depth, st.Param, ValidSymbol(st.ParamValid),
					st.PredFormula, st.PredMatch, st.CandidateW0, st.InvFormula, st.InvOK,
				)
				res.StderrLines = append(res.StderrLines, errMsg)
				if stderrWriter != nil {
					_, _ = fmt.Fprintln(stderrWriter, errMsg)
				}
			}
		}
	}
	return res, nil
}

// RunConceptualStdioStream processes interactive/command STDIN lines on a ConceptualVM
// (`write Sum 10`, `read Sum`, `call Nod 120 6`, `call Factorial 5`, `write If _`, `call Tachometer Tick`).
func RunConceptualStdioStream(
	vm *ConceptualVM,
	lines []string,
	stdoutWriter, stderrWriter io.Writer,
) (*StdioExecutionResult, error) {
	res := &StdioExecutionResult{
		StdinRecords: []QueuedEvent{},
		StdoutLines:  []string{},
		StderrLines:  []string{},
	}

	for _, rawLine := range lines {
		s := strings.TrimSpace(rawLine)
		if s == "" || strings.HasPrefix(s, "#") || strings.HasPrefix(s, "//") {
			continue
		}
		vm.StdinHistory = append(vm.StdinHistory, s)
		prevOutLen := len(vm.StdoutHistory)
		prevErrLen := len(vm.StderrHistory)

		parts := strings.Fields(s)
		cmd := strings.ToLower(parts[0])

		switch cmd {
		case "write", "toggle":
			if len(parts) < 2 {
				return nil, fmt.Errorf("STDIO-CONCEPTUAL: %s requires concept name", cmd)
			}
			target := strings.ToLower(parts[1])
			valTok := "1"
			if len(parts) >= 3 {
				valTok = parts[2]
			}
			switch target {
			case "if":
				vm.ExecuteIfToggleImpulse()
				res.StdinRecords = append(res.StdinRecords, QueuedEvent{CID: 0, Param: 1, ParamValid: true})
			case "sum":
				if valTok == "_" || strings.EqualFold(valTok, "invalid") {
					vm.ExecuteSumWrite(0, false)
					res.StdinRecords = append(res.StdinRecords, QueuedEvent{CID: 0, Param: 0, ParamValid: false})
				} else {
					fv, err := strconv.ParseFloat(valTok, 64)
					if err != nil {
						return nil, err
					}
					vm.ExecuteSumWrite(fv, true)
					res.StdinRecords = append(res.StdinRecords, QueuedEvent{CID: 0, Param: int32(fv), ParamValid: true})
				}
			default:
				return nil, fmt.Errorf("STDIO-CONCEPTUAL: unknown write concept %q", parts[1])
			}
		case "read":
			if len(parts) < 2 {
				return nil, fmt.Errorf("STDIO-CONCEPTUAL: read requires concept name")
			}
			target := strings.ToLower(parts[1])
			if target == "sum" {
				_, _, _ = vm.ExecuteSumReadWithPostDotReset()
				res.StdinRecords = append(res.StdinRecords, QueuedEvent{CID: 0, Param: 0, ParamValid: true})
			} else if cid, ok := vm.NameToCID[target]; ok {
				slot := vm.Slots[cid]
				msg := fmt.Sprintf("READ: %s = %s", slot.Name, slot.FormatValue())
				vm.StdoutHistory = append(vm.StdoutHistory, msg)
				res.StdinRecords = append(res.StdinRecords, QueuedEvent{CID: cid, Param: 0, ParamValid: slot.Valid})
			} else {
				return nil, fmt.Errorf("STDIO-CONCEPTUAL: unknown read concept %q", parts[1])
			}
		case "call":
			if len(parts) < 2 {
				return nil, fmt.Errorf("STDIO-CONCEPTUAL: call requires concept name")
			}
			target := strings.ToLower(parts[1])
			switch target {
			case "nod":
				if len(parts) < 4 {
					return nil, fmt.Errorf("STDIO-CONCEPTUAL: call Nod requires 2 integer arguments")
				}
				a, err := strconv.ParseInt(parts[2], 10, 64)
				if err != nil {
					return nil, err
				}
				b, err := strconv.ParseInt(parts[3], 10, 64)
				if err != nil {
					return nil, err
				}
				vm.ExecuteNodCall(a, b)
				res.StdinRecords = append(res.StdinRecords, QueuedEvent{CID: 0, Param: int32(a), ParamValid: true})
			case "factorial":
				if len(parts) < 3 {
					return nil, fmt.Errorf("STDIO-CONCEPTUAL: call Factorial requires 1 integer argument")
				}
				n, err := strconv.ParseInt(parts[2], 10, 64)
				if err != nil {
					return nil, err
				}
				vm.ExecuteFactorialCall(n)
				res.StdinRecords = append(res.StdinRecords, QueuedEvent{CID: 0, Param: int32(n), ParamValid: true})
			case "tachometer":
				evKind := "Tick"
				if len(parts) >= 3 {
					evKind = parts[2]
				}
				dt := 1.0
				if len(parts) >= 4 {
					dt, _ = strconv.ParseFloat(parts[3], 64)
				}
				vm.ExecuteTachometerEvent(evKind, dt)
				res.StdinRecords = append(res.StdinRecords, QueuedEvent{CID: 0, Param: int32(dt), ParamValid: true})
			default:
				return nil, fmt.Errorf("STDIO-CONCEPTUAL: unknown call target %q", parts[1])
			}
		default:
			return nil, fmt.Errorf("STDIO-CONCEPTUAL: unknown command %q (expected write, toggle, read, or call)", parts[0])
		}

		for _, msg := range vm.StdoutHistory[prevOutLen:] {
			res.StdoutLines = append(res.StdoutLines, msg)
			if stdoutWriter != nil {
				_, _ = fmt.Fprintln(stdoutWriter, msg)
			}
		}
		for _, errMsg := range vm.StderrHistory[prevErrLen:] {
			res.StderrLines = append(res.StderrLines, errMsg)
			if stderrWriter != nil {
				_, _ = fmt.Fprintln(stderrWriter, errMsg)
			}
		}
	}
	return res, nil
}
