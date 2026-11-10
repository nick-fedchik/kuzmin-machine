`timescale 1ns/1ps
module av08_top (input wire clk, input wire rst_btn, input wire din, output reg dout);
    reg [1:0] rsync;
    always @(posedge clk) rsync <= {rsync[0], ~rst_btn};
    wire rst_n = rsync[1];
    reg [109:0] sr;
    always @(posedge clk) sr <= {sr[108:0], din};
    wire [861:0] dut_o;
    reg [109:0] w0;
    always @(posedge clk) w0 <= sr ^ {sr[0], sr[109:1]};
    assign dut_o[0 +: 47] = w0[46:0];
    reg [109:0] w1;
    always @(posedge clk) w1 <= {w0[6:0], w0[109:7]};
    assign dut_o[47 +: 47] = w1[46:0];
    reg [109:0] w2;
    always @(posedge clk) w2 <= {w1[6:0], w1[109:7]};
    assign dut_o[94 +: 47] = w2[46:0];
    reg [109:0] w3;
    always @(posedge clk) w3 <= {w2[6:0], w2[109:7]};
    assign dut_o[141 +: 47] = w3[46:0];
    reg [109:0] w4;
    always @(posedge clk) w4 <= {w3[6:0], w3[109:7]};
    assign dut_o[188 +: 47] = w4[46:0];
    reg [109:0] w5;
    always @(posedge clk) w5 <= {w4[6:0], w4[109:7]};
    assign dut_o[235 +: 47] = w5[46:0];
    reg [109:0] w6;
    always @(posedge clk) w6 <= {w5[6:0], w5[109:7]};
    assign dut_o[282 +: 47] = w6[46:0];
    reg [109:0] w7;
    always @(posedge clk) w7 <= {w6[6:0], w6[109:7]};
    assign dut_o[329 +: 47] = w7[46:0];
    reg [109:0] w8;
    always @(posedge clk) w8 <= {w7[6:0], w7[109:7]};
    assign dut_o[376 +: 47] = w8[46:0];
    reg [109:0] w9;
    always @(posedge clk) w9 <= {w8[6:0], w8[109:7]};
    assign dut_o[423 +: 47] = w9[46:0];
    reg [109:0] w10;
    always @(posedge clk) w10 <= {w9[6:0], w9[109:7]};
    assign dut_o[470 +: 47] = w10[46:0];
    reg [109:0] w11;
    always @(posedge clk) w11 <= {w10[6:0], w10[109:7]};
    assign dut_o[517 +: 47] = w11[46:0];
    reg [109:0] w12;
    always @(posedge clk) w12 <= {w11[6:0], w11[109:7]};
    assign dut_o[564 +: 47] = w12[46:0];
    reg [109:0] w13;
    always @(posedge clk) w13 <= {w12[6:0], w12[109:7]};
    assign dut_o[611 +: 47] = w13[46:0];
    reg [109:0] w14;
    always @(posedge clk) w14 <= {w13[6:0], w13[109:7]};
    assign dut_o[658 +: 47] = w14[46:0];
    reg [109:0] w15;
    always @(posedge clk) w15 <= {w14[6:0], w14[109:7]};
    assign dut_o[705 +: 47] = w15[46:0];
    assign dut_o[752 +: 110] = w15;
    wire [863:0] xp0 = {2'b0, dut_o};
    reg  [143:0] xr0;
    genvar xg0;
    for (xg0 = 0; xg0 < 144; xg0 = xg0 + 1) begin : gx0
        always @(posedge clk) xr0[xg0] <= ^xp0[xg0*6 +: 6];
    end
    wire [143:0] xp1 = xr0;
    reg  [23:0] xr1;
    genvar xg1;
    for (xg1 = 0; xg1 < 24; xg1 = xg1 + 1) begin : gx1
        always @(posedge clk) xr1[xg1] <= ^xp1[xg1*6 +: 6];
    end
    wire [23:0] xp2 = xr1;
    reg  [3:0] xr2;
    genvar xg2;
    for (xg2 = 0; xg2 < 4; xg2 = xg2 + 1) begin : gx2
        always @(posedge clk) xr2[xg2] <= ^xp2[xg2*6 +: 6];
    end
    wire [5:0] xp3 = {2'b0, xr2};
    reg  [0:0] xr3;
    genvar xg3;
    for (xg3 = 0; xg3 < 1; xg3 = xg3 + 1) begin : gx3
        always @(posedge clk) xr3[xg3] <= ^xp3[xg3*6 +: 6];
    end
    always @(posedge clk) dout <= xr3;
endmodule
