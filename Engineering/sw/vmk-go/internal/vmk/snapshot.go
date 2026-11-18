package vmk

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
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

const pynqDebugProbeCSource = `#define _POSIX_C_SOURCE 200809L
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define BASE_ADDR       0x40000000UL
#define MAP_SIZE        0x2000UL
#define REG_ID          (0x000 / 4)
#define REG_BRAM_ADDR   (0x004 / 4)
#define REG_BRAM_DATA   (0x008 / 4)
#define REG_EVENT_PARAM (0x00C / 4)
#define REG_SW_TRIGGER  (0x010 / 4)
#define REG_BUSY        (0x014 / 4)
#define REG_EVENTS      (0x018 / 4)
#define REG_COMMITS     (0x01C / 4)
#define REG_REJECTS     (0x020 / 4)
#define REG_LAST_STATE  (0x024 / 4)
#define REG_DROPPED     (0x028 / 4)

static void wait_idle(volatile uint32_t *regs) {
    int guard = 0;
    while ((regs[REG_BUSY] & 1u) != 0u) {
        if (++guard > 1000000) {
            fprintf(stderr, "Timeout waiting for REG_BUSY == 0\n");
            exit(2);
        }
    }
}

static void dump_snapshot_json(const char *label, volatile uint32_t *regs) {
    uint32_t words[256];
    wait_idle(regs);
    for (uint32_t i = 0; i < 256u; ++i) {
        regs[REG_BRAM_ADDR] = i;
        words[i] = regs[REG_BRAM_DATA];
    }
    uint32_t hw_id   = regs[REG_ID];
    uint32_t ev_cnt  = regs[REG_EVENTS];
    uint32_t cm_cnt  = regs[REG_COMMITS];
    uint32_t rj_cnt  = regs[REG_REJECTS];
    int32_t  last_st = (int32_t)regs[REG_LAST_STATE];
    uint32_t dropped = (hw_id == 0x4B504841u) ? regs[REG_DROPPED] : 0u;

    printf("    \"%s\": {\n", label);
    printf("      \"hw_id\": %u,\n", (unsigned)hw_id);
    printf("      \"hw_id_hex\": \"0x%08X\",\n", (unsigned)hw_id);
    printf("      \"events\": %u,\n", (unsigned)ev_cnt);
    printf("      \"commits\": %u,\n", (unsigned)cm_cnt);
    printf("      \"rejects\": %u,\n", (unsigned)rj_cnt);
    printf("      \"last_state\": %d,\n", (int)last_st);
    printf("      \"dropped\": %u,\n", (unsigned)dropped);
    printf("      \"bram_words_hex\": [");
    for (uint32_t i = 0; i < 256u; ++i) {
        printf("\"%08X\"%s", (unsigned)words[i], (i + 1u < 256u) ? "," : "");
    }
    printf("]\n    }");
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <program.bin> [param1 param2 ...]\n", argv[0]);
        return 2;
    }
    FILE *fp = fopen(argv[1], "rb");
    if (!fp) {
        perror("fopen bin");
        return 2;
    }
    uint32_t prog_words[256];
    if (fread(prog_words, sizeof(uint32_t), 256, fp) != 256) {
        fprintf(stderr, "Failed to read 256 words from %s\n", argv[1]);
        fclose(fp);
        return 2;
    }
    fclose(fp);

    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) {
        perror("open /dev/mem");
        return 2;
    }
    volatile uint32_t *regs = (volatile uint32_t *)mmap(
        NULL, MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, BASE_ADDR
    );
    if (regs == MAP_FAILED) {
        perror("mmap");
        close(fd);
        return 2;
    }

    uint32_t chip_id = regs[REG_ID];
    if ((chip_id != 0x4B504D43u) && (chip_id != 0x4B504841u)) {
        fprintf(stderr, "Unexpected FPGA ID: 0x%08X\n", (unsigned)chip_id);
        munmap((void *)regs, MAP_SIZE);
        close(fd);
        return 2;
    }

    printf("{\n  \"snapshots\": {\n");
    dump_snapshot_json("pre_load", regs);
    printf(",\n");

    wait_idle(regs);
    for (uint32_t i = 0; i < 256u; ++i) {
        regs[REG_BRAM_ADDR] = i;
        regs[REG_BRAM_DATA] = prog_words[i];
    }
    wait_idle(regs);
    dump_snapshot_json("post_load", regs);
    printf(",\n");

    for (int a = 2; a < argc; ++a) {
        int32_t p = (int32_t)strtol(argv[a], NULL, 0);
        wait_idle(regs);
        regs[REG_EVENT_PARAM] = (uint32_t)p;
        regs[REG_SW_TRIGGER]  = 1u;
        wait_idle(regs);
    }
    dump_snapshot_json("post_run", regs);
    printf("\n  }\n}\n");

    munmap((void *)regs, MAP_SIZE);
    close(fd);
    return 0;
}
`

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

