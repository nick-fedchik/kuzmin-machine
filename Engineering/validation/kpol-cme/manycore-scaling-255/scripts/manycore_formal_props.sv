`timescale 1ns / 1ps

// ============================================================================
// Формальна SMT-верифікація багатоядерного кластера CFG-P (N = 2, Issue #255)
// Файл: manycore_formal_props.sv
// Солвер: yosys-smtbmc + Z3 (необмежена k-індукція, BMC та конструктивний Cover)
//
// Параметри верифікованої моделі:
//   NUM_CORES = 2, NUM_EXT_PORTS = 2, QUEUE_DEPTH = 4, NUM_CONCEPTS = 4,
//   DATA_WIDTH = 32, ADDR_WIDTH = 4 (0 внутрішніх assume у FORMAL_INDUCTION).
//
// Властивості:
//   - MC1_event_conservation      : точний баланс подій у кросбарі, вихідних
//                                   буферах та чергах банків (0 втрат, 0 дублів)
//   - MC2_rr_fairness             : чесний round-robin арбітраж цільового банку
//                                   (<= 3 обходи іншими джерелами, без голодування)
//   - MC3_dag_progress            : спадання топологічного рангу Ляпунова для
//                                   міжбанкового DAG (Bank 0 -> Bank 1) та
//                                   гарантоване звільнення черг у стан idle
//   - MC4_cyclic_deadlock_witness : конструктивний свідок досяжності взаємного
//                                   дедлока при циклічній підписці Bank 0 <-> Bank 1
//                                   на скінченних чергах + індуктивна незворотність
// ============================================================================

`ifndef KM_FORMAL_PIPE_STAGES
`define KM_FORMAL_PIPE_STAGES 1
`endif

