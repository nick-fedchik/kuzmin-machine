package vmk

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"
)

// CompiledKPOL holds the result of compiling a .kpol source file or loading a 1024-byte .bin image.
type CompiledKPOL struct {
	ModuleName       string
	Profile          string
	SourceCode       string
	ConceptNames     []string
	BRAMImage        []byte
	DoGoBytecodeHex  []string
	ExecDescriptors  *[64]ConceptDescriptor
}

var (
	reProblemName  = regexp.MustCompile(`(?m)\bProblem\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{`)
	reStateDecl    = regexp.MustCompile(`(?m)\bstate\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z0-9_]+)\s*=\s*(-?[0-9]+)\s*;`)
	reEventDecl    = regexp.MustCompile(`(?m)\bevent\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z0-9_]+)\s*\)\s*;`)
	reRuleDecl     = regexp.MustCompile(`(?ms)\brule\s+([A-Za-z_][A-Za-z0-9_]*)\s+on\s+(change\s*\(\s*[A-Za-z_][A-Za-z0-9_]*\s*\)|[A-Za-z_][A-Za-z0-9_]*)(?:\s+when\s+([^{]+))?\s*\{\s*set\s+([A-Za-z_][A-Za-z0-9_]*)\s*:=\s*([^;]+);\s*\}`)
	reChangeWatch  = regexp.MustCompile(`^change\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)$`)
	reAuthConcept  = regexp.MustCompile(`(?m)\bConcept\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,\s*(-?[0-9]+)`)
	reAuthSub      = regexp.MustCompile(`(?m)\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:•|\(\*\))\s*Assign\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,\s*([A-Za-z_][A-Za-z0-9_]*)\s*([+\-*])\s*(-?[0-9]+)\s*\)`)
)

func stripComments(src string) string {
	var lines []string
	for _, line := range strings.Split(src, "\n") {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "#") || strings.HasPrefix(trimmed, "//") {
			continue
		}
		if idx := strings.Index(line, "//"); idx >= 0 {
			line = line[:idx]
		}
		if idx := strings.Index(line, "#"); idx >= 0 {
			line = line[:idx]
		}
		lines = append(lines, line)
	}
	return strings.Join(lines, "\n")
}

