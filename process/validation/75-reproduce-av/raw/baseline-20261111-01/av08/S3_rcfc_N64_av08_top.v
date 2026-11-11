`timescale 1ns/1ps
module av08_top (input wire clk, input wire rst_btn, input wire din, output reg dout);
    reg [1:0] rsync;
    always @(posedge clk) rsync <= {rsync[0], ~rst_btn};
    wire rst_n = rsync[1];
    reg [17:0] sr;
    always @(posedge clk) sr <= {sr[16:0], din};
    wire [150:0] dut_o;
    km_rcfc_engine #(.NUM_SLOTS(64)) dut (
        .clk(clk), .rst_n(rst_n), .start_i(sr[0]), .cmd_i(sr[3:1]),
        .delay_param_i(sr[11:4]), .slot_sel_i(sr[17:12]),
        .busy_o(dut_o[0]), .done_o(dut_o[1]), .tc01_pass_o(dut_o[2]), .tc02_pass_o(dut_o[3]),
        .tc03_pass_o(dut_o[4]), .tc04_pass_o(dut_o[5]), .timeout_deadlock_error_o(dut_o[6]),
        .event_drop_error_o(dut_o[7]), .current_tc_o(dut_o[11:8]),
        .events_processed_o(dut_o[27:12]), .cycle_count_o(dut_o[59:28]),
        .events_enqueued_o(dut_o[75:60]), .events_dropped_o(dut_o[91:76]),
        .result_o(dut_o[123:92]), .slot_state_o(dut_o[126:124]),
        .slot_wait_cycles_o(dut_o[134:127]), .slot_payload_lo_o(dut_o[150:135]));
    wire [155:0] xp0 = {5'b0, dut_o};
    reg  [25:0] xr0;
    genvar xg0;
    for (xg0 = 0; xg0 < 26; xg0 = xg0 + 1) begin : gx0
        always @(posedge clk) xr0[xg0] <= ^xp0[xg0*6 +: 6];
    end
    wire [29:0] xp1 = {4'b0, xr0};
    reg  [4:0] xr1;
    genvar xg1;
    for (xg1 = 0; xg1 < 5; xg1 = xg1 + 1) begin : gx1
        always @(posedge clk) xr1[xg1] <= ^xp1[xg1*6 +: 6];
    end
    wire [5:0] xp2 = {1'b0, xr1};
    reg  [0:0] xr2;
    genvar xg2;
    for (xg2 = 0; xg2 < 1; xg2 = xg2 + 1) begin : gx2
        always @(posedge clk) xr2[xg2] <= ^xp2[xg2*6 +: 6];
    end
    always @(posedge clk) dout <= xr2;
endmodule
