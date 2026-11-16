// Compositional formal property harness for CFG-P and KPOL-CME-2 at NUM_CONCEPTS=16 (Issues #237, #242).
//
// Parameterized to NUM_CONCEPTS=16, QUEUE_DEPTH=16, ADDR_WIDTH=6 (64 words in BRAM).
// Internal sequencer signals obs_* are bound after Yosys flatten via `connect -set`.
//
// Modes via `define:
//   - FORMAL_SAFETY (+ FORMAL_INDUCTION)    : P1_n16_ind (Big Dot mutex, W0 preservation, no cascade on reject)
//   - FORMAL_RANK_STEP (+ FORMAL_INDUCTION) : P2_rank_step_n16 (Lyapunov rank V = 15 - cid strict decrease)
//   - FORMAL_LIVENESS                       : P3_with_and_without_cascade (8-cycle step w/ & w/o cascade, 2 ext triggers)
//   - FORMAL_COVER                          : Non-vacuity witnesses on N=16 (0->5->11->15 cascade, reject, 2 ext triggers)

`timescale 1ns/1ps

module cme2_formal_n16_props #(
    parameter int NUM_CONCEPTS = 16,
    parameter int QUEUE_DEPTH  = 16,
    parameter int DATA_WIDTH   = 32,
    parameter int ADDR_WIDTH   = 6
)(
    input  logic                   clk,
    input  logic                   rst_n,

    // External trigger interface
    input  logic                   hw_trigger_valid_i,
    input  logic [5:0]             hw_trigger_cid_i,
    input  logic [DATA_WIDTH-1:0]  hw_trigger_param_i,

    // Port A interface (used only while !rst_n to load KPOL-CME-2 descriptors)
    input  logic [ADDR_WIDTH-1:0]  a_addr_i,
    input  logic [DATA_WIDTH-1:0]  a_wdata_i,
    input  logic [3:0]             a_wstrb_i,
    input  logic                   a_we_i
);

    localparam int WORDS_TOTAL = NUM_CONCEPTS * 4;

    logic                   hw_trigger_ready_o;
    logic [ADDR_WIDTH-1:0]  bram_b_addr_o;
    logic [DATA_WIDTH-1:0]  bram_b_wdata_o;
    logic [3:0]             bram_b_wstrb_o;
    logic                   bram_b_we_o;
    logic [DATA_WIDTH-1:0]  bram_b_rdata_i;
    logic [DATA_WIDTH-1:0]  a_rdata_o;
    logic                   collision_detected_o;

    logic                   busy_o;
    logic                   fifo_full_o;
    logic                   fifo_overflow_o;
    logic [31:0]            events_dropped_count_o;
    logic [31:0]            events_processed_count_o;
    logic [31:0]            committed_count_o;
    logic [31:0]            rejected_count_o;
    logic [31:0]            last_committed_state_o;
    logic                   commit_pulse_o;
    logic                   reject_pulse_o;

    // Internal sequencer observation wires (bound via Yosys `connect -set` after flatten)
    (* keep *) wire [3:0]  obs_state_q;
    (* keep *) wire [4:0]  obs_fifo_count_q;
    (* keep *) wire [3:0]  obs_fifo_wr_ptr_q;
    (* keep *) wire [3:0]  obs_fifo_rd_ptr_q;
    (* keep *) wire        obs_cme_event_valid;
    (* keep *) wire        obs_cme_committed;
    (* keep *) wire        obs_cme_rejected;
    (* keep *) wire        obs_cme_trigger_subscriber;
    (* keep *) wire [31:0] obs_cme_subscriber_cid;
    (* keep *) wire        obs_cascade_req;
    (* keep *) wire [5:0]  obs_active_cid_q;
    (* keep *) wire        obs_cascade_pending_valid_q;
    (* keep *) wire [5:0]  obs_cascade_pending_cid_q;
    (* keep *) wire [31:0] obs_desc_w2_q;

    km_concept_bram #(
        .NUM_CONCEPTS(NUM_CONCEPTS),
        .DATA_WIDTH(DATA_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) dut_bram (
        .clk(clk),
        .rst_n(rst_n),
        .a_addr_i(a_addr_i),
        .a_wdata_i(a_wdata_i),
        .a_wstrb_i(a_wstrb_i),
        .a_we_i(a_we_i),
        .a_rdata_o(a_rdata_o),
        .b_addr_i(bram_b_addr_o),
        .b_wdata_i(bram_b_wdata_o),
        .b_wstrb_i(bram_b_wstrb_o),
        .b_we_i(bram_b_we_o),
        .b_rdata_o(bram_b_rdata_i),
        .collision_detected_o(collision_detected_o)
    );

    km_autonomous_sequencer #(
        .QUEUE_DEPTH(QUEUE_DEPTH),
        .NUM_CONCEPTS(NUM_CONCEPTS),
        .DATA_WIDTH(DATA_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) dut_seq (
        .clk(clk),
        .rst_n(rst_n),
        .hw_trigger_valid_i(hw_trigger_valid_i),
        .hw_trigger_cid_i(hw_trigger_cid_i),
        .hw_trigger_param_i(hw_trigger_param_i),
        .hw_trigger_ready_o(hw_trigger_ready_o),
        .bram_b_addr_o(bram_b_addr_o),
        .bram_b_wdata_o(bram_b_wdata_o),
        .bram_b_wstrb_o(bram_b_wstrb_o),
        .bram_b_we_o(bram_b_we_o),
        .bram_b_rdata_i(bram_b_rdata_i),
        .clear_overflow_i(1'b0),
        .busy_o(busy_o),
        .fifo_full_o(fifo_full_o),
        .fifo_overflow_o(fifo_overflow_o),
        .events_dropped_count_o(events_dropped_count_o),
        .events_processed_count_o(events_processed_count_o),
        .committed_count_o(committed_count_o),
        .rejected_count_o(rejected_count_o),
        .last_committed_state_o(last_committed_state_o),
        .commit_pulse_o(commit_pulse_o),
        .reject_pulse_o(reject_pulse_o)
    );

    // Shadow copy of BRAM W0 words (all 16 concepts, for FORMAL_SAFETY)
`ifdef FORMAL_SAFETY
    logic [DATA_WIDTH-1:0] shadow_w0 [0:NUM_CONCEPTS-1];
    logic [DATA_WIDTH-1:0] p_w0      [0:NUM_CONCEPTS-1];
    integer s_idx;
    initial begin
        for (s_idx = 0; s_idx < NUM_CONCEPTS; s_idx = s_idx + 1) begin
            shadow_w0[s_idx] = '0;
        end
    end

    always_ff @(posedge clk) begin
        if (a_we_i && (a_addr_i[1:0] == 2'b00)) begin
            if (a_wstrb_i[0]) shadow_w0[a_addr_i[5:2]][ 7: 0] <= a_wdata_i[ 7: 0];
            if (a_wstrb_i[1]) shadow_w0[a_addr_i[5:2]][15: 8] <= a_wdata_i[15: 8];
            if (a_wstrb_i[2]) shadow_w0[a_addr_i[5:2]][23:16] <= a_wdata_i[23:16];
            if (a_wstrb_i[3]) shadow_w0[a_addr_i[5:2]][31:24] <= a_wdata_i[31:24];
        end
        if (bram_b_we_o && (bram_b_addr_o[1:0] == 2'b00)) begin
            if (bram_b_wstrb_o[0]) shadow_w0[bram_b_addr_o[5:2]][ 7: 0] <= bram_b_wdata_o[ 7: 0];
            if (bram_b_wstrb_o[1]) shadow_w0[bram_b_addr_o[5:2]][15: 8] <= bram_b_wdata_o[15: 8];
            if (bram_b_wstrb_o[2]) shadow_w0[bram_b_addr_o[5:2]][23:16] <= bram_b_wdata_o[23:16];
            if (bram_b_wstrb_o[3]) shadow_w0[bram_b_addr_o[5:2]][31:24] <= bram_b_wdata_o[31:24];
        end
        for (s_idx = 0; s_idx < NUM_CONCEPTS; s_idx = s_idx + 1) begin
            p_w0[s_idx] <= shadow_w0[s_idx];
        end
    end
`endif

`ifdef FORMAL_LIVENESS
    logic [DATA_WIDTH-1:0] shadow_w2 [0:NUM_CONCEPTS-1];
    logic [DATA_WIDTH-1:0] shadow_w3 [0:NUM_CONCEPTS-1];
    integer l_idx;
    initial begin
        for (l_idx = 0; l_idx < NUM_CONCEPTS; l_idx = l_idx + 1) begin
            shadow_w2[l_idx] = '0;
            shadow_w3[l_idx] = '0;
        end
    end

    always_ff @(posedge clk) begin
        if (a_we_i) begin
            if (a_addr_i[1:0] == 2'b10) begin
                if (a_wstrb_i[0]) shadow_w2[a_addr_i[5:2]][ 7: 0] <= a_wdata_i[ 7: 0];
                if (a_wstrb_i[1]) shadow_w2[a_addr_i[5:2]][15: 8] <= a_wdata_i[15: 8];
                if (a_wstrb_i[2]) shadow_w2[a_addr_i[5:2]][23:16] <= a_wdata_i[23:16];
                if (a_wstrb_i[3]) shadow_w2[a_addr_i[5:2]][31:24] <= a_wdata_i[31:24];
            end else if (a_addr_i[1:0] == 2'b11) begin
                if (a_wstrb_i[0]) shadow_w3[a_addr_i[5:2]][ 7: 0] <= a_wdata_i[ 7: 0];
                if (a_wstrb_i[1]) shadow_w3[a_addr_i[5:2]][15: 8] <= a_wdata_i[15: 8];
                if (a_wstrb_i[2]) shadow_w3[a_addr_i[5:2]][23:16] <= a_wdata_i[23:16];
                if (a_wstrb_i[3]) shadow_w3[a_addr_i[5:2]][31:24] <= a_wdata_i[31:24];
            end
        end
    end
`endif

    // Past-state tracking
    logic                  past_valid = 1'b0;
    logic                  p_rst_n;
    logic                  p_reject_pulse;
    logic                  p_commit_pulse;

    wire ext_accept_w = hw_trigger_valid_i && hw_trigger_ready_o;

    always_ff @(posedge clk) begin
        past_valid      <= 1'b1;
        p_rst_n         <= rst_n;
        p_reject_pulse  <= reject_pulse_o;
        p_commit_pulse  <= commit_pulse_o;
    end

    // ---- Environment Assumptions ----
    always @(*) begin
        if (!past_valid) begin
            assume (!rst_n);
        end
        if (rst_n) begin
            assume (!a_we_i);
        end
        assume (hw_trigger_cid_i < NUM_CONCEPTS);
    end

`ifdef FORMAL_INDUCTION
    // ---- Proved Auxiliary Inductive Invariants of Sequencer States (ALL assert, ZERO assume!) ----
    wire [3:0] wr_rd_sum_w = obs_fifo_rd_ptr_q + obs_fifo_count_q[3:0];

    always @(*) begin
        if (rst_n) begin
            INV_state_range:
                assert (obs_state_q <= 4'd7);
            INV_fifo_count:
                assert (obs_fifo_count_q <= QUEUE_DEPTH);
            INV_fifo_ptrs:
                assert (wr_rd_sum_w == obs_fifo_wr_ptr_q);
            INV_cme_ev_valid:
                assert (obs_cme_event_valid == (obs_state_q == 4'd6));
            INV_cme_mutex:
                assert (!(obs_cme_committed && obs_cme_rejected));
            INV_cme_gate_state:
                assert (!(obs_cme_committed || obs_cme_rejected) || (obs_state_q == 4'd7));
            INV_pending_state:
                assert (!obs_cascade_pending_valid_q || ((obs_state_q == 4'd0) && (obs_fifo_count_q == QUEUE_DEPTH)));
            if (past_valid && p_rst_n) begin
                INV_we_pulse:
                    assert (bram_b_we_o == p_commit_pulse);
            end
        end
    end
`endif

`ifdef FORMAL_SAFETY
    // ---- P1_n16_ind: Big Dot Mutual Exclusion & Fail-Closed Preservation (Unbounded k-induction) ----
    always @(*) begin
        if (past_valid && rst_n && p_rst_n) begin
            // P_bigdot_mutex: atomic mutual exclusion between commit (•) and reject (¬)
            P_bigdot_mutex_pulse:
                assert (!(commit_pulse_o && reject_pulse_o));

            P_bigdot_mutex_cme:
                assert (!(obs_cme_committed && obs_cme_rejected));

            // P1a / P1b: Never assert bram_b_we_o on reject or on the cycle after reject_pulse_o
            P1a_no_we_on_reject:
                assert (!p_reject_pulse || !bram_b_we_o);

            P1b_no_we_during_reject:
                assert (!reject_pulse_o || !bram_b_we_o);

            // P1c: All 16 concept states W0 in BRAM are preserved on reject
            P1c_w0_preserved_on_reject:
                assert (!p_reject_pulse || (
                    (shadow_w0[ 0] == p_w0[ 0]) && (shadow_w0[ 1] == p_w0[ 1]) &&
                    (shadow_w0[ 2] == p_w0[ 2]) && (shadow_w0[ 3] == p_w0[ 3]) &&
                    (shadow_w0[ 4] == p_w0[ 4]) && (shadow_w0[ 5] == p_w0[ 5]) &&
                    (shadow_w0[ 6] == p_w0[ 6]) && (shadow_w0[ 7] == p_w0[ 7]) &&
                    (shadow_w0[ 8] == p_w0[ 8]) && (shadow_w0[ 9] == p_w0[ 9]) &&
                    (shadow_w0[10] == p_w0[10]) && (shadow_w0[11] == p_w0[11]) &&
                    (shadow_w0[12] == p_w0[12]) && (shadow_w0[13] == p_w0[13]) &&
                    (shadow_w0[14] == p_w0[14]) && (shadow_w0[15] == p_w0[15])
                ));

            // P1d: No cascade trigger or cascade request on reject
            P1d_no_cascade_on_reject:
                assert (!reject_pulse_o || (!obs_cme_trigger_subscriber && !obs_cascade_req));

            // P1e: Isolated reject returns immediately to idle (!busy_o)
            P1e_idle_after_isolated_reject:
                assert (!(p_reject_pulse && (obs_fifo_count_q == 5'd0) && !obs_cascade_pending_valid_q) ||
                        !busy_o);

            // P1f (closes R2): Autonomous Port B writes ONLY target W0 (2'b00); W1..W3 config words are hardware-immutable
            P1f_cfg_words_immutable:
                assert (!bram_b_we_o || (bram_b_addr_o[1:0] == 2'b00));
        end
    end
`endif

`ifdef FORMAL_RANK_STEP
    // ---- P2_rank_step_n16: Compositional Inductive Lemma of Lyapunov Rank V(cid) = 15 - cid ----
    wire cap_sub_disabled_w = (bram_b_rdata_i >= 32'd64) ||
                              ((bram_b_rdata_i == 32'd0) && !obs_desc_w2_q[12]);
    wire cap_dag_ok_w       = cap_sub_disabled_w ||
                              ((bram_b_rdata_i > {26'd0, obs_active_cid_q}) &&
                               (bram_b_rdata_i < NUM_CONCEPTS));

    always @(*) begin
        if (rst_n && (obs_state_q == 4'd5)) begin
            assume (cap_dag_ok_w);
        end
    end

    wire [5:0] rank_active_w = 6'd15 - obs_active_cid_q;
    wire [5:0] rank_next_w   = 6'd15 - obs_cme_subscriber_cid[5:0];

    always @(*) begin
        if (past_valid && rst_n && p_rst_n) begin
            P2_rank_step_n16:
                assert (!(obs_state_q == 4'd7) ||
                        !obs_cascade_req ||
                        ((obs_active_cid_q < NUM_CONCEPTS) &&
                         (obs_cme_subscriber_cid[5:0] > obs_active_cid_q) &&
                         (obs_cme_subscriber_cid[5:0] < NUM_CONCEPTS) &&
                         (rank_next_w < rank_active_w)));
        end
    end
`endif

`ifdef FORMAL_LIVENESS
    // ---- P3_with_and_without_cascade on N=16 (Compositional k-induction, closes #237) ----
    // Proves exact 8-cycle transaction step from ext_accept at idle:
    //   - Cycle 1..7: no commit/reject pulse
    //   - Cycle 8   : commit_pulse_o || reject_pulse_o
    //   - Cycle 9   : !busy_o if no cascade & no 2nd external trigger;
    //                 otherwise ST_IDLE with fifo_count >= 1 (zero-bubble dequeue)
    //   - Cycle 10  : ST_REQ_W0 (4'd1) when cascade or 2nd external trigger is present
    logic [3:0] lat_cnt_q     = 4'd0;
    logic       tracking_q    = 1'b0;
    logic       extra_ev_q    = 1'b0;
    logic       had_cascade_q = 1'b0;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            lat_cnt_q     <= 4'd0;
            tracking_q    <= 1'b0;
            extra_ev_q    <= 1'b0;
            had_cascade_q <= 1'b0;
        end else begin
            if (!busy_o && ext_accept_w) begin
                tracking_q    <= 1'b1;
                lat_cnt_q     <= 4'd1;
                extra_ev_q    <= 1'b0;
                had_cascade_q <= 1'b0;
            end else if (tracking_q) begin
                if (ext_accept_w) begin
                    extra_ev_q <= 1'b1;
                end
                if (lat_cnt_q == 4'd8) begin
                    had_cascade_q <= obs_cascade_req;
                end
                if (lat_cnt_q >= 4'd10) begin
                    tracking_q <= 1'b0;
                end else begin
                    lat_cnt_q <= lat_cnt_q + 4'd1;
                end
            end
        end
    end

    always @(*) begin
        if (past_valid && rst_n && p_rst_n && tracking_q) begin
            P3_first_tx_exact_8:
                assert ((lat_cnt_q != 4'd8) || (commit_pulse_o || reject_pulse_o));

            P3_first_tx_no_early:
                assert (!((lat_cnt_q >= 4'd1) && (lat_cnt_q <= 4'd7)) ||
                        (!commit_pulse_o && !reject_pulse_o));

            P3_no_cascade_idle_9:
                assert (!((lat_cnt_q == 4'd9) && !had_cascade_q && !extra_ev_q) || !busy_o);

            P3_cascade_or_2nd_trigger_zero_bubble:
                assert (!((lat_cnt_q == 4'd9) && (had_cascade_q || extra_ev_q)) ||
                        (busy_o && (obs_state_q == 4'd0) && (obs_fifo_count_q >= 5'd1)));

            P3_next_tx_starts_at_10:
                assert (!((lat_cnt_q == 4'd10) && (had_cascade_q || extra_ev_q)) ||
                        (obs_state_q == 4'd1));
        end
    end
`endif

`ifdef FORMAL_COVER
    // ---- Non-Vacuity Coverage Witnesses on N=16 ----
    logic [4:0] cov_init_cnt_q = 5'd0;
    logic [1:0] cov_ext_cnt_q  = 2'd0;
    always_ff @(posedge clk) begin
        if (cov_init_cnt_q < 5'd7) cov_init_cnt_q <= cov_init_cnt_q + 5'd1;
        if (!rst_n) cov_ext_cnt_q <= 2'd0;
        else if (ext_accept_w && (cov_ext_cnt_q < 2'd3)) cov_ext_cnt_q <= cov_ext_cnt_q + 2'd1;
    end

    always @(*) begin
        if (cov_init_cnt_q < 5'd7) assume (!rst_n);
        else assume (rst_n);
        assume (a_wstrb_i == 4'b1111);
    end

    always @(*) begin
        if (past_valid && rst_n && p_rst_n) begin
            // 4-commit cascade reaching cid=15 (e.g. 0 -> 5 -> 11 -> 15)
            C1_n16_cascade_4_commits:
                cover ((committed_count_o == 32'd3) && commit_pulse_o && (obs_active_cid_q == 6'd15));

            C2_n16_reject_reached:
                cover (reject_pulse_o);

            C3_n16_two_ext_triggers:
                cover ((cov_ext_cnt_q >= 2'd2) && (events_processed_count_o >= 32'd2) && !busy_o);
        end
    end
`endif

endmodule