// CompileKPOLSource compiles KPOL-CME-1, KPOL-CME-2, or KPOL-AUTH source text into a 1024-byte CME-RAW-1 BRAM image.
func CompileKPOLSource(sourceCode, profile string) (*CompiledKPOL, error) {
	if profile == "" {
		profile = "KPOL-CME-2"
	}
	if profile == "KPOL-AUTH" {
		return compileKPOLAuth(sourceCode)
	}
	if profile != "KPOL-CME-1" && profile != "KPOL-CME-2" {
		return nil, fmt.Errorf("VMK-COMPILE: unsupported profile %q", profile)
	}

	clean := stripComments(sourceCode)
	modMatch := reProblemName.FindStringSubmatch(clean)
	if len(modMatch) < 2 {
		return nil, fmt.Errorf("VMK-COMPILE: missing Problem <Name> declaration")
	}
	modName := modMatch[1]

	stateMatches := reStateDecl.FindAllStringSubmatch(clean, -1)
	if len(stateMatches) == 0 || len(stateMatches) > 64 {
		return nil, fmt.Errorf("VMK-COMPILE: expected 1..64 states, got %d", len(stateMatches))
	}
	if profile == "KPOL-CME-1" && len(stateMatches) != 1 {
		return nil, fmt.Errorf("B3-SHAPE: KPOL-CME-1 requires exactly 1 state, got %d", len(stateMatches))
	}

	stateIndex := make(map[string]int)
	var conceptNames []string
	var initVals []int32
	for cid, m := range stateMatches {
		sName := m[1]
		sType := m[2]
		if sType != "Int32" {
			return nil, fmt.Errorf("VMK-COMPILE: state %s must be Int32, got %s", sName, sType)
		}
		iv, err := strconv.ParseInt(m[3], 10, 32)
		if err != nil || iv < 0 {
			return nil, fmt.Errorf("VMK-COMPILE: state %s invalid non-negative Int32 initial value %q", sName, m[3])
		}
		stateIndex[sName] = cid
		conceptNames = append(conceptNames, sName)
		initVals = append(initVals, int32(iv))
	}

	eventParam := make(map[string]string)
	for _, m := range reEventDecl.FindAllStringSubmatch(clean, -1) {
		if m[3] != "Int32" {
			return nil, fmt.Errorf("VMK-COMPILE: event %s parameter %s must be Int32", m[1], m[2])
		}
		eventParam[m[1]] = m[2]
	}

	type parsedRule struct {
		name      string
		onClause  string
		guardExpr string
		target    string
		actExpr   string
		isChange  bool
		watchVar  string
	}

	rulesByTarget := make(map[string]parsedRule)
	subscriberOf := make(map[string]string)

	for _, m := range reRuleDecl.FindAllStringSubmatch(clean, -1) {
		rName := strings.TrimSpace(m[1])
		onCl := strings.TrimSpace(m[2])
		gExpr := strings.TrimSpace(m[3])
		target := strings.TrimSpace(m[4])
		aExpr := strings.TrimSpace(m[5])

		pr := parsedRule{
			name:      rName,
			onClause:  onCl,
			guardExpr: gExpr,
			target:    target,
			actExpr:   aExpr,
		}
		if cm := reChangeWatch.FindStringSubmatch(onCl); len(cm) == 2 {
			pr.isChange = true
			pr.watchVar = cm[1]
			subscriberOf[pr.watchVar] = target
		}
		rulesByTarget[target] = pr
	}

	if len(rulesByTarget) != len(conceptNames) {
		return nil, fmt.Errorf("VMK-COMPILE: expected 1 rule per state (%d states, %d rules)", len(conceptNames), len(rulesByTarget))
	}

	var descs [64]ConceptDescriptor
	for cid := 0; cid < 64; cid++ {
		descs[cid] = ConceptDescriptor{
			CID:      cid,
			Name:     fmt.Sprintf("Concept_%d", cid),
			TypeName: "Int32",
		}
	}

	for cid, sName := range conceptNames {
		rule := rulesByTarget[sName]
		inputVar := rule.watchVar
		if !rule.isChange {
			inputVar = eventParam[rule.onClause]
		}

		predOp, invert, guardUsesOp, guardOpU32, err := parseGuardToCME(rule.guardExpr, inputVar)
		if err != nil {
			return nil, err
		}
		actOp, actUsesOp, actOpU32, err := parseActionToCME(rule.actExpr, sName, inputVar)
		if err != nil {
			return nil, err
		}
		if guardUsesOp && actUsesOp {
			return nil, fmt.Errorf("CME2-OPERAND-COLLISION: rule %s uses both guard literal and step != 1", rule.name)
		}
		opU32 := guardOpU32
		if !guardUsesOp {
			opU32 = actOpU32
		}

		gFlags := GuardAssumptionEn | GuardInvariantEn
		if invert {
			gFlags |= GuardInvertAssumption
		}
		var subCID uint32
		if dstName, ok := subscriberOf[sName]; ok && profile == "KPOL-CME-2" {
			subCID = uint32(stateIndex[dstName])
			gFlags |= GuardSubscriberEn
		}

		descs[cid] = ConceptDescriptor{
			CID:           cid,
			Name:          sName,
			TypeName:      "Int32",
			CurrentState:  uint32(initVals[cid]),
			OperandVal:    opU32,
			PredOpcode:    predOp,
			GuardFlags:    gFlags,
			HazardLimit:   0,
			ActionOpcode:  actOp,
			SubscriberCID: subCID,
		}
	}

	return &CompiledKPOL{
		ModuleName:   modName,
		Profile:      profile,
		SourceCode:   strings.TrimSpace(sourceCode),
		ConceptNames: conceptNames,
		BRAMImage:    PackBRAM(descs),
	}, nil
}

