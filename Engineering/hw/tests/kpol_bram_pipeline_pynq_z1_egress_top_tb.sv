`timescale 1ns / 1ps

// Спрощені поведінкові моделі примітивів Zynq-7000 для RTL-симуляції top-модуля PYNQ-Z1 egress
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

module kpol_bram_pipeline_pynq_z1_egress_top_tb;
    reg        ja1 = 1'b0;
    wire       ja2, ja3, ja4;
    reg        egress_par8_mode_i = 1'b0;
    wire       ja8_egress_start, ja9_par_valid, ja10_par_clk;
    wire [7:0] jb;
    reg  [3:0] btn = 4'b0000;
    reg  [1:0] sw  = 2'b00;
    wire [3:0] led;

    kpol_bram_pipeline_pynq_z1_egress_top dut (
        .ja1                (ja1),
        .ja2                (ja2),
        .ja3                (ja3),
        .ja4                (ja4),
        .egress_par8_mode_i (egress_par8_mode_i),
        .ja8_egress_start   (ja8_egress_start),
        .ja9_par_valid      (ja9_par_valid),
        .ja10_par_clk       (ja10_par_clk),
        .jb                 (jb),
        .btn                (btn),
        .sw                 (sw),
        .led                (led)
    );

    initial begin
        #200000;
        $fatal(1, "[TB] WATCHDOG TIMEOUT");
    end

    function automatic [7:0] ref_crc8(input [55:0] payload);
        integer idx;
        reg [7:0] c;
        reg       msb;
        begin
            c = 8'h00;
            for (idx = 55; idx >= 0; idx = idx - 1) begin
                msb = c[7] ^ payload[idx];
                c = {c[6:0], 1'b0} ^ (msb ? 8'h07 : 8'h00);
            end
            ref_crc8 = c;
        end
    endfunction

    // SPI Mode 0 decoder on PMOD JB (jb[0]=CS_N, jb[1]=MOSI, jb[2]=SCK)
    wire spi_cs_n = jb[0];
    wire spi_mosi = jb[1];
    wire spi_sck  = jb[2];

    reg [63:0] spi_rx_frame = 64'd0;
    integer    spi_rx_bits  = 0;
    reg        spi_rx_done  = 1'b0;

    always @(posedge spi_sck) begin
        if (dut.rst_n && !egress_par8_mode_i && !spi_cs_n) begin
            spi_rx_frame <= {spi_rx_frame[62:0], spi_mosi};
            spi_rx_bits  <= spi_rx_bits + 1;
        end
    end

    always @(posedge spi_cs_n) begin
        if (dut.rst_n && !egress_par8_mode_i && spi_rx_bits > 0) begin
            spi_rx_done <= 1'b1;
        end
    end

    // PAR8 decoder on PMOD JB (jb[7:0]=data, ja9_par_valid=valid, ja10_par_clk=clk)
    reg [63:0] par_rx_frame = 64'd0;
    integer    par_rx_bytes = 0;
    reg        par_rx_done  = 1'b0;

    always @(posedge ja10_par_clk) begin
        if (dut.rst_n && egress_par8_mode_i && ja9_par_valid) begin
            par_rx_frame <= {par_rx_frame[55:0], jb};
            par_rx_bytes <= par_rx_bytes + 1;
        end
    end

    always @(negedge ja9_par_valid) begin
        if (dut.rst_n && egress_par8_mode_i && par_rx_bytes > 0) begin
            par_rx_done <= 1'b1;
        end
    end

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

    task automatic verify_frame(
        input [63:0] rx_frame,
        input [5:0]  exp_cid,
        input [15:0] exp_mask16,
        input [31:0] exp_state,
        input [8*16-1:0] label
    );
        reg [55:0] exp_payload;
        reg [7:0]  exp_crc;
        begin
            exp_payload = {2'b01, exp_cid, exp_mask16, exp_state};
            exp_crc     = ref_crc8(exp_payload);
            if (rx_frame !== {exp_crc, exp_payload}) begin
                $fatal(1, "[FAIL] (%0s) frame mismatch: got=%h exp=%h",
                       label, rx_frame, {exp_crc, exp_payload});
            end
        end
    endtask

    initial begin
        reg [31:0] val;

        repeat (4) @(negedge dut.clk);
        dut.ps7.MAXIGP0ARESETN = 1'b1;
        repeat (4) @(posedge dut.clk);

        for (int i = 0; i < 256; i++) begin
            write_bram_word(i[7:0], 32'd0);
        end

        // CID 2 (words 8..11): state=200, threshold=0, pred=GT (0x02), guard=0x03, action=INC (0x01)
        write_bram_word(8'd8,  32'd200);
        write_bram_word(8'd9,  32'd0);
        write_bram_word(8'd10, 32'h0100_0302);
        write_bram_word(8'd11, 32'd0);

        // --------------------------------------------------------------------
        // Test 1: End-to-End SPI Mode 0 (ja1 -> BRAM commit 200->201 -> PMOD JB)
        // --------------------------------------------------------------------
        egress_par8_mode_i = 1'b0;
        sw = 2'b10; // CID 2
        repeat (4) @(posedge dut.clk);

        spi_rx_bits = 0;
        spi_rx_done = 1'b0;

        @(negedge dut.clk);
        ja1 = 1'b1;
        repeat (3) @(negedge dut.clk);
        ja1 = 1'b0;

        wait(spi_rx_done == 1'b1);
        wait_pipe_idle();
        read_bram_word(8'd8, val);
        if (val !== 32'd201 || spi_rx_bits !== 64)
            $fatal(1, "[FAIL] E2E SPI: bram=%0d bits=%0d", val, spi_rx_bits);
        verify_frame(spi_rx_frame, 6'd2, 16'h0000, 32'd201, "TOP-E2E-SPI");
        $display("PASS: pynq_z1_egress_top E2E SPI frame=%h", spi_rx_frame);

        // --------------------------------------------------------------------
        // Test 2: End-to-End PAR8 Mode (ja1 -> BRAM commit 201->202 -> PMOD JB)
        // --------------------------------------------------------------------
        egress_par8_mode_i = 1'b1;
        repeat (4) @(posedge dut.clk);

        par_rx_bytes = 0;
        par_rx_done  = 1'b0;

        @(negedge dut.clk);
        ja1 = 1'b1;
        repeat (3) @(negedge dut.clk);
        ja1 = 1'b0;

        wait(par_rx_done == 1'b1);
        wait_pipe_idle();
        read_bram_word(8'd8, val);
        if (val !== 32'd202 || par_rx_bytes !== 8)
            $fatal(1, "[FAIL] E2E PAR8: bram=%0d bytes=%0d", val, par_rx_bytes);
        verify_frame(par_rx_frame, 6'd2, 16'h0000, 32'd202, "TOP-E2E-PAR8");
        if (led[3] !== 1'b0)
            $fatal(1, "[FAIL] E2E PAR8: unexpected drop/overflow LED led[3]=%b", led[3]);
        $display("PASS: pynq_z1_egress_top E2E PAR8 frame=%h", par_rx_frame);

        $display("PASS: ALL PYNQ_Z1_EGRESS_TOP E2E TESTS PASSED");
        $finish;
    end
endmodule
