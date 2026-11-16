// Formal property harness for CFG-P (km_autonomous_sequencer + km_concept_micro_engine +
// kpol_txn_gate_v2 + km_concept_bram) and KPOL-CME-2 cascades (Issue #227).
//
// Parameterized to NUM_CONCEPTS=4, QUEUE_DEPTH=4, ADDR_WIDTH=4 for SMT/PDR tractability.
// Modes via `define:
//   - FORMAL_SAFETY   : P1 (Fail-Closed state preservation & no cascade on reject)
//   - FORMAL_LIVENESS : P2 (Bounded acyclic cascade termination) & P3 (Exact 8-cycle latency)
//   - FORMAL_COVER    : Non-vacuity witnesses (>=3 cascade commits, reject_pulse_o)

`timescale 1ns/1ps

module cme2_formal_props #(
    parameter int NUM_CONCEPTS = 4,
    parameter int QUEUE_DEPTH  = 4,
    parameter int DATA_WIDTH   = 32,
    parameter int ADDR_WIDTH   = 4
)(
    input  logic                   clk,
    input  logic                   rst_n,

    // External trigger interface
    input  logic                   hw_trigger_valid_i,
    input  logic [5:0]             hw_trigger_cid_i,
    input  logic [DATA_WIDTH-1:0]  hw_trigger_param_i,

    // Port A interface (used only while !rst_n to load arbitrary KPOL-CME-2 images)
    input  logic [ADDR_WIDTH-1:0]  a_addr_i,
    input  logic [DATA_WIDTH-1:0]  a_wdata_i,
    input  logic [3:0]             a_wstrb_i,
    input  logic                   a_we_i
);

    localparam int WORDS_TOTAL = NUM_CONCEPTS * 4;
    localparam int MAX_CASCADE_CYCLES = 8 * NUM_CONCEPTS + 2; // 34 for NUM_CONCEPTS=4

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

    // Shadow copy of BRAM contents for formal property observation
    logic [DATA_WIDTH-1:0] shadow_ram [0:WORDS_TOTAL-1];
    integer s_idx;
    initial begin
        for (s_idx = 0; s_idx < WORDS_TOTAL; s_idx = s_idx + 1) begin
            shadow_ram[s_idx] = '0;
        end
    end

    always_ff @(posedge clk) begin
        if (a_we_i) begin
            if (a_wstrb_i[0]) shadow_ram[a_addr_i][ 7: 0] <= a_wdata_i[ 7: 0];
            if (a_wstrb_i[1]) shadow_ram[a_addr_i][15: 8] <= a_wdata_i[15: 8];
            if (a_wstrb_i[2]) shadow_ram[a_addr_i][23:16] <= a_wdata_i[23:16];
            if (a_wstrb_i[3]) shadow_ram[a_addr_i][31:24] <= a_wdata_i[31:24];
        end
        if (bram_b_we_o) begin
            if (bram_b_wstrb_o[0]) shadow_ram[bram_b_addr_o][ 7: 0] <= bram_b_wdata_o[ 7: 0];
            if (bram_b_wstrb_o[1]) shadow_ram[bram_b_addr_o][15: 8] <= bram_b_wdata_o[15: 8];
            if (bram_b_wstrb_o[2]) shadow_ram[bram_b_addr_o][23:16] <= bram_b_wdata_o[23:16];
            if (bram_b_wstrb_o[3]) shadow_ram[bram_b_addr_o][31:24] <= bram_b_wdata_o[31:24];
        end
    end

    // Past-state tracking
    logic                  past_valid = 1'b0;
    logic                  p_rst_n;
    logic                  p_reject_pulse;
    logic                  p_commit_pulse;
    logic [31:0]           p_w0_c0, p_w0_c1, p_w0_c2, p_w0_c3;
    logic [31:0]           ext_accepted_cnt_q = 32'd0;
    logic                  p_no_pending_other_q = 1'b0;

    // Liveness / latency tracking
    logic [4:0]            init_cnt_q = 5'd0;
    logic                  seen_trigger_q = 1'b0;
    logic [7:0]            busy_cnt_q = 8'd0;
    logic [7:0]            lat_cnt_q = 8'd0;
    logic                  tracking_single_q = 1'b0;
    logic [1:0]            single_cid_q = 2'd0;

    wire ext_accept_w = hw_trigger_valid_i && hw_trigger_ready_o;

    always_ff @(posedge clk) begin
        past_valid     <= 1'b1;
        p_rst_n        <= rst_n;
        p_reject_pulse <= reject_pulse_o;
        p_commit_pulse <= commit_pulse_o;
        p_w0_c0        <= shadow_ram[0];
        p_w0_c1        <= shadow_ram[4];
        p_w0_c2        <= shadow_ram[8];
        p_w0_c3        <= shadow_ram[12];

        if (init_cnt_q < 5'd16) begin
            init_cnt_q <= init_cnt_q + 5'd1;
        end

        if (!rst_n) begin
            ext_accepted_cnt_q   <= 32'd0;
            p_no_pending_other_q <= 1'b0;
            seen_trigger_q       <= 1'b0;
            busy_cnt_q           <= 8'd0;
            lat_cnt_q            <= 8'd0;
            tracking_single_q    <= 1'b0;
            single_cid_q         <= 2'd0;
        end else begin
            if (ext_accept_w) begin
                ext_accepted_cnt_q <= ext_accepted_cnt_q + 32'd1;
                seen_trigger_q     <= 1'b1;
                if (!busy_o && !seen_trigger_q) begin
                    tracking_single_q <= 1'b1;
                    single_cid_q      <= hw_trigger_cid_i[1:0];
                    lat_cnt_q         <= 8'd1;
                end
            end else if (tracking_single_q) begin
                if (lat_cnt_q < 8'd64) begin
                    lat_cnt_q <= lat_cnt_q + 8'd1;
                end
            end

            // True on the cycle after reject_pulse_o if no external trigger arrived during reject_pulse_o
            // and total processed + 1 == ext_accepted + committed (no queued events left)
            p_no_pending_other_q <= reject_pulse_o && !ext_accept_w &&
                                    ((events_processed_count_o + 32'd1) == (ext_accepted_cnt_q + committed_count_o));

            if (seen_trigger_q && busy_o) begin
                if (busy_cnt_q < 8'd255) begin
                    busy_cnt_q <= busy_cnt_q + 8'd1;
                end
            end
        end
    end

    // ---- Environment Assumptions ----
    always @(*) begin
        if (!past_valid) begin
            assume (!rst_n);
        end
        // Port A writes only while in reset (BRAM configuration phase)
        if (rst_n) begin
            assume (!a_we_i);
        end
        // Valid concept IDs within [0, NUM_CONCEPTS-1]
        assume (hw_trigger_cid_i < NUM_CONCEPTS);
    end

`ifdef FORMAL_LIVENESS
    // Acyclic KPOL-CME-2 rule table condition for cid = 0..3:
    // Either subscriber is disabled (>= 64 or (0 && !guard_flags[4]))
    // or subscriber_cid > cid && subscriber_cid < NUM_CONCEPTS.
    wire c0_sub_disabled = (shadow_ram[3] >= 32'd64) || (shadow_ram[3] == 32'd0 && !shadow_ram[2][12]);
    wire c1_sub_disabled = (shadow_ram[7] >= 32'd64) || (shadow_ram[7] == 32'd0 && !shadow_ram[6][12]);
    wire c2_sub_disabled = (shadow_ram[11] >= 32'd64) || (shadow_ram[11] == 32'd0 && !shadow_ram[10][12]);
    wire c3_sub_disabled = (shadow_ram[15] >= 32'd64) || (shadow_ram[15] == 32'd0 && !shadow_ram[14][12]);

    wire c0_acyclic = c0_sub_disabled || (shadow_ram[3] > 32'd0 && shadow_ram[3] < NUM_CONCEPTS);
    wire c1_acyclic = c1_sub_disabled || (shadow_ram[7] > 32'd1 && shadow_ram[7] < NUM_CONCEPTS);
    wire c2_acyclic = c2_sub_disabled || (shadow_ram[11] > 32'd2 && shadow_ram[11] < NUM_CONCEPTS);
    wire c3_acyclic = c3_sub_disabled; // cid=3 is max, cannot have sub > 3 and < 4

    always @(*) begin
        // Hold reset for 16 cycles to allow arbitrary BRAM initialization via Port A
        if (init_cnt_q < 5'd16) begin
            assume (!rst_n);
        end else begin
            assume (rst_n);
        end

        if (rst_n) begin
            assume (c0_acyclic && c1_acyclic && c2_acyclic && c3_acyclic);
            // Single external trigger pulse only
            if (seen_trigger_q) begin
                assume (!hw_trigger_valid_i);
            end
        end
    end
`endif

`ifdef FORMAL_COVER
    always @(*) begin
        if (init_cnt_q < 5'd16) begin
            assume (!rst_n);
        end else begin
            assume (rst_n);
        end
    end
`endif

    // ---- Formal Safety Properties (P1) ----
    always @(*) begin
        if (past_valid && rst_n && p_rst_n) begin
            // P1a: Never assert bram_b_we_o on reject or on the cycle after reject_pulse_o
            P1a_no_we_on_reject:
                assert (!p_reject_pulse || !bram_b_we_o);

            P1b_no_we_during_reject:
                assert (!reject_pulse_o || !bram_b_we_o);

            // P1c: Concept state W0 in BRAM is preserved on reject
            P1c_w0_preserved_on_reject:
                assert (!p_reject_pulse || (
                    (shadow_ram[0]  == p_w0_c0) &&
                    (shadow_ram[4]  == p_w0_c1) &&
                    (shadow_ram[8]  == p_w0_c2) &&
                    (shadow_ram[12] == p_w0_c3)
                ));

`ifndef FORMAL_INDUCTION
            // P1d: No phantom/cascade events generated on reject (conservation of events)
            P1d_no_cascade_on_reject:
                assert (events_processed_count_o <= (ext_accepted_cnt_q + committed_count_o));

            P1e_idle_after_isolated_reject:
                assert (!p_no_pending_other_q || !busy_o);
`endif

            // P1f: Mutual exclusion between commit_pulse_o and reject_pulse_o
            P1f_pulse_mutex:
                assert (!(commit_pulse_o && reject_pulse_o));
        end
    end

`ifdef FORMAL_LIVENESS
    wire single_sub_disabled_w =
        (single_cid_q == 2'd0) ? c0_sub_disabled :
        (single_cid_q == 2'd1) ? c1_sub_disabled :
        (single_cid_q == 2'd2) ? c2_sub_disabled : c3_sub_disabled;

    // ---- P2: Bounded Acyclic Cascade Termination ----
    always @(*) begin
        if (past_valid && rst_n && p_rst_n) begin
            P2_bounded_termination:
                assert (busy_cnt_q <= MAX_CASCADE_CYCLES);

            // ---- P3: Exact Single-Transaction Latency ----
            // From ext_accept at ST_IDLE (empty queue) with disabled subscriber:
            // Cycle 0: ext_accept -> Cycle 8: commit_pulse_o || reject_pulse_o
            P3a_exact_latency_pulse:
                assert (!(tracking_single_q && single_sub_disabled_w && (lat_cnt_q == 8'd8)) ||
                        (commit_pulse_o || reject_pulse_o));

            P3b_no_early_pulse:
                assert (!(tracking_single_q && single_sub_disabled_w && (lat_cnt_q > 8'd0) && (lat_cnt_q < 8'd8)) ||
                        (!commit_pulse_o && !reject_pulse_o));

            P3c_idle_after_single:
                assert (!(tracking_single_q && single_sub_disabled_w && (lat_cnt_q == 8'd9)) ||
                        !busy_o);
        end
    end
`endif

`ifdef FORMAL_COVER
    // ---- Non-Vacuity Coverage Witnesses ----
    always @(*) begin
        if (past_valid && rst_n && p_rst_n) begin
            C1_cascade_3_commits: cover (committed_count_o >= 32'd3);
            C2_reject_reached:    cover (reject_pulse_o);
            C3_commit_and_idle:   cover (committed_count_o >= 32'd1 && !busy_o);
        end
    end
`endif

endmodule
