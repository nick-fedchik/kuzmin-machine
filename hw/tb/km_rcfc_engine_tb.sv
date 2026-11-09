// ============================================================================
// Тестбенч для km_rcfc_engine.sv (TC-01 .. TC-04 Stress Suite)
// Файл: km_rcfc_engine_tb.sv
// ============================================================================
`timescale 1ns / 1ps

module km_rcfc_engine_tb;

    logic        clk;
    logic        rst_n;
    logic        start;
    logic [2:0]  cmd;
    logic [7:0]  delay_param;
    logic [5:0]  slot_sel;

    wire         busy;
    wire         done;
    wire         tc01_pass;
    wire         tc02_pass;
    wire         tc03_pass;
    wire         tc04_pass;
    wire         timeout_deadlock_error;
    wire         event_drop_error;
    wire [3:0]   current_tc;
    wire [15:0]  events_processed;
    wire [31:0]  cycle_count;
    wire [15:0]  events_enqueued;
    wire [15:0]  events_dropped;
    wire [31:0]  result;
    wire [2:0]   slot_state;
    wire [7:0]   slot_wait_cycles;
    wire [15:0]  slot_payload_lo;

    km_rcfc_engine #(
        .NUM_SLOTS(64),
        .QUEUE_DEPTH(64),
        .MAX_WAIT_CYCLES(256),
        .DATA_WIDTH(32)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .start_i(start),
        .cmd_i(cmd),
        .delay_param_i(delay_param),
        .slot_sel_i(slot_sel),
        .busy_o(busy),
        .done_o(done),
        .tc01_pass_o(tc01_pass),
        .tc02_pass_o(tc02_pass),
        .tc03_pass_o(tc03_pass),
        .tc04_pass_o(tc04_pass),
        .timeout_deadlock_error_o(timeout_deadlock_error),
        .event_drop_error_o(event_drop_error),
        .current_tc_o(current_tc),
        .events_processed_o(events_processed),
        .cycle_count_o(cycle_count),
        .events_enqueued_o(events_enqueued),
        .events_dropped_o(events_dropped),
        .result_o(result),
        .slot_state_o(slot_state),
        .slot_wait_cycles_o(slot_wait_cycles),
        .slot_payload_lo_o(slot_payload_lo)
    );

    always #5 clk = ~clk; // 100 MHz clock (10 ns period)

    initial begin
        clk         = 0;
        rst_n       = 0;
        start       = 0;
        cmd         = 0;
        delay_param = 0;
        slot_sel    = 0;

        #20;
        rst_n = 1;
        #20;

        $display("=== ТЕСТ 1: TC-01 Event Avalanche (64x) ===");
        cmd = 3'd1;
        start = 1;
        #10;
        start = 0;
        wait(done == 1);
        #10;
        $display("TC-01 Результат: enqueued=%0d, dropped=%0d, processed=%0d, pass=%0d, cycles=%0d, result=%0d",
                 events_enqueued, events_dropped, events_processed, tc01_pass, cycle_count, result);
        if (!tc01_pass || events_dropped != 0 || events_processed != 64 || result != 64) begin
            $fatal(1, "[FAIL] TC-01 failed: pass=%0d, dropped=%0d, processed=%0d, result=%0d",
                   tc01_pass, events_dropped, events_processed, result);
        end

        #20;
        $display("=== ТЕСТ 2: TC-02 All-Core Fallback Stress ===");
        cmd = 3'd2;
        slot_sel = 6'd0;
        start = 1;
        #10;
        start = 0;
        // Перевірка, що слот перейшов у стан FALLBACK (3'd4) під час виконання
        #15;
        if (slot_state !== 3'd4) begin
            $fatal(1, "[FAIL] TC-02: slot 0 did not enter SLOT_FALLBACK (3'd4), got %0d", slot_state);
        end
        wait(done == 1);
        #10;
        $display("TC-02 Результат: result=%0d, pass=%0d, cycles=%0d, timeout_err=%0d",
                 result, tc02_pass, cycle_count, timeout_deadlock_error);
        if (!tc02_pass || result != 150 || timeout_deadlock_error) begin
            $fatal(1, "[FAIL] TC-02 failed!");
        end

        #20;
        $display("=== ТЕСТ 3: TC-03 Producer-Before-Consumer ===");
        cmd = 3'd3;
        start = 1;
        #10;
        start = 0;
        wait(done == 1);
        #10;
        $display("TC-03 Результат: result=%0d, pass=%0d, cycles=%0d", result, tc03_pass, cycle_count);
        if (!tc03_pass || result != 1000) begin
            $fatal(1, "[FAIL] TC-03 failed!");
        end

        #20;
        $display("=== ТЕСТ 4: TC-04 Consumer-Before-Producer ===");
        cmd = 3'd4;
        delay_param = 8'd25; // Затримка 25 тактів
        start = 1;
        #10;
        start = 0;
        wait(done == 1);
        #10;
        $display("TC-04 Результат: result=%0d, pass=%0d, cycles=%0d, timeout_err=%0d",
                 result, tc04_pass, cycle_count, timeout_deadlock_error);
        if (!tc04_pass || result != 100 || timeout_deadlock_error) begin
            $fatal(1, "[FAIL] TC-04 failed!");
        end

        #20;
        $display("=== ТЕСТ 5: Повний запуск Suite (CMD=5) ===");
        cmd = 3'd5;
        start = 1;
        #10;
        start = 0;
        wait(done == 1);
        #10;
        $display("ALL SUITE Результат: tc01=%0d, tc02=%0d, tc03=%0d, tc04=%0d, cycles=%0d",
                 tc01_pass, tc02_pass, tc03_pass, tc04_pass, cycle_count);
        if (!tc01_pass || !tc02_pass || !tc03_pass || !tc04_pass) begin
            $fatal(1, "[FAIL] ALL Suite failed!");
        end

        $display("=== УСІ 4 СТРЕС-ТЕСТИ RCFC УСПІШНО ПРОЙДЕНО В СИМУЛЯЦІЇ ===");
        $finish;
    end

endmodule
