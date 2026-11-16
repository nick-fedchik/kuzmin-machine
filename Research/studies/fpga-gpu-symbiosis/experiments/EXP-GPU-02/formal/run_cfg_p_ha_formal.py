#!/usr/bin/env python3
"""Issue #252 (EXP-GPU-02): Formal SMT verification of dual-bank CFG-P-HA via Yosys + Z3.

Proves on parameterized top-level `kpol_bram_pipeline_axi_ha`
(NUM_CONCEPTS=4, QUEUE_DEPTH=4, DATA_WIDTH=32, ADDR_WIDTH=4) with zero vacuous
assumptions on internal states:
  * Unbounded k-induction (`yosys-smtbmc -s z3 -i -t 8`):
      H1_lockstep_phase, H2_zero_bram_collision, H3_no_torn_descriptor_read,
      H4_zero_sequencer_stall, H5_bounded_swap_latency, H6_live_state_preserved.
  * Bounded Model Checking (`yosys-smtbmc -s z3 -t 30`):
      Full 30-step reachable check of H1..H6 + H6b_banks_identical_after_resync.
  * Cover non-vacuity (`yosys-smtbmc -s z3 -c -t 36`):
      Full online rule injection lifecycle (old rule reject -> hot shadow write
      while sequencer active -> atomic bank_swap_commit_o -> background resync
      completion -> new rule commit) + pending wait + back-to-back zero-bubble swap.
  * Mutant negative controls (AGENTS.md §4.1) with counterexample VCDs:
      - M1_unsafe_immediate_swap       -> caught by H3_no_torn_descriptor_read
      - M2_write_active_bank_while_busy -> caught by H2_zero_bram_collision / H3_no_torn_descriptor_read
      - M3_drop_w0_mirror              -> caught by H6_live_state_preserved
      - M4_block_trigger_on_shadow     -> caught by H4_zero_sequencer_stall
"""

import argparse
import csv
import datetime
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", "..", ".."))
RTL_CORE = os.path.join(REPO_ROOT, "Engineering", "hw", "rtl", "core")
RTL_BUS = os.path.join(REPO_ROOT, "Engineering", "hw", "rtl", "bus")

RTL_GATE = os.path.join(RTL_CORE, "kpol_txn_gate_v2.sv")
RTL_CME = os.path.join(RTL_CORE, "km_concept_micro_engine.sv")
RTL_BRAM = os.path.join(RTL_CORE, "km_concept_bram.sv")
RTL_DUAL = os.path.join(RTL_CORE, "km_concept_bram_dual_ha.sv")
RTL_SEQ = os.path.join(RTL_CORE, "km_autonomous_sequencer.sv")
RTL_AXI_HA = os.path.join(RTL_BUS, "kpol_bram_pipeline_axi_ha.sv")
PROPS = os.path.join(HERE, "cfg_p_ha_formal_props.sv")
DEFAULT_OUT = os.path.join(HERE, "raw")

