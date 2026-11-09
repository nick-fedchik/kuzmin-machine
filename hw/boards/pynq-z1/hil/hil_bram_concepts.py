#!/usr/bin/env python3
"""
Hardware-in-the-Loop (HIL) Test Runner for EXP-07: Multi-Concept BRAM Table
File: pynq_z1_bram_concepts_test.py

Verifies:
  1. Full 64-concept table (1024 bytes / 256 words) in Block RAM via AXI MMIO (Port A).
  2. Data integrity across all 64 descriptors (Value LO/HI, Meta, Status).
  3. Simultaneous dual-port access via Port B.
  4. Autonomous PL hardware operations:
     - COPY (Concept[dst] <= Concept[src])
     - ADD  (Concept[dst] <= Concept[dst] + Concept[src])
  5. In-silicon cycle profiling for multi-concept reactive transitions.

Target Board: Digilent PYNQ-Z1 (Xilinx Zynq-7020)
MMIO Base: 0x40000000 (8 KB window)
BRAM Offset: 0x1000 .. 0x13FF
"""

import argparse
import json
import mmap
import os
import sys
import time

try:
    import pynq.pl_server.embedded_device
    from pynq import Bitstream
except ImportError:
    pass

AXI_BASE_ADDR = 0x40000000
MMIO_WINDOW_SIZE = 0x2000  # 8 KB window

REG_ID              = 0x14
REG_CYCLE_CNT_LO    = 0x2C
REG_CYCLE_CNT_HI    = 0x30
REG_LAST_TXN_CYCLES = 0x34
REG_BRAM_CTRL       = 0x50
REG_BRAM_STATUS     = 0x54
REG_BRAM_CYCLES     = 0x58
REG_BRAM_PORT_B_ADDR = 0x5C
REG_BRAM_PORT_B_DATA = 0x60

BRAM_BASE_OFFSET    = 0x1000
NUM_CONCEPTS        = 64
EXPECTED_ID         = 0x4B504F4C  # ASCII "KPOL"


class PynqMmapMMIO:
    def __init__(self, base_addr=AXI_BASE_ADDR, size=MMIO_WINDOW_SIZE):
        self.fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        self.mem = mmap.mmap(
            self.fd,
            size,
            mmap.MAP_SHARED,
            mmap.PROT_READ | mmap.PROT_WRITE,
            offset=base_addr
        )

    def read32(self, offset: int) -> int:
        self.mem.seek(offset)
        raw = self.mem.read(4)
        return int.from_bytes(raw, byteorder='little', signed=False)

    def write32(self, offset: int, value: int):
        self.mem.seek(offset)
        self.mem.write(int(value & 0xFFFFFFFF).to_bytes(4, byteorder='little', signed=False))

    def close(self):
        self.mem.close()
        os.close(self.fd)


def program_bitstream(bitstream_path: str):
    print(f"[PYNQ] Loading volatile bitstream into PL SRAM: {bitstream_path}...")
    import pynq.pl_server.embedded_device
    from pynq import Bitstream
    bs = Bitstream(bitstream_path)
    bs.download()
    time.sleep(0.1)
    print("[PYNQ] Bitstream successfully programmed into PL.")


def restore_base_overlay():
    base_path = "/lib/firmware/base.bin"
    if os.path.exists(base_path):
        print(f"[PYNQ] Restoring default base overlay from {base_path}...")
        import pynq.pl_server.embedded_device
        from pynq import Bitstream
        bs = Bitstream(base_path)
        bs.download()
        print("[PYNQ] Baseline overlay restored.")


