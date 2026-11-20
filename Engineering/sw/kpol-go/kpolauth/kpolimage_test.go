package kpolauth

import (
	"bytes"
	"testing"

	"github.com/nick-fedchik/kuzmin-machine/Engineering/sw/kpol-go/kpol"
)

// TestImageMatchesKpolDescriptorFrame builds the same image from the lowered
// tables with kpol.PackImage and compares it byte for byte (KPA-L-15), then
// checks D-A9: the assumption guard bit is never set, so the image is not an
// executable CME profile.
func TestImageMatchesKpolDescriptorFrame(t *testing.T) {
	for name, src := range map[string]string{
		"marks":   guideMarks,
		"sheets":  guideSheets,
		"thermal": thermalGraph,
		"chain":   "Concept(A, 9)\nConcept(B, 8, Upper=3)\nConcept(C, 7)\nA • Assign(B, A)\nB • Assign(C, B)\nOnAbort(B) • Assign(A, 0)",
	} {
		art := mustLower(t, src)
		ds := make([]kpol.Descriptor, 0, len(art.Concepts))
		for _, c := range art.Concepts {
			d := kpol.Descriptor{CID: c.CID, CurrentState: uint32(c.InitVal)}
			if c.Flags&FlagHWProtected != 0 {
				d.GuardFlags |= kpol.GuardInvariantEn
			}
			for _, s := range art.Subscriptions {
				if s.OwnerCID == c.CID && s.Phase == PhasePostChange {
					d.GuardFlags |= kpol.GuardSubscriberEn
					d.SubscriberCID = uint32(s.TargetCID)
				}
			}
			ds = append(ds, d)
		}
		if want := kpol.PackImage(ds); !bytes.Equal(art.BRAMImage(), want) {
			t.Errorf("%s: image differs from kpol.PackImage", name)
		}
		back, err := kpol.Disassemble(art.BRAMImage())
		if err != nil {
			t.Fatal(err)
		}
		for _, d := range back {
			if d.GuardFlags&kpol.GuardAssumptionEn != 0 || d.PredOpcode != 0 || d.ActionOpcode != 0 || d.HazardLimit != 0 || d.OperandVal != 0 {
				t.Errorf("%s: slot %d has non-routing fields: %+v", name, d.CID, d)
			}
		}
	}
}
