`timescale 1ns / 1ps

// ============================================================================
// Модуль: kpol_bram_pipeline_pynq_z1_top.v
// Призначення: Top-level модуль синтезу для плати Digilent PYNQ-Z1 (XC7Z020).
// Пов'язує PS7 AXI Master, BRAM-конвеєр (CFG-P), роз'єм PMOD JA (HIL)
// та користувацькі кнопки/перемикачі/світлодіоди.
// Відповідає нормативній архітектурі B2 (REQ-SYS-011..012, REQ-HW-011..013),
// схемі HWE.2 та вимірювальному стенду HWE.3/HWE.4.
// ============================================================================

module kpol_bram_pipeline_pynq_z1_top #(
    parameter [31:0] BTN_DEBOUNCE_CYCLES = 32'd100000 // 1.0 ms @ 100 MHz
) (
    // PMOD JA Header (HIL Interface, 3.3V LVCMOS)
    input  wire       ja1,       // Pin 1 (Y18): External trigger stimulus in
    output wire       ja2,       // Pin 2 (Y19): Commit pulse out (stretched 100 ns)
    output wire       ja3,       // Pin 3 (Y16): Reject pulse out (stretched 100 ns)
    output wire       ja4,       // Pin 4 (Y17): Pipeline busy status out

    // On-board Pushbuttons & Switches
    input  wire [3:0] btn,       // btn[0] (D19): Manual trigger button
    input  wire [1:0] sw,        // sw[1:0] (M20, M19): Target CID selection (0..3)

    // On-board User LEDs
    output wire [3:0] led        // led[0] (R14): Commit indicator (~42 ms stretch)
                                 // led[1] (P14): Reject indicator (~42 ms stretch)
                                 // led[2] (N16): Pipeline busy indicator
                                 // led[3] (M14): FIFO Overflow indicator
);
    wire [3:0] fclk_unbuffered;
    wire clk, rst_n;
    BUFG clk_buf (.I(fclk_unbuffered[0]), .O(clk));

    // AXI signals from PS7
    wire [31:0] araddr, awaddr, wdata, rdata;
    wire [11:0] arid, awid, wid;
    wire arvalid, arready, rready, rvalid;
    wire awvalid, awready, wvalid, wready, bready, bvalid;
    wire [3:0] wstrb;
    wire [1:0] rresp, bresp;
    reg [11:0] rid_q, bid_q;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rid_q <= 0;
            bid_q <= 0;
        end else begin
            if (arvalid && arready) rid_q <= arid;
            if (awvalid && awready) bid_q <= awid;
        end
    end

    wire [12:0] local_awaddr =
        (awaddr >= 32'h40000000 && awaddr < 32'h40002000) ? awaddr[12:0] : 13'h1fff;
    wire [12:0] local_araddr =
        (araddr >= 32'h40000000 && araddr < 32'h40002000) ? araddr[12:0] : 13'h1fff;

    // ------------------------------------------------------------------------
    // CDC Synchronizers, Mechanical Button Debouncer & Edge Detectors (REQ-HW-011)
    // ------------------------------------------------------------------------
    localparam [31:0] BTN_DB_LIMIT = (BTN_DEBOUNCE_CYCLES > 32'd1)
                                   ? (BTN_DEBOUNCE_CYCLES - 32'd1)
                                   : 32'd0;

    // 1. PMOD JA1 fast digital stimulus: dedicated 2-FF CDC + rising-edge detector
    (* ASYNC_REG = "TRUE" *) reg [1:0] ja1_cdc_q;
    reg ja1_d_q;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ja1_cdc_q <= 2'b00;
            ja1_d_q   <= 1'b0;
        end else begin
            ja1_cdc_q <= {ja1_cdc_q[0], ja1};
            ja1_d_q   <= ja1_cdc_q[1];
        end
    end

    wire ja1_trig_pulse = ja1_cdc_q[1] & ~ja1_d_q;

    // 2. Manual pushbutton btn[0]: 2-FF CDC + 1.0 ms debounce filter + rising-edge detector
    (* ASYNC_REG = "TRUE" *) reg [1:0] btn0_cdc_q;
    reg [31:0] btn0_db_cnt_q;
    reg        btn0_stable_q;
    reg        btn0_stable_d_q;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            btn0_cdc_q      <= 2'b00;
            btn0_db_cnt_q   <= 32'd0;
            btn0_stable_q   <= 1'b0;
            btn0_stable_d_q <= 1'b0;
        end else begin
            btn0_cdc_q      <= {btn0_cdc_q[0], btn[0]};
            btn0_stable_d_q <= btn0_stable_q;

            if (btn0_cdc_q[1] == btn0_stable_q) begin
                btn0_db_cnt_q <= 32'd0;
            end else if (btn0_db_cnt_q >= BTN_DB_LIMIT) begin
                btn0_stable_q <= btn0_cdc_q[1];
                btn0_db_cnt_q <= 32'd0;
            end else begin
                btn0_db_cnt_q <= btn0_db_cnt_q + 32'd1;
            end
        end
    end

    wire btn0_trig_pulse = btn0_stable_q & ~btn0_stable_d_q;

    // 3. Slide switches sw[1:0]: dedicated 2-FF CDC synchronizer into clk domain
    (* ASYNC_REG = "TRUE" *) reg [1:0] sw_cdc_0_q;
    (* ASYNC_REG = "TRUE" *) reg [1:0] sw_cdc_1_q;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sw_cdc_0_q <= 2'b00;
            sw_cdc_1_q <= 2'b00;
        end else begin
            sw_cdc_0_q <= sw;
            sw_cdc_1_q <= sw_cdc_0_q;
        end
    end

    wire ext_hw_trig_pulse = ja1_trig_pulse | btn0_trig_pulse;
    wire [5:0] target_cid  = {4'd0, sw_cdc_1_q};

    // ------------------------------------------------------------------------
    // Pipeline Instance
    // ------------------------------------------------------------------------
    wire hw_commit, hw_reject, pipe_busy, fifo_overflow;
    wire hw_ready;
    wire [31:0] events_dropped;

    kpol_bram_pipeline_axi pipeline (
        .clk(clk),
        .rst_n(rst_n),
        .awaddr(local_awaddr),
        .awvalid(awvalid),
        .awready(awready),
        .wdata(wdata),
        .wstrb(wstrb),
        .wvalid(wvalid),
        .wready(wready),
        .bresp(bresp),
        .bvalid(bvalid),
        .bready(bready),
        .araddr(local_araddr),
        .arvalid(arvalid),
        .arready(arready),
        .rdata(rdata),
        .rresp(rresp),
        .rvalid(rvalid),
        .rready(rready),
        .ext_hw_trigger_valid_i(ext_hw_trig_pulse),
        .ext_hw_trigger_cid_i(target_cid),
        .ext_hw_trigger_param_i(32'd1), // Fixed hardware trigger parameter = 1 for standalone PMOD/button events
        .hw_trigger_ready_o(hw_ready),
        .hw_commit_pulse_o(hw_commit),
        .hw_reject_pulse_o(hw_reject),
        .hw_pipeline_busy_o(pipe_busy),
        .fifo_overflow_o(fifo_overflow),
        .events_dropped_count_o(events_dropped),
        .busy()
    );

    // ------------------------------------------------------------------------
    // Pulse Stretchers for PMOD JA (100 ns = 10 clock cycles @ 100 MHz)
    // ------------------------------------------------------------------------
    reg [3:0] ja_commit_cnt_q;
    reg [3:0] ja_reject_cnt_q;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ja_commit_cnt_q <= 4'd0;
            ja_reject_cnt_q <= 4'd0;
        end else begin
            if (hw_commit)
                ja_commit_cnt_q <= 4'd10;
            else if (ja_commit_cnt_q != 4'd0)
                ja_commit_cnt_q <= ja_commit_cnt_q - 4'd1;

            if (hw_reject)
                ja_reject_cnt_q <= 4'd10;
            else if (ja_reject_cnt_q != 4'd0)
                ja_reject_cnt_q <= ja_reject_cnt_q - 4'd1;
        end
    end

    assign ja2 = (ja_commit_cnt_q != 4'd0);
    assign ja3 = (ja_reject_cnt_q != 4'd0);
    assign ja4 = pipe_busy;

    // ------------------------------------------------------------------------
    // Pulse Stretchers for User LEDs (~42 ms = 2^22 cycles for human visibility)
    // ------------------------------------------------------------------------
    reg [21:0] led_commit_cnt_q;
    reg [21:0] led_reject_cnt_q;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            led_commit_cnt_q <= 22'd0;
            led_reject_cnt_q <= 22'd0;
        end else begin
            if (hw_commit)
                led_commit_cnt_q <= 22'd4194303;
            else if (led_commit_cnt_q != 22'd0)
                led_commit_cnt_q <= led_commit_cnt_q - 22'd1;

            if (hw_reject)
                led_reject_cnt_q <= 22'd4194303;
            else if (led_reject_cnt_q != 22'd0)
                led_reject_cnt_q <= led_reject_cnt_q - 22'd1;
        end
    end

    assign led[0] = (led_commit_cnt_q != 22'd0);
    assign led[1] = (led_reject_cnt_q != 22'd0);
    assign led[2] = pipe_busy;
    assign led[3] = fifo_overflow;

    // ------------------------------------------------------------------------
    // PS7 Processing System Instantiation
    // ------------------------------------------------------------------------
    PS7 ps7 (
        .FCLKCLK(fclk_unbuffered),
        .MAXIGP0ACLK(clk), .MAXIGP0ARESETN(rst_n),
        .MAXIGP0ARADDR(araddr), .MAXIGP0ARID(arid),
        .MAXIGP0ARVALID(arvalid), .MAXIGP0ARREADY(arready),
        .MAXIGP0RREADY(rready), .MAXIGP0RDATA(rdata), .MAXIGP0RID(rid_q),
        .MAXIGP0RLAST(1'b1), .MAXIGP0RRESP(rresp), .MAXIGP0RVALID(rvalid),
        .MAXIGP0AWADDR(awaddr), .MAXIGP0AWID(awid),
        .MAXIGP0AWVALID(awvalid), .MAXIGP0AWREADY(awready),
        .MAXIGP0WDATA(wdata), .MAXIGP0WSTRB(wstrb), .MAXIGP0WID(wid),
        .MAXIGP0WVALID(wvalid), .MAXIGP0WREADY(wready),
        .MAXIGP0BREADY(bready), .MAXIGP0BID(bid_q),
        .MAXIGP0BRESP(bresp), .MAXIGP0BVALID(bvalid)
    );
endmodule