CORE_CONNECTS = [
    "cd cfg_p_ha_formal_props",
    "connect -set obs_state_q \\dut.sequencer.state_q",
    "connect -set obs_cme_event_valid \\dut.sequencer.cme_event_valid",
    "connect -set obs_active_cid_q \\dut.sequencer.active_cid_q",
    "connect -set obs_desc_w0_q \\dut.sequencer.desc_w0_q",
    "connect -set obs_desc_w1_q \\dut.sequencer.desc_w1_q",
    "connect -set obs_desc_w2_q \\dut.sequencer.desc_w2_q",
    "connect -set obs_desc_w3_q \\dut.sequencer.desc_w3_q",
    "connect -set obs_b_addr \\dut.b_addr",
    "connect -set obs_active_bank \\dut.active_bank",
    "connect -set obs_swap_pending \\dut.swap_pending",
    "connect -set obs_sync_busy \\dut.sync_busy",
    "connect -set obs_collision_detected \\dut.collision_detected",
    "connect -set obs_bank0_col \\dut.bram_dual.bank0.collision_q",
    "connect -set obs_bank1_col \\dut.bram_dual.bank1.collision_q",
    "connect -set obs_bank0_a_we \\dut.bram_dual.bank0_a_we",
    "connect -set obs_bank0_b_we \\dut.bram_dual.bank0_b_we",
    "connect -set obs_bank0_a_addr \\dut.bram_dual.bank0_a_addr",
    "connect -set obs_bank1_a_we \\dut.bram_dual.bank1_a_we",
    "connect -set obs_bank1_b_we \\dut.bram_dual.bank1_b_we",
    "connect -set obs_bank1_a_addr \\dut.bram_dual.bank1_a_addr",
]
for _i in range(16):
    CORE_CONNECTS.append(f"connect -set obs_b0_ram_{_i} \\dut.bram_dual.bank0.ram[{_i}]")
    CORE_CONNECTS.append(f"connect -set obs_b1_ram_{_i} \\dut.bram_dual.bank1.ram[{_i}]")

SAFETY_EXTRA_CONNECTS = [
    "connect -set obs_seq_phase_q \\dut.seq_phase_q",
    "connect -set obs_seq_busy \\dut.seq_busy",
    "connect -set obs_seq_trigger_ready \\dut.seq_trigger_ready",
    "connect -set obs_sw_trigger \\dut.sw_trigger",
    "connect -set obs_bram_we \\dut.bram_we",
    "connect -set obs_cfg_write_fire \\dut.cfg_write_fire",
    "connect -set obs_b_wdata \\dut.b_wdata",
    "connect -set obs_b_we \\dut.b_we",
    "connect -set obs_dual_a_addr \\dut.dual_a_addr",
    "connect -set obs_dual_a_wdata \\dut.dual_a_wdata",
    "connect -set obs_sync_load_accept \\dut.bram_dual.sync_load_accept",
    "connect -set obs_hot_write_accept \\dut.bram_dual.hot_write_accept",
    "connect -set obs_swap_req_accept \\dut.bram_dual.swap_req_accept",
    "connect -set obs_swap_commit_w \\dut.bram_dual.swap_commit_w",
    "connect -set obs_last_swap_wait_cycles_q \\dut.last_swap_wait_cycles_q",
    "connect -set obs_last_seq_exec_cycles_q \\dut.last_seq_exec_cycles_q",
    "connect -set obs_seq_anomaly_count_q \\dut.seq_anomaly_count_q",
]

IND_EXTRA_CONNECTS = [
    "connect -set obs_shadow_we \\dut.shadow_we",
    "connect -set obs_b_wstrb \\dut.b_wstrb",
    "connect -set obs_dirty_word_q \\dut.bram_dual.dirty_word_q",
    "connect -set obs_fifo_count_q \\dut.sequencer.fifo_count_q",
    "connect -set obs_fifo_wr_ptr_q \\dut.sequencer.fifo_wr_ptr_q",
    "connect -set obs_fifo_rd_ptr_q \\dut.sequencer.fifo_rd_ptr_q",
    "connect -set obs_cascade_pending_valid_q \\dut.sequencer.cascade_pending_valid_q",
    "connect -set obs_cme_committed \\dut.sequencer.cme_committed",
    "connect -set obs_sync_state_q \\dut.bram_dual.sync_state_q",
    "connect -set obs_sync_addr_q \\dut.bram_dual.sync_addr_q",
    "connect -set obs_shadow_w0_override_q \\dut.bram_dual.shadow_w0_override_q",
    "connect -set obs_bank0_a_rdata \\dut.bram_dual.bank0_a_rdata",
    "connect -set obs_bank1_a_rdata \\dut.bram_dual.bank1_a_rdata",
    "connect -set obs_bank0_b_rdata \\dut.bram_dual.bank0_b_rdata",
    "connect -set obs_bank1_b_rdata \\dut.bram_dual.bank1_b_rdata",
    "connect -set obs_swap_wait_cur_q \\dut.swap_wait_cur_q",
    "connect -set obs_seq_exec_cur_q \\dut.seq_exec_cur_q",
]

