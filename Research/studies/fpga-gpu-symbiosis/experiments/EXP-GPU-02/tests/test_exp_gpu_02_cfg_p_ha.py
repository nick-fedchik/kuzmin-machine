"""Automated verification suite for Issue #252 (EXP-GPU-02 Stages 1–2: dual-bank CFG-P-HA).

Evidence classes covered (honestly labeled per AGENTS.md §4.2 — NOT physical HIL):
  1. Immutability of base CFG-P RTL files and PYNQ-Z1 board directory.
  2. Positive and negative/mutant tests of `rule_injector.py` (12B/16B packets, CRC-8, AXI4-Lite encoding,
     DualBankCfgPHAModel golden reference model).
  3. Recorded 10,000-swap RTL simulation (`iverilog`), Phases 1–4 VCD protocol strobes, and comparative
     `Yosys synth_xilinx -arch xc7` synthesis logs (`CFG-P` vs `CFG-P-HA`).
  4. Live `iverilog` simulation of `kpol_bram_pipeline_axi_ha_tb.sv` + negative RTL mutant test proving
     the testbench deterministically fails on unsafe mid-event bank swap (`AGENTS.md §4.1`).
  5. Recorded Z3 formal SMT verification artifacts (`k`-induction, BMC, non-vacuity cover, 4 mutants with VCDs)
     + live Z3 `--fast` verification smoke run.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
EXP_DIR = HERE.parent
REPO_ROOT = EXP_DIR.parents[4]
HW_DIR = REPO_ROOT / "Engineering" / "hw"
RTL_CORE = HW_DIR / "rtl" / "core"
RTL_BUS = HW_DIR / "rtl" / "bus"
DATA_SIM_DIR = REPO_ROOT / "Research" / "studies" / "fpga-gpu-symbiosis" / "data" / "exp-gpu-02-sim"
FORMAL_DIR = EXP_DIR / "formal"
FORMAL_RAW_DIR = FORMAL_DIR / "raw"
CME2_PROV_PATH = (
    REPO_ROOT / "Engineering" / "validation" / "kpol-cme" / "cme2-formal-227" / "raw" / "cme2_provenance.json"
)

sys.path.insert(0, str(EXP_DIR))
import rule_injector as ri  # noqa: E402

EXPECTED_AXI_CFG_P_SHA256 = "99ccf4907785ad9e20509367ae1977fc64264cc73de4e34cc5cc71c55771a4e1"


def test_base_cfg_p_rtl_and_board_files_untouched():
    """Verifies zero byte modifications to base CFG-P RTL files pinned in #227 and PYNQ-Z1 board tree."""
    cme2_prov = json.loads(CME2_PROV_PATH.read_text(encoding="utf-8"))
    for fname in (
        "kpol_txn_gate_v2.sv",
        "km_concept_micro_engine.sv",
        "km_concept_bram.sv",
        "km_autonomous_sequencer.sv",
    ):
        actual = hashlib.sha256((RTL_CORE / fname).read_bytes()).hexdigest()
        assert actual == cme2_prov["sha256"][fname], f"Base CFG-P file {fname} was modified"

    axi_actual = hashlib.sha256((RTL_BUS / "kpol_bram_pipeline_axi.sv").read_bytes()).hexdigest()
    assert axi_actual == EXPECTED_AXI_CFG_P_SHA256, "Base kpol_bram_pipeline_axi.sv was modified"


