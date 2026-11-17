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
    parameter int NUM_CORES       = 4,
    parameter int NUM_EXT_PORTS   = NUM_CORES,
    parameter int DATA_WIDTH      = 32,
    parameter int PIPELINE_STAGES = 1,
    parameter int GROUP_SIZE      = 4
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

    logic [NUM_CORES-1:0]  s1_valid_q;
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
            logic [NUM_SRCS-1:0] grant_vec;
            logic                req_any;
            logic [SRC_W-1:0]    win_idx;

            wire [SRC_W-1:0] eff_rr_ptr = rr_ptr_q[gj];
            wire [31:0]      eff_rr_u32 = {{(32-SRC_W){1'b0}}, eff_rr_ptr};
            wire pipe_can_accept_w = !pipe_valid_q[gj] || dst_ready_i[gj];
            wire s1_can_accept_w   = !s1_valid_q[gj] || !pipe_valid_q[gj];
            wire xbar_can_accept_w = (PIPELINE_STAGES == 1) ? pipe_can_accept_w : s1_can_accept_w;
            wire dst_fire_w        = pipe_valid_q[gj] && dst_ready_i[gj];

            for (gk = 0; gk < NUM_SRCS; gk = gk + 1) begin : gen_req
                wire bank_match_w = (src_dst_bank[gk] == BANK_J);
                assign req_vec[gk] = src_valid[gk] && src_bank_in_range[gk] && bank_match_w;
            end

            always_comb begin
                req_hi = '0;
                for (int sh = 0; sh < NUM_SRCS; sh = sh + 1) begin
                    if (sh >= int'(eff_rr_u32)) begin
                        req_hi[sh] = req_vec[sh];
                    end
                end
            end

            wire grant_fire_w = req_any && xbar_can_accept_w;
            assign bank_grant_fire[gj]   = xbar_can_accept_w ? grant_vec : '0;
            assign bank_accept_pulse[gj] = grant_fire_w;

            if (PIPELINE_STAGES == 1) begin : gen_stage1
                wire [NUM_SRCS-1:0] req_eff = (|req_hi) ? req_hi : req_vec;
                assign s1_valid_q[gj] = 1'b0;

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
            end else begin : gen_stage2
                localparam int EFF_GRP_SIZE = (GROUP_SIZE >= 2) ? GROUP_SIZE : 2;
                localparam int NUM_GRPS     = (NUM_SRCS > EFF_GRP_SIZE)
                                            ? ((NUM_SRCS + EFF_GRP_SIZE - 1) / EFF_GRP_SIZE)
                                            : 1;
                localparam int GRP_W        = (NUM_GRPS > 1) ? $clog2(NUM_GRPS) : 1;
                localparam int OFS_W        = (EFF_GRP_SIZE > 1) ? $clog2(EFF_GRP_SIZE) : 1;

                logic [5:0]            s1_cid_q;
                logic [DATA_WIDTH-1:0] s1_param_q;

                logic [NUM_GRPS-1:0]   grp_hi_any;
                logic [NUM_GRPS-1:0]   grp_lo_any;
                logic [NUM_GRPS-1:0]   grp_eff_any;
                logic [NUM_GRPS-1:0]   grp_win_1hot;
                logic [GRP_W-1:0]      win_grp;

                logic [OFS_W-1:0]        grp_ofs      [NUM_GRPS];
                logic [EFF_GRP_SIZE-1:0] grp_ofs_1hot [NUM_GRPS];
                logic [5:0]              grp_cid      [NUM_GRPS];
                logic [DATA_WIDTH-1:0]   grp_param    [NUM_GRPS];

                for (gk = 0; gk < NUM_GRPS; gk = gk + 1) begin : gen_grp4
                    localparam int BASE_S = gk * EFF_GRP_SIZE;
                    logic [EFF_GRP_SIZE-1:0] r_lo;
                    logic [EFF_GRP_SIZE-1:0] r_hi;
                    logic [EFF_GRP_SIZE-1:0] r_eff;

                    always_comb begin
                        r_lo = '0;
                        r_hi = '0;
                        for (int c = 0; c < EFF_GRP_SIZE; c = c + 1) begin
                            if ((BASE_S + c) < NUM_SRCS) begin
                                r_lo[c] = req_vec[BASE_S + c];
                                r_hi[c] = req_hi[BASE_S + c];
                            end
                        end
                        grp_hi_any[gk] = (|r_hi);
                        grp_lo_any[gk] = (|r_lo);
                        r_eff          = grp_hi_any[gk] ? r_hi : r_lo;

                        grp_ofs[gk]      = '0;
                        grp_ofs_1hot[gk] = '0;
                        for (int c = 0; c < EFF_GRP_SIZE; c = c + 1) begin
                            if ((grp_ofs_1hot[gk] == '0) && r_eff[c]) begin
                                grp_ofs[gk]         = c[OFS_W-1:0];
                                grp_ofs_1hot[gk][c] = 1'b1;
                            end
                        end

                        grp_cid[gk]   = '0;
                        grp_param[gk] = '0;
                        for (int c = 0; c < EFF_GRP_SIZE; c = c + 1) begin
                            if (((BASE_S + c) < NUM_SRCS) && (grp_ofs[gk] == c[OFS_W-1:0])) begin
                                grp_cid[gk]   = src_dst_cid[BASE_S + c];
                                grp_param[gk] = src_param[BASE_S + c];
                            end
                        end
                    end

                    for (genvar gc_s = 0; gc_s < EFF_GRP_SIZE; gc_s = gc_s + 1) begin : gen_gvec
                        if ((BASE_S + gc_s) < NUM_SRCS) begin : gen_valid_s
                            assign grant_vec[BASE_S + gc_s] = grp_win_1hot[gk] && grp_ofs_1hot[gk][gc_s];
                        end
                    end
                end

                assign req_any     = (|grp_lo_any);
                assign grp_eff_any = (|grp_hi_any) ? grp_hi_any : grp_lo_any;

                always_comb begin
                    grp_win_1hot = '0;
                    win_grp      = '0;
                    for (int g = 0; g < NUM_GRPS; g = g + 1) begin
                        if ((grp_win_1hot == '0) && grp_eff_any[g]) begin
                            grp_win_1hot[g] = 1'b1;
                            win_grp         = g[GRP_W-1:0];
                        end
                    end
                end

                if (NUM_GRPS == 1) begin : gen_win_le4
                    assign win_idx = grp_ofs[0][SRC_W-1:0];
                end else begin : gen_win_gt4
                    assign win_idx = {win_grp, grp_ofs[win_grp]};
                end

                always_ff @(posedge clk or negedge rst_n) begin
                    if (!rst_n) begin
                        s1_valid_q[gj]   <= 1'b0;
                        s1_cid_q         <= '0;
                        s1_param_q       <= '0;
                        pipe_valid_q[gj] <= 1'b0;
                        pipe_cid_q[gj]   <= '0;
                        pipe_param_q[gj] <= '0;
                        rr_ptr_q[gj]     <= '0;
                    end else begin
                        if (grant_fire_w) begin
                            s1_valid_q[gj] <= 1'b1;
                            s1_cid_q       <= grp_cid[win_grp];
                            s1_param_q     <= grp_param[win_grp];
                            rr_ptr_q[gj]   <= (win_idx == LAST_SRC_IDX) ? '0 : (win_idx + SRC_ONE);
                        end else if (pipe_can_accept_w) begin
                            s1_valid_q[gj] <= 1'b0;
                        end

                        if (pipe_can_accept_w) begin
                            if (s1_valid_q[gj]) begin
                                pipe_valid_q[gj] <= 1'b1;
                                pipe_cid_q[gj]   <= s1_cid_q;
                                pipe_param_q[gj] <= s1_param_q;
                            end else if (dst_fire_w) begin
                                pipe_valid_q[gj] <= 1'b0;
                            end
                        end
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
    assign xbar_busy_o = (|pipe_valid_q) || (|s1_valid_q);

    logic [31:0] routed_cnt_q;
    logic [31:0] stall_cycles_q;
    logic [31:0] inv_drop_cnt_q;

    if (PIPELINE_STAGES == 1) begin : gen_xbar_telem_s1
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
    end else begin : gen_xbar_telem_s2
        logic [NUM_CORES-1:0] accept_s1_q;
        logic [NUM_SRCS-1:0]  stalled_s1_q;
        logic [NUM_SRCS-1:0]  inv_drop_s1_q;
        logic [NUM_SRCS-1:0]  stalled_vec_w;
        logic [NUM_SRCS-1:0]  inv_drop_vec_w;
        logic [4:0]           routed_add_n;
        logic [4:0]           inv_drop_add_n;

        always_comb begin
            for (int s = 0; s < NUM_SRCS; s = s + 1) begin
                stalled_vec_w[s]  = src_valid[s] && src_bank_in_range[s] && !src_ready[s];
                inv_drop_vec_w[s] = src_valid[s] && !src_bank_in_range[s];
            end
            routed_add_n   = 5'd0;
            inv_drop_add_n = 5'd0;
            for (int j = 0; j < NUM_CORES; j = j + 1) begin
                routed_add_n = routed_add_n + {4'd0, accept_s1_q[j]};
            end
            for (int s = 0; s < NUM_SRCS; s = s + 1) begin
                inv_drop_add_n = inv_drop_add_n + {4'd0, inv_drop_s1_q[s]};
            end
        end

        always_ff @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
                accept_s1_q    <= '0;
                stalled_s1_q   <= '0;
                inv_drop_s1_q  <= '0;
                routed_cnt_q   <= 32'd0;
                stall_cycles_q <= 32'd0;
                inv_drop_cnt_q <= 32'd0;
            end else begin
                accept_s1_q    <= bank_accept_pulse;
                stalled_s1_q   <= stalled_vec_w;
                inv_drop_s1_q  <= inv_drop_vec_w;
                routed_cnt_q   <= routed_cnt_q + {27'd0, routed_add_n};
                inv_drop_cnt_q <= inv_drop_cnt_q + {27'd0, inv_drop_add_n};
                if (|stalled_s1_q) begin
                    stall_cycles_q <= stall_cycles_q + 32'd1;
                end
            end
        end
    end

    assign routed_events_count_o       = routed_cnt_q;
    assign backpressure_stall_cycles_o = stall_cycles_q;
    assign invalid_dst_drop_count_o    = inv_drop_cnt_q;

endmodule
