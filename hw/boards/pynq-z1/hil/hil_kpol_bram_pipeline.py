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
        self.fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        try:
            self.mem = mmap.mmap(self.fd, 0x2000, mmap.MAP_SHARED,
                                 mmap.PROT_READ | mmap.PROT_WRITE, offset=BASE)
        except BaseException:
            os.close(self.fd)
            raise

    def read(self, offset):
        return ctypes.c_uint32.from_buffer(self.mem, offset).value

    def write(self, offset, value):
        ctypes.c_uint32.from_buffer(self.mem, offset).value = value

    def close(self):
        self.mem.close()
        os.close(self.fd)


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

    from pynq import Bitstream
    Bitstream(str(args.bitstream)).download()
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
