package vmk

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"
)

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

// ShellQuoteSingle quotes a string in single quotes for POSIX shells, escaping any internal `'` as `'\”`.
func ShellQuoteSingle(s string) string {
	return "'" + strings.ReplaceAll(s, "'", "'\\''") + "'"
}

// BuildPYNQRemoteExec constructs the remote compile-and-run command for the PYNQ-Z1 MMIO probe
// without ever interpolating `sudoPass` into the shell command string.
// When `sudoPass` is empty, `sudo -n` (non-interactive passwordless sudo) is used;
// when `sudoPass` is non-empty, `sudo -S -p ”` reads the password from `cmd.Stdin`.
func BuildPYNQRemoteExec(remoteDir string, hwParams []int32, sudoPass string) (remoteExec string, sudoStdin string) {
	var paramStrs []string
	for _, p := range hwParams {
		paramStrs = append(paramStrs, strconv.FormatInt(int64(p), 10))
	}
	sudoPrefix := "sudo -n"
	if sudoPass != "" {
		sudoPrefix = "sudo -S -p ''"
		sudoStdin = sudoPass + "\n"
	}
	argsSuffix := strings.Join(paramStrs, " ")
	if argsSuffix != "" {
		argsSuffix = " " + argsSuffix
	}
	remoteExec = fmt.Sprintf(
		"cd %s && gcc -std=c99 -O2 -Wall -Wextra -Werror km_pynq_debug_probe.c -o km_pynq_debug_probe && %s ./km_pynq_debug_probe program_image.bin%s",
		ShellQuoteSingle(remoteDir),
		sudoPrefix,
		argsSuffix,
	)
	return remoteExec, sudoStdin
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
	quotedRemoteDir := ShellQuoteSingle(remoteDir)
	sshOpts := []string{"-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no"}

	// Create remote directory and upload probe + binary over stdin pipe (zero local temp files!)
	mkdirCmd := exec.Command("ssh", append(append([]string{}, sshOpts...), sshHost, fmt.Sprintf("mkdir -p %s", quotedRemoteDir))...)
	if out, err := mkdirCmd.CombinedOutput(); err != nil {
		return nil, &TargetIOError{Target: c.Target, Host: sshHost, Detail: strings.TrimSpace(string(out))}
	}
	defer func() {
		cleanCmd := exec.Command("ssh", append(append([]string{}, sshOpts...), sshHost, fmt.Sprintf("rm -rf %s", quotedRemoteDir))...)
		_ = cleanCmd.Run()
	}()

	writeCCmd := exec.Command("ssh", append(append([]string{}, sshOpts...), sshHost, fmt.Sprintf("cat > %s/km_pynq_debug_probe.c", quotedRemoteDir))...)
	writeCCmd.Stdin = strings.NewReader(pynqDebugProbeCSource)
	if out, err := writeCCmd.CombinedOutput(); err != nil {
		return nil, &TargetIOError{Target: c.Target, Host: sshHost, Detail: strings.TrimSpace(string(out))}
	}

	writeBinCmd := exec.Command("ssh", append(append([]string{}, sshOpts...), sshHost, fmt.Sprintf("cat > %s/program_image.bin", quotedRemoteDir))...)
	writeBinCmd.Stdin = strings.NewReader(string(programBRAM))
	if out, err := writeBinCmd.CombinedOutput(); err != nil {
		return nil, &TargetIOError{Target: c.Target, Host: sshHost, Detail: strings.TrimSpace(string(out))}
	}

	remoteExec, sudoStdin := BuildPYNQRemoteExec(remoteDir, hwParams, os.Getenv("PYNQ_SUDO_PASS"))
	runCmd := exec.Command("ssh", append(append([]string{}, sshOpts...), sshHost, remoteExec)...)
	if sudoStdin != "" {
		runCmd.Stdin = strings.NewReader(sudoStdin)
	}
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
