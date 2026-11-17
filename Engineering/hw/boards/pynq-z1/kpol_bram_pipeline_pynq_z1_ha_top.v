`timescale 1ns / 1ps

// ============================================================================
// Модуль: kpol_bram_pipeline_pynq_z1_ha_top.v
// Призначення: Top-level модуль синтезу для плати Digilent PYNQ-Z1 (XC7Z020)
// із двобанковим ядром високої готовності CFG-P-HA (B4 Варіант 2, Issue #253,
// експеримент EXP-GPU-02).
//
// Пов'язує PS7 AXI4-Lite GP0 Master (0x40000000..0x40001FFF), двобанковий
// конвеєр дескрипторів kpol_bram_pipeline_axi_ha, штатні порти PMOD JA
// (ja1 стимул з 2-FF CDC, ja2..ja4 розтягнуті індикатори 100 нс), кнопки/
// перемикачі/світлодіоди та виводить нерозтягнуті 1-тактові (10 нс) строби
// протоколу EXP-GPU-02 на роз'єм PMOD JB (3.3V LVCMOS33) для логічного
// аналізатора RP2040 PIO (GP0..GP4) і сигнал active_bank_o на jb8.
// ============================================================================

module kpol_bram_pipeline_pynq_z1_ha_top #(
    parameter [31:0] BTN_DEBOUNCE_CYCLES = 32'd100000 // 1.0 ms @ 100 MHz
) (
    // PMOD JA Header (HIL Interface, 3.3V LVCMOS33)
    input  wire       ja1,       // Pin 1 (Y18): External trigger stimulus in
    output wire       ja2,       // Pin 2 (Y19): Commit pulse out (stretched 100 ns)
    output wire       ja3,       // Pin 3 (Y16): Reject pulse out (stretched 100 ns)
    output wire       ja4,       // Pin 4 (Y17): Pipeline busy status out

    // PMOD JB Header (EXP-GPU-02 unstretched 1-cycle 10 ns strobes for RP2040 PIO, 3.3V LVCMOS33)
    output wire       jb1,       // Pin 1 (W14): inject_strobe_o      (GP0: INJECT_STROBE)
    output wire       jb2,       // Pin 2 (Y14): bank_swap_commit_o   (GP1: BANK_SWAP_COMMIT)
    output wire       jb3,       // Pin 3 (T11): stimulus_accepted_o  (GP2: STIMULUS_EVENT)
    output wire       jb4,       // Pin 4 (T10): reaction_out_o       (GP3: REACTION_OUT)
    output wire       jb7,       // Pin 7 (V16): seq_cycle_done_o     (GP4: SEQ_CYCLE_DONE)
    output wire       jb8,       // Pin 8 (W16): active_bank_o        (Active bank level 0/1)

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
    wire [11:0] arid, awid;
    /* verilator lint_off UNUSEDSIGNAL */
    wire [11:0] wid;
    wire [3:1]  _unused_btn  = btn[3:1];
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
    // Dual-Bank Pipeline Instance (CFG-P-HA, B4 Variant 2)
    // ------------------------------------------------------------------------
    wire hw_commit, hw_reject, pipe_busy, fifo_overflow;
    wire inject_strobe, bank_swap_commit, stimulus_accepted, reaction_out, seq_cycle_done;
    /* verilator lint_off UNUSEDSIGNAL */
    wire        hw_ready;
    wire [31:0] events_dropped;
    wire [5:0]  hw_commit_cid;
    wire [31:0] hw_last_committed_state;
    wire        axi_busy;
    /* verilator lint_on UNUSEDSIGNAL */

    kpol_bram_pipeline_axi_ha pipeline_ha (
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
        .inject_strobe_o(inject_strobe),
        .bank_swap_commit_o(bank_swap_commit),
        .stimulus_accepted_o(stimulus_accepted),
        .reaction_out_o(reaction_out),
        .seq_cycle_done_o(seq_cycle_done),
        .busy(axi_busy)
    );

    // Track active bank level (0/1) via top-wrapper register active_bank_top_q:
    // kpol_bram_pipeline_axi_ha exposes active_bank via MMIO register 0x038[0], so the top wrapper
    // maintains active_bank_top_q toggled synchronously by bank_swap_commit_o under shared rst_n.
    reg active_bank_top_q;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            active_bank_top_q <= 1'b0;
        end else if (bank_swap_commit) begin
            active_bank_top_q <= ~active_bank_top_q;
        end
    end

    // Direct 1-cycle (10 ns) unstretched outputs on PMOD JB for RP2040 PIO (GP0..GP4) + active_bank_top_q
    assign jb1 = inject_strobe;
    assign jb2 = bank_swap_commit;
    assign jb3 = stimulus_accepted;
    assign jb4 = reaction_out;
    assign jb7 = seq_cycle_done;
    assign jb8 = active_bank_top_q;

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
