// ============================================================================
// Тестбенч: km_concept_micro_engine_tb.sv
// Призначення: Фізична верифікація Універсального мікро-рушія концептів (CME).
// Доводить, що різні алгоритми виконуються на одному й тому ж RTL
// виключно шляхом зміни 16-байтного дескриптора в BRAM.
// ============================================================================
`timescale 1ns / 1ps

module km_concept_micro_engine_tb;

    localparam int DATA_WIDTH = 32;

    logic                   clk;
    logic                   rst_n;
    logic                   event_valid;
    logic [7:0]             event_id;
    logic [DATA_WIDTH-1:0]  event_param;
    logic [127:0]           descriptor;

    wire                    committed;
    wire                    rejected;
    wire                    hazard_observed;
    wire                    unknown_hazard;
    wire [DATA_WIDTH-1:0]   updated_state;
    wire                    state_changed;
    wire [31:0]             subscriber_cid;
    wire                    trigger_subscriber;

    // Інстанціювання тестованого модуля CME
    km_concept_micro_engine #(
        .DATA_WIDTH(DATA_WIDTH)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .event_valid_i(event_valid),
        .event_id_i(event_id),
        .event_param_i(event_param),
        .descriptor_i(descriptor),
        .committed_o(committed),
        .rejected_o(rejected),
        .hazard_observed_o(hazard_observed),
        .unknown_hazard_o(unknown_hazard),
        .updated_state_o(updated_state),
        .state_changed_o(state_changed),
        .subscriber_cid_o(subscriber_cid),
        .trigger_subscriber_o(trigger_subscriber)
    );

    // Тактовий сигнал 100 МГц (період 10 нс)
    always #5 clk = ~clk;

    // Допоміжна функція складання 16-байтного дескриптора
    function automatic logic [127:0] make_desc(
        input logic [31:0] state,
        input logic [31:0] operand,
        input logic [7:0]  pred_op,
        input logic [7:0]  flags,
        input logic [7:0]  hazard_lim,
        input logic [7:0]  action_op,
        input logic [31:0] sub_cid
    );
        return {sub_cid, action_op, hazard_lim, flags, pred_op, operand, state};
    endfunction

    initial begin
        clk         = 0;
        rst_n       = 0;
        event_valid = 0;
        event_id    = 0;
        event_param = 0;
        descriptor  = 0;

        #20;
        rst_n = 1;
        #20;

        // ====================================================================
        // СЦЕНАРІЙ 1: Пороговий охоронець (EQ + ASSIGN)
        // Дескриптор: стан=0, операнд=100, pred=EQ(0x01), flags=0x03(Assum+Inv),
        //             hazard=0, action=ASSIGN(0x00), sub=0
        // ====================================================================
        $display("[CME-TB] Сценарій 1: Пороговий охоронець (EQ=100, вхід=100)");
        descriptor  = make_desc(32'd0, 32'd100, 8'h01, 8'h03, 8'h00, 8'h00, 32'd0);
        event_param = 32'd100;
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (!committed || rejected || updated_state !== 32'd100) begin
            $fatal(1, "[FAIL] Сценарій 1 провалено: commit=%0d, rej=%0d, state=%0d (exp 100)",
                   committed, rejected, updated_state);
        end
        $display("[PASS] Сценарій 1 успішний: транзакція committed, стан = %0d", updated_state);
        #19;

        // ====================================================================
        // СЦЕНАРІЙ 2: Невідповідний вхід (EQ=100, вхід=50) -> REJECT
        // ====================================================================
        $display("[CME-TB] Сценарій 2: Невідповідний вхід (EQ=100, вхід=50)");
        event_param = 32'd50;
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (committed || !rejected || updated_state !== 32'd0) begin
            $fatal(1, "[FAIL] Сценарій 2 провалено: commit=%0d, rej=%0d, state=%0d (exp 0)",
                   committed, rejected, updated_state);
        end
        $display("[PASS] Сценарій 2 успішний: транзакція відхилена (fail-closed)");
        #19;

        // ====================================================================
        // СЦЕНАРІЙ 3: Монотонний лічильник (LT=50 + INC)
        // Дескриптор: стан=10, операнд=50, pred=LT(0x04), flags=0x03,
        //             hazard=0, action=INC(0x01), sub=42
        // ====================================================================
        $display("[CME-TB] Сценарій 3: Монотонний лічильник (LT < 50, action=INC, sub=42)");
        descriptor  = make_desc(32'd10, 32'd50, 8'h04, 8'h03, 8'h00, 8'h01, 32'd42);
        event_param = 32'd25; // 25 < 50 -> True
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (!committed || rejected || updated_state !== 32'd11 || !trigger_subscriber || subscriber_cid !== 32'd42) begin
            $fatal(1, "[FAIL] Сценарій 3 провалено: commit=%0d, state=%0d (exp 11), sub_trig=%0d",
                   committed, updated_state, trigger_subscriber);
        end
        $display("[PASS] Сценарій 3 успішний: стан = %0d (10+1), каскад активовано для CID=%0d",
                 updated_state, subscriber_cid);
        #19;

        // ====================================================================
        // СЦЕНАРІЙ 4: Fail-Closed блокування небезпеки (Hazard Limit = 120, вхід = 150)
        // Навіть за NOP-предиката наявність hazard зобов'язана заблокувати commit!
        // ====================================================================
        $display("[CME-TB] Сценарій 4: Блокування небезпеки Hazard (Limit=120, вхід=150)");
        descriptor  = make_desc(32'd0, 32'd0, 8'h00, 8'h07, 8'd120, 8'h00, 32'd0); // flags=0x07 (Assum+Inv+Hazard)
        event_param = 32'd150;
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (committed || !rejected || !hazard_observed) begin
            $fatal(1, "[FAIL] Сценарій 4 провалено: hazard не заблокував транзакцію! commit=%0d, rej=%0d, haz=%0d",
                   committed, rejected, hazard_observed);
        end
        $display("[PASS] Сценарій 4 успішний: hazard виявлено, транзакцію апаратно заблоковано!");
        #19;

        // ====================================================================
        // СЦЕНАРІЙ 5: Велика точка Кузьміна • = ¬ (Inversion flag bit 3)
        // Дескриптор: pred=EQ(100), flags=0x0B (Assum + Inv + Invert)
        // При вході 100 предикат істинний, але через • інвертується у False -> Reject!
        // ====================================================================
        $display("[CME-TB] Сценарій 5: Велика точка Кузьміна • = ¬ (Інверсія припущення)");
        descriptor  = make_desc(32'd0, 32'd100, 8'h01, 8'h0B, 8'h00, 8'h00, 32'd0);
        event_param = 32'd100;
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (committed || !rejected) begin
            $fatal(1, "[FAIL] Сценарій 5 провалено: інверсія • не спрацювала! commit=%0d", committed);
        end
        $display("[PASS] Сценарій 5 успішний: Велика точка • = ¬ успішно відхилила транзакцію!");
        #19;

        $display("====================================================================");
        $display("   УСІ 5 ТЕСТОВИХ СЦЕНАРІЇВ УНІВЕРСАЛЬНОГО ЯДРА CME УСПІШНО ПРОЙДЕНО ");
        $display("====================================================================");
        $finish;
    end

endmodule