MUTANTS = [
    (
        "M1_unsafe_immediate_swap",
        "dual",
        ["FORMAL_SAFETY", "ONLY_H2_H3"],
        18,
        "immediate bank swap on swap_req_i without waiting for seq_at_idle_boundary_i",
        "    wire swap_commit_w     = (swap_pending_q || swap_req_accept) && seq_at_idle_boundary_i;",
        "    wire swap_commit_w     = (swap_pending_q || swap_req_accept);",
    ),
    (
        "M2_write_active_bank_while_busy",
        "dual",
        ["FORMAL_SAFETY", "ONLY_H2_H3"],
        16,
        "hot write routed into active_bank_q instead of shadow bank ~active_bank_q",
        "    wire [ADDR_WIDTH-1:0] bank0_a_addr  = active_bank_q ? sh_a_addr_w  : act_a_addr_w;\n"
        "    wire [DATA_WIDTH-1:0] bank0_a_wdata = active_bank_q ? sh_a_wdata_w : act_a_wdata_w;\n"
        "    wire [3:0]            bank0_a_wstrb = active_bank_q ? sh_a_wstrb_w : act_a_wstrb_w;\n"
        "    wire                  bank0_a_we    = active_bank_q ? sh_a_we_w    : act_a_we_w;\n"
        "    wire                  bank0_b_we    = active_bank_q ? sh_b_we_w    : act_b_we_w;\n\n"
        "    wire [ADDR_WIDTH-1:0] bank1_a_addr  = active_bank_q ? act_a_addr_w  : sh_a_addr_w;\n"
        "    wire [DATA_WIDTH-1:0] bank1_a_wdata = active_bank_q ? act_a_wdata_w : sh_a_wdata_w;\n"
        "    wire [3:0]            bank1_a_wstrb = active_bank_q ? act_a_wstrb_w : sh_a_wstrb_w;\n"
        "    wire                  bank1_a_we    = active_bank_q ? act_a_we_w    : sh_a_we_w;",
        "    wire [ADDR_WIDTH-1:0] bank0_a_addr  = active_bank_q ? act_a_addr_w  : sh_a_addr_w;\n"
        "    wire [DATA_WIDTH-1:0] bank0_a_wdata = active_bank_q ? act_a_wdata_w : sh_a_wdata_w;\n"
        "    wire [3:0]            bank0_a_wstrb = active_bank_q ? act_a_wstrb_w : sh_a_wstrb_w;\n"
        "    wire                  bank0_a_we    = active_bank_q ? act_a_we_w    : sh_a_we_w;\n"
        "    wire                  bank0_b_we    = active_bank_q ? sh_b_we_w    : act_b_we_w;\n\n"
        "    wire [ADDR_WIDTH-1:0] bank1_a_addr  = active_bank_q ? sh_a_addr_w   : act_a_addr_w;\n"
        "    wire [DATA_WIDTH-1:0] bank1_a_wdata = active_bank_q ? sh_a_wdata_w  : act_a_wdata_w;\n"
        "    wire [3:0]            bank1_a_wstrb = active_bank_q ? sh_a_wstrb_w  : act_a_wstrb_w;\n"
        "    wire                  bank1_a_we    = active_bank_q ? sh_a_we_w     : act_a_we_w;",
    ),
    (
        "M3_drop_w0_mirror",
        "dual",
        ["FORMAL_SAFETY", "ONLY_H6"],
        20,
        "disabled Port B W0 mirroring into shadow bank loses live state across swap",
        "    wire sh_b_we_w  = b_we_i && !((b_addr_i[1:0] == 2'b00) && shadow_w0_override_q[b_cid_w]) &&\n"
        "                      !(sh_a_we_w && (sh_a_addr_w == b_addr_i));",
        "    wire sh_b_we_w  = 1'b0;",
    ),
    (
        "M4_block_trigger_on_shadow",
        "axi_ha",
        ["FORMAL_SAFETY"],
        10,
        "shadow_we erroneously blocks external hw_trigger_ready_o during online rule update",
        "    wire ext_trigger_blocked   = sw_trigger || bram_we || cfg_write_fire;",
        "    wire ext_trigger_blocked   = sw_trigger || bram_we || shadow_we || cfg_write_fire;",
    ),
]


