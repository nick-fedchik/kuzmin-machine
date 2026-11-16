`timescale 1ns / 1ps

// ============================================================================
// Модуль: km_event_crossbar.sv
// Призначення: Повнозв'язний міжбанковий матричний комутатор подій Машини
// Кузьміна (Issue #255) із чесним round-robin арбітражем на кожному цільовому
// банку та однотактовим вихідним регістровим зрізом (1 такт маршрутизації =
// 10.0 нс @ 100 МГц, без комбінаційних петель ready <-> valid між вузлами).
//
// Джерела подій (NUM_SRCS = NUM_CORES + NUM_EXT_PORTS):
//   - порти [0 .. NUM_CORES-1]                     : внутрішні міжбанкові каскади вузлів
//   - порти [NUM_CORES .. NUM_CORES+NUM_EXT_PORTS-1]: зовнішні вхідні потоки подій
// ============================================================================

module km_event_crossbar #(
    parameter int NUM_CORES     = 4,
    parameter int NUM_EXT_PORTS = NUM_CORES,
    parameter int DATA_WIDTH    = 32
)(
    input  logic                                clk,
    input  logic                                rst_n,

    // Внутрішні міжбанкові порти від вузлів кластера (0 .. NUM_CORES-1)
    input  logic [NUM_CORES-1:0]                int_valid_i,
    output logic [NUM_CORES-1:0]                int_ready_o,
    input  logic [NUM_CORES*4-1:0]              int_dst_bank_i,
    input  logic [NUM_CORES*6-1:0]              int_dst_cid_i,
    input  logic [NUM_CORES*DATA_WIDTH-1:0]     int_param_i,

    // Зовнішні вхідні порти стимулів (0 .. NUM_EXT_PORTS-1)
    input  logic [NUM_EXT_PORTS-1:0]            ext_valid_i,
    output logic [NUM_EXT_PORTS-1:0]            ext_ready_o,
    input  logic [NUM_EXT_PORTS*4-1:0]          ext_dst_bank_i,
    input  logic [NUM_EXT_PORTS*6-1:0]          ext_dst_cid_i,
    input  logic [NUM_EXT_PORTS*DATA_WIDTH-1:0] ext_param_i,

    // Вихідні конвеєризовані порти до вхідних FIFO цільових банків (0 .. NUM_CORES-1)
    output logic [NUM_CORES-1:0]                dst_valid_o,
    input  logic [NUM_CORES-1:0]                dst_ready_i,
    output logic [NUM_CORES*6-1:0]              dst_cid_o,
    output logic [NUM_CORES*DATA_WIDTH-1:0]     dst_param_o,

    // Телеметрія комутатора
    output logic                                xbar_busy_o,
    output logic [31:0]                         routed_events_count_o,
    output logic [31:0]                         backpressure_stall_cycles_o,
    output logic [31:0]                         invalid_dst_drop_count_o
);

    localparam int NUM_SRCS = NUM_CORES + NUM_EXT_PORTS;
    localparam int SRC_W    = (NUM_SRCS > 1) ? $clog2(NUM_SRCS) : 1;

    localparam logic [31:0]      NUM_CORES_U32 = NUM_CORES;
    localparam logic [31:0]      LAST_SRC_U32  = NUM_SRCS - 1;
    localparam logic [SRC_W-1:0] LAST_SRC_IDX  = LAST_SRC_U32[SRC_W-1:0];
    localparam logic [31:0]      ONE_U32       = 32'd1;
    localparam logic [SRC_W-1:0] SRC_ONE       = ONE_U32[SRC_W-1:0];

    // Об'єднаний масив джерел (0..NUM_CORES-1 = внутрішні, далі зовнішні)
    logic [NUM_SRCS-1:0]        src_valid;
    logic [NUM_SRCS-1:0]        src_ready;
    logic [3:0]                 src_dst_bank [NUM_SRCS];
    logic [5:0]                 src_dst_cid  [NUM_SRCS];
    logic [DATA_WIDTH-1:0]      src_param    [NUM_SRCS];
    logic [NUM_SRCS-1:0]        src_bank_in_range;

    genvar gs;
    generate
        for (gs = 0; gs < NUM_CORES; gs = gs + 1) begin : gen_int_src
            assign src_valid[gs]         = int_valid_i[gs];
            assign src_dst_bank[gs]      = int_dst_bank_i[gs*4 +: 4];
            assign src_dst_cid[gs]       = int_dst_cid_i[gs*6 +: 6];
            assign src_param[gs]         = int_param_i[gs*DATA_WIDTH +: DATA_WIDTH];
            assign src_bank_in_range[gs] = ({28'd0, src_dst_bank[gs]} < NUM_CORES_U32);
            assign int_ready_o[gs]       = src_ready[gs];
        end

        for (gs = 0; gs < NUM_EXT_PORTS; gs = gs + 1) begin : gen_ext_src
            localparam int S_IDX = NUM_CORES + gs;
            assign src_valid[S_IDX]         = ext_valid_i[gs];
            assign src_dst_bank[S_IDX]      = ext_dst_bank_i[gs*4 +: 4];
            assign src_dst_cid[S_IDX]       = ext_dst_cid_i[gs*6 +: 6];
            assign src_param[S_IDX]         = ext_param_i[gs*DATA_WIDTH +: DATA_WIDTH];
            assign src_bank_in_range[S_IDX] = ({28'd0, src_dst_bank[S_IDX]} < NUM_CORES_U32);
            assign ext_ready_o[gs]          = src_ready[S_IDX];
        end
    endgenerate

    // Матриця грантів round-robin арбітрів та регістрових зрізів на кожному банку j
    logic [NUM_SRCS-1:0]   bank_grant_fire [NUM_CORES];
    logic [NUM_CORES-1:0]  bank_accept_pulse;

    logic [NUM_CORES-1:0]  pipe_valid_q;
    logic [5:0]            pipe_cid_q   [NUM_CORES];
    logic [DATA_WIDTH-1:0] pipe_param_q [NUM_CORES];
    logic [SRC_W-1:0]      rr_ptr_q     [NUM_CORES];

    genvar gj, gk;
    generate
        for (gj = 0; gj < NUM_CORES; gj = gj + 1) begin : gen_bank_slice
            localparam logic [31:0] BANK_J_U32 = gj;
            localparam logic [3:0]  BANK_J     = BANK_J_U32[3:0];

            logic [NUM_SRCS-1:0] req_vec;
            logic [NUM_SRCS-1:0] req_hi;
            logic [NUM_SRCS-1:0] req_eff;
            logic [NUM_SRCS-1:0] grant_vec;
            logic                req_any;
            logic [SRC_W-1:0]    win_idx;

            wire [SRC_W-1:0] eff_rr_ptr = rr_ptr_q[gj];
            wire pipe_can_accept_w = !pipe_valid_q[gj] || dst_ready_i[gj];
            wire dst_fire_w        = pipe_valid_q[gj] && dst_ready_i[gj];

            for (gk = 0; gk < NUM_SRCS; gk = gk + 1) begin : gen_req
                wire bank_match_w = (src_dst_bank[gk] == BANK_J);
                assign req_vec[gk] = src_valid[gk] && src_bank_in_range[gk] && bank_match_w;
            end

            always_comb begin
                req_hi = '0;
                for (int s = 0; s < NUM_SRCS; s = s + 1) begin
                    if (s >= int'({{(32-SRC_W){1'b0}}, eff_rr_ptr})) begin
                        req_hi[s] = req_vec[s];
                    end
                end
            end

            assign req_eff = (|req_hi) ? req_hi : req_vec;

            always_comb begin
                req_any   = 1'b0;
                win_idx   = '0;
                grant_vec = '0;
                for (int s = 0; s < NUM_SRCS; s = s + 1) begin
                    if (!req_any && req_eff[s]) begin
                        req_any      = 1'b1;
                        win_idx      = s[SRC_W-1:0];
                        grant_vec[s] = 1'b1;
                    end
                end
            end

            wire grant_fire_w = req_any && pipe_can_accept_w;
            assign bank_grant_fire[gj]   = grant_fire_w ? grant_vec : '0;
            assign bank_accept_pulse[gj] = grant_fire_w;

            always_ff @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    pipe_valid_q[gj] <= 1'b0;
                    pipe_cid_q[gj]   <= '0;
                    pipe_param_q[gj] <= '0;
                    rr_ptr_q[gj]     <= '0;
                end else begin
                    if (grant_fire_w) begin
                        pipe_valid_q[gj] <= 1'b1;
                        pipe_cid_q[gj]   <= src_dst_cid[win_idx];
                        pipe_param_q[gj] <= src_param[win_idx];
                        rr_ptr_q[gj]     <= (win_idx == LAST_SRC_IDX) ? '0 : (win_idx + SRC_ONE);
                    end else if (dst_fire_w) begin
                        pipe_valid_q[gj] <= 1'b0;
                    end
                end
            end

            assign dst_valid_o[gj]                        = pipe_valid_q[gj];
            assign dst_cid_o[gj*6 +: 6]                   = pipe_cid_q[gj];
            assign dst_param_o[gj*DATA_WIDTH +: DATA_WIDTH] = pipe_param_q[gj];
        end
    endgenerate

    // Сигнал готовності джерела: грант цільового банку або відхилення невалідної адреси банку
    always_comb begin
        for (int s = 0; s < NUM_SRCS; s = s + 1) begin
            src_ready[s] = !src_bank_in_range[s];
            for (int j = 0; j < NUM_CORES; j = j + 1) begin
                if (bank_grant_fire[j][s]) begin
                    src_ready[s] = 1'b1;
                end
            end
        end
    end

    // Статусні прапорці та апаратні лічильники телеметрії
    assign xbar_busy_o = (|pipe_valid_q);

    logic [31:0] routed_cnt_q;
    logic [31:0] stall_cycles_q;
    logic [31:0] inv_drop_cnt_q;

    logic [31:0] routed_add_w;
    logic [31:0] inv_drop_add_w;
    logic        any_src_stalled_w;

    always_comb begin
        routed_add_w      = 32'd0;
        inv_drop_add_w    = 32'd0;
        any_src_stalled_w = 1'b0;
        for (int j = 0; j < NUM_CORES; j = j + 1) begin
            if (bank_accept_pulse[j]) begin
                routed_add_w = routed_add_w + 32'd1;
            end
        end
        for (int s = 0; s < NUM_SRCS; s = s + 1) begin
            if (src_valid[s] && !src_bank_in_range[s]) begin
                inv_drop_add_w = inv_drop_add_w + 32'd1;
            end
            if (src_valid[s] && src_bank_in_range[s] && !src_ready[s]) begin
                any_src_stalled_w = 1'b1;
            end
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            routed_cnt_q   <= 32'd0;
            stall_cycles_q <= 32'd0;
            inv_drop_cnt_q <= 32'd0;
        end else begin
            routed_cnt_q   <= routed_cnt_q + routed_add_w;
            inv_drop_cnt_q <= inv_drop_cnt_q + inv_drop_add_w;
            if (any_src_stalled_w) begin
                stall_cycles_q <= stall_cycles_q + 32'd1;
            end
        end
    end

    assign routed_events_count_o       = routed_cnt_q;
    assign backpressure_stall_cycles_o = stall_cycles_q;
    assign invalid_dst_drop_count_o    = inv_drop_cnt_q;

endmodule
