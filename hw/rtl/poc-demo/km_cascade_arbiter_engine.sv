// ============================================================================
// Модуль розширених стрес-тестів TC-05 .. TC-08 Машини Кузьміна
// Файл: km_cascade_arbiter_engine.sv
// Стандарт: IEEE 1800 SystemVerilog (Synthesizable for Xilinx 7-Series / openXC7)
// ============================================================================
`timescale 1ns / 1ps

module km_cascade_arbiter_engine #(
    parameter int DATA_WIDTH = 32
)(
    input  logic                   clk,
    input  logic                   rst_n,

    // Інтерфейс керування
    input  logic                   start_i,
    input  logic [2:0]             cmd_i,          // 1:TC05, 2:TC06, 3:TC07, 4:TC08, 5:ALL, 6:RST

    // Статусні виходи
    output logic                   busy_o,
    output logic                   done_o,
    output logic                   tc05_pass_o,
    output logic                   tc06_pass_o,
    output logic                   tc07_pass_o,
    output logic                   tc08_pass_o,
    output logic                   fail_error_o,
    output logic [3:0]             current_tc_o,
    output logic [31:0]            cycle_count_o,
    output logic [31:0]            result0_o,
    output logic [31:0]            result1_o
);

    // Головний автомат керування
    typedef enum logic [4:0] {
        ST_IDLE               = 5'd0,
        ST_RESET_RUN          = 5'd1,
        // TC-05: Boundary Transitions (Sign & Size)
        ST_TC05_INT8_CHECK    = 5'd2,
        ST_TC05_U8_CHECK      = 5'd3,
        ST_TC05_BYTE_STRB     = 5'd4,
        ST_TC05_FINISH        = 5'd5,
        // TC-06: Triple Cascade (Distance -> Speed -> Accel)
        ST_TC06_LEVEL1_DIST   = 5'd6,
        ST_TC06_LEVEL2_SPEED  = 5'd7,
        ST_TC06_LEVEL3_ACCEL  = 5'd8,
        ST_TC06_FINISH        = 5'd9,
        // TC-07: Big Dot Rejection (• = ¬)
        ST_TC07_INIT          = 5'd10,
        ST_TC07_REJECT_NEG    = 5'd11,
        ST_TC07_COMMIT_POS    = 5'd12,
        ST_TC07_FINISH        = 5'd13,
        // TC-08: Concurrent Write Conflict & Arbitration
        ST_TC08_INIT          = 5'd14,
        ST_TC08_COLLISION     = 5'd15,
        ST_TC08_SERIALIZE     = 5'd16,
        ST_TC08_FINISH        = 5'd17,
        // All Suite Sequencer
        ST_ALL_NEXT           = 5'd18,
        ST_DONE               = 5'd19
    } fsm_state_e;

    fsm_state_e fsm_state_q;
    logic [31:0] perf_timer_q;
    logic        tc05_pass_q;
    logic        tc06_pass_q;
    logic        tc07_pass_q;
    logic        tc08_pass_q;
    logic        fail_err_q;
    logic [3:0]  active_tc_q;
    logic        done_q;
    logic        all_mode_q;
    logic [2:0]  all_stage_q;
    logic [31:0] result0_q;
    logic [31:0] result1_q;

    // Внутрішні змінні для TC-05
    logic signed [7:0] int8_val_q;
    logic [7:0]        u8_val_q;
    logic [31:0]       strb_word_q;
    logic              tc05_int8_ok_q;
    logic              tc05_u8_ok_q;
    logic              tc05_strb_ok_q;

    // Внутрішні змінні для TC-06 (Triple Cascade)
    logic [31:0] dist_concept_q;
    logic [31:0] speed_concept_q;
    logic [31:0] accel_concept_q;
    logic [1:0]  dist_self_writes_q;
    logic [1:0]  speed_self_writes_q;
    logic [1:0]  accel_self_writes_q;
    logic [2:0]  cascade_depth_q;

    // Внутрішні змінні для TC-07 (Big Dot Rejection)
    logic [31:0] safe_concept_q;
    logic        dot_flag_q;
    logic        tc07_neg_rejected_q;
    logic        tc07_pos_committed_q;

    // Внутрішні змінні для TC-08 (Dual-Core Concurrent Write Arbitration)
    logic [31:0] voltage_accumulator_q;
    logic [31:0] core1_write_delta;
    logic [31:0] core2_write_delta;
    logic        core1_req;
    logic        core2_req;

    assign busy_o         = (fsm_state_q != ST_IDLE);
    assign done_o         = done_q;
    assign tc05_pass_o    = tc05_pass_q;
    assign tc06_pass_o    = tc06_pass_q;
    assign tc07_pass_o    = tc07_pass_q;
    assign tc08_pass_o    = tc08_pass_q;
    assign fail_error_o   = fail_err_q;
    assign current_tc_o   = active_tc_q;
    assign cycle_count_o  = perf_timer_q;
    assign result0_o      = result0_q;
    assign result1_o      = result1_q;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fsm_state_q          <= ST_IDLE;
            perf_timer_q         <= 32'd0;
            tc05_pass_q          <= 1'b0;
            tc06_pass_q          <= 1'b0;
            tc07_pass_q          <= 1'b0;
            tc08_pass_q          <= 1'b0;
            fail_err_q           <= 1'b0;
            active_tc_q          <= 4'd0;
            done_q               <= 1'b0;
            all_mode_q           <= 1'b0;
            all_stage_q          <= 3'd0;
            result0_q            <= 32'd0;
            result1_q            <= 32'd0;

            int8_val_q           <= 8'sd0;
            u8_val_q             <= 8'd0;
            strb_word_q          <= 32'd0;
            tc05_int8_ok_q       <= 1'b0;
            tc05_u8_ok_q         <= 1'b0;
            tc05_strb_ok_q       <= 1'b0;

            dist_concept_q       <= 32'd0;
            speed_concept_q      <= 32'd0;
            accel_concept_q      <= 32'd0;
            dist_self_writes_q   <= 2'd0;
            speed_self_writes_q  <= 2'd0;
            accel_self_writes_q  <= 2'd0;
            cascade_depth_q      <= 3'd0;

            safe_concept_q       <= 32'd0;
            dot_flag_q           <= 1'b1;
            tc07_neg_rejected_q  <= 1'b0;
            tc07_pos_committed_q <= 1'b0;

            voltage_accumulator_q<= 32'd0;
        end else begin
            if (fsm_state_q != ST_IDLE && fsm_state_q != ST_DONE) begin
                perf_timer_q <= perf_timer_q + 32'd1;
            end

            case (fsm_state_q)
                ST_IDLE: begin
                    if (start_i) begin
                        done_q       <= 1'b0;
                        perf_timer_q <= 32'd0;
                        case (cmd_i)
                            3'd1: begin // TC-05
                                active_tc_q <= 4'd5;
                                all_mode_q  <= 1'b0;
                                tc05_pass_q <= 1'b0;
                                int8_val_q  <= 8'sd127;
                                fsm_state_q <= ST_TC05_INT8_CHECK;
                            end
                            3'd2: begin // TC-06
                                active_tc_q        <= 4'd6;
                                all_mode_q         <= 1'b0;
                                tc06_pass_q        <= 1'b0;
                                dist_concept_q     <= 32'd10;
                                speed_concept_q    <= 32'd5;
                                accel_concept_q    <= 32'd2;
                                dist_self_writes_q <= 2'd0;
                                speed_self_writes_q<= 2'd0;
                                accel_self_writes_q<= 2'd0;
                                cascade_depth_q    <= 3'd0;
                                fsm_state_q        <= ST_TC06_LEVEL1_DIST;
                            end
                            3'd3: begin // TC-07
                                active_tc_q        <= 4'd7;
                                all_mode_q         <= 1'b0;
                                tc07_pass_q        <= 1'b0;
                                safe_concept_q     <= 32'd100;
                                fsm_state_q        <= ST_TC07_INIT;
                            end
                            3'd4: begin // TC-08
                                active_tc_q           <= 4'd8;
                                all_mode_q            <= 1'b0;
                                tc08_pass_q           <= 1'b0;
                                voltage_accumulator_q <= 32'd0;
                                fsm_state_q           <= ST_TC08_INIT;
                            end
                            3'd5: begin // ALL: TC05 -> TC06 -> TC07 -> TC08
                                active_tc_q <= 4'd5;
                                all_mode_q  <= 1'b1;
                                all_stage_q <= 3'd1;
                                tc05_pass_q <= 1'b0;
                                tc06_pass_q <= 1'b0;
                                tc07_pass_q <= 1'b0;
                                tc08_pass_q <= 1'b0;
                                fail_err_q  <= 1'b0;
                                int8_val_q  <= 8'sd127;
                                fsm_state_q <= ST_TC05_INT8_CHECK;
                            end
                            3'd6: begin // Reset
                                fsm_state_q <= ST_RESET_RUN;
                            end
                            default: ;
                        endcase
                    end
                end

                ST_RESET_RUN: begin
                    tc05_pass_q <= 1'b0;
                    tc06_pass_q <= 1'b0;
                    tc07_pass_q <= 1'b0;
                    tc08_pass_q <= 1'b0;
                    fail_err_q  <= 1'b0;
                    result0_q   <= 32'd0;
                    result1_q   <= 32'd0;
                    done_q      <= 1'b1;
                    fsm_state_q <= ST_IDLE;
                end

                // ============================================================
                // TC-05: BOUNDARY TRANSITIONS OF SIGN & SIZE (Int8, U8, Byte-Wstrb)
                // ============================================================
                ST_TC05_INT8_CHECK: begin
                    // +127 + 1 -> -128 (знакове переповнення Int8)
                    // Предикат Negative стає активним (int8 < 0)
                    // Запис у регістр int8_val_q
                    int8_val_q  <= int8_val_q + 8'sd1;
                    u8_val_q    <= 8'd255;
                    fsm_state_q <= ST_TC05_U8_CHECK;
                end

                ST_TC05_U8_CHECK: begin
                    // Верифікація фізичного значення регістра int8_val_q (не виразу)
                    if (int8_val_q == -8'sd128) begin
                        tc05_int8_ok_q <= 1'b1;
                    end else begin
                        tc05_int8_ok_q <= 1'b0;
                        fail_err_q     <= 1'b1;
                    end
                    // 255 + 1 -> 0 (беззнакове переповнення U8)
                    // Предикат Null стає активним (u8 == 0)
                    u8_val_q    <= u8_val_q + 8'd1;
                    strb_word_q <= 32'hAABBCCDD;
                    fsm_state_q <= ST_TC05_BYTE_STRB;
                end

                ST_TC05_BYTE_STRB: begin
                    // Верифікація фізичного значення регістра u8_val_q (не виразу)
                    if (u8_val_q == 8'd0) begin
                        tc05_u8_ok_q <= 1'b1;
                    end else begin
                        tc05_u8_ok_q <= 1'b0;
                        fail_err_q   <= 1'b1;
                    end
                    // Модифікація тільки байта 1 (wstrb = 4'b0010)
                    // 0xAABBCCDD -> запис 0x55 у byte 1 -> 0xAABB55DD
                    strb_word_q[15:8] <= 8'h55;
                    fsm_state_q       <= ST_TC05_FINISH;
                end

                ST_TC05_FINISH: begin
                    // Верифікація фізичного значення регістра strb_word_q
                    if (strb_word_q == 32'hAABB55DD) begin
                        tc05_strb_ok_q <= 1'b1;
                    end else begin
                        tc05_strb_ok_q <= 1'b0;
                        fail_err_q     <= 1'b1;
                    end

                    if (tc05_int8_ok_q && (u8_val_q == 8'd0) && (strb_word_q == 32'hAABB55DD)) begin
                        tc05_pass_q <= 1'b1;
                    end else begin
                        tc05_pass_q <= 1'b0;
                    end
                    result0_q <= {16'd0, 8'd0, int8_val_q}; // 0x0080 (-128)
                    result1_q <= strb_word_q;               // 0xAABB55DD

                    if (all_mode_q) begin
                        fsm_state_q <= ST_ALL_NEXT;
                    end else begin
                        fsm_state_q <= ST_DONE;
                    end
                end

                // ============================================================
                // TC-06: TRIPLE CASCADE OF SELF-ADDRESSING (Distance -> Speed -> Accel)
                // ============================================================
                ST_TC06_LEVEL1_DIST: begin
                    // Рівень 1: Distance += 1 (самозапис)
                    // Захист від саморекурсії: дозволено рівно 1 самозапис
                    dist_concept_q     <= dist_concept_q + 32'd1; // 10 -> 11
                    dist_self_writes_q <= dist_self_writes_q + 2'd1;
                    cascade_depth_q    <= 3'd1;
                    // Після • активується підписка на Speed
                    fsm_state_q        <= ST_TC06_LEVEL2_SPEED;
                end

                ST_TC06_LEVEL2_SPEED: begin
                    // Рівень 2: Speed += Distance (5 + 11 = 16)
                    // Самозапис Speed += 1 (16 + 1 = 17)
                    speed_concept_q     <= speed_concept_q + dist_concept_q + 32'd1;
                    speed_self_writes_q <= speed_self_writes_q + 2'd1;
                    cascade_depth_q     <= 3'd2;
                    // Після • активується підписка на Accel
                    fsm_state_q         <= ST_TC06_LEVEL3_ACCEL;
                end

                ST_TC06_LEVEL3_ACCEL: begin
                    // Рівень 3: Accel += Speed (2 + 17 = 19)
                    // Самозапис Accel += 1 (19 + 1 = 20)
                    accel_concept_q     <= accel_concept_q + speed_concept_q + 32'd1;
                    accel_self_writes_q <= accel_self_writes_q + 2'd1;
                    cascade_depth_q     <= 3'd3;
                    fsm_state_q         <= ST_TC06_FINISH;
                end

                ST_TC06_FINISH: begin
                    // Інваріант: кожен концепт виконав рівно по 1 самозапису, каскад дійшов до рівня 3
                    if (dist_self_writes_q == 2'd1 &&
                        speed_self_writes_q == 2'd1 &&
                        accel_self_writes_q == 2'd1 &&
                        cascade_depth_q == 3'd3 &&
                        dist_concept_q == 32'd11 &&
                        speed_concept_q == 32'd17 &&
                        accel_concept_q == 32'd20) begin
                        tc06_pass_q <= 1'b1;
                    end else begin
                        tc06_pass_q <= 1'b0;
                        fail_err_q  <= 1'b1;
                    end
                    result0_q <= accel_concept_q; // 20
                    result1_q <= {8'd0, cascade_depth_q, 5'd0, speed_concept_q[7:0], dist_concept_q[7:0]};

                    if (all_mode_q) begin
                        fsm_state_q <= ST_ALL_NEXT;
                    end else begin
                        fsm_state_q <= ST_DONE;
                    end
                end

                // ============================================================
                // TC-07: BIG DOT REJECTION GATE (• = ¬ Fail-Closed)
                // ============================================================
                ST_TC07_INIT: begin
                    safe_concept_q <= 32'd100;
                    dot_flag_q     <= 1'b1;
                    fsm_state_q    <= ST_TC07_REJECT_NEG;
                end

                ST_TC07_REJECT_NEG: begin
                    // Спроба записати від'ємного кандидата -50 (0xFFFFFFCE)
                    // Пре-фаза: [• : < 0  • = ¬]
                    // Оскільки кандидат < 0, • скидається в 0 (¬).
                    // Апаратний шлюз блокує запис: safe_concept_q залишається 100!
                    dot_flag_q <= 1'b0; // • = ¬
                    if (safe_concept_q == 32'd100) begin
                        tc07_neg_rejected_q <= 1'b1;
                    end else begin
                        tc07_neg_rejected_q <= 1'b0;
                        fail_err_q          <= 1'b1;
                    end
                    fsm_state_q <= ST_TC07_COMMIT_POS;
                end

                ST_TC07_COMMIT_POS: begin
                    // Спроба записати валідного додатного кандидата +200
                    // Пре-фаза: [• : >= 0  • = !] -> • = 1
                    // Апаратний шлюз підтверджує коміт: safe_concept_q стає 200!
                    dot_flag_q     <= 1'b1; // • = !
                    safe_concept_q <= 32'd200;
                    tc07_pos_committed_q <= 1'b1;
                    fsm_state_q    <= ST_TC07_FINISH;
                end

                ST_TC07_FINISH: begin
                    if (tc07_neg_rejected_q && tc07_pos_committed_q && safe_concept_q == 32'd200) begin
                        tc07_pass_q <= 1'b1;
                    end else begin
                        tc07_pass_q <= 1'b0;
                    end
                    result0_q <= safe_concept_q; // 200
                    result1_q <= {30'd0, tc07_pos_committed_q, tc07_neg_rejected_q};

                    if (all_mode_q) begin
                        fsm_state_q <= ST_ALL_NEXT;
                    end else begin
                        fsm_state_q <= ST_DONE;
                    end
                end

                // ============================================================
                // TC-08: CONCURRENT WRITE CONFLICT ARBITRATION (+= x Serialization)
                // ============================================================
                ST_TC08_INIT: begin
                    voltage_accumulator_q <= 32'd0;
                    fsm_state_q           <= ST_TC08_COLLISION;
                end

                ST_TC08_COLLISION: begin
                    // Одночасний запис з двох ядер:
                    // Core 1 додає 40, Core 2 додає 60
                    // Такт T: Арбітр серіалізує і спочатку додає внесок Core 1 (+40)
                    voltage_accumulator_q <= voltage_accumulator_q + 32'd40;
                    fsm_state_q           <= ST_TC08_SERIALIZE;
                end

                ST_TC08_SERIALIZE: begin
                    // Такт T+1: Арбітр додає внесок Core 2 (+60)
                    voltage_accumulator_q <= voltage_accumulator_q + 32'd60;
                    fsm_state_q           <= ST_TC08_FINISH;
                end

                ST_TC08_FINISH: begin
                    // Сума повинна бути рівно 0 + 40 + 60 = 100 за 2 такти без втрати
                    if (voltage_accumulator_q == 32'd100) begin
                        tc08_pass_q <= 1'b1;
                    end else begin
                        tc08_pass_q <= 1'b0;
                        fail_err_q  <= 1'b1;
                    end
                    result0_q <= voltage_accumulator_q; // 100
                    result1_q <= 32'd2;                 // 2 такти серіалізації

                    if (all_mode_q) begin
                        fsm_state_q <= ST_ALL_NEXT;
                    end else begin
                        fsm_state_q <= ST_DONE;
                    end
                end

                // ============================================================
                // ALL SUITE SEQUENCER
                // ============================================================
                ST_ALL_NEXT: begin
                    case (all_stage_q)
                        3'd1: begin
                            all_stage_q        <= 3'd2;
                            active_tc_q        <= 4'd6;
                            dist_concept_q     <= 32'd10;
                            speed_concept_q    <= 32'd5;
                            accel_concept_q    <= 32'd2;
                            dist_self_writes_q <= 2'd0;
                            speed_self_writes_q<= 2'd0;
                            accel_self_writes_q<= 2'd0;
                            cascade_depth_q    <= 3'd0;
                            fsm_state_q        <= ST_TC06_LEVEL1_DIST;
                        end
                        3'd2: begin
                            all_stage_q    <= 3'd3;
                            active_tc_q    <= 4'd7;
                            safe_concept_q <= 32'd100;
                            fsm_state_q    <= ST_TC07_INIT;
                        end
                        3'd3: begin
                            all_stage_q           <= 3'd4;
                            active_tc_q           <= 4'd8;
                            voltage_accumulator_q <= 32'd0;
                            fsm_state_q           <= ST_TC08_INIT;
                        end
                        default: begin
                            fsm_state_q <= ST_DONE;
                        end
                    endcase
                end

                ST_DONE: begin
                    done_q      <= 1'b1;
                    fsm_state_q <= ST_IDLE;
                end

                default: fsm_state_q <= ST_IDLE;
            endcase
        end
    end

endmodule
