// ============================================================================
// Тестбенч: km_autonomous_sequencer_tb.sv
// Призначення: Верифікація автономного виконання МК у залізі (Крок 2),
// черги подій, зворотного тиску, немовчазного переповнення (B5, REQ-SYS-013..014,
// REQ-HW-014..016) та інтеграції зовнішнього тригера (B2, REQ-SYS-011..012).
// ============================================================================
`timescale 1ns / 1ps

module km_autonomous_sequencer_tb #(
    parameter int QUEUE_DEPTH = 16
);

    localparam int DATA_WIDTH = 32;
    localparam int ADDR_WIDTH = 8;

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

    // Монітор фактичних записів у BRAM Порт B (контроль відсутності подвійного commit і порядку)
    int          bram_we_total;
    int          commit_log_cnt;
    logic [5:0]  commit_log_cid  [0:511];
    logic [31:0] commit_log_data [0:511];

    always @(posedge clk) begin
        if (!rst_n) begin
            bram_we_total  <= 0;
            commit_log_cnt <= 0;
        end else if (bram_b_we) begin
            if (bram_b_addr[1:0] !== 2'b00 || bram_b_wstrb !== 4'b1111) begin
                $fatal(1, "[FAIL] Некоректний запис у BRAM Port B: addr=%h wstrb=%b",
                       bram_b_addr, bram_b_wstrb);
            end
            bram_we_total <= bram_we_total + 1;
            if (commit_log_cnt < 512) begin
                commit_log_cid[commit_log_cnt]  <= bram_b_addr[7:2];
                commit_log_data[commit_log_cnt] <= bram_b_wdata;
                commit_log_cnt <= commit_log_cnt + 1;
            end
        end
    end

    // Керована подача однієї зовнішньої події за протоколом valid/ready без втрат:
    // якщо ready == 0, утримує незмінні valid, cid та param до фронту з ready == 1.
    task automatic send_managed_event(
        input  logic [5:0]  cid,
        input  logic [31:0] param,
        output int          stall_cycles
    );
        begin
            stall_cycles     = 0;
            hw_trigger_valid = 1'b1;
            hw_trigger_cid   = cid;
            hw_trigger_param = param;
            #1;
            while (hw_trigger_ready !== 1'b1) begin
                stall_cycles = stall_cycles + 1;
                if (stall_cycles > 256) begin
                    $fatal(1, "[FAIL] Зависання секвенсера під зворотним тиском (stall > 256 тактів)!");
                end
                @(posedge clk);
                #1;
            end
            @(posedge clk);
            #1;
            hw_trigger_valid = 1'b0;
        end
    endtask

    // Читання стану концепту (Word 0) через Порт A BRAM
    task automatic read_concept_state(
        input  logic [5:0]  cid,
        output logic [31:0] state_val
    );
        begin
            @(posedge clk);
            #1;
            bram_a_addr = {cid, 2'b00};
            @(posedge clk);
            #2;
            state_val = bram_a_rdata;
        end
    endtask

    // Доведення секвенсера до такту ST_EVAL_GATE каскадного Концепту 0
    // при точно заданій заповненості черги target_occ елементами Концепту 1.
    // Використовує лише легальні входи/виходи модуля (commit_pulse_o == 1 на ST_EVAL_GATE).
    task automatic prepare_cascade_collision(
        input int target_occ,
        output int n_pre_out
    );
        int n_pre;
        int dummy_stall;
        int seen_commits;
        begin
            if (busy !== 1'b0 || hw_trigger_ready !== 1'b1 || fifo_full !== 1'b0) begin
                $fatal(1, "[FAIL] prepare_cascade_collision вимагає пустого секвенсера!");
            end
            n_pre = (target_occ + 6) / 7;
            n_pre_out = n_pre;

            @(posedge clk);
            #1;
            for (int k = 0; k < n_pre; k++) begin
                send_managed_event(6'd1, 32'd1, dummy_stall);
            end
            // Каскадна подія на Концепті 0 (param = 20 < 100 -> Commit + каскад на CID 1)
            send_managed_event(6'd0, 32'd20, dummy_stall);
            // Заповнення черги рівно target_occ подіями Концепту 1
            for (int k = 0; k < target_occ; k++) begin
                send_managed_event(6'd1, 32'd1, dummy_stall);
            end

            // Чекаємо такту ST_EVAL_GATE саме для Концепту 0:
            // у момент подачі останнього елемента n_pre подій вже могли завершитися,
            // але Концепт 0 гарантовано ще у фазі читання дескриптора.
            // Чекаємо перший імпульс commit_pulse, коли bramb_addr вказує на CID 0 (або за лічильником).
            seen_commits = 0;
            while (!(commit_pulse === 1'b1 && bram_b_addr[7:2] === 6'd0)) begin
                @(posedge clk);
                #1;
                seen_commits = seen_commits + 1;
                if (seen_commits > 256) begin
                    $fatal(1, "[FAIL] Не дочекалися ST_EVAL_GATE для Концепту 0!");
                end
            end
        end
    endtask

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

        // Концепт 3: Початковий стан = 100, pred = EQ(77), action = INC(0x01), sub_cid = 0
        write_concept_desc(6'd3, 32'd100, 32'd77, 8'h01, 8'h03, 8'h00, 8'h01, 32'd0);

        // Концепт 4: Початковий стан = 200, pred = EQ(0) (перевірка нульового payload під stall), action = INC(0x01)
        write_concept_desc(6'd4, 32'd200, 32'd0, 8'h01, 8'h03, 8'h00, 8'h01, 32'd0);

        // Концепт 5: Початковий стан = 300, pred = EQ(-42) (знаковий від'ємний payload під stall), action = INC(0x01)
        write_concept_desc(6'd5, 32'd300, -32'sd42, 8'h01, 8'h03, 8'h00, 8'h01, 32'd0);

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

        $display("=== 5. B5 v2: УТРИМАННЯ БЕЗ ВТРАТ ТА АРБІТРАЖ КАСКАДІВ (QUEUE_DEPTH=%0d) ===", QUEUE_DEPTH);
        begin
            logic [31:0] st0, st1, st3, st4, st5;
            logic [31:0] exp0, exp1, exp3, exp4, exp5;
            int          exp_commits;
            int          stall_cnt;
            int          n_pre;
            int          log_base;

            exp0        = 32'd11;
            exp1        = 32'd55;
            exp3        = 32'd100;
            exp4        = 32'd200;
            exp5        = 32'd300;
            exp_commits = 2;

            // Перевірка початкових меж empty: черга вільна, не переповнена
            if (busy !== 1'b0 || fifo_full !== 1'b0 || hw_trigger_ready !== 1'b1 ||
                fifo_overflow !== 1'b0 || events_dropped_count !== 32'd0 ||
                bram_we_total != exp_commits) begin
                $fatal(1, "[FAIL] 5.0 Порушено інваріанти порожньої черги перед B5-тестами!");
            end

            // ----------------------------------------------------------------
            // 5A. Межа full/empty + утримання нульового payload (param = 0) під stall
            // ----------------------------------------------------------------
            @(posedge clk);
            #1;
            // Подаємо QUEUE_DEPTH + 3 керованих подій CID=1 підряд, щоб гарантовано досягти fifo_full == 1,
            // а слідом — подію CID=4 з param=0, яка зобов'язана прочекати під ready == 0 без втрат.
            begin
                int saw_full;
                saw_full = 0;
                for (int i = 0; i < QUEUE_DEPTH + 3; i++) begin
                    send_managed_event(6'd1, 32'd1, stall_cnt);
                    if (fifo_full === 1'b1) saw_full = 1;
                end
                // Дотискаємо до моменту fifo_full == 1 перед подачею CID=4 (param=0)
                while (fifo_full !== 1'b1) begin
                    send_managed_event(6'd1, 32'd1, stall_cnt);
                    exp1 = exp1 + 32'd5;
                    exp_commits = exp_commits + 1;
                end
                saw_full = 1;
                if (hw_trigger_ready !== 1'b0) begin
                    $fatal(1, "[FAIL] 5A: При fifo_full == 1 сигнал hw_trigger_ready має бути 0!");
                end
                send_managed_event(6'd4, 32'd0, stall_cnt);
                if (!saw_full || stall_cnt == 0) begin
                    $fatal(1, "[FAIL] 5A: Подія CID=4 не пройшла реальний stall на повній черзі (stall=%0d)!", stall_cnt);
                end
                exp1        = exp1 + (QUEUE_DEPTH + 3) * 32'd5;
                exp4        = exp4 + 32'd1;
                exp_commits = exp_commits + (QUEUE_DEPTH + 3) + 1;
            end

            wait(busy == 1'b0);
            @(posedge clk);
            #2;
            read_concept_state(6'd1, st1);
            read_concept_state(6'd4, st4);
            if (fifo_full !== 1'b0 || hw_trigger_ready !== 1'b1 ||
                fifo_overflow !== 1'b0 || events_dropped_count !== 32'd0 ||
                comm_count !== exp_commits || events_count !== (exp_commits + 1) || rej_count !== 32'd1 ||
                bram_we_total != exp_commits || st1 !== exp1 || st4 !== exp4) begin
                $fatal(1, "[FAIL] 5A: full/empty або нульовий payload під stall дав збій: drop=%0d ovf=%0b ev=%0d comm=%0d/%0d rej=%0d we=%0d st1=%0d/%0d st4=%0d/%0d",
                       events_dropped_count, fifo_overflow, events_count, comm_count, exp_commits, rej_count, bram_we_total, st1, exp1, st4, exp4);
            end
            $display("[OK] 5A: Межі full/empty та param=0 під stall (%0d тактів очікування, 0 втрат)", stall_cnt);

            // ----------------------------------------------------------------
            // 5B. Два вільні слоти (occupancy = QUEUE_DEPTH - 2) + одночасний каскад і зовнішня подія
            // Очікування B5 v2: ready == 1, приймаються обидві, каскад стає попереду зовнішньої!
            // ----------------------------------------------------------------
            log_base = commit_log_cnt;
            prepare_cascade_collision(QUEUE_DEPTH - 2, n_pre);
            // Зараз активний такт ST_EVAL_GATE Концепту 0: подаємо зовнішню подію CID=3 (param=77)
            hw_trigger_valid = 1'b1;
            hw_trigger_cid   = 6'd3;
            hw_trigger_param = 32'd77;
            #1;
            if (fifo_full !== 1'b0 || hw_trigger_ready !== 1'b1) begin
                $fatal(1, "[FAIL] 5B: За 2 вільних слотів і каскаду має бути full=0, ready=1 (отримано full=%b, ready=%b)!",
                       fifo_full, hw_trigger_ready);
            end
            @(posedge clk); // Одночасний запис каскаду (wr_ptr) та CID=3 (wr_ptr+1) -> черга стає повною
            #1;
            hw_trigger_valid = 1'b0;
            if (fifo_full !== 1'b1) begin
                $fatal(1, "[FAIL] 5B: Після подвійного запису у QUEUE_DEPTH-2 черга мала стати повною (fifo_full=1)!");
            end

            wait(busy == 1'b0);
            @(posedge clk);
            #2;
            exp0        = exp0 + 32'd1;
            exp1        = exp1 + (n_pre + (QUEUE_DEPTH - 2) + 1) * 32'd5;
            exp3        = exp3 + 32'd1;
            exp_commits = exp_commits + n_pre + 1 + (QUEUE_DEPTH - 2) + 1 + 1;
            read_concept_state(6'd0, st0);
            read_concept_state(6'd1, st1);
            read_concept_state(6'd3, st3);
            if (fifo_overflow !== 1'b0 || events_dropped_count !== 32'd0 ||
                comm_count !== exp_commits || events_count !== (exp_commits + 1) || rej_count !== 32'd1 ||
                bram_we_total != exp_commits || st0 !== exp0 || st1 !== exp1 || st3 !== exp3) begin
                $fatal(1, "[FAIL] 5B: Колізія за 2 вільних слотів порушила інваріанти: drop=%0d ovf=%0b ev=%0d comm=%0d/%0d rej=%0d st0=%0d/%0d st1=%0d/%0d st3=%0d/%0d",
                       events_dropped_count, fifo_overflow, events_count, comm_count, exp_commits, rej_count, st0, exp0, st1, exp1, st3, exp3);
            end
            // Перевірка суворого порядку: передостанній commit — каскад CID=1, останній — зовнішній CID=3
            if (commit_log_cid[commit_log_cnt - 2] !== 6'd1 || commit_log_cid[commit_log_cnt - 1] !== 6'd3) begin
                $fatal(1, "[FAIL] 5B: Порушено пріоритет каскаду над зовнішньою подією: передостанній CID=%0d, останній CID=%0d",
                       commit_log_cid[commit_log_cnt - 2], commit_log_cid[commit_log_cnt - 1]);
            end
            $display("[OK] 5B: 2 вільні слоти + каскад + external прийняті за 1 такт у правильному порядку");

            // ----------------------------------------------------------------
            // 5C. Один вільний слот (occupancy = QUEUE_DEPTH - 1) + одночасний каскад і зовнішня подія
            // Очікування B5 v2: fifo_full == 0, АЛЕ hw_trigger_ready == 0 до фронту!
            // Каскад займає слот, а зовнішня подія (CID=5, param=-42) чекає під stall без втрат і без дублювання.
            // ----------------------------------------------------------------
            prepare_cascade_collision(QUEUE_DEPTH - 1, n_pre);
            hw_trigger_valid = 1'b1;
            hw_trigger_cid   = 6'd5;
            hw_trigger_param = -32'sd42;
            #1;
            if (fifo_full !== 1'b0) begin
                $fatal(1, "[FAIL] 5C: Перед фронтом мало лишатися рівно 1 вільне місце (fifo_full=0)!");
            end
            if (hw_trigger_ready !== 1'b0) begin
                $fatal(1, "[FAIL] 5C: Колізія ready/cascade! При 1 вільному слоті та активному каскаді hw_trigger_ready мусить бути 0!");
            end
            // Продовжуємо штатний керований handshake із незмінним знаковим payload (-42)
            stall_cnt = 0;
            while (hw_trigger_ready !== 1'b1) begin
                stall_cnt = stall_cnt + 1;
                if (stall_cnt > 256) $fatal(1, "[FAIL] 5C: Зависання очікування ready == 1!");
                @(posedge clk);
                #1;
            end
            @(posedge clk); // Такт фактичного прийняття CID=5 після звільнення слота
            #1;
            hw_trigger_valid = 1'b0;

            wait(busy == 1'b0);
            @(posedge clk);
            #2;
            exp0        = exp0 + 32'd1;
            exp1        = exp1 + (n_pre + (QUEUE_DEPTH - 1) + 1) * 32'd5;
            exp5        = exp5 + 32'd1;
            exp_commits = exp_commits + n_pre + 1 + (QUEUE_DEPTH - 1) + 1 + 1;
            read_concept_state(6'd0, st0);
            read_concept_state(6'd1, st1);
            read_concept_state(6'd5, st5);
            if (fifo_overflow !== 1'b0 || events_dropped_count !== 32'd0 ||
                comm_count !== exp_commits || events_count !== (exp_commits + 1) || rej_count !== 32'd1 ||
                bram_we_total != exp_commits || st0 !== exp0 || st1 !== exp1 || st5 !== exp5) begin
                $fatal(1, "[FAIL] 5C: Колізія за 1 вільного слота втратила або здублювала подію: drop=%0d ovf=%0b ev=%0d comm=%0d/%0d rej=%0d we=%0d st0=%0d/%0d st1=%0d/%0d st5=%0d/%0d",
                       events_dropped_count, fifo_overflow, events_count, comm_count, exp_commits, rej_count, bram_we_total,
                       st0, exp0, st1, exp1, st5, exp5);
            end
            if (commit_log_cid[commit_log_cnt - 2] !== 6'd1 || commit_log_cid[commit_log_cnt - 1] !== 6'd5) begin
                $fatal(1, "[FAIL] 5C: Порушено порядок каскад -> утримана зовнішня подія: [%0d, %0d]",
                       commit_log_cid[commit_log_cnt - 2], commit_log_cid[commit_log_cnt - 1]);
            end
            $display("[OK] 5C: 1 вільний слот + каскад -> ready=0, утримання param=-42 (%0d тактів), рівно 1 виконання", stall_cnt);

            // ----------------------------------------------------------------
            // 5D. Нуль вільних слотів (occupancy = QUEUE_DEPTH, full-каскад) +
            // одночасні cascade_pending / external / dequeue на наступному такті!
            // ----------------------------------------------------------------
            prepare_cascade_collision(QUEUE_DEPTH, n_pre);
            hw_trigger_valid = 1'b1;
            hw_trigger_cid   = 6'd4;
            hw_trigger_param = 32'd0;
            #1;
            if (fifo_full !== 1'b1 || hw_trigger_ready !== 1'b0) begin
                $fatal(1, "[FAIL] 5D: Перед full-каскадом очікувались fifo_full=1, ready=0 (отримано %b, %b)!",
                       fifo_full, hw_trigger_ready);
            end
            @(posedge clk); // Фронт ST_EVAL_GATE -> ST_IDLE: CID=0 комітиться 1 раз, каскад утримується в pending
            #1;
            // На цьому такті в ST_IDLE одночасно активні: dequeue голови FIFO + запис утриманого каскаду + зовнішній stall!
            if (hw_trigger_ready !== 1'b0) begin
                $fatal(1, "[FAIL] 5D: Під час розвантаження pending-каскаду у ST_IDLE ready мусить лишатися 0!");
            end
            stall_cnt = 1;
            while (hw_trigger_ready !== 1'b1) begin
                stall_cnt = stall_cnt + 1;
                if (stall_cnt > 256) $fatal(1, "[FAIL] 5D: Секвенсер завис при full-каскаді (deadlock)!");
                @(posedge clk);
                #1;
            end
            @(posedge clk); // Прийняття утриманої зовнішньої події CID=4 (param=0)
            #1;
            hw_trigger_valid = 1'b0;

            wait(busy == 1'b0);
            @(posedge clk);
            #2;
            exp0        = exp0 + 32'd1;
            exp1        = exp1 + (n_pre + QUEUE_DEPTH + 1) * 32'd5;
            exp4        = exp4 + 32'd1;
            exp_commits = exp_commits + n_pre + 1 + QUEUE_DEPTH + 1 + 1;
            read_concept_state(6'd0, st0);
            read_concept_state(6'd1, st1);
            read_concept_state(6'd4, st4);
            if (fifo_overflow !== 1'b0 || events_dropped_count !== 32'd0 ||
                comm_count !== exp_commits || events_count !== (exp_commits + 1) || rej_count !== 32'd1 ||
                bram_we_total != exp_commits || st0 !== exp0 || st1 !== exp1 || st4 !== exp4) begin
                $fatal(1, "[FAIL] 5D: Full-каскад або одночасний cascade/external/dequeue дав збій: drop=%0d ovf=%0b ev=%0d comm=%0d/%0d rej=%0d we=%0d st0=%0d/%0d st1=%0d/%0d st4=%0d/%0d",
                       events_dropped_count, fifo_overflow, events_count, comm_count, exp_commits, rej_count, bram_we_total,
                       st0, exp0, st1, exp1, st4, exp4);
            end
            if (commit_log_cid[commit_log_cnt - 2] !== 6'd1 || commit_log_cid[commit_log_cnt - 1] !== 6'd4) begin
                $fatal(1, "[FAIL] 5D: Порушено порядок full-каскад -> утримана зовнішня подія: [%0d, %0d]",
                       commit_log_cid[commit_log_cnt - 2], commit_log_cid[commit_log_cnt - 1]);
            end
            $display("[OK] 5D: Full-каскад + одночасні cascade/external/dequeue без втрат і без подвійного commit (%0d тактів stall)", stall_cnt);

            // ----------------------------------------------------------------
            // 5E. Довга керована пачка з каскадами під постійним зворотним тиском
            // ----------------------------------------------------------------
            @(posedge clk);
            #1;
            for (int i = 0; i < 3 * QUEUE_DEPTH; i++) begin
                if ((i % 3) == 0) begin
                    send_managed_event(6'd0, 32'd20, stall_cnt);
                    exp0        = exp0 + 32'd1;
                    exp1        = exp1 + 32'd5;
                    exp_commits = exp_commits + 2;
                end else begin
                    send_managed_event(6'd3, 32'd77, stall_cnt);
                    exp3        = exp3 + 32'd1;
                    exp_commits = exp_commits + 1;
                end
            end
            wait(busy == 1'b0);
            @(posedge clk);
            #2;
            read_concept_state(6'd0, st0);
            read_concept_state(6'd1, st1);
            read_concept_state(6'd3, st3);
            if (fifo_overflow !== 1'b0 || events_dropped_count !== 32'd0 ||
                comm_count !== exp_commits || events_count !== (exp_commits + 1) || rej_count !== 32'd1 ||
                bram_we_total != exp_commits || st0 !== exp0 || st1 !== exp1 || st3 !== exp3) begin
                $fatal(1, "[FAIL] 5E: Керована пачка втратила або здублювала події: drop=%0d ovf=%0b ev=%0d comm=%0d/%0d rej=%0d we=%0d st0=%0d/%0d st1=%0d/%0d st3=%0d/%0d",
                       events_dropped_count, fifo_overflow, events_count, comm_count, exp_commits, rej_count, bram_we_total,
                       st0, exp0, st1, exp1, st3, exp3);
            end
            $display("[OK] 5E: Керована пачка %0d подій з каскадами — 0 втрат, точна збіжність BRAM", 3 * QUEUE_DEPTH);

            // ----------------------------------------------------------------
            // 6. ТЕЛЕМЕТРІЯ НЕЗУПИННОГО ДЖЕРЕЛА (REQ-HW-015: втрата при порушенні утримання)
            // ----------------------------------------------------------------
            $display("=== 6. ТЕСТ НЕЗУПИННОГО ДЖЕРЕЛА (ПОРУШЕННЯ УТРИМАННЯ ПІД READY=0) ===");
            @(posedge clk);
            #1;
            while (fifo_full !== 1'b1) begin
                send_managed_event(6'd1, 32'd1, stall_cnt);
                exp1        = exp1 + 32'd5;
                exp_commits = exp_commits + 1;
            end
            // Синхронізуємося з початком вікна ST_REQ_W1..ST_IDLE (7 гарантованих тактів ready == 0 для будь-якого QUEUE_DEPTH)
            while (hw_trigger_ready !== 1'b1) begin
                @(posedge clk);
                #1;
            end
            send_managed_event(6'd1, 32'd1, stall_cnt);
            exp1        = exp1 + 32'd5;
            exp_commits = exp_commits + 1;
            if (fifo_full !== 1'b1 || hw_trigger_ready !== 1'b0) begin
                $fatal(1, "[FAIL] 6: Очікувалося вікно fifo_full=1, ready=0!");
            end
            // Імітуємо незупинне фізичне джерело:
            // (1) 1-тактовий імпульс, знятий до появи ready == 1 -> втрата №1
            hw_trigger_valid = 1'b1;
            hw_trigger_cid   = 6'd3;
            hw_trigger_param = 32'd77;
            @(posedge clk);
            #1;
            hw_trigger_valid = 1'b0;
            @(posedge clk);
            #1;
            // (2) перезапис payload під ready == 0 (param 10 -> 20) і подальше зняття valid -> втрати №2 та №3
            hw_trigger_valid = 1'b1;
            hw_trigger_cid   = 6'd1;
            hw_trigger_param = 32'd10;
            @(posedge clk);
            #1;
            hw_trigger_param = 32'd20; // перезапис неприйнятого param=10 -> втрата №2
            @(posedge clk);
            #1;
            hw_trigger_valid = 1'b0;   // зняття неприйнятого param=20 -> втрата №3

            wait(busy == 1'b0);
            @(posedge clk);
            #2;
            read_concept_state(6'd1, st1);
            read_concept_state(6'd3, st3);
            if (fifo_overflow !== 1'b1 || events_dropped_count !== 32'd3 || hw_trigger_ready !== 1'b1 ||
                comm_count !== exp_commits || events_count !== (exp_commits + 1) || rej_count !== 32'd1 ||
                bram_we_total != exp_commits || st1 !== exp1 || st3 !== exp3) begin
                $fatal(1, "[FAIL] 6: Політика обліку втрат незупинного джерела не спрацювала точно: drop=%0d (очік. 3) ovf=%b ready=%b ev=%0d comm=%0d/%0d rej=%0d st1=%0d/%0d st3=%0d/%0d",
                       events_dropped_count, fifo_overflow, hw_trigger_ready, events_count, comm_count, exp_commits, rej_count, st1, exp1, st3, exp3);
            end
            $display("[OK] 6: Незупинне джерело зафіксувало рівно 3 втрачені події (overflow=1) без псування прийнятої черги");
        end

        $display("====================================================================");
        $display("   АВТОНОМНЕ ВИКОНАННЯ, ЧЕРГА ТА НЕЗМІННЕ ЯДРО УСПІШНО ДОВЕДЕНО      ");
        $display("====================================================================");
        $finish;
    end

endmodule