module manycore_formal_props #(
    parameter int NUM_CORES       = 2,
    parameter int NUM_EXT_PORTS   = 2,
    parameter int QUEUE_DEPTH     = 4,
    parameter int NUM_CONCEPTS    = 4,
    parameter int DATA_WIDTH      = 32,
    parameter int ADDR_WIDTH      = 4,
    parameter int PIPELINE_STAGES = `KM_FORMAL_PIPE_STAGES
)(
    input  logic                                clk,
    input  logic                                rst_n,

    // Конфігураційний Порт A
    input  logic [3:0]                          cfg_bank_sel_i,
    input  logic [ADDR_WIDTH-1:0]               cfg_addr_i,
    input  logic [DATA_WIDTH-1:0]               cfg_wdata_i,
    input  logic [3:0]                          cfg_wstrb_i,
    input  logic                                cfg_we_i,

    // Зовнішні вхідні потоки подій
    input  logic [NUM_EXT_PORTS-1:0]            ext_valid_i,
    input  logic [NUM_EXT_PORTS*4-1:0]          ext_dst_bank_i,
    input  logic [NUM_EXT_PORTS*6-1:0]          ext_dst_cid_i,
    input  logic [NUM_EXT_PORTS*DATA_WIDTH-1:0] ext_param_i
);

    wire [DATA_WIDTH-1:0]           cfg_rdata_o;
    wire [NUM_CORES-1:0]            collision_detected_o;
    wire [NUM_EXT_PORTS-1:0]        ext_ready_o;
    wire [NUM_CORES-1:0]            core_busy_o;
    wire [NUM_CORES-1:0]            core_fifo_full_o;
    wire [NUM_CORES-1:0]            core_commit_pulse_o;
    wire [NUM_CORES-1:0]            core_reject_pulse_o;
    wire [NUM_CORES*DATA_WIDTH-1:0] core_last_state_o;
    (* keep *) wire                 cluster_busy_o;
    wire [31:0]                     total_events_processed_o;
    wire [31:0]                     total_committed_o;
    wire [31:0]                     total_rejected_o;
    wire [31:0]                     total_local_cascades_o;
    wire [31:0]                     total_remote_cascades_o;
    wire [31:0]                     xbar_routed_events_o;
    wire [31:0]                     backpressure_stall_cycles_o;
    wire [31:0]                     invalid_dst_drop_count_o;

    km_manycore_cluster #(
        .NUM_CORES(NUM_CORES),
        .NUM_EXT_PORTS(NUM_EXT_PORTS),
        .QUEUE_DEPTH(QUEUE_DEPTH),
        .NUM_CONCEPTS(NUM_CONCEPTS),
        .DATA_WIDTH(DATA_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH),
        .PIPELINE_STAGES(PIPELINE_STAGES)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .cfg_bank_sel_i(cfg_bank_sel_i),
        .cfg_addr_i(cfg_addr_i),
        .cfg_wdata_i(cfg_wdata_i),
        .cfg_wstrb_i(cfg_wstrb_i),
        .cfg_we_i(cfg_we_i),
        .cfg_rdata_o(cfg_rdata_o),
        .collision_detected_o(collision_detected_o),
        .ext_valid_i(ext_valid_i),
        .ext_ready_o(ext_ready_o),
        .ext_dst_bank_i(ext_dst_bank_i),
        .ext_dst_cid_i(ext_dst_cid_i),
        .ext_param_i(ext_param_i),
        .core_busy_o(core_busy_o),
        .core_fifo_full_o(core_fifo_full_o),
        .core_commit_pulse_o(core_commit_pulse_o),
        .core_reject_pulse_o(core_reject_pulse_o),
        .core_last_state_o(core_last_state_o),
        .cluster_busy_o(cluster_busy_o),
        .total_events_processed_o(total_events_processed_o),
        .total_committed_o(total_committed_o),
        .total_rejected_o(total_rejected_o),
        .total_local_cascades_o(total_local_cascades_o),
        .total_remote_cascades_o(total_remote_cascades_o),
        .xbar_routed_events_o(xbar_routed_events_o),
        .backpressure_stall_cycles_o(backpressure_stall_cycles_o),
        .invalid_dst_drop_count_o(invalid_dst_drop_count_o)
    );

    // Спостережні дроти внутрішнього стану (прив'язуються через Yosys `connect -set`)
    (* keep *) wire [1:0]  obs_node_tx_valid;
    (* keep *) wire [1:0]  obs_node_tx_ready;
    (* keep *) wire [7:0]  obs_node_tx_dst_bank;
    (* keep *) wire [11:0] obs_node_tx_dst_cid;
    (* keep *) wire [1:0]  obs_node_rx_valid;
    (* keep *) wire [1:0]  obs_node_rx_ready;

    (* keep *) wire [1:0]  obs_xbar_s1_valid;
    (* keep *) wire [1:0]  obs_xbar_pipe_valid;
    (* keep *) wire [1:0]  obs_xbar_accept_pulse;
    (* keep *) wire        obs_xbar_can_accept_0;
    (* keep *) wire        obs_xbar_can_accept_1;
    (* keep *) wire [1:0]  obs_xbar_rr_ptr_0;
    (* keep *) wire [1:0]  obs_xbar_rr_ptr_1;

    (* keep *) wire [3:0]  obs_n0_state_q;
    (* keep *) wire [2:0]  obs_n0_fifo_count_q;
    (* keep *) wire [1:0]  obs_n0_fifo_wr_ptr_q;
    (* keep *) wire [1:0]  obs_n0_fifo_rd_ptr_q;
    (* keep *) wire        obs_n0_pend_valid_q;
    (* keep *) wire [5:0]  obs_n0_active_cid_q;
    (* keep *) wire [31:0] obs_n0_desc_w2_q;
    (* keep *) wire [31:0] obs_n0_desc_w3_q;
    (* keep *) wire        obs_n0_sub_fire_w;
    (* keep *) wire        obs_n0_sub_valid_q;
    (* keep *) wire        obs_n0_sub_local_q;
    (* keep *) wire        obs_n0_sub_valid_comb_w;
    (* keep *) wire        obs_n0_sub_is_local_w;
    (* keep *) wire [3:0]  obs_n0_sub_dst_bank_w;
    (* keep *) wire [5:0]  obs_n0_sub_dst_cid_w;
    (* keep *) wire        obs_n0_b_we_q;
    (* keep *) wire [3:0]  obs_n0_b_addr_q;
    (* keep *) wire [3:0]  obs_n0_hold_bank_q;
    (* keep *) wire [31:0] obs_n0_ev_cnt_q;
    (* keep *) wire [31:0] obs_n0_loc_cnt_q;
    (* keep *) wire [31:0] obs_n0_rem_cnt_q;

    (* keep *) wire [3:0]  obs_n1_state_q;
    (* keep *) wire [2:0]  obs_n1_fifo_count_q;
    (* keep *) wire [1:0]  obs_n1_fifo_wr_ptr_q;
    (* keep *) wire [1:0]  obs_n1_fifo_rd_ptr_q;
    (* keep *) wire        obs_n1_pend_valid_q;
    (* keep *) wire [5:0]  obs_n1_active_cid_q;
    (* keep *) wire [31:0] obs_n1_desc_w2_q;
    (* keep *) wire [31:0] obs_n1_desc_w3_q;
    (* keep *) wire        obs_n1_sub_fire_w;
    (* keep *) wire        obs_n1_sub_valid_q;
    (* keep *) wire        obs_n1_sub_local_q;
    (* keep *) wire        obs_n1_sub_valid_comb_w;
    (* keep *) wire        obs_n1_sub_is_local_w;
    (* keep *) wire [3:0]  obs_n1_sub_dst_bank_w;
    (* keep *) wire [5:0]  obs_n1_sub_dst_cid_w;
    (* keep *) wire        obs_n1_b_we_q;
    (* keep *) wire [3:0]  obs_n1_b_addr_q;
    (* keep *) wire [3:0]  obs_n1_hold_bank_q;
    (* keep *) wire [31:0] obs_n1_ev_cnt_q;
    (* keep *) wire [31:0] obs_n1_loc_cnt_q;
    (* keep *) wire [31:0] obs_n1_rem_cnt_q;

    // Мінімальні зовнішні припущення середовища на первинних входах
    wire init_step_w = $initstate;
    logic past_valid = 1'b0;
    logic [6:0] step_cnt_q = 7'd0;

    always_ff @(posedge clk) begin
        past_valid <= 1'b1;
        if (!rst_n) begin
            step_cnt_q <= 7'd0;
        end else if (step_cnt_q != 7'h7f) begin
            step_cnt_q <= step_cnt_q + 7'd1;
        end
    end

    always @(*) begin
        if (init_step_w) begin
            assume (!rst_n);
        end else begin
            assume (rst_n);
        end
        assume (ext_dst_bank_i[3:0] < 4'd2);
        assume (ext_dst_bank_i[7:4] < 4'd2);
        assume (ext_dst_cid_i[5:0]  < 6'd4);
        assume (ext_dst_cid_i[11:6] < 6'd4);
        assume (cfg_bank_sel_i      < 4'd2);
    end

    // Спільне визначення взаємного циклічного дедлока Bank 0 <-> Bank 1
    wire xbar_trap_full_w = (PIPELINE_STAGES == 1)
        ? (obs_xbar_pipe_valid[0] && obs_xbar_pipe_valid[1])
        : (obs_xbar_pipe_valid[0] && obs_xbar_pipe_valid[1] &&
           obs_xbar_s1_valid[0] && obs_xbar_s1_valid[1]);

    wire cyclic_deadlock_trap_w =
        (obs_n0_state_q == 4'd8) && (obs_n1_state_q == 4'd8) &&
        obs_node_tx_valid[0] && (obs_node_tx_dst_bank[3:0] == 4'd1) &&
        obs_node_tx_valid[1] && (obs_node_tx_dst_bank[7:4] == 4'd0) &&
        (obs_n0_fifo_count_q == 3'd4) && (obs_n1_fifo_count_q == 3'd4) &&
        xbar_trap_full_w &&
        (obs_node_rx_ready == 2'b00) && (obs_node_tx_ready == 2'b00);

`ifdef FORMAL_SAFETY
    // ========================================================================
    // 1. Незалежні еталонні лічильники балансу подій для MC1_event_conservation
    // ========================================================================
    wire [3:0] src_valid_w = {ext_valid_i[1], ext_valid_i[0], obs_node_tx_valid[1], obs_node_tx_valid[0]};
    wire [3:0] src_ready_w = {ext_ready_o[1], ext_ready_o[0], obs_node_tx_ready[1], obs_node_tx_ready[0]};
    wire [3:0] src_fire_w  = src_valid_w & src_ready_w;

    wire [3:0] src_bank0_w = {
        (ext_dst_bank_i[7:4] == 4'd0),
        (ext_dst_bank_i[3:0] == 4'd0),
        (obs_node_tx_dst_bank[7:4] == 4'd0),
        (obs_node_tx_dst_bank[3:0] == 4'd0)
    };
    wire [3:0] src_bank1_w = {
        (ext_dst_bank_i[7:4] == 4'd1),
        (ext_dst_bank_i[3:0] == 4'd1),
        (obs_node_tx_dst_bank[7:4] == 4'd1),
        (obs_node_tx_dst_bank[3:0] == 4'd1)
    };

    wire [5:0] xbar_in_add_w =
        {5'd0, src_fire_w[0]} + {5'd0, src_fire_w[1]} +
        {5'd0, src_fire_w[2]} + {5'd0, src_fire_w[3]};
    wire [5:0] xbar_out_sub_w = {5'd0, obs_node_rx_valid[0] && obs_node_rx_ready[0]} +
                                {5'd0, obs_node_rx_valid[1] && obs_node_rx_ready[1]};
    wire [5:0] ext_in_add_w   = {5'd0, src_fire_w[2]} + {5'd0, src_fire_w[3]};

    wire [5:0] bank0_in_add_w =
        {5'd0, src_fire_w[0] & src_bank0_w[0]} + {5'd0, src_fire_w[1] & src_bank0_w[1]} +
        {5'd0, src_fire_w[2] & src_bank0_w[2]} + {5'd0, src_fire_w[3] & src_bank0_w[3]};
    wire [5:0] bank1_in_add_w =
        {5'd0, src_fire_w[0] & src_bank1_w[0]} + {5'd0, src_fire_w[1] & src_bank1_w[1]} +
        {5'd0, src_fire_w[2] & src_bank1_w[2]} + {5'd0, src_fire_w[3] & src_bank1_w[3]};

    wire rx0_fire_w = obs_node_rx_valid[0] && obs_node_rx_ready[0];
    wire rx1_fire_w = obs_node_rx_valid[1] && obs_node_rx_ready[1];

    wire n0_done_w     = (obs_n0_state_q == 4'd7);
    wire n1_done_w     = (obs_n1_state_q == 4'd7);
    wire n0_loc_fire_w = n0_done_w && obs_n0_sub_fire_w && (obs_n0_sub_dst_bank_w == 4'd0);
    wire n1_loc_fire_w = n1_done_w && obs_n1_sub_fire_w && (obs_n1_sub_dst_bank_w == 4'd1);
    wire n0_rem_fire_w = n0_done_w && obs_n0_sub_fire_w && (obs_n0_sub_dst_bank_w != 4'd0);
    wire n1_rem_fire_w = n1_done_w && obs_n1_sub_fire_w && (obs_n1_sub_dst_bank_w != 4'd1);

    // Точні 6-бітні регістри чистого балансу подій (діапазон 0..18 < 63, без переповнення mod 2^32)
    logic [5:0] f_xbar_net_q    = 6'd0;
    logic [5:0] f_b0_xbar_net_q = 6'd0;
    logic [5:0] f_b1_xbar_net_q = 6'd0;
    logic [5:0] f_n0_net_q      = 6'd0;
    logic [5:0] f_n1_net_q      = 6'd0;
    logic [5:0] f_tx0_net_q     = 6'd0;
    logic [5:0] f_tx1_net_q     = 6'd0;
    logic [5:0] f_cluster_net_q = 6'd0;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            f_xbar_net_q    <= 6'd0;
            f_b0_xbar_net_q <= 6'd0;
            f_b1_xbar_net_q <= 6'd0;
            f_n0_net_q      <= 6'd0;
            f_n1_net_q      <= 6'd0;
            f_tx0_net_q     <= 6'd0;
            f_tx1_net_q     <= 6'd0;
            f_cluster_net_q <= 6'd0;
        end else begin
            f_xbar_net_q    <= f_xbar_net_q + xbar_in_add_w - xbar_out_sub_w;
            f_b0_xbar_net_q <= f_b0_xbar_net_q + bank0_in_add_w - {5'd0, rx0_fire_w};
            f_b1_xbar_net_q <= f_b1_xbar_net_q + bank1_in_add_w - {5'd0, rx1_fire_w};
            f_n0_net_q      <= f_n0_net_q + {5'd0, rx0_fire_w} + {5'd0, n0_loc_fire_w} - {5'd0, n0_done_w};
            f_n1_net_q      <= f_n1_net_q + {5'd0, rx1_fire_w} + {5'd0, n1_loc_fire_w} - {5'd0, n1_done_w};
            f_tx0_net_q     <= f_tx0_net_q + {5'd0, n0_rem_fire_w} - {5'd0, src_fire_w[0]};
            f_tx1_net_q     <= f_tx1_net_q + {5'd0, n1_rem_fire_w} - {5'd0, src_fire_w[1]};
            f_cluster_net_q <= f_cluster_net_q + ext_in_add_w +
                               {5'd0, n0_loc_fire_w} + {5'd0, n1_loc_fire_w} +
                               {5'd0, n0_rem_fire_w} + {5'd0, n1_rem_fire_w} -
                               ({5'd0, n0_done_w} + {5'd0, n1_done_w});
        end
    end

    wire [5:0] b0_xbar_inflight_u6 =
        {5'd0, obs_xbar_pipe_valid[0]} + {5'd0, obs_xbar_s1_valid[0]};
    wire [5:0] b1_xbar_inflight_u6 =
        {5'd0, obs_xbar_pipe_valid[1]} + {5'd0, obs_xbar_s1_valid[1]};
    wire [5:0] xbar_inflight_u6 =
        b0_xbar_inflight_u6 + b1_xbar_inflight_u6;

    wire n0_in_eval_pipe_w = (obs_n0_state_q >= 4'd1) && (obs_n0_state_q <= 4'd7);
    wire n1_in_eval_pipe_w = (obs_n1_state_q >= 4'd1) && (obs_n1_state_q <= 4'd7);

    wire [5:0] n0_inflight_u6 =
        {3'd0, obs_n0_fifo_count_q} + {5'd0, obs_n0_pend_valid_q} + {5'd0, n0_in_eval_pipe_w};
    wire [5:0] n1_inflight_u6 =
        {3'd0, obs_n1_fifo_count_q} + {5'd0, obs_n1_pend_valid_q} + {5'd0, n1_in_eval_pipe_w};

    wire [5:0] n0_tx_inflight_u6 =
        {5'd0, obs_node_tx_valid[0]} + {5'd0, (obs_n0_state_q == 4'd8)};
    wire [5:0] n1_tx_inflight_u6 =
        {5'd0, obs_node_tx_valid[1]} + {5'd0, (obs_n1_state_q == 4'd8)};

    wire [5:0] cluster_total_inflight_u6 =
        xbar_inflight_u6 + n0_inflight_u6 + n1_inflight_u6 + n0_tx_inflight_u6 + n1_tx_inflight_u6;

    // ========================================================================
    // 2. Монітор чесності round-robin арбітражу для MC2_rr_fairness
    // ========================================================================
    wire [3:0] req_b0_w = src_valid_w & src_bank0_w;
    wire [3:0] req_b1_w = src_valid_w & src_bank1_w;

    logic [2:0] wait_b0_q [0:3];
    logic [2:0] wait_b1_q [0:3];

    integer ws;
    initial begin
        for (ws = 0; ws < 4; ws = ws + 1) begin
            wait_b0_q[ws] = 3'd0;
            wait_b1_q[ws] = 3'd0;
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            for (ws = 0; ws < 4; ws = ws + 1) begin
                wait_b0_q[ws] <= 3'd0;
                wait_b1_q[ws] <= 3'd0;
            end
        end else begin
            for (ws = 0; ws < 4; ws = ws + 1) begin
                if (req_b0_w[ws] && !src_ready_w[ws]) begin
                    if (obs_xbar_accept_pulse[0] && (wait_b0_q[ws] != 3'd7)) begin
                        wait_b0_q[ws] <= wait_b0_q[ws] + 3'd1;
                    end
                end else begin
                    wait_b0_q[ws] <= 3'd0;
                end

                if (req_b1_w[ws] && !src_ready_w[ws]) begin
                    if (obs_xbar_accept_pulse[1] && (wait_b1_q[ws] != 3'd7)) begin
                        wait_b1_q[ws] <= wait_b1_q[ws] + 3'd1;
                    end
                end else begin
                    wait_b1_q[ws] <= 3'd0;
                end
            end
        end
    end

    function automatic [2:0] rr_dist(input [1:0] ptr, input [1:0] src);
        logic [1:0] diff;
        begin
            diff = src - ptr;
            rr_dist = {1'b0, diff};
        end
    endfunction

    // ========================================================================
    // 3. Монітор спадання рангу Ляпунова для DAG та незворотності дедлока MC4
    // ========================================================================
    wire n0_dag_desc_ok_w =
        !((obs_n0_desc_w3_q[31:16] == 16'd0) && (obs_n0_desc_w3_q[14:10] == 5'd0) &&
          (obs_n0_desc_w3_q[15] || obs_n0_desc_w2_q[12] || (obs_n0_desc_w3_q[9:0] != 10'd0))) ||
        ((obs_n0_desc_w3_q[9:6] == 4'd1) && (obs_n0_desc_w3_q[5:0] < 6'd4)) ||
        ((obs_n0_desc_w3_q[9:6] == 4'd0) && (obs_n0_desc_w3_q[5:0] < 6'd4) &&
         (obs_n0_desc_w3_q[5:0] > obs_n0_active_cid_q));

    wire n1_dag_desc_ok_w =
        !((obs_n1_desc_w3_q[31:16] == 16'd0) && (obs_n1_desc_w3_q[14:10] == 5'd0) &&
          (obs_n1_desc_w3_q[15] || obs_n1_desc_w2_q[12] || (obs_n1_desc_w3_q[9:0] != 10'd0))) ||
        ((obs_n1_desc_w3_q[9:6] == 4'd1) && (obs_n1_desc_w3_q[5:0] < 6'd4) &&
         (obs_n1_desc_w3_q[5:0] > obs_n1_active_cid_q));

    // Ранг Ляпунова R(bank, cid) = (1 - bank)*4 + (3 - cid) у діапазоні 0..7
    wire [3:0] n0_src_rank_w = 4'd7 - {2'd0, obs_n0_active_cid_q[1:0]};
    wire [3:0] n0_dst_rank_w = ((obs_n0_sub_dst_bank_w == 4'd0) ? 4'd4 : 4'd0) +
                               (4'd3 - {2'd0, obs_n0_sub_dst_cid_w[1:0]});

    wire [3:0] n1_src_rank_w = 4'd3 - {2'd0, obs_n1_active_cid_q[1:0]};
    wire [3:0] n1_dst_rank_w = 4'd3 - {2'd0, obs_n1_sub_dst_cid_w[1:0]};

    logic prev_deadlock_trap_q = 1'b0;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            prev_deadlock_trap_q <= 1'b0;
        end else begin
            prev_deadlock_trap_q <= cyclic_deadlock_trap_w;
        end
    end

`ifdef FORMAL_INDUCTION
    // Допоміжні індуктивні леми досяжних станів (ВИКЛЮЧНО assert, 0 assume!)
    wire [1:0] n0_ptr_sum_w = obs_n0_fifo_rd_ptr_q + obs_n0_fifo_count_q[1:0];
    wire [1:0] n1_ptr_sum_w = obs_n1_fifo_rd_ptr_q + obs_n1_fifo_count_q[1:0];

    integer isrc;
    always @(*) begin
        if (rst_n) begin
            INV_n0_state_range:
                assert (obs_n0_state_q <= 4'd8);
            INV_n1_state_range:
                assert (obs_n1_state_q <= 4'd8);
            INV_n0_fifo_range:
                assert ((obs_n0_fifo_count_q <= 3'd4) && (n0_ptr_sum_w == obs_n0_fifo_wr_ptr_q));
            INV_n1_fifo_range:
                assert ((obs_n1_fifo_count_q <= 3'd4) && (n1_ptr_sum_w == obs_n1_fifo_wr_ptr_q));
            INV_n0_pend_full:
                assert (!obs_n0_pend_valid_q || ((obs_n0_state_q == 4'd0) && (obs_n0_fifo_count_q == 3'd4)));
            INV_n1_pend_full:
                assert (!obs_n1_pend_valid_q || ((obs_n1_state_q == 4'd0) && (obs_n1_fifo_count_q == 3'd4)));
            if (PIPELINE_STAGES == 1) begin
                INV_n0_wait_tx_has_tx_valid:
                    assert ((obs_n0_state_q != 4'd8) || obs_node_tx_valid[0]);
                INV_n1_wait_tx_has_tx_valid:
                    assert ((obs_n1_state_q != 4'd8) || obs_node_tx_valid[1]);
            end else begin
                INV_n0_sub_predecode:
                    assert ((obs_n0_state_q != 4'd7) ||
                            ((obs_n0_sub_valid_q == obs_n0_sub_valid_comb_w) &&
                             (obs_n0_sub_local_q == obs_n0_sub_is_local_w)));
                INV_n1_sub_predecode:
                    assert ((obs_n1_state_q != 4'd7) ||
                            ((obs_n1_sub_valid_q == obs_n1_sub_valid_comb_w) &&
                             (obs_n1_sub_local_q == obs_n1_sub_is_local_w)));
            end
            INV_int_dst_bank_valid:
                assert ((!obs_node_tx_valid[0] || (obs_node_tx_dst_bank[3:0] == 4'd1)) &&
                        (!obs_node_tx_valid[1] || (obs_node_tx_dst_bank[7:4] == 4'd0)) &&
                        ((obs_n0_state_q != 4'd8) || (obs_n0_hold_bank_q == 4'd1)) &&
                        ((obs_n1_state_q != 4'd8) || (obs_n1_hold_bank_q == 4'd0)));
            INV_port_b_w0_only:
                assert ((!obs_n0_b_we_q || (obs_n0_b_addr_q[1:0] == 2'b00)) &&
                        (!obs_n1_b_we_q || (obs_n1_b_addr_q[1:0] == 2'b00)));

            for (isrc = 0; isrc < 4; isrc = isrc + 1) begin
                assert ((wait_b0_q[isrc] + rr_dist(obs_xbar_rr_ptr_0, isrc[1:0])) <= 3'd3);
                assert ((wait_b1_q[isrc] + rr_dist(obs_xbar_rr_ptr_1, isrc[1:0])) <= 3'd3);
            end
        end
    end
`endif

    logic [3:0] fair_src_ok_w;
    always @(*) begin
        for (int s_idx = 0; s_idx < 4; s_idx = s_idx + 1) begin
            fair_src_ok_w[s_idx] =
                (wait_b0_q[s_idx] <= 3'd3) &&
                (wait_b1_q[s_idx] <= 3'd3) &&
                (!((wait_b0_q[s_idx] == 3'd3) && req_b0_w[s_idx] && obs_xbar_can_accept_0) || src_ready_w[s_idx]) &&
                (!((wait_b1_q[s_idx] == 3'd3) && req_b1_w[s_idx] && obs_xbar_can_accept_1) || src_ready_w[s_idx]);
        end
    end

    // Основні властивості безпеки та чесності MC1, MC2, MC3 (крок рангу), MC4 (незворотність)
    always @(*) begin
        if (rst_n) begin
`ifndef ONLY_MC2
            MC1_event_conservation:
                assert ((f_xbar_net_q == xbar_inflight_u6) &&
                        (invalid_dst_drop_count_o == 32'd0) &&
                        (f_b0_xbar_net_q == b0_xbar_inflight_u6) &&
                        (f_b1_xbar_net_q == b1_xbar_inflight_u6) &&
                        (f_n0_net_q == n0_inflight_u6) &&
                        (f_n1_net_q == n1_inflight_u6) &&
                        (f_tx0_net_q == n0_tx_inflight_u6) &&
                        (f_tx1_net_q == n1_tx_inflight_u6) &&
                        (f_cluster_net_q == cluster_total_inflight_u6));
`endif

`ifndef ONLY_MC1
            MC2_rr_fairness:
                assert (fair_src_ok_w == 4'b1111);
`endif

`ifndef ONLY_MC1
`ifndef ONLY_MC2
            // MC3 (індуктивна лема спадання рангу Ляпунова для міжбанкового DAG Bank 0 -> Bank 1)
            if ((obs_n0_state_q == 4'd7) && n0_dag_desc_ok_w && obs_n0_sub_fire_w) begin
                MC3_dag_lyapunov_rank_n0:
                    assert (n0_dst_rank_w < n0_src_rank_w);
            end
            if ((obs_n1_state_q == 4'd7) && n1_dag_desc_ok_w && obs_n1_sub_fire_w) begin
                MC3_dag_lyapunov_rank_n1:
                    assert ((obs_n1_sub_dst_bank_w == 4'd1) && (n1_dst_rank_w < n1_src_rank_w));
            end

            // MC4 (індуктивна незворотність взаємного циклічного дедлока Bank 0 <-> Bank 1)
            if (past_valid && prev_deadlock_trap_q) begin
                MC4_deadlock_permanence:
                    assert (cyclic_deadlock_trap_w && cluster_busy_o &&
                            (core_commit_pulse_o == 2'b00) && (core_reject_pulse_o == 2'b00));
            end
`endif
`endif
        end
    end
`endif

`ifdef FORMAL_DAG_BMC
    // ========================================================================
    // MC3_dag_progress: конкретна BMC-перевірка гарантованого переходу в idle
    // для довільного міжбанкового DAG (Bank 0 -> Bank 1, без зворотних ребер
    // Bank 1 -> Bank 0) після довільного 2-портового пакету зовнішніх подій.
    // ========================================================================
    always @(*) begin
        if (rst_n) begin
            if (step_cnt_q <= 7'd6) begin
                // Фаза ініціалізації правил: дозволені лише ациклічні ребра Bank 0 -> Bank 1 (без Bank 1 -> Bank 0)
                assume (ext_valid_i == 2'b00);
                if (cfg_we_i && (cfg_bank_sel_i == 4'd0) && (cfg_addr_i[1:0] == 2'b10)) begin
                    assume (!cfg_wdata_i[12]);
                end
                if (cfg_we_i && (cfg_bank_sel_i == 4'd0) && (cfg_addr_i[1:0] == 2'b11)) begin
                    assume ((cfg_wdata_i == 32'hffff_ffff) ||
                            ((cfg_wdata_i[31:16] == 16'd0) &&
                             (cfg_wdata_i[14:10] == 5'd0) &&
                             (cfg_wdata_i[9:6] == 4'd1) &&
                             (cfg_wdata_i[5:0] < 6'd4)));
                end
                if (cfg_we_i && (cfg_bank_sel_i == 4'd1) && (cfg_addr_i[1:0] == 2'b10)) begin
                    assume (!cfg_wdata_i[12]);
                end
                if (cfg_we_i && (cfg_bank_sel_i == 4'd1) && (cfg_addr_i[1:0] == 2'b11)) begin
                    assume (cfg_wdata_i == 32'hffff_ffff);
                end
            end else if (step_cnt_q <= 7'd8) begin
                // Фаза конкурентної інжекції довільних подій на обох портах ext[0..1] (до 4 подій)
                assume (!cfg_we_i);
            end else begin
                // Фаза автономного дренування черг та міжбанкових каскадів
                assume (!cfg_we_i);
                assume (ext_valid_i == 2'b00);
            end

            if (step_cnt_q == ((PIPELINE_STAGES == 1) ? 7'd44 : 7'd48)) begin
                MC3_dag_progress:
                    assert (!cluster_busy_o &&
                            (obs_n0_fifo_count_q == 3'd0) &&
                            (obs_n1_fifo_count_q == 3'd0) &&
                            (obs_xbar_s1_valid == 2'b00) &&
                            (obs_xbar_pipe_valid == 2'b00) &&
                            (obs_node_tx_valid == 2'b00));
            end
        end
    end
`endif

`ifdef FORMAL_COVER
    // ========================================================================
    // Конструктивні свідки досяжності (C1, C2 та MC4_cyclic_deadlock_witness)
    // ========================================================================
    logic cov_rem_casc_seen_q  = 1'b0;
    logic cov_bank1_comm_q     = 1'b0;
    logic cov_contention_q     = 1'b0;

    wire [2:0] b0_req_cnt_w =
        {2'd0, obs_node_tx_valid[1] && (obs_node_tx_dst_bank[7:4] == 4'd0)} +
        {2'd0, ext_valid_i[0]       && (ext_dst_bank_i[3:0] == 4'd0)} +
        {2'd0, ext_valid_i[1]       && (ext_dst_bank_i[7:4] == 4'd0)};

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            cov_rem_casc_seen_q <= 1'b0;
            cov_bank1_comm_q    <= 1'b0;
            cov_contention_q    <= 1'b0;
        end else begin
            if (obs_node_tx_valid[0] && obs_node_tx_ready[0]) begin
                cov_rem_casc_seen_q <= 1'b1;
            end
            if (cov_rem_casc_seen_q && core_commit_pulse_o[1]) begin
                cov_bank1_comm_q <= 1'b1;
            end
            if (b0_req_cnt_w >= 3'd2) begin
                cov_contention_q <= 1'b1;
            end
        end
    end

    always @(*) begin
        if (past_valid && rst_n) begin
            C1_interbank_cascade_to_idle:
                cover (cov_bank1_comm_q && !cluster_busy_o && !cfg_we_i && (ext_valid_i == 2'b00));
            C2_many_to_one_contention:
                cover (cov_contention_q && cov_bank1_comm_q && !cluster_busy_o);
            MC4_cyclic_deadlock_witness:
                cover (cyclic_deadlock_trap_w && !cfg_we_i && (ext_valid_i == 2'b00));
        end
    end
`endif

endmodule
