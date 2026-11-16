#!/usr/bin/env python3
"""Rule update packet generator, CRC-8 validator, AXI4-Lite encoder, and golden reference model
for dual-bank CFG-P-HA (B4 Variant 2, Issue #252, EXP-GPU-02).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import struct
import sys
from typing import Iterable, Sequence

# AXI4-Lite register offsets of kpol_bram_pipeline_axi_ha (CFG-P-HA)
REG_CORE_ID = 0x000
REG_BRAM_ADDR = 0x004
REG_BRAM_DATA = 0x008
REG_EVENT_PARAM = 0x00C
REG_SW_TRIGGER = 0x010
REG_STATUS_BUSY = 0x014
REG_EVENTS_COUNT = 0x018
REG_COMMITS_COUNT = 0x01C
REG_REJECTS_COUNT = 0x020
REG_LAST_STATE = 0x024
REG_DROPPED_COUNT = 0x028
REG_FIFO_STATUS = 0x02C
REG_SHADOW_ADDR = 0x030
REG_SHADOW_DATA = 0x034
REG_BANK_SWAP_CTRL = 0x038
REG_SWAP_COUNT = 0x03C
REG_LAST_SWAP_WAIT = 0x040
REG_SEQ_EXEC_MONITOR = 0x044

EXPECTED_CORE_ID_KPHA = 0x4B504841  # ASCII "KPHA"

# Predicate micro-opcodes (km_concept_micro_engine.sv)
PRED_NOP = 0x00
PRED_EQ = 0x01
PRED_NEQ = 0x02
PRED_GT = 0x03
PRED_LT = 0x04
PRED_RANGE = 0x05
PRED_BITMASK = 0x06
VALID_PRED_OPCODES = frozenset({PRED_NOP, PRED_EQ, PRED_NEQ, PRED_GT, PRED_LT, PRED_RANGE, PRED_BITMASK})

# Action micro-opcodes (km_concept_micro_engine.sv)
ACT_ASSIGN = 0x00
ACT_INC = 0x01
ACT_DEC = 0x02
ACT_ADD = 0x03
ACT_SUB = 0x04
VALID_ACT_OPCODES = frozenset({ACT_ASSIGN, ACT_INC, ACT_DEC, ACT_ADD, ACT_SUB})

# Guard flag bits
GUARD_ASSUMPTION_EN = 0x01
GUARD_INVARIANT_EN = 0x02
GUARD_HAZARD_EN = 0x04
GUARD_INVERT_PRED = 0x08
GUARD_SUBSCRIBER_EN = 0x10
GUARD_RESERVED_MASK = 0xE0

# Binary wire packet constants (4-byte header + 12B W1..W3 or 16B W0..W3)
PACKET_MAGIC = 0x4B  # 'K'
PACKET_MODE_RULES_12B = 0x02  # version 1, include_w0 = 0 (W1..W3, 12-byte payload)
PACKET_MODE_FULL_16B = 0x03   # version 1, include_w0 = 1 (W0..W3, 16-byte payload)

INT32_MIN = -2147483648
INT32_MAX = 2147483647


class RulePacketError(ValueError):
    """Raised when a rule update packet or descriptor fails validation or CRC-8."""


def _to_s32(val: int) -> int:
    u = val & 0xFFFFFFFF
    return u - 0x100000000 if (u & 0x80000000) else u


def _to_u32(val: int) -> int:
    return val & 0xFFFFFFFF


def crc8_ccitt(data: bytes, poly: int = 0x07, init: int = 0x00) -> int:
    """Computes deterministic CRC-8/CCITT (polynomial x^8 + x^2 + x + 1 = 0x07)."""
    crc = init & 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


@dataclass(frozen=True)
class RuleDescriptorPatch:
    """Represents a validated descriptor update for a single concept CID (0..63)."""

    cid: int
    operand_val: int
    pred_opcode: int
    guard_flags: int
    hazard_limit: int = 0
    action_opcode: int = ACT_INC
    subscriber_cid: int = 0xFFFFFFFF  # >= 64 disables cascade
    init_state_w0: int | None = None

    def validate(self, num_concepts: int = 64) -> None:
        if not (0 <= self.cid < num_concepts):
            raise RulePacketError(f"cid out of range [0, {num_concepts - 1}]: {self.cid}")
        if self.pred_opcode not in VALID_PRED_OPCODES:
            raise RulePacketError(f"unsupported pred_opcode: 0x{self.pred_opcode:02x}")
        if self.action_opcode not in VALID_ACT_OPCODES:
            raise RulePacketError(f"unsupported action_opcode: 0x{self.action_opcode:02x}")
        if (self.guard_flags & ~0xFF) or (self.guard_flags & GUARD_RESERVED_MASK):
            raise RulePacketError(f"invalid or reserved guard_flags bits set: 0x{self.guard_flags:02x}")
        if not (0 <= self.hazard_limit <= 0xFF):
            raise RulePacketError(f"hazard_limit out of uint8 range: {self.hazard_limit}")
        if not (INT32_MIN <= _to_s32(self.operand_val) <= INT32_MAX):
            raise RulePacketError(f"operand_val out of int32 range: {self.operand_val}")
        if self.init_state_w0 is not None and not (INT32_MIN <= _to_s32(self.init_state_w0) <= INT32_MAX):
            raise RulePacketError(f"init_state_w0 out of int32 range: {self.init_state_w0}")

    @classmethod
    def threshold_ge(
        cls,
        cid: int,
        threshold: int,
        action_opcode: int = ACT_INC,
        subscriber_cid: int = 0xFFFFFFFF,
        hazard_limit: int = 0,
        init_state_w0: int | None = None,
    ) -> "RuleDescriptorPatch":
        """Constructs an exact signed int32 rule `X >= threshold` (`!(X < threshold)`)."""
        guard = GUARD_ASSUMPTION_EN | GUARD_INVARIANT_EN | GUARD_INVERT_PRED
        if hazard_limit > 0:
            guard |= GUARD_HAZARD_EN
        if 0 <= subscriber_cid < 64:
            guard |= GUARD_SUBSCRIBER_EN
        return cls(
            cid=cid,
            operand_val=threshold,
            pred_opcode=PRED_LT,
            guard_flags=guard,
            hazard_limit=hazard_limit,
            action_opcode=action_opcode,
            subscriber_cid=subscriber_cid,
            init_state_w0=init_state_w0,
        )

    def pack_w2(self) -> int:
        return (
            (self.pred_opcode & 0xFF)
            | ((self.guard_flags & 0xFF) << 8)
            | ((self.hazard_limit & 0xFF) << 16)
            | ((self.action_opcode & 0xFF) << 24)
        )

    def words_w1_w3(self) -> tuple[int, int, int]:
        self.validate()
        return (_to_u32(self.operand_val), self.pack_w2(), _to_u32(self.subscriber_cid))

    def words_w0_w3(self) -> tuple[int, int, int, int]:
        self.validate()
        w0 = _to_u32(0 if self.init_state_w0 is None else self.init_state_w0)
        w1, w2, w3 = self.words_w1_w3()
        return (w0, w1, w2, w3)

    def payload_bytes(self) -> bytes:
        """Returns 12-byte (W1..W3) or 16-byte (W0..W3) little-endian descriptor payload."""
        if self.init_state_w0 is None:
            w1, w2, w3 = self.words_w1_w3()
            return struct.pack("<III", w1, w2, w3)
        w0, w1, w2, w3 = self.words_w0_w3()
        return struct.pack("<IIII", w0, w1, w2, w3)


@dataclass(frozen=True)
class AxiWriteTxn:
    """Single 32-bit AXI4-Lite write transaction."""

    addr: int
    data: int
    strb: int = 0xF
    comment: str = ""


def build_rule_packet(patch: RuleDescriptorPatch, num_concepts: int = 64) -> bytes:
    """Packs a validated rule patch into a CRC-8 protected wire frame.

    Frame layout:
      [0] magic (0x4B 'K')
      [1] mode  (0x02 = 12B rules W1..W3, 0x03 = 16B full W0..W3)
      [2] cid   (0..63)
      [3] crc8  (CRC-8/CCITT over bytes [0..2] + payload)
      [4..] payload (12 bytes for W1..W3 or 16 bytes for W0..W3)
    """
    patch.validate(num_concepts=num_concepts)
    payload = patch.payload_bytes()
    mode = PACKET_MODE_FULL_16B if patch.init_state_w0 is not None else PACKET_MODE_RULES_12B
    prefix = bytes((PACKET_MAGIC, mode, patch.cid & 0xFF))
    checksum = crc8_ccitt(prefix + payload)
    return prefix + bytes((checksum,)) + payload


def verify_and_unpack_packet(packet: bytes, num_concepts: int = 64) -> RuleDescriptorPatch:
    """Verifies frame magic, length, CRC-8, and CME opcode invariants; returns unpacked patch."""
    if len(packet) < 4:
        raise RulePacketError(f"packet too short ({len(packet)} bytes)")
    magic, mode, cid, rx_crc = packet[0], packet[1], packet[2], packet[3]
    if magic != PACKET_MAGIC:
        raise RulePacketError(f"invalid packet magic: 0x{magic:02x} != 0x{PACKET_MAGIC:02x}")
    if mode == PACKET_MODE_RULES_12B:
        expected_len = 4 + 12
        include_w0 = False
    elif mode == PACKET_MODE_FULL_16B:
        expected_len = 4 + 16
        include_w0 = True
    else:
        raise RulePacketError(f"unsupported packet mode: 0x{mode:02x}")

    if len(packet) != expected_len:
        raise RulePacketError(f"packet length mismatch for mode 0x{mode:02x}: {len(packet)} != {expected_len}")

    payload = packet[4:]
    calc_crc = crc8_ccitt(packet[:3] + payload)
    if calc_crc != rx_crc:
        raise RulePacketError(f"CRC-8 mismatch: rx=0x{rx_crc:02x}, expected=0x{calc_crc:02x}")

    if include_w0:
        w0, w1, w2, w3 = struct.unpack("<IIII", payload)
        init_w0: int | None = _to_s32(w0)
    else:
        w1, w2, w3 = struct.unpack("<III", payload)
        init_w0 = None

    pred_op = w2 & 0xFF
    guard_fl = (w2 >> 8) & 0xFF
    haz_lim = (w2 >> 16) & 0xFF
    act_op = (w2 >> 24) & 0xFF

    patch = RuleDescriptorPatch(
        cid=cid,
        operand_val=_to_s32(w1),
        pred_opcode=pred_op,
        guard_flags=guard_fl,
        hazard_limit=haz_lim,
        action_opcode=act_op,
        subscriber_cid=w3,
        init_state_w0=init_w0,
    )
    patch.validate(num_concepts=num_concepts)
    return patch


def encode_axi_ha_transactions(
    patch_or_packet: RuleDescriptorPatch | bytes,
    issue_swap: bool = True,
    num_concepts: int = 64,
) -> list[AxiWriteTxn]:
    """Converts a validated packet or patch into CFG-P-HA AXI4-Lite MMIO write transactions.

    Uses SHADOW_ADDR (0x030) + auto-incrementing SHADOW_DATA (0x034) + BANK_SWAP_CTRL (0x038).
    """
    patch = (
        verify_and_unpack_packet(patch_or_packet, num_concepts=num_concepts)
        if isinstance(patch_or_packet, (bytes, bytearray))
        else patch_or_packet
    )
    patch.validate(num_concepts=num_concepts)

    txns: list[AxiWriteTxn] = []
    if patch.init_state_w0 is not None:
        base_word_addr = patch.cid * 4
        w0, w1, w2, w3 = patch.words_w0_w3()
        txns.append(AxiWriteTxn(REG_SHADOW_ADDR, base_word_addr, comment=f"CID={patch.cid} W0..W3 base"))
        txns.append(AxiWriteTxn(REG_SHADOW_DATA, w0, comment=f"CID={patch.cid} W0 init_state"))
        txns.append(AxiWriteTxn(REG_SHADOW_DATA, w1, comment=f"CID={patch.cid} W1 operand"))
        txns.append(AxiWriteTxn(REG_SHADOW_DATA, w2, comment=f"CID={patch.cid} W2 opcodes/guards"))
        txns.append(AxiWriteTxn(REG_SHADOW_DATA, w3, comment=f"CID={patch.cid} W3 subscriber_cid"))
    else:
        base_word_addr = patch.cid * 4 + 1
        w1, w2, w3 = patch.words_w1_w3()
        txns.append(AxiWriteTxn(REG_SHADOW_ADDR, base_word_addr, comment=f"CID={patch.cid} W1..W3 base"))
        txns.append(AxiWriteTxn(REG_SHADOW_DATA, w1, comment=f"CID={patch.cid} W1 operand"))
        txns.append(AxiWriteTxn(REG_SHADOW_DATA, w2, comment=f"CID={patch.cid} W2 opcodes/guards"))
        txns.append(AxiWriteTxn(REG_SHADOW_DATA, w3, comment=f"CID={patch.cid} W3 subscriber_cid"))

    if issue_swap:
        txns.append(AxiWriteTxn(REG_BANK_SWAP_CTRL, 1, comment="Request atomic idle-boundary bank swap"))
    return txns


class DualBankCfgPHAModel:
    """Bit-accurate software reference model of dual-bank CFG-P-HA (km_concept_bram_dual_ha + CME)."""

    def __init__(self, num_concepts: int = 64) -> None:
        self.num_concepts = num_concepts
        self.words_total = num_concepts * 4
        self.bank0 = [0] * self.words_total
        self.bank1 = [0] * self.words_total
        self.active_bank = 0
        self.dirty = [False] * self.words_total
        self.shadow_w0_override = [False] * num_concepts
        self.swap_count = 0
        self.events_processed = 0
        self.committed_count = 0
        self.rejected_count = 0
        self.last_committed_state = 0

    def _act_ram(self) -> list[int]:
        return self.bank1 if self.active_bank else self.bank0

    def _sh_ram(self) -> list[int]:
        return self.bank0 if self.active_bank else self.bank1

    def sync_load_concept(self, patch: RuleDescriptorPatch) -> None:
        """Loads W0..W3 synchronously into both banks during PHASE_LOAD (!busy)."""
        w0, w1, w2, w3 = patch.words_w0_w3()
        base = patch.cid * 4
        for offset, val in enumerate((w0, w1, w2, w3)):
            self.bank0[base + offset] = val
            self.bank1[base + offset] = val
            self.dirty[base + offset] = False
        self.shadow_w0_override[patch.cid] = False

    def inject_shadow_packet(self, packet_or_patch: bytes | RuleDescriptorPatch) -> None:
        """Applies a hot shadow write to ~active_bank without touching active_bank."""
        patch = (
            verify_and_unpack_packet(packet_or_patch, num_concepts=self.num_concepts)
            if isinstance(packet_or_patch, (bytes, bytearray))
            else packet_or_patch
        )
        patch.validate(num_concepts=self.num_concepts)
        sh = self._sh_ram()
        base = patch.cid * 4
        if patch.init_state_w0 is not None:
            w0, w1, w2, w3 = patch.words_w0_w3()
            for offset, val in enumerate((w0, w1, w2, w3)):
                sh[base + offset] = val
                self.dirty[base + offset] = True
            self.shadow_w0_override[patch.cid] = True
        else:
            w1, w2, w3 = patch.words_w1_w3()
            for offset, val in enumerate((w1, w2, w3), start=1):
                sh[base + offset] = val
                self.dirty[base + offset] = True

    def commit_bank_swap_and_resync(self, finish_resync: bool = True) -> None:
        """Executes atomic bank flip at ST_IDLE boundary and optional background Port-A resync."""
        self.active_bank ^= 1
        self.swap_count += 1
        for c in range(self.num_concepts):
            self.shadow_w0_override[c] = False
        if finish_resync:
            self.complete_background_resync()

    def complete_background_resync(self) -> None:
        act = self._act_ram()
        sh = self._sh_ram()
        for idx in range(self.words_total):
            if self.dirty[idx]:
                sh[idx] = act[idx]
                self.dirty[idx] = False

    @staticmethod
    def evaluate_descriptor(words: Sequence[int], event_param: int) -> tuple[bool, int, int | None]:
        """Exact bit-accurate evaluation of km_concept_micro_engine.sv + kpol_txn_gate_v2.sv."""
        w0, w1, w2, w3 = (_to_u32(words[0]), _to_u32(words[1]), _to_u32(words[2]), _to_u32(words[3]))
        cur_s = _to_s32(w0)
        op_s = _to_s32(w1)
        param_s = _to_s32(event_param)
        param_u = _to_u32(event_param)

        pred_op = w2 & 0xFF
        guard_fl = (w2 >> 8) & 0xFF
        haz_lim = (w2 >> 16) & 0xFF
        act_op = (w2 >> 24) & 0xFF

        if pred_op == PRED_NOP:
            pred_raw = True
        elif pred_op == PRED_EQ:
            pred_raw = param_u == w1
        elif pred_op == PRED_NEQ:
            pred_raw = param_u != w1
        elif pred_op == PRED_GT:
            pred_raw = param_s > op_s
        elif pred_op == PRED_LT:
            pred_raw = param_s < op_s
        elif pred_op == PRED_RANGE:
            lo = w1 & 0xFFFF
            hi = (w1 >> 16) & 0xFFFF
            lo_s = lo - 0x10000 if (lo & 0x8000) else lo
            hi_s = hi - 0x10000 if (hi & 0x8000) else hi
            pred_raw = (param_s >= lo_s) and (param_s <= hi_s)
        elif pred_op == PRED_BITMASK:
            pred_raw = (param_u & w1) != 0
        else:
            pred_raw = False

        action_valid = True
        arith_overflow = False
        if act_op == ACT_ASSIGN:
            cand_u = param_u
        elif act_op == ACT_INC:
            cand_u = _to_u32(w0 + 1)
            arith_overflow = w0 == 0x7FFFFFFF
        elif act_op == ACT_DEC:
            cand_u = _to_u32(w0 - 1)
            arith_overflow = w0 == 0x80000000
        elif act_op == ACT_ADD:
            cand_u = _to_u32(w0 + w1)
            arith_overflow = ((w0 >> 31) == (w1 >> 31)) and (((cand_u >> 31) & 1) != ((w0 >> 31) & 1))
        elif act_op == ACT_SUB:
            cand_u = _to_u32(w0 - w1)
            arith_overflow = ((w0 >> 31) != (w1 >> 31)) and (((cand_u >> 31) & 1) != ((w0 >> 31) & 1))
        else:
            cand_u = w0
            action_valid = False

        assumption_known = bool(guard_fl & GUARD_ASSUMPTION_EN)
        assumption_true = (not pred_raw) if (guard_fl & GUARD_INVERT_PRED) else pred_raw
        invariant_known = bool(guard_fl & GUARD_INVARIANT_EN)
        invariant_true = (not arith_overflow) and (_to_s32(cand_u) >= 0)
        hazard_true = bool(guard_fl & GUARD_HAZARD_EN) and (haz_lim != 0) and (param_s > haz_lim)

        committed = (
            action_valid
            and assumption_known
            and assumption_true
            and invariant_known
            and invariant_true
            and (not hazard_true)
        )
        if not committed:
            return (False, w0, None)

        sub_cid: int | None = None
        if w3 < 64 and (bool(guard_fl & GUARD_SUBSCRIBER_EN) or w3 != 0):
            sub_cid = w3
        return (True, cand_u, sub_cid)

    def step_event(self, cid: int, event_param: int) -> bool:
        """Processes an external event (plus any acyclic cascades) against active_bank."""
        queue: list[tuple[int, int]] = [(cid, _to_u32(event_param))]
        first_committed: bool | None = None
        while queue:
            cur_cid, cur_param = queue.pop(0)
            act = self._act_ram()
            sh = self._sh_ram()
            base = cur_cid * 4
            desc = act[base : base + 4]
            committed, new_w0, sub_cid = self.evaluate_descriptor(desc, cur_param)
            self.events_processed += 1
            if first_committed is None:
                first_committed = committed
            if committed:
                self.committed_count += 1
                self.last_committed_state = new_w0
                act[base] = new_w0
                if not self.shadow_w0_override[cur_cid]:
                    sh[base] = new_w0
                    self.dirty[base] = False
                if sub_cid is not None and sub_cid != cur_cid:
                    queue.append((sub_cid, new_w0))
            else:
                self.rejected_count += 1
        return bool(first_committed)

    def get_active_w0(self, cid: int) -> int:
        return self._act_ram()[cid * 4]


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cid", type=int, default=5, help="Target concept ID (0..63)")
    ap.add_argument("--threshold-ge", type=int, default=40, help="Signed int32 threshold for X >= T")
    ap.add_argument("--init-w0", type=int, default=None, help="Optional explicit W0 state override")
    ap.add_argument("--no-swap", action="store_true", help="Omit BANK_SWAP_CTRL (0x038) transaction")
    args = ap.parse_args(list(argv) if argv is not None else None)

    patch = RuleDescriptorPatch.threshold_ge(
        cid=args.cid,
        threshold=args.threshold_ge,
        init_state_w0=args.init_w0,
    )
    pkt = build_rule_packet(patch)
    txns = encode_axi_ha_transactions(pkt, issue_swap=not args.no_swap)
    out = {
        "cid": patch.cid,
        "include_w0": patch.init_state_w0 is not None,
        "packet_hex": pkt.hex(),
        "packet_len_bytes": len(pkt),
        "payload_len_bytes": len(pkt) - 4,
        "crc8_hex": f"0x{pkt[3]:02x}",
        "axi_transactions": [
            {"addr": f"0x{t.addr:03x}", "data": f"0x{t.data:08x}", "strb": f"0x{t.strb:x}", "comment": t.comment}
            for t in txns
        ],
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
