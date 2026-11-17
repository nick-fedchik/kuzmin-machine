#!/usr/bin/env python3
"""Issue #255 & #263: Formal SMT verification of 2-core CFG-P cluster & crossbar via Yosys + Z3.

Verifies `km_manycore_cluster` + `km_event_crossbar` at `NUM_CORES=2, NUM_EXT_PORTS=2,
QUEUE_DEPTH=4, NUM_CONCEPTS=4, DATA_WIDTH=32, ADDR_WIDTH=4` across both `PIPELINE_STAGES=1`
(1-stage baseline, #255) and `PIPELINE_STAGES=2` (2-stage pipelined crossbar with 2-group
hierarchical round-robin arbiter `GROUP_SIZE=2, NUM_GRPS=2`, #263) with zero vacuous internal
`assume` statements inside `FORMAL_INDUCTION`:
  * Concrete base BMC (`yosys-smtbmc -s z3 -t 4`) + unbounded k-induction (`ind t=2`) for
    both `PIPELINE_STAGES=1` and `PIPELINE_STAGES=2` (`GROUP_SIZE=2, NUM_GRPS=2`):
      - MC1_event_conservation (exact Stage 1 + Stage 2 crossbar + tx buffer + node queue conservation);
      - MC2_rr_fairness (round-robin starvation freedom across groups, <= 3 bypassed grants per bank);
      - MC3_dag_lyapunov_rank_n0/n1 (strict lexicographic rank decrease for DAG profiles);
      - MC4_deadlock_permanence (inductive permanence once mutual cyclic trap is entered).
  * Bounded liveness BMC (`yosys-smtbmc -s z3 --noincr` with sound CME cutpoints):
      - MC3_dag_progress (`t=45` for 1-stage, `t=49` for 2-stage: arbitrary Bank 0 -> Bank 1 DAG +
        concurrent 2-port burst deterministically drains all queues and crossbar stages to `!cluster_busy_o`).
  * Constructive Cover witnesses (`yosys-smtbmc -s z3 -c`):
      - C1_interbank_cascade_to_idle, C2_many_to_one_contention (`t=30` for 1-stage, `t=32` for 2-stage);
      - MC4_cyclic_deadlock_witness (`t=28` with dumped VCD witness proving mutual cyclic
        deadlock on `Bank 0 <-> Bank 1` when finite queues fill under `ready == 0`).
  * Mutant negative controls (AGENTS.md §4.1) with counterexample VCDs:
      - M1_fixed_priority_starvation -> caught by MC2_rr_fairness
      - M2_drop_crossbar_backpressure -> caught by MC1_event_conservation
      - M3_duplicate_broadcast        -> caught by MC1_event_conservation
      - M4_stage2_skid_overwrite      -> caught by MC1_event_conservation (Stage 1 -> Stage 2 skid handshake)
      - M5_multigroup_arbiter_fault   -> caught by MC1_event_conservation (inter-group arbiter collision g=0 vs g=1)
"""

from __future__ import annotations

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
WP_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.abspath(os.path.join(WP_DIR, "..", "..", "..", ".."))
RTL_CORE = os.path.join(REPO_ROOT, "Engineering", "hw", "rtl", "core")
RTL_CLUSTER = os.path.join(REPO_ROOT, "Engineering", "hw", "rtl", "cluster")

RTL_GATE = os.path.join(RTL_CORE, "kpol_txn_gate_v2.sv")
RTL_CME = os.path.join(RTL_CORE, "km_concept_micro_engine.sv")
RTL_BRAM = os.path.join(RTL_CORE, "km_concept_bram.sv")
RTL_XBAR = os.path.join(RTL_CLUSTER, "km_event_crossbar.sv")
RTL_CLUSTER_SV = os.path.join(RTL_CLUSTER, "km_manycore_cluster.sv")
PROPS = os.path.join(HERE, "manycore_formal_props.sv")
DEFAULT_OUT = os.path.join(WP_DIR, "raw")

