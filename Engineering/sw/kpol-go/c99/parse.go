package c99

import (
	"fmt"
	"math/big"
	"regexp"
	"strings"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

// pyWS is Python's Unicode-aware \s; Go's \s is ASCII only.
const pyWS = `[\t\n\v\f\r \x1c-\x1f\x{85}\x{a0}\x{1680}\x{2000}-\x{200a}\x{2028}\x{2029}\x{202f}\x{205f}\x{3000}]`

// pyRe compiles a Python-style pattern, expanding \s to pyWS. The compiled
// expressions below are immutable and safe for concurrent use.
func pyRe(pattern string) *regexp.Regexp {
	return regexp.MustCompile(strings.ReplaceAll(pattern, `\s`, pyWS))
}

const (
	numTok  = `0x[0-9A-Fa-f]+u?|[0-9]+u?`
	numGrp  = `(` + numTok + `)`
	initGrp = `(\(-2147483647\s*-\s*1\)|-?[0-9]+)`
)

var (
	reTopo         = pyRe(`(?s)KM_SAFETY_TOPO_ORDER\s*\[[^\]]+\]\s*=\s*\{([^}]+)\}`)
	reTopoNum      = regexp.MustCompile(numTok)
	reTopoRev      = pyRe(`KM_SAFETY_TOPO_ORDER\s*\[\s*\(\s*KM_SAFETY_NUM_ACTIVE_TOPO\s*-\s*1u?\s*\)\s*-\s*topo_idx\s*\]`)
	reTopoFwd      = pyRe(`uint8_t\s+cid\s*=\s*KM_SAFETY_TOPO_ORDER\s*\[\s*topo_idx\s*\]\s*;`)
	reDescBlock    = pyRe(`(?s)KM_SAFETY_DESCRIPTORS\s*\[[^\]]+\]\s*=\s*\{(.*?)\n\};`)
	reDescRow      = pyRe(`\{\s*` + initGrp + `\s*,\s*` + numGrp + `\s*,\s*` + numGrp + `\s*,\s*` + numGrp + `\s*,\s*` + numGrp + `\s*,\s*` + numGrp + `\s*,\s*` + numGrp + `\s*\}`)
	reFaultGate    = pyRe(`(?s)if\s*\(\s*\(\s*!ev_param_valid\s*\)\s*\|\|\s*\(\s*!concept_valid\s*\)\s*\)\s*\{\s*ctx->rejects\+\+;\s*ctx->fault_propagations\+\+;\s*\*fault_rejected_out\s*=\s*true;\s*return\s+false;\s*\}`)
	rePredEq       = pyRe(`case\s+KM_CME_PRED_EQ:\s*pred_raw\s*=\s*\(\s*param_u32\s*(==|!=)\s*d->operand\s*\);`)
	rePredNeq      = pyRe(`case\s+KM_CME_PRED_NEQ:\s*pred_raw\s*=\s*\(\s*param_u32\s*(!=|==)\s*d->operand\s*\);`)
	rePredGt       = pyRe(`case\s+KM_CME_PRED_GT:\s*pred_raw\s*=\s*\(\s*ev_param\s*(>=|<=|>|<|==)\s*op_i32\s*\);`)
	rePredLt       = pyRe(`case\s+KM_CME_PRED_LT:\s*pred_raw\s*=\s*\(\s*ev_param\s*(<=|>=|<|>|==)\s*op_i32\s*\);`)
	reRange        = pyRe(`pred_raw\s*=\s*\(\s*ev_param\s*(>=|>)\s*lo_i32\s*\)\s*&&\s*\(\s*ev_param\s*(<=|<)\s*hi_i32\s*\);`)
	reActInc       = pyRe(`case\s+KM_CME_ACT_INC:\s*cand_u32\s*=\s*cur_u32\s*(\+|-)\s*1u;`)
	reActDec       = pyRe(`case\s+KM_CME_ACT_DEC:\s*cand_u32\s*=\s*cur_u32\s*(-|\+)\s*1u;`)
	reActAdd       = pyRe(`case\s+KM_CME_ACT_ADD:\s*cand_u32\s*=\s*cur_u32\s*(\+|-)\s*d->operand;`)
	reActSub       = pyRe(`case\s+KM_CME_ACT_SUB:\s*cand_u32\s*=\s*cur_u32\s*(-|\+)\s*d->operand;\s*arith_overflow\s*=\s*\(\(\(cur_u32\s*\^\s*d->operand\)\s*&\s*0x80000000u\)\s*(!=|==)\s*0u\)`)
	reInvariant    = pyRe(`\binvariant_true\s*=\s*([^;]+);`)
	reCommit       = pyRe(`\bcommit\s*=\s*([^;]+);`)
	reSelfSuppress = pyRe(`if\s*\(\s*target_cid\s*!=\s*cid\s*\)`)
)

// ParsedModule is the structure recovered from emitted C99 text
// (ParsedC99SafetyModule in the reference).
type ParsedModule struct {
	// TopoOrder is KM_SAFETY_TOPO_ORDER as written; TopoLoopReversed reports
	// that the cascade loop walks it backwards (mutant M3).
	TopoOrder        []int
	TopoLoopReversed bool
	Descriptors      []kpol.Descriptor
	HasFaultGate     bool
	PredEqOp         string
	PredNeqOp        string
	PredGtOp         string
	PredLtOp         string
	RangeSext        bool
	RangeLoOp        string
	RangeHiOp        string
	ActIncOp         string
	ActDecOp         string
	ActAddOp         string
	ActSubOp         string
	SubOvfXorOp      string

	InvariantChecksOverflow bool
	InvariantChecksNonneg   bool
	CommitChecksInvariant   bool
	HasSelfSuppress         bool
}

func parseError(format string, args ...any) error {
	return &kpol.Error{Code: "C99-PARSE", Msg: fmt.Sprintf(format, args...)}
}

// parsePyInt mirrors Python's int(text, 0) for the token shapes accepted by
// the reference regular expressions (optional '-', "0x" hex or decimal
// without leading zeros). Other shapes fail like Python's ValueError, which
// the reference leaves unhandled; here it is reported as C99-PARSE.
func parsePyInt(text string) (*big.Int, error) {
	bad := parseError("invalid literal for int() with base 0: '%s'", text)
	s := text
	neg := false
	if strings.HasPrefix(s, "-") {
		neg = true
		s = s[1:]
	}
	base := 10
	if strings.HasPrefix(s, "0x") || strings.HasPrefix(s, "0X") {
		base = 16
		s = s[2:]
	} else if len(s) > 1 && s[0] == '0' && strings.Trim(s, "0") != "" {
		return nil, bad
	}
	if s == "" {
		return nil, bad
	}
	v, ok := new(big.Int).SetString(s, base)
	if !ok {
		return nil, bad
	}
	if neg {
		v.Neg(v)
	}
	return v, nil
}

func parseLiteral(tok string) (*big.Int, error) {
	return parsePyInt(strings.TrimRight(tok, "uU"))
}

func low32(v *big.Int) uint32 {
	return uint32(new(big.Int).And(v, big.NewInt(0xFFFFFFFF)).Uint64())
}

func low8(v *big.Int) uint8 {
	return uint8(new(big.Int).And(v, big.NewInt(0xFF)).Uint64())
}

// ParseEmittedC99Source recovers descriptor tables, schedule and operators
// from emitted C99 text (parse_emitted_c99_source).
func ParseEmittedC99Source(src string) (*ParsedModule, error) {
	mTopo := reTopo.FindStringSubmatch(src)
	if mTopo == nil {
		return nil, parseError("missing KM_SAFETY_TOPO_ORDER array in C99 source")
	}
	var topoVals []int
	for _, tok := range reTopoNum.FindAllString(mTopo[1], -1) {
		v, err := parseLiteral(tok)
		if err != nil {
			return nil, err
		}
		if !v.IsInt64() || int64(int(v.Int64())) != v.Int64() {
			return nil, parseError("topological order constant %s is out of range", tok)
		}
		topoVals = append(topoVals, int(v.Int64()))
	}

	reversed := reTopoRev.MatchString(src)
	if !reversed && !reTopoFwd.MatchString(src) {
		return nil, parseError("unrecognized topological loop indexing in C99 source")
	}

	mBlock := reDescBlock.FindStringSubmatch(src)
	if mBlock == nil {
		return nil, parseError("missing KM_SAFETY_DESCRIPTORS table in C99 source")
	}
	var descs []kpol.Descriptor
	for cid, row := range reDescRow.FindAllStringSubmatch(mBlock[1], -1) {
		initRaw := strings.ReplaceAll(row[1], " ", "")
		var initVal *big.Int
		if initRaw == "(-2147483647-1)" {
			initVal = big.NewInt(-2147483648)
		} else {
			v, err := parsePyInt(initRaw)
			if err != nil {
				return nil, err
			}
			initVal = v
		}
		var fields [6]*big.Int
		for i := range fields {
			v, err := parseLiteral(row[2+i])
			if err != nil {
				return nil, err
			}
			fields[i] = v
		}
		descs = append(descs, kpol.Descriptor{
			CID:           cid,
			Name:          fmt.Sprintf("Concept_%d", cid),
			CurrentState:  low32(initVal),
			OperandVal:    low32(fields[0]),
			PredOpcode:    low8(fields[1]),
			GuardFlags:    low8(fields[2]),
			HazardLimit:   low8(fields[3]),
			ActionOpcode:  low8(fields[4]),
			SubscriberCID: low32(fields[5]),
		})
	}
	if len(descs) != NumConcepts {
		return nil, parseError("expected 64 rows in KM_SAFETY_DESCRIPTORS, got %d", len(descs))
	}

	p := &ParsedModule{TopoOrder: topoVals, TopoLoopReversed: reversed, Descriptors: descs}
	p.HasFaultGate = reFaultGate.MatchString(src)

	mEq := rePredEq.FindStringSubmatch(src)
	mNeq := rePredNeq.FindStringSubmatch(src)
	mGt := rePredGt.FindStringSubmatch(src)
	mLt := rePredLt.FindStringSubmatch(src)
	if mEq == nil || mNeq == nil || mGt == nil || mLt == nil {
		return nil, parseError("failed to parse predicate cases in C99 source")
	}
	p.PredEqOp, p.PredNeqOp, p.PredGtOp, p.PredLtOp = mEq[1], mNeq[1], mGt[1], mLt[1]

	p.RangeSext = strings.Contains(src, "km_u16_to_i32_sext((uint16_t)(d->operand & 0xFFFFu))") &&
		strings.Contains(src, "km_u16_to_i32_sext((uint16_t)((d->operand >> 16) & 0xFFFFu))")
	mRng := reRange.FindStringSubmatch(src)
	if mRng == nil {
		return nil, parseError("failed to parse KM_CME_PRED_RANGE comparison in C99 source")
	}
	p.RangeLoOp, p.RangeHiOp = mRng[1], mRng[2]

	mInc := reActInc.FindStringSubmatch(src)
	mDec := reActDec.FindStringSubmatch(src)
	mAdd := reActAdd.FindStringSubmatch(src)
	mSub := reActSub.FindStringSubmatch(src)
	if mInc == nil || mDec == nil || mAdd == nil || mSub == nil {
		return nil, parseError("failed to parse action cases in C99 source")
	}
	p.ActIncOp, p.ActDecOp, p.ActAddOp, p.ActSubOp, p.SubOvfXorOp = mInc[1], mDec[1], mAdd[1], mSub[1], mSub[2]

	inv := reInvariant.FindAllStringSubmatch(src, -1)
	if len(inv) < 2 {
		return nil, parseError("missing invariant_true assignment in C99 source")
	}
	invExpr := inv[len(inv)-1][1]
	p.InvariantChecksOverflow = strings.Contains(invExpr, "!arith_overflow")
	p.InvariantChecksNonneg = strings.Contains(invExpr, "(cand_u32 & 0x80000000u) == 0u")

	commits := reCommit.FindAllStringSubmatch(src, -1)
	if len(commits) < 2 {
		return nil, parseError("missing commit assignment in C99 source")
	}
	commitExpr := commits[len(commits)-1][1]
	p.CommitChecksInvariant = strings.Contains(commitExpr, "invariant_known") && strings.Contains(commitExpr, "invariant_true")

	p.HasSelfSuppress = reSelfSuppress.MatchString(src)
	return p, nil
}
