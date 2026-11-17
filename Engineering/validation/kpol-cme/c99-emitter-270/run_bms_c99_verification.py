#!/usr/bin/env python3
"""Issue #270: End-to-end verification and benchmark runner for BMS Safety Cascade (--emit-c99 + Z3).

Executes:
  1. Host x86_64 compilation (`gcc -std=c99 -O2 -Wall -Wextra -Werror -pedantic`) and execution
     of `bms_c99_hil_bench.c` + comparison with `ReferenceCmeSafetyEngine` and `Interpreter`;
  2. Host Icarus Verilog 12.0 RTL simulation of `kpol_bram_pipeline_axi.sv` (`CFG-P`) with
     `bms_safety_cascade.bin` on the 8-event BMS protection trace;
  3. Physical PYNQ-Z1 (`pynq2` @ `192.168.68.69`) execution under bench lock:
     - Compiles `bms_c99_hil_bench.c` natively on dual-core `ARM Cortex-A9 @ 650 MHz` with
       `gcc -std=c99 -O2 -Wall -Wextra -Werror -pedantic` and measures L1-cached execution latency;
     - Loads `bms_safety_cascade.bin` into the physical `Zynq-7020` FPGA PL (`0x40000000`, `CFG-P`)
       and executes the exact 8-event BMS trace on silicon, confirming 100% bit-exact state and
       telemetry identity across C99, software model, RTL simulation, and physical FPGA fabric.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime
import fcntl
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
RAW_DIR = HERE / "raw"
SW_REF_DIR = REPO_ROOT / "Engineering" / "sw" / "kpol-ref"
HW_RTL_DIR = REPO_ROOT / "Engineering" / "hw" / "rtl"

if str(SW_REF_DIR) not in sys.path:
    sys.path.insert(0, str(SW_REF_DIR))

from c99_emitter import (  # noqa: E402
    ReferenceCmeSafetyEngine,
    prove_c99_descriptor_safety_z3,
)
import kpol_reference as kr  # noqa: E402

BMS_KPOL_PATH = HERE / "bms_safety_cascade.kpol"
BMS_BIN_PATH = HERE / "bms_safety_cascade.bin"
BMS_C99_PATH = HERE / "bms_safety_cascade_gen.c"
BMS_Z3_CERT_PATH = HERE / "bms_safety_z3_certificate.json"
BMS_BENCH_C_PATH = HERE / "bms_c99_hil_bench.c"

BMS_HW_TRACE_PARAMS = [15, 5500, 120, 49, 180, 250, 5000, -10]

PYNQ_MMIO_C_SOURCE = r"""
#define _POSIX_C_SOURCE 200809L
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#define BASE_ADDR       0x40000000UL
#define MAP_SIZE        0x2000UL
#define REG_ID          (0x000 / 4)
#define REG_BRAM_ADDR   (0x004 / 4)
#define REG_BRAM_DATA   (0x008 / 4)
#define REG_EVENT_PARAM (0x00C / 4)
#define REG_SW_TRIGGER  (0x010 / 4)
#define REG_BUSY        (0x014 / 4)
#define REG_EVENTS      (0x018 / 4)
#define REG_COMMITS     (0x01C / 4)
#define REG_REJECTS     (0x020 / 4)
#define REG_LAST_STATE  (0x024 / 4)

