`timescale 1ns/1ps
module av08_top (input wire clk, input wire rst_btn, input wire din, output reg dout);
    reg [1:0] rsync;
    always @(posedge clk) rsync <= {rsync[0], ~rst_btn};
    wire rst_n = rsync[1];
    reg [109:0] sr;
    always @(posedge clk) sr <= {sr[108:0], din};
    wire [1613:0] dut_o;
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
    assign dut_o[1504 +: 110] = w31;
    wire [1613:0] xp0 = dut_o;
    reg  [268:0] xr0;
    genvar xg0;
    for (xg0 = 0; xg0 < 269; xg0 = xg0 + 1) begin : gx0
        always @(posedge clk) xr0[xg0] <= ^xp0[xg0*6 +: 6];
    end
    wire [269:0] xp1 = {1'b0, xr0};
    reg  [44:0] xr1;
    genvar xg1;
    for (xg1 = 0; xg1 < 45; xg1 = xg1 + 1) begin : gx1
        always @(posedge clk) xr1[xg1] <= ^xp1[xg1*6 +: 6];
    end
    wire [47:0] xp2 = {3'b0, xr1};
    reg  [7:0] xr2;
    genvar xg2;
    for (xg2 = 0; xg2 < 8; xg2 = xg2 + 1) begin : gx2
        always @(posedge clk) xr2[xg2] <= ^xp2[xg2*6 +: 6];
    end
    wire [11:0] xp3 = {4'b0, xr2};
    reg  [1:0] xr3;
    genvar xg3;
    for (xg3 = 0; xg3 < 2; xg3 = xg3 + 1) begin : gx3
        always @(posedge clk) xr3[xg3] <= ^xp3[xg3*6 +: 6];
    end
    wire [5:0] xp4 = {4'b0, xr3};
    reg  [0:0] xr4;
    genvar xg4;
    for (xg4 = 0; xg4 < 1; xg4 = xg4 + 1) begin : gx4
        always @(posedge clk) xr4[xg4] <= ^xp4[xg4*6 +: 6];
    end
    always @(posedge clk) dout <= xr4;
endmodule
