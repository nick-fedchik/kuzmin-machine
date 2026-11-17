`timescale 1ns / 1ps

// ============================================================================
// Файл: km_manycore_cluster.sv
// Призначення: Багатоядерна просторова матриця CFG-P (N = 1, 2, 4, 8 вузлів,
// Issue #255). Кожен вузол `km_cluster_node` використовує незмінні базові модулі
// `km_concept_bram.sv` та `km_concept_micro_engine.sv` (`kpol_txn_gate_v2.sv`),
// підтримує локальні каскади за 0 тактів кросбара (`dst_bank == CORE_ID`) та
// міжбанкові каскади (`dst_bank != CORE_ID`) через однослотовий вихідний буфер
// з рукостисканням `valid && ready` без прихованої втрати подій.
//
// Кодування поля підписника W3 (descriptor_i[127:96]):
//   - W3[5:0]  = dst_cid  (0 .. NUM_CONCEPTS-1)
//   - W3[9:6]  = dst_bank (0 .. NUM_CORES-1)
//   - W3[15]   = явний прапорець підписки (дозволяє перехід у {bank=0, cid=0});
//                також підтримується сумісність із базовим CFG-P: W2[12] == 1
//                (guard_flags[4]) або W3[9:0] != 0 при нульових старших бітах.
//   - W3 == 32'hFFFF_FFFF або нульовий дескриптор (W2[12]==0, W3==0) -> підписка вимкнена.
// ============================================================================

/* verilator lint_off DECLFILENAME */
module km_cluster_node #(
    parameter int CORE_ID         = 0,
    parameter int NUM_CORES       = 4,
    parameter int QUEUE_DEPTH     = 16,
    parameter int NUM_CONCEPTS    = 64,
    parameter int DATA_WIDTH      = 32,
    parameter int ADDR_WIDTH      = 8,
    parameter int PIPELINE_STAGES = 1
)(
    input  logic                   clk,
    input  logic                   rst_n,

    // Конфігураційний Порт A приватного банку BRAM
    input  logic [ADDR_WIDTH-1:0]  cfg_addr_i,
    input  logic [DATA_WIDTH-1:0]  cfg_wdata_i,
    input  logic [3:0]             cfg_wstrb_i,
    input  logic                   cfg_we_i,
    output logic [DATA_WIDTH-1:0]  cfg_rdata_o,
    output logic                   collision_detected_o,

    // Вхідний порт подій від комутатора km_event_crossbar
    input  logic                   rx_valid_i,
    input  logic [5:0]             rx_cid_i,
    input  logic [DATA_WIDTH-1:0]  rx_param_i,
    output logic                   rx_ready_o,

    // Вихідний міжбанковий порт каскадів до km_event_crossbar
    output logic                   tx_valid_o,
    input  logic                   tx_ready_i,
    output logic [3:0]             tx_dst_bank_o,
    output logic [5:0]             tx_dst_cid_o,
    output logic [DATA_WIDTH-1:0]  tx_param_o,

    // Статус та телеметрія вузла
    output logic                   busy_o,
    output logic                   fifo_full_o,
    output logic                   commit_pulse_o,
    output logic                   reject_pulse_o,
    output logic [31:0]            events_processed_count_o,
    output logic [31:0]            committed_count_o,
    output logic [31:0]            rejected_count_o,
    output logic [31:0]            local_cascade_count_o,
    output logic [31:0]            remote_cascade_count_o,
    output logic [31:0]            tx_stall_cycles_o,
    output logic [DATA_WIDTH-1:0]  last_committed_state_o
);

    typedef enum logic [3:0] {
        ST_IDLE          = 4'd0,
        ST_REQ_W0        = 4'd1,
        ST_REQ_W1        = 4'd2,
        ST_REQ_W2        = 4'd3,
        ST_REQ_W3        = 4'd4,
        ST_CAP_W3_STROBE = 4'd5,
        ST_WAIT_GATE     = 4'd6,
        ST_EVAL_GATE     = 4'd7,
        ST_WAIT_TX       = 4'd8
    } node_state_t;

    node_state_t state_q;

    localparam int PTR_WIDTH  = (QUEUE_DEPTH > 1) ? $clog2(QUEUE_DEPTH) : 1;
    localparam int CID_ADDR_W = ADDR_WIDTH - 2;

    localparam logic [31:0]          CORE_ID_U32      = CORE_ID;
    localparam logic [3:0]           CORE_ID_U4       = CORE_ID_U32[3:0];
    localparam logic [31:0]          NUM_CORES_U32    = NUM_CORES;
    localparam logic [31:0]          NUM_CONCEPTS_U32 = NUM_CONCEPTS;
    localparam logic [31:0]          DEPTH_U32        = QUEUE_DEPTH;
    localparam logic [PTR_WIDTH:0]   DEPTH_CNT        = DEPTH_U32[PTR_WIDTH:0];
    localparam logic [31:0]          ONE_U32          = 32'd1;
    localparam logic [PTR_WIDTH-1:0] PTR_ONE          = ONE_U32[PTR_WIDTH-1:0];

    // Внутрішня черга подій FIFO вузла
    logic [5:0]            fifo_cid_q   [QUEUE_DEPTH];
    logic [DATA_WIDTH-1:0] fifo_param_q [QUEUE_DEPTH];
    logic [PTR_WIDTH-1:0]  fifo_wr_ptr_q;
    logic [PTR_WIDTH-1:0]  fifo_rd_ptr_q;
    logic [PTR_WIDTH:0]    fifo_count_q;

    wire [PTR_WIDTH-1:0] rd_ptr_next1 = (({1'b0, fifo_rd_ptr_q} + {{PTR_WIDTH{1'b0}}, 1'b1}) >= DEPTH_CNT)
                                      ? '0 : (fifo_rd_ptr_q + PTR_ONE);
    wire [PTR_WIDTH-1:0] wr_ptr_next1 = (({1'b0, fifo_wr_ptr_q} + {{PTR_WIDTH{1'b0}}, 1'b1}) >= DEPTH_CNT)
                                      ? '0 : (fifo_wr_ptr_q + PTR_ONE);
    wire [PTR_WIDTH-1:0] wr_ptr_next2 = (({1'b0, wr_ptr_next1} + {{PTR_WIDTH{1'b0}}, 1'b1}) >= DEPTH_CNT)
                                      ? '0 : (wr_ptr_next1 + PTR_ONE);

    // 1-слотовий резервний буфер локального каскаду при повному FIFO (B5 v2)
    logic                  cascade_pending_valid_q;
    logic [5:0]            cascade_pending_cid_q;
    logic [DATA_WIDTH-1:0] cascade_pending_param_q;

    // 1-слотовий вихідний регістровий буфер міжбанкового каскаду + регістр утримання ST_WAIT_TX
    logic                  tx_valid_q;
    logic [3:0]            tx_dst_bank_q;
    logic [5:0]            tx_dst_cid_q;
    logic [DATA_WIDTH-1:0] tx_param_q;

    logic [3:0]            hold_tx_bank_q;
    logic [5:0]            hold_tx_cid_q;
    logic [DATA_WIDTH-1:0] hold_tx_param_q;

    // Активна подія та буфер 128-бітного дескриптора
    logic [5:0]            active_cid_q;
    logic [DATA_WIDTH-1:0] active_param_q;
    logic [31:0]           desc_w0_q;
    logic [31:0]           desc_w1_q;
    logic [31:0]           desc_w2_q;
    logic [31:0]           desc_w3_q;

    // Порт B приватного банку BRAM
    logic [ADDR_WIDTH-1:0] bram_b_addr_q;
    logic [DATA_WIDTH-1:0] bram_b_wdata_q;
    logic [3:0]            bram_b_wstrb_q;
    logic                  bram_b_we_q;
    wire  [DATA_WIDTH-1:0] bram_b_rdata_w;

    km_concept_bram #(
        .NUM_CONCEPTS(NUM_CONCEPTS),
        .DATA_WIDTH(DATA_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) bram_inst (
        .clk(clk),
        .rst_n(rst_n),
        .a_addr_i(cfg_addr_i),
        .a_wdata_i(cfg_wdata_i),
        .a_wstrb_i(cfg_wstrb_i),
        .a_we_i(cfg_we_i),
        .a_rdata_o(cfg_rdata_o),
        .b_addr_i(bram_b_addr_q),
        .b_wdata_i(bram_b_wdata_q),
        .b_wstrb_i(bram_b_wstrb_q),
        .b_we_i(bram_b_we_q),
        .b_rdata_o(bram_b_rdata_w),
        .collision_detected_o(collision_detected_o)
    );

    wire [127:0] active_descriptor_w = {desc_w3_q, desc_w2_q, desc_w1_q, desc_w0_q};

    logic                 cme_event_valid_q;
    wire                  cme_committed;
    /* verilator lint_off UNUSEDSIGNAL */
    wire                  cme_rejected_unused;
    wire                  cme_hazard_obs_unused;
    wire                  cme_unknown_haz_unused;
    wire                  cme_state_changed_unused;
    wire [31:0]           cme_sub_cid_unused;
    wire                  cme_trig_sub_unused;
    /* verilator lint_on UNUSEDSIGNAL */
    wire [DATA_WIDTH-1:0] cme_updated_state;

    km_concept_micro_engine #(
        .DATA_WIDTH(DATA_WIDTH)
    ) cme_inst (
        .clk(clk),
        .rst_n(rst_n),
        .event_valid_i(cme_event_valid_q),
        .event_id_i(8'h01),
        .event_param_i(active_param_q),
        .descriptor_i(active_descriptor_w),
        .committed_o(cme_committed),
        .rejected_o(cme_rejected_unused),
        .hazard_observed_o(cme_hazard_obs_unused),
        .unknown_hazard_o(cme_unknown_haz_unused),
        .updated_state_o(cme_updated_state),
        .state_changed_o(cme_state_changed_unused),
        .subscriber_cid_o(cme_sub_cid_unused),
        .trigger_subscriber_o(cme_trig_sub_unused)
    );

    // Декодування 10-бітної адреси підписника {dst_bank[3:0], dst_cid[5:0]} у W3
    wire [5:0] sub_dst_cid_w   = desc_w3_q[5:0];
    wire [3:0] sub_dst_bank_w  = desc_w3_q[9:6];
    wire       sub_hi_clean_w  = (desc_w3_q[31:16] == 16'd0) && (desc_w3_q[14:10] == 5'd0);
    wire       sub_active_w    = sub_hi_clean_w &&
                                 (desc_w3_q[15] || desc_w2_q[12] || (desc_w3_q[9:0] != 10'd0));
    wire       sub_target_ok_w = ({28'd0, sub_dst_bank_w} < NUM_CORES_U32) &&
                                 ({26'd0, sub_dst_cid_w} < NUM_CONCEPTS_U32);
    wire       sub_is_self_w   = (sub_dst_bank_w == CORE_ID_U4) && (sub_dst_cid_w == active_cid_q);
    wire       sub_valid_comb_w = sub_active_w && sub_target_ok_w && !sub_is_self_w;
    wire       sub_is_local_w  = (sub_dst_bank_w == CORE_ID_U4);

    logic      sub_valid_q;
    logic      sub_local_q;

    wire       sub_fire_w      = (PIPELINE_STAGES == 1)
                               ? (cme_committed && sub_valid_comb_w)
                               : (cme_committed && sub_valid_q);
    wire       sub_loc_eff_w   = (PIPELINE_STAGES == 1) ? sub_is_local_w : sub_local_q;

    // Управління локальною чергою FIFO (локальний каскад має пріоритет над rx_valid_i)
    wire dequeue_req        = (state_q == ST_IDLE) && (fifo_count_q > 0);
    wire local_cascade_req  = (state_q == ST_EVAL_GATE) && sub_fire_w && sub_loc_eff_w;
    wire remote_cascade_req = (state_q == ST_EVAL_GATE) && sub_fire_w && !sub_loc_eff_w;

    wire                  local_cascade_valid = cascade_pending_valid_q || local_cascade_req;
    wire [5:0]            local_cascade_cid   = cascade_pending_valid_q ? cascade_pending_cid_q : sub_dst_cid_w;
    wire [DATA_WIDTH-1:0] local_cascade_param = cascade_pending_valid_q ? cascade_pending_param_q : cme_updated_state;

    wire [PTR_WIDTH+1:0] rx_slots_needed = local_cascade_req
        ? {{PTR_WIDTH{1'b0}}, 2'd2}
        : {{PTR_WIDTH{1'b0}}, 2'd1};

    wire rx_ready_p1_w = !cascade_pending_valid_q &&
                         (({1'b0, fifo_count_q} + rx_slots_needed) <= {1'b0, DEPTH_CNT});
    wire rx_ready_p2_w = !cascade_pending_valid_q &&
                         (state_q != ST_EVAL_GATE) &&
                         (fifo_count_q < DEPTH_CNT);

    assign rx_ready_o  = (PIPELINE_STAGES == 1) ? rx_ready_p1_w : rx_ready_p2_w;
    assign fifo_full_o = (fifo_count_q == DEPTH_CNT);

    wire local_cascade_enq = local_cascade_valid && ((fifo_count_q < DEPTH_CNT) || dequeue_req);
    wire rx_accept         = rx_valid_i && rx_ready_o;
    wire fifo_we_p2_w      = local_cascade_enq || rx_accept;
    wire [5:0]            fifo_wcid_p2_w   = local_cascade_enq ? local_cascade_cid   : rx_cid_i;
    wire [DATA_WIDTH-1:0] fifo_wparam_p2_w = local_cascade_enq ? local_cascade_param : rx_param_i;

    wire [PTR_WIDTH:0] enq_delta_p1 = (local_cascade_enq && rx_accept) ? {{(PTR_WIDTH-1){1'b0}}, 2'd2}
                                    : ((local_cascade_enq || rx_accept) ? {{PTR_WIDTH{1'b0}}, 1'b1} : '0);
    wire [PTR_WIDTH:0] enq_delta_p2 = fifo_we_p2_w ? {{PTR_WIDTH{1'b0}}, 1'b1} : '0;
    wire [PTR_WIDTH:0] enq_delta    = (PIPELINE_STAGES == 1) ? enq_delta_p1 : enq_delta_p2;
    wire [PTR_WIDTH:0] deq_delta    = dequeue_req ? {{PTR_WIDTH{1'b0}}, 1'b1} : '0;

    // Рукотискання вихідного міжбанкового буфера до кросбара
    wire tx_buf_free_w = (PIPELINE_STAGES == 1) ? (!tx_valid_q || tx_ready_i) : !tx_valid_q;
    wire tx_push_eval  = remote_cascade_req && tx_buf_free_w;
    wire tx_push_wait  = (state_q == ST_WAIT_TX) && tx_buf_free_w;

    assign tx_valid_o    = tx_valid_q;
    assign tx_dst_bank_o = tx_dst_bank_q;
    assign tx_dst_cid_o  = tx_dst_cid_q;
    assign tx_param_o    = tx_param_q;

    // Статистичні лічильники вузла
    logic [31:0]           ev_count_q;
    logic [31:0]           comm_count_q;
    logic [31:0]           rej_count_q;
    logic [31:0]           loc_casc_count_q;
    logic [31:0]           rem_casc_count_q;
    logic [31:0]           tx_stall_cnt_q;
    logic [DATA_WIDTH-1:0] last_state_q;

    assign busy_o                   = (state_q != ST_IDLE) || (fifo_count_q != 0) ||
                                      cascade_pending_valid_q || tx_valid_q;
    assign commit_pulse_o           = (state_q == ST_EVAL_GATE) && cme_committed;
    assign reject_pulse_o           = (state_q == ST_EVAL_GATE) && !cme_committed;
    assign events_processed_count_o = ev_count_q;
    assign committed_count_o        = comm_count_q;
    assign rejected_count_o         = rej_count_q;
    assign local_cascade_count_o    = loc_casc_count_q;
    assign remote_cascade_count_o   = rem_casc_count_q;
    assign tx_stall_cycles_o        = tx_stall_cnt_q;
    assign last_committed_state_o   = last_state_q;

    wire [5:0] deq_cid_w = fifo_cid_q[fifo_rd_ptr_q];

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q                 <= ST_IDLE;
            bram_b_addr_q           <= '0;
            bram_b_wdata_q          <= '0;
            bram_b_wstrb_q          <= 4'b0000;
            bram_b_we_q             <= 1'b0;
            cme_event_valid_q       <= 1'b0;

            fifo_wr_ptr_q           <= '0;
            fifo_rd_ptr_q           <= '0;
            fifo_count_q            <= '0;

            cascade_pending_valid_q <= 1'b0;
            cascade_pending_cid_q   <= '0;
            cascade_pending_param_q <= '0;

            tx_valid_q              <= 1'b0;
            tx_dst_bank_q           <= '0;
            tx_dst_cid_q            <= '0;
            tx_param_q              <= '0;
            hold_tx_bank_q          <= '0;
            hold_tx_cid_q           <= '0;
            hold_tx_param_q         <= '0;

            active_cid_q            <= '0;
            active_param_q          <= '0;
            desc_w0_q               <= '0;
            desc_w1_q               <= '0;
            desc_w2_q               <= '0;
            desc_w3_q               <= '0;
            sub_valid_q             <= 1'b0;
            sub_local_q             <= 1'b0;

            ev_count_q              <= 32'd0;
            comm_count_q            <= 32'd0;
            rej_count_q             <= 32'd0;
            loc_casc_count_q        <= 32'd0;
            rem_casc_count_q        <= 32'd0;
            tx_stall_cnt_q          <= 32'd0;
            last_state_q            <= '0;
        end else begin
            bram_b_we_q       <= 1'b0;
            cme_event_valid_q <= 1'b0;

            // 1. Локальна черга подій FIFO
            if (dequeue_req) begin
                fifo_rd_ptr_q <= rd_ptr_next1;
            end

            if (PIPELINE_STAGES == 1) begin
                if (local_cascade_enq && rx_accept) begin
                    fifo_cid_q[fifo_wr_ptr_q]   <= local_cascade_cid;
                    fifo_param_q[fifo_wr_ptr_q] <= local_cascade_param;
                    fifo_cid_q[wr_ptr_next1]    <= rx_cid_i;
                    fifo_param_q[wr_ptr_next1]  <= rx_param_i;
                    fifo_wr_ptr_q               <= wr_ptr_next2;
                    cascade_pending_valid_q     <= 1'b0;
                end else if (local_cascade_enq) begin
                    fifo_cid_q[fifo_wr_ptr_q]   <= local_cascade_cid;
                    fifo_param_q[fifo_wr_ptr_q] <= local_cascade_param;
                    fifo_wr_ptr_q               <= wr_ptr_next1;
                    cascade_pending_valid_q     <= 1'b0;
                end else if (rx_accept) begin
                    fifo_cid_q[fifo_wr_ptr_q]   <= rx_cid_i;
                    fifo_param_q[fifo_wr_ptr_q] <= rx_param_i;
                    fifo_wr_ptr_q               <= wr_ptr_next1;
                end else if (local_cascade_req) begin
                    cascade_pending_valid_q <= 1'b1;
                    cascade_pending_cid_q   <= sub_dst_cid_w;
                    cascade_pending_param_q <= cme_updated_state;
                end
            end else begin
                if (fifo_we_p2_w) begin
                    fifo_cid_q[fifo_wr_ptr_q]   <= fifo_wcid_p2_w;
                    fifo_param_q[fifo_wr_ptr_q] <= fifo_wparam_p2_w;
                    fifo_wr_ptr_q               <= wr_ptr_next1;
                end
                if (local_cascade_enq) begin
                    cascade_pending_valid_q <= 1'b0;
                end else if (local_cascade_req) begin
                    cascade_pending_valid_q <= 1'b1;
                    cascade_pending_cid_q   <= sub_dst_cid_w;
                    cascade_pending_param_q <= cme_updated_state;
                end
            end

            fifo_count_q <= fifo_count_q + enq_delta - deq_delta;

            // 2. Однослотовий міжбанковий вихідний буфер tx_*
            if (tx_push_eval) begin
                tx_valid_q    <= 1'b1;
                tx_dst_bank_q <= sub_dst_bank_w;
                tx_dst_cid_q  <= sub_dst_cid_w;
                tx_param_q    <= cme_updated_state;
            end else if (tx_push_wait) begin
                tx_valid_q    <= 1'b1;
                tx_dst_bank_q <= hold_tx_bank_q;
                tx_dst_cid_q  <= hold_tx_cid_q;
                tx_param_q    <= hold_tx_param_q;
            end else if (tx_valid_q && tx_ready_i) begin
                tx_valid_q <= 1'b0;
            end

            // 3. Скінченний автомат обробки концепту
            case (state_q)
                ST_IDLE: begin
                    if (fifo_count_q > 0) begin
                        active_cid_q   <= deq_cid_w;
                        active_param_q <= fifo_param_q[fifo_rd_ptr_q];
                        bram_b_addr_q  <= {deq_cid_w[CID_ADDR_W-1:0], 2'b00};
                        state_q        <= ST_REQ_W0;
                    end
                end

                ST_REQ_W0: begin
                    bram_b_addr_q <= {active_cid_q[CID_ADDR_W-1:0], 2'b01};
                    state_q       <= ST_REQ_W1;
                end

                ST_REQ_W1: begin
                    desc_w0_q     <= bram_b_rdata_w;
                    bram_b_addr_q <= {active_cid_q[CID_ADDR_W-1:0], 2'b10};
                    state_q       <= ST_REQ_W2;
                end

                ST_REQ_W2: begin
                    desc_w1_q     <= bram_b_rdata_w;
                    bram_b_addr_q <= {active_cid_q[CID_ADDR_W-1:0], 2'b11};
                    state_q       <= ST_REQ_W3;
                end

                ST_REQ_W3: begin
                    desc_w2_q <= bram_b_rdata_w;
                    state_q   <= ST_CAP_W3_STROBE;
                end

                ST_CAP_W3_STROBE: begin
                    desc_w3_q         <= bram_b_rdata_w;
                    cme_event_valid_q <= 1'b1;
                    state_q           <= ST_WAIT_GATE;
                end

                ST_WAIT_GATE: begin
                    cme_event_valid_q <= 1'b0;
                    sub_valid_q       <= sub_valid_comb_w;
                    sub_local_q       <= sub_is_local_w;
                    state_q           <= ST_EVAL_GATE;
                end

                ST_EVAL_GATE: begin
                    ev_count_q <= ev_count_q + 32'd1;

                    if (cme_committed) begin
                        comm_count_q   <= comm_count_q + 32'd1;
                        last_state_q   <= cme_updated_state;
                        bram_b_addr_q  <= {active_cid_q[CID_ADDR_W-1:0], 2'b00};
                        bram_b_wdata_q <= cme_updated_state;
                        bram_b_wstrb_q <= 4'b1111;
                        bram_b_we_q    <= 1'b1;

                        if (sub_fire_w && sub_loc_eff_w) begin
                            loc_casc_count_q <= loc_casc_count_q + 32'd1;
                            state_q          <= ST_IDLE;
                        end else if (sub_fire_w && !sub_loc_eff_w) begin
                            rem_casc_count_q <= rem_casc_count_q + 32'd1;
                            hold_tx_bank_q   <= sub_dst_bank_w;
                            hold_tx_cid_q    <= sub_dst_cid_w;
                            hold_tx_param_q  <= cme_updated_state;
                            if (tx_buf_free_w) begin
                                state_q <= ST_IDLE;
                            end else begin
                                tx_stall_cnt_q <= tx_stall_cnt_q + 32'd1;
                                state_q        <= ST_WAIT_TX;
                            end
                        end else begin
                            state_q <= ST_IDLE;
                        end
                    end else begin
                        rej_count_q <= rej_count_q + 32'd1;
                        state_q     <= ST_IDLE;
                    end
                end

                ST_WAIT_TX: begin
                    if (tx_buf_free_w) begin
                        state_q <= ST_IDLE;
                    end else begin
                        tx_stall_cnt_q <= tx_stall_cnt_q + 32'd1;
                    end
                end

                default: state_q <= ST_IDLE;
            endcase
        end
    end

endmodule
/* verilator lint_on DECLFILENAME */


module km_manycore_cluster #(
    parameter int NUM_CORES       = 4,
    parameter int NUM_EXT_PORTS   = NUM_CORES,
    parameter int QUEUE_DEPTH     = 16,
    parameter int NUM_CONCEPTS    = 64,
    parameter int DATA_WIDTH      = 32,
    parameter int ADDR_WIDTH      = 8,
    parameter int PIPELINE_STAGES = 1,
    parameter int GROUP_SIZE      = 4
)(
    input  logic                                clk,
    input  logic                                rst_n,

    // Конфігураційна шина Порту A для читання/запису приватних банків BRAM (0 .. NUM_CORES-1)
    input  logic [3:0]                          cfg_bank_sel_i,
    input  logic [ADDR_WIDTH-1:0]               cfg_addr_i,
    input  logic [DATA_WIDTH-1:0]               cfg_wdata_i,
    input  logic [3:0]                          cfg_wstrb_i,
    input  logic                                cfg_we_i,
    output logic [DATA_WIDTH-1:0]               cfg_rdata_o,
    output logic [NUM_CORES-1:0]                collision_detected_o,

    // Зовнішні вхідні канали подій із рукостисканням valid/ready
    input  logic [NUM_EXT_PORTS-1:0]            ext_valid_i,
    output logic [NUM_EXT_PORTS-1:0]            ext_ready_o,
    input  logic [NUM_EXT_PORTS*4-1:0]          ext_dst_bank_i,
    input  logic [NUM_EXT_PORTS*6-1:0]          ext_dst_cid_i,
    input  logic [NUM_EXT_PORTS*DATA_WIDTH-1:0] ext_param_i,

    // Поядерні строби та статуси
    output logic [NUM_CORES-1:0]                core_busy_o,
    output logic [NUM_CORES-1:0]                core_fifo_full_o,
    output logic [NUM_CORES-1:0]                core_commit_pulse_o,
    output logic [NUM_CORES-1:0]                core_reject_pulse_o,
    output logic [NUM_CORES*DATA_WIDTH-1:0]     core_last_state_o,

    // Узагальнений статус та агрегована телеметрія кластера
    output logic                                cluster_busy_o,
    output logic [31:0]                         total_events_processed_o,
    output logic [31:0]                         total_committed_o,
    output logic [31:0]                         total_rejected_o,
    output logic [31:0]                         total_local_cascades_o,
    output logic [31:0]                         total_remote_cascades_o,
    output logic [31:0]                         xbar_routed_events_o,
    output logic [31:0]                         backpressure_stall_cycles_o,
    output logic [31:0]                         invalid_dst_drop_count_o
);

    logic [NUM_CORES-1:0]            node_tx_valid;
    logic [NUM_CORES-1:0]            node_tx_ready;
    logic [NUM_CORES*4-1:0]          node_tx_dst_bank;
    logic [NUM_CORES*6-1:0]          node_tx_dst_cid;
    logic [NUM_CORES*DATA_WIDTH-1:0] node_tx_param;

    logic [NUM_CORES-1:0]            node_rx_valid;
    logic [NUM_CORES-1:0]            node_rx_ready;
    logic [NUM_CORES*6-1:0]          node_rx_cid;
    logic [NUM_CORES*DATA_WIDTH-1:0] node_rx_param;

    logic [DATA_WIDTH-1:0]           node_cfg_rdata [NUM_CORES];
    logic [31:0]                     node_ev_cnt    [NUM_CORES];
    logic [31:0]                     node_comm_cnt  [NUM_CORES];
    logic [31:0]                     node_rej_cnt   [NUM_CORES];
    logic [31:0]                     node_loc_cnt   [NUM_CORES];
    logic [31:0]                     node_rem_cnt   [NUM_CORES];
    logic [31:0]                     node_tx_stalls [NUM_CORES];

    logic                            xbar_busy;
    logic [31:0]                     xbar_stall_cycles;
    logic [3:0]                      cfg_bank_sel_q;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cfg_bank_sel_q <= 4'd0;
        end else begin
            cfg_bank_sel_q <= cfg_bank_sel_i;
        end
    end

    km_event_crossbar #(
        .NUM_CORES(NUM_CORES),
        .NUM_EXT_PORTS(NUM_EXT_PORTS),
        .DATA_WIDTH(DATA_WIDTH),
        .PIPELINE_STAGES(PIPELINE_STAGES),
        .GROUP_SIZE(GROUP_SIZE)
    ) xbar_inst (
        .clk(clk),
        .rst_n(rst_n),
        .int_valid_i(node_tx_valid),
        .int_ready_o(node_tx_ready),
        .int_dst_bank_i(node_tx_dst_bank),
        .int_dst_cid_i(node_tx_dst_cid),
        .int_param_i(node_tx_param),
        .ext_valid_i(ext_valid_i),
        .ext_ready_o(ext_ready_o),
        .ext_dst_bank_i(ext_dst_bank_i),
        .ext_dst_cid_i(ext_dst_cid_i),
        .ext_param_i(ext_param_i),
        .dst_valid_o(node_rx_valid),
        .dst_ready_i(node_rx_ready),
        .dst_cid_o(node_rx_cid),
        .dst_param_o(node_rx_param),
        .xbar_busy_o(xbar_busy),
        .routed_events_count_o(xbar_routed_events_o),
        .backpressure_stall_cycles_o(xbar_stall_cycles),
        .invalid_dst_drop_count_o(invalid_dst_drop_count_o)
    );

    genvar gc;
    generate
        for (gc = 0; gc < NUM_CORES; gc = gc + 1) begin : gen_core
            localparam logic [31:0] CORE_G_U32 = gc;
            localparam logic [3:0]  CORE_G     = CORE_G_U32[3:0];

            wire node_cfg_we_w = cfg_we_i && (cfg_bank_sel_i == CORE_G);

            km_cluster_node #(
                .CORE_ID(gc),
                .NUM_CORES(NUM_CORES),
                .QUEUE_DEPTH(QUEUE_DEPTH),
                .NUM_CONCEPTS(NUM_CONCEPTS),
                .DATA_WIDTH(DATA_WIDTH),
                .ADDR_WIDTH(ADDR_WIDTH),
                .PIPELINE_STAGES(PIPELINE_STAGES)
            ) node_inst (
                .clk(clk),
                .rst_n(rst_n),
                .cfg_addr_i(cfg_addr_i),
                .cfg_wdata_i(cfg_wdata_i),
                .cfg_wstrb_i(cfg_wstrb_i),
                .cfg_we_i(node_cfg_we_w),
                .cfg_rdata_o(node_cfg_rdata[gc]),
                .collision_detected_o(collision_detected_o[gc]),
                .rx_valid_i(node_rx_valid[gc]),
                .rx_cid_i(node_rx_cid[gc*6 +: 6]),
                .rx_param_i(node_rx_param[gc*DATA_WIDTH +: DATA_WIDTH]),
                .rx_ready_o(node_rx_ready[gc]),
                .tx_valid_o(node_tx_valid[gc]),
                .tx_ready_i(node_tx_ready[gc]),
                .tx_dst_bank_o(node_tx_dst_bank[gc*4 +: 4]),
                .tx_dst_cid_o(node_tx_dst_cid[gc*6 +: 6]),
                .tx_param_o(node_tx_param[gc*DATA_WIDTH +: DATA_WIDTH]),
                .busy_o(core_busy_o[gc]),
                .fifo_full_o(core_fifo_full_o[gc]),
                .commit_pulse_o(core_commit_pulse_o[gc]),
                .reject_pulse_o(core_reject_pulse_o[gc]),
                .events_processed_count_o(node_ev_cnt[gc]),
                .committed_count_o(node_comm_cnt[gc]),
                .rejected_count_o(node_rej_cnt[gc]),
                .local_cascade_count_o(node_loc_cnt[gc]),
                .remote_cascade_count_o(node_rem_cnt[gc]),
                .tx_stall_cycles_o(node_tx_stalls[gc]),
                .last_committed_state_o(core_last_state_o[gc*DATA_WIDTH +: DATA_WIDTH])
            );
        end
    endgenerate

    if (PIPELINE_STAGES == 1) begin : gen_cluster_agg_s1
        always_comb begin
            cfg_rdata_o                 = '0;
            total_events_processed_o    = 32'd0;
            total_committed_o           = 32'd0;
            total_rejected_o            = 32'd0;
            total_local_cascades_o      = 32'd0;
            total_remote_cascades_o     = 32'd0;
            backpressure_stall_cycles_o = xbar_stall_cycles;

            for (int c = 0; c < NUM_CORES; c = c + 1) begin
                if (cfg_bank_sel_q == c[3:0]) begin
                    cfg_rdata_o = node_cfg_rdata[c];
                end
                total_events_processed_o    = total_events_processed_o + node_ev_cnt[c];
                total_committed_o           = total_committed_o + node_comm_cnt[c];
                total_rejected_o            = total_rejected_o + node_rej_cnt[c];
                total_local_cascades_o      = total_local_cascades_o + node_loc_cnt[c];
                total_remote_cascades_o     = total_remote_cascades_o + node_rem_cnt[c];
                backpressure_stall_cycles_o = backpressure_stall_cycles_o + node_tx_stalls[c];
            end
        end
    end else begin : gen_cluster_agg_s2
        localparam int NUM_PAIRS = (NUM_CORES > 1) ? ((NUM_CORES + 1) / 2) : 1;

        logic [31:0] pair_ev_q     [NUM_PAIRS];
        logic [31:0] pair_comm_q   [NUM_PAIRS];
        logic [31:0] pair_rej_q    [NUM_PAIRS];
        logic [31:0] pair_loc_q    [NUM_PAIRS];
        logic [31:0] pair_rem_q    [NUM_PAIRS];
        logic [31:0] pair_stalls_q [NUM_PAIRS];
        logic [31:0] xbar_stalls_d1_q;

        logic [31:0] tot_ev_q;
        logic [31:0] tot_comm_q;
        logic [31:0] tot_rej_q;
        logic [31:0] tot_loc_q;
        logic [31:0] tot_rem_q;
        logic [31:0] tot_stalls_q;

        logic [31:0] sum_ev_w;
        logic [31:0] sum_comm_w;
        logic [31:0] sum_rej_w;
        logic [31:0] sum_loc_w;
        logic [31:0] sum_rem_w;
        logic [31:0] sum_stalls_w;

        always_comb begin
            cfg_rdata_o  = '0;
            for (int c = 0; c < NUM_CORES; c = c + 1) begin
                if (cfg_bank_sel_q == c[3:0]) begin
                    cfg_rdata_o = node_cfg_rdata[c];
                end
            end

            sum_ev_w     = 32'd0;
            sum_comm_w   = 32'd0;
            sum_rej_w    = 32'd0;
            sum_loc_w    = 32'd0;
            sum_rem_w    = 32'd0;
            sum_stalls_w = xbar_stalls_d1_q;
            for (int p = 0; p < NUM_PAIRS; p = p + 1) begin
                sum_ev_w     = sum_ev_w + pair_ev_q[p];
                sum_comm_w   = sum_comm_w + pair_comm_q[p];
                sum_rej_w    = sum_rej_w + pair_rej_q[p];
                sum_loc_w    = sum_loc_w + pair_loc_q[p];
                sum_rem_w    = sum_rem_w + pair_rem_q[p];
                sum_stalls_w = sum_stalls_w + pair_stalls_q[p];
            end
        end

        always_ff @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
                for (int p = 0; p < NUM_PAIRS; p = p + 1) begin
                    pair_ev_q[p]     <= 32'd0;
                    pair_comm_q[p]   <= 32'd0;
                    pair_rej_q[p]    <= 32'd0;
                    pair_loc_q[p]    <= 32'd0;
                    pair_rem_q[p]    <= 32'd0;
                    pair_stalls_q[p] <= 32'd0;
                end
                xbar_stalls_d1_q <= 32'd0;
                tot_ev_q         <= 32'd0;
                tot_comm_q       <= 32'd0;
                tot_rej_q        <= 32'd0;
                tot_loc_q        <= 32'd0;
                tot_rem_q        <= 32'd0;
                tot_stalls_q     <= 32'd0;
            end else begin
                for (int p = 0; p < NUM_PAIRS; p = p + 1) begin
                    if ((2 * p + 1) < NUM_CORES) begin
                        pair_ev_q[p]     <= node_ev_cnt[2*p] + node_ev_cnt[2*p+1];
                        pair_comm_q[p]   <= node_comm_cnt[2*p] + node_comm_cnt[2*p+1];
                        pair_rej_q[p]    <= node_rej_cnt[2*p] + node_rej_cnt[2*p+1];
                        pair_loc_q[p]    <= node_loc_cnt[2*p] + node_loc_cnt[2*p+1];
                        pair_rem_q[p]    <= node_rem_cnt[2*p] + node_rem_cnt[2*p+1];
                        pair_stalls_q[p] <= node_tx_stalls[2*p] + node_tx_stalls[2*p+1];
                    end else begin
                        pair_ev_q[p]     <= node_ev_cnt[2*p];
                        pair_comm_q[p]   <= node_comm_cnt[2*p];
                        pair_rej_q[p]    <= node_rej_cnt[2*p];
                        pair_loc_q[p]    <= node_loc_cnt[2*p];
                        pair_rem_q[p]    <= node_rem_cnt[2*p];
                        pair_stalls_q[p] <= node_tx_stalls[2*p];
                    end
                end
                xbar_stalls_d1_q <= xbar_stall_cycles;
                tot_ev_q         <= sum_ev_w;
                tot_comm_q       <= sum_comm_w;
                tot_rej_q        <= sum_rej_w;
                tot_loc_q        <= sum_loc_w;
                tot_rem_q        <= sum_rem_w;
                tot_stalls_q     <= sum_stalls_w;
            end
        end

        assign total_events_processed_o    = tot_ev_q;
        assign total_committed_o           = tot_comm_q;
        assign total_rejected_o            = tot_rej_q;
        assign total_local_cascades_o      = tot_loc_q;
        assign total_remote_cascades_o     = tot_rem_q;
        assign backpressure_stall_cycles_o = tot_stalls_q;
    end

    assign cluster_busy_o = (|core_busy_o) || xbar_busy;

endmodule
