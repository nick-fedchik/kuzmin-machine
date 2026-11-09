`timescale 1ns/1ps

module kpol_txn_gate #(
    parameter integer DATA_WIDTH = 32,
    parameter logic [DATA_WIDTH-1:0] RESET_VALUE = '0
) (
    input  logic                   clk_i,
    input  logic                   rst_ni,
    input  logic                   event_valid_i,
    input  logic                   candidate_known_i,
    input  logic [DATA_WIDTH-1:0]  candidate_value_i,
    input  logic                   assumption_known_i,
    input  logic                   assumption_true_i,
    input  logic                   invariant_known_i,
    input  logic                   invariant_true_i,
    input  logic                   hazard_known_i,
    input  logic                   hazard_true_i,
    output logic [DATA_WIDTH-1:0]  state_o,
    output logic                   committed_o,
    output logic                   rejected_o,
    output logic                   rejected_input_o,
    output logic                   rejected_invariant_o,
    output logic                   changed_o,
    output logic                   hazard_observed_o,
    output logic                   unknown_hazard_o
);
    logic input_ok;
    logic invariant_ok;

    assign input_ok = candidate_known_i && assumption_known_i && assumption_true_i;
    assign invariant_ok = invariant_known_i && invariant_true_i;

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state_o              <= RESET_VALUE;
            committed_o          <= 1'b0;
            rejected_o           <= 1'b0;
            rejected_input_o     <= 1'b0;
            rejected_invariant_o <= 1'b0;
            changed_o            <= 1'b0;
            hazard_observed_o    <= 1'b0;
            unknown_hazard_o     <= 1'b0;
        end else begin
            committed_o          <= 1'b0;
            rejected_o           <= 1'b0;
            rejected_input_o     <= 1'b0;
            rejected_invariant_o <= 1'b0;
            changed_o            <= 1'b0;
            hazard_observed_o    <= 1'b0;
            unknown_hazard_o     <= 1'b0;

            if (event_valid_i === 1'b1) begin
                if (hazard_known_i !== 1'b1 || (hazard_true_i !== 1'b0 && hazard_true_i !== 1'b1)) begin
                    unknown_hazard_o <= 1'b1;
                end else if (hazard_true_i === 1'b1) begin
                    hazard_observed_o <= 1'b1;
                end

                if (input_ok !== 1'b1) begin
                    rejected_o       <= 1'b1;
                    rejected_input_o <= 1'b1;
                end else if (invariant_ok !== 1'b1) begin
                    rejected_o           <= 1'b1;
                    rejected_invariant_o <= 1'b1;
                end else begin
                    state_o     <= candidate_value_i;
                    committed_o <= 1'b1;
                    changed_o   <= candidate_value_i != state_o;
                end
            end
        end
    end
endmodule
