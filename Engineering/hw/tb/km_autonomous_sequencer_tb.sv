// ============================================================================
// Тестбенч: km_autonomous_sequencer_tb.sv
// Призначення: Верифікація автономного виконання МК у залізі (Крок 2),
// черги подій, зворотного тиску, немовчазного переповнення (B5, REQ-SYS-013..014,
// REQ-HW-014..016) та інтеграції зовнішнього тригера (B2, REQ-SYS-011..012).
// ============================================================================
`timescale 1ns / 1ps

module km_autonomous_sequencer_tb;

    localparam int DATA_WIDTH = 32;
    localparam int ADDR_WIDTH = 8;
    localparam int QUEUE_DEPTH = 16;

    logic                   clk;
    logic                   rst_n;

    // Вхідний апаратний тригер
    logic                   hw_trigger_valid;
    logic [5:0]             hw_trigger_cid;
    logic [DATA_WIDTH-1:0]  hw_trigger_param;
    wire                    hw_trigger_ready;

    // Зв'язок між Sequencer та BRAM (Порт B)
    wire [ADDR_WIDTH-1:0]   bram_b_addr;
    wire [DATA_WIDTH-1:0]   bram_b_wdata;
    wire [3:0]              bram_b_wstrb;
    wire                    bram_b_we;
    wire [DATA_WIDTH-1:0]   bram_b_rdata;

    // Порт A BRAM (імітація завантаження через Secure Boot / AXI)
    logic [ADDR_WIDTH-1:0]  bram_a_addr;
    logic [DATA_WIDTH-1:0]  bram_a_wdata;
    logic [3:0]             bram_a_wstrb;
    logic                   bram_a_we;
    wire [DATA_WIDTH-1:0]   bram_a_rdata;

    // Статус та телеметрія секвенсера
    wire                    busy;
    wire                    fifo_full;
    wire                    fifo_overflow;
    wire [31:0]             events_dropped_count;
    wire [31:0]             events_count;
    wire [31:0]             comm_count;
    wire [31:0]             rej_count;
    wire [31:0]             last_comm_state;
    wire                    commit_pulse;
    wire                    reject_pulse;

    // Інстанціювання пам'яті концептів BRAM
    km_concept_bram #(
        .NUM_CONCEPTS(64),
        .DATA_WIDTH(DATA_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) bram_inst (
        .clk(clk),
        .rst_n(rst_n),
        .a_addr_i(bram_a_addr),
        .a_wdata_i(bram_a_wdata),
        .a_wstrb_i(bram_a_wstrb),
        .a_we_i(bram_a_we),
        .a_rdata_o(bram_a_rdata),
        .b_addr_i(bram_b_addr),
        .b_wdata_i(bram_b_wdata),
        .b_wstrb_i(bram_b_wstrb),
        .b_we_i(bram_b_we),
        .b_rdata_o(bram_b_rdata),
        .collision_detected_o()
    );

    // Інстанціювання автономного секвенсера
    km_autonomous_sequencer #(
        .QUEUE_DEPTH(QUEUE_DEPTH),
        .NUM_CONCEPTS(64),
        .DATA_WIDTH(DATA_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) seq_inst (
        .clk(clk),
        .rst_n(rst_n),
        .hw_trigger_valid_i(hw_trigger_valid),
        .hw_trigger_cid_i(hw_trigger_cid),
        .hw_trigger_param_i(hw_trigger_param),
        .hw_trigger_ready_o(hw_trigger_ready),
        .bram_b_addr_o(bram_b_addr),
        .bram_b_wdata_o(bram_b_wdata),
        .bram_b_wstrb_o(bram_b_wstrb),
        .bram_b_we_o(bram_b_we),
        .bram_b_rdata_i(bram_b_rdata),
        .busy_o(busy),
        .fifo_full_o(fifo_full),
        .fifo_overflow_o(fifo_overflow),
        .events_dropped_count_o(events_dropped_count),
        .events_processed_count_o(events_count),
        .committed_count_o(comm_count),
        .rejected_count_o(rej_count),
        .last_committed_state_o(last_comm_state),
        .commit_pulse_o(commit_pulse),
        .reject_pulse_o(reject_pulse)
    );

    always #5 clk = ~clk; // 100 МГц (10 нс)

    // Процедура запису дескриптора у BRAM через Порт A (Secure Boot)
    task write_concept_desc(
        input logic [5:0]  cid,
        input logic [31:0] state,
        input logic [31:0] operand,
        input logic [7:0]  pred_op,
        input logic [7:0]  flags,
        input logic [7:0]  hazard_lim,
        input logic [7:0]  action_op,
        input logic [31:0] sub_cid
    );
        begin
            @(posedge clk);
            #1;
            // Word 0
            bram_a_addr  = {cid, 2'b00};
            bram_a_wdata = state;
            bram_a_wstrb = 4'b1111;
            bram_a_we    = 1'b1;
            @(posedge clk);
            #1;
            // Word 1
            bram_a_addr  = {cid, 2'b01};
            bram_a_wdata = operand;
            @(posedge clk);
            #1;
            // Word 2: {action, hazard, flags, pred}
            bram_a_addr  = {cid, 2'b10};
            bram_a_wdata = {action_op, hazard_lim, flags, pred_op};
            @(posedge clk);
            #1;
            // Word 3: subscriber_cid
            bram_a_addr  = {cid, 2'b11};
            bram_a_wdata = sub_cid;
            @(posedge clk);
            #1;
            bram_a_we    = 1'b0;
        end
    endtask

    initial begin
        clk              = 0;
        rst_n            = 0;
        hw_trigger_valid = 0;
        hw_trigger_cid   = 0;
        hw_trigger_param = 0;
        bram_a_addr      = 0;
        bram_a_wdata     = 0;
        bram_a_wstrb     = 0;
        bram_a_we        = 0;

        #20;
        rst_n = 1;
        #20;

        $display("=== 1. ЗАВАНТАЖЕННЯ ОБРАЗУ BRAM (Secure Boot через Порт A) ===");
        // Концепт 0: Початковий стан = 10, pred = LT(100), action = INC(0x01), sub_cid = 1
        write_concept_desc(6'd0, 32'd10, 32'd100, 8'h04, 8'h03, 8'h00, 8'h01, 32'd1);

        // Концепт 1: Початковий стан = 50, pred = NOP(0x00), action = ADD(0x03), operand = 5, sub_cid = 0 (кінець ланцюга)
        write_concept_desc(6'd1, 32'd50, 32'd5, 8'h00, 8'h03, 8'h00, 8'h03, 32'd0);

        // Концепт 2: Початковий стан = 20, pred = GT(50) (порушення), action = INC(0x01), sub_cid = 0
        write_concept_desc(6'd2, 32'd20, 32'd50, 8'h03, 8'h03, 8'h00, 8'h01, 32'd0);

        #30;
        $display("=== 2. ПОДАЧА ФІЗИЧНОГО АПАРАТНОГО ТРИГЕРА НА КОНЦЕПТ 0 ===");
        @(posedge clk);
        #1;
        hw_trigger_valid = 1'b1;
        hw_trigger_cid   = 6'd0;
        hw_trigger_param = 32'd20; // 20 < 100 -> True
        @(posedge clk);
        #1;
        hw_trigger_valid = 1'b0;

        // Чекаємо завершення автономного виконання обох транзакцій (Концепт 0 + каскад Концепт 1)
        wait(busy == 1'b1);
        wait(busy == 1'b0);
        #10;

        $display("=== 3. РЕЗУЛЬТАТИ АВТОНОМНОГО ВИКОНАННЯ У КРЕМНІЇ ===");
        $display("Опрацьовано подій: %0d (очікується 2)", events_count);
        $display("Успішних комітів:  %0d (очікується 2)", comm_count);
        $display("Відхилень:        %0d (очікується 0)", rej_count);
        $display("Останній стан:    %0d (очікується 55)", last_comm_state);

        if (events_count != 32'd2 || comm_count != 32'd2 || rej_count != 32'd0 || last_comm_state != 32'd55) begin
            $fatal(1, "[FAIL] Автономне виконання не пройшло або дало хибний стан!");
        end

        // Читання BRAM через Порт A для підтвердження збереження
        @(posedge clk);
        #1;
        bram_a_addr = {6'd0, 2'b00}; // Читаємо стан Концепту 0
        @(posedge clk);
        #2;
        $display("Фізичний стан Концепту 0 у BRAM: %0d (очікується 11: 10+1)", bram_a_rdata);
        if (bram_a_rdata !== 32'd11) begin
            $fatal(1, "[FAIL] BRAM Концепту 0 не оновлено: отримано %0d", bram_a_rdata);
        end

        bram_a_addr = {6'd1, 2'b00}; // Читаємо стан Концепту 1
        @(posedge clk);
        #2;
        $display("Фізичний стан Концепту 1 у BRAM: %0d (очікується 55: 50+5)", bram_a_rdata);
        if (bram_a_rdata !== 32'd55) begin
            $fatal(1, "[FAIL] BRAM Концепту 1 не оновлено: отримано %0d", bram_a_rdata);
        end

        $display("=== 4. ТЕСТ ВІДХИЛЕННЯ ТРАНЗАКЦІЇ (Fail-Closed Reject) ===");
        @(posedge clk);
        #1;
        hw_trigger_valid = 1'b1;
        hw_trigger_cid   = 6'd2;   // Концепт 2 вимагає param > 50
        hw_trigger_param = 32'd10; // 10 < 50 -> Порушення, Reject
        @(posedge clk);
        #1;
        hw_trigger_valid = 1'b0;

        wait(busy == 1'b1);
        wait(busy == 1'b0);
        #10;
        $display("Відхилень після Reject: %0d (очікується 1)", rej_count);
        if (rej_count != 32'd1) begin
            $fatal(1, "[FAIL] Транзакція не була відхилена!");
        end

        // Перевірка незмінності стану Концепту 2 у BRAM
        @(posedge clk);
        #1;
        bram_a_addr = {6'd2, 2'b00};
        @(posedge clk);
        #2;
        if (bram_a_rdata !== 32'd20) begin
            $fatal(1, "[FAIL] Стан Концепту 2 змінився при відхиленні: %0d", bram_a_rdata);
        end

        $display("=== 5. СТРЕС-ТЕСТ ПЕРЕПОВНЕННЯ ТА ЗВОРОТНОГО ТИСКУ (REQ-SYS-013, REQ-HW-014, REQ-HW-015) ===");
        // Швидка пачка з 25 подій підряд (темп подачі 1 такт, темп обробки 8 тактів)
        // Після 18 тактів черга повністю заповнюється і наступні події відкидаються
        for (int i = 0; i < 25; i++) begin
            @(posedge clk);
            #1;
            hw_trigger_valid = 1'b1;
            hw_trigger_cid   = 6'd1;
            hw_trigger_param = 32'd1;
        end
        @(posedge clk);
        #1;
        hw_trigger_valid = 1'b0;

        // Чекаємо завершення обробки всіх подій у черзі
        wait(busy == 1'b1);
        wait(busy == 1'b0);
        #20;

        $display("Відкинутих подій (dropped): %0d (очікується > 0)", events_dropped_count);
        $display("Прапорець переповнення (overflow): %0d (очікується 1)", fifo_overflow);
        $display("Сигнал готовності після вичитки (ready): %0d (очікується 1)", hw_trigger_ready);

        if (events_dropped_count == 0 || fifo_overflow != 1'b1 || hw_trigger_ready != 1'b1) begin
            $fatal(1, "[FAIL] Політика немовчазного відкидання не спрацювала!");
        end

        $display("====================================================================");
        $display("   АВТОНОМНЕ ВИКОНАННЯ, ЧЕРГА ТА НЕЗМІННЕ ЯДРО УСПІШНО ДОВЕДЕНО      ");
        $display("====================================================================");
        $finish;
    end

endmodule
