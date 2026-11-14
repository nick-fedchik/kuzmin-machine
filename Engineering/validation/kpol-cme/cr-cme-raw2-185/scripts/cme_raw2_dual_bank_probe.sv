// Synthesis probe only (not part of CFG-P RTL):
// Models an Even/Odd dual-bank 128-concept x 32-byte (4096 B) memory
// with 32-bit Port A (AXI loader) and 64-bit Port B ({W_odd, W_even} pairs).
module cme_raw2_dual_bank_probe (
    input  logic        clk_i,
    // Port A: 32-bit indirect AXI access (1024 words = 4096 B)
    input  logic        a_we_i,
    input  logic [9:0]  a_addr_i,
    input  logic [31:0] a_wdata_i,
    output logic [31:0] a_rdata_o,
    // Port B: 64-bit pair access (512 pairs = 128 concepts x 4 pairs)
    input  logic        b_we_i,
    input  logic [8:0]  b_addr_i,
    input  logic [63:0] b_wdata_i,
    output logic [63:0] b_rdata_o
);
    (* ram_style = "block" *) reg [31:0] bank_even [0:511];
    (* ram_style = "block" *) reg [31:0] bank_odd  [0:511];

    logic [31:0] a_rdata_even, a_rdata_odd;
    logic        a_bank_sel_q;

    always_ff @(posedge clk_i) begin
        a_bank_sel_q <= a_addr_i[0];
        if (a_we_i && !a_addr_i[0]) begin
            bank_even[a_addr_i[9:1]] <= a_wdata_i;
        end
        if (a_we_i && a_addr_i[0]) begin
            bank_odd[a_addr_i[9:1]] <= a_wdata_i;
        end
        a_rdata_even <= bank_even[a_addr_i[9:1]];
        a_rdata_odd  <= bank_odd[a_addr_i[9:1]];
    end

    assign a_rdata_o = a_bank_sel_q ? a_rdata_odd : a_rdata_even;

    always_ff @(posedge clk_i) begin
        if (b_we_i) begin
            bank_even[b_addr_i] <= b_wdata_i[31:0];
            bank_odd[b_addr_i]  <= b_wdata_i[63:32];
        end
        b_rdata_o[31:0]  <= bank_even[b_addr_i];
        b_rdata_o[63:32] <= bank_odd[b_addr_i];
    end
endmodule
