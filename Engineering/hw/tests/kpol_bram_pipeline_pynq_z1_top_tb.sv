`timescale 1ns / 1ps

// Спрощені поведінкові моделі примітивів Zynq-7000 для RTL-симуляції top-модуля PYNQ-Z1
module BUFG (
    input  wire I,
    output wire O
);
    assign O = I;
endmodule

module PS7 (
    output wire [3:0]  FCLKCLK,
    input  wire        MAXIGP0ACLK,
    output reg         MAXIGP0ARESETN,
    output reg  [31:0] MAXIGP0ARADDR,
    output reg  [11:0] MAXIGP0ARID,
    output reg         MAXIGP0ARVALID,
    input  wire        MAXIGP0ARREADY,
    output reg         MAXIGP0RREADY,
    input  wire [31:0] MAXIGP0RDATA,
    input  wire [11:0] MAXIGP0RID,
    input  wire        MAXIGP0RLAST,
    input  wire [1:0]  MAXIGP0RRESP,
    input  wire        MAXIGP0RVALID,
    output reg  [31:0] MAXIGP0AWADDR,
    output reg  [11:0] MAXIGP0AWID,
    output reg         MAXIGP0AWVALID,
    input  wire        MAXIGP0AWREADY,
    output reg  [31:0] MAXIGP0WDATA,
    output reg  [3:0]  MAXIGP0WSTRB,
    output reg  [11:0] MAXIGP0WID,
    output reg         MAXIGP0WVALID,
    input  wire        MAXIGP0WREADY,
    output reg         MAXIGP0BREADY,
    input  wire [11:0] MAXIGP0BID,
    input  wire [1:0]  MAXIGP0BRESP,
    input  wire        MAXIGP0BVALID
);
    reg fclk0 = 1'b0;
    always #5 fclk0 = ~fclk0; // 100 MHz
    assign FCLKCLK = {3'b000, fclk0};

    initial begin
        MAXIGP0ARESETN = 1'b0;
        MAXIGP0ARADDR  = 32'd0;
        MAXIGP0ARID    = 12'd0;
        MAXIGP0ARVALID = 1'b0;
        MAXIGP0RREADY  = 1'b0;
        MAXIGP0AWADDR  = 32'd0;
        MAXIGP0AWID    = 12'd0;
        MAXIGP0AWVALID = 1'b0;
        MAXIGP0WDATA   = 32'd0;
        MAXIGP0WSTRB   = 4'hf;
        MAXIGP0WID     = 12'd0;
        MAXIGP0WVALID  = 1'b0;
        MAXIGP0BREADY  = 1'b0;
    end

    task automatic axi_write(input [31:0] addr, input [31:0] data);
        @(negedge MAXIGP0ACLK);
        MAXIGP0AWADDR  = addr;
        MAXIGP0WDATA   = data;
        MAXIGP0WSTRB   = 4'hf;
        MAXIGP0AWVALID = 1'b1;
        MAXIGP0WVALID  = 1'b1;
        MAXIGP0BREADY  = 1'b1;
        do @(posedge MAXIGP0ACLK); while (!MAXIGP0AWREADY || !MAXIGP0WREADY);
        @(negedge MAXIGP0ACLK);
        MAXIGP0AWVALID = 1'b0;
        MAXIGP0WVALID  = 1'b0;
        while (!MAXIGP0BVALID) @(negedge MAXIGP0ACLK);
        if (MAXIGP0BRESP !== 2'b00)
            $fatal(1, "[FAIL] PS7 AXI write %h failed with bresp=%h", addr, MAXIGP0BRESP);
        @(negedge MAXIGP0ACLK);
        MAXIGP0BREADY  = 1'b0;
    endtask

    task automatic axi_read(input [31:0] addr, output [31:0] data);
        @(negedge MAXIGP0ACLK);
        MAXIGP0ARADDR  = addr;
        MAXIGP0ARVALID = 1'b1;
        MAXIGP0RREADY  = 1'b1;
        do @(posedge MAXIGP0ACLK); while (!MAXIGP0ARREADY);
        @(negedge MAXIGP0ACLK);
        MAXIGP0ARVALID = 1'b0;
        while (!MAXIGP0RVALID) @(negedge MAXIGP0ACLK);
        if (MAXIGP0RRESP !== 2'b00)
            $fatal(1, "[FAIL] PS7 AXI read %h failed with rresp=%h", addr, MAXIGP0RRESP);
        data = MAXIGP0RDATA;
        @(negedge MAXIGP0ACLK);
        MAXIGP0RREADY  = 1'b0;
    endtask
endmodule

module kpol_bram_pipeline_pynq_z1_top_tb;
    reg        ja1 = 1'b0;
    wire       ja2, ja3, ja4;
    reg  [3:0] btn = 4'b0000;
    reg  [1:0] sw  = 2'b00;
    wire [3:0] led;

    kpol_bram_pipeline_pynq_z1_top dut (
        .ja1(ja1),
        .ja2(ja2),
        .ja3(ja3),
        .ja4(ja4),
        .btn(btn),
        .sw(sw),
        .led(led)
    );

    task automatic write_bram_word(input [7:0] word_addr, input [31:0] val);
        dut.ps7.axi_write(32'h4000_0004, {24'd0, word_addr});
        dut.ps7.axi_write(32'h4000_0008, val);
    endtask

    task automatic read_bram_word(input [7:0] word_addr, output [31:0] val);
        dut.ps7.axi_write(32'h4000_0004, {24'd0, word_addr});
        dut.ps7.axi_read(32'h4000_0008, val);
    endtask

    task automatic wait_pipe_idle;
        reg [31:0] st;
        st = 32'd1;
        while (st[0]) dut.ps7.axi_read(32'h4000_0014, st);
    endtask

    initial begin
        reg [31:0] val, commits, events;

        repeat (4) @(negedge dut.clk);
        dut.ps7.MAXIGP0ARESETN = 1'b1;
        repeat (4) @(posedge dut.clk);

        // Ініціалізуємо BRAM нулями
        for (int i = 0; i < 256; i++) begin
            write_bram_word(i[7:0], 32'd0);
        end

        // CID 0 (слова 0..3): state=10, threshold=0, pred=GT (0x02: вимагає event_param > 0!),
        // guard_flags=0x03, action=INC (0x01: state + 1)
        write_bram_word(8'd0, 32'd10);
        write_bram_word(8'd1, 32'd0);
        write_bram_word(8'd2, 32'h0100_0302);
        write_bram_word(8'd3, 32'd0);

        // CID 2 (слова 8..11): state=200, threshold=0, pred=GT (0x02: event_param > 0),
        // guard_flags=0x03, action=INC (0x01: state + 1)
        write_bram_word(8'd8,  32'd200);
        write_bram_word(8'd9,  32'd0);
        write_bram_word(8'd10, 32'h0100_0302);
        write_bram_word(8'd11, 32'd0);

        // Навмисно записуємо event_param=0 у MMIO 0x00C, щоб перевірити, що зовнішній тригер
        // PMOD/кнопки подає фіксований апаратний параметр 32'd1, а не 32'd0.
        dut.ps7.axi_write(32'h4000_000c, 32'd0);

        // 1. Перевірка PMOD ja1 з параметром 32'd1 (GT 0 має закомітити 10 -> 11)
        sw = 2'b00;
        repeat (3) @(posedge dut.clk);
        @(negedge dut.clk);
        ja1 = 1'b1;
        repeat (3) @(negedge dut.clk);
        ja1 = 1'b0;
        repeat (20) @(posedge dut.clk);
        wait_pipe_idle();

        read_bram_word(8'd0, val);
        dut.ps7.axi_read(32'h4000_001c, commits);
        if (val !== 32'd11 || commits !== 32'd1)
            $fatal(1, "[FAIL] PYNQ top param=1 check failed: cid0_state=%0d (exp 11), commits=%0d (exp 1)",
                   val, commits);

        // 2. Перевірка 2-FF CDC синхронізації sw[1:0]: зміна sw між фронтами НЕ повинна
        // комбінаційно змінювати target_cid до проходження 2 тактів синхронізатора.
        @(posedge dut.clk);
        #2;
        sw = 2'b10;
        #1;
        if (dut.target_cid !== 6'd0)
            $fatal(1, "[FAIL] PYNQ top CDC violation: sw changed target_cid combinationally (%0d)",
                   dut.target_cid);
        @(posedge dut.clk);
        #1;
        if (dut.target_cid !== 6'd0)
            $fatal(1, "[FAIL] PYNQ top CDC violation: target_cid updated after only 1 FF (%0d)",
                   dut.target_cid);
        @(posedge dut.clk);
        #1;
        if (dut.target_cid !== 6'd2)
            $fatal(1, "[FAIL] PYNQ top CDC error: target_cid did not settle to 2 after 2 FFs (%0d)",
                   dut.target_cid);

        // Імпульс ja1 тепер має оновити CID 2: 200 -> 201
        @(negedge dut.clk);
        ja1 = 1'b1;
        repeat (3) @(negedge dut.clk);
        ja1 = 1'b0;
        repeat (20) @(posedge dut.clk);
        wait_pipe_idle();
        read_bram_word(8'd8, val);
        if (val !== 32'd201)
            $fatal(1, "[FAIL] PYNQ top sw=2 trigger failed: cid2_state=%0d (exp 201)", val);

        // 3. Перевірка антибрязкоту кнопки btn[0] та незалежності ja1 від утриманої btn[0]
        // 3a. Механічний брязкіт < 1 мс (кілька коротких імпульсів) НЕ повинен створювати подій
        @(negedge dut.clk); btn[0] = 1'b1;
        repeat (30) @(negedge dut.clk); btn[0] = 1'b0;
        repeat (20) @(negedge dut.clk); btn[0] = 1'b1;
        repeat (45) @(negedge dut.clk); btn[0] = 1'b0;
        repeat (30) @(posedge dut.clk);
        wait_pipe_idle();
        dut.ps7.axi_read(32'h4000_0018, events);
        if (events !== 32'd2)
            $fatal(1, "[FAIL] PYNQ top button bounce leaked spurious triggers: events=%0d (exp 2)", events);

        // 3b. Стабільне натискання btn[0] >= 100000 тактів (1 мс @ 100 МГц) дає рівно 1 подію
        @(negedge dut.clk);
        btn[0] = 1'b1;
        repeat (100025) @(posedge dut.clk);
        wait_pipe_idle();
        dut.ps7.axi_read(32'h4000_0018, events);
        read_bram_word(8'd8, val);
        if (events !== 32'd3 || val !== 32'd202)
            $fatal(1, "[FAIL] PYNQ top stable button press failed: events=%0d (exp 3), cid2=%0d (exp 202)",
                   events, val);

        // 3c. Поки btn[0] все ще утримується в 1, швидкий PMOD-імпульс ja1 НЕ маскується
        @(negedge dut.clk);
        ja1 = 1'b1;
        repeat (3) @(negedge dut.clk);
        ja1 = 1'b0;
        repeat (20) @(posedge dut.clk);
        wait_pipe_idle();
        dut.ps7.axi_read(32'h4000_0018, events);
        read_bram_word(8'd8, val);
        if (events !== 32'd4 || val !== 32'd203)
            $fatal(1, "[FAIL] PYNQ top ja1 masked while btn[0]==1: events=%0d (exp 4), cid2=%0d (exp 203)",
                   events, val);

        // 3d. Брязкіт при відпусканні btn[0] не породжує хибних фронтів
        @(negedge dut.clk); btn[0] = 1'b0;
        repeat (25) @(negedge dut.clk); btn[0] = 1'b1;
        repeat (25) @(negedge dut.clk); btn[0] = 1'b0;
        repeat (100025) @(posedge dut.clk);
        dut.ps7.axi_read(32'h4000_0018, events);
        if (events !== 32'd4)
            $fatal(1, "[FAIL] PYNQ top button release bounce leaked trigger: events=%0d (exp 4)", events);

        $display("PASS: pynq_z1_top cdc, debounce and param=1 verified");
        $finish;
    end

    initial begin
        #5_000_000;
        $fatal(1, "[FAIL] PYNQ top simulation timed out");
    end
endmodule
