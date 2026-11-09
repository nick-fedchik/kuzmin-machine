`timescale 1ns/1ps
module av08_top (input wire clk, input wire rst_btn, input wire din, output reg dout);
    reg [1:0] rsync;
    always @(posedge clk) rsync <= {rsync[0], ~rst_btn};
    wire rst_n = rsync[1];
    reg [109:0] sr;
    always @(posedge clk) sr <= {sr[108:0], din};
    wire [485:0] dut_o;
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
    assign dut_o[376 +: 110] = w7;
    wire [485:0] xp0 = dut_o;
    reg  [80:0] xr0;
    genvar xg0;
    for (xg0 = 0; xg0 < 81; xg0 = xg0 + 1) begin : gx0
        always @(posedge clk) xr0[xg0] <= ^xp0[xg0*6 +: 6];
    end
    wire [83:0] xp1 = {3'b0, xr0};
    reg  [13:0] xr1;
    genvar xg1;
    for (xg1 = 0; xg1 < 14; xg1 = xg1 + 1) begin : gx1
        always @(posedge clk) xr1[xg1] <= ^xp1[xg1*6 +: 6];
    end
    wire [17:0] xp2 = {4'b0, xr1};
    reg  [2:0] xr2;
    genvar xg2;
    for (xg2 = 0; xg2 < 3; xg2 = xg2 + 1) begin : gx2
        always @(posedge clk) xr2[xg2] <= ^xp2[xg2*6 +: 6];
    end
    wire [5:0] xp3 = {3'b0, xr2};
    reg  [0:0] xr3;
    genvar xg3;
    for (xg3 = 0; xg3 < 1; xg3 = xg3 + 1) begin : gx3
        always @(posedge clk) xr3[xg3] <= ^xp3[xg3*6 +: 6];
    end
    always @(posedge clk) dout <= xr3;
endmodule
