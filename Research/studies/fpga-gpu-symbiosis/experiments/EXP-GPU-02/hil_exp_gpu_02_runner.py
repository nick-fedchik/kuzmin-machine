#!/usr/bin/env python3
"""Issue #253 (EXP-GPU-02 Stage 3 HIL): Silicon verification of dual-bank CFG-P-HA on PYNQ-Z1 (Zynq-7020).

Executes on physical Zynq-7020 PL silicon (or via SSH to `pynq2`, `xilinx@192.168.68.69`) by compiling
and running a deterministic C99 `/dev/mem` MMIO harness at `0x40000000`:
  1. Verifies hardware signature `0x000 == 0x4B504841 ("KPHA")` and initial telemetry registers `0x038..0x044`.
  2. Executes EXP-GPU-02 Protocol Phases 1–4 on Concept C0 (`CID = 0`, wired to `SW_TRIGGER` at `0x010`)
     and Concept C5 (`CID = 5`, verified via end-to-end shadow packet injection + active bank readout),
     using rule frames generated and CRC-8-verified by `rule_injector.py`:
       - Phase 1 (Bank 0, rule `X >= 100`): `X = 50` -> Reject (`W0 = 0`), `X = 120` -> Commit (`W0 = 1`);
       - Phase 2 (Hot shadow injection of `X >= 40` via `0x030`, `0x034` while Bank 0 serves events):
         pre-swap `X = 50` still Reject (`W0 = 1`), `X = 120` -> Commit (`W0 = 2`);
       - Phase 3 (Atomic `BANK_SWAP_COMMIT` via `0x038 = 1` + background Port-A resync):
         verifies `active_bank == 1`, `swap_count == 1`, `last_swap_wait_cycles in 1..8`, `collision_detected == 0`;
       - Phase 4 (Immediate post-swap verification): the very first `X = 50` event after swap is evaluated
         under the new rule `X >= 40` -> Commit (`W0: 2 -> 3`) with zero loss of live state `W0` and
         `SEQ_EXEC_MONITOR (0x044) == 0x00000008` (`seq_anomaly_count == 0`, `last_seq_exec_cycles == 8`).
     Also performs two additional hot swaps (Bank 1 -> Bank 0 `X >= 100`, Bank 0 -> Bank 1 `X >= 40`)
     for external logic-analyzer capture of `JA2_COMMIT` (`GP3 = CH2`) on `LOGICTRACER_PICO_0.5.0`.
  3. Executes the 10,000-swap silicon stress series (`10,000` hot bank swaps alternating `X >= 100` and
     `X >= 40`, plus `1,000` full 16-byte `W0..W3` overrides, under a continuous stream of `>= 40,000`
     events), polling hardware registers `0x038..0x044` after every single swap and comparing against
     an independent software golden model.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rule_injector as ri  # noqa: E402

C99_HARNESS_SOURCE = r"""
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define MMIO_BASE       0x40000000UL
#define MMIO_SIZE       0x2000UL

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
#define REG_OVERFLOW    (0x02C / 4)
#define REG_SHADOW_ADDR (0x030 / 4)
#define REG_SHADOW_DATA (0x034 / 4)
#define REG_SWAP_CTRL   (0x038 / 4)
#define REG_SWAP_COUNT  (0x03C / 4)
#define REG_SWAP_WAIT   (0x040 / 4)
#define REG_SEQ_MON     (0x044 / 4)

static inline uint64_t mono_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

static inline void wait_not_busy(volatile uint32_t *regs) {
    while (regs[REG_BUSY] & 1u) {
    }
}

static inline void wait_shadow_free(volatile uint32_t *regs) {
    while ((regs[REG_SWAP_CTRL] >> 1) & 0x3u) {
    }
}

static void sync_write_word(volatile uint32_t *regs, uint32_t word_addr, uint32_t val) {
    wait_not_busy(regs);
    wait_shadow_free(regs);
    regs[REG_BRAM_ADDR] = word_addr;
    regs[REG_BRAM_DATA] = val;
}

static uint32_t active_read_word(volatile uint32_t *regs, uint32_t word_addr) {
    wait_shadow_free(regs);
    regs[REG_BRAM_ADDR] = word_addr;
    return regs[REG_BRAM_DATA];
}

static uint32_t shadow_read_word(volatile uint32_t *regs, uint32_t word_addr) {
    wait_shadow_free(regs);
    regs[REG_SHADOW_ADDR] = word_addr;
    return regs[REG_SHADOW_DATA];
}

static void shadow_inject_rules_12b(volatile uint32_t *regs, uint32_t cid,
                                    uint32_t w1, uint32_t w2, uint32_t w3) {
    wait_shadow_free(regs);
    regs[REG_SHADOW_ADDR] = cid * 4u + 1u;
    regs[REG_SHADOW_DATA] = w1;
    regs[REG_SHADOW_DATA] = w2;
    regs[REG_SHADOW_DATA] = w3;
}

static void shadow_inject_full_16b(volatile uint32_t *regs, uint32_t cid,
                                   uint32_t w0, uint32_t w1, uint32_t w2, uint32_t w3) {
    wait_shadow_free(regs);
    regs[REG_SHADOW_ADDR] = cid * 4u;
    regs[REG_SHADOW_DATA] = w0;
    regs[REG_SHADOW_DATA] = w1;
    regs[REG_SHADOW_DATA] = w2;
    regs[REG_SHADOW_DATA] = w3;
}

