#!/usr/bin/env python3
"""
Reproducible comparative baseline runner for Issue #254:
1. Variant 1 & 2 on ARM Cortex-A9 (192.168.68.69 via flock /tmp/km-bench.lock):
   - Compiles c99_cascade_bench.c with gcc -O3 -mcpu=cortex-a9 -mfpu=neon -Wall
   - Captures objdump -d disassembly (raw/arm_c99_o3_disasm.txt)
   - Measures N=100000 direct in-memory C99 (-O3, mlockall) rejected 1-concept,
     full 4-concept cascade, and RAM rule-table update, plus N=10000 Linux
     kernel eventfd+poll wakeup + 4-concept cascade (raw/arm_c99_and_eventfd_bench.log/.json)
   - Strictly CPU-only user-space execution; never touches /dev/mem, MMIO, fpgautil,
     PL bitstream, or /dev/ttyACM0; cleans up /tmp/km_base254 on the board.
2. Variant 3 & 4 FPGA synthesis and Place-and-Route on xc7z020clg400-1:
   - Runs openxc7 Yosys + nextpnr-himbaechel on km_reg_configurable_cascade_axi
     for NUM_CONCEPTS = 4, 16, 64 (and exact integer crossover probe around K*)
     and on kpol_bram_pipeline_axi (CFG-P, 64 concepts in 1 RAMB36E1).
   - Also captures standalone module-level Yosys XC7 stat (both openxc7 Yosys 0.69
     and system Yosys 0.52 where ABC9 completes without return-code-134).
   - Captures cycle-accurate Icarus Verilog timing of 1-concept reject, 4-concept
     cascade, and AXI4-Lite rule reconfiguration cycles.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

STUDY_DIR = Path(__file__).resolve().parent
RAW_DIR = STUDY_DIR / "raw"
REPO_ROOT = STUDY_DIR.parents[2]
RTL_DIR = REPO_ROOT / "Engineering" / "hw" / "rtl"
BOARD_DIR = REPO_ROOT / "Engineering" / "hw" / "boards" / "pynq-z1"
OPENXC7_DIR = Path(os.environ.get("OPENXC7_DIR", "/home/mfedchyk/opt/openxc7"))
CHIPDB_PATH = OPENXC7_DIR / "share" / "nextpnr" / "himbaechel" / "xilinx" / "chipdb-xc7z020.bin"
XDC_PATH = BOARD_DIR / "kpol_bram_pipeline.xdc"


def iso_now() -> str:
    tz = timezone(timedelta(hours=2))
    return datetime.now(tz).isoformat(timespec="seconds")


def clean_lines(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def write_logged_text(path: Path, cmd_str: str, ts: str, body: str) -> None:
    header = f"# cmd: {cmd_str}\n# timestamp: {ts}\n\n"
    path.write_text(clean_lines(header + body), encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_reg_top_wrapper_source(num_concepts: int) -> str:
    """Identical PYNQ-Z1 PS7 + PMOD JA + LED/BTN/SW wrapper as kpol_bram_pipeline_pynq_z1_top.v."""
    return f"""`timescale 1ns / 1ps

module km_reg_cascade_pynq_z1_top #(
    parameter [31:0] BTN_DEBOUNCE_CYCLES = 32'd100000
) (
    input  wire       ja1,
    output wire       ja2,
    output wire       ja3,
    output wire       ja4,
    input  wire [3:0] btn,
    input  wire [1:0] sw,
    output wire [3:0] led
);
    wire [3:0] fclk_unbuffered;
    wire clk, rst_n;
    BUFG clk_buf (.I(fclk_unbuffered[0]), .O(clk));

    wire [31:0] araddr, awaddr, wdata, rdata;
    wire [11:0] arid, awid, wid;
    wire arvalid, arready, rready, rvalid;
    wire awvalid, awready, wvalid, wready, bready, bvalid;
    wire [3:0] wstrb;
    wire [1:0] rresp, bresp;
    reg [11:0] rid_q, bid_q;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rid_q <= 0;
            bid_q <= 0;
        end else begin
            if (arvalid && arready) rid_q <= arid;
            if (awvalid && awready) bid_q <= awid;
        end
    end

    wire [12:0] local_awaddr =
        (awaddr >= 32'h40000000 && awaddr < 32'h40002000) ? awaddr[12:0] : 13'h1fff;
    wire [12:0] local_araddr =
        (araddr >= 32'h40000000 && araddr < 32'h40002000) ? araddr[12:0] : 13'h1fff;

    localparam [31:0] BTN_DB_LIMIT = (BTN_DEBOUNCE_CYCLES > 32'd1)
                                   ? (BTN_DEBOUNCE_CYCLES - 32'd1)
                                   : 32'd0;

    (* ASYNC_REG = "TRUE" *) reg [1:0] ja1_cdc_q;
    reg ja1_d_q;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ja1_cdc_q <= 2'b00;
            ja1_d_q   <= 1'b0;
        end else begin
            ja1_cdc_q <= {{ja1_cdc_q[0], ja1}};
            ja1_d_q   <= ja1_cdc_q[1];
        end
    end
    wire ja1_trig_pulse = ja1_cdc_q[1] & ~ja1_d_q;

    (* ASYNC_REG = "TRUE" *) reg [1:0] btn0_cdc_q;
    reg [31:0] btn0_db_cnt_q;
    reg        btn0_stable_q;
    reg        btn0_stable_d_q;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            btn0_cdc_q      <= 2'b00;
            btn0_db_cnt_q   <= 32'd0;
            btn0_stable_q   <= 1'b0;
            btn0_stable_d_q <= 1'b0;
        end else begin
            btn0_cdc_q      <= {{btn0_cdc_q[0], btn[0]}};
            btn0_stable_d_q <= btn0_stable_q;
            if (btn0_cdc_q[1] == btn0_stable_q) begin
                btn0_db_cnt_q <= 32'd0;
            end else if (btn0_db_cnt_q >= BTN_DB_LIMIT) begin
                btn0_stable_q <= btn0_cdc_q[1];
                btn0_db_cnt_q <= 32'd0;
            end else begin
                btn0_db_cnt_q <= btn0_db_cnt_q + 32'd1;
            end
        end
    end
    wire btn0_trig_pulse = btn0_stable_q & ~btn0_stable_d_q;

    (* ASYNC_REG = "TRUE" *) reg [1:0] sw_cdc_0_q;
    (* ASYNC_REG = "TRUE" *) reg [1:0] sw_cdc_1_q;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sw_cdc_0_q <= 2'b00;
            sw_cdc_1_q <= 2'b00;
        end else begin
            sw_cdc_0_q <= sw;
            sw_cdc_1_q <= sw_cdc_0_q;
        end
    end

    wire ext_hw_trig_pulse = ja1_trig_pulse | btn0_trig_pulse;
    wire [5:0] target_cid  = {{4'd0, sw_cdc_1_q}};

    wire hw_commit, hw_reject, pipe_busy, fifo_overflow;
    wire hw_ready;
    wire [31:0] events_dropped;

    km_reg_configurable_cascade_axi #(
        .NUM_CONCEPTS({num_concepts}),
        .QUEUE_DEPTH(16),
        .DATA_WIDTH(32)
    ) pipeline (
        .clk(clk),
        .rst_n(rst_n),
        .awaddr(local_awaddr),
        .awvalid(awvalid),
        .awready(awready),
        .wdata(wdata),
        .wstrb(wstrb),
        .wvalid(wvalid),
        .wready(wready),
        .bresp(bresp),
        .bvalid(bvalid),
        .bready(bready),
        .araddr(local_araddr),
        .arvalid(arvalid),
        .arready(arready),
        .rdata(rdata),
        .rresp(rresp),
        .rvalid(rvalid),
        .rready(rready),
        .ext_hw_trigger_valid_i(ext_hw_trig_pulse),
        .ext_hw_trigger_cid_i(target_cid),
        .ext_hw_trigger_param_i(32'd1),
        .hw_trigger_ready_o(hw_ready),
        .hw_commit_pulse_o(hw_commit),
        .hw_reject_pulse_o(hw_reject),
        .hw_pipeline_busy_o(pipe_busy),
        .fifo_overflow_o(fifo_overflow),
        .events_dropped_count_o(events_dropped),
        .hw_commit_cid_o(),
        .hw_last_committed_state_o(),
        .busy()
    );

    reg [3:0] ja_commit_cnt_q;
    reg [3:0] ja_reject_cnt_q;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ja_commit_cnt_q <= 4'd0;
            ja_reject_cnt_q <= 4'd0;
        end else begin
            if (hw_commit) ja_commit_cnt_q <= 4'd10;
            else if (ja_commit_cnt_q != 4'd0) ja_commit_cnt_q <= ja_commit_cnt_q - 4'd1;
            if (hw_reject) ja_reject_cnt_q <= 4'd10;
            else if (ja_reject_cnt_q != 4'd0) ja_reject_cnt_q <= ja_reject_cnt_q - 4'd1;
        end
    end
    assign ja2 = (ja_commit_cnt_q != 4'd0);
    assign ja3 = (ja_reject_cnt_q != 4'd0);
    assign ja4 = pipe_busy;

    reg [21:0] led_commit_cnt_q;
    reg [21:0] led_reject_cnt_q;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            led_commit_cnt_q <= 22'd0;
            led_reject_cnt_q <= 22'd0;
        end else begin
            if (hw_commit) led_commit_cnt_q <= 22'd4194303;
            else if (led_commit_cnt_q != 22'd0) led_commit_cnt_q <= led_commit_cnt_q - 22'd1;
            if (hw_reject) led_reject_cnt_q <= 22'd4194303;
            else if (led_reject_cnt_q != 22'd0) led_reject_cnt_q <= led_reject_cnt_q - 22'd1;
        end
    end
    assign led[0] = (led_commit_cnt_q != 22'd0);
    assign led[1] = (led_reject_cnt_q != 22'd0);
    assign led[2] = pipe_busy;
    assign led[3] = fifo_overflow;

    PS7 ps7 (
        .FCLKCLK(fclk_unbuffered),
        .MAXIGP0ACLK(clk), .MAXIGP0ARESETN(rst_n),
        .MAXIGP0ARADDR(araddr), .MAXIGP0ARID(arid),
        .MAXIGP0ARVALID(arvalid), .MAXIGP0ARREADY(arready),
        .MAXIGP0RREADY(rready), .MAXIGP0RDATA(rdata), .MAXIGP0RID(rid_q),
        .MAXIGP0RLAST(1'b1), .MAXIGP0RRESP(rresp), .MAXIGP0RVALID(rvalid),
        .MAXIGP0AWADDR(awaddr), .MAXIGP0AWID(awid),
        .MAXIGP0AWVALID(awvalid), .MAXIGP0AWREADY(awready),
        .MAXIGP0WDATA(wdata), .MAXIGP0WSTRB(wstrb), .MAXIGP0WID(wid),
        .MAXIGP0WVALID(wvalid), .MAXIGP0WREADY(wready),
        .MAXIGP0BREADY(bready), .MAXIGP0BID(bid_q),
        .MAXIGP0BRESP(bresp), .MAXIGP0BVALID(bvalid)
    );
endmodule
"""


def run_arm_benchmarks(pynq_host: str) -> dict:
    c_src = (STUDY_DIR / "c99_cascade_bench.c").read_bytes()
    b64_src = base64.b64encode(c_src).decode("ascii")

    remote_script = f"""set -euo pipefail
trap 'rm -rf /tmp/km_base254' EXIT
rm -rf /tmp/km_base254
mkdir -p /tmp/km_base254
cd /tmp/km_base254
printf '%s' '{b64_src}' | base64 -d > c99_cascade_bench.c
echo "=== SYSINFO ==="
uname -a
gcc --version | head -n 1
objdump --version | head -n 1
ulimit -l
grep -E "processor|model name|BogoMIPS|CPU|Hardware" /proc/cpuinfo
echo "=== COMPILE ==="
gcc -std=gnu99 -O3 -mcpu=cortex-a9 -mfpu=neon -Wall -Wextra -Werror c99_cascade_bench.c -o km_c99_cascade_bench -lpthread -lm
ls -la km_c99_cascade_bench
sha256sum c99_cascade_bench.c km_c99_cascade_bench
echo "=== DISASM_BEGIN ==="
objdump -d km_c99_cascade_bench
echo "=== DISASM_END ==="
echo "=== BENCH_BEGIN ==="
./km_c99_cascade_bench --bench 100000 10000
echo "=== BENCH_END ==="
"""
    ts = iso_now()
    ssh_cmd = [
        "flock", "-w", "600", "/tmp/km-bench.lock",
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        pynq_host, "bash -s",
    ]
    cmd_repr = (
        f"flock -w 600 /tmp/km-bench.lock ssh {pynq_host} "
        "'mkdir -p /tmp/km_base254 && gcc -std=gnu99 -O3 -mcpu=cortex-a9 -mfpu=neon "
        "-Wall -Wextra -Werror c99_cascade_bench.c -o km_c99_cascade_bench -lpthread -lm && "
        "objdump -d km_c99_cascade_bench && ./km_c99_cascade_bench --bench 100000 10000 && "
        "rm -rf /tmp/km_base254'"
    )
    proc = subprocess.run(
        ssh_cmd,
        input=remote_script,
        capture_output=True,
        text=True,
        check=True,
        timeout=300,
    )
    out = proc.stdout

    sys_part = out.split("=== DISASM_BEGIN ===")[0]
    disasm_part = out.split("=== DISASM_BEGIN ===")[1].split("=== DISASM_END ===")[0].strip()
    bench_part = out.split("=== BENCH_BEGIN ===")[1].split("=== BENCH_END ===")[0].strip()

    write_logged_text(RAW_DIR / "arm_c99_build_and_sysinfo.log", cmd_repr, ts, sys_part)
    write_logged_text(
        RAW_DIR / "arm_c99_o3_disasm.txt",
        f"flock -w 600 /tmp/km-bench.lock ssh {pynq_host} 'objdump -d /tmp/km_base254/km_c99_cascade_bench'",
        ts,
        disasm_part,
    )
    write_logged_text(
        RAW_DIR / "arm_c99_and_eventfd_bench.log",
        f"flock -w 600 /tmp/km-bench.lock ssh {pynq_host} '/tmp/km_base254/km_c99_cascade_bench --bench 100000 10000'",
        ts,
        bench_part,
    )
    bench_json = json.loads(bench_part)
    (RAW_DIR / "arm_c99_and_eventfd_bench.json").write_text(
        clean_lines(json.dumps(bench_json, indent=2)), encoding="utf-8"
    )
    return bench_json


def run_openxc7_flow(
    tag: str,
    verilog_files: list[Path],
    top_module: str,
    work_dir: Path,
    env: dict[str, str],
) -> dict:
    yosys_bin = OPENXC7_DIR / "bin" / "yosys"
    nextpnr_bin = OPENXC7_DIR / "bin" / "nextpnr-himbaechel"
    json_out = work_dir / f"{tag}.json"
    nextpnr_log_tmp = work_dir / f"{tag}_nextpnr_raw.log"
    report_json_path = RAW_DIR / f"nextpnr_{tag}_report.json"

    files_str = " ".join(str(p) for p in verilog_files)
    yosys_script = (
        f"read_verilog -sv {files_str}; "
        f"synth_xilinx -flatten -abc9 -arch xc7 -top {top_module}; "
        f"stat -tech xilinx; check; write_json {json_out}"
    )
    ts_y = iso_now()
    y_cmd = [str(yosys_bin), "-p", yosys_script]
    y_proc = subprocess.run(y_cmd, capture_output=True, text=True, check=True, env=env)
    write_logged_text(
        RAW_DIR / f"yosys_{tag}.log",
        f"{yosys_bin} -p \"{yosys_script}\"",
        ts_y,
        y_proc.stdout + ("\n" + y_proc.stderr if y_proc.stderr else ""),
    )

    ts_n = iso_now()
    n_cmd = [
        str(nextpnr_bin),
        "--chipdb", str(CHIPDB_PATH),
        "--device", "xc7z020clg400-1",
        "-o", f"xdc={XDC_PATH}",
        "--json", str(json_out),
        "--router", "router2",
        "--freq", "100",
        "--timing-allow-fail",
        "--report", str(report_json_path),
        "--log", str(nextpnr_log_tmp),
    ]
    subprocess.run(n_cmd, capture_output=True, text=True, check=True, env=env)
    write_logged_text(
        RAW_DIR / f"nextpnr_{tag}.log",
        " ".join(n_cmd),
        ts_n,
        nextpnr_log_tmp.read_text(encoding="utf-8"),
    )
    # Normalize JSON formatting so zero trailing spaces exist
    rep_data = json.loads(report_json_path.read_text(encoding="utf-8"))
    report_json_path.write_text(clean_lines(json.dumps(rep_data, indent=2)), encoding="utf-8")

    util = rep_data.get("utilization", {})
    fmax_mhz = rep_data.get("fmax", {}).get("clk", {}).get("achieved", 0.0)

    # Also extract Yosys Estimated number of LCs from yosys log
    lc_match = re.findall(r"Estimated number of LCs:\s+(\d+)", y_proc.stdout)
    yosys_lcs = int(lc_match[-1]) if lc_match else 0

    return {
        "tag": tag,
        "yosys_estimated_lcs": yosys_lcs,
        "slice_lutx": util.get("SLICE_LUTX", {}).get("used", 0),
        "slice_ffx": util.get("SLICE_FFX", {}).get("used", 0),
        "carry4": util.get("CARRY4", {}).get("used", 0),
        "selmux2_1": util.get("SELMUX2_1", {}).get("used", 0),
        "ramb36e1": util.get("RAMB36E1", {}).get("used", 0),
        "ramb18e1": util.get("RAMB18E1", {}).get("used", 0),
        "fmax_mhz": round(fmax_mhz, 2),
        "passes_100mhz": bool(fmax_mhz >= 100.0),
    }


def run_standalone_core_stat(env: dict[str, str]) -> dict:
    """Run standalone module-level Yosys XC7 stat (no PS7/PMOD wrapper) for pure core comparison."""
    yosys_bin = Path("/usr/bin/yosys") if Path("/usr/bin/yosys").exists() else (OPENXC7_DIR / "bin" / "yosys")
    reg_sv = RTL_DIR / "baseline" / "km_reg_configurable_cascade_axi.sv"
    cfgp_files = [
        RTL_DIR / "core" / "kpol_txn_gate_v2.sv",
        RTL_DIR / "core" / "km_concept_micro_engine.sv",
        RTL_DIR / "core" / "km_concept_bram.sv",
        RTL_DIR / "core" / "km_autonomous_sequencer.sv",
        RTL_DIR / "bus" / "kpol_bram_pipeline_axi.sv",
    ]
    cmds = []
    for k in (4, 16, 64):
        cmds.append(
            f"read_verilog -sv {reg_sv}; "
            f"chparam -set NUM_CONCEPTS {k} km_reg_configurable_cascade_axi; "
            f"hierarchy -check -top km_reg_configurable_cascade_axi; "
            f"synth_xilinx -flatten -arch xc7 -noiopad -top km_reg_configurable_cascade_axi; "
            f"check; stat -tech xilinx; design -reset"
        )
    cmds.append(
        f"read_verilog -sv {' '.join(str(p) for p in cfgp_files)}; "
        f"hierarchy -check -top kpol_bram_pipeline_axi; "
        f"synth_xilinx -flatten -arch xc7 -noiopad -top kpol_bram_pipeline_axi; "
        f"check; stat -tech xilinx"
    )
    full_script = "; ".join(cmds)
    ts = iso_now()
    proc = subprocess.run([str(yosys_bin), "-Q", "-p", full_script], capture_output=True, text=True, check=True, env=env)
    out = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
    write_logged_text(
        RAW_DIR / "yosys_standalone_cores_stat.log",
        f"{yosys_bin} -Q -p \"{full_script}\"",
        ts,
        out,
    )
    lcs = [int(x) for x in re.findall(r"Estimated number of LCs:\s+(\d+)", out)]
    # synth_xilinx prints stat once internally and stat -tech xilinx prints once explicitly -> take odd indices
    per_run_lcs = lcs[1::2] if len(lcs) >= 8 else lcs
    return {
        "yosys_binary": str(yosys_bin),
        "reg_k4_lcs": per_run_lcs[0] if len(per_run_lcs) >= 4 else 0,
        "reg_k16_lcs": per_run_lcs[1] if len(per_run_lcs) >= 4 else 0,
        "reg_k64_lcs": per_run_lcs[2] if len(per_run_lcs) >= 4 else 0,
        "cfg_p_k64_lcs": per_run_lcs[3] if len(per_run_lcs) >= 4 else 0,
    }


def run_rtl_cycle_timing_sim(work_dir: Path, env: dict[str, str]) -> dict:
    """Measure exact clock-cycle latency of 1-concept reject, 4-concept cascade, and AXI rule update."""
    tb_src = """`timescale 1ns/1ps
