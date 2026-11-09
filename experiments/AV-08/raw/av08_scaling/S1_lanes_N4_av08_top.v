`timescale 1ns/1ps
module av08_top (input wire clk, input wire rst_btn, input wire din, output reg dout);
    reg [1:0] rsync;
    always @(posedge clk) rsync <= {rsync[0], ~rst_btn};
    wire rst_n = rsync[1];
    reg [109:0] sr;
    always @(posedge clk) sr <= {sr[108:0], din};
    wire [297:0] dut_o;
    reg [109:0] w0;
    always @(posedge clk) w0 <= sr ^ {sr[0], sr[109:1]};
    wire [31:0] st0; wire inv0, bd0; wire [7:0] pv0;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe0 (
        .candidate_value_i(w0[31:0]), .candidate_known_i(w0[104]),
        .current_state_i(st0), .lower_bound_i(w0[63:32]), .upper_bound_i(w0[95:64]),
        .rule_cfg_i(w0[103:96]), .predicate_vector_o(pv0),
        .hw_invariant_ok_o(inv0), .big_dot_flag_o(bd0));
    kpol_txn_gate #(.DATA_WIDTH(32)) g0 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w0[105]),
        .candidate_known_i(w0[104]), .candidate_value_i(w0[31:0]),
        .assumption_known_i(w0[106]), .assumption_true_i(w0[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv0),
        .hazard_known_i(w0[108]), .hazard_true_i(w0[109]),
        .state_o(st0), .committed_o(dut_o[32]),
        .rejected_o(dut_o[33]), .rejected_input_o(dut_o[34]),
        .rejected_invariant_o(dut_o[35]), .changed_o(dut_o[36]),
        .hazard_observed_o(dut_o[37]), .unknown_hazard_o(dut_o[38]));
    assign dut_o[0 +: 32] = st0;
    assign dut_o[39 +: 8] = pv0;
    reg [109:0] w1;
    always @(posedge clk) w1 <= {w0[6:0], w0[109:7]};
    wire [31:0] st1; wire inv1, bd1; wire [7:0] pv1;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe1 (
        .candidate_value_i(w1[31:0]), .candidate_known_i(w1[104]),
        .current_state_i(st1), .lower_bound_i(w1[63:32]), .upper_bound_i(w1[95:64]),
        .rule_cfg_i(w1[103:96]), .predicate_vector_o(pv1),
        .hw_invariant_ok_o(inv1), .big_dot_flag_o(bd1));
    kpol_txn_gate #(.DATA_WIDTH(32)) g1 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w1[105]),
        .candidate_known_i(w1[104]), .candidate_value_i(w1[31:0]),
        .assumption_known_i(w1[106]), .assumption_true_i(w1[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv1),
        .hazard_known_i(w1[108]), .hazard_true_i(w1[109]),
        .state_o(st1), .committed_o(dut_o[79]),
        .rejected_o(dut_o[80]), .rejected_input_o(dut_o[81]),
        .rejected_invariant_o(dut_o[82]), .changed_o(dut_o[83]),
        .hazard_observed_o(dut_o[84]), .unknown_hazard_o(dut_o[85]));
    assign dut_o[47 +: 32] = st1;
    assign dut_o[86 +: 8] = pv1;
    reg [109:0] w2;
    always @(posedge clk) w2 <= {w1[6:0], w1[109:7]};
    wire [31:0] st2; wire inv2, bd2; wire [7:0] pv2;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe2 (
        .candidate_value_i(w2[31:0]), .candidate_known_i(w2[104]),
        .current_state_i(st2), .lower_bound_i(w2[63:32]), .upper_bound_i(w2[95:64]),
        .rule_cfg_i(w2[103:96]), .predicate_vector_o(pv2),
        .hw_invariant_ok_o(inv2), .big_dot_flag_o(bd2));
    kpol_txn_gate #(.DATA_WIDTH(32)) g2 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w2[105]),
        .candidate_known_i(w2[104]), .candidate_value_i(w2[31:0]),
        .assumption_known_i(w2[106]), .assumption_true_i(w2[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv2),
        .hazard_known_i(w2[108]), .hazard_true_i(w2[109]),
        .state_o(st2), .committed_o(dut_o[126]),
        .rejected_o(dut_o[127]), .rejected_input_o(dut_o[128]),
        .rejected_invariant_o(dut_o[129]), .changed_o(dut_o[130]),
        .hazard_observed_o(dut_o[131]), .unknown_hazard_o(dut_o[132]));
    assign dut_o[94 +: 32] = st2;
    assign dut_o[133 +: 8] = pv2;
    reg [109:0] w3;
    always @(posedge clk) w3 <= {w2[6:0], w2[109:7]};
    wire [31:0] st3; wire inv3, bd3; wire [7:0] pv3;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe3 (
        .candidate_value_i(w3[31:0]), .candidate_known_i(w3[104]),
        .current_state_i(st3), .lower_bound_i(w3[63:32]), .upper_bound_i(w3[95:64]),
        .rule_cfg_i(w3[103:96]), .predicate_vector_o(pv3),
        .hw_invariant_ok_o(inv3), .big_dot_flag_o(bd3));
    kpol_txn_gate #(.DATA_WIDTH(32)) g3 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w3[105]),
        .candidate_known_i(w3[104]), .candidate_value_i(w3[31:0]),
        .assumption_known_i(w3[106]), .assumption_true_i(w3[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv3),
        .hazard_known_i(w3[108]), .hazard_true_i(w3[109]),
        .state_o(st3), .committed_o(dut_o[173]),
        .rejected_o(dut_o[174]), .rejected_input_o(dut_o[175]),
        .rejected_invariant_o(dut_o[176]), .changed_o(dut_o[177]),
        .hazard_observed_o(dut_o[178]), .unknown_hazard_o(dut_o[179]));
    assign dut_o[141 +: 32] = st3;
    assign dut_o[180 +: 8] = pv3;
    assign dut_o[188 +: 110] = w3;
    wire [299:0] xp0 = {2'b0, dut_o};
    reg  [49:0] xr0;
    genvar xg0;
    for (xg0 = 0; xg0 < 50; xg0 = xg0 + 1) begin : gx0
        always @(posedge clk) xr0[xg0] <= ^xp0[xg0*6 +: 6];
    end
    wire [53:0] xp1 = {4'b0, xr0};
    reg  [8:0] xr1;
    genvar xg1;
    for (xg1 = 0; xg1 < 9; xg1 = xg1 + 1) begin : gx1
        always @(posedge clk) xr1[xg1] <= ^xp1[xg1*6 +: 6];
    end
    wire [11:0] xp2 = {3'b0, xr1};
    reg  [1:0] xr2;
    genvar xg2;
    for (xg2 = 0; xg2 < 2; xg2 = xg2 + 1) begin : gx2
        always @(posedge clk) xr2[xg2] <= ^xp2[xg2*6 +: 6];
    end
    wire [5:0] xp3 = {4'b0, xr2};
    reg  [0:0] xr3;
    genvar xg3;
    for (xg3 = 0; xg3 < 1; xg3 = xg3 + 1) begin : gx3
        always @(posedge clk) xr3[xg3] <= ^xp3[xg3*6 +: 6];
    end
    always @(posedge clk) dout <= xr3;
endmodule