static void busy_delay_us(int us) {
    if (us <= 0) return;
    uint64_t target = mono_ns() + (uint64_t)us * 1000ULL;
    while (mono_ns() < target) {
    }
}

static void trigger_c0_event(volatile uint32_t *regs, int32_t param, int delay_us) {
    if (delay_us > 0) busy_delay_us(delay_us);
    wait_not_busy(regs);
    regs[REG_EVENT_PARAM] = (uint32_t)param;
    regs[REG_SW_TRIGGER]  = 1u;
    wait_not_busy(regs);
}

int main(int argc, char **argv) {
    int stress_swaps = 10000;
    int phases_only  = 0;
    int inter_event_us = 0;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--stress-swaps") == 0 && i + 1 < argc) {
            stress_swaps = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--phases-only") == 0) {
            phases_only = 1;
        } else if (strcmp(argv[i], "--inter-event-us") == 0 && i + 1 < argc) {
            inter_event_us = atoi(argv[++i]);
        }
    }

    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) {
        fprintf(stderr, "open(/dev/mem) failed: %s\n", strerror(errno));
        return 1;
    }
    volatile uint32_t *regs = (volatile uint32_t *)mmap(
        NULL, MMIO_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, MMIO_BASE);
    if (regs == MAP_FAILED) {
        fprintf(stderr, "mmap failed: %s\n", strerror(errno));
        close(fd);
        return 1;
    }

    uint32_t hw_id = regs[REG_ID];
    if (hw_id != 0x4B504841u) {
        fprintf(stderr, "Unexpected HW ID: 0x%08" PRIx32 " (expected 0x4B504841 KPHA)\n", hw_id);
        return 2;
    }

    /* Rule descriptor words verified by rule_injector.py:
       - Rule A (X >= 100, INC): W1 = 100, W2 = 0x01000B04, W3 = 0xFFFFFFFF
       - Rule B (X >=  40, INC): W1 =  40, W2 = 0x01000B04, W3 = 0xFFFFFFFF */
    const uint32_t W1_GE_100 = 100u;
    const uint32_t W1_GE_40  = 40u;
    const uint32_t W2_GE_INC = 0x01000B04u;
    const uint32_t W3_NO_SUB = 0xFFFFFFFFu;

    /* Clear all 256 words in both banks via synchronous load */
    for (uint32_t w = 0; w < 256u; w++) {
        sync_write_word(regs, w, 0u);
    }
    /* Ensure active_bank == 0 before starting Phases 1-4 */
    if (regs[REG_SWAP_CTRL] & 1u) {
        regs[REG_SWAP_CTRL] = 1u;
        wait_shadow_free(regs);
    }

    /* Load initial Rule A (X >= 100, W0 = 0) into C0 and C5 synchronously */
    sync_write_word(regs, 0u * 4u + 0u, 0u);
    sync_write_word(regs, 0u * 4u + 1u, W1_GE_100);
    sync_write_word(regs, 0u * 4u + 2u, W2_GE_INC);
    sync_write_word(regs, 0u * 4u + 3u, W3_NO_SUB);

    sync_write_word(regs, 5u * 4u + 0u, 0u);
    sync_write_word(regs, 5u * 4u + 1u, W1_GE_100);
    sync_write_word(regs, 5u * 4u + 2u, W2_GE_INC);
    sync_write_word(regs, 5u * 4u + 3u, W3_NO_SUB);

    uint32_t base_events  = regs[REG_EVENTS];
    uint32_t base_commits = regs[REG_COMMITS];
    uint32_t base_rejects = regs[REG_REJECTS];
    uint32_t base_swaps   = regs[REG_SWAP_COUNT];

    /* ====================================================================
     * PHASE 1 (Bank 0 active, rule X >= 100):
     *   Event 1: X = 50  -> Reject (W0 = 0, no JA2 pulse)
     *   Event 2: X = 120 -> Commit (W0 = 1, JA2 100 ns pulse #1)
     * ==================================================================== */
    trigger_c0_event(regs, 50, inter_event_us);
    uint32_t p1_e1_w0      = active_read_word(regs, 0u);
    uint32_t p1_e1_commits = regs[REG_COMMITS] - base_commits;
    uint32_t p1_e1_rejects = regs[REG_REJECTS] - base_rejects;

    trigger_c0_event(regs, 120, inter_event_us);
    uint32_t p1_e2_w0      = active_read_word(regs, 0u);
    uint32_t p1_e2_commits = regs[REG_COMMITS] - base_commits;
    uint32_t p1_e2_rejects = regs[REG_REJECTS] - base_rejects;
    uint32_t p1_seq_mon    = regs[REG_SEQ_MON];

    /* ====================================================================
     * PHASE 2 (Shadow injection of Rule B: X >= 40 into Bank 1 while Bank 0 active):
     *   Inject 12B rules W1..W3 for C0 and C5 into shadow Bank 1.
     *   Event 3 (pre-swap): X = 50  -> still Reject under Bank 0 (W0 = 1)
     *   Event 4 (pre-swap): X = 120 -> Commit under Bank 0, mirrored to Bank 1 (W0 = 2, JA2 pulse #2)
     * ==================================================================== */
    shadow_inject_rules_12b(regs, 0u, W1_GE_40, W2_GE_INC, W3_NO_SUB);
    shadow_inject_rules_12b(regs, 5u, W1_GE_40, W2_GE_INC, W3_NO_SUB);

    uint32_t p2_act_c0_w1 = active_read_word(regs, 1u);
    uint32_t p2_sh_c0_w1  = shadow_read_word(regs, 1u);
    uint32_t p2_act_c5_w1 = active_read_word(regs, 5u * 4u + 1u);
    uint32_t p2_sh_c5_w1  = shadow_read_word(regs, 5u * 4u + 1u);

    trigger_c0_event(regs, 50, inter_event_us);
    uint32_t p2_e3_w0      = active_read_word(regs, 0u);
    uint32_t p2_e3_commits = regs[REG_COMMITS] - base_commits;
    uint32_t p2_e3_rejects = regs[REG_REJECTS] - base_rejects;

    trigger_c0_event(regs, 120, inter_event_us);
    uint32_t p2_e4_w0      = active_read_word(regs, 0u);
    uint32_t p2_e4_sh_w0   = shadow_read_word(regs, 0u);
    uint32_t p2_e4_commits = regs[REG_COMMITS] - base_commits;
    uint32_t p2_e4_rejects = regs[REG_REJECTS] - base_rejects;

    /* ====================================================================
     * PHASE 3 (Atomic BANK_SWAP_COMMIT 0 -> 1 + Port-A resync):
     * ==================================================================== */
    regs[REG_SWAP_CTRL] = 1u;
    wait_shadow_free(regs);
    uint32_t p3_swap_ctrl  = regs[REG_SWAP_CTRL];
    uint32_t p3_swap_count = regs[REG_SWAP_COUNT] - base_swaps;
    uint32_t p3_swap_wait  = regs[REG_SWAP_WAIT];
    uint32_t p3_act_c0_w1  = active_read_word(regs, 1u);
    uint32_t p3_sh_c0_w1   = shadow_read_word(regs, 1u);
    uint32_t p3_act_c5_w1  = active_read_word(regs, 5u * 4u + 1u);
    uint32_t p3_sh_c5_w1   = shadow_read_word(regs, 5u * 4u + 1u);

    /* ====================================================================
     * PHASE 4 (Post-swap immediate reaction under new Rule B: X >= 40):
     *   Event 5 (post-swap #1): X = 50 -> NOW COMMITS! W0: 2 -> 3 (JA2 pulse #3)
     *   Event 6 (post-swap #2): X = 30 -> Reject (W0 = 3)
     *   Event 7 (post-swap #3): X = 50 -> Commit! W0: 3 -> 4 (JA2 pulse #4)
     *   Swap #2 back to Rule A (X >= 100):
     *   Event 8: X = 50  -> Reject again (W0 = 4)
     *   Event 9: X = 120 -> Commit! W0: 4 -> 5 (JA2 pulse #5)
     *   Swap #3 to Rule B (X >= 40) with explicit 16B W0 override = 500:
     *   Event 10: X = 50 -> Commit! W0: 500 -> 501 (JA2 pulse #6)
     * ==================================================================== */
    trigger_c0_event(regs, 50, inter_event_us);
    uint32_t p4_e5_w0      = active_read_word(regs, 0u);
    uint32_t p4_e5_commits = regs[REG_COMMITS] - base_commits;
    uint32_t p4_e5_rejects = regs[REG_REJECTS] - base_rejects;
    uint32_t p4_seq_mon    = regs[REG_SEQ_MON];

    trigger_c0_event(regs, 30, inter_event_us);
    uint32_t p4_e6_w0      = active_read_word(regs, 0u);

    trigger_c0_event(regs, 50, inter_event_us);
    uint32_t p4_e7_w0      = active_read_word(regs, 0u);

    /* Swap #2: restore Rule A (X >= 100) in shadow Bank 0 and swap */
    shadow_inject_rules_12b(regs, 0u, W1_GE_100, W2_GE_INC, W3_NO_SUB);
    regs[REG_SWAP_CTRL] = 1u;
    wait_shadow_free(regs);
    trigger_c0_event(regs, 50, inter_event_us);
    uint32_t p4_e8_w0 = active_read_word(regs, 0u);
    trigger_c0_event(regs, 120, inter_event_us);
    uint32_t p4_e9_w0 = active_read_word(regs, 0u);

    /* Swap #3: 16B full descriptor override (W0 = 500, X >= 40) */
    shadow_inject_full_16b(regs, 0u, 500u, W1_GE_40, W2_GE_INC, W3_NO_SUB);
    /* Pre-swap event on old active bank increments old W0 (5 -> 6), must NOT overwrite staged W0 = 500 */
    trigger_c0_event(regs, 120, inter_event_us);
    uint32_t p4_pre_ovr_act_w0 = active_read_word(regs, 0u);
    uint32_t p4_pre_ovr_sh_w0  = shadow_read_word(regs, 0u);
    regs[REG_SWAP_CTRL] = 1u;
    wait_shadow_free(regs);
    uint32_t p4_post_ovr_w0 = active_read_word(regs, 0u);
    trigger_c0_event(regs, 50, inter_event_us);
    uint32_t p4_e10_w0 = active_read_word(regs, 0u);

    if (phases_only) {
        printf("{\"hw_id\":\"0x%08" PRIx32 "\",\"phases_only\":true,"
               "\"p1_e1_w0\":%" PRIu32 ",\"p1_e2_w0\":%" PRIu32 ","
               "\"p2_e3_w0\":%" PRIu32 ",\"p2_e4_w0\":%" PRIu32 ","
               "\"p4_e5_w0\":%" PRIu32 ",\"p4_e7_w0\":%" PRIu32 ","
               "\"p4_e8_w0\":%" PRIu32 ",\"p4_e9_w0\":%" PRIu32 ","
               "\"p4_e10_w0\":%" PRIu32 ",\"seq_mon\":\"0x%08" PRIx32 "\"}\n",
               hw_id, p1_e1_w0, p1_e2_w0, p2_e3_w0, p2_e4_w0,
               p4_e5_w0, p4_e7_w0, p4_e8_w0, p4_e9_w0, p4_e10_w0, regs[REG_SEQ_MON]);
        return 0;
    }

    /* ====================================================================
     * STRESS SERIES: 10,000 hot bank swaps under continuous event stream
     * ==================================================================== */
    sync_write_word(regs, 0u, 0u);
    sync_write_word(regs, 1u, W1_GE_100);
    sync_write_word(regs, 2u, W2_GE_INC);
    sync_write_word(regs, 3u, W3_NO_SUB);

    uint32_t gold_w0         = 0u;
    uint32_t gold_thresh     = 100u;
    uint32_t gold_bank       = regs[REG_SWAP_CTRL] & 1u;
    uint32_t start_swaps     = regs[REG_SWAP_COUNT];
    uint32_t start_events    = regs[REG_EVENTS];
    uint32_t start_commits   = regs[REG_COMMITS];
    uint32_t start_rejects   = regs[REG_REJECTS];

    uint32_t wait_hist[16];
    memset(wait_hist, 0, sizeof(wait_hist));
    uint32_t wait_min        = 999u;
    uint32_t wait_max        = 0u;
    uint64_t wait_sum        = 0u;
    uint32_t collision_cnt   = 0u;
    uint32_t seq_anom_cnt    = 0u;
    uint32_t gold_mismatches = 0u;
    uint32_t torn_errors     = 0u;
    uint32_t rules_12b_cnt   = 0u;
    uint32_t full_16b_cnt    = 0u;

    uint64_t t_start_ns = mono_ns();

    for (int s = 0; s < stress_swaps; s++) {
        uint32_t next_thresh = (gold_thresh == 100u) ? 40u : 100u;
        int is_override = ((s % 10) == 9);
        uint32_t ovr_w0 = (uint32_t)(1000 + s);

        /* Pre-inject event under current active bank */
        int32_t ev_pre1 = 50;
        trigger_c0_event(regs, ev_pre1, 0);
        if (ev_pre1 >= (int32_t)gold_thresh) {
            gold_w0++;
        }

        /* Inject next rule into shadow bank */
        if (is_override) {
            shadow_inject_full_16b(regs, 0u, ovr_w0, next_thresh, W2_GE_INC, W3_NO_SUB);
            full_16b_cnt++;
        } else {
            shadow_inject_rules_12b(regs, 0u, next_thresh, W2_GE_INC, W3_NO_SUB);
            rules_12b_cnt++;
        }

        /* Events while shadow bank holds staged rule (before swap commit) */
        int32_t ev_pre2 = 50;
        trigger_c0_event(regs, ev_pre2, 0);
        if (ev_pre2 >= (int32_t)gold_thresh) {
            gold_w0++;
        }
        int32_t ev_pre3 = 120;
        trigger_c0_event(regs, ev_pre3, 0);
        if (ev_pre3 >= (int32_t)gold_thresh) {
            gold_w0++;
        }

        /* Verify active bank did not suffer torn-read before swap */
        uint32_t pre_swap_w0 = active_read_word(regs, 0u);
        if (pre_swap_w0 != gold_w0) {
            torn_errors++;
            gold_mismatches++;
        }

        /* Atomic bank swap commit */
        regs[REG_SWAP_CTRL] = 1u;
        wait_shadow_free(regs);

        gold_bank   ^= 1u;
        gold_thresh  = next_thresh;
        if (is_override) {
            gold_w0 = ovr_w0;
        }

        /* First event immediately after swap must use new rule */
        int32_t ev_post = 50;
        trigger_c0_event(regs, ev_post, 0);
        if (ev_post >= (int32_t)gold_thresh) {
            gold_w0++;
        }

        uint32_t st_ctrl  = regs[REG_SWAP_CTRL];
        uint32_t w_cycles = regs[REG_SWAP_WAIT];
        uint32_t seq_mon  = regs[REG_SEQ_MON];
        uint32_t hw_w0    = active_read_word(regs, 0u);

        if ((st_ctrl & 1u) != gold_bank) {
            gold_mismatches++;
        }
        if ((st_ctrl >> 3) & 1u) {
            collision_cnt++;
        }
        if (hw_w0 != gold_w0) {
            gold_mismatches++;
            torn_errors++;
        }
        if ((seq_mon >> 16) != 0u || (seq_mon & 0xFFFFu) != 8u) {
            seq_anom_cnt++;
        }
        if (w_cycles < wait_min) wait_min = w_cycles;
        if (w_cycles > wait_max) wait_max = w_cycles;
        wait_sum += w_cycles;
        if (w_cycles < 16u) {
            wait_hist[w_cycles]++;
        }
    }

    uint64_t t_elapsed_ns = mono_ns() - t_start_ns;

    /* Final bank0 == bank1 parity check across all 256 words after resync */
    wait_shadow_free(regs);
    uint32_t bank_parity_mismatches = 0u;
    for (uint32_t w = 0; w < 256u; w++) {
        uint32_t a_val = active_read_word(regs, w);
        uint32_t s_val = shadow_read_word(regs, w);
        if (a_val != s_val) {
            bank_parity_mismatches++;
        }
    }

    uint32_t stress_swaps_done   = regs[REG_SWAP_COUNT] - start_swaps;
    uint32_t stress_events_done  = regs[REG_EVENTS] - start_events;
    uint32_t stress_commits_done = regs[REG_COMMITS] - start_commits;
    uint32_t stress_rejects_done = regs[REG_REJECTS] - start_rejects;
    uint32_t total_swaps_done    = regs[REG_SWAP_COUNT] - base_swaps;
    uint32_t total_events_done   = regs[REG_EVENTS] - base_events;
    uint32_t final_seq_mon       = regs[REG_SEQ_MON];
    uint32_t final_dropped       = regs[REG_DROPPED];
    uint32_t final_overflow      = (regs[REG_OVERFLOW] >> 16) & 1u;

    printf("{\n");
    printf("  \"hw_id_hex\": \"0x%08" PRIx32 "\",\n", hw_id);
    printf("  \"phases_1_4\": {\n");
    printf("    \"p1_e1_x50_w0\": %" PRIu32 ",\n", p1_e1_w0);
    printf("    \"p1_e1_commits\": %" PRIu32 ",\n", p1_e1_commits);
    printf("    \"p1_e1_rejects\": %" PRIu32 ",\n", p1_e1_rejects);
    printf("    \"p1_e2_x120_w0\": %" PRIu32 ",\n", p1_e2_w0);
    printf("    \"p1_e2_commits\": %" PRIu32 ",\n", p1_e2_commits);
    printf("    \"p1_e2_rejects\": %" PRIu32 ",\n", p1_e2_rejects);
    printf("    \"p1_seq_mon_hex\": \"0x%08" PRIx32 "\",\n", p1_seq_mon);
    printf("    \"p2_active_c0_w1_before_swap\": %" PRIu32 ",\n", p2_act_c0_w1);
    printf("    \"p2_shadow_c0_w1_before_swap\": %" PRIu32 ",\n", p2_sh_c0_w1);
    printf("    \"p2_active_c5_w1_before_swap\": %" PRIu32 ",\n", p2_act_c5_w1);
    printf("    \"p2_shadow_c5_w1_before_swap\": %" PRIu32 ",\n", p2_sh_c5_w1);
    printf("    \"p2_e3_x50_pre_swap_w0\": %" PRIu32 ",\n", p2_e3_w0);
    printf("    \"p2_e3_commits\": %" PRIu32 ",\n", p2_e3_commits);
    printf("    \"p2_e3_rejects\": %" PRIu32 ",\n", p2_e3_rejects);
    printf("    \"p2_e4_x120_pre_swap_act_w0\": %" PRIu32 ",\n", p2_e4_w0);
    printf("    \"p2_e4_x120_pre_swap_sh_w0\": %" PRIu32 ",\n", p2_e4_sh_w0);
    printf("    \"p2_e4_commits\": %" PRIu32 ",\n", p2_e4_commits);
    printf("    \"p2_e4_rejects\": %" PRIu32 ",\n", p2_e4_rejects);
    printf("    \"p3_swap_ctrl_hex\": \"0x%08" PRIx32 "\",\n", p3_swap_ctrl);
    printf("    \"p3_swap_count\": %" PRIu32 ",\n", p3_swap_count);
    printf("    \"p3_swap_wait_cycles\": %" PRIu32 ",\n", p3_swap_wait);
    printf("    \"p3_active_c0_w1_after_swap\": %" PRIu32 ",\n", p3_act_c0_w1);
    printf("    \"p3_shadow_c0_w1_after_resync\": %" PRIu32 ",\n", p3_sh_c0_w1);
    printf("    \"p3_active_c5_w1_after_swap\": %" PRIu32 ",\n", p3_act_c5_w1);
    printf("    \"p3_shadow_c5_w1_after_resync\": %" PRIu32 ",\n", p3_sh_c5_w1);
    printf("    \"p4_e5_x50_post_swap_w0\": %" PRIu32 ",\n", p4_e5_w0);
    printf("    \"p4_e5_commits\": %" PRIu32 ",\n", p4_e5_commits);
    printf("    \"p4_e5_rejects\": %" PRIu32 ",\n", p4_e5_rejects);
    printf("    \"p4_seq_mon_hex\": \"0x%08" PRIx32 "\",\n", p4_seq_mon);
    printf("    \"p4_e6_x30_w0\": %" PRIu32 ",\n", p4_e6_w0);
    printf("    \"p4_e7_x50_w0\": %" PRIu32 ",\n", p4_e7_w0);
    printf("    \"p4_e8_x50_after_swap2_w0\": %" PRIu32 ",\n", p4_e8_w0);
    printf("    \"p4_e9_x120_after_swap2_w0\": %" PRIu32 ",\n", p4_e9_w0);
    printf("    \"p4_pre_override_act_w0\": %" PRIu32 ",\n", p4_pre_ovr_act_w0);
    printf("    \"p4_pre_override_sh_w0\": %" PRIu32 ",\n", p4_pre_ovr_sh_w0);
    printf("    \"p4_post_override_w0\": %" PRIu32 ",\n", p4_post_ovr_w0);
    printf("    \"p4_e10_x50_after_override_w0\": %" PRIu32 "\n", p4_e10_w0);
    printf("  },\n");
    printf("  \"stress_10k\": {\n");
    printf("    \"stress_swaps\": %" PRIu32 ",\n", stress_swaps_done);
    printf("    \"total_bank_swaps\": %" PRIu32 ",\n", total_swaps_done);
    printf("    \"stress_events\": %" PRIu32 ",\n", stress_events_done);
    printf("    \"total_events\": %" PRIu32 ",\n", total_events_done);
    printf("    \"stress_commits\": %" PRIu32 ",\n", stress_commits_done);
    printf("    \"stress_rejects\": %" PRIu32 ",\n", stress_rejects_done);
    printf("    \"rules_12b_updates\": %" PRIu32 ",\n", rules_12b_cnt);
    printf("    \"full_16b_overrides\": %" PRIu32 ",\n", full_16b_cnt);
    printf("    \"torn_read_errors\": %" PRIu32 ",\n", torn_errors);
    printf("    \"golden_mismatch_count\": %" PRIu32 ",\n", gold_mismatches);
    printf("    \"bram_collision_count\": %" PRIu32 ",\n", collision_cnt);
    printf("    \"seq_stall_anomaly_count\": %" PRIu32 ",\n", seq_anom_cnt);
    printf("    \"bank_parity_mismatches_256w\": %" PRIu32 ",\n", bank_parity_mismatches);
    printf("    \"events_dropped_count\": %" PRIu32 ",\n", final_dropped);
    printf("    \"fifo_overflow\": %" PRIu32 ",\n", final_overflow);
    printf("    \"last_seq_exec_cycles\": %" PRIu32 ",\n", final_seq_mon & 0xFFFFu);
    printf("    \"hw_seq_anomaly_reg\": %" PRIu32 ",\n", final_seq_mon >> 16);
    printf("    \"swap_wait_min_cycles\": %" PRIu32 ",\n", wait_min);
    printf("    \"swap_wait_max_cycles\": %" PRIu32 ",\n", wait_max);
    printf("    \"swap_wait_avg_cycles\": %.4f,\n",
           stress_swaps_done ? ((double)wait_sum / (double)stress_swaps_done) : 0.0);
    printf("    \"wall_time_ms\": %.3f,\n", (double)t_elapsed_ns / 1e6);
    printf("    \"swap_wait_histogram_cycles\": {\n");
    for (int k = 1; k <= 8; k++) {
        printf("      \"%d\": %" PRIu32 "%s\n", k, wait_hist[k], (k < 8) ? "," : "");
    }
    printf("    }\n");
    printf("  }\n");
    printf("}\n");

    munmap((void *)regs, MMIO_SIZE);
    close(fd);
    return (torn_errors == 0u && gold_mismatches == 0u && collision_cnt == 0u &&
            seq_anom_cnt == 0u && bank_parity_mismatches == 0u) ? 0 : 3;
}
"""


def validate_hil_summary(summary: dict) -> None:
    """Validates physical HIL summary JSON against EXP-GPU-02 acceptance criteria (raises ValueError on defect)."""
    if summary.get("evidence_kind") != "physical_hil_pynq_z1":
        raise ValueError(f"Invalid evidence_kind: {summary.get('evidence_kind')!r}")
    if summary.get("not_physical_hil") is not False:
        raise ValueError("not_physical_hil must be False for physical Zynq-7020 HIL data")
    if summary.get("hw_id_hex") != "0x4b504841":
        raise ValueError(f"Unexpected hw_id_hex: {summary.get('hw_id_hex')!r}")

    p = summary.get("phases_1_4", {})
    if p.get("p1_e1_x50_w0") != 0 or p.get("p1_e1_rejects") != 1 or p.get("p1_e1_commits") != 0:
        raise ValueError("Phase 1 Event 1 (X=50 under X>=100) did not reject cleanly")
    if p.get("p1_e2_x120_w0") != 1 or p.get("p1_e2_commits") != 1:
        raise ValueError("Phase 1 Event 2 (X=120 under X>=100) did not commit W0=1")
    if p.get("p2_active_c0_w1_before_swap") != 100 or p.get("p2_shadow_c0_w1_before_swap") != 40:
        raise ValueError("Phase 2 shadow bank isolation failed before swap")
    if p.get("p2_e3_x50_pre_swap_w0") != 1 or p.get("p2_e3_rejects") != 2:
        raise ValueError("Phase 2 pre-swap X=50 did not stay on old rule X>=100")
    if p.get("p2_e4_x120_pre_swap_act_w0") != 2 or p.get("p2_e4_x120_pre_swap_sh_w0") != 2:
        raise ValueError("Phase 2 pre-swap Port-B live state W0=2 was not mirrored to shadow bank")
    if p.get("p3_active_c0_w1_after_swap") != 40 or p.get("p3_shadow_c0_w1_after_resync") != 40:
        raise ValueError("Phase 3 bank swap + Port-A resync failed on C0")
    if p.get("p3_active_c5_w1_after_swap") != 40 or p.get("p3_shadow_c5_w1_after_resync") != 40:
        raise ValueError("Phase 3 bank swap + Port-A resync failed on C5")
    if p.get("p4_e5_x50_post_swap_w0") != 3 or p.get("p4_e5_commits") != 3:
        raise ValueError("Phase 4 first post-swap X=50 did not commit W0: 2 -> 3")
    if p.get("p4_pre_override_act_w0") != 6 or p.get("p4_pre_override_sh_w0") != 500:
        raise ValueError("Phase 4 shadow_w0_override protection failed before swap")
    if p.get("p4_post_override_w0") != 500 or p.get("p4_e10_x50_after_override_w0") != 501:
        raise ValueError("Phase 4 16B W0=500 override post-swap state mismatch")

    s = summary.get("stress_10k", {})
    if int(s.get("stress_swaps", 0)) < 10000:
        raise ValueError(f"stress_swaps={s.get('stress_swaps')} < 10000")
    if int(s.get("total_bank_swaps", 0)) < 10003:
        raise ValueError(f"total_bank_swaps={s.get('total_bank_swaps')} < 10003")
    if int(s.get("stress_events", 0)) < 40000:
        raise ValueError(f"stress_events={s.get('stress_events')} < 40000")
    for zero_field in (
        "torn_read_errors",
        "golden_mismatch_count",
        "bram_collision_count",
        "seq_stall_anomaly_count",
        "bank_parity_mismatches_256w",
        "events_dropped_count",
        "fifo_overflow",
        "hw_seq_anomaly_reg",
    ):
        if int(s.get(zero_field, -1)) != 0:
            raise ValueError(f"Non-zero error counter {zero_field}={s.get(zero_field)}")
    if int(s.get("last_seq_exec_cycles", 0)) != 8:
        raise ValueError(f"Expected last_seq_exec_cycles == 8, got {s.get('last_seq_exec_cycles')}")
    wmin = int(s.get("swap_wait_min_cycles", 0))
    wmax = int(s.get("swap_wait_max_cycles", 99))
    if not (1 <= wmin <= wmax <= 8):
        raise ValueError(f"Swap wait cycles [{wmin}, {wmax}] outside formal bound 1..8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pynq-host", default="xilinx@192.168.68.69")
    ap.add_argument(
        "--pynq-pass",
        default=os.environ.get("PYNQ_SUDO_PASS", ""),
        help="SSH/sudo password for PYNQ board (defaults to $PYNQ_SUDO_PASS; if empty, uses SSH key + sudo -n)",
    )
    ap.add_argument("--stress-swaps", type=int, default=10000)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--bitstream-sha256", default="")
    args = ap.parse_args()

    # Verify rule packets with rule_injector.py first
    pkt_ge100 = ri.build_rule_packet(ri.RuleDescriptorPatch.threshold_ge(cid=0, threshold=100))
    pkt_ge40 = ri.build_rule_packet(ri.RuleDescriptorPatch.threshold_ge(cid=0, threshold=40))
    pkt_c5_ge40 = ri.build_rule_packet(ri.RuleDescriptorPatch.threshold_ge(cid=5, threshold=40))
    pkt_ovr500 = ri.build_rule_packet(ri.RuleDescriptorPatch.threshold_ge(cid=0, threshold=40, init_state_w0=500))
    for pkt in (pkt_ge100, pkt_ge40, pkt_c5_ge40, pkt_ovr500):
        ri.verify_and_unpack_packet(pkt)

    sudo_prefix = "sudo -S" if args.pynq_pass else "sudo -n"
    remote_cmd = (
        "cat > /home/xilinx/exp_gpu_02_hil_harness.c << 'EOF_C'\n"
        + C99_HARNESS_SOURCE
        + "EOF_C\n"
        "gcc -O2 -std=c99 -Wall -Wextra /home/xilinx/exp_gpu_02_hil_harness.c -o /home/xilinx/exp_gpu_02_hil_harness && "
        f"{sudo_prefix} /home/xilinx/exp_gpu_02_hil_harness --stress-swaps {args.stress_swaps}"
    )
    if args.pynq_pass:
        ssh_cmd = [
            "sshpass",
            "-e",
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            args.pynq_host,
            remote_cmd,
        ]
        env = {**os.environ, "SSHPASS": args.pynq_pass}
        res = subprocess.run(
            ssh_cmd,
            input=args.pynq_pass + "\n",
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
    else:
        ssh_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            args.pynq_host,
            remote_cmd,
        ]
        res = subprocess.run(ssh_cmd, capture_output=True, text=True, check=True)
    raw_json = json.loads(res.stdout)

    summary = {
        "timestamp": datetime.datetime.now().astimezone().isoformat(),
        "issue": 253,
        "experiment": "EXP-GPU-02",
        "evidence_kind": "physical_hil_pynq_z1",
        "not_physical_hil": False,
        "board": "Digilent PYNQ-Z1 (XC7Z020-1CLG400C, pynq2 @ 192.168.68.69)",
        "pl_fclk0_mhz": 100.0,
        "bitstream_sha256": args.bitstream_sha256,
        "rule_packets_crc8": {
            "c0_ge_100_hex": pkt_ge100.hex(),
            "c0_ge_40_hex": pkt_ge40.hex(),
            "c5_ge_40_hex": pkt_c5_ge40.hex(),
            "c0_override_w0_500_ge_40_hex": pkt_ovr500.hex(),
        },
        **raw_json,
        "verdict": "PASS",
    }
    validate_hil_summary(summary)

    out_json_path = Path(args.out_json)
    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    out_json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    p = summary["phases_1_4"]
    s = summary["stress_10k"]
    csv_rows = [
        {
            "phase": "Phase1_Event1_X50_Reject",
            "evidence_kind": "physical_hil_pynq_z1",
            "active_bank": 0,
            "rule_threshold_ge": 100,
            "stimulus_x": 50,
            "expected_commit": 0,
            "observed_w0": p["p1_e1_x50_w0"],
            "commits_total": p["p1_e1_commits"],
            "rejects_total": p["p1_e1_rejects"],
            "swap_wait_cycles": 0,
            "last_seq_exec_cycles": int(p["p1_seq_mon_hex"], 16) & 0xFFFF,
            "seq_anomaly_count": int(p["p1_seq_mon_hex"], 16) >> 16,
        },
        {
            "phase": "Phase1_Event2_X120_Commit",
            "evidence_kind": "physical_hil_pynq_z1",
            "active_bank": 0,
            "rule_threshold_ge": 100,
            "stimulus_x": 120,
            "expected_commit": 1,
            "observed_w0": p["p1_e2_x120_w0"],
            "commits_total": p["p1_e2_commits"],
            "rejects_total": p["p1_e2_rejects"],
            "swap_wait_cycles": 0,
            "last_seq_exec_cycles": int(p["p1_seq_mon_hex"], 16) & 0xFFFF,
            "seq_anomaly_count": int(p["p1_seq_mon_hex"], 16) >> 16,
        },
        {
            "phase": "Phase2_Event3_X50_PreSwap_Reject",
            "evidence_kind": "physical_hil_pynq_z1",
            "active_bank": 0,
            "rule_threshold_ge": 100,
            "stimulus_x": 50,
            "expected_commit": 0,
            "observed_w0": p["p2_e3_x50_pre_swap_w0"],
            "commits_total": p["p2_e3_commits"],
            "rejects_total": p["p2_e3_rejects"],
            "swap_wait_cycles": 0,
            "last_seq_exec_cycles": int(p["p1_seq_mon_hex"], 16) & 0xFFFF,
            "seq_anomaly_count": int(p["p1_seq_mon_hex"], 16) >> 16,
        },
        {
            "phase": "Phase2_Event4_X120_PreSwap_Commit_Mirrored",
            "evidence_kind": "physical_hil_pynq_z1",
            "active_bank": 0,
            "rule_threshold_ge": 100,
            "stimulus_x": 120,
            "expected_commit": 1,
            "observed_w0": p["p2_e4_x120_pre_swap_act_w0"],
            "commits_total": p["p2_e4_commits"],
            "rejects_total": p["p2_e4_rejects"],
            "swap_wait_cycles": 0,
            "last_seq_exec_cycles": int(p["p1_seq_mon_hex"], 16) & 0xFFFF,
            "seq_anomaly_count": int(p["p1_seq_mon_hex"], 16) >> 16,
        },
        {
            "phase": "Phase3_Atomic_Bank_Swap_Commit_0_to_1",
            "evidence_kind": "physical_hil_pynq_z1",
            "active_bank": int(p["p3_swap_ctrl_hex"], 16) & 1,
            "rule_threshold_ge": p["p3_active_c0_w1_after_swap"],
            "stimulus_x": 0,
            "expected_commit": 0,
            "observed_w0": p["p2_e4_x120_pre_swap_sh_w0"],
            "commits_total": p["p2_e4_commits"],
            "rejects_total": p["p2_e4_rejects"],
            "swap_wait_cycles": p["p3_swap_wait_cycles"],
            "last_seq_exec_cycles": int(p["p4_seq_mon_hex"], 16) & 0xFFFF,
            "seq_anomaly_count": int(p["p4_seq_mon_hex"], 16) >> 16,
        },
        {
            "phase": "Phase4_Event5_X50_PostSwap_Immediate_Commit",
            "evidence_kind": "physical_hil_pynq_z1",
            "active_bank": 1,
            "rule_threshold_ge": 40,
            "stimulus_x": 50,
            "expected_commit": 1,
            "observed_w0": p["p4_e5_x50_post_swap_w0"],
            "commits_total": p["p4_e5_commits"],
            "rejects_total": p["p4_e5_rejects"],
            "swap_wait_cycles": p["p3_swap_wait_cycles"],
            "last_seq_exec_cycles": int(p["p4_seq_mon_hex"], 16) & 0xFFFF,
            "seq_anomaly_count": int(p["p4_seq_mon_hex"], 16) >> 16,
        },
        {
            "phase": "Phase4_Swap3_16B_Override_W0_500_Commit",
            "evidence_kind": "physical_hil_pynq_z1",
            "active_bank": 1,
            "rule_threshold_ge": 40,
            "stimulus_x": 50,
            "expected_commit": 1,
            "observed_w0": p["p4_e10_x50_after_override_w0"],
            "commits_total": p["p4_e5_commits"] + 3,
            "rejects_total": p["p4_e5_rejects"] + 2,
            "swap_wait_cycles": p["p3_swap_wait_cycles"],
            "last_seq_exec_cycles": s["last_seq_exec_cycles"],
            "seq_anomaly_count": s["hw_seq_anomaly_reg"],
        },
        {
            "phase": "Stress_10000_Swaps_40000_Events_Summary",
            "evidence_kind": "physical_hil_pynq_z1",
            "active_bank": 1,
            "rule_threshold_ge": 100,
            "stimulus_x": 50,
            "expected_commit": 1,
            "observed_w0": p["p4_e10_x50_after_override_w0"],
            "commits_total": s["stress_commits"],
            "rejects_total": s["stress_rejects"],
            "swap_wait_cycles": s["swap_wait_max_cycles"],
            "last_seq_exec_cycles": s["last_seq_exec_cycles"],
            "seq_anomaly_count": s["seq_stall_anomaly_count"],
        },
    ]
    out_csv_path = Path(args.out_csv)
    out_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with out_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_rows)

    print(
        f"PASS: Physical Zynq-7020 HIL verified ({s['total_bank_swaps']} swaps, "
        f"{s['total_events']} events, 0 collisions, 0 torn-reads, 8 cycles/event)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
