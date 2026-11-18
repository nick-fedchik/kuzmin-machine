package vmk

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sort"
	"strconv"
	"strings"
)

// ConceptTopologySummary classifies the 64 BRAM slots into active, entry, internal, leaf, and free.
type ConceptTopologySummary struct {
	TotalSlots              int   `json:"total_slots"`
	ActiveConcepts          int   `json:"active_concepts"`
	FreeSlots               int   `json:"free_slots"`
	EntryConcepts           []int `json:"entry_concepts"`
	InternalCascadeConcepts []int `json:"internal_cascade_concepts"`
	LeafConcepts            []int `json:"leaf_concepts"`
	IsolatedConcepts        []int `json:"isolated_concepts"`
}

// AnalyzeConceptTopology computes the topology breakdown for 64 BRAM descriptors.
func AnalyzeConceptTopology(descs [64]ConceptDescriptor) ConceptTopologySummary {
	activeSet := make(map[int]bool)
	outEdges := make(map[int]int)
	inDeg := make(map[int]int)

	for cid := 0; cid < 64; cid++ {
		d := descs[cid]
		if d.IsConfigured() {
			activeSet[cid] = true
		}
		if d.HasSubscriptionEdge() {
			dst := int(d.SubscriberCID)
			if dst >= 0 && dst < 64 && dst != cid {
				activeSet[cid] = true
				activeSet[dst] = true
				outEdges[cid] = dst
				inDeg[dst]++
			}
		}
	}

	var activeSorted []int
	for cid := range activeSet {
		activeSorted = append(activeSorted, cid)
	}
	sort.Ints(activeSorted)

	entry := []int{}
	internal := []int{}
	leaf := []int{}
	isolated := []int{}

	for _, cid := range activeSorted {
		hasIn := inDeg[cid] > 0
		_, hasOut := outEdges[cid]
		if !hasIn && hasOut {
			entry = append(entry, cid)
		} else if hasIn && hasOut {
			internal = append(internal, cid)
		} else if hasIn && !hasOut {
			leaf = append(leaf, cid)
		} else {
			isolated = append(isolated, cid)
			entry = append(entry, cid)
		}
	}

	return ConceptTopologySummary{
		TotalSlots:              64,
		ActiveConcepts:          len(activeSorted),
		FreeSlots:               64 - len(activeSorted),
		EntryConcepts:           entry,
		InternalCascadeConcepts: internal,
		LeafConcepts:            leaf,
		IsolatedConcepts:        isolated,
	}
}

// MachineSnapshot captures the full machine state at PRE-LOAD, POST-LOAD, or POST-RUN.
type MachineSnapshot struct {
	Phase       string                 `json:"phase"`
	Target      string                 `json:"target"`
	HWIDHex     string                 `json:"hw_id_hex"`
	HWIDASCII   string                 `json:"hw_id_ascii"`
	BRAMBytes   []byte                 `json:"-"`
	BRAMSHA256  string                 `json:"bram_sha256"`
	Descriptors [64]ConceptDescriptor  `json:"-"`
	Topology    ConceptTopologySummary `json:"topology"`
	HWEvents    uint32                 `json:"hw_events"`
	HWCommits   uint32                 `json:"hw_commits"`
	HWRejects   uint32                 `json:"hw_rejects"`
	HWLastState int32                  `json:"hw_last_state"`
	HWDropped   uint32                 `json:"hw_dropped"`
}

func hwIDToASCII(hwID uint32) string {
	var b [4]byte
	b[0] = byte((hwID >> 24) & 0xFF)
	b[1] = byte((hwID >> 16) & 0xFF)
	b[2] = byte((hwID >> 8) & 0xFF)
	b[3] = byte(hwID & 0xFF)
	for i := 0; i < 4; i++ {
		if b[i] < 32 || b[i] > 126 {
			b[i] = '?'
		}
	}
	return string(b[:])
}

// MakeSnapshotFromBytes constructs a MachineSnapshot from a 1024-byte BRAM image and hardware counters.
func MakeSnapshotFromBytes(
	bramBytes []byte,
	phase, target string,
	hwID, hwEvents, hwCommits, hwRejects uint32,
	hwLastState int32,
	hwDropped uint32,
	conceptNames []string,
) (MachineSnapshot, error) {
	descs, err := DisassembleBRAM(bramBytes, conceptNames)
	if err != nil {
		return MachineSnapshot{}, err
	}
	topo := AnalyzeConceptTopology(descs)
	sum := sha256.Sum256(bramBytes)
	rawCopy := make([]byte, len(bramBytes))
	copy(rawCopy, bramBytes)
	return MachineSnapshot{
		Phase:       phase,
		Target:      target,
		HWIDHex:     fmt.Sprintf("0x%08X", hwID),
		HWIDASCII:   hwIDToASCII(hwID),
		BRAMBytes:   rawCopy,
		BRAMSHA256:  hex.EncodeToString(sum[:]),
		Descriptors: descs,
		Topology:    topo,
		HWEvents:    hwEvents,
		HWCommits:   hwCommits,
		HWRejects:   hwRejects,
		HWLastState: hwLastState,
		HWDropped:   hwDropped,
	}, nil
}

