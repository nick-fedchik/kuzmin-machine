// AV-04: formal property harness for kpol_txn_gate.sv (yosys + yosys-smtbmc).
// Properties are pre-registered in the AV plan, sec. 4.2 (P1..P5).
// The DUT is instantiated unmodified; the harness only observes it.
//
// Two-cycle relational style: p_* registers hold the inputs/state sampled at
// the previous clock edge, so every property compares the registered outputs
// with what the KPOL decision rule demands for those inputs.
//
// `SPEC_POL_HAZARD_BLOCKS` adds the stricter requirement from
// Problem-Oriented-Language-Specification (lines 75, 94): a known, true
// hazard must block commit. The current RTL follows KPOL Draft v0.1 and is
// expected to FAIL this extra property; it documents the spec conflict.

module av04_gate_formal #(
    parameter integer W = 8,
    // non-zero, non-all-ones reset value so that a "reset to 0" bug is visible
    parameter logic [W-1:0] RV = {{(W-2){1'b1}}, 2'b10}
) (
    input logic         clk,
    input logic         rst_ni,
    input logic         event_valid_i,
    input logic         candidate_known_i,
    input logic [W-1:0] candidate_value_i,
    input logic         assumption_known_i,
    input logic         assumption_true_i,
    input logic         invariant_known_i,
    input logic         invariant_true_i,
    input logic         hazard_known_i,
    input logic         hazard_true_i
);
    logic [W-1:0] state;
    logic committed, rejected, rej_in, rej_inv, changed, hz_obs, hz_unk;

    kpol_txn_gate #(.DATA_WIDTH(W), .RESET_VALUE(RV)) dut (
        .clk_i(clk), .rst_ni(rst_ni),
        .event_valid_i(event_valid_i),
        .candidate_known_i(candidate_known_i),
        .candidate_value_i(candidate_value_i),
        .assumption_known_i(assumption_known_i),
        .assumption_true_i(assumption_true_i),
        .invariant_known_i(invariant_known_i),
        .invariant_true_i(invariant_true_i),
        .hazard_known_i(hazard_known_i),
        .hazard_true_i(hazard_true_i),
        .state_o(state),
        .committed_o(committed),
        .rejected_o(rejected),
        .rejected_input_o(rej_in),
        .rejected_invariant_o(rej_inv),
        .changed_o(changed),
        .hazard_observed_o(hz_obs),
        .unknown_hazard_o(hz_unk)
    );

    logic         past_valid = 1'b0;
    logic         p_rst, p_ev, p_ck, p_ak, p_at, p_ik, p_it, p_hk, p_ht;
    logic [W-1:0] p_cv, p_state;

    always @(posedge clk) begin
        past_valid <= 1'b1;
        p_rst   <= rst_ni;
        p_ev    <= event_valid_i;
        p_ck    <= candidate_known_i;
        p_cv    <= candidate_value_i;
        p_ak    <= assumption_known_i;
        p_at    <= assumption_true_i;
        p_ik    <= invariant_known_i;
        p_it    <= invariant_true_i;
        p_hk    <= hazard_known_i;
        p_ht    <= hazard_true_i;
        p_state <= state;
    end

    wire p_input_ok = p_ck & p_ak & p_at;
    wire p_inv_ok   = p_ik & p_it;
    wire p_commit   = p_ev & p_input_ok & p_inv_ok;
    wire active     = past_valid & p_rst & rst_ni;

    always @(*) begin
        if (active) begin
            // P1: commit <=> event_valid & all knowns & assumption & invariant
            P1_commit_iff:   assert (committed == p_commit);
            // P2: commit/reject mutually exclusive; exactly one on event_valid
            P2_exclusive:    assert (!(committed && rejected));
            P2_exactly_one:  assert ((committed | rejected) == p_ev);
            P2_reason_input: assert (rej_in  == (p_ev & ~p_input_ok));
            P2_reason_inv:   assert (rej_inv == (p_ev &  p_input_ok & ~p_inv_ok));
            P2_reason_or:    assert (rejected == (rej_in | rej_inv));
            // P3: state changes only on commit, and then takes the candidate
            P3_hold:         assert (committed || state == p_state);
            P3_take:         assert (!committed || state == p_cv);
            P3_changed:      assert (changed == (committed && (p_cv != p_state)));
            // P5: unknown hazard is flagged; known hazard is observed
            P5_unknown:      assert (hz_unk == (p_ev & ~p_hk));
            P5_observed:     assert (hz_obs == (p_ev & p_hk & p_ht));
`ifdef SPEC_POL_HAZARD_BLOCKS
            // POL spec: a known true hazard must forbid commit
            PX_hazard_blocks: assert (!(committed && p_hk && p_ht));
`endif
            // non-vacuity: each decision outcome is reachable
            C_commit:        cover (committed);
            C_commit_change: cover (committed && changed);
            C_rej_input:     cover (rej_in);
            C_rej_inv:       cover (rej_inv);
            C_unknown_hz:    cover (hz_unk);
            C_commit_hazard: cover (committed && hz_obs);
        end
        // P4: reset (async2sync model) yields RESET_VALUE and quiet flags
        if (!rst_ni || (past_valid && !p_rst)) begin
            P4_reset_state:  assert (state == RV);
            P4_reset_flags:  assert (!committed && !rejected && !rej_in && !rej_inv
                                     && !changed && !hz_obs && !hz_unk);
        end
        if (past_valid && !p_rst && rst_ni) begin
            C_reset_release: cover (state == RV);
        end
    end
endmodule
