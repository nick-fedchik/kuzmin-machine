#!/usr/bin/env bash
# ==============================================================================
# Kuzmin Machine: RTL verification, XC7 mapping and iCE40 timing proxy
# Related to open-source tools used in ~/vida; not a complete PYNQ build flow
# Tools: Icarus Verilog (12.0), Verilator (5.032), Yosys (0.52), nextpnr-ice40
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
AXI_RTL="rtl/core/km_predicate_evaluator.sv rtl/core/kpol_txn_gate.sv rtl/core/km_concept_bram.sv rtl/core/km_concept_bram_core.sv rtl/io/km_io_trigger_engine.sv rtl/poc-demo/km_euclid_core.sv rtl/poc-demo/km_rcfc_engine.sv rtl/poc-demo/km_cascade_arbiter_engine.sv rtl/poc-demo/km_stream_pipeline_engine.sv rtl/bus/kpol_txn_gate_axi_lite.sv"

echo "========================================================================"
echo " [КРОК 1/5] Функціональна симуляція всіх тестбенчів (pytest + Icarus Verilog)"
echo "========================================================================"
python3 -m pytest -q tests/test_testbenches.py

echo "========================================================================"
echo " [КРОК 2/5] Строгий лінтинг ядра (Verilator -Wall, попередження = помилка)"
echo "========================================================================"
for m in kpol_txn_gate kpol_txn_gate_v2 km_predicate_evaluator km_concept_bram km_concept_bram_core; do
  verilator --lint-only -Wall --top-module "$m" "rtl/core/$m.sv"
done
echo ">> Verilator strict lint ядра: PASS"

echo "========================================================================"
echo " [КРОК 3/5] Інформаційний лінтинг (відомі попередження, F13 у MIGRATION-REGISTER)"
echo "========================================================================"
# shellcheck disable=SC2086
verilator --lint-only -Wall -Wno-fatal --top-module km_autonomous_sequencer \
  rtl/core/kpol_txn_gate_v2.sv rtl/core/km_concept_micro_engine.sv rtl/core/km_concept_bram.sv \
  rtl/core/km_autonomous_sequencer.sv 2>&1 | grep -c "%Warning" | sed 's/^/>> CME + sequencer: попереджень: /' || true
# shellcheck disable=SC2086
verilator --lint-only -Wall -Wno-fatal --top-module kpol_txn_gate_axi_lite $AXI_RTL 2>&1 \
  | grep -c "%Warning" | sed 's/^/>> AXI-обгортка + poc-demo: попереджень: /' || true

echo "========================================================================"
echo " [КРОК 4/5] Логічний синтез під Xilinx 7-Series (Yosys synth_xilinx)"
echo "========================================================================"
yosys -q -p "read_verilog -sv rtl/core/kpol_txn_gate.sv; hierarchy -top kpol_txn_gate; synth_xilinx -top kpol_txn_gate; stat"

echo "========================================================================"
echo " [КРОК 5/5] Оціночний P&R/Fmax для iCE40 HX8K (не XC7/PYNQ)"
echo "========================================================================"
yosys -q -p "read_verilog -sv rtl/core/kpol_txn_gate.sv; hierarchy -top kpol_txn_gate; synth_ice40 -top kpol_txn_gate -json /tmp/gate_ice40.json"
nextpnr-ice40 --hx8k --package ct256 --json /tmp/gate_ice40.json --freq 100 --log /tmp/nextpnr_sta.log -q
grep "Max frequency" /tmp/nextpnr_sta.log | tail -2
echo ">> Увага: ці Fmax оцінки стосуються iCE40 HX8K, а не XC7Z020/PYNQ-Z1."

echo "========================================================================"
echo ">> RTL-перевірки, XC7 mapping та iCE40 proxy timing успішні."
echo ">> Це не підтверджує XC7 P&R/STA, bitstream або HIL на PYNQ-Z1."
echo "========================================================================"
