// ============================================================================
// Багатоконцептна таблиця концептів у Block RAM (BRAM_CONCEPTS)
// Файл: km_concept_bram.sv
// Стандарт: IEEE 1800-2012 SystemVerilog
//
// Структура 128-бітного дескриптора концепту (16 байтів / 4 слова по 32 біти):
//   Word 0 (offset +0x0): VALUE_LO [31:0]
//   Word 1 (offset +0x4): VALUE_HI [63:32]
//   Word 2 (offset +0x8): META_WORD:
//                         [3:0]   Type ID (0=Int, 1=Float, 2=Char, 3=Byte, ...)
//                         [7:4]   Size mask (1|2|4|8 bytes)
//                         [8]     Initialized flag (1 = value defined, 0 = '_')
//                         [9]     Big Dot Flag (1 = '!', 0 = '¬')
//                         [31:16] Event subscription mask
//   Word 3 (offset +0xC): STATUS_WORD / PREDICT_VECTOR
//
// Кількість концептів: 64 (256 слів x 32 біти = 1 КБ у Block RAM)
// Порт A: AXI4-Lite доступ з процесора ARM (PS MMIO: 0x40001000 .. 0x400013FF)
// Порт B: Апаратний доступ обчислювального ядра PL (одночасне читання/запис)
// ============================================================================
`timescale 1ns/1ps

module km_concept_bram #(
    parameter int NUM_CONCEPTS = 64,
    parameter int DATA_WIDTH   = 32,
    parameter int ADDR_WIDTH   = 8   // 64 * 4 = 256 слів (8-бітний адресний простір)
)(
    input  logic                   clk,
    input  logic                   rst_n,

    // Порт A: AXI4-Lite міст (PS)
    input  logic [ADDR_WIDTH-1:0]  a_addr_i,
    input  logic [DATA_WIDTH-1:0]  a_wdata_i,
    input  logic [3:0]             a_wstrb_i,
    input  logic                   a_we_i,
    output logic [DATA_WIDTH-1:0]  a_rdata_o,

    // Порт B: Внутрішнє апаратне ядро PL
    input  logic [ADDR_WIDTH-1:0]  b_addr_i,
    input  logic [DATA_WIDTH-1:0]  b_wdata_i,
    input  logic [3:0]             b_wstrb_i,
    input  logic                   b_we_i,
    output logic [DATA_WIDTH-1:0]  b_rdata_o,

    // Монітор колізій арбітражу
    output logic                   collision_detected_o
);

    localparam int WORDS_TOTAL = NUM_CONCEPTS * 4;

    // Масив пам'яті: 256 слів по 32 біти (1024 байти)
    logic [DATA_WIDTH-1:0] ram [0:WORDS_TOTAL-1];

    integer init_idx;
    initial begin
        for (init_idx = 0; init_idx < WORDS_TOTAL; init_idx = init_idx + 1) begin
            ram[init_idx] = '0;
        end
    end

    logic [DATA_WIDTH-1:0] a_rdata_q;
    logic [DATA_WIDTH-1:0] b_rdata_q;
    logic                  collision_q;

    assign a_rdata_o = a_rdata_q;
    assign b_rdata_o = b_rdata_q;
    assign collision_detected_o = collision_q;

    // Порт A (AXI-доступ) з побайтовим дозволом запису
    always_ff @(posedge clk) begin
        if (a_we_i) begin
            if (a_wstrb_i[0]) ram[a_addr_i][ 7: 0] <= a_wdata_i[ 7: 0];
            if (a_wstrb_i[1]) ram[a_addr_i][15: 8] <= a_wdata_i[15: 8];
            if (a_wstrb_i[2]) ram[a_addr_i][23:16] <= a_wdata_i[23:16];
            if (a_wstrb_i[3]) ram[a_addr_i][31:24] <= a_wdata_i[31:24];
        end
        a_rdata_q <= ram[a_addr_i];
    end

    // Порт B (Апаратний доступ ядра)
    always_ff @(posedge clk) begin
        if (b_we_i) begin
            if (b_wstrb_i[0]) ram[b_addr_i][ 7: 0] <= b_wdata_i[ 7: 0];
            if (b_wstrb_i[1]) ram[b_addr_i][15: 8] <= b_wdata_i[15: 8];
            if (b_wstrb_i[2]) ram[b_addr_i][23:16] <= b_wdata_i[23:16];
            if (b_wstrb_i[3]) ram[b_addr_i][31:24] <= b_wdata_i[31:24];
        end
        b_rdata_q <= ram[b_addr_i];
    end

    // Детекція одночасного конфліктного запису в одну комірку
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            collision_q <= 1'b0;
        end else begin
            if (a_we_i && b_we_i && (a_addr_i == b_addr_i)) begin
                collision_q <= 1'b1;
            end
        end
    end

endmodule