CONNECTS = [
    "cd manycore_formal_props",
    "connect -nomap -set obs_node_tx_valid \\dut.node_tx_valid",
    "connect -nomap -set obs_node_tx_ready \\dut.node_tx_ready",
    "connect -nomap -set obs_node_tx_dst_bank \\dut.node_tx_dst_bank",
    "connect -nomap -set obs_node_tx_dst_cid \\dut.node_tx_dst_cid",
    "connect -nomap -set obs_node_rx_valid \\dut.node_rx_valid",
    "connect -nomap -set obs_node_rx_ready \\dut.node_rx_ready",
    "connect -nomap -set obs_xbar_s1_valid \\dut.xbar_inst.s1_valid_q",
    "connect -nomap -set obs_xbar_pipe_valid \\dut.xbar_inst.pipe_valid_q",
    "connect -nomap -set obs_xbar_accept_pulse \\dut.xbar_inst.bank_accept_pulse",
    "connect -nomap -set obs_xbar_can_accept_0 \\dut.xbar_inst.gen_bank_slice[0].xbar_can_accept_w",
    "connect -nomap -set obs_xbar_can_accept_1 \\dut.xbar_inst.gen_bank_slice[1].xbar_can_accept_w",
    "connect -nomap -set obs_xbar_rr_ptr_0 \\dut.xbar_inst.rr_ptr_q[0]",
    "connect -nomap -set obs_xbar_rr_ptr_1 \\dut.xbar_inst.rr_ptr_q[1]",
    "connect -nomap -set obs_n0_state_q \\dut.gen_core[0].node_inst.state_q",
    "connect -nomap -set obs_n0_fifo_count_q \\dut.gen_core[0].node_inst.fifo_count_q",
    "connect -nomap -set obs_n0_fifo_wr_ptr_q \\dut.gen_core[0].node_inst.fifo_wr_ptr_q",
    "connect -nomap -set obs_n0_fifo_rd_ptr_q \\dut.gen_core[0].node_inst.fifo_rd_ptr_q",
    "connect -nomap -set obs_n0_pend_valid_q \\dut.gen_core[0].node_inst.cascade_pending_valid_q",
    "connect -nomap -set obs_n0_active_cid_q \\dut.gen_core[0].node_inst.active_cid_q",
    "connect -nomap -set obs_n0_desc_w2_q \\dut.gen_core[0].node_inst.desc_w2_q",
    "connect -nomap -set obs_n0_desc_w3_q \\dut.gen_core[0].node_inst.desc_w3_q",
    "connect -nomap -set obs_n0_sub_fire_w \\dut.gen_core[0].node_inst.sub_fire_w",
    "connect -nomap -set obs_n0_sub_valid_q \\dut.gen_core[0].node_inst.sub_valid_q",
    "connect -nomap -set obs_n0_sub_local_q \\dut.gen_core[0].node_inst.sub_local_q",
    "connect -nomap -set obs_n0_sub_valid_comb_w \\dut.gen_core[0].node_inst.sub_valid_comb_w",
    "connect -nomap -set obs_n0_sub_is_local_w \\dut.gen_core[0].node_inst.sub_is_local_w",
    "connect -nomap -set obs_n0_sub_dst_bank_w \\dut.gen_core[0].node_inst.sub_dst_bank_w",
    "connect -nomap -set obs_n0_sub_dst_cid_w \\dut.gen_core[0].node_inst.sub_dst_cid_w",
    "connect -nomap -set obs_n0_b_we_q \\dut.gen_core[0].node_inst.bram_b_we_q",
    "connect -nomap -set obs_n0_b_addr_q \\dut.gen_core[0].node_inst.bram_b_addr_q",
    "connect -nomap -set obs_n0_hold_bank_q \\dut.gen_core[0].node_inst.hold_tx_bank_q",
    "connect -nomap -set obs_n0_ev_cnt_q \\dut.gen_core[0].node_inst.ev_count_q",
    "connect -nomap -set obs_n0_loc_cnt_q \\dut.gen_core[0].node_inst.loc_casc_count_q",
    "connect -nomap -set obs_n0_rem_cnt_q \\dut.gen_core[0].node_inst.rem_casc_count_q",
    "connect -nomap -set obs_n1_state_q \\dut.gen_core[1].node_inst.state_q",
    "connect -nomap -set obs_n1_fifo_count_q \\dut.gen_core[1].node_inst.fifo_count_q",
    "connect -nomap -set obs_n1_fifo_wr_ptr_q \\dut.gen_core[1].node_inst.fifo_wr_ptr_q",
    "connect -nomap -set obs_n1_fifo_rd_ptr_q \\dut.gen_core[1].node_inst.fifo_rd_ptr_q",
    "connect -nomap -set obs_n1_pend_valid_q \\dut.gen_core[1].node_inst.cascade_pending_valid_q",
    "connect -nomap -set obs_n1_active_cid_q \\dut.gen_core[1].node_inst.active_cid_q",
    "connect -nomap -set obs_n1_desc_w2_q \\dut.gen_core[1].node_inst.desc_w2_q",
    "connect -nomap -set obs_n1_desc_w3_q \\dut.gen_core[1].node_inst.desc_w3_q",
    "connect -nomap -set obs_n1_sub_fire_w \\dut.gen_core[1].node_inst.sub_fire_w",
    "connect -nomap -set obs_n1_sub_valid_q \\dut.gen_core[1].node_inst.sub_valid_q",
    "connect -nomap -set obs_n1_sub_local_q \\dut.gen_core[1].node_inst.sub_local_q",
    "connect -nomap -set obs_n1_sub_valid_comb_w \\dut.gen_core[1].node_inst.sub_valid_comb_w",
    "connect -nomap -set obs_n1_sub_is_local_w \\dut.gen_core[1].node_inst.sub_is_local_w",
    "connect -nomap -set obs_n1_sub_dst_bank_w \\dut.gen_core[1].node_inst.sub_dst_bank_w",
    "connect -nomap -set obs_n1_sub_dst_cid_w \\dut.gen_core[1].node_inst.sub_dst_cid_w",
    "connect -nomap -set obs_n1_b_we_q \\dut.gen_core[1].node_inst.bram_b_we_q",
    "connect -nomap -set obs_n1_b_addr_q \\dut.gen_core[1].node_inst.bram_b_addr_q",
    "connect -nomap -set obs_n1_hold_bank_q \\dut.gen_core[1].node_inst.hold_tx_bank_q",
    "connect -nomap -set obs_n1_ev_cnt_q \\dut.gen_core[1].node_inst.ev_count_q",
    "connect -nomap -set obs_n1_loc_cnt_q \\dut.gen_core[1].node_inst.loc_casc_count_q",
    "connect -nomap -set obs_n1_rem_cnt_q \\dut.gen_core[1].node_inst.rem_casc_count_q",
    "cd ..",
]

