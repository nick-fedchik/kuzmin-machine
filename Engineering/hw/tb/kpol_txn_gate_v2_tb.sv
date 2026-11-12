`timescale 1ns/1ps

module kpol_txn_gate_v2_tb;
    localparam integer DATA_WIDTH = 32;

    logic clk_i = 1'b0;
    logic rst_ni = 1'b0;
    logic event_valid_i = 1'b0;
    logic candidate_known_i = 1'b0;
    logic [DATA_WIDTH-1:0] candidate_value_i = '0;
    logic assumption_known_i = 1'b0;
    logic assumption_true_i = 1'b0;
    logic invariant_known_i = 1'b0;
    logic invariant_true_i = 1'b0;
    logic hazard_known_i = 1'b0;
    logic hazard_true_i = 1'b0;
    logic alert_known_i = 1'b0;
    logic alert_true_i = 1'b0;

    logic [DATA_WIDTH-1:0] state_o;
    logic committed_o;
    logic rejected_o;
    logic rejected_input_o;
    logic rejected_invariant_o;
    logic rejected_hazard_o;
    logic changed_o;
    logic hazard_observed_o;
    logic hazard_blocked_o;
    logic unknown_hazard_o;
    logic alert_observed_o;

    always #5 clk_i = ~clk_i; // 100 MHz

    // DUT з увімкненим Fail-Closed режимом для Hazard
    kpol_txn_gate_v2 #(
        .DATA_WIDTH(DATA_WIDTH),
        .RESET_VALUE('0),
        .FAIL_CLOSED_HAZARDS(1'b1)
    ) dut (.*);

    task automatic apply_event(
        input logic [DATA_WIDTH-1:0] cand,
        input logic cand_k,
        input logic assump_k, assump_t,
        input logic inv_k, inv_t,
        input logic haz_k, haz_t,
        input logic alrt_k, alrt_t
    );
        begin
            @(negedge clk_i);
            event_valid_i       = 1'b1;
            candidate_value_i   = cand;
            candidate_known_i   = cand_k;
            assumption_known_i  = assump_k;
            assumption_true_i   = assump_t;
            invariant_known_i   = inv_k;
            invariant_true_i    = inv_t;
            hazard_known_i      = haz_k;
            hazard_true_i       = haz_t;
            alert_known_i       = alrt_k;
            alert_true_i        = alrt_t;

            @(posedge clk_i);
            #1;
            event_valid_i = 1'b0;
        end
    endtask

    initial begin
        repeat (2) @(posedge clk_i);
        #1;
        rst_ni = 1'b1;

        $display("=== START kpol_txn_gate_v2_tb (KPOL v0.2) ===");

        // Тест 1: Номінальний успішний коміт
        $display("[TEST 1] Nominal Commit...");
        apply_event(32'd100, 1, 1, 1, 1, 1, 1, 0, 1, 0);
        if (state_o !== 32'd100 || committed_o !== 1'b1 || rejected_o !== 1'b0) begin
            $fatal(1, "[FAIL] Test 1: state=%0d, committed=%b", state_o, committed_o);
        end
        $display("  -> PASS: state=%0d, committed=%b", state_o, committed_o);

        // Тест 2: Alert спостереження (НЕ блокує коміт)
        $display("[TEST 2] Alert Observation (Must NOT block commit)...");
        apply_event(32'd200, 1, 1, 1, 1, 1, 1, 0, 1, 1);
        if (state_o !== 32'd200 || committed_o !== 1'b1 || alert_observed_o !== 1'b1) begin
            $fatal(1, "[FAIL] Test 2: state=%0d, alert=%b", state_o, alert_observed_o);
        end
        $display("  -> PASS: state=%0d, alert_observed=%b", state_o, alert_observed_o);

        // Тест 3: Hazard Fail-Closed блокування (ПОВИННО заблокувати коміт)
        $display("[TEST 3] Hazard Interlock (MUST block commit)...");
        apply_event(32'd999, 1, 1, 1, 1, 1, 1, 1, 1, 0);
        if (state_o !== 32'd200 || committed_o !== 1'b0 || rejected_hazard_o !== 1'b1 || hazard_blocked_o !== 1'b1) begin
            $fatal(1, "[FAIL] Test 3: Hazard did NOT block commit! state=%0d, comm=%b", state_o, committed_o);
        end
        $display("  -> PASS: state preserved=%0d, rejected_hazard=%b, hazard_blocked=%b",
                 state_o, rejected_hazard_o, hazard_blocked_o);

        // Тест 4: Unknown Hazard (стан невідомий -> Fail-Closed замок)
        $display("[TEST 4] Unknown Hazard (MUST block commit on Unknown)...");
        apply_event(32'd888, 1, 1, 1, 1, 1, 0, 0, 1, 0);
        if (state_o !== 32'd200 || committed_o !== 1'b0 || unknown_hazard_o !== 1'b1 || rejected_hazard_o !== 1'b1) begin
            $fatal(1, "[FAIL] Test 4: Unknown hazard did NOT block commit! state=%0d", state_o);
        end
        $display("  -> PASS: unknown_hazard=%b, rejected_hazard=%b", unknown_hazard_o, rejected_hazard_o);

        // Тест 5: Порушення Assumption
        $display("[TEST 5] Assumption Violation...");
        apply_event(32'd300, 1, 1, 0, 1, 1, 1, 0, 1, 0);
        if (state_o !== 32'd200 || rejected_input_o !== 1'b1 || committed_o !== 1'b0) begin
            $fatal(1, "[FAIL] Test 5 failed");
        end
        $display("  -> PASS: rejected_input=%b", rejected_input_o);

        // Тест 6: Порушення Invariant
        $display("[TEST 6] Invariant Violation...");
        apply_event(32'd400, 1, 1, 1, 1, 0, 1, 0, 1, 0);
        if (state_o !== 32'd200 || rejected_invariant_o !== 1'b1 || committed_o !== 1'b0) begin
            $fatal(1, "[FAIL] Test 6 failed");
        end
        $display("  -> PASS: rejected_invariant=%b", rejected_invariant_o);

        $display("=== ALL TESTS PASSED FOR KPOL v0.2 GATE ===");
        $finish;
    end
endmodule
