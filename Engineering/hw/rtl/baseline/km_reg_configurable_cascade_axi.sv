`timescale 1ns / 1ps

// ============================================================================
// Module: km_reg_configurable_cascade_axi.sv
// Purpose: Specialized register-configurable cascade engine with AXI4-Lite
// rule/state configuration (Variant 3 comparative baseline for Issue #254).
//
// Architectural contrast vs CFG-P (kpol_bram_pipeline_axi.sv):
// - Rules and states of NUM_CONCEPTS concepts are stored directly in flip-flop
//   registers (0 RAMB36E1 blocks, no 8-cycle sequential BRAM fetch FSM).
// - Rules are reconfigurable at runtime via AXI4-Lite when !busy without FPGA
//   bitstream resynthesis (both direct MMIO window 0x100..0x4FC at 1 write/word
//   and indirect 0x004/0x008 CSR pair).
// - Executes 1 concept evaluation step in 1 clock cycle (10 ns @ 100 MHz):
//   10 ns for a rejected/single-concept event, 40 ns (4 cycles) for a full
//   4-concept cascade C0 -> C1 -> C2 -> C3 (8x lower latency than CFG-P).
// - Trades O(1) logic area of CFG-P for O(NUM_CONCEPTS) flip-flops and wide
//   combinational read/write multiplexers.
// ============================================================================

module km_reg_configurable_cascade_axi #(
    parameter int NUM_CONCEPTS = 4,
    parameter int QUEUE_DEPTH  = 16,
    parameter int DATA_WIDTH   = 32
) (
    input  logic                  clk,
    input  logic                  rst_n,

    // AXI4-Lite Slave Write Channel
    input  logic [12:0]           awaddr,
    input  logic                  awvalid,
    output logic                  awready,
    input  logic [31:0]           wdata,
    input  logic [3:0]            wstrb,
    input  logic                  wvalid,
    output logic                  wready,
    output logic [1:0]            bresp,
    output logic                  bvalid,
    input  logic                  bready,

    // AXI4-Lite Slave Read Channel
    input  logic [12:0]           araddr,
    input  logic                  arvalid,
    output logic                  arready,
    output logic [31:0]           rdata,
    output logic [1:0]            rresp,
    output logic                  rvalid,
    input  logic                  rready,

    // External Hardware Event Trigger
    input  logic                  ext_hw_trigger_valid_i,
    input  logic [5:0]            ext_hw_trigger_cid_i,
    input  logic [DATA_WIDTH-1:0] ext_hw_trigger_param_i,
    output logic                  hw_trigger_ready_o,

    // Physical Status and Telemetry Outputs
    output logic                  hw_commit_pulse_o,
    output logic                  hw_reject_pulse_o,
    output logic                  hw_pipeline_busy_o,
    output logic                  fifo_overflow_o,
    output logic [31:0]           events_dropped_count_o,
    output logic [5:0]            hw_commit_cid_o,
    output logic [DATA_WIDTH-1:0] hw_last_committed_state_o,

    output logic                  busy
);
    localparam logic [1:0] OKAY = 2'b00, SLVERR = 2'b10, DECERR = 2'b11;
    localparam int PTR_WIDTH     = (QUEUE_DEPTH > 1) ? $clog2(QUEUE_DEPTH) : 1;
    localparam int CID_IDX_WIDTH = (NUM_CONCEPTS > 1) ? $clog2(NUM_CONCEPTS) : 1;
    localparam logic [31:0]          DEPTH_U32 = QUEUE_DEPTH;
    localparam logic [PTR_WIDTH:0]   DEPTH_CNT = DEPTH_U32[PTR_WIDTH:0];
    localparam logic [31:0]          ONE_U32   = 32'd1;
    localparam logic [PTR_WIDTH-1:0] PTR_ONE   = ONE_U32[PTR_WIDTH-1:0];
    localparam logic [31:0]          NUM_C_U32 = NUM_CONCEPTS;
    localparam logic [6:0]           NUM_C_U7  = NUM_C_U32[6:0];

    // ------------------------------------------------------------------------
    // 1. AXI4-Lite Handshake State
    // ------------------------------------------------------------------------
    logic        aw_pending, w_pending, read_pending;
    logic [12:0] awaddr_q, read_addr_q;
    logic [31:0] wdata_q;
    logic [3:0]  wstrb_q;

    wire aw_fire    = awvalid && awready;
    wire w_fire     = wvalid && wready;
    wire write_fire = (aw_pending || aw_fire) && (w_pending || w_fire);
    wire [12:0] write_addr = aw_pending ? awaddr_q : awaddr;
    wire [31:0] write_data = w_pending  ? wdata_q  : wdata;
    wire [3:0]  write_strb = w_pending  ? wstrb_q  : wstrb;

    assign awready = !aw_pending && !bvalid;
    assign wready  = !w_pending && !bvalid;
    assign arready = !rvalid && !read_pending;

    // ------------------------------------------------------------------------
    // 2. Register-Configured Concept Bank (Flip-Flops, 0 BRAM)
    //    Active semantic fields per concept (92 FFs/concept):
    //    state (32b), operand (32b), pred_op (4b), guard_flags (5b),
    //    hazard_limit (8b), action_op (4b), subscriber_cid (6b) + oob (1b).
    // ------------------------------------------------------------------------
    logic [DATA_WIDTH-1:0] state_q        [0:NUM_CONCEPTS-1];
    logic [DATA_WIDTH-1:0] operand_q      [0:NUM_CONCEPTS-1];
    logic [3:0]            pred_op_q      [0:NUM_CONCEPTS-1];
    logic [4:0]            guard_flags_q  [0:NUM_CONCEPTS-1];
    logic [7:0]            hazard_limit_q [0:NUM_CONCEPTS-1];
    logic [3:0]            action_op_q    [0:NUM_CONCEPTS-1];
    logic [5:0]            sub_cid_q      [0:NUM_CONCEPTS-1];
    logic                  sub_oob_q      [0:NUM_CONCEPTS-1];

    logic [7:0]            cfg_addr_q;
    logic [DATA_WIDTH-1:0] event_param_q;
    logic                  sw_trigger_q;

    // ------------------------------------------------------------------------
    // 3. Event FIFO and Active 1-Cycle Evaluation Stage
    // ------------------------------------------------------------------------
    logic [5:0]            fifo_cid_q   [0:QUEUE_DEPTH-1];
    logic [DATA_WIDTH-1:0] fifo_param_q [0:QUEUE_DEPTH-1];
    logic [PTR_WIDTH-1:0]  fifo_wr_ptr_q;
    logic [PTR_WIDTH-1:0]  fifo_rd_ptr_q;
    logic [PTR_WIDTH:0]    fifo_count_q;

    logic                  active_valid_q;
    logic [5:0]            active_cid_q;
    logic [DATA_WIDTH-1:0] active_param_q;

    logic [31:0] ev_count_q;
    logic [31:0] comm_count_q;
    logic [31:0] rej_count_q;
    logic [DATA_WIDTH-1:0] last_state_q;
    logic [31:0] seq_dropped_q;
    logic        seq_overflow_q;
    logic        stalled_ext_q;
    logic [5:0]  stalled_cid_q;
    logic [DATA_WIDTH-1:0] stalled_param_q;

    logic        ext_sw_stalled_q;
    logic [5:0]  ext_sw_cid_q;
    logic [DATA_WIDTH-1:0] ext_sw_param_q;
    logic        axi_sw_overflow_q;
    logic [31:0] axi_sw_dropped_q;

    wire seq_busy = active_valid_q || (fifo_count_q != '0);
    assign busy              = seq_busy || sw_trigger_q;
    assign hw_pipeline_busy_o = busy;

    wire direct_mmio_write = (write_addr >= 13'h100) && (write_addr < 13'h500) &&
                             (write_addr[1:0] == 2'b00);
    wire cfg_write_fire = write_fire && (write_strb == 4'hf) && !busy &&
                          ((write_addr == 13'h004) || (write_addr == 13'h008) ||
                           (write_addr == 13'h00c) || (write_addr == 13'h02c) ||
                           direct_mmio_write);
    wire w1c_clear_overflow = write_fire && (write_strb == 4'hf) && !busy &&
                              (write_addr == 13'h02c) && write_data[16];

    wire ext_trigger_blocked = sw_trigger_q || cfg_write_fire;
    wire seq_trigger_valid   = sw_trigger_q || (!ext_trigger_blocked && ext_hw_trigger_valid_i);
    wire [5:0] seq_trigger_cid = sw_trigger_q ? 6'd0 : ext_hw_trigger_cid_i;
    wire [DATA_WIDTH-1:0] seq_trigger_param = sw_trigger_q ? event_param_q : ext_hw_trigger_param_i;

    // ------------------------------------------------------------------------
    // 4. Shared Concept Read Multiplexer & 1-Cycle Combinational Evaluator
    //    Shared between active execution (active_valid_q == 1) and AXI readback
    //    when idle (!active_valid_q), eliminating a duplicate K:1 array MUX.
    // ------------------------------------------------------------------------
    wire [7:0]  direct_read_word_idx = read_addr_q[9:2] - 8'h40;
    wire [7:0]  eff_read_word_idx    = (read_addr_q >= 13'h100 && read_addr_q < 13'h500)
                                     ? direct_read_word_idx : cfg_addr_q;
    wire [5:0]  eff_read_cid         = eff_read_word_idx[7:2];
    wire [1:0]  eff_read_wsel        = eff_read_word_idx[1:0];

    wire [5:0]               mux_cid_w   = active_valid_q ? active_cid_q : eff_read_cid;
    wire [CID_IDX_WIDTH-1:0] mux_cid_idx = mux_cid_w[CID_IDX_WIDTH-1:0];
    wire [CID_IDX_WIDTH-1:0] active_cid_idx = active_cid_q[CID_IDX_WIDTH-1:0];

    logic [DATA_WIDTH-1:0] cur_state_w;
    logic [DATA_WIDTH-1:0] cur_operand_w;
    logic [3:0]            cur_pred_op_w;
    logic [4:0]            cur_guard_flags_w;
    logic [7:0]            cur_hazard_limit_w;
    logic [3:0]            cur_action_op_w;
    logic [5:0]            cur_sub_cid_w;
    logic                  cur_sub_oob_w;

    always_comb begin
        cur_state_w        = '0;
        cur_operand_w      = '0;
        cur_pred_op_w      = 4'd0;
        cur_guard_flags_w  = 5'd0;
        cur_hazard_limit_w = 8'd0;
        cur_action_op_w    = 4'd0;
        cur_sub_cid_w      = 6'd0;
        cur_sub_oob_w      = 1'b0;
        if ({1'b0, mux_cid_w} < NUM_C_U7) begin
            cur_state_w        = state_q[mux_cid_idx];
            cur_operand_w      = operand_q[mux_cid_idx];
            cur_pred_op_w      = pred_op_q[mux_cid_idx];
            cur_guard_flags_w  = guard_flags_q[mux_cid_idx];
            cur_hazard_limit_w = hazard_limit_q[mux_cid_idx];
            cur_action_op_w    = action_op_q[mux_cid_idx];
            cur_sub_cid_w      = sub_cid_q[mux_cid_idx];
            cur_sub_oob_w      = sub_oob_q[mux_cid_idx];
        end
    end

    wire signed [DATA_WIDTH-1:0] range_lo_sext_w = {{(DATA_WIDTH-16){cur_operand_w[15]}}, cur_operand_w[15:0]};
    wire signed [DATA_WIDTH-1:0] range_hi_sext_w = {{(DATA_WIDTH-16){cur_operand_w[31]}}, cur_operand_w[31:16]};

    logic pred_raw_res_w;
    always_comb begin
        case (cur_pred_op_w)
            4'h0: pred_raw_res_w = 1'b1; // NOP
            4'h1: pred_raw_res_w = (active_param_q == cur_operand_w); // EQ
            4'h2: pred_raw_res_w = (active_param_q != cur_operand_w); // NEQ
            `ifdef MUTANT_FLIP_GT
            4'h3: pred_raw_res_w = ($signed(active_param_q) >= $signed(cur_operand_w)); // Mutant: >= instead of >
            `else
            4'h3: pred_raw_res_w = ($signed(active_param_q) > $signed(cur_operand_w));  // GT
            `endif
            4'h4: pred_raw_res_w = ($signed(active_param_q) < $signed(cur_operand_w));  // LT
            4'h5: pred_raw_res_w = ($signed(active_param_q) >= range_lo_sext_w) &&
                                   ($signed(active_param_q) <= range_hi_sext_w);         // RANGE
            4'h6: pred_raw_res_w = ((active_param_q & cur_operand_w) != 32'd0);         // BITMASK
            default: pred_raw_res_w = 1'b0;
        endcase
    end

    wire [DATA_WIDTH-1:0] add_res_w = cur_state_w + cur_operand_w;
    wire [DATA_WIDTH-1:0] sub_res_w = cur_state_w - cur_operand_w;
    wire add_ovf_w = (cur_state_w[DATA_WIDTH-1] == cur_operand_w[DATA_WIDTH-1]) &&
                     (add_res_w[DATA_WIDTH-1] != cur_state_w[DATA_WIDTH-1]);
    wire sub_ovf_w = (cur_state_w[DATA_WIDTH-1] != cur_operand_w[DATA_WIDTH-1]) &&
                     (sub_res_w[DATA_WIDTH-1] != cur_state_w[DATA_WIDTH-1]);

    logic [DATA_WIDTH-1:0] candidate_state_w;
    logic                  action_valid_w;
    logic                  arith_overflow_w;

    always_comb begin
        action_valid_w   = 1'b1;
        arith_overflow_w = 1'b0;
        case (cur_action_op_w)
            4'h0: begin // ASSIGN
                candidate_state_w = active_param_q;
            end
            4'h1: begin // INC
                candidate_state_w = cur_state_w + {{(DATA_WIDTH-1){1'b0}}, 1'b1};
                arith_overflow_w  = (cur_state_w == {1'b0, {(DATA_WIDTH-1){1'b1}}});
            end
            4'h2: begin // DEC
                candidate_state_w = cur_state_w - {{(DATA_WIDTH-1){1'b0}}, 1'b1};
                arith_overflow_w  = (cur_state_w == {1'b1, {(DATA_WIDTH-1){1'b0}}});
            end
            4'h3: begin // ADD
                candidate_state_w = add_res_w;
                arith_overflow_w  = add_ovf_w;
            end
            4'h4: begin // SUB
                candidate_state_w = sub_res_w;
                arith_overflow_w  = sub_ovf_w;
            end
            default: begin
                candidate_state_w = cur_state_w;
                action_valid_w    = 1'b0;
            end
        endcase
    end

    wire assumption_known_w = cur_guard_flags_w[0];
    wire assumption_true_w  = cur_guard_flags_w[3] ? ~pred_raw_res_w : pred_raw_res_w;
    wire invariant_known_w  = cur_guard_flags_w[1];
    `ifdef MUTANT_SKIP_INVARIANT
    wire invariant_true_w   = 1'b1;
    `else
    wire invariant_true_w   = !arith_overflow_w && ($signed(candidate_state_w) >= 0);
    `endif
    wire hazard_true_w      = cur_guard_flags_w[2] && (cur_hazard_limit_w != 8'd0) &&
                              ($signed(active_param_q) > $signed({24'd0, cur_hazard_limit_w}));

    wire step_commit_w = active_valid_q && action_valid_w &&
                         assumption_known_w && assumption_true_w &&
                         invariant_known_w && invariant_true_w && !hazard_true_w;
    wire step_reject_w = active_valid_q && !step_commit_w;

    `ifdef MUTANT_DROP_CASCADE
    wire cascade_req_w = 1'b0;
    `else
    wire cascade_req_w = step_commit_w && !cur_sub_oob_w &&
                         (cur_guard_flags_w[4] || (cur_sub_cid_w != 6'd0)) &&
                         (cur_sub_cid_w != active_cid_q);
    `endif

    // ------------------------------------------------------------------------
    // 5. Single-Write-Port Input Queue & Atomic 1-Cycle Cascade Arbitration
    // ------------------------------------------------------------------------
    wire [PTR_WIDTH-1:0] rd_ptr_next1 = (({1'b0, fifo_rd_ptr_q} + {{PTR_WIDTH{1'b0}}, 1'b1}) >= DEPTH_CNT)
                                      ? '0 : (fifo_rd_ptr_q + PTR_ONE);
    wire [PTR_WIDTH-1:0] wr_ptr_next1 = (({1'b0, fifo_wr_ptr_q} + {{PTR_WIDTH{1'b0}}, 1'b1}) >= DEPTH_CNT)
                                      ? '0 : (fifo_wr_ptr_q + PTR_ONE);

    wire seq_trigger_ready = (fifo_count_q < DEPTH_CNT);
    assign hw_trigger_ready_o        = seq_trigger_ready && !ext_trigger_blocked;
    assign fifo_overflow_o           = seq_overflow_q || axi_sw_overflow_q;
    assign events_dropped_count_o    = seq_dropped_q + axi_sw_dropped_q;
    assign hw_commit_pulse_o         = step_commit_w;
    assign hw_reject_pulse_o         = step_reject_w;
    assign hw_commit_cid_o           = active_cid_q;
    assign hw_last_committed_state_o = last_state_q;

    wire ext_accept_w         = seq_trigger_valid && seq_trigger_ready;
    wire fifo_bypass_w        = ext_accept_w && !active_valid_q && (fifo_count_q == '0);
    wire fifo_push_w          = ext_accept_w && !fifo_bypass_w;
    wire fifo_pop_w           = !cascade_req_w && (fifo_count_q != '0);
    wire same_stalled_payload = (seq_trigger_cid == stalled_cid_q) &&
                                (seq_trigger_param == stalled_param_q);

    function automatic logic [3:0] encode_pred_op(input logic [7:0] raw_op);
        encode_pred_op = (raw_op <= 8'h06) ? raw_op[3:0] : 4'hf;
    endfunction

    function automatic logic [3:0] encode_act_op(input logic [7:0] raw_op);
        encode_act_op = (raw_op <= 8'h04) ? raw_op[3:0] : 4'hf;
    endfunction

    logic [31:0] cfg_word_rdata_w;
    always_comb begin
        cfg_word_rdata_w = 32'd0;
        if (!active_valid_q && ({1'b0, eff_read_cid} < NUM_C_U7)) begin
            case (eff_read_wsel)
                2'b00: cfg_word_rdata_w = cur_state_w;
                2'b01: cfg_word_rdata_w = cur_operand_w;
                2'b10: cfg_word_rdata_w = {
                    (cur_action_op_w == 4'hf) ? 8'hff : {4'b0, cur_action_op_w},
                    cur_hazard_limit_w,
                    3'b0, cur_guard_flags_w,
                    (cur_pred_op_w == 4'hf) ? 8'hff : {4'b0, cur_pred_op_w}
                };
                2'b11: cfg_word_rdata_w = {25'b0, cur_sub_oob_w, cur_sub_cid_w};
            endcase
        end
    end

    wire [7:0]  direct_write_word_idx = write_addr[9:2] - 8'h40;
    wire [7:0]  eff_write_word_idx    = direct_mmio_write ? direct_write_word_idx : cfg_addr_q;
    wire [5:0]  eff_write_cid         = eff_write_word_idx[7:2];
    wire [CID_IDX_WIDTH-1:0] eff_write_cid_idx = eff_write_cid[CID_IDX_WIDTH-1:0];
    wire [1:0]  eff_write_wsel        = eff_write_word_idx[1:0];

    // Single-port synchronous FIFO memory write (maps cleanly to LUTRAM/FDRE)
    always_ff @(posedge clk) begin
        if (fifo_push_w) begin
            fifo_cid_q[fifo_wr_ptr_q]   <= seq_trigger_cid;
            fifo_param_q[fifo_wr_ptr_q] <= seq_trigger_param;
        end
    end

    // ------------------------------------------------------------------------
    // 6. Sequential Datapath & AXI4-Lite State Machine (Synchronous Reset -> FDRE)
    // ------------------------------------------------------------------------
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            aw_pending        <= 1'b0;
            w_pending         <= 1'b0;
            read_pending      <= 1'b0;
            awaddr_q          <= 13'd0;
            read_addr_q       <= 13'd0;
            wdata_q           <= 32'd0;
            wstrb_q           <= 4'd0;
            bresp             <= OKAY;
            bvalid            <= 1'b0;
            rdata             <= 32'd0;
            rresp             <= OKAY;
            rvalid            <= 1'b0;

            cfg_addr_q        <= 8'd0;
            event_param_q     <= '0;
            sw_trigger_q      <= 1'b0;

            fifo_wr_ptr_q     <= '0;
            fifo_rd_ptr_q     <= '0;
            fifo_count_q      <= '0;

            active_valid_q    <= 1'b0;
            active_cid_q      <= 6'd0;
            active_param_q    <= '0;

            ev_count_q        <= 32'd0;
            comm_count_q      <= 32'd0;
            rej_count_q       <= 32'd0;
            last_state_q      <= '0;
            seq_dropped_q     <= 32'd0;
            seq_overflow_q    <= 1'b0;
            stalled_ext_q     <= 1'b0;
            stalled_cid_q     <= 6'd0;
            stalled_param_q   <= '0;

            ext_sw_stalled_q  <= 1'b0;
            ext_sw_cid_q      <= 6'd0;
            ext_sw_param_q    <= '0;
            axi_sw_overflow_q <= 1'b0;
            axi_sw_dropped_q  <= 32'd0;

            for (int c = 0; c < NUM_CONCEPTS; c++) begin
                state_q[c]        <= '0;
                operand_q[c]      <= '0;
                pred_op_q[c]      <= 4'd0;
                guard_flags_q[c]  <= 5'd0;
                hazard_limit_q[c] <= 8'd0;
                action_op_q[c]    <= 4'd0;
                sub_cid_q[c]      <= 6'd0;
                sub_oob_q[c]      <= 1'b0;
            end
        end else begin
            sw_trigger_q <= 1'b0;

            // ----------------------------------------------------------------
            // A. External Stall / Drop Telemetry on B4 Boundary & Queue Full
            // ----------------------------------------------------------------
            if (w1c_clear_overflow) begin
                axi_sw_overflow_q <= 1'b0;
                axi_sw_dropped_q  <= 32'd0;
                seq_overflow_q    <= 1'b0;
                seq_dropped_q     <= 32'd0;
                stalled_ext_q     <= 1'b0;
                if (ext_hw_trigger_valid_i) begin
                    ext_sw_stalled_q <= 1'b1;
                    ext_sw_cid_q     <= ext_hw_trigger_cid_i;
                    ext_sw_param_q   <= ext_hw_trigger_param_i;
                end else begin
                    ext_sw_stalled_q <= 1'b0;
                end
            end else begin
                if (!ext_sw_stalled_q) begin
                    if (ext_trigger_blocked && seq_trigger_ready && ext_hw_trigger_valid_i) begin
                        ext_sw_stalled_q <= 1'b1;
                        ext_sw_cid_q     <= ext_hw_trigger_cid_i;
                        ext_sw_param_q   <= ext_hw_trigger_param_i;
                    end
                end else begin
                    if (!ext_hw_trigger_valid_i) begin
                        axi_sw_overflow_q <= 1'b1;
                        axi_sw_dropped_q  <= axi_sw_dropped_q + 32'd1;
                        ext_sw_stalled_q  <= 1'b0;
                    end else if ((ext_hw_trigger_cid_i != ext_sw_cid_q) ||
                                 (ext_hw_trigger_param_i != ext_sw_param_q)) begin
                        axi_sw_overflow_q <= 1'b1;
                        axi_sw_dropped_q  <= axi_sw_dropped_q + 32'd1;
                        if (hw_trigger_ready_o) begin
                            ext_sw_stalled_q <= 1'b0;
                        end else begin
                            ext_sw_stalled_q <= 1'b1;
                            ext_sw_cid_q     <= ext_hw_trigger_cid_i;
                            ext_sw_param_q   <= ext_hw_trigger_param_i;
                        end
                    end else if (hw_trigger_ready_o) begin
                        ext_sw_stalled_q <= 1'b0;
                    end
                end

                if (!stalled_ext_q) begin
                    if (seq_trigger_valid && !seq_trigger_ready) begin
                        stalled_ext_q   <= 1'b1;
                        stalled_cid_q   <= seq_trigger_cid;
                        stalled_param_q <= seq_trigger_param;
                    end
                end else begin
                    if (!seq_trigger_valid) begin
                        seq_overflow_q <= 1'b1;
                        seq_dropped_q  <= seq_dropped_q + 32'd1;
                        stalled_ext_q  <= 1'b0;
                    end else if (!same_stalled_payload) begin
                        seq_overflow_q <= 1'b1;
                        seq_dropped_q  <= seq_dropped_q + 32'd1;
                        if (seq_trigger_ready) begin
                            stalled_ext_q <= 1'b0;
                        end else begin
                            stalled_ext_q   <= 1'b1;
                            stalled_cid_q   <= seq_trigger_cid;
                            stalled_param_q <= seq_trigger_param;
                        end
                    end else if (seq_trigger_ready) begin
                        stalled_ext_q <= 1'b0;
                    end
                end
            end

            // ----------------------------------------------------------------
            // B. 1-Cycle Concept Evaluation & Atomic Cascade Step
            // ----------------------------------------------------------------
            if (active_valid_q) begin
                ev_count_q <= ev_count_q + 32'd1;
                if (step_commit_w) begin
                    comm_count_q <= comm_count_q + 32'd1;
                    last_state_q <= candidate_state_w;
                    if ({1'b0, active_cid_q} < NUM_C_U7) begin
                        state_q[active_cid_idx] <= candidate_state_w;
                    end
                end else begin
                    rej_count_q <= rej_count_q + 32'd1;
                end
            end

            if (fifo_push_w) begin
                fifo_wr_ptr_q <= wr_ptr_next1;
            end
            if (fifo_pop_w) begin
                fifo_rd_ptr_q <= rd_ptr_next1;
            end
            case ({fifo_push_w, fifo_pop_w})
                2'b10:   fifo_count_q <= fifo_count_q + {{PTR_WIDTH{1'b0}}, 1'b1};
                2'b01:   fifo_count_q <= fifo_count_q - {{PTR_WIDTH{1'b0}}, 1'b1};
                default: fifo_count_q <= fifo_count_q;
            endcase

            if (cascade_req_w) begin
                active_valid_q <= 1'b1;
                active_cid_q   <= cur_sub_cid_w;
                active_param_q <= candidate_state_w;
            end else if (fifo_pop_w) begin
                active_valid_q <= 1'b1;
                active_cid_q   <= fifo_cid_q[fifo_rd_ptr_q];
                active_param_q <= fifo_param_q[fifo_rd_ptr_q];
            end else if (fifo_bypass_w) begin
                active_valid_q <= 1'b1;
                active_cid_q   <= seq_trigger_cid;
                active_param_q <= seq_trigger_param;
            end else begin
                active_valid_q <= 1'b0;
            end

            // ----------------------------------------------------------------
            // C. AXI4-Lite Write & Read Channels
            // ----------------------------------------------------------------
            if (bvalid && bready) bvalid <= 1'b0;
            if (rvalid && rready) rvalid <= 1'b0;

            if (aw_fire) begin
                awaddr_q   <= awaddr;
                aw_pending <= 1'b1;
            end
            if (w_fire) begin
                wdata_q   <= wdata;
                wstrb_q   <= wstrb;
                w_pending <= 1'b1;
            end

            if (write_fire) begin
                aw_pending <= 1'b0;
                w_pending  <= 1'b0;
                bvalid     <= 1'b1;
                bresp      <= OKAY;
                if (write_strb != 4'hf) begin
                    bresp <= SLVERR;
                end else if (direct_mmio_write || (write_addr == 13'h008)) begin
                    if (busy) begin
                        bresp <= SLVERR;
                    end else if ({1'b0, eff_write_cid} < NUM_C_U7) begin
                        case (eff_write_wsel)
                            2'b00: state_q[eff_write_cid_idx]   <= write_data;
                            2'b01: operand_q[eff_write_cid_idx] <= write_data;
                            2'b10: begin
                                pred_op_q[eff_write_cid_idx]      <= encode_pred_op(write_data[7:0]);
                                guard_flags_q[eff_write_cid_idx]  <= write_data[12:8];
                                hazard_limit_q[eff_write_cid_idx] <= write_data[23:16];
                                action_op_q[eff_write_cid_idx]    <= encode_act_op(write_data[31:24]);
                            end
                            2'b11: begin
                                sub_cid_q[eff_write_cid_idx] <= write_data[5:0];
                                sub_oob_q[eff_write_cid_idx] <= (write_data >= 32'd64);
                            end
                        endcase
                    end
                end else begin
                    case (write_addr)
                        13'h004: if (busy) bresp <= SLVERR;
                                  else cfg_addr_q <= write_data[7:0];
                        13'h00c: if (busy) bresp <= SLVERR;
                                  else event_param_q <= write_data;
                        13'h010: if (busy || (write_data != 32'd1)) bresp <= SLVERR;
                                  else sw_trigger_q <= 1'b1;
                        13'h02c: if (busy) bresp <= SLVERR;
                        default: bresp <= DECERR;
                    endcase
                end
            end

            if (arvalid && arready) begin
                read_addr_q  <= araddr;
                read_pending <= 1'b1;
            end else if (read_pending) begin
                read_pending <= 1'b0;
                rvalid       <= 1'b1;
                rresp        <= OKAY;
                if ((read_addr_q >= 13'h100) && (read_addr_q < 13'h500) &&
                    (read_addr_q[1:0] == 2'b00)) begin
                    rdata <= cfg_word_rdata_w;
                end else begin
                    case (read_addr_q)
                        13'h000: rdata <= 32'h4b524743; // ASCII "KRGC"
                        13'h004: rdata <= {24'b0, cfg_addr_q};
                        13'h008: rdata <= cfg_word_rdata_w;
                        13'h00c: rdata <= event_param_q;
                        13'h014: rdata <= {31'b0, busy};
                        13'h018: rdata <= ev_count_q;
                        13'h01c: rdata <= comm_count_q;
                        13'h020: rdata <= rej_count_q;
                        13'h024: rdata <= last_state_q;
                        13'h028: rdata <= events_dropped_count_o;
                        13'h02c: rdata <= {15'b0, fifo_overflow_o, 8'b0, hw_trigger_ready_o, 7'b0};
                        default: begin
                            rdata <= 32'd0;
                            rresp <= DECERR;
                        end
                    endcase
                end
            end
        end
    end
endmodule
