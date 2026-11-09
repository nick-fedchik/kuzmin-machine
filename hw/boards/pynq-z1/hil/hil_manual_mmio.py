#!/usr/bin/env python3
import argparse
import time
from pathlib import Path

import pynq.pl_server.embedded_device
from pynq import Bitstream, MMIO


BASE_ADDRESS = 0x40000000
MMIO_SIZE = 0x1000
REG_CANDIDATE = 0x00
REG_CONDITIONS = 0x04
REG_COMMAND = 0x08
REG_STATUS = 0x0C
REG_STATE = 0x10
REG_ID = 0x14
STATUS_BUSY = 1 << 8
STATUS_VALID = 1 << 0
STATUS_COMMITTED = 1 << 1
STATUS_REJECTED = 1 << 2
STATUS_REJECTED_INVARIANT = 1 << 4


def wait_for_result(mmio: MMIO, timeout_seconds: float) -> int:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = mmio.read(REG_STATUS)
        if status & STATUS_VALID and not status & STATUS_BUSY:
            return status
        time.sleep(0.001)
    raise TimeoutError(f"KPOL transaction timed out; status=0x{mmio.read(REG_STATUS):08x}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load and manually test the Kuzmin Machine PYNQ-Z1 bitstream."
    )
    parser.add_argument("--bitstream", type=Path, required=True)
    parser.add_argument(
        "--program",
        action="store_true",
        help="explicitly authorize loading this bitstream onto the connected FPGA",
    )
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()

    if not args.program:
        parser.error("refusing to program the FPGA without the explicit --program flag")
    if not args.bitstream.is_file():
        parser.error(f"bitstream not found: {args.bitstream}")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    Bitstream(str(args.bitstream)).download()
    mmio = MMIO(BASE_ADDRESS, MMIO_SIZE)

    device_id = mmio.read(REG_ID)
    if device_id != 0x4B504F4C:
        raise RuntimeError(f"unexpected KPOL ID: 0x{device_id:08x}")

    mmio.write(REG_CANDIDATE, 0x00001234)
    mmio.write(REG_CONDITIONS, 0x0000003F)
    mmio.write(REG_COMMAND, 1)
    nominal_status = wait_for_result(mmio, args.timeout)
    nominal_state = mmio.read(REG_STATE)
    if nominal_state != 0x00001234 or not nominal_status & STATUS_COMMITTED:
        raise RuntimeError(
            f"nominal commit failed: state=0x{nominal_state:08x}, "
            f"status=0x{nominal_status:08x}"
        )

    mmio.write(REG_CANDIDATE, 0x00005678)
    mmio.write(REG_CONDITIONS, 0x0000002F)
    mmio.write(REG_COMMAND, 1)
    reject_status = wait_for_result(mmio, args.timeout)
    reject_state = mmio.read(REG_STATE)
    if (
        reject_state != nominal_state
        or not reject_status & STATUS_REJECTED
        or not reject_status & STATUS_REJECTED_INVARIANT
    ):
        raise RuntimeError(
            f"invariant rejection failed: state=0x{reject_state:08x}, "
            f"status=0x{reject_status:08x}"
        )

    print(
        "PASS: KPOL ID, nominal commit, and invariant fail-closed behavior "
        f"(state=0x{reject_state:08x})"
    )


if __name__ == "__main__":
    main()
