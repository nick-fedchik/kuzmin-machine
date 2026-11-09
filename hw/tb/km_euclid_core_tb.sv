`timescale 1ns/1ps

module km_euclid_core_tb;
    logic        clk;
    logic        rst_n;
    logic        start;
    logic [31:0] a_init;
    logic [31:0] b_init;

    wire        busy;
    wire        done;
    wire        error;
    wire [31:0] result;
    wire [15:0] iterations;
    wire [31:0] cycle_count;
    wire [31:0] concept_a;
    wire [31:0] concept_b;

    km_euclid_core #(
        .DATA_WIDTH(32)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .start_i(start),
        .a_init_i(a_init),
        .b_init_i(b_init),
        .busy_o(busy),
        .done_o(done),
        .error_o(error),
        .result_o(result),
        .iterations_o(iterations),
        .cycle_count_o(cycle_count),
        .concept_a_o(concept_a),
        .concept_b_o(concept_b)
    );

    always #5 clk = ~clk; // 100 MHz clock (10 ns period)

    initial begin
        clk = 0;
        rst_n = 0;
        start = 0;
        a_init = 0;
        b_init = 0;

        #20 rst_n = 1;
        #10;

        // Test 1: Nod(120, 6)
        $display("[TB] Starting Test 1: Nod(120, 6)...");
        a_init = 32'd120;
        b_init = 32'd6;
        start  = 1'b1;
        #10;
        start  = 1'b0;

        wait(done);
        #10;
        $display("[TB] Test 1 Completed:");
        $display("     Result: %0d (Expected: 6)", result);
        $display("     Iterations: %0d (Expected: 19)", iterations);
        $display("     Cycles: %0d (Expected: 58)", cycle_count);

        if (result != 32'd6 || iterations != 16'd19 || cycle_count != 32'd58) begin
            $display("[FAIL] Test 1 assertion failed!");
            $fatal(1);
        end else begin
            $display("[PASS] Test 1 passed with flying colors!");
        end

        // Test 2: Nod(1071, 462) -> 21
        #50;
        $display("[TB] Starting Test 2: Nod(1071, 462)...");
        a_init = 32'd1071;
        b_init = 32'd462;
        start  = 1'b1;
        #10;
        start  = 1'b0;

        wait(done);
        #10;
        $display("[TB] Test 2 Completed: Result = %0d, Iterations = %0d, Cycles = %0d",
                 result, iterations, cycle_count);
        if (result != 32'd21) begin
            $display("[FAIL] Test 2 assertion failed!");
            $fatal(1);
        end

        $display("[ALL TESTS PASSED]");
        $finish;
    end

endmodule
