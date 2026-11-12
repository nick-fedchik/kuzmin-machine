#!/usr/bin/env python3
"""Run the two-image experiment after explicitly programming its bitstream.

Run on the board through a host-side `flock -w 600 /tmp/km-bench.lock ssh ...`.
Use sudo and the board's /usr/local/share/pynq-venv/bin/python. This replaces
the current PL configuration and does not restore it.
Images are 1024-byte little-endian outputs of
compile_concept_microcode_bram_image. Save stdout as a new raw result file.
"""
import argparse
import ctypes
import hashlib
import json
import mmap
import os
import platform
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = 0x40000000
REG_ID, REG_ADDR, REG_DATA = 0x00, 0x04, 0x08
REG_PARAM, REG_TRIGGER, REG_BUSY = 0x0C, 0x10, 0x14
REG_EVENTS, REG_COMMITS, REG_REJECTS = 0x18, 0x1C, 0x20
EXPECTED_ID = 0x4B504D43


class MMIO:
    def __init__(self):
        c_src = """#include <stdint.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
static volatile uint32_t *mmio_base = 0;
static int mmio_fd = -1;
int km_mmio_open(uint32_t base_addr) {
    mmio_fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (mmio_fd < 0) return -1;
    mmio_base = (volatile uint32_t *)mmap(NULL, 0x2000, PROT_READ | PROT_WRITE, MAP_SHARED, mmio_fd, base_addr);
    return (mmio_base == MAP_FAILED) ? -1 : 0;
}
uint32_t km_mmio_read(uint32_t offset) {
    return mmio_base[offset >> 2];
}
void km_mmio_write(uint32_t offset, uint32_t value) {
    mmio_base[offset >> 2] = value;
}
void km_mmio_close() {
    if (mmio_base) munmap((void*)mmio_base, 0x2000);
    if (mmio_fd >= 0) close(mmio_fd);
}
"""
        so_path = "/tmp/libkm_mmio.so"
        if not os.path.exists(so_path):
            import subprocess
            subprocess.run(["gcc", "-O2", "-shared", "-fPIC", "-x", "c", "-", "-o", so_path],
                           input=c_src, text=True, check=True)
        self.lib = ctypes.CDLL(so_path)
        self.lib.km_mmio_read.restype = ctypes.c_uint32
        if self.lib.km_mmio_open(BASE) != 0:
            raise RuntimeError(f"failed to mmap 0x{BASE:08X}")

    def read(self, offset):
        return int(self.lib.km_mmio_read(offset))

    def write(self, offset, value):
        self.lib.km_mmio_write(offset, value)

    def close(self):
        self.lib.km_mmio_close()


def run_image(mmio, image, expected, totals):
    words = struct.unpack("<256I", image)
    for address, word in enumerate(words):
        mmio.write(REG_ADDR, address)
        mmio.write(REG_DATA, word)
    for address, word in enumerate(words):
        mmio.write(REG_ADDR, address)
        if mmio.read(REG_DATA) != word:
            raise AssertionError(f"BRAM readback mismatch at word {address}")

    states = []
    for param in (5, 25):
        before = mmio.read(REG_EVENTS)
        mmio.write(REG_PARAM, param)
        mmio.write(REG_TRIGGER, 1)
        deadline = time.monotonic() + 2
        while mmio.read(REG_EVENTS) != ((before + 1) & 0xFFFFFFFF) or mmio.read(REG_BUSY):
            if time.monotonic() >= deadline:
                raise TimeoutError("sequencer did not finish")
        mmio.write(REG_ADDR, 0)
        state = mmio.read(REG_DATA)
        if state != expected:
            raise AssertionError(f"parameter {param}: expected {expected}, got {state}")
        states.append(state)
    actual = [mmio.read(REG_EVENTS), mmio.read(REG_COMMITS), mmio.read(REG_REJECTS)]
    if actual != totals:
        raise AssertionError(f"counts {actual}, expected {totals}")
    return {"states": states, "counts": actual}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bitstream", type=Path, required=True)
    parser.add_argument("--image-a", type=Path, required=True)
    parser.add_argument("--image-b", type=Path, required=True)
    parser.add_argument("--program", action="store_true", required=True,
                        help="replace the current PL configuration")
    args = parser.parse_args()
    if sys.byteorder != "little":
        raise RuntimeError("the MMIO interface requires a little-endian host")
    bitstream_hash = hashlib.sha256(args.bitstream.read_bytes()).hexdigest()
    images = [args.image_a.read_bytes(), args.image_b.read_bytes()]
    if any(len(image) != 1024 for image in images) or images[0] == images[1]:
        raise ValueError("two different 1024-byte images are required")

    try:
        from pynq import Bitstream
        Bitstream(str(args.bitstream)).download()
    except Exception:
        # Fallback to Linux FPGA Manager on Zynq-7000
        content = args.bitstream.read_bytes()
        pos = content.find(b'e\x00')
        if pos != -1:
            length = struct.unpack('>I', content[pos+1:pos+5])[0]
            payload = content[pos+5:pos+5+length]
        else:
            payload = content
        sl = struct.Struct('<I')
        sb = struct.Struct('>I')
        d = bytearray(len(payload))
        for offset in range(0, len(payload) - 3, 4):
            sb.pack_into(d, offset, sl.unpack_from(payload, offset)[0])
        fw_path = Path("/lib/firmware/pipeline.bin")
        fw_path.write_bytes(d)
        with open("/sys/class/fpga_manager/fpga0/flags", "w") as f:
            f.write("0\n")
        with open("/sys/class/fpga_manager/fpga0/firmware", "w") as f:
            f.write("pipeline.bin\n")
        time.sleep(0.5)
    mmio = MMIO()
    try:
        if mmio.read(REG_ID) != EXPECTED_ID:
            raise RuntimeError("unexpected FPGA interface ID")
        if [mmio.read(REG_EVENTS), mmio.read(REG_COMMITS), mmio.read(REG_REJECTS)] != [0, 0, 0]:
            raise RuntimeError("expected reset counters after programming")
        a = run_image(mmio, images[0], 11, [2, 1, 1])
        b = run_image(mmio, images[1], 9, [4, 2, 2])
    finally:
        mmio.close()
    if hashlib.sha256(args.bitstream.read_bytes()).hexdigest() != bitstream_hash:
        raise RuntimeError("bitstream file changed during the experiment")
    print(json.dumps({
        "host": platform.node(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "bitstream_sha256": bitstream_hash,
        "image_sha256": [hashlib.sha256(image).hexdigest() for image in images],
        "image_a": a,
        "image_b": b,
    }, indent=2))


if __name__ == "__main__":
    main()
