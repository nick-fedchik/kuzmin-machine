`timescale 1ns/1ps

module kpol_bram_pipeline_axi_tb;
    logic clk = 0, rst_n = 0;
    logic [12:0] awaddr = 0, araddr = 0;
    logic awvalid = 0, wvalid = 0, bready = 0, arvalid = 0, rready = 0;
    logic [31:0] wdata = 0;
    logic [3:0] wstrb = 4'hf;
    wire awready, wready, bvalid, arready, rvalid, busy;
    wire [1:0] bresp, rresp;
    wire [31:0] rdata;
    logic [31:0] image [0:255];
    reg [4095:0] image_a, image_b;
    localparam int MAX_EVENTS = 64;
    logic [31:0] trace_data [0:MAX_EVENTS*3-1];
    reg [4095:0] trace_file;
    logic trace_mode = 0;
    logic [31:0] initial_expected;
    integer trace_length, trace_writes = 0;

    // Сигнали зовнішнього тригера та апаратної телеметрії
    logic ext_hw_trigger_valid_i = 0;
    logic [5:0] ext_hw_trigger_cid_i = 0;
    logic [31:0] ext_hw_trigger_param_i = 0;
    wire hw_trigger_ready_o;
    wire hw_commit_pulse_o;
    wire hw_reject_pulse_o;
    wire hw_pipeline_busy_o;
    wire fifo_overflow_o;
    wire [31:0] events_dropped_count_o;
    wire [5:0] hw_commit_cid_o;
    wire [31:0] hw_last_committed_state_o;
    logic b4_audit_mode = 0;

    always #5 clk = ~clk;
    always @(posedge clk) begin
        if (!rst_n) trace_writes = 0;
        else begin
            if (b4_audit_mode && dut.bram_we && dut.busy)
                $fatal(1, "[FAIL] B4 race: Port A bram_we=1 overlapped with PHASE_RUN busy=1");
            if (trace_mode && dut.b_we) begin
                if (dut.b_addr !== 0 || dut.b_wstrb !== 4'hf)
                    $fatal(1, "trace: write outside W0 or partial write");
                trace_writes = trace_writes + 1;
            end
        end
    end

    kpol_bram_pipeline_axi dut (.*);

    task automatic write_reg(input [12:0] addr, input [31:0] data,
                             input [3:0] strb, input [1:0] expected_resp);
        @(negedge clk);
        awaddr = addr;
        wdata = data;
        wstrb = strb;
        awvalid = 1;
        wvalid = 1;
        bready = 1;
        do @(posedge clk); while (!awready || !wready);
        @(negedge clk);
        awvalid = 0;
        wvalid = 0;
        while (!bvalid) @(negedge clk);
        if (bresp !== expected_resp)
            $fatal(1, "write %h response %h expected %h", addr, bresp, expected_resp);
        @(negedge clk);
        bready = 0;
    endtask

    task automatic read_reg(input [12:0] addr, output [31:0] data);
        @(negedge clk);
        araddr = addr;
        arvalid = 1;
        rready = 1;
        do @(posedge clk); while (!arready);
        @(negedge clk);
        arvalid = 0;
        while (!rvalid) @(negedge clk);
        if (rresp !== 0) $fatal(1, "read %h response %h", addr, rresp);
        data = rdata;
        @(negedge clk);
        rready = 0;
    endtask

    task automatic write_split(input bit data_first);
        @(negedge clk);
        awaddr = 'h00c;
        wdata = 123;
        wstrb = 4'hf;
        if (data_first) wvalid = 1;
        else awvalid = 1;
        @(negedge clk);
        awvalid = 0;
        wvalid = 0;
        repeat (2) @(negedge clk);
        if (data_first) awvalid = 1;
        else wvalid = 1;
        @(negedge clk);
        awvalid = 0;
        wvalid = 0;
        while (!bvalid) @(negedge clk);
        repeat (3) begin
            if (!bvalid || bresp !== 0 || awready || wready)
                $fatal(1, "write response did not hold under backpressure");
            @(negedge clk);
        end
        bready = 1;
        @(negedge clk);
        bready = 0;
    endtask

    task automatic load_image(input reg [4095:0] filename);
        $readmemh(filename, image);
        for (int i = 0; i < 256; i++) begin
            write_reg('h004, i, 4'hf, 0);
            write_reg('h008, image[i], 4'hf, 0);
        end
    endtask

    task automatic wait_idle;
        reg [31:0] status;
        status = 1;
        while (status[0]) read_reg('h014, status);
    endtask

    task automatic send_event(input [31:0] value);
        write_reg('h00c, value, 4'hf, 0);
        write_reg('h010, 1, 4'hf, 0);
        wait_idle();
    endtask

    task automatic send_hw_trigger(input [5:0] cid, input [31:0] value);
        @(negedge clk);
        ext_hw_trigger_cid_i = cid;
        ext_hw_trigger_param_i = value;
        ext_hw_trigger_valid_i = 1;
        @(negedge clk);
        ext_hw_trigger_valid_i = 0;
        wait_idle();
    endtask

    task automatic check_state(input [31:0] expected, input reg [63:0] label);
        reg [31:0] actual;
        write_reg('h004, 0, 4'hf, 0);
        read_reg('h008, actual);
        if (actual !== expected)
            $fatal(1, "%0s: expected state %0d, got %0d", label, expected, actual);
    endtask

    task automatic check_descriptor(input logic [31:0] expected, input integer step);
        logic [31:0] actual, word_expected;
        for (int word_index = 0; word_index < 4; word_index++) begin
            write_reg('h004, word_index, 4'hf, 0);
            read_reg('h008, actual);
            word_expected = word_index == 0 ? expected : image[word_index];
            if (actual !== word_expected)
                $fatal(1, "trace event=%0d word=%0d expected=%h got=%h",
                       step, word_index, word_expected, actual);
        end
        $display("TRACE event=%0d state=%h commits=%0d rejects=%0d writes=%0d",
                 step, expected, dut.commits, dut.rejects, trace_writes);
    endtask

    initial begin : run
        reg [31:0] value;
        integer expected_commits;
        trace_mode = $value$plusargs("trace=%s", trace_file);
        if ($test$plusargs("b4_race_audit")) begin
            b4_audit_mode = 1'b1;
            if (!$value$plusargs("image_a=%s", image_a))
                $fatal(1, "b4_race_audit requires image_a");
            repeat (3) @(negedge clk);
            rst_n = 1;
            load_image(image_a);
            check_state(10, "b4 initial");

            // A. 1-тактова колізія B4 Load vs Run з керованим зовнішнім джерелом:
            // на такті write_fire(0x008) та наступному такті bram_we=1 сигнал hw_trigger_ready_o
            // зобов'язаний опуститися в 0, щоб кероване джерело утримало подію до завершення запису Port A.
            write_reg('h004, 0, 4'hf, 0);
            @(negedge clk);
            awaddr  = 'h008;
            wdata   = 32'd50;
            wstrb   = 4'hf;
            awvalid = 1'b1;
            wvalid  = 1'b1;
            bready  = 1'b1;
            ext_hw_trigger_cid_i   = 6'd0;
            ext_hw_trigger_param_i = 32'd5;
            ext_hw_trigger_valid_i = 1'b1;
            #1;
            if (hw_trigger_ready_o !== 1'b0)
                $fatal(1, "[FAIL] B4 race: hw_trigger_ready_o remained 1 during write_fire(0x008)");
            do @(posedge clk); while (!awready || !wready);
            #1;
            awvalid = 1'b0;
            wvalid  = 1'b0;
            if (dut.bram_we !== 1'b1 || hw_trigger_ready_o !== 1'b0)
                $fatal(1, "[FAIL] B4 race: expected bram_we=1 and hw_trigger_ready_o=0, got we=%b ready=%b",
                       dut.bram_we, hw_trigger_ready_o);
            while (hw_trigger_ready_o !== 1'b1) begin
                @(posedge clk);
                #1;
                if (bvalid) bready = 1'b0;
            end
            @(posedge clk); // Прийняття утриманої події строго після запису 50 у BRAM
            #1;
            ext_hw_trigger_valid_i = 1'b0;
            bready = 1'b0;
            wait_idle();
            check_state(51, "b4 managed after write");
            if (fifo_overflow_o !== 1'b0 || events_dropped_count_o !== 32'd0)
                $fatal(1, "[FAIL] B4 managed stall caused unexpected drop=%0d ovf=%b",
                       events_dropped_count_o, fifo_overflow_o);

            // B. Незупинний 1-тактовий імпульс у такт write_fire(0x008) блокується від запуску PHASE_RUN
            // та обліковується за B5 (overflow=1, dropped=1).
            write_reg('h004, 0, 4'hf, 0);
            @(negedge clk);
            awaddr  = 'h008;
            wdata   = 32'd70;
            wstrb   = 4'hf;
            awvalid = 1'b1;
            wvalid  = 1'b1;
            bready  = 1'b1;
            ext_hw_trigger_cid_i   = 6'd0;
            ext_hw_trigger_param_i = 32'd5;
            ext_hw_trigger_valid_i = 1'b1;
            do @(posedge clk); while (!awready || !wready);
            @(negedge clk);
            awvalid = 1'b0;
            wvalid  = 1'b0;
            ext_hw_trigger_valid_i = 1'b0; // Зняття до появи ready=1 -> B5 drop
            while (!bvalid) @(negedge clk);
            @(negedge clk);
            bready = 1'b0;
            wait_idle();
            check_state(70, "b4 unstoppable blocked during write");
            if (fifo_overflow_o !== 1'b1 || events_dropped_count_o !== 32'd1)
                $fatal(1, "[FAIL] B4 unstoppable pulse not accounted: ovf=%b dropped=%0d",
                       fifo_overflow_o, events_dropped_count_o);

            $display("PASS: axi b4_race_audit");
            $finish;
        end
        if ($test$plusargs("w1c_clear_audit")) begin
            if (!$value$plusargs("image_a=%s", image_a))
                $fatal(1, "w1c_clear_audit requires image_a");
            repeat (3) @(negedge clk);
            rst_n = 1;
            load_image(image_a);

            // Генеруємо одночасно втрату на AXI-рівні (під sw_trigger) та в секвенсері (переповнення FIFO)
            write_reg('h00c, 5, 4'hf, 0);
            @(negedge clk);
            awaddr  = 'h010;
            wdata   = 1;
            wstrb   = 4'hf;
            awvalid = 1'b1;
            wvalid  = 1'b1;
            bready  = 1'b1;
            do @(posedge clk); while (!awready || !wready);
            @(negedge clk);
            awvalid = 1'b0;
            wvalid  = 1'b0;
            // Однотактовий імпульс під час sw_trigger -> axi_sw_overflow_q=1, axi_sw_dropped_q=1
            ext_hw_trigger_cid_i   = 6'd0;
            ext_hw_trigger_param_i = 32'd5;
            ext_hw_trigger_valid_i = 1'b1;
            @(negedge clk);
            ext_hw_trigger_valid_i = 1'b0;
            bready = 1'b0;

            // Додатково подаємо 20 незупинних подій поспіль -> переповнення FIFO секвенсера
            for (int k = 0; k < 20; k++) begin
                @(negedge clk);
                ext_hw_trigger_cid_i   = 6'd0;
                ext_hw_trigger_param_i = 32'd25 + k;
                ext_hw_trigger_valid_i = 1'b1;
            end
            @(negedge clk);
            ext_hw_trigger_valid_i = 1'b0;

            // Поки секвенсер ще активно розвантажує чергу (busy == 1), W1C-запис у 0x02C має отримати SLVERR
            if (!busy) $fatal(1, "[FAIL] expected busy==1 during 16-event queue drain");
            write_reg('h02c, 32'h0001_0000, 4'hf, 2'd2);
            wait_idle();

            read_reg('h028, value);
            if (value < 32'd2 || !fifo_overflow_o)
                $fatal(1, "[FAIL] expected sticky overflow & drops >= 2 before W1C, got ovf=%b drops=%0d",
                       fifo_overflow_o, value);

            // Запис 0 у W1C-регістр 0x02C є no-op (OKAY, прапорець лишається зведеним)
            write_reg('h02c, 32'h0000_0000, 4'hf, 2'd0);
            read_reg('h02c, value);
            if (value[16] !== 1'b1)
                $fatal(1, "[FAIL] W1C write of 0 unexpectedly cleared overflow: 0x02c=%h", value);

            // Запис 1 у біт 16 (0x0001_0000) при busy==0 очищує і 0x02C[16], і лічильник 0x028
            write_reg('h02c, 32'h0001_0000, 4'hf, 2'd0);
            if (fifo_overflow_o !== 1'b0 || events_dropped_count_o !== 32'd0)
                $fatal(1, "[FAIL] W1C write 0x0001_0000 did not clear outputs: ovf=%b dropped=%0d",
                       fifo_overflow_o, events_dropped_count_o);
            read_reg('h02c, value);
            if (value[16] !== 1'b0 || value[7] !== 1'b1)
                $fatal(1, "[FAIL] expected 0x02c[16]=0 and [7]=1 after W1C, got %h", value);
            read_reg('h028, value);
            if (value !== 32'd0)
                $fatal(1, "[FAIL] expected 0x028 == 0 after W1C, got %0d", value);

            $display("PASS: axi w1c_clear_audit");
            $finish;
        end
        if ($test$plusargs("hw_burst")) begin
            integer saw_stall;
            saw_stall = 0;
            if (!$value$plusargs("image_a=%s", image_a))
                $fatal(1, "hw_burst requires image_a");
            repeat (3) @(negedge clk);
            rst_n = 1;
            load_image(image_a);
            check_state(10, "burst initial");

            // 1. Одночасна колізія sw_trigger (MMIO 0x010) та зовнішнього керованого тригера:
            // під час імпульсу sw_trigger апаратний порт має опустити hw_trigger_ready_o у 0,
            // щоб керований зовнішній продюсер утримав подію ще 1 такт без тихої втрати на мультиплексорі.
            write_reg('h00c, 5, 4'hf, 0);
            @(negedge clk);
            awaddr  = 'h010;
            wdata   = 1;
            wstrb   = 4'hf;
            awvalid = 1;
            wvalid  = 1;
            bready  = 1;
            do @(posedge clk); while (!awready || !wready);
            // На цьому фронті sw_trigger зареєстровано у 1; подаємо зовнішню подію з param = 5
            #1;
            awvalid                = 0;
            wvalid                 = 0;
            if (!bvalid || bresp !== 0)
                $fatal(1, "hw_burst: write 0x010 failed bvalid=%b bresp=%h", bvalid, bresp);
            ext_hw_trigger_cid_i   = 6'd0;
            ext_hw_trigger_param_i = 32'd5;
            ext_hw_trigger_valid_i = 1'b1;
            #1;
            if (hw_trigger_ready_o !== 1'b0) begin
                $fatal(1, "hw_burst: expected hw_trigger_ready_o=0 during sw_trigger collision");
            end
            while (hw_trigger_ready_o !== 1'b1) begin
                @(posedge clk);
                #1;
                bready = 0;
            end
            @(posedge clk); // Прийняття утриманого ext_hw_trigger після sw_trigger
            #1;
            ext_hw_trigger_valid_i = 1'b0;
            bready                 = 0;
            wait_idle();
            // Обидві події (sw_trigger + ext_hw_trigger) мали виконатися рівно по одному разу: 10 + 2 = 12
            check_state(12, "after sw+hw collision");

            // 2. Керована пачка з 24 зовнішніх подій під зворотним тиском черги (20 commit, 4 reject)
            @(posedge clk);
            #1;
            for (int i = 0; i < 24; i++) begin
                ext_hw_trigger_cid_i   = 6'd0;
                ext_hw_trigger_param_i = ((i % 6) == 5) ? 32'd25 : 32'd3;
                ext_hw_trigger_valid_i = 1'b1;
                #1;
                while (hw_trigger_ready_o !== 1'b1) begin
                    saw_stall = saw_stall + 1;
                    if (saw_stall > 512) $fatal(1, "hw_burst: deadlock under backpressure");
                    @(posedge clk);
                    #1;
                end
                @(posedge clk);
                #1;
            end
            ext_hw_trigger_valid_i = 1'b0;
            if (saw_stall == 0)
                $fatal(1, "hw_burst: burst did not exercisehw_trigger_ready_o=0 backpressure");

            wait_idle();
            check_state(32, "after managed hw burst");
            read_reg('h018, value);
            if (value !== 26) $fatal(1, "hw_burst: expected 26 events, got %0d", value);
            read_reg('h01c, value);
            if (value !== 22) $fatal(1, "hw_burst: expected 22 commits, got %0d", value);
            read_reg('h020, value);
            if (value !== 4) $fatal(1, "hw_burst: expected 4 rejects, got %0d", value);
            read_reg('h028, value);
            if (value !== 0 || fifo_overflow_o || events_dropped_count_o !== 0)
                $fatal(1, "hw_burst: unexpected drop=%0d ovf=%b", value, fifo_overflow_o);
            read_reg('h02c, value);
            if (value[6] !== 1'b0 || value[7] !== 1'b1)
                $fatal(1, "hw_burst: unexpected queue flags reg 0x02c=%h", value);
            $display("PASS: axi hw_burst lossless (stall_cycles=%0d)", saw_stall);
            $finish;
        end
        if (trace_mode) begin
            if (!$value$plusargs("image_a=%s", image_a) ||
                !$value$plusargs("events=%d", trace_length) ||
                !$value$plusargs("initial=%h", initial_expected))
                $fatal(1, "trace requires image, events and initial");
            if (trace_length < 1 || trace_length > MAX_EVENTS)
                $fatal(1, "trace length out of range");
            $readmemh(trace_file, trace_data, 0, trace_length*3-1);
            repeat (3) @(negedge clk);
            rst_n = 1;
            load_image(image_a);
            check_descriptor(initial_expected, -1);
            expected_commits = 0;
            for (int i = 0; i < trace_length; i++) begin
                if ($test$plusargs("hw_events")) begin
                    write_reg('h00c, 123, 4'hf, 0);
                    send_hw_trigger(6'd0, trace_data[3*i]);
                end else send_event(trace_data[3*i]);
                check_descriptor(trace_data[3*i+1], i);
                expected_commits = expected_commits + int'(trace_data[3*i+2]);
                read_reg('h018, value);
                if (value !== i+1) $fatal(1, "trace: incorrect event count");
                read_reg('h01c, value);
                if (value !== expected_commits || trace_writes !== expected_commits)
                    $fatal(1, "trace: incorrect commit/write count");
                read_reg('h020, value);
                if (value !== i+1-expected_commits) $fatal(1, "trace: incorrect reject count");
                read_reg('h028, value);
                if (value !== 0 || fifo_overflow_o)
                    $fatal(1, "trace: unexpected event loss");
            end
            $display("PASS: profile trace");
            $finish;
        end
        if (!$value$plusargs("image_a=%s", image_a) ||
            !$value$plusargs("image_b=%s", image_b))
            $fatal(1, "two image paths are required");
        repeat (3) @(negedge clk);
        rst_n = 1;

        read_reg('h000, value);
        if (value !== 32'h4b504d43) $fatal(1, "incorrect ID");
        write_reg('h004, 1, 4'h1, 2);
        write_reg('h028, 0, 4'hf, 3);
        write_split(0);
        write_split(1);
        read_reg('h00c, value);
        if (value !== 123) $fatal(1, "split writes lost data");

        load_image(image_a);
        write_reg('h00c, 5, 4'hf, 0);
        write_reg('h010, 1, 4'hf, 0);
        write_reg('h004, 0, 4'hf, 2);
        wait_idle();
        check_state(11, "image A");
        send_event(25);
        check_state(11, "image A");

        // Перевірка апаратного зовнішнього тригера (REQ-SYS-011)
        send_hw_trigger(6'd0, 5);
        check_state(12, "image A via HW trigger");

        load_image(image_b);
        send_event(5);
        check_state(9, "image B");
        send_event(25);
        check_state(9, "image B");

        read_reg('h018, value);
        if (value !== 5) $fatal(1, "incorrect event count: %0d", value);
        read_reg('h01c, value);
        if (value !== 3) $fatal(1, "incorrect commit count: %0d", value);
        read_reg('h020, value);
        if (value !== 2) $fatal(1, "incorrect reject count: %0d", value);

        // Перевірка регістрів телеметрії черги
        read_reg('h028, value);
        if (value !== 0) $fatal(1, "expected 0 dropped events, got %0d", value);
        read_reg('h02c, value);
        // ready повинен бути 1
        if (value[7] !== 1'b1) $fatal(1, "expected ready flag in reg 0x02c, got %h", value);

        $display("PASS: both compiled images");
        $finish;
    end
    initial begin
        #1000000;
        $fatal(1, "simulation timed out");
    end
endmodule