module rtl_cycle_timing_bench_tb;
    logic clk = 0, rst_n = 0;
    always #5 clk = ~clk;

    // Shared AXI & trigger wires for REG (K=4) and CFG-P (K=64)
    logic [12:0] reg_awaddr = 0, reg_araddr = 0;
    logic reg_awvalid = 0, reg_wvalid = 0, reg_bready = 0, reg_arvalid = 0, reg_rready = 0;
    logic [31:0] reg_wdata = 0;
    wire reg_awready, reg_wready, reg_bvalid, reg_arready, reg_rvalid, reg_busy;
    wire [1:0] reg_bresp, reg_rresp;
    wire [31:0] reg_rdata;
    logic reg_trig_v = 0;
    wire reg_trig_r, reg_comm, reg_rej;

    logic [12:0] bram_awaddr = 0, bram_araddr = 0;
    logic bram_awvalid = 0, bram_wvalid = 0, bram_bready = 0, bram_arvalid = 0, bram_rready = 0;
    logic [31:0] bram_wdata = 0;
    wire bram_awready, bram_wready, bram_bvalid, bram_arready, bram_rvalid, bram_busy;
    wire [1:0] bram_bresp, bram_rresp;
    wire [31:0] bram_rdata;
    logic bram_trig_v = 0;
    wire bram_trig_r, bram_comm, bram_rej;

    logic [31:0] stimulus_param = 0;

    km_reg_configurable_cascade_axi #(.NUM_CONCEPTS(4)) u_reg (
        .clk(clk), .rst_n(rst_n),
        .awaddr(reg_awaddr), .awvalid(reg_awvalid), .awready(reg_awready),
        .wdata(reg_wdata), .wstrb(4'hf), .wvalid(reg_wvalid), .wready(reg_wready),
        .bresp(reg_bresp), .bvalid(reg_bvalid), .bready(reg_bready),
        .araddr(reg_araddr), .arvalid(reg_arvalid), .arready(reg_arready),
        .rdata(reg_rdata), .rresp(reg_rresp), .rvalid(reg_rvalid), .rready(reg_rready),
        .ext_hw_trigger_valid_i(reg_trig_v), .ext_hw_trigger_cid_i(6'd0),
        .ext_hw_trigger_param_i(stimulus_param), .hw_trigger_ready_o(reg_trig_r),
        .hw_commit_pulse_o(reg_comm), .hw_reject_pulse_o(reg_rej),
        .hw_pipeline_busy_o(), .fifo_overflow_o(), .events_dropped_count_o(),
        .hw_commit_cid_o(), .hw_last_committed_state_o(), .busy(reg_busy)
    );

    kpol_bram_pipeline_axi u_bram (
        .clk(clk), .rst_n(rst_n),
        .awaddr(bram_awaddr), .awvalid(bram_awvalid), .awready(bram_awready),
        .wdata(bram_wdata), .wstrb(4'hf), .wvalid(bram_wvalid), .wready(bram_wready),
        .bresp(bram_bresp), .bvalid(bram_bvalid), .bready(bram_bready),
        .araddr(bram_araddr), .arvalid(bram_arvalid), .arready(bram_arready),
        .rdata(bram_rdata), .rresp(bram_rresp), .rvalid(bram_rvalid), .rready(bram_rready),
        .ext_hw_trigger_valid_i(bram_trig_v), .ext_hw_trigger_cid_i(6'd0),
        .ext_hw_trigger_param_i(stimulus_param), .hw_trigger_ready_o(bram_trig_r),
        .hw_commit_pulse_o(bram_comm), .hw_reject_pulse_o(bram_rej),
        .hw_pipeline_busy_o(), .fifo_overflow_o(), .events_dropped_count_o(),
        .hw_commit_cid_o(), .hw_last_committed_state_o(), .busy(bram_busy)
    );

    task automatic write_reg_axi(input [12:0] addr, input [31:0] data, inout int cyc_acc);
        @(posedge clk);
        reg_awaddr <= addr; reg_wdata <= data;
        reg_awvalid <= 1; reg_wvalid <= 1; reg_bready <= 1;
        do begin @(posedge clk); cyc_acc++; end while (!reg_awready || !reg_wready);
        reg_awvalid <= 0; reg_wvalid <= 0;
        while (!reg_bvalid) begin @(posedge clk); cyc_acc++; end
        reg_bready <= 0;
    endtask

    task automatic write_bram_axi(input [12:0] addr, input [31:0] data, inout int cyc_acc);
        @(posedge clk);
        bram_awaddr <= addr; bram_wdata <= data;
        bram_awvalid <= 1; bram_wvalid <= 1; bram_bready <= 1;
        do begin @(posedge clk); cyc_acc++; end while (!bram_awready || !bram_wready);
        bram_awvalid <= 0; bram_wvalid <= 0;
        while (!bram_bvalid) begin @(posedge clk); cyc_acc++; end
        bram_bready <= 0;
    endtask

    logic [31:0] prog [0:15];
    initial begin
        int reg_load_4_cyc = 0, reg_rules_only_4_cyc = 0;
        int bram_load_4_cyc = 0, bram_rules_only_4_cyc = 0, bram_load_64_cyc = 0;
        int reg_rej_cyc = 0, reg_casc4_cyc = 0;
        int bram_rej_cyc = 0, bram_casc4_cyc = 0;

        prog[0]  = 32'd10; prog[1]  = (32'd1000 << 16) | 32'd10; prog[2]  = 32'h0100_1305; prog[3]  = 32'd1;
        prog[4]  = 32'd0;  prog[5]  = 32'd10;                    prog[6]  = 32'h0100_1303; prog[7]  = 32'd2;
        prog[8]  = 32'd100;prog[9]  = 32'd1;                     prog[10] = 32'h0200_1b04; prog[11] = 32'd3;
        prog[12] = 32'd0;  prog[13] = 32'd100;                   prog[14] = 32'h0000_0b01; prog[15] = 32'd0;

        rst_n = 0;
        repeat (4) @(posedge clk);
        rst_n = 1;
        repeat (2) @(posedge clk);

        // 1. Measure full 4-concept load (W0..W3 = 16 words)
        for (int i = 0; i < 16; i++) write_reg_axi(13'h100 + (i << 2), prog[i], reg_load_4_cyc);
        for (int c = 0; c < 4; c++) begin
            for (int w = 1; w < 4; w++) write_reg_axi(13'h100 + ((c*4 + w) << 2), prog[c*4 + w], reg_rules_only_4_cyc);
        end

        for (int i = 0; i < 16; i++) begin
            write_bram_axi(13'h004, i, bram_load_4_cyc);
            write_bram_axi(13'h008, prog[i], bram_load_4_cyc);
        end
        for (int c = 0; c < 4; c++) begin
            for (int w = 1; w < 4; w++) begin
                write_bram_axi(13'h004, c*4 + w, bram_rules_only_4_cyc);
                write_bram_axi(13'h008, prog[c*4 + w], bram_rules_only_4_cyc);
            end
        end
        for (int i = 0; i < 256; i++) begin
            write_bram_axi(13'h004, i, bram_load_64_cyc);
            write_bram_axi(13'h008, (i < 16) ? prog[i] : 32'd0, bram_load_64_cyc);
        end
        repeat (2) @(posedge clk);

        // 2. Measure 1-concept rejected event (p0 = 5)
        @(negedge clk); stimulus_param = 32'd5; reg_trig_v = 1;
        @(posedge clk); @(negedge clk); reg_trig_v = 0;
        while (reg_busy) begin @(posedge clk); reg_rej_cyc++; #1; end

        @(negedge clk); stimulus_param = 32'd5; bram_trig_v = 1;
        @(posedge clk); @(negedge clk); bram_trig_v = 0;
        while (!bram_rej) begin @(posedge clk); bram_rej_cyc++; end
        bram_rej_cyc++; // include ST_EVAL_GATE cycle
        while (bram_busy) @(posedge clk);

        // 3. Measure full 4-concept cascade (p0 = 25)
        @(negedge clk); stimulus_param = 32'd25; reg_trig_v = 1;
        @(posedge clk); @(negedge clk); reg_trig_v = 0;
        while (reg_busy) begin @(posedge clk); reg_casc4_cyc++; #1; end

        @(negedge clk); stimulus_param = 32'd25; bram_trig_v = 1;
        @(posedge clk); @(negedge clk); bram_trig_v = 0;
        begin
            int comm_seen = 0;
            while (comm_seen < 4) begin
                @(posedge clk);
                bram_casc4_cyc++;
                if (bram_comm) comm_seen++;
            end
        end
        while (bram_busy) @(posedge clk);

        $display("REG_REJECT_CYCLES=%0d", reg_rej_cyc);
        $display("REG_CASCADE4_CYCLES=%0d", reg_casc4_cyc);
        $display("REG_AXI_UPDATE_12WORDS_CYCLES=%0d", reg_rules_only_4_cyc);
        $display("REG_AXI_LOAD_16WORDS_CYCLES=%0d", reg_load_4_cyc);
        $display("CFGP_REJECT_CYCLES=%0d", bram_rej_cyc);
        $display("CFGP_CASCADE4_CYCLES=%0d", bram_casc4_cyc);
        $display("CFGP_AXI_UPDATE_12WORDS_CYCLES=%0d", bram_rules_only_4_cyc);
        $display("CFGP_AXI_LOAD_16WORDS_CYCLES=%0d", bram_load_4_cyc);
        $display("CFGP_AXI_LOAD_256WORDS_CYCLES=%0d", bram_load_64_cyc);
        $finish;
    end
endmodule
"""
    tb_file = work_dir / "rtl_cycle_timing_bench_tb.sv"
    vvp_file = work_dir / "rtl_cycle_timing_bench.vvp"
    tb_file.write_text(tb_src, encoding="utf-8")
    rtl_list = [
        RTL_DIR / "baseline" / "km_reg_configurable_cascade_axi.sv",
        RTL_DIR / "core" / "kpol_txn_gate_v2.sv",
        RTL_DIR / "core" / "km_concept_micro_engine.sv",
        RTL_DIR / "core" / "km_concept_bram.sv",
        RTL_DIR / "core" / "km_autonomous_sequencer.sv",
        RTL_DIR / "bus" / "kpol_bram_pipeline_axi.sv",
        tb_file,
    ]
    ts = iso_now()
    comp_cmd = ["iverilog", "-g2012", "-s", "rtl_cycle_timing_bench_tb", "-o", str(vvp_file), *map(str, rtl_list)]
    subprocess.run(comp_cmd, check=True, capture_output=True, text=True, env=env)
    sim_proc = subprocess.run(["vvp", "-n", str(vvp_file)], check=True, capture_output=True, text=True, env=env)
    write_logged_text(
        RAW_DIR / "rtl_cycle_timing_sim.log",
        f"{' '.join(comp_cmd)} && vvp -n {vvp_file}",
        ts,
        sim_proc.stdout,
    )
    parsed = {}
    for line in sim_proc.stdout.splitlines():
        if "=" in line:
            k, v = line.strip().split("=", 1)
            parsed[k.lower()] = int(v)
    return parsed


def compute_lut_crossover(pnr_by_k: dict[int, dict], cfg_p_lut: int) -> dict:
    """Compute exact piecewise-linear and ordinary-least-squares K* crossover for SLICE_LUTX."""
    ks = sorted(pnr_by_k.keys())
    piecewise_k_star = None
    segment = None
    for k0, k1 in zip(ks, ks[1:]):
        y0 = pnr_by_k[k0]["slice_lutx"]
        y1 = pnr_by_k[k1]["slice_lutx"]
        if (y0 <= cfg_p_lut <= y1) or (y1 <= cfg_p_lut <= y0):
            if y1 != y0:
                piecewise_k_star = k0 + (cfg_p_lut - y0) * (k1 - k0) / (y1 - y0)
                segment = [k0, k1]
            break

    # Linear regression y = a + b * K over {4, 16, 64}
    xs = [float(k) for k in (4, 16, 64) if k in pnr_by_k]
    ys = [float(pnr_by_k[int(k)]["slice_lutx"]) for k in xs]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    intercept = my - slope * mx
    ols_k_star = (cfg_p_lut - intercept) / slope if slope > 0 else None

    return {
        "cfg_p_slice_lutx": cfg_p_lut,
        "piecewise_segment": segment,
        "piecewise_k_star": round(piecewise_k_star, 2) if piecewise_k_star is not None else None,
        "piecewise_k_star_ceil_int": int(piecewise_k_star // 1 + (1 if piecewise_k_star % 1 > 0 else 0))
        if piecewise_k_star is not None
        else None,
        "ols_intercept_lut": round(intercept, 2),
        "ols_slope_lut_per_concept": round(slope, 2),
        "ols_k_star": round(ols_k_star, 2) if ols_k_star is not None else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pynq-host", default="xilinx@192.168.68.69")
    parser.add_argument("--skip-arm", action="store_true")
    parser.add_argument("--skip-pnr", action="store_true")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    work_dir = STUDY_DIR / ".build_work"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    env = os.environ.copy()
    env["TMPDIR"] = str(work_dir)
    env["PRJXRAY_DB_DIR"] = str(OPENXC7_DIR / "share" / "prjxray-db")

    try:
        arm_results = {}
        if not args.skip_arm:
            print("[1/4] Running C99 (-O3) and Linux eventfd benchmarks on ARM Cortex-A9...", flush=True)
            arm_results = run_arm_benchmarks(args.pynq_host)
        elif (RAW_DIR / "arm_c99_and_eventfd_bench.json").exists():
            arm_results = json.loads((RAW_DIR / "arm_c99_and_eventfd_bench.json").read_text(encoding="utf-8"))

        print("[2/4] Running cycle-accurate RTL latency & AXI update simulation...", flush=True)
        cycle_sim = run_rtl_cycle_timing_sim(work_dir, env)

        print("[3/4] Running standalone module-level Yosys XC7 synthesis...", flush=True)
        standalone_yosys = run_standalone_core_stat(env)

        pnr_results = {}
        if not args.skip_pnr:
            print("[4/4] Running openxc7 Yosys + nextpnr-himbaechel on xc7z020clg400-1...", flush=True)
            cfgp_files = [
                RTL_DIR / "core" / "kpol_txn_gate_v2.sv",
                RTL_DIR / "core" / "km_concept_micro_engine.sv",
                RTL_DIR / "core" / "km_concept_bram.sv",
                RTL_DIR / "core" / "km_autonomous_sequencer.sv",
                RTL_DIR / "bus" / "kpol_bram_pipeline_axi.sv",
                BOARD_DIR / "kpol_bram_pipeline_pynq_z1_top.v",
            ]
            pnr_results["cfg_p_k64"] = run_openxc7_flow(
                "cfg_p_k64", cfgp_files, "kpol_bram_pipeline_pynq_z1_top", work_dir, env
            )
            print("  CFG-P (K=64):", pnr_results["cfg_p_k64"], flush=True)

            reg_by_k: dict[int, dict] = {}
            for k in (4, 16, 64):
                top_v = work_dir / f"km_reg_cascade_top_k{k}.v"
                top_v.write_text(make_reg_top_wrapper_source(k), encoding="utf-8")
                res_k = run_openxc7_flow(
                    f"reg_k{k}",
                    [RTL_DIR / "baseline" / "km_reg_configurable_cascade_axi.sv", top_v],
                    "km_reg_cascade_pynq_z1_top",
                    work_dir,
                    env,
                )
                pnr_results[f"reg_k{k}"] = res_k
                reg_by_k[k] = res_k
                print(f"  REG (K={k}):", res_k, flush=True)

            crossover = compute_lut_crossover(reg_by_k, pnr_results["cfg_p_k64"]["slice_lutx"])
            pnr_results["crossover"] = crossover
            print("  LUT Crossover K*:", crossover, flush=True)
        elif (RAW_DIR / "baseline_254_summary.json").exists():
            prev = json.loads((RAW_DIR / "baseline_254_summary.json").read_text(encoding="utf-8"))
            pnr_results = prev.get("openxc7_pnr_xc7z020", {})

        head_sha = subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], text=True
        ).strip()

        raw_hashes = {}
        for p in sorted(RAW_DIR.iterdir()):
            if p.is_file() and p.name != "baseline_254_summary.json":
                raw_hashes[p.name] = sha256_file(p)

        summary = {
            "base_commit_sha": head_sha,
            "generated_at": iso_now(),
            "arm_cortex_a9": arm_results,
            "rtl_cycle_timing": cycle_sim,
            "standalone_yosys_xc7": standalone_yosys,
            "openxc7_pnr_xc7z020": pnr_results,
            "raw_artifact_sha256": raw_hashes,
        }
        (RAW_DIR / "baseline_254_summary.json").write_text(
            clean_lines(json.dumps(summary, indent=2)), encoding="utf-8"
        )
    finally:
        if work_dir.exists():
            shutil.rmtree(work_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
