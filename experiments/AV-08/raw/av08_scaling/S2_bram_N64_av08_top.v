`timescale 1ns/1ps
module av08_top (input wire clk, input wire rst_btn, input wire din, output reg dout);
    reg [1:0] rsync;
    always @(posedge clk) rsync <= {rsync[0], ~rst_btn};
    wire rst_n = rsync[1];
    reg [89:0] sr;
    always @(posedge clk) sr <= {sr[88:0], din};
    wire [64:0] dut_o;
    km_concept_bram #(.NUM_CONCEPTS(64), .DATA_WIDTH(32), .ADDR_WIDTH(8)) dut (
        .clk(clk), .rst_n(rst_n),
        .a_addr_i(sr[7:0]), .a_wdata_i(sr[39:8]), .a_wstrb_i(sr[43:40]),
        .a_we_i(sr[44]), .a_rdata_o(dut_o[31:0]),
        .b_addr_i(sr[52:45]), .b_wdata_i(sr[84:53]),
        .b_wstrb_i(sr[88:85]), .b_we_i(sr[89]), .b_rdata_o(dut_o[63:32]),
        .collision_detected_o(dut_o[64]));
    wire [65:0] xp0 = {1'b0, dut_o};
    reg  [10:0] xr0;
    genvar xg0;
    for (xg0 = 0; xg0 < 11; xg0 = xg0 + 1) begin : gx0
        always @(posedge clk) xr0[xg0] <= ^xp0[xg0*6 +: 6];
    end
    wire [11:0] xp1 = {1'b0, xr0};
    reg  [1:0] xr1;
    genvar xg1;
    for (xg1 = 0; xg1 < 2; xg1 = xg1 + 1) begin : gx1
        always @(posedge clk) xr1[xg1] <= ^xp1[xg1*6 +: 6];
    end
    wire [5:0] xp2 = {4'b0, xr1};
    reg  [0:0] xr2;
    genvar xg2;
    for (xg2 = 0; xg2 < 1; xg2 = xg2 + 1) begin : gx2
        always @(posedge clk) xr2[xg2] <= ^xp2[xg2*6 +: 6];
    end
    always @(posedge clk) dout <= xr2;
endmodule
