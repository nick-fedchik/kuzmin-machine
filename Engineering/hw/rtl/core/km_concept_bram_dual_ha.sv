// ============================================================================
// Двобанкова обгортка таблиці дескрипторів концептів (CFG-P-HA, B4 Варіант 2)
// Файл: km_concept_bram_dual_ha.sv
// Стандарт: IEEE 1800-2012 SystemVerilog
//
// Призначення (Issue #252, EXP-GPU-02):
//   Забезпечує онлайнове оновлення 128-бітних дескрипторів правил (W1..W3 та
//   опційно ініціалізаційного стану W0) у тіньовому банку Block RAM під час
//   активної роботи 8-тактового секвенсера без розірваного читання (torn-read),
//   без колізій портів BRAM, без втрати живих станів W0 та без жодного такту
//   додаткової затримки основного контуру реакції.
// ============================================================================
`timescale 1ns/1ps

module km_concept_bram_dual_ha #(
    parameter int NUM_CONCEPTS = 64,
    parameter int DATA_WIDTH   = 32,
    parameter int ADDR_WIDTH   = 8   // NUM_CONCEPTS * 4 слів
)(
    input  logic                   clk,
    input  logic                   rst_n,

    // Порт A хоста (AXI4-Lite конфігуратор / онлайн-інжектор)
    input  logic [ADDR_WIDTH-1:0]  a_addr_i,
    input  logic [DATA_WIDTH-1:0]  a_wdata_i,
    input  logic [3:0]             a_wstrb_i,
    input  logic                   a_we_i,
    input  logic                   a_shadow_only_i,
    input  logic                   a_read_shadow_i,
    output logic [DATA_WIDTH-1:0]  a_rdata_o,

    // Керування атомарним перемиканням активного банку
    input  logic                   swap_req_i,
    input  logic                   seq_at_idle_boundary_i,

    // Порт B автономного секвенсера
    input  logic [ADDR_WIDTH-1:0]  b_addr_i,
    input  logic [DATA_WIDTH-1:0]  b_wdata_i,
    input  logic [3:0]             b_wstrb_i,
    input  logic                   b_we_i,
    output logic [DATA_WIDTH-1:0]  b_rdata_o,

    // Статусні та стробові виходи протоколу EXP-GPU-02
    output logic                   active_bank_o,
    output logic                   swap_pending_o,
    output logic                   sync_busy_o,
    output logic                   inject_strobe_o,
    output logic                   bank_swap_commit_o,
    output logic                   collision_detected_o
);

    localparam int WORDS_TOTAL = NUM_CONCEPTS * 4;
    localparam int CID_WIDTH   = ADDR_WIDTH - 2;

    typedef enum logic [1:0] {
        SYNC_IDLE  = 2'd0,
        SYNC_READ  = 2'd1,
        SYNC_WRITE = 2'd2
    } sync_state_t;

    logic                     active_bank_q;
    logic                     swap_pending_q;
    sync_state_t              sync_state_q;
    logic [ADDR_WIDTH-1:0]    sync_addr_q;
    logic [WORDS_TOTAL-1:0]   dirty_word_q;
    logic [NUM_CONCEPTS-1:0]  shadow_w0_override_q;
    logic                     inject_session_started_q;
    logic                     inject_strobe_q;
    logic                     bank_swap_commit_q;

    wire sync_busy_w = (sync_state_q != SYNC_IDLE);

    assign active_bank_o      = active_bank_q;
    assign swap_pending_o     = swap_pending_q;
    assign sync_busy_o        = sync_busy_w;
    assign inject_strobe_o    = inject_strobe_q;
    assign bank_swap_commit_o = bank_swap_commit_q;

    // Прийняття операцій керування на Порту A
    wire sync_load_accept  = a_we_i && !a_shadow_only_i && !swap_pending_q && !sync_busy_w && !b_we_i;
    wire swap_req_accept   = swap_req_i && !swap_pending_q && !sync_busy_w && !sync_load_accept;
    wire hot_write_accept  = a_we_i && a_shadow_only_i && !swap_pending_q && !sync_busy_w && !swap_req_accept;
    wire swap_commit_w     = (swap_pending_q || swap_req_accept) && seq_at_idle_boundary_i;

    wire [CID_WIDTH-1:0] a_cid_w = a_addr_i[ADDR_WIDTH-1:2];
    wire [CID_WIDTH-1:0] b_cid_w = b_addr_i[ADDR_WIDTH-1:2];

    // Дані з виходів Порту A обох банків
    wire [DATA_WIDTH-1:0] bank0_a_rdata;
    wire [DATA_WIDTH-1:0] bank1_a_rdata;
    wire [DATA_WIDTH-1:0] bank0_b_rdata;
    wire [DATA_WIDTH-1:0] bank1_b_rdata;
    wire                  bank0_col;
    wire                  bank1_col;

    assign collision_detected_o = bank0_col | bank1_col;

    wire [DATA_WIDTH-1:0] act_a_rdata_w = active_bank_q ? bank1_a_rdata : bank0_a_rdata;
    wire [DATA_WIDTH-1:0] sh_a_rdata_w  = active_bank_q ? bank0_a_rdata : bank1_a_rdata;

    assign a_rdata_o = a_read_shadow_i ? sh_a_rdata_w : act_a_rdata_w;
    assign b_rdata_o = active_bank_q   ? bank1_b_rdata : bank0_b_rdata;

    // Побайтове злиття для випадку одночасного часткового запису Port B у такті SYNC_WRITE
    logic [DATA_WIDTH-1:0] sync_merged_wdata_w;
    always_comb begin
        sync_merged_wdata_w[ 7: 0] = b_wstrb_i[0] ? b_wdata_i[ 7: 0] : act_a_rdata_w[ 7: 0];
        sync_merged_wdata_w[15: 8] = b_wstrb_i[1] ? b_wdata_i[15: 8] : act_a_rdata_w[15: 8];
        sync_merged_wdata_w[23:16] = b_wstrb_i[2] ? b_wdata_i[23:16] : act_a_rdata_w[23:16];
        sync_merged_wdata_w[31:24] = b_wstrb_i[3] ? b_wdata_i[31:24] : act_a_rdata_w[31:24];
    end

    // Комутація активного та тіньового сигналів Порту A
    logic [ADDR_WIDTH-1:0] act_a_addr_w;
    logic [DATA_WIDTH-1:0] act_a_wdata_w;
    logic [3:0]            act_a_wstrb_w;
    logic                  act_a_we_w;

    logic [ADDR_WIDTH-1:0] sh_a_addr_w;
    logic [DATA_WIDTH-1:0] sh_a_wdata_w;
    logic [3:0]            sh_a_wstrb_w;
    logic                  sh_a_we_w;

    wire sync_write_b_same_addr = (sync_state_q == SYNC_WRITE) && b_we_i && (b_addr_i == sync_addr_q);
    wire sync_write_b_full_win  = sync_write_b_same_addr && (b_wstrb_i == 4'hf);

    always_comb begin
        // Активний банк, Порт A: пише лише при початковому синхронному завантаженні (!busy)
        act_a_addr_w  = (sync_state_q == SYNC_READ) ? sync_addr_q : a_addr_i;
        act_a_wdata_w = a_wdata_i;
        act_a_wstrb_w = a_wstrb_i;
        act_a_we_w    = sync_load_accept;

        // Тіньовий банк, Порт A: пише при sync_load, hot_write або SYNC_WRITE
        if (sync_state_q == SYNC_WRITE) begin
            sh_a_addr_w  = sync_addr_q;
            sh_a_wdata_w = sync_write_b_same_addr ? sync_merged_wdata_w : act_a_rdata_w;
            sh_a_wstrb_w = 4'hf;
            // Якщо Port B одночасно пише повне слово 4'hf у ту саму адресу, свіжіший Port B перемагає
            sh_a_we_w    = !sync_write_b_full_win;
        end else begin
            sh_a_addr_w  = a_addr_i;
            sh_a_wdata_w = a_wdata_i;
            sh_a_wstrb_w = a_wstrb_i;
            sh_a_we_w    = sync_load_accept || hot_write_accept;
        end
    end

    // Комутація сигналів Порту B (дзеркалювання живих станів без колізій з Портом A)
    wire act_b_we_w = b_we_i;
    wire sh_b_we_w  = b_we_i && !((b_addr_i[1:0] == 2'b00) && shadow_w0_override_q[b_cid_w]) &&
                      !(sh_a_we_w && (sh_a_addr_w == b_addr_i));

    // Розведення на фізичні банки bank0 та bank1 залежно від active_bank_q
    wire [ADDR_WIDTH-1:0] bank0_a_addr  = active_bank_q ? sh_a_addr_w  : act_a_addr_w;
    wire [DATA_WIDTH-1:0] bank0_a_wdata = active_bank_q ? sh_a_wdata_w : act_a_wdata_w;
    wire [3:0]            bank0_a_wstrb = active_bank_q ? sh_a_wstrb_w : act_a_wstrb_w;
    wire                  bank0_a_we    = active_bank_q ? sh_a_we_w    : act_a_we_w;
    wire                  bank0_b_we    = active_bank_q ? sh_b_we_w    : act_b_we_w;

    wire [ADDR_WIDTH-1:0] bank1_a_addr  = active_bank_q ? act_a_addr_w  : sh_a_addr_w;
    wire [DATA_WIDTH-1:0] bank1_a_wdata = active_bank_q ? act_a_wdata_w : sh_a_wdata_w;
    wire [3:0]            bank1_a_wstrb = active_bank_q ? act_a_wstrb_w : sh_a_wstrb_w;
    wire                  bank1_a_we    = active_bank_q ? act_a_we_w    : sh_a_we_w;
    wire                  bank1_b_we    = active_bank_q ? act_b_we_w    : sh_b_we_w;

    km_concept_bram #(
        .NUM_CONCEPTS(NUM_CONCEPTS),
        .DATA_WIDTH(DATA_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) bank0 (
        .clk(clk),
        .rst_n(rst_n),
        .a_addr_i(bank0_a_addr),
        .a_wdata_i(bank0_a_wdata),
        .a_wstrb_i(bank0_a_wstrb),
        .a_we_i(bank0_a_we),
        .a_rdata_o(bank0_a_rdata),
        .b_addr_i(b_addr_i),
        .b_wdata_i(b_wdata_i),
        .b_wstrb_i(b_wstrb_i),
        .b_we_i(bank0_b_we),
        .b_rdata_o(bank0_b_rdata),
        .collision_detected_o(bank0_col)
    );

    km_concept_bram #(
        .NUM_CONCEPTS(NUM_CONCEPTS),
        .DATA_WIDTH(DATA_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) bank1 (
        .clk(clk),
        .rst_n(rst_n),
        .a_addr_i(bank1_a_addr),
        .a_wdata_i(bank1_a_wdata),
        .a_wstrb_i(bank1_a_wstrb),
        .a_we_i(bank1_a_we),
        .a_rdata_o(bank1_a_rdata),
        .b_addr_i(b_addr_i),
        .b_wdata_i(b_wdata_i),
        .b_wstrb_i(b_wstrb_i),
        .b_we_i(bank1_b_we),
        .b_rdata_o(bank1_b_rdata),
        .collision_detected_o(bank1_col)
    );

    // Обчислення наступної бітової маски змінених слів та пошук першого dirty-слова
    logic [WORDS_TOTAL-1:0] dirty_next_w;
    logic                   next_has_dirty_w;
    logic [ADDR_WIDTH-1:0]  next_dirty_addr_w;

    always_comb begin
        dirty_next_w = dirty_word_q;

        if (sync_load_accept) begin
            if (a_wstrb_i == 4'hf) begin
                dirty_next_w[a_addr_i] = 1'b0;
            end
        end else if (hot_write_accept) begin
            dirty_next_w[a_addr_i] = 1'b1;
        end else if (sync_busy_w) begin
            if (sync_state_q == SYNC_WRITE) begin
                dirty_next_w[sync_addr_q] = 1'b0;
            end
            if (b_we_i && (b_wstrb_i == 4'hf)) begin
                dirty_next_w[b_addr_i] = 1'b0;
            end
        end

        next_has_dirty_w  = 1'b0;
        next_dirty_addr_w = '0;
        for (int idx = 0; idx < WORDS_TOTAL; idx = idx + 1) begin
            if (!next_has_dirty_w && dirty_next_w[idx]) begin
                next_has_dirty_w  = 1'b1;
                next_dirty_addr_w = idx[ADDR_WIDTH-1:0];
            end
        end
    end

    wire sync_read_b_same_addr = (sync_state_q == SYNC_READ) && b_we_i && (b_addr_i == sync_addr_q);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            active_bank_q            <= 1'b0;
            swap_pending_q           <= 1'b0;
            sync_state_q             <= SYNC_IDLE;
            sync_addr_q              <= '0;
            dirty_word_q             <= '0;
            shadow_w0_override_q     <= '0;
            inject_session_started_q <= 1'b0;
            inject_strobe_q          <= 1'b0;
            bank_swap_commit_q       <= 1'b0;
        end else begin
            inject_strobe_q    <= 1'b0;
            bank_swap_commit_q <= 1'b0;
            dirty_word_q       <= dirty_next_w;

            case (sync_state_q)
                SYNC_IDLE: begin
                    if (sync_load_accept) begin
                        if ((a_addr_i[1:0] == 2'b00) && (a_wstrb_i == 4'hf)) begin
                            shadow_w0_override_q[a_cid_w] <= 1'b0;
                        end
                        inject_session_started_q <= 1'b0;
                    end else if (hot_write_accept) begin
                        if (a_addr_i[1:0] == 2'b00) begin
                            shadow_w0_override_q[a_cid_w] <= 1'b1;
                        end
                        if (!inject_session_started_q) begin
                            inject_strobe_q          <= 1'b1;
                            inject_session_started_q <= 1'b1;
                        end
                    end

                    if (swap_commit_w) begin
                        active_bank_q            <= ~active_bank_q;
                        bank_swap_commit_q       <= 1'b1;
                        swap_pending_q           <= 1'b0;
                        shadow_w0_override_q     <= '0;
                        inject_session_started_q <= 1'b0;
                        if (next_has_dirty_w) begin
                            sync_state_q <= SYNC_READ;
                            sync_addr_q  <= next_dirty_addr_w;
                        end
                    end else if (swap_req_accept) begin
                        swap_pending_q <= 1'b1;
                    end
                end

                SYNC_READ: begin
                    if (sync_read_b_same_addr) begin
                        if (b_wstrb_i == 4'hf) begin
                            // Обидва банки щойно синхронно отримали нове слово через Port B
                            if (next_has_dirty_w) begin
                                sync_state_q <= SYNC_READ;
                                sync_addr_q  <= next_dirty_addr_w;
                            end else begin
                                sync_state_q <= SYNC_IDLE;
                            end
                        end else begin
                            // Частковий запис Port B оновив активний банк; перечитуємо слово
                            sync_state_q <= SYNC_READ;
                        end
                    end else begin
                        sync_state_q <= SYNC_WRITE;
                    end
                end

                SYNC_WRITE: begin
                    if (next_has_dirty_w) begin
                        sync_state_q <= SYNC_READ;
                        sync_addr_q  <= next_dirty_addr_w;
                    end else begin
                        sync_state_q <= SYNC_IDLE;
                    end
                end

                default: begin
                    sync_state_q <= SYNC_IDLE;
                end
            endcase
        end
    end

endmodule
