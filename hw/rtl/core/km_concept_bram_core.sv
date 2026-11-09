// ============================================================================
// Автономний апаратний контролер BRAM-концептів для Port B (PL Core)
// Файл: km_concept_bram_core.sv
// Стандарт: IEEE 1800-2012 SystemVerilog
//
// Функціонал:
//   1. Ручний доступ до Port B через службові регістри (для перевірки колізій)
//   2. Автономні багатоконцептні операції в PL:
//      - OP 0: COPY (Concept[dst] <= Concept[src])
//      - OP 1: ADD  (Concept[dst] <= Concept[dst] + Concept[src])
// ============================================================================
`timescale 1ns/1ps

module km_concept_bram_core #(
    parameter int DATA_WIDTH = 32,
    parameter int ADDR_WIDTH = 8
)(
    input  logic                   clk,
    input  logic                   rst_n,

    // Інтерфейс запуску автономної операції
    input  logic                   ctrl_start_i,
    input  logic                   ctrl_op_i,        // 0 = COPY, 1 = ADD
    input  logic [5:0]             ctrl_src_cid_i,
    input  logic [5:0]             ctrl_dst_cid_i,

    // Інтерфейс ручного доступу до Port B через регістри
    input  logic                   manual_we_i,
    input  logic [ADDR_WIDTH-1:0]  manual_addr_i,
    input  logic [DATA_WIDTH-1:0]  manual_wdata_i,
    output logic [DATA_WIDTH-1:0]  manual_rdata_o,

    // Сигнали до BRAM (Port B)
    output logic [ADDR_WIDTH-1:0]  b_addr_o,
    output logic [DATA_WIDTH-1:0]  b_wdata_o,
    output logic [3:0]             b_wstrb_o,
    output logic                   b_we_o,
    input  logic [DATA_WIDTH-1:0]  b_rdata_i,

    // Статус та таймінг
    output logic                   busy_o,
    output logic                   done_o,
    output logic [31:0]            cycles_o
);

    typedef enum logic [2:0] {
        ST_IDLE             = 3'd0,
        ST_READ_SRC_LO      = 3'd1,
        ST_READ_DST_LO      = 3'd2,
        ST_CALC_WRITE_DST   = 3'd3,
        ST_FINISH           = 3'd4
    } state_t;

    state_t state_q;

    logic [DATA_WIDTH-1:0] src_val_lo_q;
    logic [31:0] cyc_cnt_q;
    logic        done_q;
    logic        op_q;
    logic [5:0]  dst_cid_q;

    assign busy_o   = (state_q != ST_IDLE);
    assign done_o   = done_q;
    assign cycles_o = cyc_cnt_q;
    assign manual_rdata_o = b_rdata_i;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q       <= ST_IDLE;
            b_addr_o      <= '0;
            b_wdata_o     <= '0;
            b_wstrb_o     <= 4'h0;
            b_we_o        <= 1'b0;
            src_val_lo_q  <= '0;
            cyc_cnt_q     <= 32'd0;
            done_q        <= 1'b0;
            op_q          <= 1'b0;
            dst_cid_q     <= '0;
        end else begin
            case (state_q)
                ST_IDLE: begin
                    b_we_o <= 1'b0;

                    if (ctrl_start_i) begin
                        done_q    <= 1'b0; // Скидається лише при новому запуску (sticky flag)
                        op_q      <= ctrl_op_i;
                        dst_cid_q <= ctrl_dst_cid_i;
                        cyc_cnt_q <= 32'd1;
                        // Запит на читання Word 0 концепту src
                        b_addr_o  <= {ctrl_src_cid_i, 2'b00};
                        state_q   <= ST_READ_SRC_LO;
                    end else if (manual_we_i) begin
                        b_addr_o  <= manual_addr_i;
                        b_wdata_o <= manual_wdata_i;
                        b_wstrb_o <= 4'hF;
                        b_we_o    <= 1'b1;
                    end else begin
                        b_addr_o  <= manual_addr_i;
                        b_we_o    <= 1'b0;
                    end
                end

                ST_READ_SRC_LO: begin
                    cyc_cnt_q <= cyc_cnt_q + 32'd1;
                    // Запит на читання Word 0 концепту dst
                    b_addr_o  <= {dst_cid_q, 2'b00};
                    state_q   <= ST_READ_DST_LO;
                end

                ST_READ_DST_LO: begin
                    cyc_cnt_q    <= cyc_cnt_q + 32'd1;
                    // Фіксація даних з src
                    src_val_lo_q <= b_rdata_i;
                    state_q      <= ST_CALC_WRITE_DST;
                end

                ST_CALC_WRITE_DST: begin
                    cyc_cnt_q <= cyc_cnt_q + 32'd1;
                    // Запис результату у dst
                    b_addr_o  <= {dst_cid_q, 2'b00};
                    if (op_q == 1'b0) begin
                        // COPY
                        b_wdata_o <= src_val_lo_q;
                    end else begin
                        // ADD
                        b_wdata_o <= b_rdata_i + src_val_lo_q;
                    end
                    b_wstrb_o <= 4'hF;
                    b_we_o    <= 1'b1;
                    state_q   <= ST_FINISH;
                end

                ST_FINISH: begin
                    cyc_cnt_q <= cyc_cnt_q + 32'd1;
                    b_we_o    <= 1'b0;
                    done_q    <= 1'b1; // Лишається 1 до наступного ctrl_start_i
                    state_q   <= ST_IDLE;
                end

                default: state_q <= ST_IDLE;
            endcase
        end
    end

endmodule
