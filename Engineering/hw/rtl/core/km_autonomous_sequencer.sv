// ============================================================================
// Модуль: km_autonomous_sequencer.sv
// Призначення: Автономний апаратний диспетчер подій Машини Кузьміна (Крок 2).
// Забезпечує виконання транзакцій у PL на частоті 100 МГц без втручання
// процесора ARM та операційної системи Linux (усунення AXI Bottleneck).
// Відповідає нормативній специфікації черги подій (B5, REQ-SYS-013..014,
// REQ-HW-014..016) та архітектурі інтеграції зовнішніх подій (B2, REQ-SYS-011..012).
// ============================================================================
`timescale 1ns / 1ps

module km_autonomous_sequencer #(
    parameter int QUEUE_DEPTH  = 16,
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
    output logic                   hw_trigger_ready_o,

    // Інтерфейс до BRAM Порту B (для автономного читання/запису дескрипторів)
    output logic [ADDR_WIDTH-1:0]  bram_b_addr_o,
    output logic [DATA_WIDTH-1:0]  bram_b_wdata_o,
    output logic [3:0]             bram_b_wstrb_o,
    output logic                   bram_b_we_o,
    input  logic [DATA_WIDTH-1:0]  bram_b_rdata_i,

    // Статусні лічильники, телеметрія та сигнали черги
    input  logic                   clear_overflow_i,
    output logic                   busy_o,
    output logic                   fifo_full_o,
    output logic                   fifo_overflow_o,
    output logic [31:0]            events_dropped_count_o,
    output logic [31:0]            events_processed_count_o,
    output logic [31:0]            committed_count_o,
    output logic [31:0]            rejected_count_o,
    output logic [31:0]            last_committed_state_o,

    // Однотактові строби результату транзакції для зовнішньої індикації/моніторингу
    output logic                   commit_pulse_o,
    output logic                   reject_pulse_o
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
        ST_EVAL_GATE        = 4'd7  // Фіксація рішення вентиля та запис у BRAM
    } seq_state_t;

    seq_state_t state_q;

    // Внутрішня апаратна черга подій
    localparam int PTR_WIDTH = (QUEUE_DEPTH > 1) ? $clog2(QUEUE_DEPTH) : 1;
    localparam logic [31:0]          DEPTH_U32 = QUEUE_DEPTH;
    localparam logic [PTR_WIDTH:0]   DEPTH_CNT = DEPTH_U32[PTR_WIDTH:0];
    localparam logic [31:0]          ONE_U32   = 32'd1;
    localparam logic [PTR_WIDTH-1:0] PTR_ONE   = ONE_U32[PTR_WIDTH-1:0];

    logic [5:0]            fifo_cid_q   [QUEUE_DEPTH];
    logic [DATA_WIDTH-1:0] fifo_param_q [QUEUE_DEPTH];
    logic [PTR_WIDTH-1:0]  fifo_wr_ptr_q;
    logic [PTR_WIDTH-1:0]  fifo_rd_ptr_q;
    logic [PTR_WIDTH:0]    fifo_count_q;

    wire [PTR_WIDTH-1:0] rd_ptr_next1 = (({1'b0, fifo_rd_ptr_q} + {{PTR_WIDTH{1'b0}}, 1'b1}) >= DEPTH_CNT)
                                      ? '0 : (fifo_rd_ptr_q + PTR_ONE);
    wire [PTR_WIDTH-1:0] wr_ptr_next1 = (({1'b0, fifo_wr_ptr_q} + {{PTR_WIDTH{1'b0}}, 1'b1}) >= DEPTH_CNT)
                                      ? '0 : (fifo_wr_ptr_q + PTR_ONE);
    wire [PTR_WIDTH-1:0] wr_ptr_next2 = (({1'b0, wr_ptr_next1} + {{PTR_WIDTH{1'b0}}, 1'b1}) >= DEPTH_CNT)
                                      ? '0 : (wr_ptr_next1 + PTR_ONE);

    // 1-слотовий внутрішній буфер утримання full-каскаду (B5 v2, #151):
    // запобігає втраті каскаду при fifo_count_q == QUEUE_DEPTH без зупинки вичитки FIFO
    // та без повторної фіксації (commit) поточної транзакції у BRAM.
    logic                  cascade_pending_valid_q;
    logic [5:0]            cascade_pending_cid_q;
    logic [DATA_WIDTH-1:0] cascade_pending_param_q;

    // Монітор утримання зовнішнього входу під час hw_trigger_ready_o == 0 (REQ-HW-015):
    // штатне очікування зі стабільними valid/cid/param не рахується втратою;
    // зняття valid або перезапис payload до появи ready == 1 фіксується як втрата незупинного джерела.
    logic                  stalled_ext_q;
    logic [5:0]            stalled_cid_q;
    logic [DATA_WIDTH-1:0] stalled_param_q;

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

    // Статистичні лічильники та статус
    logic [31:0] ev_count_q;
    logic [31:0] comm_count_q;
    logic [31:0] rej_count_q;
    logic [31:0] last_state_q;
    logic [31:0] dropped_count_q;
    logic        overflow_latched_q;

    assign busy_o                   = (state_q != ST_IDLE) || (fifo_count_q != 0) || cascade_pending_valid_q;
    assign events_processed_count_o = ev_count_q;
    assign committed_count_o        = comm_count_q;
    assign rejected_count_o         = rej_count_q;
    assign last_committed_state_o   = last_state_q;
    assign events_dropped_count_o   = dropped_count_q;
    assign fifo_overflow_o          = overflow_latched_q;

    // Однотактові строби результату транзакції на такті фіксації
    assign commit_pulse_o           = (state_q == ST_EVAL_GATE) && cme_committed;
    assign reject_pulse_o           = (state_q == ST_EVAL_GATE) && !cme_committed;

    // Умови запитів до черги та арбітражу каскаду над зовнішнім входом (B5 v2, REQ-SYS-014, REQ-HW-014)
    wire dequeue_req   = (state_q == ST_IDLE) && (fifo_count_q > 0);
    wire cascade_req   = (state_q == ST_EVAL_GATE) && cme_committed &&
                         cme_trigger_subscriber && (cme_subscriber_cid[5:0] != active_cid_q);
    wire cascade_valid = cascade_pending_valid_q || cascade_req;
    wire [5:0]            cascade_cid   = cascade_pending_valid_q ? cascade_pending_cid_q
                                                                  : cme_subscriber_cid[5:0];
    wire [DATA_WIDTH-1:0] cascade_param = cascade_pending_valid_q ? cascade_pending_param_q
                                                                  : cme_updated_state;

    wire [PTR_WIDTH+1:0] ext_slots_needed = cascade_req
        ? {{PTR_WIDTH{1'b0}}, 2'd2}
        : {{PTR_WIDTH{1'b0}}, 2'd1};

    // Сигнал готовності враховує резервування слота під активний або утриманий каскад:
    // при 1 вільному слоті та одночасному cascade_req сигнал ready опускається у 0 до фронту.
    assign hw_trigger_ready_o       = !cascade_pending_valid_q &&
                                      (({1'b0, fifo_count_q} + ext_slots_needed) <= {1'b0, DEPTH_CNT});
    assign fifo_full_o              = (fifo_count_q == DEPTH_CNT);

    wire cascade_enq = cascade_valid && ((fifo_count_q < DEPTH_CNT) || dequeue_req);
    wire ext_accept  = hw_trigger_valid_i && hw_trigger_ready_o;
    wire same_stalled_payload = (hw_trigger_cid_i == stalled_cid_q) &&
                                (hw_trigger_param_i == stalled_param_q);

    wire [PTR_WIDTH:0] enq_delta = (cascade_enq && ext_accept) ? {{(PTR_WIDTH-1){1'b0}}, 2'd2}
                                 : ((cascade_enq || ext_accept) ? {{PTR_WIDTH{1'b0}}, 1'b1} : '0);
    wire [PTR_WIDTH:0] deq_delta = dequeue_req ? {{PTR_WIDTH{1'b0}}, 1'b1} : '0;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q                 <= ST_IDLE;
            bram_b_addr_o           <= '0;
            bram_b_wdata_o          <= '0;
            bram_b_wstrb_o          <= 4'b0000;
            bram_b_we_o             <= 1'b0;
            cme_event_valid         <= 1'b0;

            fifo_wr_ptr_q           <= '0;
            fifo_rd_ptr_q           <= '0;
            fifo_count_q            <= '0;

            cascade_pending_valid_q <= 1'b0;
            cascade_pending_cid_q   <= '0;
            cascade_pending_param_q <= '0;

            stalled_ext_q           <= 1'b0;
            stalled_cid_q           <= '0;
            stalled_param_q         <= '0;

            active_cid_q            <= '0;
            active_param_q          <= '0;
            desc_w0_q               <= '0;
            desc_w1_q               <= '0;
            desc_w2_q               <= '0;
            desc_w3_q               <= '0;

            ev_count_q              <= 32'd0;
            comm_count_q            <= 32'd0;
            rej_count_q             <= 32'd0;
            last_state_q            <= 32'd0;
            dropped_count_q         <= 32'd0;
            overflow_latched_q      <= 1'b0;
        end else begin
            // За замовчуванням деактивуємо строби
            bram_b_we_o     <= 1'b0;
            cme_event_valid <= 1'b0;

            // ================================================================
            // 1. УПРАВЛІННЯ ЧЕРГОЮ FIFO (Арбітраж: Каскад > Зовнішній тригер)
            // ================================================================
            if (dequeue_req) begin
                fifo_rd_ptr_q <= rd_ptr_next1;
            end

            if (cascade_enq && ext_accept) begin
                // Наявні >= 2 вільні слоти: каскад стає першим, зовнішня подія — слідом
                fifo_cid_q[fifo_wr_ptr_q]    <= cascade_cid;
                fifo_param_q[fifo_wr_ptr_q]  <= cascade_param;
                fifo_cid_q[wr_ptr_next1]     <= hw_trigger_cid_i;
                fifo_param_q[wr_ptr_next1]   <= hw_trigger_param_i;
                fifo_wr_ptr_q                <= wr_ptr_next2;
                cascade_pending_valid_q      <= 1'b0;
            end else if (cascade_enq) begin
                fifo_cid_q[fifo_wr_ptr_q]   <= cascade_cid;
                fifo_param_q[fifo_wr_ptr_q] <= cascade_param;
                fifo_wr_ptr_q               <= wr_ptr_next1;
                cascade_pending_valid_q     <= 1'b0;
            end else if (ext_accept) begin
                fifo_cid_q[fifo_wr_ptr_q]   <= hw_trigger_cid_i;
                fifo_param_q[fifo_wr_ptr_q] <= hw_trigger_param_i;
                fifo_wr_ptr_q               <= wr_ptr_next1;
            end else if (cascade_req) begin
                // Черга повна без одночасної вичитки (full-каскад у ST_EVAL_GATE):
                // утримуємо каскад у 1-слотовому регістрі до наступного такту ST_IDLE,
                // де dequeue_req гарантовано звільнить слот у FIFO.
                cascade_pending_valid_q <= 1'b1;
                cascade_pending_cid_q   <= cme_subscriber_cid[5:0];
                cascade_pending_param_q <= cme_updated_state;
            end

            fifo_count_q <= fifo_count_q + enq_delta - deq_delta;

            // Моніторинг протоколу утримання на зовнішньому вході (REQ-SYS-013, REQ-HW-015)
            if (!stalled_ext_q) begin
                if (hw_trigger_valid_i && !hw_trigger_ready_o) begin
                    stalled_ext_q   <= 1'b1;
                    stalled_cid_q   <= hw_trigger_cid_i;
                    stalled_param_q <= hw_trigger_param_i;
                end
            end else begin
                if (!hw_trigger_valid_i) begin
                    // Незупинне джерело зняло valid до появи ready == 1 -> фактична втрата події
                    overflow_latched_q <= 1'b1;
                    dropped_count_q    <= dropped_count_q + 32'd1;
                    stalled_ext_q      <= 1'b0;
                end else if (!same_stalled_payload) begin
                    // Незупинне джерело перезаписало неприйняту подію новою
                    overflow_latched_q <= 1'b1;
                    dropped_count_q    <= dropped_count_q + 32'd1;
                    if (hw_trigger_ready_o) begin
                        stalled_ext_q <= 1'b0;
                    end else begin
                        stalled_ext_q   <= 1'b1;
                        stalled_cid_q   <= hw_trigger_cid_i;
                        stalled_param_q <= hw_trigger_param_i;
                    end
                end else if (hw_trigger_ready_o) begin
                    // Кероване джерело коректно утримало подію до прийняття — 0 втрат
                    stalled_ext_q <= 1'b0;
                end
            end

            if (clear_overflow_i && !busy_o) begin
                overflow_latched_q <= 1'b0;
                dropped_count_q    <= 32'd0;
                stalled_ext_q      <= 1'b0;
            end

            // ================================================================
            // 2. СКІНЧЕННИЙ АВТОМАТ ДИСПЕТЧЕРА (FSM)
            // ================================================================
            case (state_q)
                ST_IDLE: begin
                    if (fifo_count_q > 0) begin
                        active_cid_q   <= fifo_cid_q[fifo_rd_ptr_q];
                        active_param_q <= fifo_param_q[fifo_rd_ptr_q];

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
                    // BRAM видає Word 0 на цьому такті
                    desc_w0_q     <= bram_b_rdata_i;
                    bram_b_addr_o <= {active_cid_q, 2'b10}; // Подаємо адресу Word 2
                    state_q       <= ST_REQ_W2;
                end

                ST_REQ_W2: begin
                    // BRAM видає Word 1 на цьому такті
                    desc_w1_q     <= bram_b_rdata_i;
                    bram_b_addr_o <= {active_cid_q, 2'b11}; // Подаємо адресу Word 3
                    state_q       <= ST_REQ_W3;
                end

                ST_REQ_W3: begin
                    // BRAM видає Word 2 на цьому такті
                    desc_w2_q     <= bram_b_rdata_i;
                    state_q       <= ST_CAP_W3_STROBE;
                end

                ST_CAP_W3_STROBE: begin
                    // BRAM видає Word 3 на цьому такті
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