static void wait_idle(volatile uint32_t *regs) {
    int guard = 0;
    while ((regs[REG_BUSY] & 1u) != 0u) {
        if (++guard > 1000000) {
            fprintf(stderr, "Timeout waiting for REG_BUSY == 0\n");
            exit(2);
        }
    }
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <bms_safety_cascade.bin>\n", argv[0]);
        return 2;
    }
    FILE *fp = fopen(argv[1], "rb");
    if (!fp) {
        perror("fopen bin");
        return 2;
    }
    uint32_t words[256];
    if (fread(words, sizeof(uint32_t), 256, fp) != 256) {
        fprintf(stderr, "Failed to read 256 words\n");
        fclose(fp);
        return 2;
    }
    fclose(fp);

    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) {
        perror("open /dev/mem");
        return 2;
    }
    volatile uint32_t *regs = (volatile uint32_t *)mmap(
        NULL, MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, BASE_ADDR
    );
    if (regs == MAP_FAILED) {
        perror("mmap");
        close(fd);
        return 2;
    }

    uint32_t chip_id = regs[REG_ID];
    /* Accept either single-bank KPMC (0x4B504D43) or dual-bank KPHA (0x4B504841) */
    if ((chip_id != 0x4B504D43u) && (chip_id != 0x4B504841u)) {
        fprintf(stderr, "Unexpected FPGA ID: 0x%08X\n", (unsigned)chip_id);
        munmap((void *)regs, MAP_SIZE);
        close(fd);
        return 2;
    }

    wait_idle(regs);
    for (uint32_t i = 0; i < 256u; ++i) {
        regs[REG_BRAM_ADDR] = i;
        regs[REG_BRAM_DATA] = words[i];
    }
    wait_idle(regs);

    uint32_t ev0 = regs[REG_EVENTS];
    uint32_t cm0 = regs[REG_COMMITS];
    uint32_t rj0 = regs[REG_REJECTS];

    const int32_t params[8] = { 15, 5500, 120, 49, 180, 250, 5000, -10 };
    for (int i = 0; i < 8; ++i) {
        wait_idle(regs);
        regs[REG_EVENT_PARAM] = (uint32_t)params[i];
        regs[REG_SW_TRIGGER]  = 1u;
        wait_idle(regs);
    }

    uint32_t ev1 = regs[REG_EVENTS];
    uint32_t cm1 = regs[REG_COMMITS];
    uint32_t rj1 = regs[REG_REJECTS];
    int32_t st[4];
    for (uint32_t c = 0; c < 4u; ++c) {
        regs[REG_BRAM_ADDR] = c * 4u;
        st[c] = (int32_t)regs[REG_BRAM_DATA];
    }

    printf("{\n");
    printf("  \"fpga_id_hex\": \"0x%08X\",\n", (unsigned)chip_id);
    printf("  \"pl_final_state\": [%d, %d, %d, %d],\n",
           (int)st[0], (int)st[1], (int)st[2], (int)st[3]);
    printf("  \"pl_events_delta\": %u,\n", (unsigned)(ev1 - ev0));
    printf("  \"pl_commits_delta\": %u,\n", (unsigned)(cm1 - cm0));
    printf("  \"pl_rejects_delta\": %u\n", (unsigned)(rj1 - rj0));
    printf("}\n");

    munmap((void *)regs, MAP_SIZE);
    close(fd);
    return 0;
}
"""


@contextmanager
def _scratch_dir():
    base = REPO_ROOT / ".pytest_cache" / f"bms270_{uuid.uuid4().hex}"
    base.mkdir(parents=True, exist_ok=False)
    try:
        yield base
    finally:
        shutil.rmtree(base, ignore_errors=True)


@contextmanager
def _hardware_bench_lock(timeout_sec: float = 600.0):
    lock_path = "/" + "tmp/km-bench.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o666)
    deadline = time.monotonic() + timeout_sec
    acquired = False
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out acquiring {lock_path}")
                time.sleep(0.2)
        yield lock_path
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _git_head_sha() -> str:
    res = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout.strip()


def _write_log(path: Path, cmd_str: str, body: str, extra_headers: dict[str, str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().astimezone().isoformat()
    git_sha = _git_head_sha()
    host_str = platform.platform()
    hdr_lines = [
        f"# cmd: {cmd_str}",
        f"# timestamp: {ts}",
        f"# git_commit: {git_sha}",
        f"# host: {host_str}",
    ]
    for k, v in (extra_headers or {}).items():
        hdr_lines.append(f"# {k}: {v}")
    header = "\n".join(hdr_lines) + "\n"
    cleaned = "\n".join(line.rstrip() for line in (header + body).splitlines()) + "\n"
    path.write_text(cleaned, encoding="utf-8")


def run_iverilog_bms_trace(scratch_dir: Path, image_bytes: bytes) -> dict:
    """Run Icarus Verilog simulation of CFG-P on bms_safety_cascade.bin."""
    words = struct.unpack("<256I", image_bytes)
    img_hex = scratch_dir / "bms_img.hex"
    img_hex.write_text("\n".join(f"{w:08x}" for w in words) + "\n", encoding="utf-8")

    ev_lines = []
    for p in BMS_HW_TRACE_PARAMS:
        ev_lines.append("00000000")
        ev_lines.append(f"{p & 0xFFFFFFFF:08x}")
    ev_hex = scratch_dir / "bms_events.hex"
    ev_hex.write_text("\n".join(ev_lines) + "\n", encoding="utf-8")

    tb_sv = scratch_dir / "bms_cfgp_tb.sv"
    tb_sv.write_text(
        """`timescale 1ns/1ps
module bms_cfgp_tb;
    logic clk = 0, rst_n = 0;
    always #5 clk = ~clk;

    logic [12:0] awaddr = 0, araddr = 0;
    logic awvalid = 0, wvalid = 0, bready = 0, arvalid = 0, rready = 0;
    logic [31:0] wdata = 0;
    wire awready, wready, bvalid, arready, rvalid, busy;
    wire [1:0] bresp, rresp;
    wire [31:0] rdata;
    logic ext_hw_trigger_valid_i = 0;
    logic [5:0] ext_hw_trigger_cid_i = 0;
    logic [31:0] ext_hw_trigger_param_i = 0;
    wire hw_trigger_ready_o, hw_commit_pulse_o, hw_reject_pulse_o;

    kpol_bram_pipeline_axi dut (
        .clk(clk), .rst_n(rst_n),
        .awaddr(awaddr), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(4'hf), .wvalid(wvalid), .wready(wready),
        .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arvalid(arvalid), .arready(arready),
        .rdata(rdata), .rresp(rresp), .rvalid(rvalid), .rready(rready),
        .ext_hw_trigger_valid_i(ext_hw_trigger_valid_i),
        .ext_hw_trigger_cid_i(ext_hw_trigger_cid_i),
        .ext_hw_trigger_param_i(ext_hw_trigger_param_i),
        .hw_trigger_ready_o(hw_trigger_ready_o),
        .hw_commit_pulse_o(hw_commit_pulse_o),
        .hw_reject_pulse_o(hw_reject_pulse_o),
        .hw_pipeline_busy_o(), .fifo_overflow_o(), .events_dropped_count_o(),
        .hw_commit_cid_o(), .hw_last_committed_state_o(),
        .busy(busy)
    );

    task automatic axi_write(input [12:0] addr, input [31:0] data);
        @(negedge clk);
        awaddr = addr; wdata = data; awvalid = 1; wvalid = 1; bready = 1;
        do @(posedge clk); while (!awready || !wready);
        @(negedge clk); awvalid = 0; wvalid = 0;
        while (!bvalid) @(negedge clk);
        @(negedge clk); bready = 0;
    endtask

    task automatic axi_read(input [12:0] addr, output [31:0] data);
        @(negedge clk);
        araddr = addr; arvalid = 1; rready = 1;
        do @(posedge clk); while (!arready);
        @(negedge clk); arvalid = 0;
        while (!rvalid) @(negedge clk);
        data = rdata;
        @(negedge clk); rready = 0;
    endtask

    reg [4095:0] image_hex_path, events_hex_path;
    logic [31:0] img [0:255];
    logic [31:0] event_words [0:63];
    int num_events;

    initial begin
        logic [31:0] ev_cnt, cm_cnt, rj_cnt, w0, w1, w2, w3;
        rst_n = 0;
        repeat (4) @(posedge clk);
        @(negedge clk); rst_n = 1;
        repeat (2) @(posedge clk);

        if (!$value$plusargs("image_hex=%s", image_hex_path)) $fatal(1, "no image_hex");
        if (!$value$plusargs("events_hex=%s", events_hex_path)) $fatal(1, "no events_hex");
        if (!$value$plusargs("num_events=%d", num_events)) num_events = 0;

        $readmemh(image_hex_path, img);
        for (int i = 0; i < 256; i++) begin
            axi_write(13'h004, i);
            axi_write(13'h008, img[i]);
        end

        $readmemh(events_hex_path, event_words);
        for (int e = 0; e < num_events; e++) begin
            int cyc;
            cyc = 0;
            @(negedge clk);
            while (!hw_trigger_ready_o) @(negedge clk);
            ext_hw_trigger_cid_i = event_words[e * 2][5:0];
            ext_hw_trigger_param_i = event_words[e * 2 + 1];
            ext_hw_trigger_valid_i = 1;
            @(posedge clk);
            @(negedge clk);
            ext_hw_trigger_valid_i = 0;
            while (busy) begin
                @(posedge clk);
                cyc++;
            end
            $display("RTL_STEP %0d param=%0d cycles=%0d", e, $signed(event_words[e * 2 + 1]), cyc);
        end

        axi_read(13'h018, ev_cnt);
        axi_read(13'h01c, cm_cnt);
        axi_read(13'h020, rj_cnt);
        axi_write(13'h004, 0); axi_read(13'h008, w0);
        axi_write(13'h004, 4); axi_read(13'h008, w1);
        axi_write(13'h004, 8); axi_read(13'h008, w2);
        axi_write(13'h004, 12); axi_read(13'h008, w3);
        $display("RTL_SUMMARY events=%0d commits=%0d rejects=%0d states=%0d,%0d,%0d,%0d",
                 ev_cnt, cm_cnt, rj_cnt, $signed(w0), $signed(w1), $signed(w2), $signed(w3));
        $finish;
    end
endmodule
""",
        encoding="utf-8",
    )

    sim_bin = scratch_dir / "bms_cfgp.vvp"
    rtl_files = [
        str(HW_RTL_DIR / "core" / "kpol_txn_gate_v2.sv"),
        str(HW_RTL_DIR / "core" / "km_concept_micro_engine.sv"),
        str(HW_RTL_DIR / "core" / "km_concept_bram.sv"),
        str(HW_RTL_DIR / "core" / "km_autonomous_sequencer.sv"),
        str(HW_RTL_DIR / "bus" / "kpol_bram_pipeline_axi.sv"),
        str(tb_sv),
    ]
    subprocess.run(
        ["iverilog", "-g2012", "-o", str(sim_bin), *rtl_files],
        check=True,
        capture_output=True,
        text=True,
    )
    vvp_cmd = [
        "vvp",
        str(sim_bin),
        f"+image_hex={img_hex}",
        f"+events_hex={ev_hex}",
        f"+num_events={len(BMS_HW_TRACE_PARAMS)}",
    ]
    res = subprocess.run(vvp_cmd, check=True, capture_output=True, text=True)
    _write_log(
        RAW_DIR / "iverilog_bms_cfg_p_trace.log",
        "iverilog -g2012 ... && vvp bms_cfgp.vvp +num_events=8",
        res.stdout,
    )
    summary_line = next(l for l in res.stdout.splitlines() if l.startswith("RTL_SUMMARY "))
    parts = dict(kv.split("=") for kv in summary_line.split()[1:])
    states = [int(x) for x in parts["states"].split(",")]
    return {
        "events": int(parts["events"]),
        "commits": int(parts["commits"]),
        "rejects": int(parts["rejects"]),
        "states": states,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pynq-host", default="xilinx@192.168.68.69")
    ap.add_argument("--skip-pynq", action="store_true")
    args = ap.parse_args()

    image_bytes = BMS_BIN_PATH.read_bytes()
    kpol_src = BMS_KPOL_PATH.read_text(encoding="utf-8")
    module = kr.parse_module(kpol_src)

    # 1. Verify Python ReferenceCmeSafetyEngine & kpol_reference.Interpreter
    ref_eng = ReferenceCmeSafetyEngine(image_bytes, concept_names=[s.name for s in module.states])
    interp = kr.Interpreter(module)
    interp.run([])
    for p in BMS_HW_TRACE_PARAMS:
        ref_eng.step_event(0, p, True)
        interp.run([kr.EventInput("EvCellDelta", {"delta_mv": p})])

    interp_states = [int(interp.state[s.name]) for s in module.states]
    assert ref_eng.state[:4] == [4, 4, 0, 0]
    assert interp_states == [4, 4, 0, 0]
    assert (ref_eng.events_processed, ref_eng.commits, ref_eng.rejects) == (18, 12, 6)

    cert = prove_c99_descriptor_safety_z3(
        image_bytes,
        c99_source=BMS_C99_PATH.read_text(encoding="utf-8"),
        module_name=module.name,
        concept_names=[s.name for s in module.states],
    )
    assert cert["passed"] is True
    git_sha = _git_head_sha()
    bench_c_sha256 = hashlib.sha256(BMS_BENCH_C_PATH.read_bytes()).hexdigest()

    with _scratch_dir() as scratch:
        # 2. Host x86_64 strict C99 build & run
        x86_bin = scratch / "bms_c99_hil_bench_x86"
        gcc_cmd = [
            "gcc",
            "-std=c99",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-pedantic",
            str(BMS_BENCH_C_PATH),
            "-lm",
            "-o",
            str(x86_bin),
        ]
        subprocess.run(gcc_cmd, check=True, capture_output=True, text=True)
        x86_bin_sha256 = hashlib.sha256(x86_bin.read_bytes()).hexdigest()
        x86_run = subprocess.run([str(x86_bin)], check=True, capture_output=True, text=True)
        x86_json = json.loads(x86_run.stdout)

        # 3. Host Icarus Verilog CFG-P RTL simulation
        rtl_sim = run_iverilog_bms_trace(scratch, image_bytes)

        assert x86_json["hw_trace_final_state"] == rtl_sim["states"] == [4, 4, 0, 0]
        assert x86_json["hw_trace_events"] == rtl_sim["events"] == 18
        assert x86_json["hw_trace_commits"] == rtl_sim["commits"] == 12
        assert x86_json["hw_trace_rejects"] == rtl_sim["rejects"] == 6

        x86_summary = {
            "timestamp": datetime.datetime.now().astimezone().isoformat(),
            "issue": 270,
            "git_commit": git_sha,
            "evidence_kind": "host_x86_64_c99_and_iverilog_rtl_simulation",
            "host_platform": platform.platform(),
            "gcc_flags": "-std=c99 -O2 -Wall -Wextra -Werror -pedantic -lm",
            "bms_bin_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "bms_c99_sha256": hashlib.sha256(BMS_C99_PATH.read_bytes()).hexdigest(),
            "bms_bench_c_sha256": bench_c_sha256,
            "x86_compiled_bin_sha256": x86_bin_sha256,
            "z3_certificate_verdict": cert["verdict"],
            "z3_solver": cert["solver"],
            "c99_x86_64": x86_json,
            "cfg_p_rtl_simulation": rtl_sim,
            "python_reference_model": {
                "final_state": ref_eng.state[:4],
                "events": ref_eng.events_processed,
                "commits": ref_eng.commits,
                "rejects": ref_eng.rejects,
            },
        }
        (RAW_DIR / "x86_64_bms_c99_verification.json").write_text(
            json.dumps(x86_summary, indent=2) + "\n",
            encoding="utf-8",
        )
        _write_log(
            RAW_DIR / "x86_64_bms_c99_verification.log",
            "gcc -std=c99 -O2 -Wall -Wextra -Werror -pedantic bms_c99_hil_bench.c -lm -o bms_c99_hil_bench_x86 && ./bms_c99_hil_bench_x86",
            x86_run.stdout,
            extra_headers={
                "bms_bench_c_sha256": bench_c_sha256,
                "x86_compiled_bin_sha256": x86_bin_sha256,
            },
        )

        # 4. Physical ARM Cortex-A9 + Zynq-7020 PL on PYNQ-Z1 (pynq2)
        if not args.skip_pynq:
            with _hardware_bench_lock(600.0) as lock_path:
                mmio_c_file = scratch / "pynq_bms_pl_mmio.c"
                mmio_c_file.write_text(PYNQ_MMIO_C_SOURCE, encoding="utf-8")

                subprocess.run(
                    [
                        "ssh",
                        "-o",
                        "StrictHostKeyChecking=no",
                        args.pynq_host,
                        "mkdir -p /home/xilinx/km_270_bms",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    [
                        "scp",
                        "-o",
                        "StrictHostKeyChecking=no",
                        str(BMS_BIN_PATH),
                        str(BMS_C99_PATH),
                        str(BMS_BENCH_C_PATH),
                        str(mmio_c_file),
                        f"{args.pynq_host}:/home/xilinx/km_270_bms/",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                remote_sh = (
                    "cd /home/xilinx/km_270_bms && "
                    "uname -a && "
                    "gcc --version | head -n 1 && "
                    "sha256sum bms_safety_cascade.bin bms_safety_cascade_gen.c bms_c99_hil_bench.c && "
                    "gcc -std=c99 -O2 -Wall -Wextra -Werror -pedantic bms_c99_hil_bench.c -lm -o bms_c99_hil_bench && "
                    "sha256sum bms_c99_hil_bench && "
                    "echo '=== ARM_C99_JSON_START ===' && "
                    "./bms_c99_hil_bench && "
                    "echo '=== ARM_C99_JSON_END ===' && "
                    "gcc -std=c99 -O2 -Wall -Wextra -Werror pynq_bms_pl_mmio.c -o pynq_bms_pl_mmio && "
                    "sha256sum pynq_bms_pl_mmio && "
                    "echo '=== ZYNQ_PL_JSON_START ===' && "
                    "echo xilinx | sudo -S -p '' ./pynq_bms_pl_mmio bms_safety_cascade.bin && "
                    "echo '=== ZYNQ_PL_JSON_END ==='"
                )
                pynq_res = subprocess.run(
                    ["ssh", "-o", "StrictHostKeyChecking=no", args.pynq_host, remote_sh],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                out_text = pynq_res.stdout
                _write_log(
                    RAW_DIR / "pynq_cortex_a9_bms_c99_hil.log",
                    f"flock -w 600 {lock_path} ssh {args.pynq_host} 'gcc -std=c99 -O2 -Wall -Wextra -Werror -pedantic bms_c99_hil_bench.c -lm ...'",
                    out_text,
                    extra_headers={
                        "bench_lock": f"flock -w 600 {lock_path} (acquired)",
                        "bms_bench_c_sha256": bench_c_sha256,
                    },
                )

                arm_block = out_text.split("=== ARM_C99_JSON_START ===")[1].split("=== ARM_C99_JSON_END ===")[0].strip()
                pl_block = out_text.split("=== ZYNQ_PL_JSON_START ===")[1].split("=== ZYNQ_PL_JSON_END ===")[0].strip()
                arm_json = json.loads(arm_block)
                pl_json = json.loads(pl_block)

                assert arm_json["hw_trace_final_state"] == pl_json["pl_final_state"] == [4, 4, 0, 0]
                assert arm_json["hw_trace_events"] == pl_json["pl_events_delta"] == 18
                assert arm_json["hw_trace_commits"] == pl_json["pl_commits_delta"] == 12
                assert arm_json["hw_trace_rejects"] == pl_json["pl_rejects_delta"] == 6

                pynq_summary = {
                    "timestamp": datetime.datetime.now().astimezone().isoformat(),
                    "issue": 270,
                    "git_commit": git_sha,
                    "bench_lock": f"flock -w 600 {lock_path}",
                    "evidence_kind": "physical_hil_pynq_z1_cortex_a9_and_zynq7020_pl",
                    "board": f"Digilent PYNQ-Z1 ({args.pynq_host}, Dual ARM Cortex-A9 @ 650 MHz + XC7Z020 PL @ 100 MHz)",
                    "gcc_flags": "-std=c99 -O2 -Wall -Wextra -Werror -pedantic -lm",
                    "bms_bin_sha256": hashlib.sha256(image_bytes).hexdigest(),
                    "bms_c99_sha256": hashlib.sha256(BMS_C99_PATH.read_bytes()).hexdigest(),
                    "bms_bench_c_sha256": bench_c_sha256,
                    "arm_cortex_a9_c99": arm_json,
                    "zynq_7020_pl_cfg_p": pl_json,
                    "bit_exact_match_c99_vs_pl_vs_model": True,
                }
                (RAW_DIR / "pynq_cortex_a9_bms_c99_hil.json").write_text(
                    json.dumps(pynq_summary, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(json.dumps(pynq_summary, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
