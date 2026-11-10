`timescale 1ns/1ps
module av08_top (input wire clk, input wire rst_btn, input wire din, output reg dout);
    reg [1:0] rsync;
    always @(posedge clk) rsync <= {rsync[0], ~rst_btn};
    wire rst_n = rsync[1];
    reg [109:0] sr;
    always @(posedge clk) sr <= {sr[108:0], din};
    wire [3117:0] dut_o;
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
    reg [109:0] w4;
    always @(posedge clk) w4 <= {w3[6:0], w3[109:7]};
    wire [31:0] st4; wire inv4, bd4; wire [7:0] pv4;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe4 (
        .candidate_value_i(w4[31:0]), .candidate_known_i(w4[104]),
        .current_state_i(st4), .lower_bound_i(w4[63:32]), .upper_bound_i(w4[95:64]),
        .rule_cfg_i(w4[103:96]), .predicate_vector_o(pv4),
        .hw_invariant_ok_o(inv4), .big_dot_flag_o(bd4));
    kpol_txn_gate #(.DATA_WIDTH(32)) g4 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w4[105]),
        .candidate_known_i(w4[104]), .candidate_value_i(w4[31:0]),
        .assumption_known_i(w4[106]), .assumption_true_i(w4[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv4),
        .hazard_known_i(w4[108]), .hazard_true_i(w4[109]),
        .state_o(st4), .committed_o(dut_o[220]),
        .rejected_o(dut_o[221]), .rejected_input_o(dut_o[222]),
        .rejected_invariant_o(dut_o[223]), .changed_o(dut_o[224]),
        .hazard_observed_o(dut_o[225]), .unknown_hazard_o(dut_o[226]));
    assign dut_o[188 +: 32] = st4;
    assign dut_o[227 +: 8] = pv4;
    reg [109:0] w5;
    always @(posedge clk) w5 <= {w4[6:0], w4[109:7]};
    wire [31:0] st5; wire inv5, bd5; wire [7:0] pv5;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe5 (
        .candidate_value_i(w5[31:0]), .candidate_known_i(w5[104]),
        .current_state_i(st5), .lower_bound_i(w5[63:32]), .upper_bound_i(w5[95:64]),
        .rule_cfg_i(w5[103:96]), .predicate_vector_o(pv5),
        .hw_invariant_ok_o(inv5), .big_dot_flag_o(bd5));
    kpol_txn_gate #(.DATA_WIDTH(32)) g5 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w5[105]),
        .candidate_known_i(w5[104]), .candidate_value_i(w5[31:0]),
        .assumption_known_i(w5[106]), .assumption_true_i(w5[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv5),
        .hazard_known_i(w5[108]), .hazard_true_i(w5[109]),
        .state_o(st5), .committed_o(dut_o[267]),
        .rejected_o(dut_o[268]), .rejected_input_o(dut_o[269]),
        .rejected_invariant_o(dut_o[270]), .changed_o(dut_o[271]),
        .hazard_observed_o(dut_o[272]), .unknown_hazard_o(dut_o[273]));
    assign dut_o[235 +: 32] = st5;
    assign dut_o[274 +: 8] = pv5;
    reg [109:0] w6;
    always @(posedge clk) w6 <= {w5[6:0], w5[109:7]};
    wire [31:0] st6; wire inv6, bd6; wire [7:0] pv6;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe6 (
        .candidate_value_i(w6[31:0]), .candidate_known_i(w6[104]),
        .current_state_i(st6), .lower_bound_i(w6[63:32]), .upper_bound_i(w6[95:64]),
        .rule_cfg_i(w6[103:96]), .predicate_vector_o(pv6),
        .hw_invariant_ok_o(inv6), .big_dot_flag_o(bd6));
    kpol_txn_gate #(.DATA_WIDTH(32)) g6 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w6[105]),
        .candidate_known_i(w6[104]), .candidate_value_i(w6[31:0]),
        .assumption_known_i(w6[106]), .assumption_true_i(w6[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv6),
        .hazard_known_i(w6[108]), .hazard_true_i(w6[109]),
        .state_o(st6), .committed_o(dut_o[314]),
        .rejected_o(dut_o[315]), .rejected_input_o(dut_o[316]),
        .rejected_invariant_o(dut_o[317]), .changed_o(dut_o[318]),
        .hazard_observed_o(dut_o[319]), .unknown_hazard_o(dut_o[320]));
    assign dut_o[282 +: 32] = st6;
    assign dut_o[321 +: 8] = pv6;
    reg [109:0] w7;
    always @(posedge clk) w7 <= {w6[6:0], w6[109:7]};
    wire [31:0] st7; wire inv7, bd7; wire [7:0] pv7;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe7 (
        .candidate_value_i(w7[31:0]), .candidate_known_i(w7[104]),
        .current_state_i(st7), .lower_bound_i(w7[63:32]), .upper_bound_i(w7[95:64]),
        .rule_cfg_i(w7[103:96]), .predicate_vector_o(pv7),
        .hw_invariant_ok_o(inv7), .big_dot_flag_o(bd7));
    kpol_txn_gate #(.DATA_WIDTH(32)) g7 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w7[105]),
        .candidate_known_i(w7[104]), .candidate_value_i(w7[31:0]),
        .assumption_known_i(w7[106]), .assumption_true_i(w7[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv7),
        .hazard_known_i(w7[108]), .hazard_true_i(w7[109]),
        .state_o(st7), .committed_o(dut_o[361]),
        .rejected_o(dut_o[362]), .rejected_input_o(dut_o[363]),
        .rejected_invariant_o(dut_o[364]), .changed_o(dut_o[365]),
        .hazard_observed_o(dut_o[366]), .unknown_hazard_o(dut_o[367]));
    assign dut_o[329 +: 32] = st7;
    assign dut_o[368 +: 8] = pv7;
    reg [109:0] w8;
    always @(posedge clk) w8 <= {w7[6:0], w7[109:7]};
    wire [31:0] st8; wire inv8, bd8; wire [7:0] pv8;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe8 (
        .candidate_value_i(w8[31:0]), .candidate_known_i(w8[104]),
        .current_state_i(st8), .lower_bound_i(w8[63:32]), .upper_bound_i(w8[95:64]),
        .rule_cfg_i(w8[103:96]), .predicate_vector_o(pv8),
        .hw_invariant_ok_o(inv8), .big_dot_flag_o(bd8));
    kpol_txn_gate #(.DATA_WIDTH(32)) g8 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w8[105]),
        .candidate_known_i(w8[104]), .candidate_value_i(w8[31:0]),
        .assumption_known_i(w8[106]), .assumption_true_i(w8[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv8),
        .hazard_known_i(w8[108]), .hazard_true_i(w8[109]),
        .state_o(st8), .committed_o(dut_o[408]),
        .rejected_o(dut_o[409]), .rejected_input_o(dut_o[410]),
        .rejected_invariant_o(dut_o[411]), .changed_o(dut_o[412]),
        .hazard_observed_o(dut_o[413]), .unknown_hazard_o(dut_o[414]));
    assign dut_o[376 +: 32] = st8;
    assign dut_o[415 +: 8] = pv8;
    reg [109:0] w9;
    always @(posedge clk) w9 <= {w8[6:0], w8[109:7]};
    wire [31:0] st9; wire inv9, bd9; wire [7:0] pv9;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe9 (
        .candidate_value_i(w9[31:0]), .candidate_known_i(w9[104]),
        .current_state_i(st9), .lower_bound_i(w9[63:32]), .upper_bound_i(w9[95:64]),
        .rule_cfg_i(w9[103:96]), .predicate_vector_o(pv9),
        .hw_invariant_ok_o(inv9), .big_dot_flag_o(bd9));
    kpol_txn_gate #(.DATA_WIDTH(32)) g9 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w9[105]),
        .candidate_known_i(w9[104]), .candidate_value_i(w9[31:0]),
        .assumption_known_i(w9[106]), .assumption_true_i(w9[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv9),
        .hazard_known_i(w9[108]), .hazard_true_i(w9[109]),
        .state_o(st9), .committed_o(dut_o[455]),
        .rejected_o(dut_o[456]), .rejected_input_o(dut_o[457]),
        .rejected_invariant_o(dut_o[458]), .changed_o(dut_o[459]),
        .hazard_observed_o(dut_o[460]), .unknown_hazard_o(dut_o[461]));
    assign dut_o[423 +: 32] = st9;
    assign dut_o[462 +: 8] = pv9;
    reg [109:0] w10;
    always @(posedge clk) w10 <= {w9[6:0], w9[109:7]};
    wire [31:0] st10; wire inv10, bd10; wire [7:0] pv10;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe10 (
        .candidate_value_i(w10[31:0]), .candidate_known_i(w10[104]),
        .current_state_i(st10), .lower_bound_i(w10[63:32]), .upper_bound_i(w10[95:64]),
        .rule_cfg_i(w10[103:96]), .predicate_vector_o(pv10),
        .hw_invariant_ok_o(inv10), .big_dot_flag_o(bd10));
    kpol_txn_gate #(.DATA_WIDTH(32)) g10 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w10[105]),
        .candidate_known_i(w10[104]), .candidate_value_i(w10[31:0]),
        .assumption_known_i(w10[106]), .assumption_true_i(w10[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv10),
        .hazard_known_i(w10[108]), .hazard_true_i(w10[109]),
        .state_o(st10), .committed_o(dut_o[502]),
        .rejected_o(dut_o[503]), .rejected_input_o(dut_o[504]),
        .rejected_invariant_o(dut_o[505]), .changed_o(dut_o[506]),
        .hazard_observed_o(dut_o[507]), .unknown_hazard_o(dut_o[508]));
    assign dut_o[470 +: 32] = st10;
    assign dut_o[509 +: 8] = pv10;
    reg [109:0] w11;
    always @(posedge clk) w11 <= {w10[6:0], w10[109:7]};
    wire [31:0] st11; wire inv11, bd11; wire [7:0] pv11;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe11 (
        .candidate_value_i(w11[31:0]), .candidate_known_i(w11[104]),
        .current_state_i(st11), .lower_bound_i(w11[63:32]), .upper_bound_i(w11[95:64]),
        .rule_cfg_i(w11[103:96]), .predicate_vector_o(pv11),
        .hw_invariant_ok_o(inv11), .big_dot_flag_o(bd11));
    kpol_txn_gate #(.DATA_WIDTH(32)) g11 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w11[105]),
        .candidate_known_i(w11[104]), .candidate_value_i(w11[31:0]),
        .assumption_known_i(w11[106]), .assumption_true_i(w11[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv11),
        .hazard_known_i(w11[108]), .hazard_true_i(w11[109]),
        .state_o(st11), .committed_o(dut_o[549]),
        .rejected_o(dut_o[550]), .rejected_input_o(dut_o[551]),
        .rejected_invariant_o(dut_o[552]), .changed_o(dut_o[553]),
        .hazard_observed_o(dut_o[554]), .unknown_hazard_o(dut_o[555]));
    assign dut_o[517 +: 32] = st11;
    assign dut_o[556 +: 8] = pv11;
    reg [109:0] w12;
    always @(posedge clk) w12 <= {w11[6:0], w11[109:7]};
    wire [31:0] st12; wire inv12, bd12; wire [7:0] pv12;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe12 (
        .candidate_value_i(w12[31:0]), .candidate_known_i(w12[104]),
        .current_state_i(st12), .lower_bound_i(w12[63:32]), .upper_bound_i(w12[95:64]),
        .rule_cfg_i(w12[103:96]), .predicate_vector_o(pv12),
        .hw_invariant_ok_o(inv12), .big_dot_flag_o(bd12));
    kpol_txn_gate #(.DATA_WIDTH(32)) g12 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w12[105]),
        .candidate_known_i(w12[104]), .candidate_value_i(w12[31:0]),
        .assumption_known_i(w12[106]), .assumption_true_i(w12[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv12),
        .hazard_known_i(w12[108]), .hazard_true_i(w12[109]),
        .state_o(st12), .committed_o(dut_o[596]),
        .rejected_o(dut_o[597]), .rejected_input_o(dut_o[598]),
        .rejected_invariant_o(dut_o[599]), .changed_o(dut_o[600]),
        .hazard_observed_o(dut_o[601]), .unknown_hazard_o(dut_o[602]));
    assign dut_o[564 +: 32] = st12;
    assign dut_o[603 +: 8] = pv12;
    reg [109:0] w13;
    always @(posedge clk) w13 <= {w12[6:0], w12[109:7]};
    wire [31:0] st13; wire inv13, bd13; wire [7:0] pv13;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe13 (
        .candidate_value_i(w13[31:0]), .candidate_known_i(w13[104]),
        .current_state_i(st13), .lower_bound_i(w13[63:32]), .upper_bound_i(w13[95:64]),
        .rule_cfg_i(w13[103:96]), .predicate_vector_o(pv13),
        .hw_invariant_ok_o(inv13), .big_dot_flag_o(bd13));
    kpol_txn_gate #(.DATA_WIDTH(32)) g13 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w13[105]),
        .candidate_known_i(w13[104]), .candidate_value_i(w13[31:0]),
        .assumption_known_i(w13[106]), .assumption_true_i(w13[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv13),
        .hazard_known_i(w13[108]), .hazard_true_i(w13[109]),
        .state_o(st13), .committed_o(dut_o[643]),
        .rejected_o(dut_o[644]), .rejected_input_o(dut_o[645]),
        .rejected_invariant_o(dut_o[646]), .changed_o(dut_o[647]),
        .hazard_observed_o(dut_o[648]), .unknown_hazard_o(dut_o[649]));
    assign dut_o[611 +: 32] = st13;
    assign dut_o[650 +: 8] = pv13;
    reg [109:0] w14;
    always @(posedge clk) w14 <= {w13[6:0], w13[109:7]};
    wire [31:0] st14; wire inv14, bd14; wire [7:0] pv14;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe14 (
        .candidate_value_i(w14[31:0]), .candidate_known_i(w14[104]),
        .current_state_i(st14), .lower_bound_i(w14[63:32]), .upper_bound_i(w14[95:64]),
        .rule_cfg_i(w14[103:96]), .predicate_vector_o(pv14),
        .hw_invariant_ok_o(inv14), .big_dot_flag_o(bd14));
    kpol_txn_gate #(.DATA_WIDTH(32)) g14 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w14[105]),
        .candidate_known_i(w14[104]), .candidate_value_i(w14[31:0]),
        .assumption_known_i(w14[106]), .assumption_true_i(w14[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv14),
        .hazard_known_i(w14[108]), .hazard_true_i(w14[109]),
        .state_o(st14), .committed_o(dut_o[690]),
        .rejected_o(dut_o[691]), .rejected_input_o(dut_o[692]),
        .rejected_invariant_o(dut_o[693]), .changed_o(dut_o[694]),
        .hazard_observed_o(dut_o[695]), .unknown_hazard_o(dut_o[696]));
    assign dut_o[658 +: 32] = st14;
    assign dut_o[697 +: 8] = pv14;
    reg [109:0] w15;
    always @(posedge clk) w15 <= {w14[6:0], w14[109:7]};
    wire [31:0] st15; wire inv15, bd15; wire [7:0] pv15;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe15 (
        .candidate_value_i(w15[31:0]), .candidate_known_i(w15[104]),
        .current_state_i(st15), .lower_bound_i(w15[63:32]), .upper_bound_i(w15[95:64]),
        .rule_cfg_i(w15[103:96]), .predicate_vector_o(pv15),
        .hw_invariant_ok_o(inv15), .big_dot_flag_o(bd15));
    kpol_txn_gate #(.DATA_WIDTH(32)) g15 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w15[105]),
        .candidate_known_i(w15[104]), .candidate_value_i(w15[31:0]),
        .assumption_known_i(w15[106]), .assumption_true_i(w15[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv15),
        .hazard_known_i(w15[108]), .hazard_true_i(w15[109]),
        .state_o(st15), .committed_o(dut_o[737]),
        .rejected_o(dut_o[738]), .rejected_input_o(dut_o[739]),
        .rejected_invariant_o(dut_o[740]), .changed_o(dut_o[741]),
        .hazard_observed_o(dut_o[742]), .unknown_hazard_o(dut_o[743]));
    assign dut_o[705 +: 32] = st15;
    assign dut_o[744 +: 8] = pv15;
    reg [109:0] w16;
    always @(posedge clk) w16 <= {w15[6:0], w15[109:7]};
    wire [31:0] st16; wire inv16, bd16; wire [7:0] pv16;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe16 (
        .candidate_value_i(w16[31:0]), .candidate_known_i(w16[104]),
        .current_state_i(st16), .lower_bound_i(w16[63:32]), .upper_bound_i(w16[95:64]),
        .rule_cfg_i(w16[103:96]), .predicate_vector_o(pv16),
        .hw_invariant_ok_o(inv16), .big_dot_flag_o(bd16));
    kpol_txn_gate #(.DATA_WIDTH(32)) g16 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w16[105]),
        .candidate_known_i(w16[104]), .candidate_value_i(w16[31:0]),
        .assumption_known_i(w16[106]), .assumption_true_i(w16[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv16),
        .hazard_known_i(w16[108]), .hazard_true_i(w16[109]),
        .state_o(st16), .committed_o(dut_o[784]),
        .rejected_o(dut_o[785]), .rejected_input_o(dut_o[786]),
        .rejected_invariant_o(dut_o[787]), .changed_o(dut_o[788]),
        .hazard_observed_o(dut_o[789]), .unknown_hazard_o(dut_o[790]));
    assign dut_o[752 +: 32] = st16;
    assign dut_o[791 +: 8] = pv16;
    reg [109:0] w17;
    always @(posedge clk) w17 <= {w16[6:0], w16[109:7]};
    wire [31:0] st17; wire inv17, bd17; wire [7:0] pv17;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe17 (
        .candidate_value_i(w17[31:0]), .candidate_known_i(w17[104]),
        .current_state_i(st17), .lower_bound_i(w17[63:32]), .upper_bound_i(w17[95:64]),
        .rule_cfg_i(w17[103:96]), .predicate_vector_o(pv17),
        .hw_invariant_ok_o(inv17), .big_dot_flag_o(bd17));
    kpol_txn_gate #(.DATA_WIDTH(32)) g17 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w17[105]),
        .candidate_known_i(w17[104]), .candidate_value_i(w17[31:0]),
        .assumption_known_i(w17[106]), .assumption_true_i(w17[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv17),
        .hazard_known_i(w17[108]), .hazard_true_i(w17[109]),
        .state_o(st17), .committed_o(dut_o[831]),
        .rejected_o(dut_o[832]), .rejected_input_o(dut_o[833]),
        .rejected_invariant_o(dut_o[834]), .changed_o(dut_o[835]),
        .hazard_observed_o(dut_o[836]), .unknown_hazard_o(dut_o[837]));
    assign dut_o[799 +: 32] = st17;
    assign dut_o[838 +: 8] = pv17;
    reg [109:0] w18;
    always @(posedge clk) w18 <= {w17[6:0], w17[109:7]};
    wire [31:0] st18; wire inv18, bd18; wire [7:0] pv18;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe18 (
        .candidate_value_i(w18[31:0]), .candidate_known_i(w18[104]),
        .current_state_i(st18), .lower_bound_i(w18[63:32]), .upper_bound_i(w18[95:64]),
        .rule_cfg_i(w18[103:96]), .predicate_vector_o(pv18),
        .hw_invariant_ok_o(inv18), .big_dot_flag_o(bd18));
    kpol_txn_gate #(.DATA_WIDTH(32)) g18 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w18[105]),
        .candidate_known_i(w18[104]), .candidate_value_i(w18[31:0]),
        .assumption_known_i(w18[106]), .assumption_true_i(w18[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv18),
        .hazard_known_i(w18[108]), .hazard_true_i(w18[109]),
        .state_o(st18), .committed_o(dut_o[878]),
        .rejected_o(dut_o[879]), .rejected_input_o(dut_o[880]),
        .rejected_invariant_o(dut_o[881]), .changed_o(dut_o[882]),
        .hazard_observed_o(dut_o[883]), .unknown_hazard_o(dut_o[884]));
    assign dut_o[846 +: 32] = st18;
    assign dut_o[885 +: 8] = pv18;
    reg [109:0] w19;
    always @(posedge clk) w19 <= {w18[6:0], w18[109:7]};
    wire [31:0] st19; wire inv19, bd19; wire [7:0] pv19;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe19 (
        .candidate_value_i(w19[31:0]), .candidate_known_i(w19[104]),
        .current_state_i(st19), .lower_bound_i(w19[63:32]), .upper_bound_i(w19[95:64]),
        .rule_cfg_i(w19[103:96]), .predicate_vector_o(pv19),
        .hw_invariant_ok_o(inv19), .big_dot_flag_o(bd19));
    kpol_txn_gate #(.DATA_WIDTH(32)) g19 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w19[105]),
        .candidate_known_i(w19[104]), .candidate_value_i(w19[31:0]),
        .assumption_known_i(w19[106]), .assumption_true_i(w19[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv19),
        .hazard_known_i(w19[108]), .hazard_true_i(w19[109]),
        .state_o(st19), .committed_o(dut_o[925]),
        .rejected_o(dut_o[926]), .rejected_input_o(dut_o[927]),
        .rejected_invariant_o(dut_o[928]), .changed_o(dut_o[929]),
        .hazard_observed_o(dut_o[930]), .unknown_hazard_o(dut_o[931]));
    assign dut_o[893 +: 32] = st19;
    assign dut_o[932 +: 8] = pv19;
    reg [109:0] w20;
    always @(posedge clk) w20 <= {w19[6:0], w19[109:7]};
    wire [31:0] st20; wire inv20, bd20; wire [7:0] pv20;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe20 (
        .candidate_value_i(w20[31:0]), .candidate_known_i(w20[104]),
        .current_state_i(st20), .lower_bound_i(w20[63:32]), .upper_bound_i(w20[95:64]),
        .rule_cfg_i(w20[103:96]), .predicate_vector_o(pv20),
        .hw_invariant_ok_o(inv20), .big_dot_flag_o(bd20));
    kpol_txn_gate #(.DATA_WIDTH(32)) g20 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w20[105]),
        .candidate_known_i(w20[104]), .candidate_value_i(w20[31:0]),
        .assumption_known_i(w20[106]), .assumption_true_i(w20[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv20),
        .hazard_known_i(w20[108]), .hazard_true_i(w20[109]),
        .state_o(st20), .committed_o(dut_o[972]),
        .rejected_o(dut_o[973]), .rejected_input_o(dut_o[974]),
        .rejected_invariant_o(dut_o[975]), .changed_o(dut_o[976]),
        .hazard_observed_o(dut_o[977]), .unknown_hazard_o(dut_o[978]));
    assign dut_o[940 +: 32] = st20;
    assign dut_o[979 +: 8] = pv20;
    reg [109:0] w21;
    always @(posedge clk) w21 <= {w20[6:0], w20[109:7]};
    wire [31:0] st21; wire inv21, bd21; wire [7:0] pv21;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe21 (
        .candidate_value_i(w21[31:0]), .candidate_known_i(w21[104]),
        .current_state_i(st21), .lower_bound_i(w21[63:32]), .upper_bound_i(w21[95:64]),
        .rule_cfg_i(w21[103:96]), .predicate_vector_o(pv21),
        .hw_invariant_ok_o(inv21), .big_dot_flag_o(bd21));
    kpol_txn_gate #(.DATA_WIDTH(32)) g21 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w21[105]),
        .candidate_known_i(w21[104]), .candidate_value_i(w21[31:0]),
        .assumption_known_i(w21[106]), .assumption_true_i(w21[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv21),
        .hazard_known_i(w21[108]), .hazard_true_i(w21[109]),
        .state_o(st21), .committed_o(dut_o[1019]),
        .rejected_o(dut_o[1020]), .rejected_input_o(dut_o[1021]),
        .rejected_invariant_o(dut_o[1022]), .changed_o(dut_o[1023]),
        .hazard_observed_o(dut_o[1024]), .unknown_hazard_o(dut_o[1025]));
    assign dut_o[987 +: 32] = st21;
    assign dut_o[1026 +: 8] = pv21;
    reg [109:0] w22;
    always @(posedge clk) w22 <= {w21[6:0], w21[109:7]};
    wire [31:0] st22; wire inv22, bd22; wire [7:0] pv22;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe22 (
        .candidate_value_i(w22[31:0]), .candidate_known_i(w22[104]),
        .current_state_i(st22), .lower_bound_i(w22[63:32]), .upper_bound_i(w22[95:64]),
        .rule_cfg_i(w22[103:96]), .predicate_vector_o(pv22),
        .hw_invariant_ok_o(inv22), .big_dot_flag_o(bd22));
    kpol_txn_gate #(.DATA_WIDTH(32)) g22 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w22[105]),
        .candidate_known_i(w22[104]), .candidate_value_i(w22[31:0]),
        .assumption_known_i(w22[106]), .assumption_true_i(w22[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv22),
        .hazard_known_i(w22[108]), .hazard_true_i(w22[109]),
        .state_o(st22), .committed_o(dut_o[1066]),
        .rejected_o(dut_o[1067]), .rejected_input_o(dut_o[1068]),
        .rejected_invariant_o(dut_o[1069]), .changed_o(dut_o[1070]),
        .hazard_observed_o(dut_o[1071]), .unknown_hazard_o(dut_o[1072]));
    assign dut_o[1034 +: 32] = st22;
    assign dut_o[1073 +: 8] = pv22;
    reg [109:0] w23;
    always @(posedge clk) w23 <= {w22[6:0], w22[109:7]};
    wire [31:0] st23; wire inv23, bd23; wire [7:0] pv23;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe23 (
        .candidate_value_i(w23[31:0]), .candidate_known_i(w23[104]),
        .current_state_i(st23), .lower_bound_i(w23[63:32]), .upper_bound_i(w23[95:64]),
        .rule_cfg_i(w23[103:96]), .predicate_vector_o(pv23),
        .hw_invariant_ok_o(inv23), .big_dot_flag_o(bd23));
    kpol_txn_gate #(.DATA_WIDTH(32)) g23 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w23[105]),
        .candidate_known_i(w23[104]), .candidate_value_i(w23[31:0]),
        .assumption_known_i(w23[106]), .assumption_true_i(w23[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv23),
        .hazard_known_i(w23[108]), .hazard_true_i(w23[109]),
        .state_o(st23), .committed_o(dut_o[1113]),
        .rejected_o(dut_o[1114]), .rejected_input_o(dut_o[1115]),
        .rejected_invariant_o(dut_o[1116]), .changed_o(dut_o[1117]),
        .hazard_observed_o(dut_o[1118]), .unknown_hazard_o(dut_o[1119]));
    assign dut_o[1081 +: 32] = st23;
    assign dut_o[1120 +: 8] = pv23;
    reg [109:0] w24;
    always @(posedge clk) w24 <= {w23[6:0], w23[109:7]};
    wire [31:0] st24; wire inv24, bd24; wire [7:0] pv24;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe24 (
        .candidate_value_i(w24[31:0]), .candidate_known_i(w24[104]),
        .current_state_i(st24), .lower_bound_i(w24[63:32]), .upper_bound_i(w24[95:64]),
        .rule_cfg_i(w24[103:96]), .predicate_vector_o(pv24),
        .hw_invariant_ok_o(inv24), .big_dot_flag_o(bd24));
    kpol_txn_gate #(.DATA_WIDTH(32)) g24 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w24[105]),
        .candidate_known_i(w24[104]), .candidate_value_i(w24[31:0]),
        .assumption_known_i(w24[106]), .assumption_true_i(w24[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv24),
        .hazard_known_i(w24[108]), .hazard_true_i(w24[109]),
        .state_o(st24), .committed_o(dut_o[1160]),
        .rejected_o(dut_o[1161]), .rejected_input_o(dut_o[1162]),
        .rejected_invariant_o(dut_o[1163]), .changed_o(dut_o[1164]),
        .hazard_observed_o(dut_o[1165]), .unknown_hazard_o(dut_o[1166]));
    assign dut_o[1128 +: 32] = st24;
    assign dut_o[1167 +: 8] = pv24;
    reg [109:0] w25;
    always @(posedge clk) w25 <= {w24[6:0], w24[109:7]};
    wire [31:0] st25; wire inv25, bd25; wire [7:0] pv25;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe25 (
        .candidate_value_i(w25[31:0]), .candidate_known_i(w25[104]),
        .current_state_i(st25), .lower_bound_i(w25[63:32]), .upper_bound_i(w25[95:64]),
        .rule_cfg_i(w25[103:96]), .predicate_vector_o(pv25),
        .hw_invariant_ok_o(inv25), .big_dot_flag_o(bd25));
    kpol_txn_gate #(.DATA_WIDTH(32)) g25 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w25[105]),
        .candidate_known_i(w25[104]), .candidate_value_i(w25[31:0]),
        .assumption_known_i(w25[106]), .assumption_true_i(w25[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv25),
        .hazard_known_i(w25[108]), .hazard_true_i(w25[109]),
        .state_o(st25), .committed_o(dut_o[1207]),
        .rejected_o(dut_o[1208]), .rejected_input_o(dut_o[1209]),
        .rejected_invariant_o(dut_o[1210]), .changed_o(dut_o[1211]),
        .hazard_observed_o(dut_o[1212]), .unknown_hazard_o(dut_o[1213]));
    assign dut_o[1175 +: 32] = st25;
    assign dut_o[1214 +: 8] = pv25;
    reg [109:0] w26;
    always @(posedge clk) w26 <= {w25[6:0], w25[109:7]};
    wire [31:0] st26; wire inv26, bd26; wire [7:0] pv26;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe26 (
        .candidate_value_i(w26[31:0]), .candidate_known_i(w26[104]),
        .current_state_i(st26), .lower_bound_i(w26[63:32]), .upper_bound_i(w26[95:64]),
        .rule_cfg_i(w26[103:96]), .predicate_vector_o(pv26),
        .hw_invariant_ok_o(inv26), .big_dot_flag_o(bd26));
    kpol_txn_gate #(.DATA_WIDTH(32)) g26 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w26[105]),
        .candidate_known_i(w26[104]), .candidate_value_i(w26[31:0]),
        .assumption_known_i(w26[106]), .assumption_true_i(w26[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv26),
        .hazard_known_i(w26[108]), .hazard_true_i(w26[109]),
        .state_o(st26), .committed_o(dut_o[1254]),
        .rejected_o(dut_o[1255]), .rejected_input_o(dut_o[1256]),
        .rejected_invariant_o(dut_o[1257]), .changed_o(dut_o[1258]),
        .hazard_observed_o(dut_o[1259]), .unknown_hazard_o(dut_o[1260]));
    assign dut_o[1222 +: 32] = st26;
    assign dut_o[1261 +: 8] = pv26;
    reg [109:0] w27;
    always @(posedge clk) w27 <= {w26[6:0], w26[109:7]};
    wire [31:0] st27; wire inv27, bd27; wire [7:0] pv27;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe27 (
        .candidate_value_i(w27[31:0]), .candidate_known_i(w27[104]),
        .current_state_i(st27), .lower_bound_i(w27[63:32]), .upper_bound_i(w27[95:64]),
        .rule_cfg_i(w27[103:96]), .predicate_vector_o(pv27),
        .hw_invariant_ok_o(inv27), .big_dot_flag_o(bd27));
    kpol_txn_gate #(.DATA_WIDTH(32)) g27 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w27[105]),
        .candidate_known_i(w27[104]), .candidate_value_i(w27[31:0]),
        .assumption_known_i(w27[106]), .assumption_true_i(w27[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv27),
        .hazard_known_i(w27[108]), .hazard_true_i(w27[109]),
        .state_o(st27), .committed_o(dut_o[1301]),
        .rejected_o(dut_o[1302]), .rejected_input_o(dut_o[1303]),
        .rejected_invariant_o(dut_o[1304]), .changed_o(dut_o[1305]),
        .hazard_observed_o(dut_o[1306]), .unknown_hazard_o(dut_o[1307]));
    assign dut_o[1269 +: 32] = st27;
    assign dut_o[1308 +: 8] = pv27;
    reg [109:0] w28;
    always @(posedge clk) w28 <= {w27[6:0], w27[109:7]};
    wire [31:0] st28; wire inv28, bd28; wire [7:0] pv28;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe28 (
        .candidate_value_i(w28[31:0]), .candidate_known_i(w28[104]),
        .current_state_i(st28), .lower_bound_i(w28[63:32]), .upper_bound_i(w28[95:64]),
        .rule_cfg_i(w28[103:96]), .predicate_vector_o(pv28),
        .hw_invariant_ok_o(inv28), .big_dot_flag_o(bd28));
    kpol_txn_gate #(.DATA_WIDTH(32)) g28 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w28[105]),
        .candidate_known_i(w28[104]), .candidate_value_i(w28[31:0]),
        .assumption_known_i(w28[106]), .assumption_true_i(w28[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv28),
        .hazard_known_i(w28[108]), .hazard_true_i(w28[109]),
        .state_o(st28), .committed_o(dut_o[1348]),
        .rejected_o(dut_o[1349]), .rejected_input_o(dut_o[1350]),
        .rejected_invariant_o(dut_o[1351]), .changed_o(dut_o[1352]),
        .hazard_observed_o(dut_o[1353]), .unknown_hazard_o(dut_o[1354]));
    assign dut_o[1316 +: 32] = st28;
    assign dut_o[1355 +: 8] = pv28;
    reg [109:0] w29;
    always @(posedge clk) w29 <= {w28[6:0], w28[109:7]};
    wire [31:0] st29; wire inv29, bd29; wire [7:0] pv29;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe29 (
        .candidate_value_i(w29[31:0]), .candidate_known_i(w29[104]),
        .current_state_i(st29), .lower_bound_i(w29[63:32]), .upper_bound_i(w29[95:64]),
        .rule_cfg_i(w29[103:96]), .predicate_vector_o(pv29),
        .hw_invariant_ok_o(inv29), .big_dot_flag_o(bd29));
    kpol_txn_gate #(.DATA_WIDTH(32)) g29 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w29[105]),
        .candidate_known_i(w29[104]), .candidate_value_i(w29[31:0]),
        .assumption_known_i(w29[106]), .assumption_true_i(w29[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv29),
        .hazard_known_i(w29[108]), .hazard_true_i(w29[109]),
        .state_o(st29), .committed_o(dut_o[1395]),
        .rejected_o(dut_o[1396]), .rejected_input_o(dut_o[1397]),
        .rejected_invariant_o(dut_o[1398]), .changed_o(dut_o[1399]),
        .hazard_observed_o(dut_o[1400]), .unknown_hazard_o(dut_o[1401]));
    assign dut_o[1363 +: 32] = st29;
    assign dut_o[1402 +: 8] = pv29;
    reg [109:0] w30;
    always @(posedge clk) w30 <= {w29[6:0], w29[109:7]};
    wire [31:0] st30; wire inv30, bd30; wire [7:0] pv30;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe30 (
        .candidate_value_i(w30[31:0]), .candidate_known_i(w30[104]),
        .current_state_i(st30), .lower_bound_i(w30[63:32]), .upper_bound_i(w30[95:64]),
        .rule_cfg_i(w30[103:96]), .predicate_vector_o(pv30),
        .hw_invariant_ok_o(inv30), .big_dot_flag_o(bd30));
    kpol_txn_gate #(.DATA_WIDTH(32)) g30 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w30[105]),
        .candidate_known_i(w30[104]), .candidate_value_i(w30[31:0]),
        .assumption_known_i(w30[106]), .assumption_true_i(w30[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv30),
        .hazard_known_i(w30[108]), .hazard_true_i(w30[109]),
        .state_o(st30), .committed_o(dut_o[1442]),
        .rejected_o(dut_o[1443]), .rejected_input_o(dut_o[1444]),
        .rejected_invariant_o(dut_o[1445]), .changed_o(dut_o[1446]),
        .hazard_observed_o(dut_o[1447]), .unknown_hazard_o(dut_o[1448]));
    assign dut_o[1410 +: 32] = st30;
    assign dut_o[1449 +: 8] = pv30;
    reg [109:0] w31;
    always @(posedge clk) w31 <= {w30[6:0], w30[109:7]};
    wire [31:0] st31; wire inv31, bd31; wire [7:0] pv31;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe31 (
        .candidate_value_i(w31[31:0]), .candidate_known_i(w31[104]),
        .current_state_i(st31), .lower_bound_i(w31[63:32]), .upper_bound_i(w31[95:64]),
        .rule_cfg_i(w31[103:96]), .predicate_vector_o(pv31),
        .hw_invariant_ok_o(inv31), .big_dot_flag_o(bd31));
    kpol_txn_gate #(.DATA_WIDTH(32)) g31 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w31[105]),
        .candidate_known_i(w31[104]), .candidate_value_i(w31[31:0]),
        .assumption_known_i(w31[106]), .assumption_true_i(w31[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv31),
        .hazard_known_i(w31[108]), .hazard_true_i(w31[109]),
        .state_o(st31), .committed_o(dut_o[1489]),
        .rejected_o(dut_o[1490]), .rejected_input_o(dut_o[1491]),
        .rejected_invariant_o(dut_o[1492]), .changed_o(dut_o[1493]),
        .hazard_observed_o(dut_o[1494]), .unknown_hazard_o(dut_o[1495]));
    assign dut_o[1457 +: 32] = st31;
    assign dut_o[1496 +: 8] = pv31;
    reg [109:0] w32;
    always @(posedge clk) w32 <= {w31[6:0], w31[109:7]};
    wire [31:0] st32; wire inv32, bd32; wire [7:0] pv32;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe32 (
        .candidate_value_i(w32[31:0]), .candidate_known_i(w32[104]),
        .current_state_i(st32), .lower_bound_i(w32[63:32]), .upper_bound_i(w32[95:64]),
        .rule_cfg_i(w32[103:96]), .predicate_vector_o(pv32),
        .hw_invariant_ok_o(inv32), .big_dot_flag_o(bd32));
    kpol_txn_gate #(.DATA_WIDTH(32)) g32 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w32[105]),
        .candidate_known_i(w32[104]), .candidate_value_i(w32[31:0]),
        .assumption_known_i(w32[106]), .assumption_true_i(w32[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv32),
        .hazard_known_i(w32[108]), .hazard_true_i(w32[109]),
        .state_o(st32), .committed_o(dut_o[1536]),
        .rejected_o(dut_o[1537]), .rejected_input_o(dut_o[1538]),
        .rejected_invariant_o(dut_o[1539]), .changed_o(dut_o[1540]),
        .hazard_observed_o(dut_o[1541]), .unknown_hazard_o(dut_o[1542]));
    assign dut_o[1504 +: 32] = st32;
    assign dut_o[1543 +: 8] = pv32;
    reg [109:0] w33;
    always @(posedge clk) w33 <= {w32[6:0], w32[109:7]};
    wire [31:0] st33; wire inv33, bd33; wire [7:0] pv33;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe33 (
        .candidate_value_i(w33[31:0]), .candidate_known_i(w33[104]),
        .current_state_i(st33), .lower_bound_i(w33[63:32]), .upper_bound_i(w33[95:64]),
        .rule_cfg_i(w33[103:96]), .predicate_vector_o(pv33),
        .hw_invariant_ok_o(inv33), .big_dot_flag_o(bd33));
    kpol_txn_gate #(.DATA_WIDTH(32)) g33 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w33[105]),
        .candidate_known_i(w33[104]), .candidate_value_i(w33[31:0]),
        .assumption_known_i(w33[106]), .assumption_true_i(w33[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv33),
        .hazard_known_i(w33[108]), .hazard_true_i(w33[109]),
        .state_o(st33), .committed_o(dut_o[1583]),
        .rejected_o(dut_o[1584]), .rejected_input_o(dut_o[1585]),
        .rejected_invariant_o(dut_o[1586]), .changed_o(dut_o[1587]),
        .hazard_observed_o(dut_o[1588]), .unknown_hazard_o(dut_o[1589]));
    assign dut_o[1551 +: 32] = st33;
    assign dut_o[1590 +: 8] = pv33;
    reg [109:0] w34;
    always @(posedge clk) w34 <= {w33[6:0], w33[109:7]};
    wire [31:0] st34; wire inv34, bd34; wire [7:0] pv34;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe34 (
        .candidate_value_i(w34[31:0]), .candidate_known_i(w34[104]),
        .current_state_i(st34), .lower_bound_i(w34[63:32]), .upper_bound_i(w34[95:64]),
        .rule_cfg_i(w34[103:96]), .predicate_vector_o(pv34),
        .hw_invariant_ok_o(inv34), .big_dot_flag_o(bd34));
    kpol_txn_gate #(.DATA_WIDTH(32)) g34 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w34[105]),
        .candidate_known_i(w34[104]), .candidate_value_i(w34[31:0]),
        .assumption_known_i(w34[106]), .assumption_true_i(w34[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv34),
        .hazard_known_i(w34[108]), .hazard_true_i(w34[109]),
        .state_o(st34), .committed_o(dut_o[1630]),
        .rejected_o(dut_o[1631]), .rejected_input_o(dut_o[1632]),
        .rejected_invariant_o(dut_o[1633]), .changed_o(dut_o[1634]),
        .hazard_observed_o(dut_o[1635]), .unknown_hazard_o(dut_o[1636]));
    assign dut_o[1598 +: 32] = st34;
    assign dut_o[1637 +: 8] = pv34;
    reg [109:0] w35;
    always @(posedge clk) w35 <= {w34[6:0], w34[109:7]};
    wire [31:0] st35; wire inv35, bd35; wire [7:0] pv35;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe35 (
        .candidate_value_i(w35[31:0]), .candidate_known_i(w35[104]),
        .current_state_i(st35), .lower_bound_i(w35[63:32]), .upper_bound_i(w35[95:64]),
        .rule_cfg_i(w35[103:96]), .predicate_vector_o(pv35),
        .hw_invariant_ok_o(inv35), .big_dot_flag_o(bd35));
    kpol_txn_gate #(.DATA_WIDTH(32)) g35 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w35[105]),
        .candidate_known_i(w35[104]), .candidate_value_i(w35[31:0]),
        .assumption_known_i(w35[106]), .assumption_true_i(w35[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv35),
        .hazard_known_i(w35[108]), .hazard_true_i(w35[109]),
        .state_o(st35), .committed_o(dut_o[1677]),
        .rejected_o(dut_o[1678]), .rejected_input_o(dut_o[1679]),
        .rejected_invariant_o(dut_o[1680]), .changed_o(dut_o[1681]),
        .hazard_observed_o(dut_o[1682]), .unknown_hazard_o(dut_o[1683]));
    assign dut_o[1645 +: 32] = st35;
    assign dut_o[1684 +: 8] = pv35;
    reg [109:0] w36;
    always @(posedge clk) w36 <= {w35[6:0], w35[109:7]};
    wire [31:0] st36; wire inv36, bd36; wire [7:0] pv36;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe36 (
        .candidate_value_i(w36[31:0]), .candidate_known_i(w36[104]),
        .current_state_i(st36), .lower_bound_i(w36[63:32]), .upper_bound_i(w36[95:64]),
        .rule_cfg_i(w36[103:96]), .predicate_vector_o(pv36),
        .hw_invariant_ok_o(inv36), .big_dot_flag_o(bd36));
    kpol_txn_gate #(.DATA_WIDTH(32)) g36 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w36[105]),
        .candidate_known_i(w36[104]), .candidate_value_i(w36[31:0]),
        .assumption_known_i(w36[106]), .assumption_true_i(w36[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv36),
        .hazard_known_i(w36[108]), .hazard_true_i(w36[109]),
        .state_o(st36), .committed_o(dut_o[1724]),
        .rejected_o(dut_o[1725]), .rejected_input_o(dut_o[1726]),
        .rejected_invariant_o(dut_o[1727]), .changed_o(dut_o[1728]),
        .hazard_observed_o(dut_o[1729]), .unknown_hazard_o(dut_o[1730]));
    assign dut_o[1692 +: 32] = st36;
    assign dut_o[1731 +: 8] = pv36;
    reg [109:0] w37;
    always @(posedge clk) w37 <= {w36[6:0], w36[109:7]};
    wire [31:0] st37; wire inv37, bd37; wire [7:0] pv37;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe37 (
        .candidate_value_i(w37[31:0]), .candidate_known_i(w37[104]),
        .current_state_i(st37), .lower_bound_i(w37[63:32]), .upper_bound_i(w37[95:64]),
        .rule_cfg_i(w37[103:96]), .predicate_vector_o(pv37),
        .hw_invariant_ok_o(inv37), .big_dot_flag_o(bd37));
    kpol_txn_gate #(.DATA_WIDTH(32)) g37 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w37[105]),
        .candidate_known_i(w37[104]), .candidate_value_i(w37[31:0]),
        .assumption_known_i(w37[106]), .assumption_true_i(w37[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv37),
        .hazard_known_i(w37[108]), .hazard_true_i(w37[109]),
        .state_o(st37), .committed_o(dut_o[1771]),
        .rejected_o(dut_o[1772]), .rejected_input_o(dut_o[1773]),
        .rejected_invariant_o(dut_o[1774]), .changed_o(dut_o[1775]),
        .hazard_observed_o(dut_o[1776]), .unknown_hazard_o(dut_o[1777]));
    assign dut_o[1739 +: 32] = st37;
    assign dut_o[1778 +: 8] = pv37;
    reg [109:0] w38;
    always @(posedge clk) w38 <= {w37[6:0], w37[109:7]};
    wire [31:0] st38; wire inv38, bd38; wire [7:0] pv38;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe38 (
        .candidate_value_i(w38[31:0]), .candidate_known_i(w38[104]),
        .current_state_i(st38), .lower_bound_i(w38[63:32]), .upper_bound_i(w38[95:64]),
        .rule_cfg_i(w38[103:96]), .predicate_vector_o(pv38),
        .hw_invariant_ok_o(inv38), .big_dot_flag_o(bd38));
    kpol_txn_gate #(.DATA_WIDTH(32)) g38 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w38[105]),
        .candidate_known_i(w38[104]), .candidate_value_i(w38[31:0]),
        .assumption_known_i(w38[106]), .assumption_true_i(w38[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv38),
        .hazard_known_i(w38[108]), .hazard_true_i(w38[109]),
        .state_o(st38), .committed_o(dut_o[1818]),
        .rejected_o(dut_o[1819]), .rejected_input_o(dut_o[1820]),
        .rejected_invariant_o(dut_o[1821]), .changed_o(dut_o[1822]),
        .hazard_observed_o(dut_o[1823]), .unknown_hazard_o(dut_o[1824]));
    assign dut_o[1786 +: 32] = st38;
    assign dut_o[1825 +: 8] = pv38;
    reg [109:0] w39;
    always @(posedge clk) w39 <= {w38[6:0], w38[109:7]};
    wire [31:0] st39; wire inv39, bd39; wire [7:0] pv39;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe39 (
        .candidate_value_i(w39[31:0]), .candidate_known_i(w39[104]),
        .current_state_i(st39), .lower_bound_i(w39[63:32]), .upper_bound_i(w39[95:64]),
        .rule_cfg_i(w39[103:96]), .predicate_vector_o(pv39),
        .hw_invariant_ok_o(inv39), .big_dot_flag_o(bd39));
    kpol_txn_gate #(.DATA_WIDTH(32)) g39 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w39[105]),
        .candidate_known_i(w39[104]), .candidate_value_i(w39[31:0]),
        .assumption_known_i(w39[106]), .assumption_true_i(w39[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv39),
        .hazard_known_i(w39[108]), .hazard_true_i(w39[109]),
        .state_o(st39), .committed_o(dut_o[1865]),
        .rejected_o(dut_o[1866]), .rejected_input_o(dut_o[1867]),
        .rejected_invariant_o(dut_o[1868]), .changed_o(dut_o[1869]),
        .hazard_observed_o(dut_o[1870]), .unknown_hazard_o(dut_o[1871]));
    assign dut_o[1833 +: 32] = st39;
    assign dut_o[1872 +: 8] = pv39;
    reg [109:0] w40;
    always @(posedge clk) w40 <= {w39[6:0], w39[109:7]};
    wire [31:0] st40; wire inv40, bd40; wire [7:0] pv40;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe40 (
        .candidate_value_i(w40[31:0]), .candidate_known_i(w40[104]),
        .current_state_i(st40), .lower_bound_i(w40[63:32]), .upper_bound_i(w40[95:64]),
        .rule_cfg_i(w40[103:96]), .predicate_vector_o(pv40),
        .hw_invariant_ok_o(inv40), .big_dot_flag_o(bd40));
    kpol_txn_gate #(.DATA_WIDTH(32)) g40 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w40[105]),
        .candidate_known_i(w40[104]), .candidate_value_i(w40[31:0]),
        .assumption_known_i(w40[106]), .assumption_true_i(w40[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv40),
        .hazard_known_i(w40[108]), .hazard_true_i(w40[109]),
        .state_o(st40), .committed_o(dut_o[1912]),
        .rejected_o(dut_o[1913]), .rejected_input_o(dut_o[1914]),
        .rejected_invariant_o(dut_o[1915]), .changed_o(dut_o[1916]),
        .hazard_observed_o(dut_o[1917]), .unknown_hazard_o(dut_o[1918]));
    assign dut_o[1880 +: 32] = st40;
    assign dut_o[1919 +: 8] = pv40;
    reg [109:0] w41;
    always @(posedge clk) w41 <= {w40[6:0], w40[109:7]};
    wire [31:0] st41; wire inv41, bd41; wire [7:0] pv41;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe41 (
        .candidate_value_i(w41[31:0]), .candidate_known_i(w41[104]),
        .current_state_i(st41), .lower_bound_i(w41[63:32]), .upper_bound_i(w41[95:64]),
        .rule_cfg_i(w41[103:96]), .predicate_vector_o(pv41),
        .hw_invariant_ok_o(inv41), .big_dot_flag_o(bd41));
    kpol_txn_gate #(.DATA_WIDTH(32)) g41 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w41[105]),
        .candidate_known_i(w41[104]), .candidate_value_i(w41[31:0]),
        .assumption_known_i(w41[106]), .assumption_true_i(w41[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv41),
        .hazard_known_i(w41[108]), .hazard_true_i(w41[109]),
        .state_o(st41), .committed_o(dut_o[1959]),
        .rejected_o(dut_o[1960]), .rejected_input_o(dut_o[1961]),
        .rejected_invariant_o(dut_o[1962]), .changed_o(dut_o[1963]),
        .hazard_observed_o(dut_o[1964]), .unknown_hazard_o(dut_o[1965]));
    assign dut_o[1927 +: 32] = st41;
    assign dut_o[1966 +: 8] = pv41;
    reg [109:0] w42;
    always @(posedge clk) w42 <= {w41[6:0], w41[109:7]};
    wire [31:0] st42; wire inv42, bd42; wire [7:0] pv42;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe42 (
        .candidate_value_i(w42[31:0]), .candidate_known_i(w42[104]),
        .current_state_i(st42), .lower_bound_i(w42[63:32]), .upper_bound_i(w42[95:64]),
        .rule_cfg_i(w42[103:96]), .predicate_vector_o(pv42),
        .hw_invariant_ok_o(inv42), .big_dot_flag_o(bd42));
    kpol_txn_gate #(.DATA_WIDTH(32)) g42 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w42[105]),
        .candidate_known_i(w42[104]), .candidate_value_i(w42[31:0]),
        .assumption_known_i(w42[106]), .assumption_true_i(w42[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv42),
        .hazard_known_i(w42[108]), .hazard_true_i(w42[109]),
        .state_o(st42), .committed_o(dut_o[2006]),
        .rejected_o(dut_o[2007]), .rejected_input_o(dut_o[2008]),
        .rejected_invariant_o(dut_o[2009]), .changed_o(dut_o[2010]),
        .hazard_observed_o(dut_o[2011]), .unknown_hazard_o(dut_o[2012]));
    assign dut_o[1974 +: 32] = st42;
    assign dut_o[2013 +: 8] = pv42;
    reg [109:0] w43;
    always @(posedge clk) w43 <= {w42[6:0], w42[109:7]};
    wire [31:0] st43; wire inv43, bd43; wire [7:0] pv43;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe43 (
        .candidate_value_i(w43[31:0]), .candidate_known_i(w43[104]),
        .current_state_i(st43), .lower_bound_i(w43[63:32]), .upper_bound_i(w43[95:64]),
        .rule_cfg_i(w43[103:96]), .predicate_vector_o(pv43),
        .hw_invariant_ok_o(inv43), .big_dot_flag_o(bd43));
    kpol_txn_gate #(.DATA_WIDTH(32)) g43 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w43[105]),
        .candidate_known_i(w43[104]), .candidate_value_i(w43[31:0]),
        .assumption_known_i(w43[106]), .assumption_true_i(w43[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv43),
        .hazard_known_i(w43[108]), .hazard_true_i(w43[109]),
        .state_o(st43), .committed_o(dut_o[2053]),
        .rejected_o(dut_o[2054]), .rejected_input_o(dut_o[2055]),
        .rejected_invariant_o(dut_o[2056]), .changed_o(dut_o[2057]),
        .hazard_observed_o(dut_o[2058]), .unknown_hazard_o(dut_o[2059]));
    assign dut_o[2021 +: 32] = st43;
    assign dut_o[2060 +: 8] = pv43;
    reg [109:0] w44;
    always @(posedge clk) w44 <= {w43[6:0], w43[109:7]};
    wire [31:0] st44; wire inv44, bd44; wire [7:0] pv44;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe44 (
        .candidate_value_i(w44[31:0]), .candidate_known_i(w44[104]),
        .current_state_i(st44), .lower_bound_i(w44[63:32]), .upper_bound_i(w44[95:64]),
        .rule_cfg_i(w44[103:96]), .predicate_vector_o(pv44),
        .hw_invariant_ok_o(inv44), .big_dot_flag_o(bd44));
    kpol_txn_gate #(.DATA_WIDTH(32)) g44 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w44[105]),
        .candidate_known_i(w44[104]), .candidate_value_i(w44[31:0]),
        .assumption_known_i(w44[106]), .assumption_true_i(w44[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv44),
        .hazard_known_i(w44[108]), .hazard_true_i(w44[109]),
        .state_o(st44), .committed_o(dut_o[2100]),
        .rejected_o(dut_o[2101]), .rejected_input_o(dut_o[2102]),
        .rejected_invariant_o(dut_o[2103]), .changed_o(dut_o[2104]),
        .hazard_observed_o(dut_o[2105]), .unknown_hazard_o(dut_o[2106]));
    assign dut_o[2068 +: 32] = st44;
    assign dut_o[2107 +: 8] = pv44;
    reg [109:0] w45;
    always @(posedge clk) w45 <= {w44[6:0], w44[109:7]};
    wire [31:0] st45; wire inv45, bd45; wire [7:0] pv45;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe45 (
        .candidate_value_i(w45[31:0]), .candidate_known_i(w45[104]),
        .current_state_i(st45), .lower_bound_i(w45[63:32]), .upper_bound_i(w45[95:64]),
        .rule_cfg_i(w45[103:96]), .predicate_vector_o(pv45),
        .hw_invariant_ok_o(inv45), .big_dot_flag_o(bd45));
    kpol_txn_gate #(.DATA_WIDTH(32)) g45 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w45[105]),
        .candidate_known_i(w45[104]), .candidate_value_i(w45[31:0]),
        .assumption_known_i(w45[106]), .assumption_true_i(w45[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv45),
        .hazard_known_i(w45[108]), .hazard_true_i(w45[109]),
        .state_o(st45), .committed_o(dut_o[2147]),
        .rejected_o(dut_o[2148]), .rejected_input_o(dut_o[2149]),
        .rejected_invariant_o(dut_o[2150]), .changed_o(dut_o[2151]),
        .hazard_observed_o(dut_o[2152]), .unknown_hazard_o(dut_o[2153]));
    assign dut_o[2115 +: 32] = st45;
    assign dut_o[2154 +: 8] = pv45;
    reg [109:0] w46;
    always @(posedge clk) w46 <= {w45[6:0], w45[109:7]};
    wire [31:0] st46; wire inv46, bd46; wire [7:0] pv46;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe46 (
        .candidate_value_i(w46[31:0]), .candidate_known_i(w46[104]),
        .current_state_i(st46), .lower_bound_i(w46[63:32]), .upper_bound_i(w46[95:64]),
        .rule_cfg_i(w46[103:96]), .predicate_vector_o(pv46),
        .hw_invariant_ok_o(inv46), .big_dot_flag_o(bd46));
    kpol_txn_gate #(.DATA_WIDTH(32)) g46 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w46[105]),
        .candidate_known_i(w46[104]), .candidate_value_i(w46[31:0]),
        .assumption_known_i(w46[106]), .assumption_true_i(w46[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv46),
        .hazard_known_i(w46[108]), .hazard_true_i(w46[109]),
        .state_o(st46), .committed_o(dut_o[2194]),
        .rejected_o(dut_o[2195]), .rejected_input_o(dut_o[2196]),
        .rejected_invariant_o(dut_o[2197]), .changed_o(dut_o[2198]),
        .hazard_observed_o(dut_o[2199]), .unknown_hazard_o(dut_o[2200]));
    assign dut_o[2162 +: 32] = st46;
    assign dut_o[2201 +: 8] = pv46;
    reg [109:0] w47;
    always @(posedge clk) w47 <= {w46[6:0], w46[109:7]};
    wire [31:0] st47; wire inv47, bd47; wire [7:0] pv47;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe47 (
        .candidate_value_i(w47[31:0]), .candidate_known_i(w47[104]),
        .current_state_i(st47), .lower_bound_i(w47[63:32]), .upper_bound_i(w47[95:64]),
        .rule_cfg_i(w47[103:96]), .predicate_vector_o(pv47),
        .hw_invariant_ok_o(inv47), .big_dot_flag_o(bd47));
    kpol_txn_gate #(.DATA_WIDTH(32)) g47 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w47[105]),
        .candidate_known_i(w47[104]), .candidate_value_i(w47[31:0]),
        .assumption_known_i(w47[106]), .assumption_true_i(w47[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv47),
        .hazard_known_i(w47[108]), .hazard_true_i(w47[109]),
        .state_o(st47), .committed_o(dut_o[2241]),
        .rejected_o(dut_o[2242]), .rejected_input_o(dut_o[2243]),
        .rejected_invariant_o(dut_o[2244]), .changed_o(dut_o[2245]),
        .hazard_observed_o(dut_o[2246]), .unknown_hazard_o(dut_o[2247]));
    assign dut_o[2209 +: 32] = st47;
    assign dut_o[2248 +: 8] = pv47;
    reg [109:0] w48;
    always @(posedge clk) w48 <= {w47[6:0], w47[109:7]};
    wire [31:0] st48; wire inv48, bd48; wire [7:0] pv48;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe48 (
        .candidate_value_i(w48[31:0]), .candidate_known_i(w48[104]),
        .current_state_i(st48), .lower_bound_i(w48[63:32]), .upper_bound_i(w48[95:64]),
        .rule_cfg_i(w48[103:96]), .predicate_vector_o(pv48),
        .hw_invariant_ok_o(inv48), .big_dot_flag_o(bd48));
    kpol_txn_gate #(.DATA_WIDTH(32)) g48 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w48[105]),
        .candidate_known_i(w48[104]), .candidate_value_i(w48[31:0]),
        .assumption_known_i(w48[106]), .assumption_true_i(w48[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv48),
        .hazard_known_i(w48[108]), .hazard_true_i(w48[109]),
        .state_o(st48), .committed_o(dut_o[2288]),
        .rejected_o(dut_o[2289]), .rejected_input_o(dut_o[2290]),
        .rejected_invariant_o(dut_o[2291]), .changed_o(dut_o[2292]),
        .hazard_observed_o(dut_o[2293]), .unknown_hazard_o(dut_o[2294]));
    assign dut_o[2256 +: 32] = st48;
    assign dut_o[2295 +: 8] = pv48;
    reg [109:0] w49;
    always @(posedge clk) w49 <= {w48[6:0], w48[109:7]};
    wire [31:0] st49; wire inv49, bd49; wire [7:0] pv49;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe49 (
        .candidate_value_i(w49[31:0]), .candidate_known_i(w49[104]),
        .current_state_i(st49), .lower_bound_i(w49[63:32]), .upper_bound_i(w49[95:64]),
        .rule_cfg_i(w49[103:96]), .predicate_vector_o(pv49),
        .hw_invariant_ok_o(inv49), .big_dot_flag_o(bd49));
    kpol_txn_gate #(.DATA_WIDTH(32)) g49 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w49[105]),
        .candidate_known_i(w49[104]), .candidate_value_i(w49[31:0]),
        .assumption_known_i(w49[106]), .assumption_true_i(w49[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv49),
        .hazard_known_i(w49[108]), .hazard_true_i(w49[109]),
        .state_o(st49), .committed_o(dut_o[2335]),
        .rejected_o(dut_o[2336]), .rejected_input_o(dut_o[2337]),
        .rejected_invariant_o(dut_o[2338]), .changed_o(dut_o[2339]),
        .hazard_observed_o(dut_o[2340]), .unknown_hazard_o(dut_o[2341]));
    assign dut_o[2303 +: 32] = st49;
    assign dut_o[2342 +: 8] = pv49;
    reg [109:0] w50;
    always @(posedge clk) w50 <= {w49[6:0], w49[109:7]};
    wire [31:0] st50; wire inv50, bd50; wire [7:0] pv50;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe50 (
        .candidate_value_i(w50[31:0]), .candidate_known_i(w50[104]),
        .current_state_i(st50), .lower_bound_i(w50[63:32]), .upper_bound_i(w50[95:64]),
        .rule_cfg_i(w50[103:96]), .predicate_vector_o(pv50),
        .hw_invariant_ok_o(inv50), .big_dot_flag_o(bd50));
    kpol_txn_gate #(.DATA_WIDTH(32)) g50 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w50[105]),
        .candidate_known_i(w50[104]), .candidate_value_i(w50[31:0]),
        .assumption_known_i(w50[106]), .assumption_true_i(w50[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv50),
        .hazard_known_i(w50[108]), .hazard_true_i(w50[109]),
        .state_o(st50), .committed_o(dut_o[2382]),
        .rejected_o(dut_o[2383]), .rejected_input_o(dut_o[2384]),
        .rejected_invariant_o(dut_o[2385]), .changed_o(dut_o[2386]),
        .hazard_observed_o(dut_o[2387]), .unknown_hazard_o(dut_o[2388]));
    assign dut_o[2350 +: 32] = st50;
    assign dut_o[2389 +: 8] = pv50;
    reg [109:0] w51;
    always @(posedge clk) w51 <= {w50[6:0], w50[109:7]};
    wire [31:0] st51; wire inv51, bd51; wire [7:0] pv51;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe51 (
        .candidate_value_i(w51[31:0]), .candidate_known_i(w51[104]),
        .current_state_i(st51), .lower_bound_i(w51[63:32]), .upper_bound_i(w51[95:64]),
        .rule_cfg_i(w51[103:96]), .predicate_vector_o(pv51),
        .hw_invariant_ok_o(inv51), .big_dot_flag_o(bd51));
    kpol_txn_gate #(.DATA_WIDTH(32)) g51 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w51[105]),
        .candidate_known_i(w51[104]), .candidate_value_i(w51[31:0]),
        .assumption_known_i(w51[106]), .assumption_true_i(w51[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv51),
        .hazard_known_i(w51[108]), .hazard_true_i(w51[109]),
        .state_o(st51), .committed_o(dut_o[2429]),
        .rejected_o(dut_o[2430]), .rejected_input_o(dut_o[2431]),
        .rejected_invariant_o(dut_o[2432]), .changed_o(dut_o[2433]),
        .hazard_observed_o(dut_o[2434]), .unknown_hazard_o(dut_o[2435]));
    assign dut_o[2397 +: 32] = st51;
    assign dut_o[2436 +: 8] = pv51;
    reg [109:0] w52;
    always @(posedge clk) w52 <= {w51[6:0], w51[109:7]};
    wire [31:0] st52; wire inv52, bd52; wire [7:0] pv52;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe52 (
        .candidate_value_i(w52[31:0]), .candidate_known_i(w52[104]),
        .current_state_i(st52), .lower_bound_i(w52[63:32]), .upper_bound_i(w52[95:64]),
        .rule_cfg_i(w52[103:96]), .predicate_vector_o(pv52),
        .hw_invariant_ok_o(inv52), .big_dot_flag_o(bd52));
    kpol_txn_gate #(.DATA_WIDTH(32)) g52 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w52[105]),
        .candidate_known_i(w52[104]), .candidate_value_i(w52[31:0]),
        .assumption_known_i(w52[106]), .assumption_true_i(w52[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv52),
        .hazard_known_i(w52[108]), .hazard_true_i(w52[109]),
        .state_o(st52), .committed_o(dut_o[2476]),
        .rejected_o(dut_o[2477]), .rejected_input_o(dut_o[2478]),
        .rejected_invariant_o(dut_o[2479]), .changed_o(dut_o[2480]),
        .hazard_observed_o(dut_o[2481]), .unknown_hazard_o(dut_o[2482]));
    assign dut_o[2444 +: 32] = st52;
    assign dut_o[2483 +: 8] = pv52;
    reg [109:0] w53;
    always @(posedge clk) w53 <= {w52[6:0], w52[109:7]};
    wire [31:0] st53; wire inv53, bd53; wire [7:0] pv53;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe53 (
        .candidate_value_i(w53[31:0]), .candidate_known_i(w53[104]),
        .current_state_i(st53), .lower_bound_i(w53[63:32]), .upper_bound_i(w53[95:64]),
        .rule_cfg_i(w53[103:96]), .predicate_vector_o(pv53),
        .hw_invariant_ok_o(inv53), .big_dot_flag_o(bd53));
    kpol_txn_gate #(.DATA_WIDTH(32)) g53 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w53[105]),
        .candidate_known_i(w53[104]), .candidate_value_i(w53[31:0]),
        .assumption_known_i(w53[106]), .assumption_true_i(w53[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv53),
        .hazard_known_i(w53[108]), .hazard_true_i(w53[109]),
        .state_o(st53), .committed_o(dut_o[2523]),
        .rejected_o(dut_o[2524]), .rejected_input_o(dut_o[2525]),
        .rejected_invariant_o(dut_o[2526]), .changed_o(dut_o[2527]),
        .hazard_observed_o(dut_o[2528]), .unknown_hazard_o(dut_o[2529]));
    assign dut_o[2491 +: 32] = st53;
    assign dut_o[2530 +: 8] = pv53;
    reg [109:0] w54;
    always @(posedge clk) w54 <= {w53[6:0], w53[109:7]};
    wire [31:0] st54; wire inv54, bd54; wire [7:0] pv54;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe54 (
        .candidate_value_i(w54[31:0]), .candidate_known_i(w54[104]),
        .current_state_i(st54), .lower_bound_i(w54[63:32]), .upper_bound_i(w54[95:64]),
        .rule_cfg_i(w54[103:96]), .predicate_vector_o(pv54),
        .hw_invariant_ok_o(inv54), .big_dot_flag_o(bd54));
    kpol_txn_gate #(.DATA_WIDTH(32)) g54 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w54[105]),
        .candidate_known_i(w54[104]), .candidate_value_i(w54[31:0]),
        .assumption_known_i(w54[106]), .assumption_true_i(w54[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv54),
        .hazard_known_i(w54[108]), .hazard_true_i(w54[109]),
        .state_o(st54), .committed_o(dut_o[2570]),
        .rejected_o(dut_o[2571]), .rejected_input_o(dut_o[2572]),
        .rejected_invariant_o(dut_o[2573]), .changed_o(dut_o[2574]),
        .hazard_observed_o(dut_o[2575]), .unknown_hazard_o(dut_o[2576]));
    assign dut_o[2538 +: 32] = st54;
    assign dut_o[2577 +: 8] = pv54;
    reg [109:0] w55;
    always @(posedge clk) w55 <= {w54[6:0], w54[109:7]};
    wire [31:0] st55; wire inv55, bd55; wire [7:0] pv55;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe55 (
        .candidate_value_i(w55[31:0]), .candidate_known_i(w55[104]),
        .current_state_i(st55), .lower_bound_i(w55[63:32]), .upper_bound_i(w55[95:64]),
        .rule_cfg_i(w55[103:96]), .predicate_vector_o(pv55),
        .hw_invariant_ok_o(inv55), .big_dot_flag_o(bd55));
    kpol_txn_gate #(.DATA_WIDTH(32)) g55 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w55[105]),
        .candidate_known_i(w55[104]), .candidate_value_i(w55[31:0]),
        .assumption_known_i(w55[106]), .assumption_true_i(w55[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv55),
        .hazard_known_i(w55[108]), .hazard_true_i(w55[109]),
        .state_o(st55), .committed_o(dut_o[2617]),
        .rejected_o(dut_o[2618]), .rejected_input_o(dut_o[2619]),
        .rejected_invariant_o(dut_o[2620]), .changed_o(dut_o[2621]),
        .hazard_observed_o(dut_o[2622]), .unknown_hazard_o(dut_o[2623]));
    assign dut_o[2585 +: 32] = st55;
    assign dut_o[2624 +: 8] = pv55;
    reg [109:0] w56;
    always @(posedge clk) w56 <= {w55[6:0], w55[109:7]};
    wire [31:0] st56; wire inv56, bd56; wire [7:0] pv56;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe56 (
        .candidate_value_i(w56[31:0]), .candidate_known_i(w56[104]),
        .current_state_i(st56), .lower_bound_i(w56[63:32]), .upper_bound_i(w56[95:64]),
        .rule_cfg_i(w56[103:96]), .predicate_vector_o(pv56),
        .hw_invariant_ok_o(inv56), .big_dot_flag_o(bd56));
    kpol_txn_gate #(.DATA_WIDTH(32)) g56 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w56[105]),
        .candidate_known_i(w56[104]), .candidate_value_i(w56[31:0]),
        .assumption_known_i(w56[106]), .assumption_true_i(w56[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv56),
        .hazard_known_i(w56[108]), .hazard_true_i(w56[109]),
        .state_o(st56), .committed_o(dut_o[2664]),
        .rejected_o(dut_o[2665]), .rejected_input_o(dut_o[2666]),
        .rejected_invariant_o(dut_o[2667]), .changed_o(dut_o[2668]),
        .hazard_observed_o(dut_o[2669]), .unknown_hazard_o(dut_o[2670]));
    assign dut_o[2632 +: 32] = st56;
    assign dut_o[2671 +: 8] = pv56;
    reg [109:0] w57;
    always @(posedge clk) w57 <= {w56[6:0], w56[109:7]};
    wire [31:0] st57; wire inv57, bd57; wire [7:0] pv57;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe57 (
        .candidate_value_i(w57[31:0]), .candidate_known_i(w57[104]),
        .current_state_i(st57), .lower_bound_i(w57[63:32]), .upper_bound_i(w57[95:64]),
        .rule_cfg_i(w57[103:96]), .predicate_vector_o(pv57),
        .hw_invariant_ok_o(inv57), .big_dot_flag_o(bd57));
    kpol_txn_gate #(.DATA_WIDTH(32)) g57 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w57[105]),
        .candidate_known_i(w57[104]), .candidate_value_i(w57[31:0]),
        .assumption_known_i(w57[106]), .assumption_true_i(w57[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv57),
        .hazard_known_i(w57[108]), .hazard_true_i(w57[109]),
        .state_o(st57), .committed_o(dut_o[2711]),
        .rejected_o(dut_o[2712]), .rejected_input_o(dut_o[2713]),
        .rejected_invariant_o(dut_o[2714]), .changed_o(dut_o[2715]),
        .hazard_observed_o(dut_o[2716]), .unknown_hazard_o(dut_o[2717]));
    assign dut_o[2679 +: 32] = st57;
    assign dut_o[2718 +: 8] = pv57;
    reg [109:0] w58;
    always @(posedge clk) w58 <= {w57[6:0], w57[109:7]};
    wire [31:0] st58; wire inv58, bd58; wire [7:0] pv58;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe58 (
        .candidate_value_i(w58[31:0]), .candidate_known_i(w58[104]),
        .current_state_i(st58), .lower_bound_i(w58[63:32]), .upper_bound_i(w58[95:64]),
        .rule_cfg_i(w58[103:96]), .predicate_vector_o(pv58),
        .hw_invariant_ok_o(inv58), .big_dot_flag_o(bd58));
    kpol_txn_gate #(.DATA_WIDTH(32)) g58 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w58[105]),
        .candidate_known_i(w58[104]), .candidate_value_i(w58[31:0]),
        .assumption_known_i(w58[106]), .assumption_true_i(w58[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv58),
        .hazard_known_i(w58[108]), .hazard_true_i(w58[109]),
        .state_o(st58), .committed_o(dut_o[2758]),
        .rejected_o(dut_o[2759]), .rejected_input_o(dut_o[2760]),
        .rejected_invariant_o(dut_o[2761]), .changed_o(dut_o[2762]),
        .hazard_observed_o(dut_o[2763]), .unknown_hazard_o(dut_o[2764]));
    assign dut_o[2726 +: 32] = st58;
    assign dut_o[2765 +: 8] = pv58;
    reg [109:0] w59;
    always @(posedge clk) w59 <= {w58[6:0], w58[109:7]};
    wire [31:0] st59; wire inv59, bd59; wire [7:0] pv59;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe59 (
        .candidate_value_i(w59[31:0]), .candidate_known_i(w59[104]),
        .current_state_i(st59), .lower_bound_i(w59[63:32]), .upper_bound_i(w59[95:64]),
        .rule_cfg_i(w59[103:96]), .predicate_vector_o(pv59),
        .hw_invariant_ok_o(inv59), .big_dot_flag_o(bd59));
    kpol_txn_gate #(.DATA_WIDTH(32)) g59 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w59[105]),
        .candidate_known_i(w59[104]), .candidate_value_i(w59[31:0]),
        .assumption_known_i(w59[106]), .assumption_true_i(w59[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv59),
        .hazard_known_i(w59[108]), .hazard_true_i(w59[109]),
        .state_o(st59), .committed_o(dut_o[2805]),
        .rejected_o(dut_o[2806]), .rejected_input_o(dut_o[2807]),
        .rejected_invariant_o(dut_o[2808]), .changed_o(dut_o[2809]),
        .hazard_observed_o(dut_o[2810]), .unknown_hazard_o(dut_o[2811]));
    assign dut_o[2773 +: 32] = st59;
    assign dut_o[2812 +: 8] = pv59;
    reg [109:0] w60;
    always @(posedge clk) w60 <= {w59[6:0], w59[109:7]};
    wire [31:0] st60; wire inv60, bd60; wire [7:0] pv60;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe60 (
        .candidate_value_i(w60[31:0]), .candidate_known_i(w60[104]),
        .current_state_i(st60), .lower_bound_i(w60[63:32]), .upper_bound_i(w60[95:64]),
        .rule_cfg_i(w60[103:96]), .predicate_vector_o(pv60),
        .hw_invariant_ok_o(inv60), .big_dot_flag_o(bd60));
    kpol_txn_gate #(.DATA_WIDTH(32)) g60 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w60[105]),
        .candidate_known_i(w60[104]), .candidate_value_i(w60[31:0]),
        .assumption_known_i(w60[106]), .assumption_true_i(w60[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv60),
        .hazard_known_i(w60[108]), .hazard_true_i(w60[109]),
        .state_o(st60), .committed_o(dut_o[2852]),
        .rejected_o(dut_o[2853]), .rejected_input_o(dut_o[2854]),
        .rejected_invariant_o(dut_o[2855]), .changed_o(dut_o[2856]),
        .hazard_observed_o(dut_o[2857]), .unknown_hazard_o(dut_o[2858]));
    assign dut_o[2820 +: 32] = st60;
    assign dut_o[2859 +: 8] = pv60;
    reg [109:0] w61;
    always @(posedge clk) w61 <= {w60[6:0], w60[109:7]};
    wire [31:0] st61; wire inv61, bd61; wire [7:0] pv61;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe61 (
        .candidate_value_i(w61[31:0]), .candidate_known_i(w61[104]),
        .current_state_i(st61), .lower_bound_i(w61[63:32]), .upper_bound_i(w61[95:64]),
        .rule_cfg_i(w61[103:96]), .predicate_vector_o(pv61),
        .hw_invariant_ok_o(inv61), .big_dot_flag_o(bd61));
    kpol_txn_gate #(.DATA_WIDTH(32)) g61 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w61[105]),
        .candidate_known_i(w61[104]), .candidate_value_i(w61[31:0]),
        .assumption_known_i(w61[106]), .assumption_true_i(w61[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv61),
        .hazard_known_i(w61[108]), .hazard_true_i(w61[109]),
        .state_o(st61), .committed_o(dut_o[2899]),
        .rejected_o(dut_o[2900]), .rejected_input_o(dut_o[2901]),
        .rejected_invariant_o(dut_o[2902]), .changed_o(dut_o[2903]),
        .hazard_observed_o(dut_o[2904]), .unknown_hazard_o(dut_o[2905]));
    assign dut_o[2867 +: 32] = st61;
    assign dut_o[2906 +: 8] = pv61;
    reg [109:0] w62;
    always @(posedge clk) w62 <= {w61[6:0], w61[109:7]};
    wire [31:0] st62; wire inv62, bd62; wire [7:0] pv62;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe62 (
        .candidate_value_i(w62[31:0]), .candidate_known_i(w62[104]),
        .current_state_i(st62), .lower_bound_i(w62[63:32]), .upper_bound_i(w62[95:64]),
        .rule_cfg_i(w62[103:96]), .predicate_vector_o(pv62),
        .hw_invariant_ok_o(inv62), .big_dot_flag_o(bd62));
    kpol_txn_gate #(.DATA_WIDTH(32)) g62 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w62[105]),
        .candidate_known_i(w62[104]), .candidate_value_i(w62[31:0]),
        .assumption_known_i(w62[106]), .assumption_true_i(w62[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv62),
        .hazard_known_i(w62[108]), .hazard_true_i(w62[109]),
        .state_o(st62), .committed_o(dut_o[2946]),
        .rejected_o(dut_o[2947]), .rejected_input_o(dut_o[2948]),
        .rejected_invariant_o(dut_o[2949]), .changed_o(dut_o[2950]),
        .hazard_observed_o(dut_o[2951]), .unknown_hazard_o(dut_o[2952]));
    assign dut_o[2914 +: 32] = st62;
    assign dut_o[2953 +: 8] = pv62;
    reg [109:0] w63;
    always @(posedge clk) w63 <= {w62[6:0], w62[109:7]};
    wire [31:0] st63; wire inv63, bd63; wire [7:0] pv63;
    km_predicate_evaluator #(.DATA_WIDTH(32)) pe63 (
        .candidate_value_i(w63[31:0]), .candidate_known_i(w63[104]),
        .current_state_i(st63), .lower_bound_i(w63[63:32]), .upper_bound_i(w63[95:64]),
        .rule_cfg_i(w63[103:96]), .predicate_vector_o(pv63),
        .hw_invariant_ok_o(inv63), .big_dot_flag_o(bd63));
    kpol_txn_gate #(.DATA_WIDTH(32)) g63 (
        .clk_i(clk), .rst_ni(rst_n), .event_valid_i(w63[105]),
        .candidate_known_i(w63[104]), .candidate_value_i(w63[31:0]),
        .assumption_known_i(w63[106]), .assumption_true_i(w63[107]),
        .invariant_known_i(1'b1), .invariant_true_i(inv63),
        .hazard_known_i(w63[108]), .hazard_true_i(w63[109]),
        .state_o(st63), .committed_o(dut_o[2993]),
        .rejected_o(dut_o[2994]), .rejected_input_o(dut_o[2995]),
        .rejected_invariant_o(dut_o[2996]), .changed_o(dut_o[2997]),
        .hazard_observed_o(dut_o[2998]), .unknown_hazard_o(dut_o[2999]));
    assign dut_o[2961 +: 32] = st63;
    assign dut_o[3000 +: 8] = pv63;
    assign dut_o[3008 +: 110] = w63;
    wire [3119:0] xp0 = {2'b0, dut_o};
    reg  [519:0] xr0;
    genvar xg0;
    for (xg0 = 0; xg0 < 520; xg0 = xg0 + 1) begin : gx0
        always @(posedge clk) xr0[xg0] <= ^xp0[xg0*6 +: 6];
    end
    wire [521:0] xp1 = {2'b0, xr0};
    reg  [86:0] xr1;
    genvar xg1;
    for (xg1 = 0; xg1 < 87; xg1 = xg1 + 1) begin : gx1
        always @(posedge clk) xr1[xg1] <= ^xp1[xg1*6 +: 6];
    end
    wire [89:0] xp2 = {3'b0, xr1};
    reg  [14:0] xr2;
    genvar xg2;
    for (xg2 = 0; xg2 < 15; xg2 = xg2 + 1) begin : gx2
        always @(posedge clk) xr2[xg2] <= ^xp2[xg2*6 +: 6];
    end
    wire [17:0] xp3 = {3'b0, xr2};
    reg  [2:0] xr3;
    genvar xg3;
    for (xg3 = 0; xg3 < 3; xg3 = xg3 + 1) begin : gx3
        always @(posedge clk) xr3[xg3] <= ^xp3[xg3*6 +: 6];
    end
    wire [5:0] xp4 = {3'b0, xr3};
    reg  [0:0] xr4;
    genvar xg4;
    for (xg4 = 0; xg4 < 1; xg4 = xg4 + 1) begin : gx4
        always @(posedge clk) xr4[xg4] <= ^xp4[xg4*6 +: 6];
    end
    always @(posedge clk) dout <= xr4;
endmodule
