// ============================================================================
// Тестбенч для km_cascade_arbiter_engine.sv (TC-05 .. TC-08 Stress Suite)
// Файл: km_cascade_arbiter_engine_tb.sv
// ============================================================================
`timescale 1ns / 1ps

module km_cascade_arbiter_engine_tb;

    logic        clk;
    logic        rst_n;
    logic        start;
    logic [2:0]  cmd;

    wire         busy;
    wire         done;
    wire         tc05_pass;
    wire         tc06_pass;
    wire         tc07_pass;
    wire         tc08_pass;
    wire         fail_error;
    wire [3:0]   current_tc;
    wire [31:0]  cycle_count;
    wire [31:0]  result0;
    wire [31:0]  result1;

    km_cascade_arbiter_engine #(
        .DATA_WIDTH(32)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .start_i(start),
        .cmd_i(cmd),
        .busy_o(busy),
        .done_o(done),
        .tc05_pass_o(tc05_pass),
        .tc06_pass_o(tc06_pass),
        .tc07_pass_o(tc07_pass),
        .tc08_pass_o(tc08_pass),
        .fail_error_o(fail_error),
        .current_tc_o(current_tc),
        .cycle_count_o(cycle_count),
        .result0_o(result0),
        .result1_o(result1)
    );

    always #5 clk = ~clk;

    initial begin
        clk   = 0;
        rst_n = 0;
        start = 0;
        cmd   = 0;

        #20;
        rst_n = 1;
        #20;

        $display("=== ТЕСТ 1: TC-05 Boundary Transitions of Sign & Size ===");
        cmd = 3'd1;
        start = 1;
        #10;
        start = 0;
        wait(done == 1);
        #10;
        $display("TC-05 Результат: pass=%0d, res0=0x%08X, res1=0x%08X, cycles=%0d, fail_err=%0d",
                 tc05_pass, result0, result1, cycle_count, fail_error);
        if (!tc05_pass || (result0[7:0] !== 8'h80) || (result1 !== 32'hAABB55DD) || fail_error) begin
            $fatal(1, "[FAIL] TC-05 failed: tc05_pass=%0d, res0=0x%08X (exp 0x80), res1=0x%08X (exp 0xAABB55DD), fail_err=%0d",
                   tc05_pass, result0, result1, fail_error);
        end

        #20;
        $display("=== ТЕСТ 2: TC-06 Triple Cascade (Distance -> Speed -> Accel) ===");
        cmd = 3'd2;
        start = 1;
        #10;
        start = 0;
        wait(done == 1);
        #10;
        $display("TC-06 Результат: pass=%0d, accel=%0d, cycles=%0d", tc06_pass, result0, cycle_count);
        if (!tc06_pass || result0 != 20) $fatal(1, "[FAIL] TC-06 failed!");

        #20;
        $display("=== ТЕСТ 3: TC-07 Big Dot Rejection (• = ¬) ===");
        cmd = 3'd3;
        start = 1;
        #10;
        start = 0;
        wait(done == 1);
        #10;
        $display("TC-07 Результат: pass=%0d, safe_val=%0d, cycles=%0d", tc07_pass, result0, cycle_count);
        if (!tc07_pass || result0 != 200) $fatal(1, "[FAIL] TC-07 failed!");

        #20;
        $display("=== ТЕСТ 4: TC-08 Concurrent Write Conflict Arbitration ===");
        cmd = 3'd4;
        start = 1;
        #10;
        start = 0;
        wait(done == 1);
        #10;
        $display("TC-08 Результат: pass=%0d, sum=%0d, cycles=%0d", tc08_pass, result0, cycle_count);
        if (!tc08_pass || result0 != 100) $fatal(1, "[FAIL] TC-08 failed!");

        #20;
        $display("=== ТЕСТ 5: Повний запуск Suite B (CMD=5) ===");
        cmd = 3'd5;
        start = 1;
        #10;
        start = 0;
        wait(done == 1);
        #10;
        $display("ALL SUITE B Результат: tc05=%0d, tc06=%0d, tc07=%0d, tc08=%0d, cycles=%0d",
                 tc05_pass, tc06_pass, tc07_pass, tc08_pass, cycle_count);
        if (!tc05_pass || !tc06_pass || !tc07_pass || !tc08_pass) $fatal(1, "[FAIL] ALL Suite B failed!");

        $display("=== УСІ ТЕСТИ TC-05 .. TC-08 УСПІШНО ПРОЙДЕНО В СИМУЛЯЦІЇ ===");
        $finish;
    end

endmodule