def clean_lines(text):
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


def write_log(log_path, cmd, text):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    ts = datetime.datetime.now().astimezone().isoformat()
    header = f"# cmd: {' '.join(cmd)}\n# timestamp: {ts}\n"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(clean_lines(header + text))


def sh(cmd, cwd, log_path=None):
    t0 = time.time()
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    dt = time.time() - t0
    out = (p.stdout or "") + (p.stderr or "")
    if log_path:
        write_log(log_path, cmd, out)
    return p.returncode, out, dt


def build_smt2(work, out_dir, dual_path, axi_ha_path, defines, tag, use_stbv=False, cut_cme=False, slice_1bit=False):
    smt2 = os.path.join(work, f"{tag}.smt2")
    ys = os.path.join(work, f"{tag}.ys")
    def_flags = " ".join(f"-D{d}" for d in defines)
    if "ONLY_CTRL" in defines:
        all_conns = [
            "cd cfg_p_ha_formal_props",
            "connect -set obs_seq_phase_q \\dut.seq_phase_q",
            "connect -set obs_state_q \\dut.sequencer.state_q",
            "connect -set obs_seq_busy \\dut.seq_busy",
            "connect -set obs_seq_trigger_ready \\dut.seq_trigger_ready",
            "connect -set obs_sw_trigger \\dut.sw_trigger",
            "connect -set obs_bram_we \\dut.bram_we",
            "connect -set obs_cfg_write_fire \\dut.cfg_write_fire",
            "connect -set obs_b_addr \\dut.b_addr",
            "connect -set obs_swap_pending \\dut.swap_pending",
            "connect -set obs_collision_detected \\dut.collision_detected",
            "connect -set obs_bank0_col \\dut.bram_dual.bank0.collision_q",
            "connect -set obs_bank1_col \\dut.bram_dual.bank1.collision_q",
            "connect -set obs_bank0_a_we \\dut.bram_dual.bank0_a_we",
            "connect -set obs_bank0_b_we \\dut.bram_dual.bank0_b_we",
            "connect -set obs_bank0_a_addr \\dut.bram_dual.bank0_a_addr",
            "connect -set obs_bank1_a_we \\dut.bram_dual.bank1_a_we",
            "connect -set obs_bank1_b_we \\dut.bram_dual.bank1_b_we",
            "connect -set obs_bank1_a_addr \\dut.bram_dual.bank1_a_addr",
            "connect -set obs_swap_req_accept \\dut.bram_dual.swap_req_accept",
            "connect -set obs_last_swap_wait_cycles_q \\dut.last_swap_wait_cycles_q",
            "connect -set obs_last_seq_exec_cycles_q \\dut.last_seq_exec_cycles_q",
            "connect -set obs_seq_anomaly_count_q \\dut.seq_anomaly_count_q",
        ]
    else:
        all_conns = list(CORE_CONNECTS)
        if "FORMAL_SAFETY" in defines and "ONLY_H2_H3" not in defines:
            all_conns.extend(SAFETY_EXTRA_CONNECTS)
        if "FORMAL_INDUCTION" in defines:
            all_conns.extend(IND_EXTRA_CONNECTS)

    non_ram_conns = [c.replace("connect -set ", "connect -nomap -set ") for c in all_conns if "ram[" not in c]
    non_ram_conns.append("cd ..")
    ram_items = [c.replace("connect -set ", "connect -nomap -set ") for c in all_conns if "ram[" in c]
    ram_lines = ("cd cfg_p_ha_formal_props\n" + "\n".join(ram_items) + "\ncd ..\n") if ram_items else ""

    non_ram_lines = "\n".join(non_ram_conns)
    cut_block = (
        "cd cfg_p_ha_formal_props\n"
        "cutpoint \\dut.sequencer.cme_committed \\dut.sequencer.cascade_req "
        "\\dut.sequencer.cascade_cid \\dut.sequencer.cascade_param "
        "\\dut.sequencer.cme_inst.gate_state_out\n"
        "cd ..\n"
        if cut_cme
        else ""
    )
    if slice_1bit:
        post_block = (
            "setattr -unset keep\n"
            "async2sync\n"
            "chformal -assume -early\n"
            "dffunmap\n"
            "simplemap\n"
            "splitnets\n"
            "splitcells\n"
            "select -set nonports w:* x:* %d\n"
            "rename -hide @nonports\n"
            "select -clear\n"
            "abc -fast\n"
            "opt_clean -purge\n"
            f"write_smt2 -stbv {smt2}\n"
        )
    else:
        smt_flags = "-stbv" if use_stbv else "-wires"
        check_cmd = "" if cut_cme else "check -assert\n"
        post_block = (
            "setattr -unset keep\n"
            "opt -fast\n"
            f"{check_cmd}"
            "async2sync\n"
            "chformal -assume -early\n"
            "opt_clean -purge\n"
            "opt -fast\n"
            "dffunmap\n"
            f"write_smt2 {smt_flags} {smt2}\n"
        )

    script = (
        f"read_verilog -sv -formal {def_flags} "
        f"{RTL_GATE} {RTL_CME} {RTL_BRAM} {dual_path} {RTL_SEQ} {axi_ha_path} {PROPS}\n"
        "hierarchy -check -top cfg_p_ha_formal_props\n"
        "proc\n"
        "flatten\n"
        f"{non_ram_lines}\n"
        "prep -top cfg_p_ha_formal_props\n"
        "memory_map\n"
        f"{ram_lines}"
        f"{cut_block}"
        f"{post_block}"
    )
    with open(ys, "w", encoding="utf-8") as f:
        f.write(script)
    rc, log, _ = sh(["yosys", "-q", ys], work, os.path.join(out_dir, f"{tag}.yosys.log"))
    if rc != 0:
        raise RuntimeError(f"yosys failed for {tag}:\n{log}")
    return smt2


