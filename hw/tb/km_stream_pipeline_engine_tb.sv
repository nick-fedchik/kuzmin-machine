// ============================================================================
// File: km_stream_pipeline_engine_tb.sv
// Description: Testbench for km_stream_pipeline_engine (EXP-10)
// ============================================================================

`timescale 1ns / 1ps

module km_stream_pipeline_engine_tb;

    reg clk;
    reg rst_n;
    reg start;
    reg [1:0] mode;
    reg [15:0] count_cfg;

    wire busy;
    wire done;
    wire pass;
    wire [31:0] cycle_count;
    wire [15:0] processed_count;
    wire [15:0] clamped_count;
    wire [31:0] checksum;
    wire [31:0] last_val;

    km_stream_pipeline_engine #(
        .BURST_SIZE(1024)
    ) dut (
        .clk_i(clk),
        .rst_ni(rst_n),
        .start_i(start),
        .mode_i(mode),
        .count_cfg_i(count_cfg),
        .busy_o(busy),
        .done_o(done),
        .pass_o(pass),
        .cycle_count_o(cycle_count),
        .processed_count_o(processed_count),
        .clamped_count_o(clamped_count),
        .checksum_o(checksum),
        .last_val_o(last_val)
    );

    always #5 clk = ~clk; // 100 MHz clock (10 ns period)

    initial begin
        clk = 0;
        rst_n = 0;
        start = 0;
        mode = 2'b00;
        count_cfg = 16'd0;

        #20 rst_n = 1;
        #20;

        // Test 1: Normal burst (64 samples)
        $display("[TB] Starting Test 1: Normal burst (64 samples)");
        count_cfg = 16'd64;
        mode = 2'b00;
        start = 1;
        #10 start = 0;

        wait(done);
        #10;
        $display("[TB] Test 1 Done: cycles=%0d, processed=%0d, clamped=%0d, pass=%0b",
                 cycle_count, processed_count, clamped_count, pass);
        if (!pass || processed_count != 64 || clamped_count != 0) begin
            $display("[TB] ERROR: Test 1 failed!");
            $fatal(1);
        end

        #50;

        // Test 2: Glitch burst (1024 samples)
        $display("[TB] Starting Test 2: Glitch injection burst (1024 samples)");
        count_cfg = 16'd1024;
        mode = 2'b01;
        start = 1;
        #10 start = 0;

        wait(done);
        #10;
        $display("[TB] Test 2 Done: cycles=%0d, processed=%0d, clamped=%0d, checksum=%0h, pass=%0b",
                 cycle_count, processed_count, clamped_count, checksum, pass);
        if (!pass || processed_count != 1024 || clamped_count == 0 || checksum != 32'h1eb2521) begin
            $display("[TB] ERROR: Test 2 failed: pass=%0d, processed=%0d, clamped=%0d, checksum=0x%0h (exp 0x1eb2521)",
                     pass, processed_count, clamped_count, checksum);
            $fatal(1);
        end

        $display("[TB] ALL EXP-10 SIMULATION TESTS PASSED!");
        $finish;
    end

endmodule
