// ============================================================================
// File: km_io_trigger_engine_tb.sv
// Description: Testbench for km_io_trigger_engine (EXP-06)
// ============================================================================

`timescale 1ns / 1ps

module km_io_trigger_engine_tb;

    reg clk;
    reg rst_n;
    reg ext_pin;
    wire reactive_out;
    reg start_stim;
    reg clear_stats;
    reg [15:0] burst_count;

    wire busy;
    wire done;
    wire pass;
    wire [15:0] last_latency;
    wire [15:0] min_latency;
    wire [15:0] max_latency;
    wire [31:0] trigger_count;
    wire [63:0] last_timestamp;

    km_io_trigger_engine dut (
        .clk_i(clk),
        .rst_ni(rst_n),
        .ext_pin_i(ext_pin),
        .reactive_out_o(reactive_out),
        .start_stim_i(start_stim),
        .clear_stats_i(clear_stats),
        .burst_count_i(burst_count),
        .busy_o(busy),
        .done_o(done),
        .pass_o(pass),
        .last_latency_o(last_latency),
        .min_latency_o(min_latency),
        .max_latency_o(max_latency),
        .trigger_count_o(trigger_count),
        .last_timestamp_o(last_timestamp)
    );

    always #5 clk = ~clk; // 100 MHz clock (10 ns period)

    initial begin
        clk = 0;
        rst_n = 0;
        ext_pin = 0;
        start_stim = 0;
        clear_stats = 0;
        burst_count = 16'd50;

        #20 rst_n = 1;
        #20;

        // Test 1: Autonomous burst of 50 stimulus triggers
        $display("[TB] Starting Test 1: Autonomous burst of 50 triggers");
        start_stim = 1;
        #10 start_stim = 0;

        wait(done);
        #20;
        $display("[TB] Test 1 Done: pass=%0b, count=%0d, last_lat=%0d, min_lat=%0d, max_lat=%0d",
                 pass, trigger_count, last_latency, min_latency, max_latency);

        if (!pass || trigger_count != 50 || min_latency != 3 || max_latency != 3) begin
            $display("[TB] ERROR: Test 1 failed!");
            $fatal(1);
        end

        #50;

        // Test 2: Physical external pin trigger
        $display("[TB] Starting Test 2: External pin trigger");
        ext_pin = 1;
        #20 ext_pin = 0;
        #50;

        $display("[TB] Test 2 Trigger Count: %0d", trigger_count);
        if (trigger_count != 51) begin
            $display("[TB] ERROR: External pin event not counted!");
            $fatal(1);
        end

        $display("[TB] ALL EXP-06 SIMULATION TESTS PASSED!");
        $finish;
    end

endmodule
