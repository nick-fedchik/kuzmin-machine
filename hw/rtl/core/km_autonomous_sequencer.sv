// ============================================================================
// Модуль: km_autonomous_sequencer.sv
// Призначення: Автономний апаратний диспетчер подій Машини Кузьміна (Крок 2).
// Забезпечує виконання транзакцій у PL на частоті 100 МГц без втручання
// процесора ARM та операційної системи Linux (усунення AXI Bottleneck).
// ============================================================================
`timescale 1ns / 1ps

module km_autonomous_sequencer #(
    parameter int NUM_CONCEPTS = 64,
    parameter int DATA_WIDTH   = 32,
    parameter int ADDR_WIDTH   = 8
)(
    input  logic                   clk,
    input  logic                   rst_n,

    // Зовнішній апаратний тригер події (фізичний пін GPIO або таймер)
    input  logic                   hw_trigger_valid_i,
    input  logic [5:0]             hw_trigger_cid_i,
    input  logic [DATA_WIDTH-1:0]  hw_trigger_param_i,

    // Інтерфейс до BRAM Порту B (для автономного читання/запису дескрипторів)
    output logic [ADDR_WIDTH-1:0]  bram_b_addr_o,
    output logic [DATA_WIDTH-1:0]  bram_b_wdata_o,
    output logic [3:0]             bram_b_wstrb_o,
    output logic                   bram_b_we_o,
    input  logic [DATA_WIDTH-1:0]  bram_b_rdata_i,

    // Статусні лічильники та телеметрія
    output logic                   busy_o,
    output logic [31:0]            events_processed_count_o,
    output logic [31:0]            committed_count_o,
    output logic [31:0]            rejected_count_o,
    output logic [31:0]            last_committed_state_o
);

    // Скінченний автомат автономного диспетчера
    typedef enum logic [3:0] {
        ST_IDLE             = 4'd0,
        ST_REQ_W0           = 4'd1, // Запит Word 0
        ST_REQ_W1           = 4'd2, // Запит Word 1
        ST_REQ_W2           = 4'd3, // Запит Word 2 (захоплення Word 0)
        ST_REQ_W3           = 4'd4, // Запит Word 3 (захоплення Word 1)
        ST_CAP_W3_STROBE    = 4'd5, // Захоплення Word 3 та виставлення cme_event_valid
        ST_WAIT_GATE        = 4'd6, // Очікування такту спрацьовування шлюзу
        ST_EVAL_GATE        = 4'd7, // Фіксація рішення вентиля
        ST_WRITE_BACK_STATE = 4'd8, // Запис оновленого стану у BRAM при commit
        ST_CHECK_CASCADE    = 4'd9  // Каскадне додавання підписника в чергу
    } seq_state_t;

    seq_state_t state_q;

    // Внутрішня апаратна черга подій (FIFO на 16 елементів для каскадів)
    logic [5:0]            fifo_cid_q [16];
    logic [DATA_WIDTH-1:0] fifo_param_q [16];
    logic [3:0]            fifo_wr_ptr_q;
    logic [3:0]            fifo_rd_ptr_q;
    logic [4:0]            fifo_count_q;

    // Регістри активної події
    logic [5:0]            active_cid_q;
    logic [DATA_WIDTH-1:0] active_param_q;

    // Буфер 128-бітного дескриптора концепту
    logic [31:0] desc_w0_q; // state
    logic [31:0] desc_w1_q; // operand
    logic [31:0] desc_w2_q; // opcodes/guards
    logic [31:0] desc_w3_q; // subscriber_cid

    wire [127:0] active_descriptor_w = {desc_w3_q, desc_w2_q, desc_w1_q, desc_w0_q};

    // Інстанціювання Concept Micro-Engine (CME)
    logic                  cme_event_valid;
    wire                   cme_committed;
    wire                   cme_rejected;
    wire                   cme_hazard_obs;
    wire                   cme_unknown_haz;
    wire [DATA_WIDTH-1:0]  cme_updated_state;
    wire                   cme_state_changed;
    wire [31:0]            cme_subscriber_cid;
    wire                   cme_trigger_subscriber;

    km_concept_micro_engine #(
        .DATA_WIDTH(DATA_WIDTH)
    ) cme_inst (
        .clk(clk),
        .rst_n(rst_n),
        .event_valid_i(cme_event_valid),
        .event_id_i(8'h01),
        .event_param_i(active_param_q),
        .descriptor_i(active_descriptor_w),
        .committed_o(cme_committed),
        .rejected_o(cme_rejected),
        .hazard_observed_o(cme_hazard_obs),
        .unknown_hazard_o(cme_unknown_haz),
        .updated_state_o(cme_updated_state),
        .state_changed_o(cme_state_changed),
        .subscriber_cid_o(cme_subscriber_cid),
        .trigger_subscriber_o(cme_trigger_subscriber)
    );

    // Статистичні лічильники
    logic [31:0] ev_count_q;
    logic [31:0] comm_count_q;
    logic [31:0] rej_count_q;
    logic [31:0] last_state_q;

    assign busy_o                   = (state_q != ST_IDLE) || (fifo_count_q != 0);
    assign events_processed_count_o = ev_count_q;
    assign committed_count_o        = comm_count_q;
    assign rejected_count_o         = rej_count_q;
    assign last_committed_state_o   = last_state_q;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q         <= ST_IDLE;
            bram_b_addr_o   <= '0;
            bram_b_wdata_o  <= '0;
            bram_b_wstrb_o  <= 4'b0000;
            bram_b_we_o     <= 1'b0;
            cme_event_valid <= 1'b0;

            fifo_wr_ptr_q   <= '0;
            fifo_rd_ptr_q   <= '0;
            fifo_count_q    <= '0;

            active_cid_q    <= '0;
            active_param_q  <= '0;
            desc_w0_q       <= '0;
            desc_w1_q       <= '0;
            desc_w2_q       <= '0;
            desc_w3_q       <= '0;

            ev_count_q      <= 32'd0;
            comm_count_q    <= 32'd0;
            rej_count_q     <= 32'd0;
            last_state_q    <= 32'd0;
        end else begin
            // За замовчуванням деактивуємо строби запису
            bram_b_we_o     <= 1'b0;
            cme_event_valid <= 1'b0;

            // Прийом зовнішнього тригера у чергу FIFO
            if (hw_trigger_valid_i && (fifo_count_q < 16)) begin
                fifo_cid_q[fifo_wr_ptr_q]   <= hw_trigger_cid_i;
                fifo_param_q[fifo_wr_ptr_q] <= hw_trigger_param_i;
                fifo_wr_ptr_q               <= (fifo_wr_ptr_q + 1) % 16;
                fifo_count_q                <= fifo_count_q + 1;
            end

            case (state_q)
                ST_IDLE: begin
                    if (fifo_count_q > 0) begin
                        active_cid_q   <= fifo_cid_q[fifo_rd_ptr_q];
                        active_param_q <= fifo_param_q[fifo_rd_ptr_q];
                        fifo_rd_ptr_q  <= (fifo_rd_ptr_q + 1) % 16;
                        fifo_count_q   <= fifo_count_q - 1;

                        // Подаємо адресу Word 0
                        bram_b_addr_o  <= {fifo_cid_q[fifo_rd_ptr_q], 2'b00};
                        state_q        <= ST_REQ_W0;
                    end
                end

                ST_REQ_W0: begin
                    // BRAM семплює addr W0 на цьому такті
                    bram_b_addr_o <= {active_cid_q, 2'b01}; // Подаємо адресу Word 1
                    state_q       <= ST_REQ_W1;
                end

                ST_REQ_W1: begin
                    // BRAM видає Word 0 на цьому такті!
                    desc_w0_q     <= bram_b_rdata_i;
                    bram_b_addr_o <= {active_cid_q, 2'b10}; // Подаємо адресу Word 2
                    state_q       <= ST_REQ_W2;
                end

                ST_REQ_W2: begin
                    // BRAM видає Word 1 на цьому такті!
                    desc_w1_q     <= bram_b_rdata_i;
                    bram_b_addr_o <= {active_cid_q, 2'b11}; // Подаємо адресу Word 3
                    state_q       <= ST_REQ_W3;
                end

                ST_REQ_W3: begin
                    // BRAM видає Word 2 на цьому такті!
                    desc_w2_q     <= bram_b_rdata_i;
                    state_q       <= ST_CAP_W3_STROBE;
                end

                ST_CAP_W3_STROBE: begin
                    // BRAM видає Word 3 на цьому такті!
                    desc_w3_q       <= bram_b_rdata_i;
                    cme_event_valid <= 1'b1;
                    state_q         <= ST_WAIT_GATE;
                end

                ST_WAIT_GATE: begin
                    // Шлюз kpol_txn_gate_v2 опрацьовує строб на цьому такті
                    cme_event_valid <= 1'b0;
                    state_q         <= ST_EVAL_GATE;
                end

                ST_EVAL_GATE: begin
                    ev_count_q <= ev_count_q + 32'd1;

                    if (cme_committed) begin
                        comm_count_q <= comm_count_q + 32'd1;
                        last_state_q <= cme_updated_state;

                        // Якщо у концепту є підписник, додаємо його в чергу прямо на такті валідного рішення
                        if (cme_trigger_subscriber && (cme_subscriber_cid[5:0] != active_cid_q)) begin
                            if (fifo_count_q < 16) begin
                                fifo_cid_q[fifo_wr_ptr_q]   <= cme_subscriber_cid[5:0];
                                fifo_param_q[fifo_wr_ptr_q] <= cme_updated_state;
                                fifo_wr_ptr_q               <= (fifo_wr_ptr_q + 1) % 16;
                                fifo_count_q                <= fifo_count_q + 1;
                            end
                        end

                        // Запис оновленого стану у Word 0 концепту в BRAM
                        bram_b_addr_o  <= {active_cid_q, 2'b00};
                        bram_b_wdata_o <= cme_updated_state;
                        bram_b_wstrb_o <= 4'b1111;
                        bram_b_we_o    <= 1'b1;

                        state_q <= ST_IDLE;
                    end else begin
                        rej_count_q <= rej_count_q + 32'd1;
                        state_q     <= ST_IDLE; // Відхилена транзакція не оновлює пам'ять
                    end
                end

                default: state_q <= ST_IDLE;
            endcase
        end
    end

endmodule