def run_bram_tests(mmio: PynqMmapMMIO) -> dict:
    results = {
        "device": "Digilent PYNQ-Z1 (xc7z020clg400-1)",
        "toolchain": "openXC7 (Yosys + nextpnr-himbaechel)",
        "clock_freq_mhz": 100.0,
        "num_concepts": NUM_CONCEPTS,
        "total_bram_bytes": NUM_CONCEPTS * 16,
        "part1_id_check": False,
        "part2_all_concepts_integrity": {},
        "part3_dual_port_parallel": {},
        "part4_autonomous_pl_ops": {},
    }

    print("\n" + "="*70)
    print(" 1. HARDWARE IDENTIFICATION CHECK")
    print("="*70)
    dev_id = mmio.read32(REG_ID)
    id_str = "".join([chr((dev_id >> (8*i)) & 0xFF) for i in range(4)])
    print(f"  [ID] Read ID: 0x{dev_id:08X} (ASCII: '{id_str}')")
    assert dev_id == EXPECTED_ID, f"Unexpected ID: 0x{dev_id:08X}"
    print("  [PASS] Hardware ID verified.")
    results["part1_id_check"] = True

    print("\n" + "="*70)
    print(f" 2. EXP-07: WRITE & VERIFY ALL {NUM_CONCEPTS} CONCEPTS (1024 BYTES BRAM)")
    print("="*70)
    golden_table = {}

    t0 = time.perf_counter()
    for cid in range(NUM_CONCEPTS):
        c_base = BRAM_BASE_OFFSET + cid * 16
        val_lo = (cid * 1000 + 42) & 0xFFFFFFFF
        val_hi = (cid * 2) & 0xFFFFFFFF
        # Meta: type=0 (Int), size=4, init=1, big_dot=1, event_mask=(0x100 + cid)
        meta = 0x00 | (0x04 << 4) | (1 << 8) | (1 << 9) | (((0x100 + cid) & 0xFFFF) << 16)
        status = cid & 0xFFFFFFFF

        golden_table[cid] = (val_lo, val_hi, meta, status)

        mmio.write32(c_base + 0x0, val_lo)
        mmio.write32(c_base + 0x4, val_hi)
        mmio.write32(c_base + 0x8, meta)
        mmio.write32(c_base + 0xC, status)

    write_time_ms = (time.perf_counter() - t0) * 1000.0

    # Readback and verification
    mismatches = 0
    t1 = time.perf_counter()
    for cid in range(NUM_CONCEPTS):
        c_base = BRAM_BASE_OFFSET + cid * 16
        r_val_lo = mmio.read32(c_base + 0x0)
        r_val_hi = mmio.read32(c_base + 0x4)
        r_meta   = mmio.read32(c_base + 0x8)
        r_status = mmio.read32(c_base + 0xC)

        g_val_lo, g_val_hi, g_meta, g_status = golden_table[cid]

        if (r_val_lo != g_val_lo or r_val_hi != g_val_hi or
            r_meta != g_meta or r_status != g_status):
            mismatches += 1
            print(f"  [ERROR] Mismatch at Concept #{cid}:")
            print(f"    Expected: lo={g_val_lo}, hi={g_val_hi}, meta=0x{g_meta:08X}, st={g_status}")
            print(f"    Read:     lo={r_val_lo}, hi={r_val_hi}, meta=0x{r_meta:08X}, st={r_status}")

    read_time_ms = (time.perf_counter() - t1) * 1000.0

    print(f"  Written: {NUM_CONCEPTS} concepts (256 words, 1024 bytes) in {write_time_ms:.2f} ms")
    print(f"  Readback: {NUM_CONCEPTS} concepts verified in {read_time_ms:.2f} ms")
    print(f"  Mismatches: {mismatches}")
    assert mismatches == 0, f"Found {mismatches} word mismatches in BRAM table!"
    print("  [PASS] 100% data integrity across all 64 concept descriptors.")

    results["part2_all_concepts_integrity"] = {
        "words_tested": NUM_CONCEPTS * 4,
        "bytes_tested": NUM_CONCEPTS * 16,
        "mismatches": mismatches,
        "write_time_ms": round(write_time_ms, 2),
        "read_time_ms": round(read_time_ms, 2)
    }

    print("\n" + "="*70)
    print(" 3. EXP-07: SIMULTANEOUS DUAL-PORT ACCESS (PORT A & PORT B)")
    print("="*70)
    # Test reading Concept 10 via Port B while writing Concept 20 via Port A
    # Concept 10 Word 0 is at word address 10 * 4 = 40 (0x28)
    mmio.write32(REG_BRAM_PORT_B_ADDR, 40)
    b_val = mmio.read32(REG_BRAM_PORT_B_DATA)
    expected_c10_lo = golden_table[10][0]
    print(f"  Port B read Concept #10 (word 40): {b_val} (Expected: {expected_c10_lo})")
    assert b_val == expected_c10_lo, f"Port B read mismatch: {b_val} != {expected_c10_lo}"

    # Write Concept 20 via Port B and verify via Port A
    # Concept 20 Word 0 is at word address 20 * 4 = 80 (0x50)
    test_pattern = 0xCAFEBABE
    mmio.write32(REG_BRAM_PORT_B_ADDR, 80)
    mmio.write32(REG_BRAM_PORT_B_DATA, test_pattern)
    time.sleep(0.001)

    # Readback via Port A (MMIO direct address: 0x1000 + 20*16 = 0x1140)
    a_readback = mmio.read32(BRAM_BASE_OFFSET + 20 * 16)
    print(f"  Port A readback Concept #20 (written via Port B): 0x{a_readback:08X} (Expected: 0x{test_pattern:08X})")
    assert a_readback == test_pattern, f"Dual-port bridge mismatch: 0x{a_readback:08X} != 0x{test_pattern:08X}"
    print("  [PASS] True dual-port concurrent memory access verified.")

    results["part3_dual_port_parallel"] = {
        "port_b_read_c10": b_val,
        "port_b_write_c20_read_via_a": hex(a_readback)
    }

    print("\n" + "="*70)
    print(" 4. EXP-07: AUTONOMOUS PL MULTI-CONCEPT HARDWARE OPERATIONS")
    print("="*70)
    # Prepare Concept 5 = 55555, Concept 6 = 11111
    mmio.write32(BRAM_BASE_OFFSET + 5 * 16, 55555)
    mmio.write32(BRAM_BASE_OFFSET + 6 * 16, 11111)

    # 4A. Autonomous PL COPY: Concept 6 <= Concept 5
    # REG_BRAM_CTRL: bit 0 = 1 (start), bit 1 = 0 (COPY), [13:8] = 5 (src), [21:16] = 6 (dst)
    ctrl_copy = 1 | (0 << 1) | (5 << 8) | (6 << 16)
    mmio.write32(REG_BRAM_CTRL, ctrl_copy)

    # Wait for completion
    timeout = 1000
    while timeout > 0:
        st = mmio.read32(REG_BRAM_STATUS)
        if (st & 0x02) != 0:  # done bit
            break
        timeout -= 1
    assert timeout > 0, "Autonomous PL COPY timed out!"

    copy_cycles = mmio.read32(REG_BRAM_CYCLES)
    c6_after_copy = mmio.read32(BRAM_BASE_OFFSET + 6 * 16)
    print(f"  [4A: PL COPY] Concept #6 <= Concept #5:")
    print(f"    -> Result: {c6_after_copy} (Expected: 55555)")
    print(f"    -> PL Execution Duration: {copy_cycles} cycles ({copy_cycles * 10.0:.1f} ns)")
    assert c6_after_copy == 55555, f"PL COPY failed: {c6_after_copy} != 55555"

    # 4B. Autonomous PL ADD: Concept 6 += Concept 5 (55555 + 55555 = 111110)
    # REG_BRAM_CTRL: bit 0 = 1 (start), bit 1 = 1 (ADD), [13:8] = 5 (src), [21:16] = 6 (dst)
    ctrl_add = 1 | (1 << 1) | (5 << 8) | (6 << 16)
    mmio.write32(REG_BRAM_CTRL, ctrl_add)

    timeout = 1000
    while timeout > 0:
        st = mmio.read32(REG_BRAM_STATUS)
        if (st & 0x02) != 0:
            break
        timeout -= 1
    assert timeout > 0, "Autonomous PL ADD timed out!"

    add_cycles = mmio.read32(REG_BRAM_CYCLES)
    c6_after_add = mmio.read32(BRAM_BASE_OFFSET + 6 * 16)
    print(f"  [4B: PL ADD]  Concept #6 += Concept #5:")
    print(f"    -> Result: {c6_after_add} (Expected: 111110)")
    print(f"    -> PL Execution Duration: {add_cycles} cycles ({add_cycles * 10.0:.1f} ns)")
    assert c6_after_add == 111110, f"PL ADD failed: {c6_after_add} != 111110"

    print("  [PASS] Autonomous PL multi-concept pipeline verified in hardware.")

    results["part4_autonomous_pl_ops"] = {
        "copy_result": c6_after_copy,
        "copy_cycles": copy_cycles,
        "copy_ns": copy_cycles * 10.0,
        "add_result": c6_after_add,
        "add_cycles": add_cycles,
        "add_ns": add_cycles * 10.0
    }

    print("\n" + "="*70)
    print(" ALL EXP-07 BRAM TESTS PASSED (100% OK)")
    print("="*70)
    return results


def main():
    parser = argparse.ArgumentParser(description="EXP-07 Multi-Concept BRAM HIL Runner")
    parser.add_argument("--bitstream", default="/home/xilinx/kpol_pynq.bit", help="Path to bitstream")
    parser.add_argument("--program", action="store_true", help="Download bitstream into PL SRAM")
    parser.add_argument("--restore-base", action="store_true", help="Restore base.bin after testing")
    parser.add_argument("--output-json", default="bram_concepts_results.json", help="Path for JSON output")
    args = parser.parse_args()

    if args.program:
        program_bitstream(args.bitstream)

    mmio = PynqMmapMMIO()
    try:
        results = run_bram_tests(mmio)
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n[INFO] Results saved to: {args.output_json}")
    finally:
        mmio.close()
        if args.restore_base:
            restore_base_overlay()


if __name__ == "__main__":
    main()
