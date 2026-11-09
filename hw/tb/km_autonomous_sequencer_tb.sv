// ============================================================================
// Тестбенч: km_autonomous_sequencer_tb.sv
// Призначення: Верифікація автономного виконання МК у залізі (Крок 2).
// Доводить, що ядро обробляє транзакції та каскади за наносекунди
// без участі процесора та операційної системи Linux.
// ============================================================================
`timescale 1ns / 1ps

module km_autonomous_sequencer_tb;

    localparam int DATA_WIDTH = 32;
    localparam int ADDR_WIDTH = 8;

    logic                   clk;
    logic                   rst_n;

    // Вхідний апаратний тригер
    logic                   hw_trigger_valid;
    logic [5:0]             hw_trigger_cid;
    logic [DATA_WIDTH-1:0]  hw_trigger_param;

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

    // Статус секвенсера
    wire                    busy;
    wire [31:0]             events_count;
    wire [31:0]             comm_count;
    wire [31:0]             rej_count;
    wire [31:0]             last_comm_state;

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
        .NUM_CONCEPTS(64),
        .DATA_WIDTH(DATA_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) seq_inst (
        .clk(clk),
        .rst_n(rst_n),
        .hw_trigger_valid_i(hw_trigger_valid),
        .hw_trigger_cid_i(hw_trigger_cid),
        .hw_trigger_param_i(hw_trigger_param),
        .bram_b_addr_o(bram_b_addr),
        .bram_b_wdata_o(bram_b_wdata),
        .bram_b_wstrb_o(bram_b_wstrb),
        .bram_b_we_o(bram_b_we),
        .bram_b_rdata_i(bram_b_rdata),
        .busy_o(busy),
        .events_processed_count_o(events_count),
        .committed_count_o(comm_count),
        .rejected_count_o(rej_count),
        .last_committed_state_o(last_comm_state)
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

        $display("====================================================================");
        $display("   АВТОНОМНЕ ВИКОНАННЯ ТА КАСКАДНЕ РАНДЕВУ УСПІШНО ДОВЕДЕНО (TRL 4)   ");
        $display("====================================================================");
        $finish;
    end

endmodule