// SlotLoadDiff compares one BRAM slot between PRE-LOAD and POST-LOAD snapshots.
type SlotLoadDiff struct {
	CID        int    `json:"cid"`
	Name       string `json:"name"`
	Changed    bool   `json:"changed"`
	PreActive  bool   `json:"pre_active"`
	PostActive bool   `json:"post_active"`
	PreW0      int32  `json:"pre_w0"`
	PostW0     int32  `json:"post_w0"`
	PreW1      int32  `json:"pre_w1"`
	PostW1     int32  `json:"post_w1"`
	PreW2Hex   string `json:"pre_w2_hex"`
	PostW2Hex  string `json:"post_w2_hex"`
	PreRule    string `json:"pre_rule"`
	PostRule   string `json:"post_rule"`
	PreSub     string `json:"pre_sub"`
	PostSub    string `json:"post_sub"`
}

// ComputePrePostLoadDiff compares all 64 BRAM slots between PRE-LOAD and POST-LOAD snapshots.
func ComputePrePostLoadDiff(pre, post MachineSnapshot) []SlotLoadDiff {
	var diffs []SlotLoadDiff
	for cid := 0; cid < 64; cid++ {
		d0 := pre.Descriptors[cid]
		d1 := post.Descriptors[cid]
		preAct := d0.IsConfigured()
		postAct := d1.IsConfigured()
		w0Changed := d0.CurrentState != d1.CurrentState
		w123Changed := (d0.OperandVal != d1.OperandVal) || (d0.W2Word() != d1.W2Word()) || (d0.SubscriberCID != d1.SubscriberCID)
		slotChanged := w0Changed || w123Changed
		if !(preAct || postAct || slotChanged) {
			continue
		}
		w2_0, dec0 := DecodeW2Summary(d0)
		w2_1, dec1 := DecodeW2Summary(d1)
		name := d1.Name
		if !postAct {
			name = d0.Name
		}
		preRule := "EMPTY"
		if preAct {
			preRule = dec0
		}
		postRule := "EMPTY"
		if postAct {
			postRule = dec1
		}
		preSub := "None"
		if preAct {
			preSub = DecodeW3Subscriber(d0, pre.Descriptors)
		}
		postSub := "None"
		if postAct {
			postSub = DecodeW3Subscriber(d1, post.Descriptors)
		}
		diffs = append(diffs, SlotLoadDiff{
			CID:        cid,
			Name:       name,
			Changed:    slotChanged,
			PreActive:  preAct,
			PostActive: postAct,
			PreW0:      int32(d0.CurrentState),
			PostW0:     int32(d1.CurrentState),
			PreW1:      int32(d0.OperandVal),
			PostW1:     int32(d1.OperandVal),
			PreW2Hex:   fmt.Sprintf("0x%08X", w2_0),
			PostW2Hex:  fmt.Sprintf("0x%08X", w2_1),
			PreRule:    preRule,
			PostRule:   postRule,
			PreSub:     preSub,
			PostSub:    postSub,
		})
	}
	return diffs
}

// MachineConnection manages target lifecycle: PRE-LOAD -> POST-LOAD -> RUNNING/POST-RUN.
type MachineConnection struct {
	Target           string           `json:"target"`
	SimHWID          uint32           `json:"-"`
	SimBRAM          []byte           `json:"-"`
	SimEvents        uint32           `json:"-"`
	SimCommits       uint32           `json:"-"`
	SimRejects       uint32           `json:"-"`
	SimLastState     int32            `json:"-"`
	PreLoadSnapshot  *MachineSnapshot `json:"pre_load_snapshot,omitempty"`
	PostLoadSnapshot *MachineSnapshot `json:"post_load_snapshot,omitempty"`
	PostRunSnapshot  *MachineSnapshot `json:"post_run_snapshot,omitempty"`
	LoadDiffs        []SlotLoadDiff   `json:"load_diffs,omitempty"`
	ReadbackVerified bool             `json:"readback_verified"`
}

// NewMachineConnection creates a MachineConnection for `sim`, `pynq1`, `pynq2`, or an SSH host.
func NewMachineConnection(target string, initialBRAM []byte) (*MachineConnection, error) {
	t := strings.TrimSpace(target)
	if t == "" {
		t = "sim"
	}
	bram := make([]byte, 1024)
	if len(initialBRAM) > 0 {
		if len(initialBRAM) != 1024 {
			return nil, fmt.Errorf("VMK-BRAM-SIZE: initialBRAM must be 1024 bytes, got %d", len(initialBRAM))
		}
		copy(bram, initialBRAM)
	}
	return &MachineConnection{
		Target:  t,
		SimHWID: HWIDCfgP,
		SimBRAM: bram,
	}, nil
}

