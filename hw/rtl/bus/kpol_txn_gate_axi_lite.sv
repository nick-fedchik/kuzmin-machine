`timescale 1ns/1ps

module kpol_txn_gate_axi_lite (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 S_AXI_ACLK CLK",
       X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI_ACLK, ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET S_AXI_ARESETN, FREQ_HZ 100000000" *)
    input  logic        s_axi_aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 S_AXI_ARESETN RST",
       X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI_ARESETN, POLARITY ACTIVE_LOW" *)
    input  logic        s_axi_aresetn,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWADDR",
       X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 13, FREQ_HZ 100000000, ID_WIDTH 0, HAS_BRESP 1, HAS_RRESP 1" *)
    input  logic [12:0] s_axi_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *)
    input  logic        s_axi_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *)
    output logic        s_axi_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *)
    input  logic [31:0] s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *)
    input  logic [3:0]  s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *)
    input  logic        s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *)
    output logic        s_axi_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *)
    output logic [1:0]  s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *)
    output logic        s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *)
    input  logic        s_axi_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *)
    input  logic [12:0] s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *)
    input  logic        s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *)
    output logic        s_axi_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *)
    output logic [31:0] s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *)
    output logic [1:0]  s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *)
    output logic        s_axi_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *)
    input  logic        s_axi_rready,

    // Status and state monitors for physical board LEDs
    output logic [7:0]  status_monitor_o,
    output logic [31:0] state_monitor_o,

    // Optional manual external event trigger (e.g. from physical pushbuttons)
    input  logic        ext_event_valid_i,
    input  logic [31:0] ext_candidate_value_i,
    input  logic [6:0]  ext_conditions_i,

    // EXP-06: Physical I/O pins for "0p0" reactive trigger
    input  logic        ext_pin_0p0_i,
    output logic        reactive_out_0p0_o
);
    localparam logic [1:0] AXI_RESP_OKAY   = 2'b00;
    localparam logic [1:0] AXI_RESP_SLVERR = 2'b10;
    localparam logic [1:0] AXI_RESP_DECERR = 2'b11;

    logic aw_pending_q;
    logic w_pending_q;
    logic [12:0] awaddr_q;
    logic [31:0] wdata_q;
    logic [3:0] wstrb_q;
    logic [31:0] candidate_value_q;
    logic [6:0] conditions_q;
    logic [7:0] status_q;
    logic busy_q;
    logic event_valid_q;

    // Registers for Hardware Invariant / Predicate Evaluator
    logic [31:0] lower_bound_q;
    logic [31:0] upper_bound_q;
    logic [7:0]  rule_cfg_q;

    // EXP-04: Free-running 64-bit Hardware Cycle Counter (100 MHz, 10 ns)
    logic [63:0] hw_cycle_cnt_q;
    logic [31:0] last_txn_cycles_q;
    logic [31:0] txn_timer_q;
    logic        txn_measuring_q;

    // EXP-05: Hardware Euclid Reactive Core Registers & Signals
    logic [31:0] euclid_a_init_q;
    logic [31:0] euclid_b_init_q;
    logic        euclid_start_pulse_q;
    wire         euclid_busy;
    wire         euclid_done;
    wire         euclid_error;
    wire [31:0]  euclid_result;
    wire [15:0]  euclid_iterations;
    wire [31:0]  euclid_cycle_count;
    wire [31:0]  euclid_concept_a;
    wire [31:0]  euclid_concept_b;

    // EXP-07: BRAM Concepts Table & Core Registers
    logic [31:0] bram_ctrl_q;
    logic        bram_ctrl_start_pulse_q;
    logic [7:0]  bram_manual_addr_q;
    logic [31:0] bram_manual_wdata_q;
    logic        bram_manual_we_pulse_q;

    wire         bram_core_busy;
    wire         bram_core_done;
    wire [31:0]  bram_core_cycles;
    wire [31:0]  bram_manual_rdata;
    wire         bram_collision;

    // EXP-08: RCFC Rendezvous & Fallback Engine Registers & Signals
    logic [31:0] rcfc_ctrl_q;
    logic        rcfc_start_pulse_q;
    logic [5:0]  rcfc_slot_sel_q;

    wire         rcfc_busy;
    wire         rcfc_done;
    wire         rcfc_tc01_pass;
    wire         rcfc_tc02_pass;
    wire         rcfc_tc03_pass;
    wire         rcfc_tc04_pass;
    wire         rcfc_deadlock_error;
    wire         rcfc_drop_error;
    wire [3:0]   rcfc_current_tc;
    wire [15:0]  rcfc_events_processed;
    wire [31:0]  rcfc_cycle_count;
    wire [15:0]  rcfc_events_enqueued;
    wire [15:0]  rcfc_events_dropped;
    wire [31:0]  rcfc_result;
    wire [2:0]   rcfc_slot_state;
    wire [7:0]   rcfc_slot_wait_cycles;
    wire [15:0]  rcfc_slot_payload_lo;

    // EXP-09: Cascade & Arbiter Stress Suite B (TC-05 .. TC-08)
    logic [31:0] suite_b_ctrl_q;
    logic        suite_b_start_pulse_q;

    wire         suite_b_busy;
    wire         suite_b_done;
    wire         suite_b_tc05_pass;
    wire         suite_b_tc06_pass;
    wire         suite_b_tc07_pass;
    wire         suite_b_tc08_pass;
    wire         suite_b_fail_error;
    wire [3:0]   suite_b_current_tc;
    wire [31:0]  suite_b_cycle_count;
    wire [31:0]  suite_b_result0;
    wire [31:0]  suite_b_result1;

    // EXP-10: Streaming Dataflow Pipeline Engine
    logic [31:0] stream_ctrl_q;
    logic        stream_start_pulse_q;

    wire         stream_busy;
    wire         stream_done;
    wire         stream_pass;
    wire [31:0]  stream_cycle_count;
    wire [15:0]  stream_processed_count;
    wire [15:0]  stream_clamped_count;
    wire [31:0]  stream_checksum;
    wire [31:0]  stream_last_val;

    // EXP-06: Autonomous & Physical I/O Trigger Engine for "0p0"
    logic [31:0] io_trig_ctrl_q;
    logic        io_trig_start_pulse_q;
    logic        io_trig_clear_pulse_q;

    wire         io_trig_busy;
    wire         io_trig_done;
    wire         io_trig_pass;
    wire [15:0]  io_trig_last_latency;
    wire [15:0]  io_trig_min_latency;
    wire [15:0]  io_trig_max_latency;
    wire [31:0]  io_trig_trigger_count;
    wire [63:0]  io_trig_last_timestamp;

    // BRAM Port A Signals (AXI)
    wire  [7:0]  bram_a_addr;
    wire  [31:0] bram_a_wdata;
    wire  [3:0]  bram_a_wstrb;
    wire         bram_a_we;
    wire  [31:0] bram_a_rdata;

    // BRAM Port B Signals (Core)
    wire  [7:0]  bram_b_addr;
    wire  [31:0] bram_b_wdata;
    wire  [3:0]  bram_b_wstrb;
    wire         bram_b_we;
    wire  [31:0] bram_b_rdata;

    // Signals from Hardware Predicate Evaluator (km_predicate_evaluator)
    logic [7:0]  hw_predicate_vector;
    logic        hw_invariant_ok;
    logic        hw_big_dot;

    logic [31:0] state;
    logic committed;
    logic rejected;
    logic rejected_input;
    logic rejected_invariant;
    logic changed;
    logic hazard_observed;
    logic unknown_hazard;

    // AXI read pipelining
    logic        ar_busy_q;
    logic [12:0] ar_latched_addr_q;
    logic [31:0] read_value;
    logic [1:0]  read_response;

    wire aw_fire = s_axi_awvalid && s_axi_awready;
    wire w_fire  = s_axi_wvalid && s_axi_wready;

    wire write_fire = (aw_pending_q || aw_fire) && (w_pending_q || w_fire);
    wire [12:0] write_address = aw_pending_q ? awaddr_q : s_axi_awaddr;
    wire [31:0] write_data   = w_pending_q ? wdata_q : s_axi_wdata;
    wire [3:0] write_strobe  = w_pending_q ? wstrb_q : s_axi_wstrb;

    assign s_axi_awready = !aw_pending_q && !s_axi_bvalid;
    assign s_axi_wready  = !w_pending_q && !s_axi_bvalid;
    assign s_axi_arready = !ar_busy_q && !s_axi_rvalid;

    assign status_monitor_o = status_q;
    assign state_monitor_o  = state;

    function automatic [31:0] merge_write_bytes(
        input logic [31:0] old_value,
        input logic [31:0] new_value,
        input logic [3:0] strobe
    );
        integer byte_index;
        begin
            merge_write_bytes = old_value;
            for (byte_index = 0; byte_index < 4; byte_index = byte_index + 1) begin
                if (strobe[byte_index]) begin
                    merge_write_bytes[byte_index*8 +: 8] = new_value[byte_index*8 +: 8];
                end
            end
        end
    endfunction

    // Port A BRAM address multiplexer (Write vs Read)
    wire bram_write_active = write_fire && (write_address[12:10] == 3'b100) && (write_address[1:0] == 2'b00);
    wire is_bram_read      = (ar_latched_addr_q[12:10] == 3'b100);

    assign bram_a_addr  = bram_write_active ? write_address[9:2] :
                          (s_axi_arvalid ? s_axi_araddr[9:2] : ar_latched_addr_q[9:2]);
    assign bram_a_wdata = write_data;
    assign bram_a_wstrb = write_strobe;
    assign bram_a_we    = bram_write_active;

    // Read address decoder (evaluates latched address)
    always @* begin
        read_value    = 32'b0;
        read_response = AXI_RESP_OKAY;

        if (ar_latched_addr_q[1:0] != 2'b00) begin
            read_response = AXI_RESP_DECERR;
        end else if (is_bram_read) begin
            // BRAM Concepts Table: 0x1000 .. 0x13FF (64 concepts x 4 words)
            read_value = bram_a_rdata;
        end else if (ar_latched_addr_q[12:8] == 5'b00000) begin
            // Control and Status Registers: 0x00 .. 0xFF
            case (ar_latched_addr_q[7:0])
                8'h00: read_value = candidate_value_q;
                8'h04: read_value = {25'b0, conditions_q};
                8'h08: read_value = 32'b0;
                8'h0C: read_value = {23'b0, busy_q, status_q};
                8'h10: read_value = state;
                8'h14: read_value = 32'h4B504F4C; // ASCII "KPOL"
                8'h18: read_value = lower_bound_q;
                8'h1C: read_value = upper_bound_q;
                8'h20: read_value = {24'b0, rule_cfg_q};
                8'h24: read_value = {24'b0, hw_predicate_vector};
                8'h28: read_value = {31'b0, hw_big_dot};
                // EXP-04: Cycle Counter & Transaction Profiler
                8'h2C: read_value = hw_cycle_cnt_q[31:0];      // REG_CYCLE_CNT_LO
                8'h30: read_value = hw_cycle_cnt_q[63:32];     // REG_CYCLE_CNT_HI
                8'h34: read_value = last_txn_cycles_q;         // REG_LAST_TXN_CYCLES
                // EXP-05: Euclid Engine Registers
                8'h38: read_value = euclid_concept_a;          // REG_EUCLID_A (Live A)
                8'h3C: read_value = euclid_concept_b;          // REG_EUCLID_B (Live B)
                8'h40: read_value = 32'b0;                     // REG_EUCLID_CMD
                8'h44: read_value = {8'b0, euclid_iterations, 5'b0, euclid_error, euclid_done, euclid_busy};
                8'h48: read_value = euclid_cycle_count;        // REG_EUCLID_CYCLES
                8'h4C: read_value = euclid_result;             // REG_EUCLID_RESULT
                // EXP-07: BRAM Concept Core Registers
                8'h50: read_value = bram_ctrl_q;               // REG_BRAM_CTRL
                8'h54: read_value = {29'b0, bram_collision, bram_core_done, bram_core_busy}; // REG_BRAM_STATUS
                8'h58: read_value = bram_core_cycles;          // REG_BRAM_CYCLES
                8'h5C: read_value = {24'b0, bram_manual_addr_q}; // REG_BRAM_PORT_B_ADDR
                8'h60: read_value = bram_manual_rdata;         // REG_BRAM_PORT_B_DATA
                // EXP-08: RCFC Rendezvous & Fallback Engine Registers
                8'h64: read_value = rcfc_ctrl_q;               // REG_RCFC_CTRL
                8'h68: read_value = {rcfc_events_processed, 4'b0, rcfc_current_tc, rcfc_drop_error, rcfc_deadlock_error, rcfc_tc04_pass, rcfc_tc03_pass, rcfc_tc02_pass, rcfc_tc01_pass, rcfc_done, rcfc_busy}; // REG_RCFC_STATUS
                8'h6C: read_value = rcfc_cycle_count;          // REG_RCFC_CYCLES
                8'h70: read_value = {rcfc_slot_payload_lo, rcfc_slot_wait_cycles, 5'b0, rcfc_slot_state}; // REG_RCFC_SLOT_STATE
                8'h74: read_value = {rcfc_events_dropped, rcfc_events_enqueued}; // REG_RCFC_AVALANCHE_STATS
                8'h78: read_value = rcfc_result;               // REG_RCFC_RESULT
                // EXP-09: Cascade & Arbiter Stress Suite B Registers
                8'h80: read_value = suite_b_ctrl_q;            // REG_SUITE_B_CTRL
                8'h84: read_value = {16'b0, 4'b0, suite_b_current_tc, suite_b_fail_error, 1'b0, suite_b_tc08_pass, suite_b_tc07_pass, suite_b_tc06_pass, suite_b_tc05_pass, suite_b_done, suite_b_busy}; // REG_SUITE_B_STATUS
                8'h88: read_value = suite_b_cycle_count;       // REG_SUITE_B_CYCLES
                8'h8C: read_value = suite_b_result0;           // REG_SUITE_B_RES0
                8'h90: read_value = suite_b_result1;           // REG_SUITE_B_RES1
                // EXP-10: Streaming Dataflow Pipeline Registers
                8'h94: read_value = stream_ctrl_q;             // REG_STREAM_CTRL
                8'h98: read_value = {16'b0, 13'b0, stream_pass, stream_done, stream_busy}; // REG_STREAM_STATUS
                8'h9C: read_value = stream_cycle_count;        // REG_STREAM_CYCLES
                8'hA0: read_value = {stream_clamped_count, stream_processed_count}; // REG_STREAM_COUNTS
                8'hA4: read_value = stream_checksum;           // REG_STREAM_CHECKSUM
                8'hA8: read_value = stream_last_val;           // REG_STREAM_LAST_VAL
                // EXP-06: Autonomous & Physical I/O Trigger Registers ("0p0")
                8'hAC: read_value = io_trig_ctrl_q;            // REG_IO_TRIGGER_CTRL
                8'hB0: read_value = {16'b0, 10'b0, reactive_out_0p0_o, ext_pin_0p0_i, 1'b0, io_trig_pass, io_trig_done, io_trig_busy}; // REG_IO_TRIGGER_STATUS
                8'hB4: read_value = {io_trig_min_latency, io_trig_last_latency}; // REG_IO_TRIGGER_CYCLES
                8'hB8: read_value = {io_trig_max_latency, io_trig_trigger_count[15:0]}; // REG_IO_TRIGGER_MAX_CYCLES
                8'hBC: read_value = io_trig_last_timestamp[31:0];  // REG_IO_TRIGGER_TS_LO
                8'hC0: read_value = io_trig_last_timestamp[63:32]; // REG_IO_TRIGGER_TS_HI
                default: read_response = AXI_RESP_DECERR;
            endcase
        end else begin
            read_response = AXI_RESP_DECERR;
        end
    end

    // Combinational Hardware Predicate Evaluator
    km_predicate_evaluator #(
        .DATA_WIDTH(32)
    ) pred_eval (
        .candidate_value_i(candidate_value_q),
        .candidate_known_i(conditions_q[0]),
        .current_state_i(state),
        .lower_bound_i(lower_bound_q),
        .upper_bound_i(upper_bound_q),
        .rule_cfg_i(rule_cfg_q),
        .predicate_vector_o(hw_predicate_vector),
        .hw_invariant_ok_o(hw_invariant_ok),
        .big_dot_flag_o(hw_big_dot)
    );

    wire effective_inv_known = rule_cfg_q[5] ? 1'b1 : conditions_q[3];
    wire effective_inv_true  = rule_cfg_q[5] ? hw_invariant_ok : conditions_q[4];

    kpol_txn_gate #(
        .DATA_WIDTH(32)
    ) gate_inst (
        .clk_i(s_axi_aclk),
        .rst_ni(s_axi_aresetn),
        .event_valid_i(event_valid_q || ext_event_valid_i),
        .candidate_value_i(ext_event_valid_i ? ext_candidate_value_i : candidate_value_q),
        .candidate_known_i(ext_event_valid_i ? ext_conditions_i[0] : conditions_q[0]),
        .assumption_known_i(ext_event_valid_i ? ext_conditions_i[1] : conditions_q[1]),
        .assumption_true_i(ext_event_valid_i ? ext_conditions_i[2] : conditions_q[2]),
        .invariant_known_i(ext_event_valid_i ? ext_conditions_i[3] : effective_inv_known),
        .invariant_true_i(ext_event_valid_i ? ext_conditions_i[4] : effective_inv_true),
        .hazard_known_i(ext_event_valid_i ? ext_conditions_i[5] : conditions_q[5]),
        .hazard_true_i(ext_event_valid_i ? ext_conditions_i[6] : conditions_q[6]),
        .state_o(state),
        .committed_o(committed),
        .rejected_o(rejected),
        .rejected_input_o(rejected_input),
        .rejected_invariant_o(rejected_invariant),
        .changed_o(changed),
        .hazard_observed_o(hazard_observed),
        .unknown_hazard_o(unknown_hazard)
    );

    // EXP-05: Hardware Euclid Reactive Core
    km_euclid_core #(
        .DATA_WIDTH(32)
    ) euclid_core (
        .clk(s_axi_aclk),
        .rst_n(s_axi_aresetn),
        .start_i(euclid_start_pulse_q),
        .a_init_i(euclid_a_init_q),
        .b_init_i(euclid_b_init_q),
        .busy_o(euclid_busy),
        .done_o(euclid_done),
        .error_o(euclid_error),
        .result_o(euclid_result),
        .iterations_o(euclid_iterations),
        .cycle_count_o(euclid_cycle_count),
        .concept_a_o(euclid_concept_a),
        .concept_b_o(euclid_concept_b)
    );

    // EXP-07: Dual-Port BRAM Concept Table
    km_concept_bram #(
        .NUM_CONCEPTS(64),
        .DATA_WIDTH(32),
        .ADDR_WIDTH(8)
    ) concept_bram (
        .clk(s_axi_aclk),
        .rst_n(s_axi_aresetn),
        .a_addr_i(bram_a_addr),
        .a_wdata_i(bram_a_wdata),
        .a_wstrb_i(bram_a_wstrb),
        .a_we_i(bram_a_we),
        .a_rdata_o(bram_a_rdata),
        .b_addr_i(bram_b_addr),
        .b_wdata_i(bram_b_wdata),
        .b_wstrb_i(bram_b_wstrb),
        .b_we_i(bram_b_we),
        .b_rdata_o(bram_b_rdata),
        .collision_detected_o(bram_collision)
    );

    // EXP-07: Autonomous BRAM Concept Core for Port B
    km_concept_bram_core #(
        .DATA_WIDTH(32),
        .ADDR_WIDTH(8)
    ) concept_core (
        .clk(s_axi_aclk),
        .rst_n(s_axi_aresetn),
        .ctrl_start_i(bram_ctrl_start_pulse_q),
        .ctrl_op_i(bram_ctrl_q[1]),
        .ctrl_src_cid_i(bram_ctrl_q[13:8]),
        .ctrl_dst_cid_i(bram_ctrl_q[21:16]),
        .manual_we_i(bram_manual_we_pulse_q),
        .manual_addr_i(bram_manual_addr_q),
        .manual_wdata_i(bram_manual_wdata_q),
        .manual_rdata_o(bram_manual_rdata),
        .b_addr_o(bram_b_addr),
        .b_wdata_o(bram_b_wdata),
        .b_wstrb_o(bram_b_wstrb),
        .b_we_o(bram_b_we),
        .b_rdata_i(bram_b_rdata),
        .busy_o(bram_core_busy),
        .done_o(bram_core_done),
        .cycles_o(bram_core_cycles)
    );

    // EXP-08: RCFC Rendezvous & Fallback Engine Instance
    km_rcfc_engine #(
        .NUM_SLOTS(64),
        .QUEUE_DEPTH(64),
        .MAX_WAIT_CYCLES(256),
        .DATA_WIDTH(32)
    ) rcfc_engine (
        .clk(s_axi_aclk),
        .rst_n(s_axi_aresetn),
        .start_i(rcfc_start_pulse_q),
        .cmd_i(rcfc_ctrl_q[2:0]),
        .delay_param_i(rcfc_ctrl_q[15:8]),
        .slot_sel_i(rcfc_slot_sel_q),
        .busy_o(rcfc_busy),
        .done_o(rcfc_done),
        .tc01_pass_o(rcfc_tc01_pass),
        .tc02_pass_o(rcfc_tc02_pass),
        .tc03_pass_o(rcfc_tc03_pass),
        .tc04_pass_o(rcfc_tc04_pass),
        .timeout_deadlock_error_o(rcfc_deadlock_error),
        .event_drop_error_o(rcfc_drop_error),
        .current_tc_o(rcfc_current_tc),
        .events_processed_o(rcfc_events_processed),
        .cycle_count_o(rcfc_cycle_count),
        .events_enqueued_o(rcfc_events_enqueued),
        .events_dropped_o(rcfc_events_dropped),
        .result_o(rcfc_result),
        .slot_state_o(rcfc_slot_state),
        .slot_wait_cycles_o(rcfc_slot_wait_cycles),
        .slot_payload_lo_o(rcfc_slot_payload_lo)
    );

    // EXP-09: Cascade & Arbiter Stress Suite B Instance
    km_cascade_arbiter_engine #(
        .DATA_WIDTH(32)
    ) suite_b_engine (
        .clk(s_axi_aclk),
        .rst_n(s_axi_aresetn),
        .start_i(suite_b_start_pulse_q),
        .cmd_i(suite_b_ctrl_q[2:0]),
        .busy_o(suite_b_busy),
        .done_o(suite_b_done),
        .tc05_pass_o(suite_b_tc05_pass),
        .tc06_pass_o(suite_b_tc06_pass),
        .tc07_pass_o(suite_b_tc07_pass),
        .tc08_pass_o(suite_b_tc08_pass),
        .fail_error_o(suite_b_fail_error),
        .current_tc_o(suite_b_current_tc),
        .cycle_count_o(suite_b_cycle_count),
        .result0_o(suite_b_result0),
        .result1_o(suite_b_result1)
    );

    // EXP-10: Streaming Dataflow Pipeline Engine Instance
    km_stream_pipeline_engine #(
        .BURST_SIZE(1024)
    ) stream_engine (
        .clk_i(s_axi_aclk),
        .rst_ni(s_axi_aresetn),
        .start_i(stream_start_pulse_q),
        .mode_i(stream_ctrl_q[2:1]),
        .count_cfg_i(stream_ctrl_q[31:16]),
        .busy_o(stream_busy),
        .done_o(stream_done),
        .pass_o(stream_pass),
        .cycle_count_o(stream_cycle_count),
        .processed_count_o(stream_processed_count),
        .clamped_count_o(stream_clamped_count),
        .checksum_o(stream_checksum),
        .last_val_o(stream_last_val)
    );

    // EXP-06: Autonomous & Physical I/O Trigger Engine Instance ("0p0")
    km_io_trigger_engine io_trig_engine (
        .clk_i(s_axi_aclk),
        .rst_ni(s_axi_aresetn),
        .ext_pin_i(ext_pin_0p0_i),
        .reactive_out_o(reactive_out_0p0_o),
        .start_stim_i(io_trig_start_pulse_q),
        .clear_stats_i(io_trig_clear_pulse_q),
        .burst_count_i(io_trig_ctrl_q[31:16]),
        .busy_o(io_trig_busy),
        .done_o(io_trig_done),
        .pass_o(io_trig_pass),
        .last_latency_o(io_trig_last_latency),
        .min_latency_o(io_trig_min_latency),
        .max_latency_o(io_trig_max_latency),
        .trigger_count_o(io_trig_trigger_count),
        .last_timestamp_o(io_trig_last_timestamp)
    );

    // Main clocked sequential logic
    always_ff @(posedge s_axi_aclk or negedge s_axi_aresetn) begin
        if (!s_axi_aresetn) begin
            aw_pending_q            <= 1'b0;
            w_pending_q             <= 1'b0;
            awaddr_q                <= '0;
            wdata_q                 <= '0;
            wstrb_q                 <= '0;
            s_axi_bvalid            <= 1'b0;
            s_axi_bresp             <= AXI_RESP_OKAY;
            s_axi_rvalid            <= 1'b0;
            s_axi_rdata             <= '0;
            s_axi_rresp             <= AXI_RESP_OKAY;
            candidate_value_q       <= '0;
            conditions_q            <= '0;
            status_q                <= '0;
            busy_q                  <= 1'b0;
            event_valid_q           <= 1'b0;
            lower_bound_q           <= '0;
            upper_bound_q           <= '0;
            rule_cfg_q              <= '0;
            // EXP-04: Reset cycle counters
            hw_cycle_cnt_q          <= 64'd0;
            last_txn_cycles_q       <= 32'd0;
            txn_timer_q             <= 32'd0;
            txn_measuring_q         <= 1'b0;
            // EXP-05: Reset Euclid registers
            euclid_a_init_q         <= 32'd0;
            euclid_b_init_q         <= 32'd0;
            euclid_start_pulse_q    <= 1'b0;
            // EXP-07: Reset BRAM registers
            bram_ctrl_q             <= '0;
            bram_ctrl_start_pulse_q <= 1'b0;
            bram_manual_addr_q      <= '0;
            bram_manual_wdata_q     <= '0;
            bram_manual_we_pulse_q  <= 1'b0;
            // EXP-08: Reset RCFC registers
            rcfc_ctrl_q             <= '0;
            rcfc_start_pulse_q      <= 1'b0;
            rcfc_slot_sel_q         <= 6'd0;
            // EXP-09: Reset Suite B registers
            suite_b_ctrl_q          <= '0;
            suite_b_start_pulse_q   <= 1'b0;
            // EXP-10: Reset Stream Pipeline registers
            stream_ctrl_q           <= '0;
            stream_start_pulse_q    <= 1'b0;
            // EXP-06: Reset I/O Trigger registers
            io_trig_ctrl_q          <= '0;
            io_trig_start_pulse_q   <= 1'b0;
            io_trig_clear_pulse_q   <= 1'b0;
            ar_busy_q               <= 1'b0;
            ar_latched_addr_q       <= '0;
        end else begin
            // Free-running 64-bit cycle counter (100 MHz = 10.0 ns tick)
            hw_cycle_cnt_q <= hw_cycle_cnt_q + 64'd1;

            // Single cycle pulses
            event_valid_q           <= 1'b0;
            euclid_start_pulse_q    <= 1'b0;
            bram_ctrl_start_pulse_q <= 1'b0;
            bram_manual_we_pulse_q  <= 1'b0;
            rcfc_start_pulse_q      <= 1'b0;
            suite_b_start_pulse_q   <= 1'b0;
            stream_start_pulse_q    <= 1'b0;
            io_trig_start_pulse_q   <= 1'b0;
            io_trig_clear_pulse_q   <= 1'b0;

            // EXP-04: Transaction duration timer
            if (txn_measuring_q) begin
                txn_timer_q <= txn_timer_q + 32'd1;
            end

            // AXI write response clear
            if (s_axi_bvalid && s_axi_bready) begin
                s_axi_bvalid <= 1'b0;
            end

            // AXI read response clear
            if (s_axi_rvalid && s_axi_rready) begin
                s_axi_rvalid <= 1'b0;
            end

            // AXI read pipelining
            if (s_axi_arvalid && s_axi_arready) begin
                ar_latched_addr_q <= s_axi_araddr;
                ar_busy_q         <= 1'b1;
            end else if (ar_busy_q) begin
                ar_busy_q    <= 1'b0;
                s_axi_rvalid <= 1'b1;
                s_axi_rresp  <= read_response;
                s_axi_rdata  <= read_value;
            end

            // AXI AW / W channel latching
            if (aw_fire) begin
                awaddr_q     <= s_axi_awaddr;
                aw_pending_q <= 1'b1;
            end

            if (w_fire) begin
                wdata_q     <= s_axi_wdata;
                wstrb_q     <= s_axi_wstrb;
                w_pending_q <= 1'b1;
            end

            if (write_fire) begin
                aw_pending_q <= 1'b0;
                w_pending_q  <= 1'b0;
                s_axi_bvalid <= 1'b1;
                s_axi_bresp  <= AXI_RESP_OKAY;

                if (write_address[1:0] != 2'b00) begin
                    s_axi_bresp <= AXI_RESP_DECERR;
                end else if (write_address[12:10] == 3'b100) begin
                    // EXP-07: BRAM Concept Direct Write via Port A (0x1000..0x13FF)
                    // Handled combinationally by bram_write_active
                end else if (write_address[12:8] == 5'b00000) begin
                    // Control and Status Registers (0x00..0xFF)
                    if (busy_q && write_address[7:0] < 8'h10) begin
                        s_axi_bresp <= AXI_RESP_SLVERR;
                    end else begin
                        case (write_address[7:0])
                            8'h00: candidate_value_q <= merge_write_bytes(
                                candidate_value_q, write_data, write_strobe
                            );
                            8'h04: begin
                                if (write_strobe[0]) begin
                                    conditions_q <= write_data[6:0];
                                end
                            end
                            8'h08: begin
                                if (write_strobe[0] && write_data[31:1] == 31'b0) begin
                                    if (write_data[0]) begin
                                        event_valid_q   <= 1'b1;
                                        busy_q          <= 1'b1;
                                        status_q        <= 8'b0;
                                        txn_timer_q     <= 32'd1;
                                        txn_measuring_q <= 1'b1;
                                    end
                                end else begin
                                    s_axi_bresp <= AXI_RESP_SLVERR;
                                end
                            end
                            8'h18: lower_bound_q <= merge_write_bytes(
                                lower_bound_q, write_data, write_strobe
                            );
                            8'h1C: upper_bound_q <= merge_write_bytes(
                                upper_bound_q, write_data, write_strobe
                            );
                            8'h20: begin
                                if (write_strobe[0]) begin
                                    rule_cfg_q <= write_data[7:0];
                                end
                            end
                            // EXP-05: Euclid register writes
                            8'h38: euclid_a_init_q <= merge_write_bytes(
                                euclid_a_init_q, write_data, write_strobe
                            );
                            8'h3C: euclid_b_init_q <= merge_write_bytes(
                                euclid_b_init_q, write_data, write_strobe
                            );
                            8'h40: begin
                                if (write_strobe[0] && write_data[0]) begin
                                    if (euclid_busy) begin
                                        s_axi_bresp <= AXI_RESP_SLVERR;
                                    end else begin
                                        euclid_start_pulse_q <= 1'b1;
                                    end
                                end
                            end
                            // EXP-07: BRAM control writes
                            8'h50: begin
                                bram_ctrl_q <= merge_write_bytes(
                                    bram_ctrl_q, write_data, write_strobe
                                );
                                if (write_strobe[0] && write_data[0]) begin
                                    if (bram_core_busy) begin
                                        s_axi_bresp <= AXI_RESP_SLVERR;
                                    end else begin
                                        bram_ctrl_start_pulse_q <= 1'b1;
                                    end
                                end
                            end
                            8'h5C: begin
                                if (write_strobe[0]) begin
                                    bram_manual_addr_q <= write_data[7:0];
                                end
                            end
                            8'h60: begin
                                bram_manual_wdata_q    <= write_data;
                                bram_manual_we_pulse_q <= 1'b1;
                            end
                            // EXP-08: RCFC control & slot select writes
                            8'h64: begin
                                rcfc_ctrl_q <= merge_write_bytes(
                                    rcfc_ctrl_q, write_data, write_strobe
                                );
                                if (write_strobe[0] && write_data[3]) begin
                                    if (rcfc_busy) begin
                                        s_axi_bresp <= AXI_RESP_SLVERR;
                                    end else begin
                                        rcfc_start_pulse_q <= 1'b1;
                                    end
                                end
                            end
                            8'h70: begin
                                if (write_strobe[0]) begin
                                    rcfc_slot_sel_q <= write_data[5:0];
                                end
                            end
                            // EXP-09: Suite B control writes
                            8'h80: begin
                                suite_b_ctrl_q <= merge_write_bytes(
                                    suite_b_ctrl_q, write_data, write_strobe
                                );
                                if (write_strobe[0] && write_data[3]) begin
                                    if (suite_b_busy) begin
                                        s_axi_bresp <= AXI_RESP_SLVERR;
                                    end else begin
                                        suite_b_start_pulse_q <= 1'b1;
                                    end
                                end
                            end
                            // EXP-10: Stream Pipeline control writes
                            8'h94: begin
                                stream_ctrl_q <= merge_write_bytes(
                                    stream_ctrl_q, write_data, write_strobe
                                );
                                if (write_strobe[0] && write_data[0]) begin
                                    if (stream_busy) begin
                                        s_axi_bresp <= AXI_RESP_SLVERR;
                                    end else begin
                                        stream_start_pulse_q <= 1'b1;
                                    end
                                end
                            end
                            // EXP-06: I/O Trigger control writes
                            8'hAC: begin
                                io_trig_ctrl_q <= merge_write_bytes(
                                    io_trig_ctrl_q, write_data, write_strobe
                                );
                                if (write_strobe[0] && write_data[0]) begin
                                    if (io_trig_busy) begin
                                        s_axi_bresp <= AXI_RESP_SLVERR;
                                    end else begin
                                        io_trig_start_pulse_q <= 1'b1;
                                    end
                                end
                                if (write_strobe[0] && write_data[1]) begin
                                    io_trig_clear_pulse_q <= 1'b1;
                                end
                            end
                            default: s_axi_bresp <= AXI_RESP_DECERR;
                        endcase
                    end
                end else begin
                    s_axi_bresp <= AXI_RESP_DECERR;
                end
            end

            if (committed || rejected) begin
                status_q <= {
                    unknown_hazard,
                    hazard_observed,
                    changed,
                    rejected_invariant,
                    rejected_input,
                    rejected,
                    committed,
                    1'b1
                };
                busy_q            <= 1'b0;
                last_txn_cycles_q <= txn_timer_q;
                txn_measuring_q   <= 1'b0;
            end
        end
    end
endmodule