def test_rule_injector_valid_packets_and_axi_encoding():
    """Checks 12-byte (W1..W3) and 16-byte (W0..W3) rule packets, CRC-8, CLI, and AXI4-Lite encoding."""
    patch_12b = ri.RuleDescriptorPatch.threshold_ge(cid=5, threshold=40)
    pkt_12b = ri.build_rule_packet(patch_12b)
    assert len(pkt_12b) == 16  # 4B header + 12B W1..W3 payload
    assert pkt_12b[0] == ri.PACKET_MAGIC
    assert pkt_12b[1] == ri.PACKET_MODE_RULES_12B
    assert pkt_12b[2] == 5

    unpacked_12b = ri.verify_and_unpack_packet(pkt_12b)
    assert unpacked_12b == patch_12b

    txns_12b = ri.encode_axi_ha_transactions(pkt_12b, issue_swap=True)
    assert [(t.addr, t.data) for t in txns_12b] == [
        (0x030, 5 * 4 + 1),
        (0x034, 40),
        (0x034, 0x01000B04),
        (0x034, 0xFFFFFFFF),
        (0x038, 1),
    ]

    patch_16b = ri.RuleDescriptorPatch.threshold_ge(cid=5, threshold=-25, init_state_w0=77)
    pkt_16b = ri.build_rule_packet(patch_16b)
    assert len(pkt_16b) == 20  # 4B header + 16B W0..W3 payload
    assert pkt_16b[1] == ri.PACKET_MODE_FULL_16B
    unpacked_16b = ri.verify_and_unpack_packet(pkt_16b)
    assert unpacked_16b == patch_16b

    txns_16b = ri.encode_axi_ha_transactions(pkt_16b, issue_swap=False)
    assert [t.addr for t in txns_16b] == [0x030, 0x034, 0x034, 0x034, 0x034]
    assert txns_16b[0].data == 20
    assert txns_16b[1].data == 77

    cli_res = subprocess.run(
        [sys.executable, str(EXP_DIR / "rule_injector.py"), "--cid", "5", "--threshold-ge", "40"],
        capture_output=True,
        text=True,
        check=True,
    )
    cli_json = json.loads(cli_res.stdout)
    assert cli_json["cid"] == 5
    assert cli_json["payload_len_bytes"] == 12
    assert len(cli_json["axi_transactions"]) == 5


def test_rule_injector_rejects_corrupted_crc8_and_invalid_mutants():
    """Negative/mutant controls (AGENTS.md §4.1): every single-bit corruption or invalid opcode is rejected."""
    valid_pkt = bytearray(ri.build_rule_packet(ri.RuleDescriptorPatch.threshold_ge(cid=5, threshold=40)))

    # Flip 1 bit in every byte position across header + CRC + payload
    for byte_idx in range(len(valid_pkt)):
        for bit_idx in (0, 3, 7):
            mutated = bytearray(valid_pkt)
            mutated[byte_idx] ^= 1 << bit_idx
            with pytest.raises(ri.RulePacketError):
                ri.verify_and_unpack_packet(bytes(mutated))

    # Truncated and oversized frames
    with pytest.raises(ri.RulePacketError):
        ri.verify_and_unpack_packet(bytes(valid_pkt[:-1]))
    with pytest.raises(ri.RulePacketError):
        ri.verify_and_unpack_packet(bytes(valid_pkt) + b"\x00")

    # Invalid CID, pred_opcode, action_opcode, reserved guard bits (even if re-signed with valid CRC-8!)
    invalid_patches = [
        ri.RuleDescriptorPatch(cid=64, operand_val=10, pred_opcode=ri.PRED_LT, guard_flags=0x0B),
        ri.RuleDescriptorPatch(cid=-1, operand_val=10, pred_opcode=ri.PRED_LT, guard_flags=0x0B),
        ri.RuleDescriptorPatch(cid=3, operand_val=10, pred_opcode=0x07, guard_flags=0x0B),
        ri.RuleDescriptorPatch(cid=3, operand_val=10, pred_opcode=ri.PRED_LT, guard_flags=0x0B, action_opcode=0x05),
        ri.RuleDescriptorPatch(cid=3, operand_val=10, pred_opcode=ri.PRED_LT, guard_flags=0x23),
    ]
    for bad_patch in invalid_patches:
        with pytest.raises(ri.RulePacketError):
            ri.build_rule_packet(bad_patch)

    # Craft a raw frame with valid CRC-8 but illegal action_opcode=0x09 -> must still fail validation
    bad_w2 = (0x09 << 24) | (0x03 << 8) | ri.PRED_NOP
    raw_payload = ri.struct.pack("<III", 40, bad_w2, 0xFFFFFFFF)
    prefix = bytes((ri.PACKET_MAGIC, ri.PACKET_MODE_RULES_12B, 5))
    forged_frame = prefix + bytes((ri.crc8_ccitt(prefix + raw_payload),)) + raw_payload
    with pytest.raises(ri.RulePacketError, match="unsupported action_opcode"):
        ri.verify_and_unpack_packet(forged_frame)