// CapturePreLoadSim records the PRE-LOAD snapshot on the simulated target before programming.
func (c *MachineConnection) CapturePreLoadSim(preConceptNames []string) (*MachineSnapshot, error) {
	snap, err := MakeSnapshotFromBytes(
		c.SimBRAM,
		"PRE-LOAD",
		c.Target,
		c.SimHWID,
		c.SimEvents,
		c.SimCommits,
		c.SimRejects,
		c.SimLastState,
		0,
		preConceptNames,
	)
	if err != nil {
		return nil, err
	}
	c.PreLoadSnapshot = &snap
	return &snap, nil
}

// LoadProgramIntoSim captures PRE-LOAD (if not yet captured), writes programBRAM, verifies 256/256 words readback, and computes diffs.
func (c *MachineConnection) LoadProgramIntoSim(programBRAM []byte, conceptNames, preConceptNames []string) error {
	if len(programBRAM) != 1024 {
		return fmt.Errorf("VMK-BRAM-SIZE: expected 1024-byte program image, got %d", len(programBRAM))
	}
	if c.PreLoadSnapshot == nil {
		if _, err := c.CapturePreLoadSim(preConceptNames); err != nil {
			return err
		}
	}
	copy(c.SimBRAM, programBRAM)
	for i := 0; i < 1024; i++ {
		if c.SimBRAM[i] != programBRAM[i] {
			return fmt.Errorf("VMK-READBACK: BRAM readback verification failed at byte %d", i)
		}
	}
	c.ReadbackVerified = true
	post, err := MakeSnapshotFromBytes(
		c.SimBRAM,
		"POST-LOAD",
		c.Target,
		c.SimHWID,
		c.SimEvents,
		c.SimCommits,
		c.SimRejects,
		c.SimLastState,
		0,
		conceptNames,
	)
	if err != nil {
		return err
	}
	c.PostLoadSnapshot = &post
	c.LoadDiffs = ComputePrePostLoadDiff(*c.PreLoadSnapshot, post)
	return nil
}

// FormatPrePostLoadSummary renders the PRE-LOAD vs POST-LOAD concept count & per-slot diff table.
func (c *MachineConnection) FormatPrePostLoadSummary() string {
	if c.PreLoadSnapshot == nil || c.PostLoadSnapshot == nil {
		return "No PRE-LOAD / POST-LOAD snapshots captured yet."
	}
	pre := c.PreLoadSnapshot
	post := c.PostLoadSnapshot
	t0 := pre.Topology
	t1 := post.Topology
	changedCount := 0
	for _, d := range c.LoadDiffs {
		if d.Changed {
			changedCount++
		}
	}

	lines := []string{
		fmt.Sprintf("=== MACHINE CONNECTION & PROGRAMMING SNAPSHOT (%s | HW_ID=%s '%s') ===", strings.ToUpper(post.Target), post.HWIDHex, post.HWIDASCII),
		fmt.Sprintf("  Capacity          : %d concept slots (1024 B CME-RAW-1 BRAM)", t1.TotalSlots),
		fmt.Sprintf("  PRE-LOAD State    : %d / %d active concepts (free=%d, SHA-256=%s...) | HW Counters: events=%d, commits=%d, rejects=%d, dropped=%d",
			t0.ActiveConcepts, t0.TotalSlots, t0.FreeSlots, pre.BRAMSHA256[:16], pre.HWEvents, pre.HWCommits, pre.HWRejects, pre.HWDropped),
		fmt.Sprintf("  POST-LOAD State   : %d / %d active concepts (entry=%v, internal=%v, leaf=%v, free=%d, SHA-256=%s...)",
			t1.ActiveConcepts, t1.TotalSlots, t1.EntryConcepts, t1.InternalCascadeConcepts, t1.LeafConcepts, t1.FreeSlots, post.BRAMSHA256[:16]),
		fmt.Sprintf("  Readback & Diff   : 256/256 words OK (verified=%v); %d slot(s) modified during programming", c.ReadbackVerified, changedCount),
	}

	headers := []string{
		"CID",
		"Name",
		"Changed",
		"Pre-Load W0",
		"Post-Load W0",
		"Pre-Load Rule -> Post-Load Rule",
		"Pre-Sub -> Post-Sub (W3)",
	}
	var rows [][]string
	for _, d := range c.LoadDiffs {
		chg := "NO"
		if d.Changed {
			chg = "YES"
		}
		preW0 := "_ (empty)"
		if d.PreActive {
			preW0 = strconv.FormatInt(int64(d.PreW0), 10)
		}
		postW0 := "_ (empty)"
		if d.PostActive {
			postW0 = strconv.FormatInt(int64(d.PostW0), 10)
		}
		rows = append(rows, []string{
			fmt.Sprintf("C%02d", d.CID),
			d.Name,
			chg,
			preW0,
			postW0,
			fmt.Sprintf("%s => %s", d.PreRule, d.PostRule),
			fmt.Sprintf("%s => %s", d.PreSub, d.PostSub),
		})
	}
	lines = append(lines, RenderASCIITable(headers, rows))
	return strings.Join(lines, "\n")
}
