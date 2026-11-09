#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENXC7_DIR="${OPENXC7_DIR:-$HOME/opt/openxc7}"
BUILD_DIR="${BUILD_DIR:-$HOME/opt/openxc7-build/kuzmin-pynq-z1}"

if [[ ! -f "$OPENXC7_DIR/export.sh" ]]; then
    echo "OpenXC7 environment not found: $OPENXC7_DIR/export.sh" >&2
    exit 1
fi

source "$OPENXC7_DIR/export.sh"
if ! command -v fpga-as >/dev/null 2>&1 \
    && { ! command -v fasm2frames >/dev/null 2>&1 \
        || ! command -v xc7frames2bit >/dev/null 2>&1; }; then
    echo "No supported XC7 bitstream assembler is available in the OpenXC7 environment" >&2
    exit 1
fi
mkdir -p "$BUILD_DIR"

RTL_DIR="$SCRIPT_DIR/rtl"
YOSYS_JSON="$BUILD_DIR/kpol_pynq.json"
CHIPDB_BBA="$BUILD_DIR/xc7z020.bba"
CHIPDB="${CHIPDB:-$OPENXC7_DIR/share/nextpnr/himbaechel/xilinx/chipdb-xc7z020.bin}"
FASM="$BUILD_DIR/kpol_pynq.fasm"
FRAMES="$BUILD_DIR/kpol_pynq.frames"
BITSTREAM="$BUILD_DIR/kpol_pynq.bit"
BITSTREAM_TMP="$BITSTREAM.tmp.$$"
trap 'rm -f "$BITSTREAM_TMP"' EXIT

yosys -p "read_verilog -sv \
  $RTL_DIR/km_predicate_evaluator.sv \
  $RTL_DIR/km_euclid_core.sv \
  $RTL_DIR/km_concept_bram.sv \
  $RTL_DIR/km_concept_bram_core.sv \
  $RTL_DIR/km_rcfc_engine.sv \
  $RTL_DIR/km_cascade_arbiter_engine.sv \
  $RTL_DIR/km_stream_pipeline_engine.sv \
  $RTL_DIR/km_io_trigger_engine.sv \
  $RTL_DIR/kpol_txn_gate.sv \
  $RTL_DIR/kpol_txn_gate_axi_lite.sv \
  $RTL_DIR/kpol_txn_gate_pynq_z1_top.v; \
  synth_xilinx -flatten -abc9 -arch xc7 -top kpol_txn_gate_pynq_z1_top; \
  stat; check; write_json $YOSYS_JSON" \
  2>&1 | tee "$BUILD_DIR/yosys.log"

if [[ ! -s "$CHIPDB" ]]; then
    python3 "$NEXTPNR_XILINX_DIR/share/nextpnr/himbaechel/uarch/xilinx/gen/xilinx_gen.py" \
        --xray "$PRJXRAY_DB_DIR/zynq7" \
        --device xc7z020 \
        --bba "$CHIPDB_BBA"
    "$NEXTPNR_XILINX_DIR/bin/bbasm" -l "$CHIPDB_BBA" "$CHIPDB"
fi

nextpnr-himbaechel \
    --chipdb "$CHIPDB" \
    --device xc7z020clg400-1 \
    -o xdc="$SCRIPT_DIR/pynq_z1.xdc" \
    --json "$YOSYS_JSON" \
    -o fasm="$FASM" \
    --router router2 \
    --freq 100 \
    --report "$BUILD_DIR/nextpnr-report.json" \
    2>&1 | tee "$BUILD_DIR/nextpnr.log"

if command -v fpga-as >/dev/null 2>&1; then
    fpga-as \
        --prjxray_db_path="$PRJXRAY_DB_DIR/zynq7" \
        --part xc7z020clg400-1 \
        "$FASM" > "$BITSTREAM_TMP"
    mv "$BITSTREAM_TMP" "$BITSTREAM"
else
    fasm2frames \
        --part xc7z020clg400-1 \
        --db-root "$PRJXRAY_DB_DIR/zynq7" \
        "$FASM" "$FRAMES"
    xc7frames2bit \
        --part_file "$PRJXRAY_DB_DIR/zynq7/xc7z020clg400-1/part.yaml" \
        --part_name xc7z020clg400-1 \
        --frm_file "$FRAMES" \
        --output_file "$BITSTREAM_TMP"
    mv "$BITSTREAM_TMP" "$BITSTREAM"
fi
trap - EXIT

sha256sum "$BITSTREAM" | tee "$BUILD_DIR/bitstream.sha256"
stat --printf='Bitstream: %n (%s bytes)\n' "$BITSTREAM"