def run_smtbmc(
    work,
    out_dir,
    dual_path,
    axi_ha_path,
    defines,
    mode,
    depth,
    tag,
    keep_vcd=False,
    batch_qfbv=False,
    cut_cme=False,
    slice_1bit=False,
):
    smt2 = build_smt2(
        work,
        out_dir,
        dual_path,
        axi_ha_path,
        defines,
        tag,
        use_stbv=batch_qfbv,
        cut_cme=cut_cme,
        slice_1bit=slice_1bit,
    )
    vcd = os.path.join(out_dir, f"{tag}.vcd")
    cmd = ["yosys-smtbmc", "--noprogress", "-s", "z3"]
    if batch_qfbv:
        cmd += ["--noincr", "-S", "tactic.default_tactic=qfbv", "-t", f"0:{depth}:{depth}"]
    elif mode == "ind":
        cmd += ["-i", "-t", str(depth)]
    elif mode == "cover":
        cmd += ["-c", "-t", str(depth)]
    else:
        cmd += ["-t", str(depth)]
        if keep_vcd:
            cmd += ["--dump-vcd", vcd]
    cmd.append(smt2)

    rc, out, dt = sh(cmd, work, os.path.join(out_dir, f"{tag}.log"))
    m = re.findall(r"Status: (\w+)", out)
    status = m[-1] if m else "ERROR"
    if not keep_vcd and os.path.exists(vcd):
        os.remove(vcd)
    return {
        "engine": f"smtbmc z3 {mode} t={depth}",
        "status": status,
        "seconds": round(dt, 3),
        "failed": ";".join(sorted(set(re.findall(r"Assert failed in \S+: (\w+)", out)))),
        "reached": ";".join(sorted(set(re.findall(r"Reached cover statement .*: (\w+)", out)))),
        "unreached": ";".join(sorted(set(re.findall(r"Unreached cover statement .*: (\w+)", out)))),
        "vcd": os.path.basename(vcd) if (keep_vcd and os.path.exists(vcd)) else "",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument(
        "--fast",
        action="store_true",
        help="Run fast smoke subset (unbounded k-induction + all 4 mutants, skip 30-step BMC/cover)",
    )
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    work = os.path.join(out_dir, "_work")
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work, exist_ok=True)

    with open(RTL_DUAL, "r", encoding="utf-8") as f:
        dual_src = f.read()
    with open(RTL_AXI_HA, "r", encoding="utf-8") as f:
        axi_ha_src = f.read()

    rows = []
    try:
        # 1a. Induction base case BMC (t=3) + 1b. Unbounded k-induction (k=2) of H1..H6 + H6b
        rows.append({
            "design": "original (CFG-P-HA)",
            "check": "H1_H6_base_bmc",
            **run_smtbmc(
                work,
                out_dir,
                RTL_DUAL,
                RTL_AXI_HA,
                ["FORMAL_SAFETY", "FORMAL_INDUCTION"],
                "bmc",
                3,
                "orig_h1_h6_base_bmc",
            ),
        })
        rows.append({
            "design": "original (CFG-P-HA)",
            "check": "H1_H6_safety_ind",
            **run_smtbmc(
                work,
                out_dir,
                RTL_DUAL,
                RTL_AXI_HA,
                ["FORMAL_SAFETY", "FORMAL_INDUCTION"],
                "ind",
                2,
                "orig_h1_h6_ind",
            ),
        })

        if not args.fast:
            # 2a. Full 30-step BMC (t=30) of H1, H2, H4, H5 via sound CME over-approximation
            rows.append({
                "design": "original (CFG-P-HA)",
                "check": "H1_H2_H4_H5_safety_bmc",
                **run_smtbmc(
                    work,
                    out_dir,
                    RTL_DUAL,
                    RTL_AXI_HA,
                    ["FORMAL_SAFETY", "ONLY_CTRL"],
                    "bmc",
                    30,
                    "orig_ctrl_bmc30",
                    batch_qfbv=True,
                    cut_cme=True,
                ),
            })

            # 2b. Full 30-step BMC (t=30) of H2 & H3_no_torn_descriptor_read via Wolper data-independence symmetry
            rows.append({
                "design": "original (CFG-P-HA)",
                "check": "H2_H3_safety_bmc",
                **run_smtbmc(
                    work,
                    out_dir,
                    RTL_DUAL,
                    RTL_AXI_HA,
                    ["FORMAL_SAFETY", "ONLY_H2_H3", "WOLPER_1BIT_SLICE"],
                    "bmc",
                    30,
                    "orig_h3_bmc30",
                    batch_qfbv=True,
                    cut_cme=True,
                    slice_1bit=True,
                ),
            })

            # 3. Non-vacuity Cover witnesses (t=30)
            rows.append({
                "design": "original (CFG-P-HA)",
                "check": "cover_non_vacuity",
                **run_smtbmc(
                    work,
                    out_dir,
                    RTL_DUAL,
                    RTL_AXI_HA,
                    ["FORMAL_COVER"],
                    "cover",
                    30,
                    "orig_cover",
                ),
            })

        # 4. Mutant negative controls (AGENTS.md §4.1)
        for mid, target_kind, m_defines, depth, desc, old, new in MUTANTS:
            if target_kind == "dual":
                n = dual_src.count(old)
                if n != 1:
                    raise RuntimeError(f"{mid}: expected 1 match in {RTL_DUAL}, found {n}")
                m_dual = os.path.join(work, f"{mid}_dual.sv")
                with open(m_dual, "w", encoding="utf-8") as f:
                    f.write(dual_src.replace(old, new))
                m_axi = RTL_AXI_HA
            else:
                n = axi_ha_src.count(old)
                if n != 1:
                    raise RuntimeError(f"{mid}: expected 1 match in {RTL_AXI_HA}, found {n}")
                m_dual = RTL_DUAL
                m_axi = os.path.join(work, f"{mid}_axi_ha.sv")
                with open(m_axi, "w", encoding="utf-8") as f:
                    f.write(axi_ha_src.replace(old, new))

            rows.append({
                "design": f"{mid}: {desc}",
                "check": "mutant_bmc",
                **run_smtbmc(
                    work,
                    out_dir,
                    m_dual,
                    m_axi,
                    m_defines,
                    "bmc",
                    depth,
                    mid,
                    keep_vcd=True,
                ),
            })
    finally:
        if os.path.isdir(work):
            shutil.rmtree(work)

    csv_path = os.path.join(out_dir, "cfg_p_ha_formal_results.csv")
    fields = ["design", "check", "engine", "status", "seconds", "failed", "reached", "unreached", "vcd"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    orig_ok = all(r["status"] == "PASSED" for r in rows if r["design"].startswith("original"))
    muts_ok = all(
        r["status"] == "FAILED" and bool(r["vcd"]) and bool(r["failed"])
        for r in rows
        if not r["design"].startswith("original")
    )
    verdict = "PASSED" if (orig_ok and muts_ok) else "FAILED"

    provenance = {
        "timestamp": datetime.datetime.now().astimezone().isoformat(),
        "issue": 252,
        "experiment": "EXP-GPU-02",
        "evidence_kind": "formal_smt_z3_verification",
        "parameters": {"NUM_CONCEPTS": 4, "QUEUE_DEPTH": 4, "DATA_WIDTH": 32, "ADDR_WIDTH": 4},
        "platform": {
            "node": platform.node(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "sha256": {
            "kpol_txn_gate_v2.sv": hashlib.sha256(open(RTL_GATE, "rb").read()).hexdigest(),
            "km_concept_micro_engine.sv": hashlib.sha256(open(RTL_CME, "rb").read()).hexdigest(),
            "km_concept_bram.sv": hashlib.sha256(open(RTL_BRAM, "rb").read()).hexdigest(),
            "km_concept_bram_dual_ha.sv": hashlib.sha256(open(RTL_DUAL, "rb").read()).hexdigest(),
            "km_autonomous_sequencer.sv": hashlib.sha256(open(RTL_SEQ, "rb").read()).hexdigest(),
            "kpol_bram_pipeline_axi_ha.sv": hashlib.sha256(open(RTL_AXI_HA, "rb").read()).hexdigest(),
            "cfg_p_ha_formal_props.sv": hashlib.sha256(open(PROPS, "rb").read()).hexdigest(),
        },
        "verdict": verdict,
        "rows": rows,
    }
    with open(os.path.join(out_dir, "cfg_p_ha_formal_provenance.json"), "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2)

    print("=" * 92)
    print("EXP-GPU-02 CFG-P-HA FORMAL SMT SUMMARY (Issue #252)")
    print("=" * 92)
    for r in rows:
        extra = ""
        if r["failed"]:
            extra += f" [failed: {r['failed']}]"
        if r["reached"]:
            extra += f" [reached: {r['reached']}]"
        if r["vcd"]:
            extra += f" [vcd: {r['vcd']}]"
        print(f"  {r['design']:<48} | {r['engine']:<22} | {r['status']:<6}{extra} ({r['seconds']}s)")
    print("-" * 92)
    print(f"VERDICT: {verdict}")
    print("=" * 92)

    if verdict != "PASSED":
        sys.exit(1)


if __name__ == "__main__":
    main()
