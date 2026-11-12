// S3-62: Formal property harness for KPOL v0.2 Fail-Closed Transaction Gate (kpol_txn_gate_v2)
// Proves requirement S3, hypothesis H6, and gates Issue #62, Issue #18.
//
// Properties P1..P10 verify fail-closed invariant protection, mutual exclusion,
// zero side-effects on rejection, and exact causality.
// Cover properties C1..C6 witness non-vacuity for every reachable operational mode.

`timescale 1ns/1ps

module s3_formal (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        event_valid,
    input  logic        candidate_known,
    input  logic [31:0] candidate_value,
    input  logic        assumption_known,
    input  logic        assumption_true,
    input  logic        invariant_known,
    input  logic        invariant_true,
    input  logic        hazard_known,
    input  logic        hazard_true,
    input  logic        alert_known,
    input  logic        alert_true
);
    logic [31:0] state;
    logic        committed;
    logic        rejected;
    logic        rejected_input;
    logic        rejected_invariant;
    logic        rejected_hazard;
    logic        changed;
    logic        hazard_observed;
    logic        hazard_blocked;
    logic        unknown_hazard;
    logic        alert_observed;

    kpol_txn_gate_v2 #(
        .DATA_WIDTH(32),
        .RESET_VALUE(32'h0000_0000),
        .FAIL_CLOSED_HAZARDS(1'b1)
    ) dut (
        .clk_i(clk),
        .rst_ni(rst_n),
        .event_valid_i(event_valid),
        .candidate_known_i(candidate_known),
        .candidate_value_i(candidate_value),
        .assumption_known_i(assumption_known),
        .assumption_true_i(assumption_true),
        .invariant_known_i(invariant_known),
        .invariant_true_i(invariant_true),
        .hazard_known_i(hazard_known),
        .hazard_true_i(hazard_true),
        .alert_known_i(alert_known),
        .alert_true_i(alert_true),
        .state_o(state),
        .committed_o(committed),
        .rejected_o(rejected),
        .rejected_input_o(rejected_input),
        .rejected_invariant_o(rejected_invariant),
        .rejected_hazard_o(rejected_hazard),
        .changed_o(changed),
        .hazard_observed_o(hazard_observed),
        .hazard_blocked_o(hazard_blocked),
        .unknown_hazard_o(unknown_hazard),
        .alert_observed_o(alert_observed)
    );

    logic past_valid = 1'b0;
    logic p_rst;
    logic p_event_valid;
    logic p_cand_known, p_assump_known, p_assump_true;
    logic p_inv_known, p_inv_true;
    logic p_haz_known, p_haz_true;
    logic [31:0] p_cand_val;
    logic [31:0] p_state;

    wire p_input_ok   = p_cand_known && p_assump_known && p_assump_true;
    wire p_inv_ok     = p_inv_known && p_inv_true;
    wire p_hazard_ok  = p_haz_known && !p_haz_true; // FAIL_CLOSED_HAZARDS = 1

    always @(posedge clk) begin
        past_valid     <= 1'b1;
        p_rst          <= !rst_n;
        p_event_valid  <= event_valid;
        p_cand_known   <= candidate_known;
        p_assump_known <= assumption_known;
        p_assump_true  <= assumption_true;
        p_inv_known    <= invariant_known;
        p_inv_true     <= invariant_true;
        p_haz_known    <= hazard_known;
        p_haz_true     <= hazard_true;
        p_cand_val     <= candidate_value;
        p_state        <= state;
    end

    // ---- Assumptions on Initial State ----
    always @(*) begin
        if (!past_valid) begin
            assume (!rst_n);
        end
    end

    // ---- Formal Safety Properties (P1..P10) ----
    always @(*) begin
        if (past_valid && !p_rst && rst_n) begin
            // P1: Fail-Closed on Hazard: NEVER commit if hazard is active or unknown
            P1_fail_closed_hazard:
                assert (!committed || p_hazard_ok);

            // P2: Fail-Closed on Invariant: NEVER commit if invariant is violated or unknown
            P2_fail_closed_invariant:
                assert (!committed || p_inv_ok);

            // P3: Fail-Closed on Input: NEVER commit if candidate or assumption is invalid
            P3_fail_closed_input:
                assert (!committed || p_input_ok);

            // P4: Strict Causality: NEVER commit without an event in previous cycle
            P4_causality_event:
                assert (!committed || p_event_valid);

            // P5: Mutual Exclusion: committed and rejected can NEVER be asserted simultaneously
            P5_mutual_exclusion:
                assert (!(committed && rejected));

            // P6: Deterministic Rejection on Hazard: if event arrives with hazard, MUST reject with rejected_hazard
            P6_rejection_hazard:
                assert (!(p_event_valid && p_input_ok && p_inv_ok && !p_hazard_ok) ||
                        (rejected && rejected_hazard && hazard_blocked));

            // P7: Deterministic Rejection on Invariant: if event arrives with inv violation, MUST reject with rejected_invariant
            P7_rejection_invariant:
                assert (!(p_event_valid && p_input_ok && !p_inv_ok) ||
                        (rejected && rejected_invariant));

            // P8: Zero Side-Effect State Integrity: State NEVER changes on rejection or idle
            P8_state_integrity:
                assert (!(rejected || !p_event_valid) || (state == p_state));

            // P9: State Update on Commit: State MUST equal candidate_value on commit
            P9_state_commit:
                assert (!committed || (state == p_cand_val));
        end

        if (past_valid && p_rst) begin
            P10_reset:
                assert (!committed && !rejected && state == 32'h0);
        end
    end

    // ---- Coverage Witnesses (Non-vacuity C1..C6) ----
    always @(*) begin
        if (past_valid && !p_rst && rst_n) begin
            C1_commit:         cover (committed);
            C2_reject_hazard:  cover (rejected_hazard && hazard_blocked);
            C3_reject_inv:     cover (rejected_invariant);
            C4_reject_input:   cover (rejected_input);
            C5_alert_observed: cover (alert_observed);
            C6_state_changed:  cover (changed);
        end
    end
endmodule