MUTANTS = [
    (
        "M1_fixed_priority_starvation",
        ["FORMAL_SAFETY", "ONLY_MC2"],
        8,
        "fixed priority 0 > 1 > 2 > 3 instead of round-robin pointer causes starvation",
        "            wire [SRC_W-1:0] eff_rr_ptr = rr_ptr_q[gj];",
        "            wire [SRC_W-1:0] eff_rr_ptr = '0;",
    ),
    (
        "M2_drop_crossbar_backpressure",
        ["FORMAL_SAFETY", "ONLY_MC1"],
        12,
        "ignoring dst_ready_i == 0 overwrites crossbar slice under backpressure and drops events",
        "            wire pipe_can_accept_w = !pipe_valid_q[gj] || dst_ready_i[gj];",
        "            wire pipe_can_accept_w = 1'b1;",
    ),
    (
        "M3_duplicate_broadcast",
        ["FORMAL_SAFETY", "ONLY_MC1"],
        6,
        "faulty crossbar bank decode routes a single event into both banks simultaneously",
        "                wire bank_match_w = (src_dst_bank[gk] == BANK_J);",
        "                wire bank_match_w = 1'b1;",
    ),
    (
        "M4_stage2_skid_overwrite",
        ["FORMAL_SAFETY", "ONLY_MC1", "KM_FORMAL_PIPE_STAGES=2"],
        12,
        "broken Stage 1 -> Stage 2 skid handshake overwrites Stage 1 register when Stage 2 is stalled",
        "            wire s1_can_accept_w   = !s1_valid_q[gj] || !pipe_valid_q[gj];",
        "            wire s1_can_accept_w   = 1'b1;",
    ),
    (
        "M5_multigroup_arbiter_fault",
        ["FORMAL_SAFETY", "ONLY_MC1", "KM_FORMAL_PIPE_STAGES=2"],
        6,
        "broken inter-group wrap-around mux (grp_eff_any = grp_hi_any) corrupts multi-group grant handoff",
        "                assign grp_eff_any = (|grp_hi_any) ? grp_hi_any : grp_lo_any;",
        "                assign grp_eff_any = grp_hi_any;",
    ),
]


