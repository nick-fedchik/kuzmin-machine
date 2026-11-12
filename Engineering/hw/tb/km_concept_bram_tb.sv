`timescale 1ns/1ps

module km_concept_bram_tb;
    logic        clk;
    logic        rst_n;

    logic [7:0]  a_addr;
    logic [31:0] a_wdata;
    logic [3:0]  a_wstrb;
    logic        a_we;
    wire  [31:0] a_rdata;

    logic [7:0]  b_addr;
    logic [31:0] b_wdata;
    logic [3:0]  b_wstrb;
    logic        b_we;
    wire  [31:0] b_rdata;

    wire         collision;

    km_concept_bram #(
        .NUM_CONCEPTS(64),
        .DATA_WIDTH(32),
        .ADDR_WIDTH(8)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .a_addr_i(a_addr),
        .a_wdata_i(a_wdata),
        .a_wstrb_i(a_wstrb),
        .a_we_i(a_we),
        .a_rdata_o(a_rdata),
        .b_addr_i(b_addr),
        .b_wdata_i(b_wdata),
        .b_wstrb_i(b_wstrb),
        .b_we_i(b_we),
        .b_rdata_o(b_rdata),
        .collision_detected_o(collision)
    );

    always #5 clk = ~clk;

    initial begin
        clk = 0;
        rst_n = 0;
        a_addr = 0; a_wdata = 0; a_wstrb = 0; a_we = 0;
        b_addr = 0; b_wdata = 0; b_wstrb = 0; b_we = 0;

        #20 rst_n = 1;
        #10;

        // Test 1: Write Concept 0 descriptor via Port A
        $display("[TB] Writing Concept 0 descriptor via Port A...");
        @(posedge clk);
        #1;
        a_addr = 8'h00; a_wdata = 32'd120; a_wstrb = 4'hF; a_we = 1;
        @(posedge clk);
        #1;
        a_addr = 8'h01; a_wdata = 32'd0; a_wstrb = 4'hF; a_we = 1;
        @(posedge clk);
        #1;
        a_addr = 8'h02; a_wdata = 32'h00010100; a_wstrb = 4'hF; a_we = 1;
        @(posedge clk);
        #1;
        a_addr = 8'h03; a_wdata = 32'h00000000; a_wstrb = 4'hF; a_we = 1;
        @(posedge clk);
        #1;
        a_we = 0;

        // Test 2: Write Concept 1 descriptor via Port B
        $display("[TB] Writing Concept 1 descriptor via Port B...");
        @(posedge clk);
        #1;
        b_addr = 8'h04; b_wdata = 32'd6; b_wstrb = 4'hF; b_we = 1;
        @(posedge clk);
        #1;
        b_addr = 8'h05; b_wdata = 32'd0; b_wstrb = 4'hF; b_we = 1;
        @(posedge clk);
        #1;
        b_we = 0;

        // Test 3: Read back both concepts simultaneously
        // Port A reads Concept 0 (word 0), Port B reads Concept 1 (word 4)
        @(posedge clk);
        #1;
        a_addr = 8'h00;
        b_addr = 8'h04;
        @(posedge clk);
        #1; // Wait for registered output
        $display("[TB] Read Concept 0 Value LO: %0d (Expected: 120)", a_rdata);
        $display("[TB] Read Concept 1 Value LO: %0d (Expected: 6)", b_rdata);

        if (a_rdata != 32'd120 || b_rdata != 32'd6) begin
            $display("[FAIL] Readback mismatch!");
            $fatal(1);
        end

        // Test 4: Write to upper boundary Concept 63 (words 252..255 / 8'hFC..8'hFF)
        $display("[TB] Writing Concept 63 (boundary test)...");
        @(posedge clk);
        a_addr = 8'hFC; a_wdata = 32'hDEADBEEF; a_wstrb = 4'hF; a_we = 1;
        @(posedge clk);
        a_we = 0;
        @(posedge clk);
        a_addr = 8'hFC;
        @(posedge clk);
        #1;
        $display("[TB] Concept 63 Value: 0x%08X (Expected: 0xDEADBEEF)", a_rdata);
        if (a_rdata != 32'hDEADBEEF) begin
            $display("[FAIL] Boundary Concept 63 failed!");
            $fatal(1);
        end

        // Test 5: Collision detection
        $display("[TB] Testing write collision on same word...");
        @(posedge clk);
        a_addr = 8'h10; a_wdata = 32'hAAAAAAAA; a_wstrb = 4'hF; a_we = 1;
        b_addr = 8'h10; b_wdata = 32'hBBBBBBBB; b_wstrb = 4'hF; b_we = 1;
        @(posedge clk);
        a_we = 0; b_we = 0;
        #1;
        $display("[TB] Collision flag: %b (Expected: 1)", collision);
        if (!collision) begin
            $display("[FAIL] Collision not detected!");
            $fatal(1);
        end

        $display("[ALL BRAM TESTS PASSED]");
        $finish;
    end

endmodule
