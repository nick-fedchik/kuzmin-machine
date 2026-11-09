`timescale 1ns/1ps

module kpol_txn_gate_tb;
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
    logic [DATA_WIDTH-1:0] state_o;
    logic committed_o;
    logic rejected_o;
    logic rejected_input_o;
    logic rejected_invariant_o;
    logic changed_o;
    logic hazard_observed_o;
    logic unknown_hazard_o;

    always #5 clk_i = ~clk_i;

    kpol_txn_gate #(
        .DATA_WIDTH(DATA_WIDTH),
        .RESET_VALUE('0)
    ) dut (.*);

    task automatic check_event(
        input logic [DATA_WIDTH-1:0] candidate,
        input logic candidate_known,
        input logic assumption_known,
        input logic assumption_true,
        input logic invariant_known,
        input logic invariant_true,
        input logic hazard_known,
        input logic hazard_true,
        input logic [DATA_WIDTH-1:0] expected_state,
        input logic expected_commit,
        input logic expected_rejected_input,
        input logic expected_rejected_invariant,
        input logic expected_changed,
        input logic expected_hazard,
        input logic expected_unknown_hazard
    );
        begin
            @(negedge clk_i);
            event_valid_i = 1'b1;
            candidate_value_i = candidate;
            candidate_known_i = candidate_known;
            assumption_known_i = assumption_known;
            assumption_true_i = assumption_true;
            invariant_known_i = invariant_known;
            invariant_true_i = invariant_true;
            hazard_known_i = hazard_known;
            hazard_true_i = hazard_true;

            @(posedge clk_i);
            #1;
            if (state_o !== expected_state
                || committed_o !== expected_commit
                || rejected_o !== (expected_rejected_input || expected_rejected_invariant)
                || rejected_input_o !== expected_rejected_input
                || rejected_invariant_o !== expected_rejected_invariant
                || changed_o !== expected_changed
                || hazard_observed_o !== expected_hazard
                || unknown_hazard_o !== expected_unknown_hazard) begin
                $fatal(1, "unexpected transaction result: state=%0d", state_o);
            end

            event_valid_i = 1'b0;
            @(posedge clk_i);
            #1;
            if (committed_o || rejected_o || changed_o || hazard_observed_o || unknown_hazard_o) begin
                $fatal(1, "transaction outputs must be one-cycle pulses");
            end
        end
    endtask

    initial begin
        repeat (2) @(posedge clk_i);
        #1;
        if (state_o !== '0) $fatal(1, "reset state was not initialized");
        rst_ni = 1'b1;

        check_event(32'd10, 1, 1, 1, 1, 1, 1, 0,
                    32'd10, 1, 0, 0, 1, 0, 0);
        check_event(32'd20, 1, 1, 0, 1, 1, 1, 1,
                    32'd10, 0, 1, 0, 0, 1, 0);
        check_event(32'd20, 1, 0, 0, 1, 1, 1, 0,
                    32'd10, 0, 1, 0, 0, 0, 0);
        check_event(32'd20, 1, 1, 1, 1, 0, 0, 0,
                    32'd10, 0, 0, 1, 0, 0, 1);
        check_event(32'd20, 1, 1, 1, 0, 0, 1, 0,
                    32'd10, 0, 0, 1, 0, 0, 0);
        check_event(32'd10, 1, 1, 1, 1, 1, 1, 0,
                    32'd10, 1, 0, 0, 0, 0, 0);
        check_event(32'd30, 0, 1, 1, 1, 1, 1, 0,
                    32'd10, 0, 1, 0, 0, 0, 0);

        $display("PASS: KPOL single-event transaction gate");
        $finish;
    end
endmodule