def clean_lines(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


def write_log(log_path: str, cmd: list[str], text: str) -> None:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    ts = datetime.datetime.now().astimezone().isoformat()
    header = f"# cmd: {' '.join(cmd)}\n# timestamp: {ts}\n"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(clean_lines(header + text))


def sh(cmd: list[str], cwd: str, log_path: str | None = None) -> tuple[int, str, float]:
    t0 = time.time()
    env = {**os.environ, "TMPDIR": cwd}
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    dt = time.time() - t0
    out = (p.stdout or "") + (p.stderr or "")
    if log_path:
        write_log(log_path, cmd, out)
    return p.returncode, out, dt


def build_smt2(
    work: str,
    out_dir: str,
    xbar_path: str,
    props_path: str,
    defines: list[str],
    tag: str,
    use_stbv: bool = False,
    cut_cme: bool = False,
) -> str:
    smt2 = os.path.join(work, f"{tag}.smt2")
    ys = os.path.join(work, f"{tag}.ys")
    def_flags = " ".join(f"-D{d}" for d in defines)
    conn_lines = "\n".join(CONNECTS)
    cut_block = (
        "cd manycore_formal_props\n"
        "cutpoint \\dut.gen_core[0].node_inst.cme_committed "
        "\\dut.gen_core[0].node_inst.cme_updated_state "
        "\\dut.gen_core[1].node_inst.cme_committed "
        "\\dut.gen_core[1].node_inst.cme_updated_state\n"
        "cd ..\n"
        if cut_cme
        else ""
    )
    smt_flags = "-stbv" if use_stbv else "-wires"
    check_cmd = "" if cut_cme else "check -assert\n"
    script = (
        f"read_verilog -sv -formal {def_flags} "
        f"{RTL_GATE} {RTL_CME} {RTL_BRAM} {xbar_path} {RTL_CLUSTER_SV} {props_path}\n"
        "hierarchy -check -top manycore_formal_props\n"
        "proc\n"
        "flatten\n"
        f"{conn_lines}\n"
        "prep -top manycore_formal_props\n"
        "memory_map\n"
        f"{cut_block}"
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
    with open(ys, "w", encoding="utf-8") as f:
        f.write(script)
    rc, log, _ = sh(["yosys", "-q", ys], work, os.path.join(out_dir, f"{tag}.yosys.log"))
    if rc != 0:
        raise RuntimeError(f"yosys failed for {tag}:\n{log}")
    return smt2


def run_smtbmc(
    work: str,
    out_dir: str,
    xbar_path: str,
    props_path: str,
    defines: list[str],
    mode: str,
    depth: int,
    tag: str,
    keep_vcd: bool = False,
    vcd_name: str | None = None,
    batch_qfbv: bool = False,
    cut_cme: bool = False,
) -> dict[str, object]:
    smt2 = build_smt2(
        work,
        out_dir,
        xbar_path,
        props_path,
        defines,
        tag,
        use_stbv=batch_qfbv,
        cut_cme=cut_cme,
    )
    target_vcd = os.path.join(out_dir, vcd_name if vcd_name else f"{tag}.vcd")
    cmd = ["yosys-smtbmc", "--noprogress", "-s", "z3"]
    if batch_qfbv:
        cmd += ["--noincr", "-S", "tactic.default_tactic=qfbv", "-t", f"0:{depth}:{depth}"]
    elif mode == "ind":
        cmd += ["-i", "-t", str(depth)]
    elif mode == "cover":
        cmd += ["-c", "-t", str(depth)]
        if keep_vcd:
            cmd += ["--dump-vcd", target_vcd]
    else:
        cmd += ["-t", str(depth)]
        if keep_vcd:
            cmd += ["--dump-vcd", target_vcd]
    cmd.append(smt2)

    rc, out, dt = sh(cmd, work, os.path.join(out_dir, f"{tag}.log"))
    m = re.findall(r"Status: (\w+)", out)
    status = m[-1] if m else "ERROR"

    # Note: yosys-smtbmc -c with %-free --dump-vcd writes target_vcd (overwriting per cover if multiple)
    if not keep_vcd and os.path.exists(target_vcd):
        os.remove(target_vcd)

    return {
        "engine": f"smtbmc z3 {mode} t={depth}",
        "status": status,
        "seconds": round(dt, 3),
        "failed": ";".join(sorted(set(re.findall(r"Assert failed in \S+: (\w+)", out)))),
        "reached": ";".join(sorted(set(re.findall(r"Reached cover statement .*: (\w+)", out)))),
        "unreached": ";".join(sorted(set(re.findall(r"Unreached cover statement .*: (\w+)", out)))),
        "vcd": os.path.basename(target_vcd) if (keep_vcd and os.path.exists(target_vcd)) else "",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument(
        "--fast",
        action="store_true",
        help="Run fast smoke subset (base BMC + k-induction + all 3 mutants, skip deep DAG BMC/cover)",
    )
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    work = os.path.join(out_dir, "_work_formal")
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work, exist_ok=True)

    with open(RTL_XBAR, "r", encoding="utf-8") as f:
        xbar_src = f.read()
    with open(PROPS, "r", encoding="utf-8") as f:
        props_src = f.read()

    rows = []
    try:
        # 1a. Concrete 32-bit base BMC (t=4) + 1b. Unbounded k-induction (k=2) of MC1, MC2, MC3-rank, MC4-permanence
        rows.append({
            "design": "original (Cluster N=2)",
            "check": "MC1_MC4_base_bmc",
            **run_smtbmc(
                work,
                out_dir,
                RTL_XBAR,
                PROPS,
                ["FORMAL_SAFETY", "FORMAL_INDUCTION"],
                "bmc",
                4,
                "formal_mc1_mc4_base_bmc",
            ),
        })
        rows.append({
            "design": "original (Cluster N=2)",
            "check": "MC1_MC4_safety_ind",
            **run_smtbmc(
                work,
                out_dir,
                RTL_XBAR,
                PROPS,
                ["FORMAL_SAFETY", "FORMAL_INDUCTION"],
                "ind",
                2,
                "formal_mc1_mc4_ind",
                cut_cme=False,
            ),
        })

        # 1c. Concrete 32-bit base BMC (t=4) + 1d. Unbounded k-induction (k=2) for PIPELINE_STAGES=2 (#263)
        rows.append({
            "design": "original (Cluster N=2, 2-stage)",
            "check": "MC1_MC4_base_bmc_p2",
            **run_smtbmc(
                work,
                out_dir,
                RTL_XBAR,
                PROPS,
                ["FORMAL_SAFETY", "FORMAL_INDUCTION", "KM_FORMAL_PIPE_STAGES=2"],
                "bmc",
                4,
                "formal_mc1_mc4_base_bmc_p2",
            ),
        })
        rows.append({
            "design": "original (Cluster N=2, 2-stage)",
            "check": "MC1_MC4_safety_ind_p2",
            **run_smtbmc(
                work,
                out_dir,
                RTL_XBAR,
                PROPS,
                ["FORMAL_SAFETY", "FORMAL_INDUCTION", "KM_FORMAL_PIPE_STAGES=2"],
                "ind",
                2,
                "formal_mc1_mc4_ind_p2",
                cut_cme=False,
            ),
        })

        if not args.fast:
            # 2. Bounded liveness BMC (t=45) for MC3_dag_progress (Bank 0 -> Bank 1 drains to idle)
            rows.append({
                "design": "original (Cluster N=2)",
                "check": "MC3_dag_progress_bmc",
                **run_smtbmc(
                    work,
                    out_dir,
                    RTL_XBAR,
                    PROPS,
                    ["FORMAL_DAG_BMC"],
                    "bmc",
                    45,
                    "formal_mc3_dag_bmc45",
                    batch_qfbv=True,
                    cut_cme=True,
                ),
            })

            # 2b. Bounded liveness BMC (t=49) for MC3_dag_progress at PIPELINE_STAGES=2 (#263)
            rows.append({
                "design": "original (Cluster N=2, 2-stage)",
                "check": "MC3_dag_progress_bmc_p2",
                **run_smtbmc(
                    work,
                    out_dir,
                    RTL_XBAR,
                    PROPS,
                    ["FORMAL_DAG_BMC", "KM_FORMAL_PIPE_STAGES=2"],
                    "bmc",
                    49,
                    "formal_mc3_dag_bmc49_p2",
                    batch_qfbv=True,
                    cut_cme=True,
                ),
            })

            # 3a. Constructive Cover of C1 + C2 + MC4_cyclic_deadlock_witness (with dedicated VCD for MC4)
            # First run dedicated MC4 witness cover with cut_cme=False to capture exact 32-bit VCD trace!
            mc4_only_props = os.path.join(work, "mc4_only_props.sv")
            with open(mc4_only_props, "w", encoding="utf-8") as f:
                f.write(
                    props_src.replace(
                        "            C1_interbank_cascade_to_idle:\n"
                        "                cover (cov_bank1_comm_q && !cluster_busy_o && !cfg_we_i && (ext_valid_i == 2'b00));\n"
                        "            C2_many_to_one_contention:\n"
                        "                cover (cov_contention_q && cov_bank1_comm_q && !cluster_busy_o);\n",
                        "",
                    )
                )
            rows.append({
                "design": "original (Cluster N=2)",
                "check": "MC4_cyclic_deadlock_witness",
                **run_smtbmc(
                    work,
                    out_dir,
                    RTL_XBAR,
                    mc4_only_props,
                    ["FORMAL_COVER"],
                    "cover",
                    28,
                    "formal_mc4_deadlock_cover",
                    keep_vcd=True,
                    vcd_name="MC4_cyclic_deadlock_witness.vcd",
                    cut_cme=False,
                ),
            })

            # 3b. Non-vacuity cover C1 + C2 on concrete 32-bit cluster (no cutpoints)
            c12_only_props = os.path.join(work, "c12_only_props.sv")
            with open(c12_only_props, "w", encoding="utf-8") as f:
                f.write(
                    props_src.replace(
                        "            MC4_cyclic_deadlock_witness:\n"
                        "                cover (cyclic_deadlock_trap_w && !cfg_we_i && (ext_valid_i == 2'b00));\n",
                        "",
                    )
                )
            rows.append({
                "design": "original (Cluster N=2)",
                "check": "cover_dag_and_contention",
                **run_smtbmc(
                    work,
                    out_dir,
                    RTL_XBAR,
                    c12_only_props,
                    ["FORMAL_COVER"],
                    "cover",
                    30,
                    "formal_c1_c2_cover",
                ),
            })
            rows.append({
                "design": "original (Cluster N=2, 2-stage)",
                "check": "cover_dag_and_contention_p2",
                **run_smtbmc(
                    work,
                    out_dir,
                    RTL_XBAR,
                    c12_only_props,
                    ["FORMAL_COVER", "KM_FORMAL_PIPE_STAGES=2"],
                    "cover",
                    32,
                    "formal_c1_c2_cover_p2",
                ),
            })

        # 4. Mutant negative controls (AGENTS.md §4.1)
        for mid, m_defines, depth, desc, old, new in MUTANTS:
            cnt = xbar_src.count(old)
            if cnt != 1:
                raise RuntimeError(f"{mid}: expected 1 match in {RTL_XBAR}, found {cnt}")
            m_xbar = os.path.join(work, f"{mid}_xbar.sv")
            with open(m_xbar, "w", encoding="utf-8") as f:
                f.write(xbar_src.replace(old, new))

            rows.append({
                "design": f"{mid}: {desc}",
                "check": "mutant_bmc",
                **run_smtbmc(
                    work,
                    out_dir,
                    m_xbar,
                    PROPS,
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

    csv_path = os.path.join(out_dir, "manycore_formal_results.csv")
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
        "issue": 255,
        "evidence_kind": "formal_smt_z3_verification",
        "parameters": {
            "NUM_CORES": 2,
            "NUM_EXT_PORTS": 2,
            "QUEUE_DEPTH": 4,
            "NUM_CONCEPTS": 4,
            "DATA_WIDTH": 32,
            "ADDR_WIDTH": 4,
        },
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
            "km_event_crossbar.sv": hashlib.sha256(open(RTL_XBAR, "rb").read()).hexdigest(),
            "km_manycore_cluster.sv": hashlib.sha256(open(RTL_CLUSTER_SV, "rb").read()).hexdigest(),
            "manycore_formal_props.sv": hashlib.sha256(open(PROPS, "rb").read()).hexdigest(),
        },
        "verdict": verdict,
        "rows": rows,
    }
    with open(os.path.join(out_dir, "manycore_formal_provenance.json"), "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2)
        f.write("\n")

    print("=" * 94)
    print("ISSUE #255 MANY-CORE CLUSTER (N=2) FORMAL SMT SUMMARY")
    print("=" * 94)
    for r in rows:
        extra = ""
        if r["failed"]:
            extra += f" [failed: {r['failed']}]"
        if r["reached"]:
            extra += f" [reached: {r['reached']}]"
        if r["vcd"]:
            extra += f" [vcd: {r['vcd']}]"
        print(f"  {r['design']:<48} | {r['engine']:<22} | {r['status']:<6}{extra} ({r['seconds']}s)")
    print("-" * 94)
    print(f"VERDICT: {verdict}")
    print("=" * 94)

    if verdict != "PASSED":
        sys.exit(1)


if __name__ == "__main__":
    main()
