#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

python3 -m pytest -q tests/test_testbenches.py tests/test_kpol_bram_pipeline.py

for module in kpol_txn_gate_v2 km_concept_bram; do
    verilator --lint-only -Wall --top-module "$module" "rtl/core/$module.sv"
    yosys -Q -q -p "read_verilog -sv rtl/core/$module.sv; hierarchy -check -top $module; synth_xilinx -top $module; check"
done

verilator --lint-only -Wall -Wno-fatal --top-module kpol_bram_pipeline_axi \
    rtl/core/kpol_txn_gate_v2.sv rtl/core/km_concept_micro_engine.sv \
    rtl/core/km_concept_bram.sv rtl/core/km_autonomous_sequencer.sv \
    rtl/bus/kpol_bram_pipeline_axi.sv

yosys -Q -q -p "read_verilog -sv rtl/core/kpol_txn_gate_v2.sv rtl/core/km_concept_micro_engine.sv rtl/core/km_concept_bram.sv rtl/core/km_autonomous_sequencer.sv rtl/bus/kpol_bram_pipeline_axi.sv; hierarchy -check -top kpol_bram_pipeline_axi; synth_xilinx -top kpol_bram_pipeline_axi; check"

printf 'NG RTL simulation, lint and XC7 logic synthesis completed; no P&R, bitstream or HIL performed.\n'
