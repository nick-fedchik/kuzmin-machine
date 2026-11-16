`timescale 1ns / 1ps

// ============================================================================
// Модуль: kpol_bram_pipeline_pynq_z1_egress_top.v
// Призначення: Top-level модуль синтезу для плати Digilent PYNQ-Z1 (XC7Z020)
// із інтеграцією PMOD Event Egress (km_pmod_event_egress) на PMOD JA/JB.
// Пов'язує PS7 AXI Master, BRAM-конвеєр (CFG-P), km_pmod_event_egress
// (SPI Mode 0 / PAR8) та індикацію backpressure на LED/PMOD JB.
// ============================================================================

module kpol_bram_pipeline_pynq_z1_egress_top #(
    parameter [31:0] BTN_DEBOUNCE_CYCLES = 32'd100000 // 1.0 ms @ 100 MHz
) (
    // PMOD JA Header (HIL Interface + Egress Control, 3.3V LVCMOS)
    input  wire       ja1,               // Pin 1 (Y18): External trigger stimulus in
    output wire       ja2,               // Pin 2 (Y19): Commit pulse out (stretched 100 ns)
    output wire       ja3,               // Pin 3 (Y16): Reject pulse out (stretched 100 ns)
    output wire       ja4,               // Pin 4 (Y17): Pipeline busy status out
    input  wire       egress_par8_mode_i,// Pin 7 (U18): 0 = SPI Mode 0, 1 = PAR8 mode
    output wire       ja8_egress_start,  // Pin 8 (U19): Egress event_start_o strobe
    output wire       ja9_par_valid,     // Pin 9 (W18): PAR8 par_valid_o
    output wire       ja10_par_clk,      // Pin 10 (W19): PAR8 par_clk_o

    // PMOD JB Header (Egress Data / SPI + Backpressure Status, 3.3V LVCMOS)
    // SPI mode (mode=0): jb[0]=CS_N, jb[1]=MOSI, jb[2]=SCK, jb[3]=START,
    //                    jb[4]=egress_busy, jb[5]=egress_drop_seen, jb[7:6]=0
    // PAR8 mode (mode=1): jb[7:0]=par_data_o[7:0]
    output wire [7:0] jb,

    // On-board Pushbuttons & Switches
    input  wire [3:0] btn,               // btn[0] (D19): Manual trigger button
    input  wire [1:0] sw,                // sw[1:0] (M20, M19): Target CID selection (0..3)

    // On-board User LEDs
    output wire [3:0] led                // led[0] (R14): Commit indicator (~42 ms stretch)
                                         // led[1] (P14): Reject indicator (~42 ms stretch)
                                         // led[2] (N16): Pipeline / Egress busy indicator
                                         // led[3] (M14): FIFO Overflow / Egress drop indicator
);
    wire [3:0] fclk_unbuffered;
    wire clk, rst_n;
    BUFG clk_buf (.I(fclk_unbuffered[0]), .O(clk));

    // AXI signals from PS7
    wire [31:0] araddr, awaddr, wdata, rdata;
    wire [11:0] arid, awid;
    /* verilator lint_off UNUSEDSIGNAL */
    wire [11:0] wid;
    wire [3:1]  _unused_btn = btn[3:1];
    wire [2:0]  _unused_fclk = fclk_unbuffered[3:1];
    /* verilator lint_on UNUSEDSIGNAL */
    wire arvalid, arready, rready, rvalid;
    wire awvalid, awready, wvalid, wready, bready, bvalid;
    wire [3:0] wstrb;
    wire [1:0] rresp, bresp;
    reg [11:0] rid_q, bid_q;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rid_q <= 12'd0;
            bid_q <= 12'd0;
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
    // CDC Synchronizers, Mechanical Button Debouncer & Edge Detectors
    // ------------------------------------------------------------------------
    localparam [31:0] BTN_DB_LIMIT = (BTN_DEBOUNCE_CYCLES > 32'd1)
                                   ? (BTN_DEBOUNCE_CYCLES - 32'd1)
                                   : 32'd0;

    // 1. PMOD JA1 fast digital stimulus: 2-FF CDC + rising-edge detector
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

    // 2. Manual pushbutton btn[0]: 2-FF CDC + 1.0 ms debounce + rising-edge detector
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

    // 3. Slide switches sw[1:0] & egress_par8_mode_i: 2-FF CDC synchronizers
    (* ASYNC_REG = "TRUE" *) reg [1:0] sw_cdc_0_q;
    (* ASYNC_REG = "TRUE" *) reg [1:0] sw_cdc_1_q;
    (* ASYNC_REG = "TRUE" *) reg [1:0] par8_mode_cdc_q;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sw_cdc_0_q      <= 2'b00;
            sw_cdc_1_q      <= 2'b00;
            par8_mode_cdc_q <= 2'b00;
        end else begin
            sw_cdc_0_q      <= sw;
            sw_cdc_1_q      <= sw_cdc_0_q;
            par8_mode_cdc_q <= {par8_mode_cdc_q[0], egress_par8_mode_i};
        end
    end

    wire ext_hw_trig_pulse = ja1_trig_pulse | btn0_trig_pulse;
    wire [5:0] target_cid  = {4'd0, sw_cdc_1_q};
    wire       par8_mode   = par8_mode_cdc_q[1];

    // ------------------------------------------------------------------------
    // Pipeline Instance
    // ------------------------------------------------------------------------
    wire hw_commit, hw_reject, pipe_busy, fifo_overflow;
    wire [5:0]  hw_commit_cid;
    wire [31:0] hw_last_committed_state;
    /* verilator lint_off UNUSEDSIGNAL */
    wire        hw_ready;
    wire [31:0] events_dropped;
    wire        axi_busy;
    /* verilator lint_on UNUSEDSIGNAL */

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
        .ext_hw_trigger_param_i(32'd1),
        .hw_trigger_ready_o(hw_ready),
        .hw_commit_pulse_o(hw_commit),
        .hw_reject_pulse_o(hw_reject),
        .hw_pipeline_busy_o(pipe_busy),
        .fifo_overflow_o(fifo_overflow),
        .events_dropped_count_o(events_dropped),
        .hw_commit_cid_o(hw_commit_cid),
        .hw_last_committed_state_o(hw_last_committed_state),
        .busy(axi_busy)
    );

    // 1-cycle alignment: hw_commit_cid and hw_last_committed_state are valid
    // on the cycle immediately following hw_commit_pulse_o.
    reg hw_commit_d_q;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            hw_commit_d_q <= 1'b0;
        else
            hw_commit_d_q <= hw_commit;
    end

    // ------------------------------------------------------------------------
    // PMOD Event Egress Instance (SPI Mode 0 / PAR8)
    // ------------------------------------------------------------------------
    wire        egress_event_start;
    wire        spi_cs_n, spi_sck, spi_mosi;
    wire        par_valid, par_clk;
    wire [7:0]  par_data;
    wire        egress_busy;
    wire [31:0] egress_drop_count;
    /* verilator lint_off UNUSEDSIGNAL */
    wire        egress_ready;
    wire [31:0] egress_tx_count;
    /* verilator lint_on UNUSEDSIGNAL */

    km_pmod_event_egress u_egress (
        .clk           (clk),
        .rst_n         (rst_n),
        .mode_par8_i   (par8_mode),
        .event_valid_i (hw_commit_d_q),
        .event_cid_i   (hw_commit_cid),
        .event_mask_i  (32'd0),
        .event_state_i (hw_last_committed_state),
        .event_start_o (egress_event_start),
        .spi_cs_n_o    (spi_cs_n),
        .spi_sck_o     (spi_sck),
        .spi_mosi_o    (spi_mosi),
        .par_valid_o   (par_valid),
        .par_clk_o     (par_clk),
        .par_data_o    (par_data),
        .busy_o        (egress_busy),
        .ready_o       (egress_ready),
        .tx_count_o    (egress_tx_count),
        .drop_count_o  (egress_drop_count)
    );

    wire egress_drop_seen = (egress_drop_count != 32'd0);

    assign ja8_egress_start = egress_event_start;
    assign ja9_par_valid    = par_valid;
    assign ja10_par_clk     = par_clk;

    assign jb = par8_mode
              ? par_data
              : {2'b00, egress_drop_seen, egress_busy, egress_event_start, spi_sck, spi_mosi, spi_cs_n};

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
    assign led[2] = pipe_busy | egress_busy;
    assign led[3] = fifo_overflow | egress_drop_seen;

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
