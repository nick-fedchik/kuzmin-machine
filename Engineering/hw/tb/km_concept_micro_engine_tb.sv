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

        // ====================================================================
        // СЦЕНАРІЙ 6: Каскадна підписка на CID=0 (guard_flags[4]=1) та межа CID < 64
        // ====================================================================
        $display("[CME-TB] Сценарій 6: Каскадна підписка на CID=0 (flags=0x13) та межа CID < 64");
        // 6A: явний дозвіл каскаду (bit 4 = 0x10) на CID=0 зобов'язаний виставити trigger_subscriber=1
        descriptor  = make_desc(32'd10, 32'd0, 8'h00, 8'h13, 8'h00, 8'h01, 32'd0);
        event_param = 32'd1;
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (!committed || rejected || updated_state !== 32'd11 || !trigger_subscriber || subscriber_cid !== 32'd0) begin
            $fatal(1, "[FAIL] Сценарій 6A провалено: каскад на CID=0 заблоковано! commit=%0d, state=%0d, trig=%0d, sub=%0d",
                   committed, updated_state, trigger_subscriber, subscriber_cid);
        end
        #19;
        // 6B: без bit 4 при sub_cid=0 каскад НЕ активується (зворотна сумісність KPOL-CME-1)
        descriptor  = make_desc(32'd11, 32'd0, 8'h00, 8'h03, 8'h00, 8'h01, 32'd0);
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (!committed || trigger_subscriber) begin
            $fatal(1, "[FAIL] Сценарій 6B провалено: небажаний каскад без flags[4]! commit=%0d, trig=%0d",
                   committed, trigger_subscriber);
        end
        #19;
        // 6C: позамежний sub_cid=64 не має активувати каскад навіть при flags[4]=1
        descriptor  = make_desc(32'd12, 32'd0, 8'h00, 8'h13, 8'h00, 8'h01, 32'd64);
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (!committed || trigger_subscriber) begin
            $fatal(1, "[FAIL] Сценарій 6C провалено: каскад на невалідний CID=64 не заблоковано! commit=%0d, trig=%0d",
                   committed, trigger_subscriber);
        end
        $display("[PASS] Сценарій 6 успішний: каскад на CID=0 працює і межа CID < 64 захищена");
        #19;

        // ====================================================================
        // СЦЕНАРІЙ 7: Точний по-концептний state_changed_o без міжконцептного забруднення
        // ====================================================================
        $display("[CME-TB] Сценарій 7: По-концептний state_changed_o");
        // Крок 7.0: Concept A переходить 0 -> 50 (залишає 50 у спільному регістрі шлюзу)
        descriptor  = make_desc(32'd0, 32'd0, 8'h00, 8'h03, 8'h00, 8'h00, 32'd0);
        event_param = 32'd50;
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (!committed || !state_changed || updated_state !== 32'd50) begin
            $fatal(1, "[FAIL] Сценарій 7.0 провалено: commit=%0d, chg=%0d, state=%0d",
                   committed, state_changed, updated_state);
        end
        #19;
        // Крок 7A: Concept B вже мав стан 100 і отримує ASSIGN 100 -> state_changed МАЄ БУТИ 0!
        descriptor  = make_desc(32'd100, 32'd0, 8'h00, 8'h03, 8'h00, 8'h00, 32'd0);
        event_param = 32'd100;
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (!committed || state_changed || updated_state !== 32'd100) begin
            $fatal(1, "[FAIL] Сценарій 7A провалено: хибний state_changed=%0d для незмінного стану 100->100!",
                   state_changed);
        end
        #19;
        // Крок 7B: Concept C мав стан 0 і отримує ASSIGN 100 (коли шлюз вже тримав 100) -> state_changed МАЄ БУТИ 1!
        descriptor  = make_desc(32'd0, 32'd0, 8'h00, 8'h03, 8'h00, 8'h00, 32'd0);
        event_param = 32'd100;
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (!committed || !state_changed || updated_state !== 32'd100) begin
            $fatal(1, "[FAIL] Сценарій 7B провалено: пропущено state_changed=%0d для переходу 0->100!",
                   state_changed);
        end
        $display("[PASS] Сценарій 7 успішний: state_changed_o точно відображає перехід поточного концепту");
        #19;

        // ====================================================================
        // СЦЕНАРІЙ 8: Детекція знакового переповнення / underflow (INC/DEC/ADD/SUB)
        // ====================================================================
        $display("[CME-TB] Сценарій 8: Знакове переповнення та underflow (SUB/ADD/INC/DEC)");
        // 8A: SUB signed underflow wrap-around (-10 - 2147483643 -> +2147483643 у 2's complement)
        descriptor  = make_desc(32'hFFFF_FFF6, 32'h7FFF_FFFB, 8'h00, 8'h03, 8'h00, 8'h04, 32'd0);
        event_param = 32'd0;
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (committed || !rejected) begin
            $fatal(1, "[FAIL] Сценарій 8A провалено: SUB signed underflow помилково пройшов інваріант! commit=%0d, state=%0d",
                   committed, $signed(updated_state));
        end
        #19;
        // 8B: ADD signed underflow wrap-around (INT32_MIN + (-1) -> +2147483647)
        descriptor  = make_desc(32'h8000_0000, 32'hFFFF_FFFF, 8'h00, 8'h03, 8'h00, 8'h03, 32'd0);
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (committed || !rejected) begin
            $fatal(1, "[FAIL] Сценарій 8B провалено: ADD signed underflow помилково пройшов інваріант! commit=%0d",
                   committed);
        end
        #19;
        // 8C: ADD signed positive overflow (0x7FFFFFF0 + 32 -> negative)
        descriptor  = make_desc(32'h7FFF_FFF0, 32'd32, 8'h00, 8'h03, 8'h00, 8'h03, 32'd0);
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (committed || !rejected) begin
            $fatal(1, "[FAIL] Сценарій 8C провалено: ADD positive overflow не відхилено! commit=%0d",
                   committed);
        end
        #19;
        // 8D: DEC на INT32_MIN (0x80000000 - 1 -> +2147483647) та INC на INT32_MAX
        descriptor  = make_desc(32'h8000_0000, 32'd0, 8'h00, 8'h03, 8'h00, 8'h02, 32'd0);
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (committed || !rejected) begin
            $fatal(1, "[FAIL] Сценарій 8D провалено: DEC на INT32_MIN помилково пройшов інваріант! commit=%0d",
                   committed);
        end
        #19;
        descriptor  = make_desc(32'h7FFF_FFFF, 32'd0, 8'h00, 8'h03, 8'h00, 8'h01, 32'd0);
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (committed || !rejected) begin
            $fatal(1, "[FAIL] Сценарій 8E провалено: INC на INT32_MAX не відхилено! commit=%0d",
                   committed);
        end
        $display("[PASS] Сценарій 8 успішний: усі знакові переповнення та underflow заблоковано");
        #19;

        // ====================================================================
        // СЦЕНАРІЙ 9: Знаковий компаратор RANGE (pred_opcode = 0x05) для [-10, +10]
        // ====================================================================
        $display("[CME-TB] Сценарій 9: Знаковий предикат RANGE [-10, +10]");
        // range_lo = -10 (16'hFFF6), range_hi = +10 (16'h000A)
        descriptor  = make_desc(32'd5, {16'h000A, 16'hFFF6}, 8'h05, 8'h03, 8'h00, 8'h01, 32'd0);
        // 9A: event_param = -5 -> всередині [-10, +10] -> COMMIT (5 -> 6)
        event_param = -32'sd5;
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (!committed || rejected || updated_state !== 32'd6) begin
            $fatal(1, "[FAIL] Сценарій 9A провалено: RANGE [-10,+10] відхилив вхід -5! commit=%0d, rej=%0d, state=%0d",
                   committed, rejected, updated_state);
        end
        #19;
        // 9B: event_param = +5 -> всередині [-10, +10] -> COMMIT (5 -> 6)
        event_param = 32'sd5;
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (!committed || rejected || updated_state !== 32'd6) begin
            $fatal(1, "[FAIL] Сценарій 9B провалено: RANGE [-10,+10] відхилив вхід +5! commit=%0d, rej=%0d",
                   committed, rejected);
        end
        #19;
        // 9C: event_param = -20 -> поза межами [-10, +10] -> REJECT
        event_param = -32'sd20;
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (committed || !rejected) begin
            $fatal(1, "[FAIL] Сценарій 9C провалено: RANGE [-10,+10] пропустив вхід -20! commit=%0d",
                   committed);
        end
        $display("[PASS] Сценарій 9 успішний: знаковий компаратор RANGE працює коректно");
        #19;

        // ====================================================================
        // СЦЕНАРІЙ 10: Fail-Closed відхилення невідомих action_opcode (> 0x04)
        // ====================================================================
        $display("[CME-TB] Сценарій 10: Fail-Closed відхилення невідомого action_opcode=0xFF");
        descriptor  = make_desc(32'd42, 32'd0, 8'h00, 8'h03, 8'h00, 8'hFF, 32'd0);
        event_param = 32'd1;
        event_valid = 1'b1;
        #10;
        event_valid = 1'b0;
        #1;
        if (committed || !rejected || state_changed) begin
            $fatal(1, "[FAIL] Сценарій 10 провалено: невідомий action_opcode=0xFF дав мовчазний commit=%0d, rej=%0d!",
                   committed, rejected);
        end
        $display("[PASS] Сценарій 10 успішний: невідомий action_opcode гарантовано відхилено (fail-closed)");
        #19;

        $display("====================================================================");
        $display("   УСІ 10 ТЕСТОВИХ СЦЕНАРІЇВ УНІВЕРСАЛЬНОГО ЯДРА CME УСПІШНО ПРОЙДЕНО");
        $display("====================================================================");
        $finish;
    end

endmodule
