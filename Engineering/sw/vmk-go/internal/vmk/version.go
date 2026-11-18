package vmk

import (
	"fmt"
	"regexp"
	"strings"
)

// Version is the SemVer 2.0.0 release version of the Go VMK emulator and TUI debugger.
const Version = "0.1.0"

// Execution modes supported by VMK.
const (
	ModeBRAM64     = "bram64"
	ModeConceptual = "conceptual"
)

// Step verdicts matching km_concept_micro_engine.sv and kpol_debugger.py.
const (
	VerdictCommit          = "COMMIT"
	VerdictRejectGuard     = "REJECT_GUARD"
	VerdictRejectInvariant = "REJECT_INVARIANT"
	VerdictRejectFault     = "REJECT_FAULT"
	VerdictSuppressedSelf  = "SUPPRESSED_SELF"
)

// CME-RAW-1 predicate opcodes (0..7).
const (
	PredNOP     uint8 = 0x00
	PredEQ      uint8 = 0x01
	PredNEQ     uint8 = 0x02
	PredGT      uint8 = 0x03
	PredLT      uint8 = 0x04
	PredRANGE   uint8 = 0x05
	PredBITMASK uint8 = 0x06
	PredUGT     uint8 = 0x07
)

// CME-RAW-1 action opcodes (0..5).
const (
	ActAssign uint8 = 0x00
	ActInc    uint8 = 0x01
	ActDec    uint8 = 0x02
	ActAdd    uint8 = 0x03
	ActSub    uint8 = 0x04
	ActNOP    uint8 = 0x05
)

// CME-RAW-1 guard flags in W2[15:8].
const (
	GuardAssumptionEn     uint8 = 0x01
	GuardInvariantEn      uint8 = 0x02
	GuardHazardEn         uint8 = 0x04
	GuardInvertAssumption uint8 = 0x08
	GuardSubscriberEn     uint8 = 0x10
)

// Hardware IDs for CFG-P ("KPMC") and CFG-P-HA ("KPHA").
const (
	HWIDCfgP   uint32 = 0x4B504D43
	HWIDCfgPHA uint32 = 0x4B504841
)

// TargetIOError represents a hardware/SSH target connection error (exit code 2).
type TargetIOError struct {
	Target string
	Host   string
	Detail string
}

func (e *TargetIOError) Error() string {
	return fmt.Sprintf("VMK-TARGET-IO: failed to connect or execute on target %q (%s): %s", e.Target, e.Host, e.Detail)
}

var identRegex = regexp.MustCompile(`[^0-9A-Za-z_]`)

// SanitizeIdent normalizes a concept identifier to a C/KPOL-safe name.
func SanitizeIdent(name, fallback string) string {
	s := strings.TrimSpace(name)
	s = identRegex.ReplaceAllString(s, "_")
	if s == "" {
		return fallback
	}
	if s[0] >= '0' && s[0] <= '9' {
		s = "_" + s
	}
	return s
}

// ValidSymbol returns "1" for valid (defined) and "_" for invalid (uncertainty).
func ValidSymbol(valid bool) string {
	if valid {
		return "1"
	}
	return "_"
}
