#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пакетування/верифікація 64-бітного кадра km_pmod_event_egress (CRC-8 poly 0x07)
та статистичний агрегатор міжплатного експерименту EXP-GPU-01 (Issue #226).
"""

from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path
from typing import Any

FRAME_TAG_CRC8 = 0b01
CRC8_POLY = 0x07
CRC8_INIT = 0x00

# Попперівські критерії фальсифікації з Issue #226:
POPPER_MAX_P99_9_US = 15.0
POPPER_MAX_SIGMA_US = 2.0


class EgressFrameError(ValueError):
    """Виняток при порушенні формату або CRC-8 64-бітного кадра події."""


def calc_crc8(payload_56: int) -> int:
    """Еталонний розрахунок CRC-8 (poly 0x07, init 0x00, MSB-first по 56 бітах [55:0])."""
    if not (0 <= payload_56 < (1 << 56)):
        raise EgressFrameError(f"payload_56 out of 56-bit range: {payload_56:#x}")
    crc = CRC8_INIT
    for bit in range(55, -1, -1):
        fb = ((crc >> 7) ^ ((payload_56 >> bit) & 1)) & 1
        crc = ((crc << 1) & 0xFF) ^ (CRC8_POLY if fb else 0x00)
    return crc


def pack_egress_frame64(cid: int, mask16: int, state: int, tag: int = FRAME_TAG_CRC8) -> int:
    """Формує 64-бітний кадр km_pmod_event_egress.sv:
    [63:56] crc8, [55:54] tag (2'b01), [53:48] cid[5:0], [47:32] mask[15:0], [31:0] state[31:0].
    """
    if not (0 <= tag <= 0b11):
        raise EgressFrameError(f"tag out of 2-bit range: {tag}")
    if not (0 <= cid <= 63):
        raise EgressFrameError(f"cid out of 6-bit range (0..63): {cid}")
    if not (0 <= mask16 <= 0xFFFF):
        raise EgressFrameError(f"mask16 out of 16-bit range: {mask16:#x}")
    state_u32 = state & 0xFFFFFFFF
    payload_56 = ((tag & 0x3) << 54) | ((cid & 0x3F) << 48) | ((mask16 & 0xFFFF) << 32) | state_u32
    crc8 = calc_crc8(payload_56)
    return (crc8 << 56) | payload_56


def encode_egress_frame_bytes(cid: int, mask16: int, state: int, tag: int = FRAME_TAG_CRC8) -> bytes:
    """Кодує 64-бітний кадр у 8 байтів MSB-first (порядок передачі SPI / PAR8)."""
    frame64 = pack_egress_frame64(cid=cid, mask16=mask16, state=state, tag=tag)
    return struct.pack(">Q", frame64)


def verify_and_unpack_egress_frame64(frame64: int) -> dict[str, int]:
    """Перевіряє CRC-8 і тег 64-бітного кадра та повертає розпаковані поля."""
    if not (0 <= frame64 < (1 << 64)):
        raise EgressFrameError(f"frame64 out of 64-bit range: {frame64:#x}")
    got_crc8 = (frame64 >> 56) & 0xFF
    payload_56 = frame64 & ((1 << 56) - 1)
    exp_crc8 = calc_crc8(payload_56)
    if got_crc8 != exp_crc8:
        raise EgressFrameError(
            f"CRC-8 mismatch: got 0x{got_crc8:02x}, expected 0x{exp_crc8:02x} for frame 0x{frame64:016x}"
        )
    tag = (payload_56 >> 54) & 0x3
    if tag != FRAME_TAG_CRC8:
        raise EgressFrameError(f"Invalid frame tag: got 0b{tag:02b}, expected 0b{FRAME_TAG_CRC8:02b}")
    cid = (payload_56 >> 48) & 0x3F
    mask16 = (payload_56 >> 32) & 0xFFFF
    state_u32 = payload_56 & 0xFFFFFFFF
    return {
        "frame64": frame64,
        "crc8": got_crc8,
        "tag": tag,
        "cid": cid,
        "mask16": mask16,
        "state": state_u32,
    }


def verify_and_unpack_egress_bytes(raw: bytes) -> dict[str, int]:
    """Перевіряє 8-байтний буфер кадра MSB-first та розпаковує поля."""
    if len(raw) != 8:
        raise EgressFrameError(f"Expected 8 bytes for egress frame, got {len(raw)}")
    (frame64,) = struct.unpack(">Q", raw)
    return verify_and_unpack_egress_frame64(frame64)


def compute_distribution_stats(samples_us: list[float]) -> dict[str, float]:
    """Обчислює min, p50, p99, p99.9, max, mean, sigma (ddof=1) для вибірки у мікросекундах."""
    if not samples_us:
        raise ValueError("Empty sample list")
    s = sorted(float(x) for x in samples_us)
    n = len(s)

    def _pct(p: float) -> float:
        idx = int(math.ceil((p / 100.0) * n)) - 1
        idx = max(0, min(n - 1, idx))
        return s[idx]

    mean = sum(s) / n
    var = sum((x - mean) ** 2 for x in s) / (n - 1) if n > 1 else 0.0
    sigma = math.sqrt(var)
    return {
        "count": n,
        "min_us": round(s[0], 4),
        "p50_us": round(_pct(50.0), 4),
        "p99_us": round(_pct(99.0), 4),
        "p99_9_us": round(_pct(99.9), 4),
        "max_us": round(s[-1], 4),
        "mean_us": round(mean, 4),
        "sigma_us": round(sigma, 4),
    }


def evaluate_popper_criterion_226(stats_us: dict[str, float]) -> dict[str, Any]:
    """Перевіряє Попперівський критерій фальсифікації Issue #226:
    Якщо p99.9(T_e2e) > 15 мкс або sigma > 2 мкс — гіпотеза субмікросекундного/мікросекундного
    міжплатного контуру без PCIe вважається спростованою.
    """
    p99_9 = float(stats_us["p99_9_us"])
    sigma = float(stats_us["sigma_us"])
    p99_9_exceeded = p99_9 > POPPER_MAX_P99_9_US
    sigma_exceeded = sigma > POPPER_MAX_SIGMA_US
    falsified = p99_9_exceeded or sigma_exceeded
    return {
        "threshold_p99_9_us": POPPER_MAX_P99_9_US,
        "threshold_sigma_us": POPPER_MAX_SIGMA_US,
        "measured_p99_9_us": p99_9,
        "measured_sigma_us": sigma,
        "p99_9_exceeded": p99_9_exceeded,
        "sigma_exceeded": sigma_exceeded,
        "hypothesis_falsified": falsified,
        "verdict": (
            "FALSIFIED_NEEDS_PCIE_OR_DIRECT_HW_BUS"
            if falsified
            else "NOT_FALSIFIED_WITHIN_15US_BUDGET"
        ),
    }


def summarize_crossboard_runs(run_paths: list[Path]) -> dict[str, Any]:
    """Агрегує серію R прогонів міжплатного контуру PYNQ-Z1 -> Jetson AGX Orin."""
    all_rtt_us: list[float] = []
    all_oneway_us: list[float] = []
    all_pl_mmio_us: list[float] = []
    all_jetson_host_us: list[float] = []
    all_net_rtt_us: list[float] = []
    all_net_oneway_est_us: list[float] = []
    all_rtt_net_plus_pynq_mmio_us: list[float] = []
    all_gpu_math_ns: list[float] = []
    all_gpu_e2e_sm_ns: list[float] = []
    per_run_summaries: list[dict[str, Any]] = []

    for rp in run_paths:
        data = json.loads(rp.read_text(encoding="utf-8"))
        rtt_us = [float(x) for x in data["samples_rtt_us"]]
        oneway_us = [float(x) for x in data["samples_oneway_est_us"]]
        pl_mmio_us = [float(x) for x in data["samples_pl_mmio_us"]]
        j_host_us = [float(x) for x in data["samples_jetson_host_us"]]
        net_rtt_us = [
            round(max(0.0, r - p - j), 4)
            for r, p, j in zip(rtt_us, pl_mmio_us, j_host_us)
        ]
        net_oneway_est_us = [
            round(max(0.0, (r - p - j) / 2.0), 4)
            for r, p, j in zip(rtt_us, pl_mmio_us, j_host_us)
        ]
        rtt_net_plus_pynq_us = [
            round(max(0.0, r - j), 4)
            for r, j in zip(rtt_us, j_host_us)
        ]
        all_rtt_us.extend(rtt_us)
        all_oneway_us.extend(oneway_us)
        all_pl_mmio_us.extend(pl_mmio_us)
        all_jetson_host_us.extend(j_host_us)
        all_net_rtt_us.extend(net_rtt_us)
        all_net_oneway_est_us.extend(net_oneway_est_us)
        all_rtt_net_plus_pynq_mmio_us.extend(rtt_net_plus_pynq_us)
        gpu_rep = data.get("jetson_gpu_report", {})
        if "gpu_math_gt_ns_p50" in gpu_rep:
            all_gpu_math_ns.append(float(gpu_rep["gpu_math_gt_ns_p50"]))
            all_gpu_e2e_sm_ns.append(float(gpu_rep["gpu_e2e_gt_ns_p50"]))
        r_rtt = compute_distribution_stats(rtt_us)
        r_oneway = compute_distribution_stats(oneway_us)
        per_run_summaries.append(
            {
                "run_index": data.get("run_index"),
                "file": rp.name,
                "events": len(rtt_us),
                "neg_crc_test_rejected": data.get("neg_crc_test_rejected", False),
                "cpu_gpu_state_mismatches": gpu_rep.get("state_mismatches", -1),
                "rtt_us": r_rtt,
                "oneway_est_us": r_oneway,
                "gpu_math_gt_ns_p50": gpu_rep.get("gpu_math_gt_ns_p50"),
                "gpu_e2e_gt_ns_p50": gpu_rep.get("gpu_e2e_gt_ns_p50"),
                "gpu_e2e_gt_ns_p99_9": gpu_rep.get("gpu_e2e_gt_ns_p99_9"),
            }
        )

    pooled_rtt = compute_distribution_stats(all_rtt_us)
    pooled_oneway = compute_distribution_stats(all_oneway_us)
    pooled_pl_mmio = compute_distribution_stats(all_pl_mmio_us)
    pooled_jetson_host = compute_distribution_stats(all_jetson_host_us)
    pooled_net_rtt = compute_distribution_stats(all_net_rtt_us)
    pooled_net_oneway_est = compute_distribution_stats(all_net_oneway_est_us)
    pooled_rtt_net_plus_pynq = compute_distribution_stats(all_rtt_net_plus_pynq_mmio_us)

    return {
        "runs_count": len(run_paths),
        "total_events": len(all_rtt_us),
        "pl_core_fixed_cycles": 8,
        "pl_core_fixed_ns_at_100mhz": 80.0,
        "pmod_par8_wire_ns_at_100mhz": 170.0,
        "pmod_spi_wire_ns_at_100mhz": 1290.0,
        "pooled_rtt_us": pooled_rtt,
        "pooled_oneway_est_us": pooled_oneway,
        "pooled_pl_mmio_us": pooled_pl_mmio,
        "pooled_jetson_host_us": pooled_jetson_host,
        "pooled_net_rtt_us": pooled_net_rtt,
        "pooled_net_oneway_est_us": pooled_net_oneway_est,
        "pooled_rtt_net_plus_pynq_mmio_us": pooled_rtt_net_plus_pynq,
        "popper_rtt_evaluation": evaluate_popper_criterion_226(pooled_rtt),
        "popper_oneway_evaluation": evaluate_popper_criterion_226(pooled_oneway),
        "per_run": per_run_summaries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summarize", nargs="+", type=Path, help="JSON run files to summarize")
    parser.add_argument("--out", type=Path, help="Output summary JSON path")
    args = parser.parse_args()
    if args.summarize:
        summary = summarize_crossboard_runs(args.summarize)
        txt = json.dumps(summary, indent=2, ensure_ascii=False)
        if args.out:
            args.out.write_text(txt + "\n", encoding="utf-8")
        print(txt)


if __name__ == "__main__":
    main()
