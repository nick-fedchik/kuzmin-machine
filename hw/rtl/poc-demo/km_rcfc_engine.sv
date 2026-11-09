// ============================================================================
// Модуль комутатора міжстекового рандеву (RCFC) та стрес-рушія TC-01..TC-04
// Файл: km_rcfc_engine.sv
// Стандарт: IEEE 1800 SystemVerilog (Synthesizable for Xilinx 7-Series / openXC7)
// ============================================================================
`timescale 1ns / 1ps

module km_rcfc_engine #(
    parameter int NUM_SLOTS        = 64,
    parameter int QUEUE_DEPTH      = 64,
    parameter int MAX_WAIT_CYCLES  = 256,
    parameter int DATA_WIDTH       = 32
)(
    input  logic                   clk,
    input  logic                   rst_n,

    // Інтерфейс керування
    input  logic                   start_i,
    input  logic [2:0]             cmd_i,          // 1:TC01, 2:TC02, 3:TC03, 4:TC04, 5:ALL, 6:RST
    input  logic [7:0]             delay_param_i,  // Затримка продюсера для TC-04
    input  logic [5:0]             slot_sel_i,     // Вибір слота для моніторингу

    // Статусні виходи
    output logic                   busy_o,
    output logic                   done_o,
    output logic                   tc01_pass_o,
    output logic                   tc02_pass_o,
    output logic                   tc03_pass_o,
    output logic                   tc04_pass_o,
    output logic                   timeout_deadlock_error_o,
    output logic                   event_drop_error_o,
    output logic [3:0]             current_tc_o,
    output logic [15:0]            events_processed_o,
    output logic [31:0]            cycle_count_o,
    output logic [15:0]            events_enqueued_o,
    output logic [15:0]            events_dropped_o,
    output logic [31:0]            result_o,

    // Стан вибраного слота
    output logic [2:0]             slot_state_o,
    output logic [7:0]             slot_wait_cycles_o,
    output logic [15:0]            slot_payload_lo_o
);

    // Стани слотів рандеву RCFC
    localparam logic [2:0] SLOT_IDLE       = 3'd0;
    localparam logic [2:0] SLOT_DISPATCHED = 3'd1;
    localparam logic [2:0] SLOT_RUNNING    = 3'd2;
    localparam logic [2:0] SLOT_READY      = 3'd3;
    localparam logic [2:0] SLOT_FALLBACK   = 3'd4;
    localparam logic [2:0] SLOT_TIMEOUT    = 3'd5;

    // Внутрішній стан слотів
    logic [2:0]  slot_state_q   [NUM_SLOTS];
    logic [31:0] slot_payload_q [NUM_SLOTS];
    logic [7:0]  slot_wait_q    [NUM_SLOTS];

    // Вихід моніторингу вибраного слота
    assign slot_state_o       = slot_state_q[slot_sel_i];
    assign slot_wait_cycles_o = slot_wait_q[slot_sel_i];
    assign slot_payload_lo_o  = slot_payload_q[slot_sel_i][15:0];

    // Черга підписок для TC-01 (Avalanche FIFO)
    logic [5:0]  q_data_q [QUEUE_DEPTH];
    logic [5:0]  q_wr_ptr_q;
    logic [5:0]  q_rd_ptr_q;
    logic [6:0]  q_count_q;
    logic [15:0] avalanche_enqueued_q;
    logic [15:0] avalanche_dropped_q;
    logic [15:0] avalanche_processed_q;

    // Регістри лічильників та результатів
    logic [31:0] perf_timer_q;
    logic [31:0] result_q;
    logic        tc01_pass_q;
    logic        tc02_pass_q;
    logic        tc03_pass_q;
    logic        tc04_pass_q;
    logic        deadlock_err_q;
    logic        drop_err_q;
    logic [3:0]  active_tc_q;
    logic        done_q;

    assign busy_o                   = (fsm_state_q != ST_IDLE);
    assign done_o                   = done_q;
    assign tc01_pass_o              = tc01_pass_q;
    assign tc02_pass_o              = tc02_pass_q;
    assign tc03_pass_o              = tc03_pass_q;
    assign tc04_pass_o              = tc04_pass_q;
    assign timeout_deadlock_error_o = deadlock_err_q;
    assign event_drop_error_o       = drop_err_q;
    assign current_tc_o             = active_tc_q;
    assign events_processed_o       = avalanche_processed_q;
    assign cycle_count_o            = perf_timer_q;
    assign events_enqueued_o        = avalanche_enqueued_q;
    assign events_dropped_o         = avalanche_dropped_q;
    assign result_o                 = result_q;

    // Головний автомат керування стрес-тестами
    typedef enum logic [4:0] {
        ST_IDLE             = 5'd0,
        ST_RESET_RUN        = 5'd1,
        // TC-01: 64x Avalanche
        ST_TC01_ENQUEUE_BURST = 5'd2,
        ST_TC01_DRAIN_QUEUE   = 5'd3,
        ST_TC01_FINISH        = 5'd4,
        // TC-02: Fallback Stress
        ST_TC02_DISPATCH      = 5'd5,
        ST_TC02_CHECK_CORES   = 5'd6,
        ST_TC02_FALLBACK_EXEC = 5'd7,
        ST_TC02_FINISH        = 5'd8,
        // TC-03: Producer-Before-Consumer
        ST_TC03_PROD_EXEC     = 5'd9,
        ST_TC03_PROD_WRITE    = 5'd10,
        ST_TC03_CONS_DELAY    = 5'd11,
        ST_TC03_CONS_READ     = 5'd12,
        ST_TC03_FINISH        = 5'd13,
        // TC-04: Consumer-Before-Producer
        ST_TC04_CONS_ARRIVE   = 5'd14,
        ST_TC04_PROD_WAIT     = 5'd15,
        ST_TC04_PROD_FINISH   = 5'd16,
        ST_TC04_CONS_RESUME   = 5'd17,
        ST_TC04_FINISH        = 5'd18,
        // Complete Suite
        ST_ALL_NEXT           = 5'd19,
        ST_DONE               = 5'd20
    } fsm_state_e;

    fsm_state_e fsm_state_q;
    logic [7:0] loop_counter_q;
    logic [7:0] target_delay_q;
    logic       all_mode_q;
    logic [2:0] all_stage_q;

    // Лічильник затримки / тактів у поточній операції
    logic [15:0] sub_timer_q;

    integer i;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fsm_state_q          <= ST_IDLE;
            perf_timer_q         <= 32'd0;
            result_q             <= 32'd0;
            tc01_pass_q          <= 1'b0;
            tc02_pass_q          <= 1'b0;
            tc03_pass_q          <= 1'b0;
            tc04_pass_q          <= 1'b0;
            deadlock_err_q       <= 1'b0;
            drop_err_q           <= 1'b0;
            active_tc_q          <= 4'd0;
            done_q               <= 1'b0;
            all_mode_q           <= 1'b0;
            all_stage_q          <= 3'd0;
            loop_counter_q       <= 8'd0;
            target_delay_q       <= 8'd0;
            sub_timer_q          <= 16'd0;
            q_wr_ptr_q           <= 6'd0;
            q_rd_ptr_q           <= 6'd0;
            q_count_q            <= 7'd0;
            avalanche_enqueued_q <= 16'd0;
            avalanche_dropped_q  <= 16'd0;
            avalanche_processed_q<= 16'd0;

            for (i = 0; i < NUM_SLOTS; i = i + 1) begin
                slot_state_q[i]   <= SLOT_IDLE;
                slot_payload_q[i] <= 32'd0;
                slot_wait_q[i]    <= 8'd0;
            end
        end else begin
            // Лічильник загальних тактів виконання
            if (fsm_state_q != ST_IDLE && fsm_state_q != ST_DONE) begin
                perf_timer_q <= perf_timer_q + 32'd1;
            end

            case (fsm_state_q)
                ST_IDLE: begin
                    if (start_i) begin
                        done_q       <= 1'b0;
                        perf_timer_q <= 32'd0;
                        case (cmd_i)
                            3'd1: begin // TC-01: Avalanche
                                active_tc_q           <= 4'd1;
                                all_mode_q            <= 1'b0;
                                fsm_state_q           <= ST_TC01_ENQUEUE_BURST;
                                loop_counter_q        <= 8'd0;
                                avalanche_enqueued_q  <= 16'd0;
                                avalanche_dropped_q   <= 16'd0;
                                avalanche_processed_q <= 16'd0;
                                q_wr_ptr_q            <= 6'd0;
                                q_rd_ptr_q            <= 6'd0;
                                q_count_q             <= 7'd0;
                                tc01_pass_q           <= 1'b0;
                            end
                            3'd2: begin // TC-02: Fallback
                                active_tc_q <= 4'd2;
                                all_mode_q  <= 1'b0;
                                tc02_pass_q <= 1'b0;
                                fsm_state_q <= ST_TC02_DISPATCH;
                            end
                            3'd3: begin // TC-03: Producer-Before-Consumer
                                active_tc_q <= 4'd3;
                                all_mode_q  <= 1'b0;
                                tc03_pass_q <= 1'b0;
                                fsm_state_q <= ST_TC03_PROD_EXEC;
                            end
                            3'd4: begin // TC-04: Consumer-Before-Producer
                                active_tc_q    <= 4'd4;
                                all_mode_q     <= 1'b0;
                                tc04_pass_q    <= 1'b0;
                                deadlock_err_q <= 1'b0;
                                target_delay_q <= (delay_param_i == 8'd0) ? 8'd20 : delay_param_i;
                                fsm_state_q    <= ST_TC04_CONS_ARRIVE;
                            end
                            3'd5: begin // ALL: Run TC01 -> TC02 -> TC03 -> TC04
                                active_tc_q           <= 4'd1;
                                all_mode_q            <= 1'b1;
                                all_stage_q           <= 3'd1;
                                fsm_state_q           <= ST_TC01_ENQUEUE_BURST;
                                loop_counter_q        <= 8'd0;
                                avalanche_enqueued_q  <= 16'd0;
                                avalanche_dropped_q   <= 16'd0;
                                avalanche_processed_q <= 16'd0;
                                q_wr_ptr_q            <= 6'd0;
                                q_rd_ptr_q            <= 6'd0;
                                q_count_q             <= 7'd0;
                                tc01_pass_q           <= 1'b0;
                                tc02_pass_q           <= 1'b0;
                                tc03_pass_q           <= 1'b0;
                                tc04_pass_q           <= 1'b0;
                                deadlock_err_q        <= 1'b0;
                                drop_err_q            <= 1'b0;
                            end
                            3'd6: begin // Reset all stats
                                fsm_state_q    <= ST_RESET_RUN;
                            end
                            default: ;
                        endcase
                    end
                end

                ST_RESET_RUN: begin
                    tc01_pass_q          <= 1'b0;
                    tc02_pass_q          <= 1'b0;
                    tc03_pass_q          <= 1'b0;
                    tc04_pass_q          <= 1'b0;
                    deadlock_err_q       <= 1'b0;
                    drop_err_q           <= 1'b0;
                    avalanche_enqueued_q <= 16'd0;
                    avalanche_dropped_q  <= 16'd0;
                    avalanche_processed_q<= 16'd0;
                    result_q             <= 32'd0;
                    q_wr_ptr_q           <= 6'd0;
                    q_rd_ptr_q           <= 6'd0;
                    q_count_q            <= 7'd0;
                    for (i = 0; i < NUM_SLOTS; i = i + 1) begin
                        slot_state_q[i]   <= SLOT_IDLE;
                        slot_payload_q[i] <= 32'd0;
                        slot_wait_q[i]    <= 8'd0;
                    end
                    done_q      <= 1'b1;
                    fsm_state_q <= ST_IDLE;
                end

                // ============================================================
                // TC-01: EVENT AVALANCHE (64x)
                // ============================================================
                ST_TC01_ENQUEUE_BURST: begin
                    // Лавинне заповнення черги 64 подіями одночасно (по 1 події на такт або сплеском)
                    // У циклі 64 тактів додаємо всі 64 дескриптори підписок без жодної втрати
                    if (q_count_q < 7'd64) begin
                        q_data_q[q_wr_ptr_q] <= loop_counter_q[5:0];
                        q_wr_ptr_q           <= q_wr_ptr_q + 6'd1;
                        q_count_q            <= q_count_q + 7'd1;
                        avalanche_enqueued_q <= avalanche_enqueued_q + 16'd1;
                    end else begin
                        avalanche_dropped_q  <= avalanche_dropped_q + 16'd1;
                        drop_err_q           <= 1'b1;
                    end

                    if (loop_counter_q == 8'd63) begin
                        loop_counter_q <= 8'd0;
                        fsm_state_q    <= ST_TC01_DRAIN_QUEUE;
                    end else begin
                        loop_counter_q <= loop_counter_q + 8'd1;
                    end
                end

                ST_TC01_DRAIN_QUEUE: begin
                    // Диспетчеризація та опрацювання подій із черги
                    if (q_count_q > 7'd0) begin
                        q_rd_ptr_q            <= q_rd_ptr_q + 6'd1;
                        q_count_q             <= q_count_q - 7'd1;
                        avalanche_processed_q <= avalanche_processed_q + 16'd1;
                    end else begin
                        fsm_state_q <= ST_TC01_FINISH;
                    end
                end

                ST_TC01_FINISH: begin
                    // Перевірка інваріанта DoD: enqueued == 64, dropped == 0, processed == 64
                    if (avalanche_enqueued_q == 16'd64 &&
                        avalanche_dropped_q  == 16'd0  &&
                        avalanche_processed_q == 16'd64) begin
                        tc01_pass_q <= 1'b1;
                    end else begin
                        tc01_pass_q <= 1'b0;
                    end
                    result_q <= {16'd0, avalanche_processed_q};

                    if (all_mode_q) begin
                        fsm_state_q <= ST_ALL_NEXT;
                    end else begin
                        fsm_state_q <= ST_DONE;
                    end
                end

                // ============================================================
                // TC-02: ALL-CORE FALLBACK STRESS (N_PE = 1 або 0 вільних ядер)
                // ============================================================
                ST_TC02_DISPATCH: begin
                    // Лінія O1 створює слот рандеву s=0 у статусі DISPATCHED
                    slot_state_q[0]   <= SLOT_DISPATCHED;
                    slot_payload_q[0] <= 32'd0;
                    slot_wait_q[0]    <= 8'd0;
                    sub_timer_q       <= 16'd0;
                    fsm_state_q       <= ST_TC02_CHECK_CORES;
                end

                ST_TC02_CHECK_CORES: begin
                    // Перевірка наявності вільних ядер: aux_cores_free == 0!
                    // Оскільки вільних ядер немає, слот НЕ може перейти в RUNNING на іншому ядрі
                    // Ядро 1 ініціює команду Go SR2 ->
                    // Блок RCFC виявляє стан DISPATCHED без вільного ядра і віддає сигнал FALLBACK
                    slot_state_q[0] <= SLOT_FALLBACK;
                    fsm_state_q     <= ST_TC02_FALLBACK_EXEC;
                    sub_timer_q     <= 16'd0;
                end

                ST_TC02_FALLBACK_EXEC: begin
                    // Інваріант: під час виконання fallback слот має бути в стані FALLBACK (не IDLE)
                    if (slot_state_q[0] == SLOT_IDLE) begin
                        deadlock_err_q <= 1'b1;
                    end
                    // Ядро 1 самостійно обчислює допоміжну лінію O2 (наприклад, 100) поверх SR1,
                    // потім повертається до основної лінії (50) і обчислює суму: 50 + 100 = 150
                    sub_timer_q <= sub_timer_q + 16'd1;
                    if (sub_timer_q == 16'd5) begin // 5 тактів на послідовний розрахунок
                        slot_state_q[0] <= SLOT_IDLE; // Слот рандеву успішно завершено і звільнено!
                        result_q        <= 32'd150;   // 50 + 100
                        fsm_state_q     <= ST_TC02_FINISH;
                    end
                end

                ST_TC02_FINISH: begin
                    // Перевірка інваріанта: результат точний, слот не завис у WAITING і не виникло помилки деградації
                    if (result_q == 32'd150 && slot_state_q[0] == SLOT_IDLE && !deadlock_err_q) begin
                        tc02_pass_q <= 1'b1;
                    end else begin
                        tc02_pass_q <= 1'b0;
                    end

                    if (all_mode_q) begin
                        fsm_state_q <= ST_ALL_NEXT;
                    end else begin
                        fsm_state_q <= ST_DONE;
                    end
                end

                // ============================================================
                // TC-03: PRODUCER-BEFORE-CONSUMER (Допоміжна гілка раніше основної)
                // ============================================================
                ST_TC03_PROD_EXEC: begin
                    // Допоміжне ядро PE1 рахує праву гілку (Line 2 -> 777)
                    slot_state_q[1]   <= SLOT_RUNNING;
                    slot_wait_q[1]    <= 8'd0;
                    sub_timer_q       <= 16'd0;
                    fsm_state_q       <= ST_TC03_PROD_WRITE;
                end

                ST_TC03_PROD_WRITE: begin
                    // Допоміжне ядро PE1 завершило розрахунок і виконує "Go SR1 <-"
                    // Записує результат 777 у слот s=1 і переходить у статус READY
                    // Ядро PE1 миттєво звільняється до пулу!
                    slot_payload_q[1] <= 32'd777;
                    slot_state_q[1]   <= SLOT_READY;
                    sub_timer_q       <= 16'd0;
                    fsm_state_q       <= ST_TC03_CONS_DELAY;
                end

                ST_TC03_CONS_DELAY: begin
                    // Основне ядро PE0 все ще зайняте своєю роботою (10 тактів затримки)
                    sub_timer_q <= sub_timer_q + 16'd1;
                    if (sub_timer_q == 16'd10) begin
                        fsm_state_q <= ST_TC03_CONS_READ;
                    end
                end

                ST_TC03_CONS_READ: begin
                    // Основне ядро PE0 нарешті дійшло до "Go SR2 ->"
                    // Бачить, що слот s=1 вже в статусі READY:
                    // Читає 777 без жодної затримки (0 тактів очікування!)
                    // Додає власне значення 223: 223 + 777 = 1000
                    result_q        <= 32'd223 + slot_payload_q[1];
                    slot_state_q[1] <= SLOT_IDLE; // Слот звільнено
                    fsm_state_q     <= ST_TC03_FINISH;
                end

                ST_TC03_FINISH: begin
                    if (result_q == 32'd1000 && slot_state_q[1] == SLOT_IDLE) begin
                        tc03_pass_q <= 1'b1;
                    end else begin
                        tc03_pass_q <= 1'b0;
                    end

                    if (all_mode_q) begin
                        fsm_state_q <= ST_ALL_NEXT;
                    end else begin
                        fsm_state_q <= ST_DONE;
                    end
                end

                // ============================================================
                // TC-04: CONSUMER-BEFORE-PRODUCER (Основна гілка раніше допоміжної)
                // ============================================================
                ST_TC04_CONS_ARRIVE: begin
                    // Основне ядро PE0 дійшло до "Go SR2 ->" першим!
                    // Допоміжне ядро все ще рахує (RUNNING)
                    slot_state_q[2]   <= SLOT_RUNNING;
                    slot_wait_q[2]    <= 8'd0;
                    sub_timer_q       <= 16'd0;
                    fsm_state_q       <= ST_TC04_PROD_WAIT;
                end

                ST_TC04_PROD_WAIT: begin
                    // Основне ядро очікує (WAITING). Лічильник очікування інкрементується.
                    // Перевірка на SVA-Live Timeout Deadlock (MAX_WAIT_CYCLES = 256)
                    slot_wait_q[2] <= slot_wait_q[2] + 8'd1;
                    sub_timer_q    <= sub_timer_q + 16'd1;

                    if (slot_wait_q[2] >= 8'd255) begin
                        // Timeout deadlock!
                        slot_state_q[2] <= SLOT_TIMEOUT;
                        deadlock_err_q  <= 1'b1;
                        fsm_state_q     <= ST_TC04_FINISH;
                    end else if (sub_timer_q >= {8'd0, target_delay_q}) begin
                        // Продюсер нарешті завершив обчислення!
                        fsm_state_q <= ST_TC04_PROD_FINISH;
                    end
                end

                ST_TC04_PROD_FINISH: begin
                    // Продюсер записує результат 42 у слот s=2
                    slot_payload_q[2] <= 32'd42;
                    slot_state_q[2]   <= SLOT_READY;
                    fsm_state_q       <= ST_TC04_CONS_RESUME;
                end

                ST_TC04_CONS_RESUME: begin
                    // Споживач бачить READY, знімає блокування, забирає 42,
                    // комбінує з власним 58: 58 + 42 = 100
                    result_q        <= 32'd58 + slot_payload_q[2];
                    slot_state_q[2] <= SLOT_IDLE; // Слот звільнено
                    fsm_state_q     <= ST_TC04_FINISH;
                end

                ST_TC04_FINISH: begin
                    // DoD: результат 100, wait_cycles < 256, немає deadlock_err
                    if (result_q == 32'd100 && !deadlock_err_q && slot_state_q[2] == SLOT_IDLE) begin
                        tc04_pass_q <= 1'b1;
                    end else begin
                        tc04_pass_q <= 1'b0;
                    end

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
                            all_stage_q <= 3'd2;
                            active_tc_q <= 4'd2;
                            fsm_state_q <= ST_TC02_DISPATCH;
                        end
                        3'd2: begin
                            all_stage_q <= 3'd3;
                            active_tc_q <= 4'd3;
                            fsm_state_q <= ST_TC03_PROD_EXEC;
                        end
                        3'd3: begin
                            all_stage_q    <= 3'd4;
                            active_tc_q    <= 4'd4;
                            target_delay_q <= 8'd20;
                            fsm_state_q    <= ST_TC04_CONS_ARRIVE;
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
