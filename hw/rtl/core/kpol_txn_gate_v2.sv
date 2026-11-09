`timescale 1ns/1ps

/**
 * Модуль kpol_txn_gate_v2:
 * Уніфікований транзакційний шлюз Машини Кузьміна за стандартом KPOL v0.2.
 *
 * Відмінності від v0.1:
 * 1. Строгий захист Fail-Closed при небезпеці (FAIL_CLOSED_HAZARDS = 1):
 *    якщо hazard_true_i == 1 або hazard_known_i == 0 -> транзакція ВІДХИЛЯЄТЬСЯ (committed_o = 0, rejected_hazard_o = 1).
 * 2. Додано незалежний канал спостереження (Alert):
 *    alert_observed_o виставляється суто для телеметрії і НЕ блокує коміт.
 * 3. 1 такт реакції (10.0 нс при 100 МГц), нульовий джитер.
 */

module kpol_txn_gate_v2 #(
    parameter integer DATA_WIDTH = 32,
    parameter logic [DATA_WIDTH-1:0] RESET_VALUE = '0,
    parameter bit FAIL_CLOSED_HAZARDS = 1'b1
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
    input  logic                   alert_known_i,
    input  logic                   alert_true_i,

    output logic [DATA_WIDTH-1:0]  state_o,
    output logic                   committed_o,
    output logic                   rejected_o,
    output logic                   rejected_input_o,
    output logic                   rejected_invariant_o,
    output logic                   rejected_hazard_o,
    output logic                   changed_o,
    output logic                   hazard_observed_o,
    output logic                   hazard_blocked_o,
    output logic                   unknown_hazard_o,
    output logic                   alert_observed_o
);
    logic input_ok;
    logic invariant_ok;
    logic hazard_ok;

    assign input_ok     = candidate_known_i && assumption_known_i && assumption_true_i;
    assign invariant_ok = invariant_known_i && invariant_true_i;
    assign hazard_ok    = !FAIL_CLOSED_HAZARDS || (hazard_known_i && !hazard_true_i);

    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state_o              <= RESET_VALUE;
            committed_o          <= 1'b0;
            rejected_o           <= 1'b0;
            rejected_input_o     <= 1'b0;
            rejected_invariant_o <= 1'b0;
            rejected_hazard_o    <= 1'b0;
            changed_o            <= 1'b0;
            hazard_observed_o    <= 1'b0;
            hazard_blocked_o     <= 1'b0;
            unknown_hazard_o     <= 1'b0;
            alert_observed_o     <= 1'b0;
        end else begin
            committed_o          <= 1'b0;
            rejected_o           <= 1'b0;
            rejected_input_o     <= 1'b0;
            rejected_invariant_o <= 1'b0;
            rejected_hazard_o    <= 1'b0;
            changed_o            <= 1'b0;
            hazard_observed_o    <= 1'b0;
            hazard_blocked_o     <= 1'b0;
            unknown_hazard_o     <= 1'b0;
            alert_observed_o     <= 1'b0;

            if (event_valid_i === 1'b1) begin
                // Спостереження небезпеки та телеметрія
                if (hazard_known_i !== 1'b1 || (hazard_true_i !== 1'b0 && hazard_true_i !== 1'b1)) begin
                    unknown_hazard_o <= 1'b1;
                end else if (hazard_true_i === 1'b1) begin
                    hazard_observed_o <= 1'b1;
                end

                // Спостереження попередження (Alert)
                if (alert_known_i === 1'b1 && alert_true_i === 1'b1) begin
                    alert_observed_o <= 1'b1;
                end

                // Фазовий вентиль прийняття рішення (• / Big Dot)
                if (input_ok !== 1'b1) begin
                    rejected_o       <= 1'b1;
                    rejected_input_o <= 1'b1;
                end else if (invariant_ok !== 1'b1) begin
                    rejected_o           <= 1'b1;
                    rejected_invariant_o <= 1'b1;
                end else if (hazard_ok !== 1'b1) begin
                    rejected_o        <= 1'b1;
                    rejected_hazard_o <= 1'b1;
                    hazard_blocked_o  <= 1'b1;
                end else begin
                    state_o     <= candidate_value_i;
                    committed_o <= 1'b1;
                    changed_o   <= (candidate_value_i != state_o);
                end
            end
        end
    end
endmodule
