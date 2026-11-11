#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RTL_DIR="$(cd "$SCRIPT_DIR/../../rtl" && pwd)"
OPENXC7_DIR="${OPENXC7_DIR:-$HOME/opt/openxc7}"
: "${BUILD_DIR:?Set BUILD_DIR to a new isolated build directory}"
# shellcheck source=/dev/null
source "$OPENXC7_DIR/export.sh"
CHIPDB="${CHIPDB:-$OPENXC7_DIR/share/nextpnr/himbaechel/xilinx/chipdb-xc7z020.bin}"
test -s "$CHIPDB"
mkdir -- "$BUILD_DIR"

yosys -p "read_verilog -sv \
  $RTL_DIR/core/kpol_txn_gate_v2.sv \
  $RTL_DIR/core/km_concept_micro_engine.sv \
  $RTL_DIR/core/km_concept_bram.sv \
  $RTL_DIR/core/km_autonomous_sequencer.sv \
  $RTL_DIR/bus/kpol_bram_pipeline_axi.sv \
  $SCRIPT_DIR/kpol_bram_pipeline_pynq_z1_top.v; \
  synth_xilinx -flatten -abc9 -arch xc7 -top kpol_bram_pipeline_pynq_z1_top; \
  stat; check; write_json $BUILD_DIR/pipeline.json" \
  2>&1 | tee "$BUILD_DIR/yosys.log"

nextpnr-himbaechel \
  --chipdb "$CHIPDB" --device xc7z020clg400-1 \
  -o xdc="$SCRIPT_DIR/kpol_bram_pipeline.xdc" \
  --json "$BUILD_DIR/pipeline.json" -o fasm="$BUILD_DIR/pipeline.fasm" \
  --router router2 --freq 100 --report "$BUILD_DIR/nextpnr-report.json" \
  --log "$BUILD_DIR/nextpnr.log"

if command -v fpga-as >/dev/null 2>&1; then
    fpga-as --prjxray_db_path="$PRJXRAY_DB_DIR/zynq7" \
      --part xc7z020clg400-1 "$BUILD_DIR/pipeline.fasm" > "$BUILD_DIR/pipeline.bit.tmp"
else
    fasm2frames --part xc7z020clg400-1 --db-root "$PRJXRAY_DB_DIR/zynq7" \
      "$BUILD_DIR/pipeline.fasm" "$BUILD_DIR/pipeline.frames"
    xc7frames2bit --part_file "$PRJXRAY_DB_DIR/zynq7/xc7z020clg400-1/part.yaml" \
      --part_name xc7z020clg400-1 --frm_file "$BUILD_DIR/pipeline.frames" \
      --output_file "$BUILD_DIR/pipeline.bit.tmp"
fi
mv "$BUILD_DIR/pipeline.bit.tmp" "$BUILD_DIR/pipeline.bit"
sha256sum "$BUILD_DIR/pipeline.bit" | tee "$BUILD_DIR/bitstream.sha256"
