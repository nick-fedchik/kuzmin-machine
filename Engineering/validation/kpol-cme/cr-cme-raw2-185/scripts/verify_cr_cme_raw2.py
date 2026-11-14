#!/usr/bin/env python3
"""Reproducible verification script for ADR B7 / CR #185 (CME-RAW-2 & KPOL-SYS-02)."""
import math
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "Engineering" / "sw" / "kpol-ref"))
import kpol_reference as kr  # noqa: E402


def verify_bit_layout(name: str, words: dict[str, list[tuple[int, int, str]]]) -> None:
    for word_name, fields in words.items():
        covered = set()
        for hi, lo, field_name in fields:
            assert 0 <= lo <= hi <= 31, f"{name}.{word_name}.{field_name}: invalid bit slice [{hi}:{lo}]"
            bits = set(range(lo, hi + 1))
            overlap = covered & bits
            assert not overlap, f"{name}.{word_name}.{field_name}: overlap on bits {sorted(overlap)}"
            covered |= bits
        assert covered == set(range(32)), f"{name}.{word_name}: uncovered bits {sorted(set(range(32)) - covered)}"


def main() -> int:
    cme_raw1_words = {
        "W0": [(31, 0, "current_state")],
        "W1": [(31, 0, "operand_val")],
        "W2": [(31, 24, "action_opcode"), (23, 16, "hazard_limit"), (15, 8, "guard_flags"), (7, 0, "pred_opcode")],
        "W3": [(31, 8, "reserved"), (7, 0, "subscriber_cid")],
    }
    cme_raw2_words = {
        "W0": [(31, 0, "state_value_i32")],
        "W1": [
            (31, 16, "commit_seq_u16"),
            (15, 8, "last_reject_code"),
            (7, 2, "runtime_flags_rsvd"),
            (1, 1, "fault_latched"),
            (0, 0, "state_valid"),
        ],
        "W2": [(31, 0, "guard_operand_i32")],
        "W3": [(31, 0, "action_operand_i32")],
        "W4": [(31, 24, "inv_mode"), (23, 16, "action_opcode"), (15, 8, "guard_flags"), (7, 0, "pred_opcode")],
        "W5": [(31, 0, "inv_bound_lo_i32")],
        "W6": [(31, 0, "inv_bound_hi_i32")],
        "W7": [
            (31, 24, "routing_acl_flags"),
            (23, 16, "hazard_target_cid"),
            (15, 8, "uninit_sub_cid"),
            (7, 0, "subscriber0_cid"),
        ],
    }
    verify_bit_layout("CME-RAW-1", cme_raw1_words)
    verify_bit_layout("CME-RAW-2", cme_raw2_words)

    # Cross-check CME-RAW-1 W2 layout against ConceptMicroDescriptor.pack()
    desc = kr.ConceptMicroDescriptor(
        cid=0,
        name="Probe",
        current_state=0x11223344,
        operand_val=0x55667788,
        pred_opcode=0x01,
        guard_flags=0x03,
        hazard_limit=0x07,
        action_opcode=0x04,
        subscriber_cid=0x09,
    )
    packed = desc.pack()
    assert len(packed) == 16
    w0, w1, w2, w3 = (int.from_bytes(packed[i : i + 4], "little") for i in range(0, 16, 4))
    assert w2 == ((0x04 << 24) | (0x07 << 16) | (0x03 << 8) | 0x01)
    assert w3 == 0x09
    print("PASS: CME-RAW-1 (128 bits, verified vs ConceptMicroDescriptor.pack) and CME-RAW-2 W0..W7 (256 bits) complete.")

    # Capacity calculation for RAMB36E1 (36 Kb = 4096 B usable per 32-bit bank, 140 blocks on XC7Z020)
    for n in (64, 128, 256):
        total_bytes = n * 32
        ramb36_single = math.ceil(total_bytes / 4096)
        ramb36_dual = 2 * math.ceil((total_bytes // 2) / 4096)
        print(
            f"CALC: N={n} concepts -> {total_bytes} B -> "
            f"single-bank {ramb36_single}xRAMB36E1 ({ramb36_single/140*100:.2f}%), "
            f"dual-bank {ramb36_dual}xRAMB36E1 ({ramb36_dual/140*100:.2f}%)"
        )

    # Real Secure Boot API check (current v0x0006, 1024-byte payload) + fail-closed rejection of v0x0007 / 2048 B
    key = b"kuzmin-machine-cr185-probe-key-01"
    payload_1024 = bytes(1024)
    signed_1024 = kr.compile_signed_bram_image(payload_1024, key, key_id=1)
    assert len(signed_1024) == 1088
    ok, reason = kr.verify_bram_signature(signed_1024, key)
    assert ok, f"expected valid signature, got: {reason}"

    # Tampering version field from 0x0006 to 0x0007 must be rejected by verify_bram_signature
    tampered_ver = bytearray(signed_1024)
    tampered_ver[4:6] = (0x0007).to_bytes(2, "little")
    ok_bad, reason_bad = kr.verify_bram_signature(bytes(tampered_ver), key)
    assert not ok_bad, "expected failure for version 0x0007"
    print(f"PASS: verify_bram_signature rejects version 0x0007 on current code ({reason_bad})")

    # Passing 2048-byte payload to current compile_signed_bram_image must fail (hardcoded 1024 B)
    try:
        kr.compile_signed_bram_image(bytes(2048), key, key_id=1)
        raise AssertionError("expected failure for 2048-byte payload")
    except (ValueError, kr.KpolError) as exc:
        print(f"PASS: current compile_signed_bram_image rejects 2048 B until v0x0007 update ({exc})")

    # Verify zero changes in Engineering/hw and Engineering/sw relative to feat/184-kpol-cme2-profile
    diff = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--name-only", "origin/feat/184-kpol-cme2-profile", "--", "Engineering/hw", "Engineering/sw"],
        capture_output=True, text=True, check=True,
    )
    assert diff.stdout.strip() == "", f"unexpected changes in hw/sw: {diff.stdout}"
    print("PASS: zero changes in Engineering/hw and Engineering/sw.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
