// ============================================================================
// Модуль: km_concept_micro_engine.sv
// Призначення: Універсальне обчислювальне ядро концепту Машини Кузьміна (CME).
// Повністю усуває жорстке кодування FSM, декодуючи логіку предикатів,
// інваріантів та переходів із 16-байтного дескриптора BRAM.
// ============================================================================
`timescale 1ns / 1ps

module km_concept_micro_engine #(
    parameter int DATA_WIDTH = 32
)(
    input  logic                   clk,
    input  logic                   rst_n,

    // Вхідна подія
    input  logic                   event_valid_i,
    input  logic [7:0]             event_id_i,
    input  logic [DATA_WIDTH-1:0]  event_param_i,

    // 16-байтний дескриптор концепту (128 біт), зчитаний з BRAM
    input  logic [127:0]           descriptor_i,

    // Виходи рішення транзакційного шлюзу
    output logic                   committed_o,
    output logic                   rejected_o,
    output logic                   hazard_observed_o,
    output logic                   unknown_hazard_o,

    // Оновлений стан концепту для запису назад у BRAM
    output logic [DATA_WIDTH-1:0]  updated_state_o,
    output logic                   state_changed_o,

    // Каскадна підписка для міжконцептного рандеву
    output logic [31:0]            subscriber_cid_o,
    output logic                   trigger_subscriber_o
);

    // ========================================================================
    // 1. РОЗПАКУВАННЯ 16-БАЙТНОГО ДЕСКРИПТОРА (128 біт)
    // ========================================================================
    logic [31:0] current_state_w;
    logic [31:0] operand_val_w;
    logic [7:0]  pred_opcode_w;
    logic [7:0]  guard_flags_w;
    logic [7:0]  hazard_limit_w;
    logic [7:0]  action_opcode_w;
    logic [31:0] subscriber_cid_w;

    assign current_state_w  = descriptor_i[31:0];
    assign operand_val_w    = descriptor_i[63:32];
    assign pred_opcode_w    = descriptor_i[71:64];
    assign guard_flags_w    = descriptor_i[79:72];
    assign hazard_limit_w   = descriptor_i[87:80];
    assign action_opcode_w  = descriptor_i[95:88];
    assign subscriber_cid_w = descriptor_i[127:96];

    wire [15:0] range_lo_w = operand_val_w[15:0];
    wire [15:0] range_hi_w = operand_val_w[31:16];

    // ========================================================================
    // 2. ДЕКОДУВАННЯ ПРЕДИКАТУ (Predicate Micro-Opcode)
    // ========================================================================
    logic pred_raw_res;

    always_comb begin
        case (pred_opcode_w)
            8'h00: pred_raw_res = 1'b1; // NOP: завжди істина
            8'h01: pred_raw_res = (event_param_i == operand_val_w); // EQ
            8'h02: pred_raw_res = (event_param_i != operand_val_w); // NEQ
            8'h03: pred_raw_res = ($signed(event_param_i) > $signed(operand_val_w)); // GT
            8'h04: pred_raw_res = ($signed(event_param_i) < $signed(operand_val_w)); // LT
            8'h05: pred_raw_res = (event_param_i >= range_lo_w) &&
                                  (event_param_i <= range_hi_w); // RANGE
            8'h06: pred_raw_res = ((event_param_i & operand_val_w) != 32'd0); // BITMASK
            default: pred_raw_res = 1'b0;
        endcase
    end

    // ========================================================================
    // 3. ФОРМУВАННЯ КАНДИДАТА НА НОВИЙ СТАН (Action Micro-Opcode)
    // ========================================================================
    logic [DATA_WIDTH-1:0] candidate_state_w;

    always_comb begin
        case (action_opcode_w)
            8'h00: candidate_state_w = event_param_i;                  // ASSIGN
            8'h01: candidate_state_w = current_state_w + 32'd1;        // INC
            8'h02: candidate_state_w = current_state_w - 32'd1;        // DEC
            8'h03: candidate_state_w = current_state_w + operand_val_w; // ADD
            8'h04: candidate_state_w = current_state_w - operand_val_w; // SUB
            default: candidate_state_w = current_state_w;
        endcase
    end

    // ========================================================================
    // 4. ГЕНЕРАЦІЯ ОХОРОНЦІВ (Guards: Assumption, Invariant, Hazard)
    // ========================================================================
    logic assumption_known_w;
    logic assumption_true_w;
    logic invariant_known_w;
    logic invariant_true_w;
    logic hazard_known_w;
    logic hazard_true_w;

    // bit 0: Enable Assumption; bit 3: Invert assumption (• = ¬)
    assign assumption_known_w = guard_flags_w[0];
    assign assumption_true_w  = guard_flags_w[3] ? ~pred_raw_res : pred_raw_res;

    // bit 1: Enable Invariant; захист від знакового переповнення або від'ємного стану
    assign invariant_known_w  = guard_flags_w[1];
    assign invariant_true_w   = ($signed(candidate_state_w) >= 0);

    // bit 2: Enable Hazard; порогова детекція небезпечного значення
    // Статус небезпеки відомий (known = 1'b1); істинний лише коли прапорець активний і ліміт перевищено
    assign hazard_known_w     = 1'b1;
    assign hazard_true_w      = guard_flags_w[2] && (hazard_limit_w != 8'd0) &&
                                ($signed(event_param_i) > $signed({24'd0, hazard_limit_w}));

    // ========================================================================
    // 5. ТРАНЗАКЦІЙНИЙ ШЛЮЗ KPOL v2 (Строгий Fail-Closed режим для Hazards)
    // ========================================================================
    logic [DATA_WIDTH-1:0] gate_state_out;
    logic                  gate_committed;
    logic                  gate_rejected;
    logic                  gate_changed;
    logic                  gate_hazard_obs;
    logic                  gate_unknown_haz;

    kpol_txn_gate_v2 #(
        .DATA_WIDTH(DATA_WIDTH),
        .RESET_VALUE(32'd0),
        .FAIL_CLOSED_HAZARDS(1'b1)
    ) txn_gate_inst (
        .clk_i(clk),
        .rst_ni(rst_n),
        .event_valid_i(event_valid_i),
        .candidate_value_i(candidate_state_w),
        .candidate_known_i(1'b1),
        .assumption_known_i(assumption_known_w),
        .assumption_true_i(assumption_true_w),
        .invariant_known_i(invariant_known_w),
        .invariant_true_i(invariant_true_w),
        .hazard_known_i(hazard_known_w),
        .hazard_true_i(hazard_true_w),
        .alert_known_i(1'b0),
        .alert_true_i(1'b0),
        .state_o(gate_state_out),
        .committed_o(gate_committed),
        .rejected_o(gate_rejected),
        .rejected_input_o(),
        .rejected_invariant_o(),
        .rejected_hazard_o(),
        .changed_o(gate_changed),
        .hazard_observed_o(gate_hazard_obs),
        .hazard_blocked_o(),
        .unknown_hazard_o(gate_unknown_haz),
        .alert_observed_o()
    );

    // ========================================================================
    // 6. ВИХІДНІ СИГНАЛИ ТА МІЖКОНЦЕПТНЕ РАНДЕВУ
    // ========================================================================
    assign committed_o          = gate_committed;
    assign rejected_o           = gate_rejected;
    assign hazard_observed_o    = gate_hazard_obs;
    assign unknown_hazard_o     = gate_unknown_haz;

    assign updated_state_o      = gate_committed ? gate_state_out : current_state_w;
    assign state_changed_o      = gate_changed;

    assign subscriber_cid_o     = subscriber_cid_w;
    assign trigger_subscriber_o = gate_committed && (subscriber_cid_w != 32'd0);

endmodule
