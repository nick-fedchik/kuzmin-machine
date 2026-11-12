module kpol_txn_gate_pynq_z1_top (
    output wire [3:0] led,
    output wire       rgb4_r,
    output wire       rgb4_g,
    output wire       rgb4_b,
    output wire       rgb5_r,
    output wire       rgb5_g,
    output wire       rgb5_b,
    input  wire [3:0] btn,
    input  wire [1:0] sw,
    output wire       ja1,
    output wire       ja2,
    output wire       ja3
);
    wire [3:0] fclk_unbuffered;
    wire fclk0;

    BUFG fclk0_buf (
        .I(fclk_unbuffered[0]),
        .O(fclk0)
    );

    wire gp0_aresetn;
    wire [31:0] gp0_araddr;
    wire [11:0] gp0_arid;
    wire gp0_arvalid;
    wire gp0_arready;
    wire gp0_rready;
    wire [31:0] gp0_rdata;
    wire [1:0] gp0_rresp;
    wire gp0_rvalid;
    wire [31:0] gp0_awaddr;
    wire [11:0] gp0_awid;
    wire [11:0] gp0_wid;
    wire gp0_awvalid;
    wire gp0_awready;
    wire [31:0] gp0_wdata;
    wire [3:0] gp0_wstrb;
    wire gp0_wvalid;
    wire gp0_wready;
    wire gp0_bready;
    wire [1:0] gp0_bresp;
    wire gp0_bvalid;

    wire [11:0] gp0_bid = gp0_wid;
    wire [11:0] gp0_rid = gp0_arid;
    wire gp0_rlast = 1'b1;

    wire [12:0] gate_awaddr =
        (gp0_awaddr >= 32'h40000000 && gp0_awaddr < 32'h40002000) ? gp0_awaddr[12:0] : 13'h1fff;
    wire [12:0] gate_araddr =
        (gp0_araddr >= 32'h40000000 && gp0_araddr < 32'h40002000) ? gp0_araddr[12:0] : 13'h1fff;

    wire [7:0]  status_mon;
    wire [31:0] state_mon;
    wire        reactive_out_0p0;

    // Heartbeat counter (100 MHz clock -> ~1.49 Hz toggle on bit 25)
    reg [25:0] hb_counter;
    always @(posedge fclk0 or negedge gp0_aresetn) begin
        if (!gp0_aresetn)
            hb_counter <= 26'd0;
        else
            hb_counter <= hb_counter + 26'd1;
    end
    wire hb_pulse = hb_counter[25];

    // BTN0 debounce filter (~10.4 ms @ 100 MHz)
    reg [19:0] btn0_cnt;
    reg btn0_debounced;
    reg btn0_q;
    always @(posedge fclk0 or negedge gp0_aresetn) begin
        if (!gp0_aresetn) begin
            btn0_cnt <= 20'd0;
            btn0_debounced <= 1'b0;
            btn0_q <= 1'b0;
        end else begin
            if (btn[0] != btn0_debounced) begin
                btn0_cnt <= btn0_cnt + 20'd1;
                if (btn0_cnt == 20'hFFFFF) begin
                    btn0_debounced <= btn[0];
                    btn0_cnt <= 20'd0;
                end
            end else begin
                btn0_cnt <= 20'd0;
            end
            btn0_q <= btn0_debounced;
        end
    end
    wire btn0_rise = btn0_debounced && !btn0_q;

    // Conditions from physical switches:
    // sw[0]: 1 = Invariant true, 0 = Invariant violation (Fail-closed!)
    // sw[1]: 1 = Assumption true, 0 = Assumption false (Input reject)
    wire [6:0] btn_conditions = {
        1'b0,         // hazard_true
        1'b1,         // hazard_known
        sw[0],        // invariant_true (SW0)
        1'b1,         // invariant_known
        sw[1],        // assumption_true (SW1)
        1'b1,         // assumption_known
        1'b1          // candidate_known
    };
    wire [31:0] btn_candidate = state_mon + 32'd1;

    kpol_txn_gate_axi_lite gate (
        .s_axi_aclk(fclk0),
        .s_axi_aresetn(gp0_aresetn),
        .s_axi_awaddr(gate_awaddr),
        .s_axi_awvalid(gp0_awvalid),
        .s_axi_awready(gp0_awready),
        .s_axi_wdata(gp0_wdata),
        .s_axi_wstrb(gp0_wstrb),
        .s_axi_wvalid(gp0_wvalid),
        .s_axi_wready(gp0_wready),
        .s_axi_bresp(gp0_bresp),
        .s_axi_bvalid(gp0_bvalid),
        .s_axi_bready(gp0_bready),
        .s_axi_araddr(gate_araddr),
        .s_axi_arvalid(gp0_arvalid),
        .s_axi_arready(gp0_arready),
        .s_axi_rdata(gp0_rdata),
        .s_axi_rresp(gp0_rresp),
        .s_axi_rvalid(gp0_rvalid),
        .s_axi_rready(gp0_rready),
        .status_monitor_o(status_mon),
        .state_monitor_o(state_mon),
        .ext_event_valid_i(btn0_rise),
        .ext_candidate_value_i(btn_candidate),
        .ext_conditions_i(btn_conditions),
        .ext_pin_0p0_i(btn[0]),
        .reactive_out_0p0_o(reactive_out_0p0)
    );

    // PMODA Signals:
    // JA1 (Pin 1): Stimulus Monitor (driven by BTN0 directly to Pico Channel 1)
    // JA2 (Pin 2): Reactive Output from RTL Transaction Gate (to Pico Channel 2)
    // JA3 (Pin 3): Mirror of Reactive Output
    assign ja1 = btn[0];
    assign ja2 = reactive_out_0p0;
    assign ja3 = reactive_out_0p0;

    // Green LEDs LD0..LD3:
    // LD0 = Committed OR Reactive Pin "0p0" Active
    // LD1 = Rejected Invariant (Fail-Closed)
    // LD2 = Hazard Observed
    // LD3 = Rejected Input
    assign led[0] = status_mon[1] | reactive_out_0p0;
    assign led[1] = status_mon[4];
    assign led[2] = status_mon[6];
    assign led[3] = status_mon[3];

    // RGB4: Transaction Status (Green = Commit, Red = Invariant Reject, Blue = Input/Hazard)
    assign rgb4_g = status_mon[1];
    assign rgb4_r = status_mon[4];
    assign rgb4_b = status_mon[3] || status_mon[6];

    // RGB5: Heartbeat Pulse (Cyan/Green blinking ~1.5 Hz)
    assign rgb5_r = 1'b0;
    assign rgb5_g = hb_pulse;
    assign rgb5_b = hb_pulse;

    PS7 ps7 (
        .FCLKCLK(fclk_unbuffered),
        .MAXIGP0ACLK(fclk0),
        .MAXIGP0ARESETN(gp0_aresetn),
        .MAXIGP0ARADDR(gp0_araddr),
        .MAXIGP0ARID(gp0_arid),
        .MAXIGP0ARVALID(gp0_arvalid),
        .MAXIGP0ARREADY(gp0_arready),
        .MAXIGP0RREADY(gp0_rready),
        .MAXIGP0RDATA(gp0_rdata),
        .MAXIGP0RID(gp0_rid),
        .MAXIGP0RLAST(gp0_rlast),
        .MAXIGP0RRESP(gp0_rresp),
        .MAXIGP0RVALID(gp0_rvalid),
        .MAXIGP0AWADDR(gp0_awaddr),
        .MAXIGP0AWID(gp0_awid),
        .MAXIGP0AWVALID(gp0_awvalid),
        .MAXIGP0AWREADY(gp0_awready),
        .MAXIGP0WDATA(gp0_wdata),
        .MAXIGP0WSTRB(gp0_wstrb),
        .MAXIGP0WID(gp0_wid),
        .MAXIGP0WVALID(gp0_wvalid),
        .MAXIGP0WREADY(gp0_wready),
        .MAXIGP0BREADY(gp0_bready),
        .MAXIGP0BID(gp0_bid),
        .MAXIGP0BRESP(gp0_bresp),
        .MAXIGP0BVALID(gp0_bvalid)
    );
endmodule
