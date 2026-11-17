`timescale 1ns / 1ps

// ============================================================================
// Testbench: km_reg_configurable_cascade_axi_tb.sv
// Verifies:
// 1. Cycle-accurate 1-cycle-per-step latency (10 ns single step, 40 ns full
//    4-concept cascade C0 -> C1 -> C2 -> C3 at 100 MHz).
// 2. Online AXI4-Lite rule reconfiguration via direct MMIO window 0x100..0x4FC
//    and indirect 0x004/0x008 without resynthesis, plus SLVERR protection when busy.
// 3. Plusarg trace execution (+image_hex=..., +events_hex=..., +update_hex=...)
//    for bit-exact cross-checking against kpol_reference.py, C99, and CFG-P.
// ============================================================================

module km_reg_configurable_cascade_axi_tb;
    parameter int NUM_CONCEPTS = 4;

    logic        clk = 1'b0;
    logic        rst_n = 1'b0;
    logic [12:0] awaddr = 13'd0;
    logic        awvalid = 1'b0;
    wire         awready;
    logic [31:0] wdata = 32'd0;
    logic [3:0]  wstrb = 4'hf;
    logic        wvalid = 1'b0;
    wire         wready;
    wire  [1:0]  bresp;
    wire         bvalid;
    logic        bready = 1'b0;

    logic [12:0] araddr = 13'd0;
    logic        arvalid = 1'b0;
    wire         arready;
    wire  [31:0] rdata;
    wire  [1:0]  rresp;
    wire         rvalid;
    logic        rready = 1'b0;

    logic        ext_hw_trigger_valid_i = 1'b0;
    logic [5:0]  ext_hw_trigger_cid_i = 6'd0;
    logic [31:0] ext_hw_trigger_param_i = 32'd0;
    wire         hw_trigger_ready_o;
    wire         hw_commit_pulse_o;
    wire         hw_reject_pulse_o;
    wire         hw_pipeline_busy_o;
    wire         fifo_overflow_o;
    wire  [31:0] events_dropped_count_o;
    wire  [5:0]  hw_commit_cid_o;
    wire  [31:0] hw_last_committed_state_o;
    wire         busy;

    always #5 clk = ~clk; // 100 MHz (10 ns period)

    km_reg_configurable_cascade_axi #(
        .NUM_CONCEPTS(NUM_CONCEPTS),
        .QUEUE_DEPTH(16),
        .DATA_WIDTH(32)
    ) dut (.*);

    task automatic axi_write(
        input [12:0] addr,
        input [31:0] data,
        input [3:0]  strb,
        input [1:0]  expected_resp
    );
        @(negedge clk);
        awaddr  = addr;
        wdata   = data;
        wstrb   = strb;
        awvalid = 1'b1;
        wvalid  = 1'b1;
        bready  = 1'b1;
        do @(posedge clk); while (!awready || !wready);
        @(negedge clk);
        awvalid = 1'b0;
        wvalid  = 1'b0;
        while (!bvalid) @(negedge clk);
        if (bresp !== expected_resp)
            $fatal(1, "AXI write 0x%03h resp=%0d expected=%0d", addr, bresp, expected_resp);
        @(negedge clk);
        bready = 1'b0;
    endtask

    task automatic axi_read(input [12:0] addr, output [31:0] data);
        @(negedge clk);
        araddr  = addr;
        arvalid = 1'b1;
        rready  = 1'b1;
        do @(posedge clk); while (!arready);
        @(negedge clk);
        arvalid = 1'b0;
        while (!rvalid) @(negedge clk);
        if (rresp !== 2'b00)
            $fatal(1, "AXI read 0x%03h resp=%0d", addr, rresp);
        data = rdata;
        @(negedge clk);
        rready = 1'b0;
    endtask

    task automatic load_image_direct(input reg [4095:0] hex_path);
        logic [31:0] img [0:255];
        $readmemh(hex_path, img);
        for (int i = 0; i < NUM_CONCEPTS * 4; i++) begin
            axi_write(13'h100 + (i[12:0] << 2), img[i], 4'hf, 2'b00);
        end
    endtask

    task automatic trigger_and_count_cycles(
        input  [5:0]  cid,
        input  [31:0] param,
        output int    busy_cycles,
        output int    commit_pulses,
        output int    reject_pulses
    );
        busy_cycles   = 0;
        commit_pulses = 0;
        reject_pulses = 0;

        @(negedge clk);
        while (!hw_trigger_ready_o) @(negedge clk);
        ext_hw_trigger_cid_i   = cid;
        ext_hw_trigger_param_i = param;
        ext_hw_trigger_valid_i = 1'b1;
        @(posedge clk); // Trigger sampled here
        @(negedge clk);
        ext_hw_trigger_valid_i = 1'b0;

        while (busy) begin
            @(posedge clk);
            busy_cycles = busy_cycles + 1;
            if (hw_commit_pulse_o) commit_pulses = commit_pulses + 1;
            if (hw_reject_pulse_o) reject_pulses = reject_pulses + 1;
            #1;
            if (busy_cycles > 256)
                $fatal(1, "Watchdog timeout waiting for !busy");
        end
    endtask

    reg [4095:0] image_hex_path;
    reg [4095:0] events_hex_path;
    logic [31:0] event_words [0:511];

    initial begin
        int cyc, n_comm, n_rej;
        logic [31:0] rd_val, ev_cnt, cm_cnt, rj_cnt, last_st;
        int num_events;

        rst_n = 1'b0;
        repeat (4) @(posedge clk);
        @(negedge clk);
        rst_n = 1'b1;
        repeat (2) @(posedge clk);

        axi_read(13'h000, rd_val);
        if (rd_val !== 32'h4b524743)
            $fatal(1, "Unexpected ID 0x%08h", rd_val);

        if ($value$plusargs("image_hex=%s", image_hex_path) &&
            $value$plusargs("events_hex=%s", events_hex_path)) begin
            if (!$value$plusargs("num_events=%d", num_events))
                num_events = 0;

            load_image_direct(image_hex_path);
            $readmemh(events_hex_path, event_words);

            for (int e = 0; e < num_events; e++) begin
                logic [31:0] cmd_w, arg_w;
                cmd_w = event_words[e * 2];
                arg_w = event_words[e * 2 + 1];
                if (cmd_w[31:24] == 8'h01) begin
                    // Direct MMIO rule/state word update: cmd_w[7:0] = word_idx, arg_w = word_val
                    axi_write(13'h100 + ({5'd0, cmd_w[7:0]} << 2), arg_w, 4'hf, 2'b00);
                end else begin
                    trigger_and_count_cycles(cmd_w[5:0], arg_w, cyc, n_comm, n_rej);
                    $display("STEP %0d cycles=%0d commits=%0d rejects=%0d", e, cyc, n_comm, n_rej);
                end
            end

            for (int c = 0; c < 64; c++) begin
                logic [31:0] w0, w1, w2, w3;
                axi_write(13'h004, c * 4 + 0, 4'hf, 2'b00); axi_read(13'h008, w0);
                axi_write(13'h004, c * 4 + 1, 4'hf, 2'b00); axi_read(13'h008, w1);
                axi_write(13'h004, c * 4 + 2, 4'hf, 2'b00); axi_read(13'h008, w2);
                axi_write(13'h004, c * 4 + 3, 4'hf, 2'b00); axi_read(13'h008, w3);
                $display("SLOT %0d %08x %08x %08x %08x", c, w0, w1, w2, w3);
            end
            axi_read(13'h018, ev_cnt);
            axi_read(13'h01c, cm_cnt);
            axi_read(13'h020, rj_cnt);
            axi_read(13'h024, last_st);
            $display("SUMMARY events=%0d commits=%0d rejects=%0d last_state=%08x",
                     ev_cnt, cm_cnt, rj_cnt, last_st);
            $finish;
        end

        // Standalone self-check: configure canonical 4-concept cascade C0->C1->C2->C3
        // C0: init=10, RANGE [10, 1000], INC, sub=1 (flags=0x13)
        axi_write(13'h100, 32'd10, 4'hf, 2'b00);
        axi_write(13'h104, (32'd1000 << 16) | 32'd10, 4'hf, 2'b00);
        axi_write(13'h108, 32'h0100_1305, 4'hf, 2'b00);
        axi_write(13'h10c, 32'd1, 4'hf, 2'b00);

        // C1: init=0, GT 10, INC, sub=2 (flags=0x13)
        axi_write(13'h110, 32'd0, 4'hf, 2'b00);
        axi_write(13'h114, 32'd10, 4'hf, 2'b00);
        axi_write(13'h118, 32'h0100_1303, 4'hf, 2'b00);
        axi_write(13'h11c, 32'd2, 4'hf, 2'b00);

        // C2: init=2, LT 1 inverted (>= 1), DEC, sub=3 (flags=0x1b)
        axi_write(13'h120, 32'd2, 4'hf, 2'b00);
        axi_write(13'h124, 32'd1, 4'hf, 2'b00);
        axi_write(13'h128, 32'h0200_1b04, 4'hf, 2'b00);
        axi_write(13'h12c, 32'd3, 4'hf, 2'b00);

        // C3: init=0, EQ 2 inverted (!= 2), ASSIGN, leaf (flags=0x0b)
        axi_write(13'h130, 32'd0, 4'hf, 2'b00);
        axi_write(13'h134, 32'd2, 4'hf, 2'b00);
        axi_write(13'h138, 32'h0000_0b01, 4'hf, 2'b00);
        axi_write(13'h13c, 32'd0, 4'hf, 2'b00);

        // 1) Invalid stimulus p0=5 (< 10): must reject in exactly 1 clock cycle (10 ns)
        trigger_and_count_cycles(6'd0, 32'd5, cyc, n_comm, n_rej);
        if (cyc !== 1 || n_comm !== 0 || n_rej !== 1)
            $fatal(1, "Expected 1-cycle reject, got cyc=%0d comm=%0d rej=%0d", cyc, n_comm, n_rej);

        // 2) Valid stimulus p0=25: full 4-concept cascade in exactly 4 clock cycles (40 ns)
        trigger_and_count_cycles(6'd0, 32'd25, cyc, n_comm, n_rej);
        if (cyc !== 4 || n_comm !== 4 || n_rej !== 0)
            $fatal(1, "Expected 4-cycle cascade, got cyc=%0d comm=%0d rej=%0d", cyc, n_comm, n_rej);

        // Verify busy SLVERR protection during execution
        @(negedge clk);
        ext_hw_trigger_cid_i   = 6'd0;
        ext_hw_trigger_param_i = 32'd25;
        ext_hw_trigger_valid_i = 1'b1;
        @(posedge clk);
        @(negedge clk);
        ext_hw_trigger_valid_i = 1'b0;
        // Attempt AXI write while 4-cycle cascade is in flight -> must return SLVERR
        axi_write(13'h104, 32'hdeadbeef, 4'hf, 2'b10);
        while (busy) @(posedge clk);

        // 3) Third valid p0=25: C2 is now 0, DEC attempts -1 -> invariant S_2 >= 0 rejects at C2 (3 cycles)
        trigger_and_count_cycles(6'd0, 32'd25, cyc, n_comm, n_rej);
        if (cyc !== 3 || n_comm !== 2 || n_rej !== 1)
            $fatal(1, "Expected 3-cycle mid-cascade invariant reject, got cyc=%0d comm=%0d rej=%0d",
                   cyc, n_comm, n_rej);

        $display("PASS: km_reg_configurable_cascade_axi_tb standalone checks complete");
        $finish;
    end
endmodule