func parseGuardToCME(guardStr, inputVar string) (uint8, bool, bool, uint32, error) {
	g := strings.TrimSpace(guardStr)
	if g == "" || g == "true" {
		return PredNOP, false, false, 0, nil
	}
	if g == "false" {
		return PredNOP, true, false, 0, nil
	}
	invert := false
	for strings.HasPrefix(g, "not ") || strings.HasPrefix(g, "not(") || strings.HasPrefix(g, "!") {
		invert = !invert
		if strings.HasPrefix(g, "not") {
			g = strings.TrimSpace(g[3:])
		} else {
			g = strings.TrimSpace(g[1:])
		}
		if strings.HasPrefix(g, "(") && strings.HasSuffix(g, ")") {
			g = strings.TrimSpace(g[1 : len(g)-1])
		}
	}
	if strings.HasPrefix(g, "(") && strings.HasSuffix(g, ")") && !strings.Contains(g, " and ") {
		g = strings.TrimSpace(g[1 : len(g)-1])
	}

	if strings.Contains(g, " and ") {
		parts := strings.Split(g, " and ")
		if len(parts) != 2 {
			return 0, false, false, 0, fmt.Errorf("CME2-RANGE: unsupported compound guard %q", guardStr)
		}
		opL, valL, err := parseSingleCmp(parts[0], inputVar)
		if err != nil {
			return 0, false, false, 0, err
		}
		opR, valR, err := parseSingleCmp(parts[1], inputVar)
		if err != nil {
			return 0, false, false, 0, err
		}
		var loVal, hiVal *int64
		for _, item := range []struct {
			op  string
			val int64
		}{{opL, valL}, {opR, valR}} {
			switch item.op {
			case ">=":
				v := item.val
				loVal = &v
			case ">":
				v := item.val + 1
				loVal = &v
			case "<=":
				v := item.val
				hiVal = &v
			case "<":
				v := item.val - 1
				hiVal = &v
			default:
				return 0, false, false, 0, fmt.Errorf("CME2-RANGE: invalid range operator %s", item.op)
			}
		}
		if loVal == nil || hiVal == nil || *loVal < -32768 || *hiVal > 32767 || *loVal > *hiVal {
			return 0, false, false, 0, fmt.Errorf("CME2-RANGE: invalid int16 range bounds")
		}
		packed := (uint32(uint16(int16(*hiVal))) << 16) | uint32(uint16(int16(*loVal)))
		return PredRANGE, invert, true, packed, nil
	}

	op, val, err := parseSingleCmp(g, inputVar)
	if err != nil {
		return 0, false, false, 0, err
	}
	opU32 := uint32(int32(val))
	switch op {
	case "==":
		return PredEQ, invert, true, opU32, nil
	case "!=":
		return PredNEQ, invert, true, opU32, nil
	case "<":
		return PredLT, invert, true, opU32, nil
	case ">":
		return PredGT, invert, true, opU32, nil
	case ">=":
		return PredLT, !invert, true, opU32, nil
	case "<=":
		return PredGT, !invert, true, opU32, nil
	default:
		return 0, false, false, 0, fmt.Errorf("CME2-GUARD: unsupported operator %s", op)
	}
}

func parseSingleCmp(expr, inputVar string) (string, int64, error) {
	s := strings.TrimSpace(expr)
	if strings.HasPrefix(s, "(") && strings.HasSuffix(s, ")") {
		s = strings.TrimSpace(s[1 : len(s)-1])
	}
	ops := []string{"==", "!=", ">=", "<=", ">", "<"}
	flip := map[string]string{"<": ">", ">": "<", "<=": ">=", ">=": "<=", "==": "==", "!=": "!="}
	for _, op := range ops {
		if idx := strings.Index(s, op); idx > 0 {
			lhs := strings.TrimSpace(s[:idx])
			rhs := strings.TrimSpace(s[idx+len(op):])
			if lhs == inputVar {
				v, err := strconv.ParseInt(rhs, 10, 64)
				if err != nil {
					return "", 0, err
				}
				return op, v, nil
			}
			if rhs == inputVar {
				v, err := strconv.ParseInt(lhs, 10, 64)
				if err != nil {
					return "", 0, err
				}
				return flip[op], v, nil
			}
		}
	}
	return "", 0, fmt.Errorf("CME2-GUARD: cannot parse comparison %q on %s", expr, inputVar)
}

func parseActionToCME(actStr, stateName, inputVar string) (uint8, bool, uint32, error) {
	a := strings.TrimSpace(actStr)
	if a == inputVar {
		return ActAssign, false, 0, nil
	}
	for _, op := range []string{"+", "-"} {
		if idx := strings.Index(a, op); idx > 0 {
			lhs := strings.TrimSpace(a[:idx])
			rhs := strings.TrimSpace(a[idx+1:])
			var stepStr string
			if lhs == stateName {
				stepStr = rhs
			} else if op == "+" && rhs == stateName {
				stepStr = lhs
			} else {
				continue
			}
			stepVal, err := strconv.ParseInt(stepStr, 10, 32)
			if err != nil || stepVal < 1 {
				return 0, false, 0, fmt.Errorf("CME2-ACTION: invalid step literal %q", stepStr)
			}
			if stepVal == 1 {
				if op == "+" {
					return ActInc, false, 0, nil
				}
				return ActDec, false, 0, nil
			}
			if op == "+" {
				return ActAdd, true, uint32(int32(stepVal)), nil
			}
			return ActSub, true, uint32(int32(stepVal)), nil
		}
	}
	return 0, false, 0, fmt.Errorf("CME2-ACTION: unsupported action %q", actStr)
}