// ResolveSSHTarget maps `pynq1` or `pynq2` to its SSH host, or returns the custom target string.
func (c *MachineConnection) ResolveSSHTarget() string {
	switch c.Target {
	case "sim":
		return ""
	case "pynq1":
		if v := os.Getenv("KM_PYNQ1_HOST"); v != "" {
			return v
		}
		return "xilinx@192.168.68.81"
	case "pynq2":
		if v := os.Getenv("KM_PYNQ2_HOST"); v != "" {
			return v
		}
		return "xilinx@192.168.68.69"
	default:
		return c.Target
	}
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

type rawSnapJSON struct {
	HWID         uint32   `json:"hw_id"`
	HWIDHex      string   `json:"hw_id_hex"`
	Events       uint32   `json:"events"`
	Commits      uint32   `json:"commits"`
	Rejects      uint32   `json:"rejects"`
	LastState    int32    `json:"last_state"`
	Dropped      uint32   `json:"dropped"`
	BRAMWordsHex []string `json:"bram_words_hex"`
}

type rawProbePayload struct {
	Snapshots map[string]rawSnapJSON `json:"snapshots"`
}

func decodeRawSnap(raw rawSnapJSON, phase, target string, conceptNames []string) (MachineSnapshot, error) {
	if len(raw.BRAMWordsHex) != 256 {
		return MachineSnapshot{}, fmt.Errorf("expected 256 BRAM hex words, got %d", len(raw.BRAMWordsHex))
	}
	bramBytes := make([]byte, 1024)
	for i, hexW := range raw.BRAMWordsHex {
		u, err := strconv.ParseUint(strings.TrimSpace(hexW), 16, 32)
		if err != nil {
			return MachineSnapshot{}, err
		}
		ramOff := i * 4
		bramBytes[ramOff] = byte(u & 0xFF)
		bramBytes[ramOff+1] = byte((u >> 8) & 0xFF)
		bramBytes[ramOff+2] = byte((u >> 16) & 0xFF)
		bramBytes[ramOff+3] = byte((u >> 24) & 0xFF)
	}
	return MakeSnapshotFromBytes(
		bramBytes,
		phase,
		target,
		raw.HWID,
		raw.Events,
		raw.Commits,
		raw.Rejects,
		raw.LastState,
		raw.Dropped,
		conceptNames,
	)
}

// ExecutePYNQSession connects to a live PYNQ-Z1 board under flock /tmp/km-bench.lock,
// captures PRE-LOAD, programs 1024B BRAM, verifies POST-LOAD readback, executes hwParams, and captures POST-RUN.
func (c *MachineConnection) ExecutePYNQSession(programBRAM []byte, hwParams []int32, conceptNames, preConceptNames []string) (map[string]any, error) {
	sshHost := c.ResolveSSHTarget()
	if sshHost == "" {
		return nil, &TargetIOError{Target: c.Target, Host: "sim", Detail: "ExecutePYNQSession requires a hardware target"}
	}

	lockPath := filepath.Join(string(filepath.Separator)+"tmp", "km-bench.lock")
	lockFile, err := os.OpenFile(lockPath, os.O_CREATE|os.O_RDWR, 0666)
	if err != nil {
		return nil, &TargetIOError{Target: c.Target, Host: sshHost, Detail: fmt.Sprintf("open lock %s: %v", lockPath, err)}
	}
	defer lockFile.Close()

	deadline := time.Now().Add(120 * time.Second)
	for {
		err = syscall.Flock(int(lockFile.Fd()), syscall.LOCK_EX|syscall.LOCK_NB)
		if err == nil {
			break
		}
		if time.Now().After(deadline) {
			return nil, &TargetIOError{Target: c.Target, Host: sshHost, Detail: fmt.Sprintf("timeout acquiring %s", lockPath)}
		}
		time.Sleep(100 * time.Millisecond)
	}
	defer syscall.Flock(int(lockFile.Fd()), syscall.LOCK_UN)

	remoteDir := "/home/xilinx/km_vmk_274_work"
	sshOpts := []string{"-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no"}

	// Create remote directory and upload probe + binary over stdin pipe (zero local temp files!)
	mkdirCmd := exec.Command("ssh", append(append([]string{}, sshOpts...), sshHost, fmt.Sprintf("mkdir -p %s", remoteDir))...)
	if out, err := mkdirCmd.CombinedOutput(); err != nil {
		return nil, &TargetIOError{Target: c.Target, Host: sshHost, Detail: strings.TrimSpace(string(out))}
	}
	defer func() {
		cleanCmd := exec.Command("ssh", append(append([]string{}, sshOpts...), sshHost, fmt.Sprintf("rm -rf %s", remoteDir))...)
		_ = cleanCmd.Run()
	}()

	writeCCmd := exec.Command("ssh", append(append([]string{}, sshOpts...), sshHost, fmt.Sprintf("cat > %s/km_pynq_debug_probe.c", remoteDir))...)
	writeCCmd.Stdin = strings.NewReader(pynqDebugProbeCSource)
	if out, err := writeCCmd.CombinedOutput(); err != nil {
		return nil, &TargetIOError{Target: c.Target, Host: sshHost, Detail: strings.TrimSpace(string(out))}
	}

	writeBinCmd := exec.Command("ssh", append(append([]string{}, sshOpts...), sshHost, fmt.Sprintf("cat > %s/program_image.bin", remoteDir))...)
	writeBinCmd.Stdin = strings.NewReader(string(programBRAM))
	if out, err := writeBinCmd.CombinedOutput(); err != nil {
		return nil, &TargetIOError{Target: c.Target, Host: sshHost, Detail: strings.TrimSpace(string(out))}
	}

	var paramStrs []string
	for _, p := range hwParams {
		paramStrs = append(paramStrs, strconv.FormatInt(int64(p), 10))
	}
	sudoPass := os.Getenv("PYNQ_SUDO_PASS")
	if sudoPass == "" {
		sudoPass = "xilinx"
	}
	remoteExec := fmt.Sprintf(
		"cd %s && gcc -std=c99 -O2 -Wall -Wextra -Werror km_pynq_debug_probe.c -o km_pynq_debug_probe && echo %s | sudo -S -p '' ./km_pynq_debug_probe program_image.bin %s",
		remoteDir,
		sudoPass,
		strings.Join(paramStrs, " "),
	)
	runCmd := exec.Command("ssh", append(append([]string{}, sshOpts...), sshHost, remoteExec)...)
	outBytes, err := runCmd.CombinedOutput()
	if err != nil {
		return nil, &TargetIOError{Target: c.Target, Host: sshHost, Detail: strings.TrimSpace(string(outBytes))}
	}

	var payload rawProbePayload
	if err := json.Unmarshal(outBytes, &payload); err != nil {
		return nil, &TargetIOError{Target: c.Target, Host: sshHost, Detail: fmt.Sprintf("invalid JSON from probe: %v", err)}
	}

	preSnap, err := decodeRawSnap(payload.Snapshots["pre_load"], "PRE-LOAD", c.Target, preConceptNames)
	if err != nil {
		return nil, err
	}
	postSnap, err := decodeRawSnap(payload.Snapshots["post_load"], "POST-LOAD", c.Target, conceptNames)
	if err != nil {
		return nil, err
	}
	postRunSnap, err := decodeRawSnap(payload.Snapshots["post_run"], "POST-RUN", c.Target, conceptNames)
	if err != nil {
		return nil, err
	}

	if string(postSnap.BRAMBytes) != string(programBRAM) {
		return nil, &TargetIOError{Target: c.Target, Host: sshHost, Detail: "POST-LOAD BRAM readback mismatch against programBRAM"}
	}
	c.ReadbackVerified = true
	c.PreLoadSnapshot = &preSnap
	c.PostLoadSnapshot = &postSnap
	c.PostRunSnapshot = &postRunSnap
	c.LoadDiffs = ComputePrePostLoadDiff(preSnap, postSnap)

	changedSlots := 0
	for _, d := range c.LoadDiffs {
		if d.Changed {
			changedSlots++
		}
	}

	return map[string]any{
		"target":                c.Target,
		"ssh_host":              sshHost,
		"readback_verified":     true,
		"pre_load":              preSnap,
		"post_load":             postSnap,
		"post_run":              postRunSnap,
		"changed_slots_on_load": changedSlots,
		"events_delta":          int64(postRunSnap.HWEvents) - int64(postSnap.HWEvents),
		"commits_delta":         int64(postRunSnap.HWCommits) - int64(postSnap.HWCommits),
		"rejects_delta":         int64(postRunSnap.HWRejects) - int64(postSnap.HWRejects),
	}, nil
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
