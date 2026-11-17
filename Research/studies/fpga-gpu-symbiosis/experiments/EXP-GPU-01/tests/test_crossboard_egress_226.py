# -*- coding: utf-8 -*-
"""Автоматизована верифікація Issue #226 (EXP-GPU-01 Фази 1–2, 4):
1. Фізичний Place & Route та STA @ 100 МГц бітстріму pipeline_egress.bit в OpenXC7.
2. Натурна перевірка на PYNQ-Z1 (pynq2) + захват LOGICTRACER_PICO_0.5.0 @ 100 МГц.
3. Пакетування/верифікація 64-бітного кадра з CRC-8 та негативні мутантні тести (AGENTS.md §4.1).
4. Серія R = 5 x 1000 подій міжплатного контуру PYNQ-Z1 -> GbE -> Jetson AGX Orin J501
   (1024 підписники) та перевірка Попперівського критерію фальсифікації (#226).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
EXP_DIR = HERE.parent
REPO_ROOT = EXP_DIR.parents[4]
RAW_EGRESS_DIR = REPO_ROOT / "Engineering" / "validation" / "kpol-cme" / "pmod-event-egress-230" / "raw"
DATA_CB_DIR = REPO_ROOT / "Research" / "studies" / "fpga-gpu-symbiosis" / "data" / "exp-gpu-01-crossboard"
BUILD_SCRIPT = REPO_ROOT / "Engineering" / "hw" / "boards" / "pynq-z1" / "build_bram_pipeline_egress.sh"

sys.path.insert(0, str(EXP_DIR))
import crossboard_frame as cbf  # noqa: E402

EXPECTED_EGRESS_BIT_SHA256 = "7bfd5f5742334a7f08f2a290d5dde0a241e5bd06ced64c39d82e70021f30bbce"


def test_openxc7_egress_pnr_and_sta_100mhz():
    """Перевіряє скрипт збірки OpenXC7, звіт ресурсів nextpnr-himbaechel та STA >= 100 МГц."""
    assert BUILD_SCRIPT.is_file(), f"Missing {BUILD_SCRIPT}"
    script_txt = BUILD_SCRIPT.read_text(encoding="utf-8")
    for required_src in (
        "kpol_txn_gate_v2.sv",
        "km_concept_micro_engine.sv",
        "km_concept_bram.sv",
        "km_autonomous_sequencer.sv",
        "kpol_bram_pipeline_axi.sv",
        "km_pmod_event_egress.sv",
        "kpol_bram_pipeline_pynq_z1_egress_top.v",
        "kpol_bram_pipeline_egress.xdc",
    ):
        assert required_src in script_txt, f"{required_src} missing from build_bram_pipeline_egress.sh"

    yosys_log = (RAW_EGRESS_DIR / "openxc7_egress_yosys.log").read_text(encoding="utf-8")
    assert "Yosys 0.69" in yosys_log
    assert "End of script." in yosys_log

    nextpnr_log = (RAW_EGRESS_DIR / "openxc7_egress_nextpnr.log").read_text(encoding="utf-8")
    assert "Max frequency for clock 'clk': 101.67 MHz (PASS at 100.00 MHz)" in nextpnr_log
    assert "Info: Program finished normally." in nextpnr_log
    assert "ERROR:" not in nextpnr_log

    report = json.loads((RAW_EGRESS_DIR / "openxc7_egress_nextpnr_report.json").read_text(encoding="utf-8"))
    fmax_clk = report["fmax"]["clk"]
    assert fmax_clk["constraint"] == 100.0
    assert fmax_clk["achieved"] >= 100.0
    assert round(fmax_clk["achieved"], 2) == 101.67

    util = report["utilization"]
    assert util["SLICE_LUTX"]["used"] == 3630
    assert util["SLICE_FFX"]["used"] == 1524
    assert util["RAMB36E1"]["used"] == 1
    assert util["CARRY4"]["used"] == 155
    assert util["PAD"]["used"] == 26
    assert util["PS7"]["used"] == 1

    sha_txt = (RAW_EGRESS_DIR / "openxc7_egress_bitstream.sha256").read_text(encoding="utf-8").strip()
    assert sha_txt == f"{EXPECTED_EGRESS_BIT_SHA256}  pipeline_egress.bit"


def test_pynq2_silicon_cascade_and_logictracer_100mhz_capture():
    """Перевіряє живу верифікацію pipeline_egress.bit на pynq2 та захват LOGICTRACER_PICO_0.5.0 @ 100 МГц."""
    silicon_log = (RAW_EGRESS_DIR / "pynq2_egress_silicon_cascade.log").read_text(encoding="utf-8")
    assert EXPECTED_EGRESS_BIT_SHA256 in silicon_log
    assert "operating" in silicon_log
    assert "0x4B504D43 (Очікується 0x4B504D43 'KPMC')" in silicon_log
    assert "СЦЕНАРІЙ 1 УСПІХ: Повний апаратний каскад C0 -> C1 -> C2 -> C3 відпрацював у BRAM!" in silicon_log
    assert "СЦЕНАРІЙ 2 УСПІХ: Невалідний стимул відхилено кремнієм, каскад заблоковано!" in silicon_log

    lt_log = (RAW_EGRESS_DIR / "logictracer_egress_ja2_100mhz.log").read_text(encoding="utf-8")
    assert "Capture OK on /dev/ttyACM0 (LOGICTRACER_PICO_0.5.0)" in lt_log
    assert "32000 samples @ 100 MHz (320 us), trigger CH2 rising" in lt_log

    # Незалежний розрахунок ширини імпульсу JA2_COMMIT для 4-концептного каскаду:
    # 4 коміти з інтервалом 8 тактів (80 нс) + 10-тактовий розширювач (100 нс) = 3 * 80 + 100 = 340 нс
    expected_cascade_pw_ns = 3 * 80 + 100
    assert expected_cascade_pw_ns == 340
    assert f"{expected_cascade_pw_ns} ns" in lt_log

    cap_json = json.loads((DATA_CB_DIR / "logictracer_egress_ja2_100mhz.json").read_text(encoding="utf-8"))
    ch2 = cap_json["capture"]["channels"][1]
    assert ch2["name"] == "JA2_COMMIT"
    assert ch2["samples"] == 32000
    assert ch2["pulse_count_high"] == 200
    assert ch2["pulse_count_low"] == 199
    assert ch2["rising_edges"] == 200
    assert ch2["falling_edges"] == 200
    assert ch2["transitions"] == 400
    assert round(ch2["high_pulse_width_us"]["min"] * 1000.0) == expected_cascade_pw_ns
    assert round(ch2["high_pulse_width_us"]["max"] * 1000.0) == expected_cascade_pw_ns
    assert round(ch2["low_pulse_width_us"]["min"] * 1000.0) == 250
    assert (REPO_ROOT / "Engineering" / "hw" / "boards" / "pynq-z1" / "hil" / "burst_egress_trig.c").is_file()
    assert (DATA_CB_DIR / "logictracer_egress_ja2_100mhz.vcd").stat().st_size > 1000


def test_crossboard_frame_crc8_positive_and_golden_vectors():
    """Перевіряє пакування та розпакування 64-бітних кадрів проти незалежних еталонних векторів RTL."""
    # Еталонні вектори з kpol_bram_pipeline_pynq_z1_egress_top_tb.sv:
    f_spi = cbf.pack_egress_frame64(cid=2, mask16=0x0000, state=201)
    f_par = cbf.pack_egress_frame64(cid=2, mask16=0x0000, state=202)
    assert f_spi == 0x8D420000000000C9
    assert f_par == 0x84420000000000CA

    unpacked = cbf.verify_and_unpack_egress_frame64(f_spi)
    assert unpacked["crc8"] == 0x8D
    assert unpacked["tag"] == 0b01
    assert unpacked["cid"] == 2
    assert unpacked["mask16"] == 0
    assert unpacked["state"] == 201

    raw_bytes = cbf.encode_egress_frame_bytes(cid=63, mask16=0xA55A, state=0xDEADBEEF)
    assert len(raw_bytes) == 8
    unpacked_bytes = cbf.verify_and_unpack_egress_bytes(raw_bytes)
    assert unpacked_bytes["cid"] == 63
    assert unpacked_bytes["mask16"] == 0xA55A
    assert unpacked_bytes["state"] == 0xDEADBEEF


def test_crossboard_frame_crc8_negative_mutants_kill_all_corruptions():
    """Негативний мутантний контроль (AGENTS.md §4.1):
    кожен із 64 однобітових мутантів, невалідних тегів та пошкоджених поліномів має відхилятися.
    """
    valid_frame = cbf.pack_egress_frame64(cid=19, mask16=0x5AA5, state=0x13579BDF)

    # 1. Однобітові інверсії в кожному з 64 бітів кадра (включно з payload та CRC-8)
    for bit in range(64):
        corrupted = valid_frame ^ (1 << bit)
        with pytest.raises(cbf.EgressFrameError):
            cbf.verify_and_unpack_egress_frame64(corrupted)

    # 2. Мутанти тегу формату (0b00, 0b10, 0b11) навіть із перерахованим валідним CRC-8
    for bad_tag in (0b00, 0b10, 0b11):
        bad_tag_frame = cbf.pack_egress_frame64(cid=3, mask16=0x1234, state=42, tag=bad_tag)
        with pytest.raises(cbf.EgressFrameError, match="Invalid frame tag"):
            cbf.verify_and_unpack_egress_frame64(bad_tag_frame)

    # 3. Мутант полінома CRC-8 (0x05 замість 0x07)
    payload_56 = valid_frame & ((1 << 56) - 1)
    bad_crc = 0
    for bit in range(55, -1, -1):
        fb = ((bad_crc >> 7) ^ ((payload_56 >> bit) & 1)) & 1
        bad_crc = ((bad_crc << 1) & 0xFF) ^ (0x05 if fb else 0x00)
    mutant_poly_frame = (bad_crc << 56) | payload_56
    with pytest.raises(cbf.EgressFrameError, match="CRC-8 mismatch"):
        cbf.verify_and_unpack_egress_frame64(mutant_poly_frame)

    # 4. Некоректні діапазони аргументів і довжини буфера
    with pytest.raises(cbf.EgressFrameError):
        cbf.pack_egress_frame64(cid=64, mask16=0, state=0)
    with pytest.raises(cbf.EgressFrameError):
        cbf.pack_egress_frame64(cid=0, mask16=0x10000, state=0)
    with pytest.raises(cbf.EgressFrameError):
        cbf.verify_and_unpack_egress_bytes(b"\x00" * 7)


def test_crossboard_5x1000_runs_and_popper_falsification_verdict():
    """Перевіряє цілісність 5 натурних міжплатних серій (5000 подій), SHA-256 та вердикт Поппера."""
    sha_lines = (DATA_CB_DIR / "sha256sums.txt").read_text(encoding="utf-8").strip().splitlines()
    assert len(sha_lines) >= 9
    for line in sha_lines:
        exp_sha, fname = line.split()
        actual_sha = hashlib.sha256((DATA_CB_DIR / fname).read_bytes()).hexdigest()
        assert actual_sha == exp_sha, f"SHA-256 mismatch for {fname}"

    run_paths = sorted(DATA_CB_DIR.glob("crossboard_r*.json"))
    assert len(run_paths) == 5

    for rp in run_paths:
        rdata = json.loads(rp.read_text(encoding="utf-8"))
        assert rdata["events"] == 1000
        assert rdata["pl_reg_id"] == "0x4b504d43"
        assert rdata["pl_commits_delta"] == 4000  # 1000 triggers * 4 concepts in cascade
        assert rdata["neg_crc_test_rejected"] is True
        # Перевіряємо, що останній кадр у кожному прогоні має валідний CRC-8
        last_frame = int(rdata["last_frame64_hex"], 16)
        unpacked = cbf.verify_and_unpack_egress_frame64(last_frame)
        assert unpacked["cid"] == 3

        gpu_rep = rdata["jetson_gpu_report"]
        assert gpu_rep["valid_events_processed"] == 1000
        assert gpu_rep["crc_drop_count"] == 1
        assert gpu_rep["state_mismatches"] == 0
        assert gpu_rep["subscribers_verified"] == 1024
        assert gpu_rep["gpu_math_gt_ns_p50"] == 64

    recomputed = cbf.summarize_crossboard_runs(run_paths)
    recorded = json.loads((DATA_CB_DIR / "summary_crossboard_226.json").read_text(encoding="utf-8"))
    assert recomputed == recorded

    # Перевірка по-подієвої декомпозиції (F-3, F-4): сума середніх складових == середнє RTT
    mean_sum = (
        recomputed["pooled_pl_mmio_us"]["mean_us"]
        + recomputed["pooled_net_rtt_us"]["mean_us"]
        + recomputed["pooled_jetson_host_us"]["mean_us"]
    )
    assert abs(mean_sum - recomputed["pooled_rtt_us"]["mean_us"]) < 1e-3
    assert recomputed["pooled_net_oneway_est_us"]["max_us"] == 471.858
    assert recomputed["pooled_net_oneway_est_us"]["p99_9_us"] == 443.4975
    assert recomputed["pooled_rtt_net_plus_pynq_mmio_us"]["max_us"] == 945.851
    assert recomputed["pooled_jetson_host_us"]["p99_9_us"] == 2471.488

    # Перевірка Попперівського критерію фальсифікації (#226) на реальних даних GbE без PCIe
    popper_oneway = recomputed["popper_oneway_evaluation"]
    assert popper_oneway["measured_p99_9_us"] > 15.0
    assert popper_oneway["measured_sigma_us"] > 2.0
    assert popper_oneway["hypothesis_falsified"] is True
    assert popper_oneway["verdict"] == "FALSIFIED_NEEDS_PCIE_OR_DIRECT_HW_BUS"

    # Контрприклад / граничні тести функції evaluate_popper_criterion_226 (AGENTS.md §4.1)
    pass_case = cbf.evaluate_popper_criterion_226({"p99_9_us": 2.944, "sigma_us": 0.35})
    assert pass_case["hypothesis_falsified"] is False
    assert pass_case["verdict"] == "NOT_FALSIFIED_WITHIN_15US_BUDGET"

    fail_p99_only = cbf.evaluate_popper_criterion_226({"p99_9_us": 15.001, "sigma_us": 0.50})
    assert fail_p99_only["p99_9_exceeded"] is True
    assert fail_p99_only["sigma_exceeded"] is False
    assert fail_p99_only["hypothesis_falsified"] is True

    fail_sigma_only = cbf.evaluate_popper_criterion_226({"p99_9_us": 8.0, "sigma_us": 2.001})
    assert fail_sigma_only["p99_9_exceeded"] is False
    assert fail_sigma_only["sigma_exceeded"] is True
    assert fail_sigma_only["hypothesis_falsified"] is True