func kmPackInstr(opc, subOp, flags, operand uint32) uint32 {
	return ((opc & 0x0F) << 28) | ((subOp & 0x0F) << 24) | ((flags & 0xFF) << 16) | (operand & 0xFFFF)
}

func compileKPOLAuth(sourceCode string) (*CompiledKPOL, error) {
	conceptMatches := reAuthConcept.FindAllStringSubmatch(sourceCode, -1)
	if len(conceptMatches) == 0 {
		return nil, fmt.Errorf("KPOL-AUTH: no Concept(...) declarations found")
	}
	stateIndex := make(map[string]int)
	var cNames []string
	var initVals []int32
	for cid, m := range conceptMatches {
		name := m[1]
		iv, err := strconv.ParseInt(m[2], 10, 32)
		if err != nil {
			return nil, err
		}
		stateIndex[name] = cid
		cNames = append(cNames, name)
		initVals = append(initVals, int32(iv))
	}

	var bramDescs [64]ConceptDescriptor
	var execDescs [64]ConceptDescriptor
	for cid := 0; cid < 64; cid++ {
		nm := fmt.Sprintf("Concept_%d", cid)
		if cid < len(cNames) {
			nm = cNames[cid]
		}
		bramDescs[cid] = ConceptDescriptor{
			CID:      cid,
			Name:     nm,
			TypeName: "Int32",
		}
		execDescs[cid] = bramDescs[cid]
	}

	for cid := range cNames {
		bramDescs[cid].CurrentState = uint32(initVals[cid])
		bramDescs[cid].GuardFlags = GuardInvariantEn
		execDescs[cid].CurrentState = uint32(initVals[cid])
		execDescs[cid].GuardFlags = GuardAssumptionEn | GuardInvariantEn
	}

	var dogoHex []string
	for _, sm := range reAuthSub.FindAllStringSubmatch(sourceCode, -1) {
		owner := sm[1]
		dst := sm[2]
		src := sm[3]
		op := sm[4]
		lit, _ := strconv.ParseInt(sm[5], 10, 32)

		ownerCID := stateIndex[owner]
		dstCID := stateIndex[dst]
		srcCID := stateIndex[src]

		bramDescs[ownerCID].GuardFlags |= GuardSubscriberEn
		bramDescs[ownerCID].SubscriberCID = uint32(dstCID)

		execDescs[ownerCID].PredOpcode = PredGT
		execDescs[ownerCID].OperandVal = 0
		execDescs[ownerCID].GuardFlags = GuardAssumptionEn | GuardInvariantEn | GuardSubscriberEn
		execDescs[ownerCID].ActionOpcode = ActAssign
		execDescs[ownerCID].SubscriberCID = uint32(dstCID)

		execDescs[dstCID].PredOpcode = PredNOP
		execDescs[dstCID].OperandVal = uint32(int32(lit))
		execDescs[dstCID].GuardFlags = GuardAssumptionEn | GuardInvariantEn
		if op == "+" {
			if lit == 1 {
				execDescs[dstCID].ActionOpcode = ActAdd
			} else {
				execDescs[dstCID].ActionOpcode = ActAdd
			}
		} else if op == "-" {
			execDescs[dstCID].ActionOpcode = ActSub
		}

		var doOp uint32
		if op == "-" {
			doOp = 1
		} else if op == "*" {
			doOp = 2
		}
		words := []uint32{
			kmPackInstr(0x1, 0x2, 0, uint32(srcCID)),
			kmPackInstr(0x3, 0x0, 0, uint32(lit)&0xFFFF),
			kmPackInstr(0x2, doOp, 0, 0),
			kmPackInstr(0x1, 0x1, 0, uint32(dstCID)),
			kmPackInstr(0x5, 0x0, 0, 0),
		}
		for _, w := range words {
			dogoHex = append(dogoHex, fmt.Sprintf("0x%08X", w))
		}
	}

	return &CompiledKPOL{
		ModuleName:      "AuthCounterSubset",
		Profile:         "KPOL-AUTH",
		SourceCode:      strings.TrimSpace(sourceCode),
		ConceptNames:    cNames,
		BRAMImage:       PackBRAM(bramDescs),
		DoGoBytecodeHex: dogoHex,
		ExecDescriptors: &execDescs,
	}, nil
}
