// ============================================================================
// Апаратне ядро алгоритму Евкліда на базі подій Машини Кузьміна (KPOL)
// Файл: km_euclid_core.sv
// Стандарт: IEEE 1800-2012 SystemVerilog
//
// Семантика МК:
//   Концепт A: [ A_ > B -= B ]
//   Концепт B: [ B_ > A -= A ]
//
// Трьохфазний реактивний цикл (3 такти на подію):
//   1. EVAL   (1 такт) : обчислення предикатів (A > B, B > A, A == B)
//   2. EXEC   (1 такт) : операція Do-Sub (A <= A - B або B <= B - A)
//   3. COMMIT (1 такт) : фіксація концепту та генерація події для підписника
//
// Цільовий бенчмарк Nod(120, 6):
//   19 ітерацій віднімання * 3 такти + 1 фінальний такт EVAL = 58 тактів (0.58 мкс @ 100 МГц)
// ============================================================================
`timescale 1ns/1ps

module km_euclid_core #(
    parameter int DATA_WIDTH = 32
)(
    input  logic                   clk,
    input  logic                   rst_n,

    // Інтерфейс запуску та налаштування
    input  logic                   start_i,
    input  logic [DATA_WIDTH-1:0]  a_init_i,
    input  logic [DATA_WIDTH-1:0]  b_init_i,

    // Інтерфейс статусу та результатів
    output logic                   busy_o,
    output logic                   done_o,
    output logic                   error_o,
    output logic [DATA_WIDTH-1:0]  result_o,
    output logic [15:0]            iterations_o,
    output logic [31:0]            cycle_count_o,

    // Поточні спостережувані стани концептів A та B
    output logic [DATA_WIDTH-1:0]  concept_a_o,
    output logic [DATA_WIDTH-1:0]  concept_b_o
);

    typedef enum logic [1:0] {
        ST_IDLE   = 2'd0,
        ST_EVAL   = 2'd1,
        ST_EXEC   = 2'd2,
        ST_COMMIT = 2'd3
    } state_t;

    state_t state_q;

    logic [DATA_WIDTH-1:0] reg_a_q;
    logic [DATA_WIDTH-1:0] reg_b_q;
    logic [DATA_WIDTH-1:0] next_val_q;
    logic                  target_is_a_q;

    logic [15:0] iter_cnt_q;
    logic [31:0] cyc_cnt_q;
    logic        done_q;
    logic        error_q;
    logic [DATA_WIDTH-1:0] result_q;

    assign concept_a_o   = reg_a_q;
    assign concept_b_o   = reg_b_q;
    assign busy_o        = (state_q != ST_IDLE);
    assign done_o        = done_q;
    assign error_o       = error_q;
    assign result_o      = result_q;
    assign iterations_o  = iter_cnt_q;
    assign cycle_count_o = cyc_cnt_q;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q       <= ST_IDLE;
            reg_a_q       <= '0;
            reg_b_q       <= '0;
            next_val_q    <= '0;
            target_is_a_q <= 1'b0;
            iter_cnt_q    <= 16'd0;
            cyc_cnt_q     <= 32'd0;
            done_q        <= 1'b0;
            error_q       <= 1'b0;
            result_q      <= '0;
        end else begin
            case (state_q)
                ST_IDLE: begin
                    if (start_i) begin
                        done_q     <= 1'b0;
                        error_q    <= 1'b0;
                        cyc_cnt_q  <= 32'd0;
                        iter_cnt_q <= 16'd0;

                        if (a_init_i == '0 || b_init_i == '0) begin
                            // Некоректні вхідні дані (0 не має сенсу для НСД у даній постановці)
                            error_q  <= 1'b1;
                            done_q   <= 1'b1;
                            result_q <= '0;
                            state_q  <= ST_IDLE;
                        end else begin
                            reg_a_q <= a_init_i;
                            reg_b_q <= b_init_i;
                            state_q <= ST_EVAL;
                        end
                    end
                end

                ST_EVAL: begin
                    cyc_cnt_q <= cyc_cnt_q + 32'd1;

                    // Фаза 1: Оцінка предикатів відношення
                    if (reg_a_q == reg_b_q) begin
                        // Збіжність знайдена (A == B)
                        result_q <= reg_a_q;
                        done_q   <= 1'b1;
                        state_q  <= ST_IDLE;
                    end else if (reg_a_q > reg_b_q) begin
                        // Предикат: A > B істинний -> підписка [ A_ > B -= B ]
                        target_is_a_q <= 1'b1;
                        state_q       <= ST_EXEC;
                    end else begin
                        // Предикат: B > A істинний -> підписка [ B_ > A -= A ]
                        target_is_a_q <= 1'b0;
                        state_q       <= ST_EXEC;
                    end
                end

                ST_EXEC: begin
                    cyc_cnt_q <= cyc_cnt_q + 32'd1;

                    // Фаза 2: Обчислення в АЛП
                    if (target_is_a_q) begin
                        next_val_q <= reg_a_q - reg_b_q;
                    end else begin
                        next_val_q <= reg_b_q - reg_a_q;
                    end
                    state_q <= ST_COMMIT;
                end

                ST_COMMIT: begin
                    cyc_cnt_q  <= cyc_cnt_q + 32'd1;
                    iter_cnt_q <= iter_cnt_q + 16'd1;

                    // Фаза 3: Фіксація стану концепту та виклик нової події
                    if (target_is_a_q) begin
                        reg_a_q <= next_val_q;
                    end else begin
                        reg_b_q <= next_val_q;
                    end
                    state_q <= ST_EVAL;
                end

                default: state_q <= ST_IDLE;
            endcase
        end
    end

endmodule
