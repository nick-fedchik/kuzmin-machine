#!/usr/bin/env bash
# ==============================================================================
# Kuzmin Machine: RTL verification, XC7 mapping and iCE40 timing proxy
# Related to open-source tools used in ~/vida; not a complete PYNQ build flow
# Tools: Icarus Verilog (12.0), Verilator (5.032), Yosys (0.52), nextpnr-ice40
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================================"
echo " [КРОК 1/5] Функціональна симуляція Verilog (Icarus Verilog)"
echo "========================================================================"
iverilog -g2012 -Wall -s kpol_txn_gate_tb -o /tmp/kpol_txn_gate_tb.vvp \
  rtl/kpol_txn_gate.sv tb/kpol_txn_gate_tb.sv
vvp /tmp/kpol_txn_gate_tb.vvp

echo "========================================================================"
echo " [КРОК 2/5] Статичний лінтинг SystemVerilog (Verilator)"
echo "========================================================================"
verilator --lint-only -Wall --top-module kpol_txn_gate rtl/kpol_txn_gate.sv
verilator --lint-only -Wall --top-module kpol_txn_gate_axi_lite \
  rtl/km_predicate_evaluator.sv rtl/kpol_txn_gate.sv rtl/kpol_txn_gate_axi_lite.sv
echo ">> Verilator lint: 0 errors, 0 warnings (PASS)"

echo "========================================================================"
echo " [КРОК 3/5] Симуляція AXI4-Lite прототипу (Icarus Verilog)"
echo "========================================================================"
iverilog -g2012 -Wall -s kpol_txn_gate_axi_lite_tb -o /tmp/kpol_axi_tb.vvp \
  rtl/km_predicate_evaluator.sv rtl/kpol_txn_gate.sv rtl/kpol_txn_gate_axi_lite.sv tb/kpol_txn_gate_axi_lite_tb.sv
vvp /tmp/kpol_axi_tb.vvp

echo "========================================================================"
echo " [КРОК 4/5] Логічний синтез під Xilinx 7-Series (Yosys synth_xilinx)"
echo "========================================================================"
yosys -q -p "read_verilog -sv rtl/kpol_txn_gate.sv; hierarchy -top kpol_txn_gate; synth_xilinx -top kpol_txn_gate; stat"

echo "========================================================================"
echo " [КРОК 5/5] Оціночний P&R/Fmax для iCE40 HX8K (не XC7/PYNQ)"
echo "========================================================================"
yosys -q -p "read_verilog -sv rtl/kpol_txn_gate.sv; hierarchy -top kpol_txn_gate; synth_ice40 -top kpol_txn_gate -json /tmp/gate_ice40.json"
nextpnr-ice40 --hx8k --package ct256 --json /tmp/gate_ice40.json --freq 100 --log /tmp/nextpnr_sta.log -q
grep "Max frequency" /tmp/nextpnr_sta.log | tail -2
echo ">> Увага: ці Fmax оцінки стосуються iCE40 HX8K, а не XC7Z020/PYNQ-Z1."

echo "========================================================================"
echo ">> RTL-перевірки, XC7 mapping та iCE40 proxy timing успішні."
echo ">> Це не підтверджує XC7 P&R/STA, bitstream або HIL на PYNQ-Z1."
echo "========================================================================"
