package kpol

import (
	"encoding/binary"
	"fmt"
)

// CME predicate opcodes (kpol-formal-specification.md §7.1, KPOL-P0-1).
const (
	PredNOP     = 0x00
	PredEQ      = 0x01
	PredNEQ     = 0x02
	PredGT      = 0x03
	PredLT      = 0x04
	PredRANGE   = 0x05
	PredBITMASK = 0x06
)

// CME action opcodes.
const (
	ActAssign = 0x00
	ActInc    = 0x01
	ActDec    = 0x02
	ActAdd    = 0x03
	ActSub    = 0x04
)

// CME guard flag bits (W2 bits 8..15).
const (
	GuardAssumptionEn     = 0x01
	GuardInvariantEn      = 0x02
	GuardHazardEn         = 0x04
	GuardInvertAssumption = 0x08
	GuardSubscriberEn     = 0x10
)

// Image geometry.
const (
	ImageSize = 1024
	SlotSize  = 16
	SlotCount = 64
)

// Descriptor is one 16-byte CME-RAW-1 slot (W0..W3, little-endian uint32 words).
type Descriptor struct {
	CID           int
	Name          string
	CurrentState  uint32 // W0
	OperandVal    uint32 // W1
	PredOpcode    uint8  // W2 bits 0..7
	GuardFlags    uint8  // W2 bits 8..15
	HazardLimit   uint8  // W2 bits 16..23
	ActionOpcode  uint8  // W2 bits 24..31
	SubscriberCID uint32 // W3
}

// Pack encodes the descriptor as 16 bytes.
func (d Descriptor) Pack() [SlotSize]byte {
	var out [SlotSize]byte
	w2 := uint32(d.PredOpcode) | uint32(d.GuardFlags)<<8 | uint32(d.HazardLimit)<<16 | uint32(d.ActionOpcode)<<24
	binary.LittleEndian.PutUint32(out[0:], d.CurrentState)
	binary.LittleEndian.PutUint32(out[4:], d.OperandVal)
	binary.LittleEndian.PutUint32(out[8:], w2)
	binary.LittleEndian.PutUint32(out[12:], d.SubscriberCID)
	return out
}

// PackImage places descriptors at slot CID into a zeroed 1024-byte image.
func PackImage(ds []Descriptor) []byte {
	img := make([]byte, ImageSize)
	for _, d := range ds {
		if d.CID < 0 || d.CID >= SlotCount {
			continue
		}
		p := d.Pack()
		copy(img[d.CID*SlotSize:], p[:])
	}
	return img
}

// Disassemble unpacks a 1024-byte image into 64 descriptors named "Concept_<cid>".
func Disassemble(img []byte) ([]Descriptor, error) {
	if len(img) != ImageSize {
		return nil, &Error{Code: "KPOL-IMAGE", Msg: fmt.Sprintf("Expected exactly 1024 bytes for CME microcode, got %d", len(img))}
	}
	ds := make([]Descriptor, SlotCount)
	for cid := 0; cid < SlotCount; cid++ {
		o := cid * SlotSize
		w0 := binary.LittleEndian.Uint32(img[o:])
		w1 := binary.LittleEndian.Uint32(img[o+4:])
		w2 := binary.LittleEndian.Uint32(img[o+8:])
		w3 := binary.LittleEndian.Uint32(img[o+12:])
		ds[cid] = Descriptor{
			CID: cid, Name: fmt.Sprintf("Concept_%d", cid),
			CurrentState: w0, OperandVal: w1,
			PredOpcode: uint8(w2), GuardFlags: uint8(w2 >> 8), HazardLimit: uint8(w2 >> 16), ActionOpcode: uint8(w2 >> 24),
			SubscriberCID: w3,
		}
	}
	return ds, nil
}