def test_dual_bank_reference_model_protocol_phases_and_w0_preservation():
    """Verifies software golden model on EXP-GPU-02 Phases 1–4 (CID=5: X>=100 -> X>=40) and W0 override."""
    model = ri.DualBankCfgPHAModel(num_concepts=64)
    model.sync_load_concept(ri.RuleDescriptorPatch.threshold_ge(cid=5, threshold=100, init_state_w0=0))

    # Phase 1: X=50 rejects, X=120 commits
    assert model.step_event(5, 50) is False
    assert model.get_active_w0(5) == 0
    assert model.step_event(5, 120) is True
    assert model.get_active_w0(5) == 1

    # Phase 2: Hot inject X>=40 into shadow bank while Bank 0 continues processing events
    pkt_new = ri.build_rule_packet(ri.RuleDescriptorPatch.threshold_ge(cid=5, threshold=40))
    model.inject_shadow_packet(pkt_new)
    assert model.step_event(5, 50) is False  # Still old rule X>=100 before swap!
    assert model.step_event(5, 120) is True  # Live W0 increments to 2 in both banks!
    assert model.get_active_w0(5) == 2

    # Atomic bank swap + resync
    model.commit_bank_swap_and_resync(finish_resync=True)
    assert model.active_bank == 1
    assert model.get_active_w0(5) == 2
    assert model.bank0 == model.bank1

    # Phase 4: X=50 now commits immediately and increments preserved live W0 (2 -> 3)
    assert model.step_event(5, 50) is True
    assert model.get_active_w0(5) == 3

    # Explicit 16-byte W0 override protects staged W0 from pre-swap Port B commits
    pkt_override = ri.build_rule_packet(
        ri.RuleDescriptorPatch.threshold_ge(cid=5, threshold=40, init_state_w0=500)
    )
    model.inject_shadow_packet(pkt_override)
    assert model.step_event(5, 60) is True  # Old active bank becomes 4, shadow bank stays 500
    assert model.get_active_w0(5) == 4
    model.commit_bank_swap_and_resync(finish_resync=True)
    assert model.get_active_w0(5) == 500
    assert model.bank0 == model.bank1


def test_committed_10k_rtl_simulation_and_yosys_xc7_synthesis_artifacts():
    """Checks recorded 10,000-swap RTL simulation artifacts and Yosys XC7 synthesis logs."""
    summary_path = DATA_SIM_DIR / "exp_gpu_02_sim_10k_swaps_summary.json"
    vcd_path = DATA_SIM_DIR / "exp_gpu_02_sim_phases1_4.vcd"
    csv_path = DATA_SIM_DIR / "exp_gpu_02_sim_timing.csv"
    sim_log = DATA_SIM_DIR / "iverilog_10k_swaps.log"
    synth_log = DATA_SIM_DIR / "yosys_xc7_cfg_p_ha.log"

    for p in (summary_path, vcd_path, csv_path, sim_log, synth_log):
        assert p.is_file(), f"Missing artifact: {p}"

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["evidence_kind"] == "rtl_simulation_iverilog"
    assert summary["not_physical_hil"] is True
    assert summary["verdict"] == "PASS"
    assert summary["stress_swaps"] >= 10000
    assert summary["total_bank_swaps"] >= 10003
    assert summary["torn_read_errors"] == 0
    assert summary["golden_mismatch_count"] == 0
    assert summary["seq_stall_anomaly_count"] == 0
    assert summary["bram_collision_count"] == 0
    assert summary["ready_drop_on_shadow_count"] == 0
    assert summary["events_dropped_count"] == 0
    assert summary["last_seq_exec_cycles"] == 8
    assert summary["stress_swap_wait_min_cycles"] == 1
    assert summary["stress_swap_wait_max_cycles"] == 8
    for k in map(str, range(1, 9)):
        assert summary["stress_swap_wait_histogram_cycles"][k] > 0

    vcd_text = vcd_path.read_text(encoding="utf-8")
    for sig in ("INJECT_STROBE", "BANK_SWAP_COMMIT", "STIMULUS_EVENT", "REACTION_OUT", "SEQ_CYCLE_DONE"):
        assert sig in vcd_text, f"Missing protocol strobe {sig} in VCD"

    with csv_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) >= 25
    assert all(r["evidence_kind"] == "rtl_simulation_iverilog" for r in rows)
    assert all(int(r["seq_anomaly_count"]) == 0 for r in rows)
    assert all(int(r["last_seq_exec_cycles"]) == 8 for r in rows)

    for log_path in (sim_log, synth_log):
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("# cmd: ")
        assert lines[1].startswith("# timestamp: ")

    synth_txt = synth_log.read_text(encoding="utf-8")
    assert "RAMB36E1                        1" in synth_txt
    assert "RAMB36E1                        2" in synth_txt
    assert "Estimated number of LCs:       1750" in synth_txt
    assert "Estimated number of LCs:       3867" in synth_txt


@pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="Потрібні iverilog і vvp",
)
def test_live_iverilog_rtl_simulation_and_unsafe_swap_mutant(tmp_path):
    """Runs live Icarus Verilog simulation on CFG-P-HA AND verifies a torn-read mutant fails."""
    rtl_sources = [
        RTL_CORE / "kpol_txn_gate_v2.sv",
        RTL_CORE / "km_concept_micro_engine.sv",
        RTL_CORE / "km_concept_bram.sv",
        RTL_CORE / "km_concept_bram_dual_ha.sv",
        RTL_CORE / "km_autonomous_sequencer.sv",
        RTL_BUS / "kpol_bram_pipeline_axi_ha.sv",
        HW_DIR / "tests" / "kpol_bram_pipeline_axi_ha_tb.sv",
    ]
    sim_ok = tmp_path / "cfg_p_ha_ok.vvp"
    subprocess.run(
        ["iverilog", "-g2012", "-s", "kpol_bram_pipeline_axi_ha_tb", "-o", str(sim_ok), *map(str, rtl_sources)],
        check=True,
        capture_output=True,
        text=True,
    )
    sum_json = tmp_path / "live_summary.json"
    run_ok = subprocess.run(
        ["vvp", "-n", str(sim_ok), "+num_swaps=200", f"+summary_json={sum_json}"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run_ok.returncode == 0, run_ok.stdout + run_ok.stderr
    assert "PASS: CFG-P-HA EXP-GPU-02 Phases 1-4 and 200 hot bank swaps verified" in run_ok.stdout
    live_data = json.loads(sum_json.read_text(encoding="utf-8"))
    assert live_data["torn_read_errors"] == 0
    assert live_data["seq_stall_anomaly_count"] == 0

    # Negative mutant control (AGENTS.md §4.1): immediate swap mid-event without ST_IDLE guard must fail TB
    dual_src = (RTL_CORE / "km_concept_bram_dual_ha.sv").read_text(encoding="utf-8")
    old_line = "    wire swap_commit_w     = (swap_pending_q || swap_req_accept) && seq_at_idle_boundary_i;"
    assert dual_src.count(old_line) == 1
    mutant_dual = tmp_path / "mutant_dual_ha.sv"
    mutant_dual.write_text(
        dual_src.replace(old_line, "    wire swap_commit_w     = (swap_pending_q || swap_req_accept);"),
        encoding="utf-8",
    )
    mut_sources = [mutant_dual if p.name == "km_concept_bram_dual_ha.sv" else p for p in rtl_sources]
    sim_mut = tmp_path / "cfg_p_ha_mut.vvp"
    subprocess.run(
        ["iverilog", "-g2012", "-s", "kpol_bram_pipeline_axi_ha_tb", "-o", str(sim_mut), *map(str, mut_sources)],
        check=True,
        capture_output=True,
        text=True,
    )
    run_mut = subprocess.run(
        ["vvp", "-n", str(sim_mut), "+num_swaps=200"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    combined_mut = run_mut.stdout + run_mut.stderr
    assert run_mut.returncode != 0 or "[FAIL]" in combined_mut, (
        "Mutant unsafe immediate swap was NOT caught by kpol_bram_pipeline_axi_ha_tb.sv"
    )
    assert "[FAIL]" in combined_mut


def test_committed_formal_smt_z3_artifacts():
    """Verifies committed Z3 formal SMT proof artifacts, zero vacuous assumes, and mutant VCDs."""
    prov_path = FORMAL_RAW_DIR / "cfg_p_ha_formal_provenance.json"
    csv_path = FORMAL_RAW_DIR / "cfg_p_ha_formal_results.csv"
    props_path = FORMAL_DIR / "cfg_p_ha_formal_props.sv"

    assert prov_path.is_file()
    assert csv_path.is_file()

    # R1 guard: FORMAL_INDUCTION block must contain zero assume statements
    props_src = props_path.read_text(encoding="utf-8")
    ind_block = props_src.split("`ifdef FORMAL_INDUCTION", 1)[1].split("`endif", 1)[0]
    for line in ind_block.splitlines():
        stripped = line.split("//", 1)[0].strip()
        assert "assume" not in stripped, f"Prohibited assume inside FORMAL_INDUCTION: {line}"

    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    assert prov["issue"] == 252
    assert prov["verdict"] == "PASSED"
    assert prov["parameters"] == {
        "NUM_CONCEPTS": 4,
        "QUEUE_DEPTH": 4,
        "DATA_WIDTH": 32,
        "ADDR_WIDTH": 4,
    }

    expected_paths = {
        "kpol_txn_gate_v2.sv": RTL_CORE / "kpol_txn_gate_v2.sv",
        "km_concept_micro_engine.sv": RTL_CORE / "km_concept_micro_engine.sv",
        "km_concept_bram.sv": RTL_CORE / "km_concept_bram.sv",
        "km_concept_bram_dual_ha.sv": RTL_CORE / "km_concept_bram_dual_ha.sv",
        "km_autonomous_sequencer.sv": RTL_CORE / "km_autonomous_sequencer.sv",
        "kpol_bram_pipeline_axi_ha.sv": RTL_BUS / "kpol_bram_pipeline_axi_ha.sv",
        "cfg_p_ha_formal_props.sv": props_path,
    }
    for fname, fpath in expected_paths.items():
        actual_sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
        assert prov["sha256"][fname] == actual_sha, f"SHA-256 mismatch for {fname}"

    with csv_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_check = {r["check"]: r for r in rows if r["design"].startswith("original")}
    for req_check in (
        "H1_H6_base_bmc",
        "H1_H6_safety_ind",
        "H1_H2_H4_H5_safety_bmc",
        "H2_H3_safety_bmc",
        "cover_non_vacuity",
    ):
        assert by_check[req_check]["status"] == "PASSED"

    reached = set(by_check["cover_non_vacuity"]["reached"].split(";"))
    assert {
        "C1_full_online_update_lifecycle",
        "C2_swap_after_pending_wait",
        "C3_back_to_back_events_across_swap",
    } <= reached

    by_mut = {r["design"].split(":")[0]: r for r in rows if not r["design"].startswith("original")}
    expected_mutants = {
        "M1_unsafe_immediate_swap": "H3_no_torn_descriptor_read",
        "M2_write_active_bank_while_busy": "H3_no_torn_descriptor_read",
        "M3_drop_w0_mirror": "H6_live_state_preserved",
        "M4_block_trigger_on_shadow": "H4_zero_sequencer_stall",
    }
    for mid, expected_prop in expected_mutants.items():
        row = by_mut[mid]
        assert row["status"] == "FAILED"
        assert expected_prop in row["failed"]
        assert row["vcd"]
        vcd_file = FORMAL_RAW_DIR / row["vcd"]
        assert vcd_file.is_file() and vcd_file.stat().st_size > 0

    for log_file in FORMAL_RAW_DIR.glob("*.log"):
        lines = log_file.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("# cmd: "), f"Missing # cmd header in {log_file.name}"
        assert lines[1].startswith("# timestamp: "), f"Missing # timestamp header in {log_file.name}"


@pytest.mark.skipif(
    shutil.which("yosys") is None
    or shutil.which("yosys-smtbmc") is None
    or shutil.which("z3") is None,
    reason="Потрібні yosys, yosys-smtbmc і z3",
)
def test_live_formal_smt_z3_induction_and_mutants(tmp_path):
    """Runs live Z3 unbounded k-induction + all 4 mutant negative controls in --fast mode."""
    res = subprocess.run(
        [sys.executable, str(FORMAL_DIR / "run_cfg_p_ha_formal.py"), "--out-dir", str(tmp_path), "--fast"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "VERDICT: PASSED" in res.stdout

    prov = json.loads((tmp_path / "cfg_p_ha_formal_provenance.json").read_text(encoding="utf-8"))
    assert prov["verdict"] == "PASSED"
    for mid in (
        "M1_unsafe_immediate_swap",
        "M2_write_active_bank_while_busy",
        "M3_drop_w0_mirror",
        "M4_block_trigger_on_shadow",
    ):
        assert (tmp_path / f"{mid}.vcd").is_file()
