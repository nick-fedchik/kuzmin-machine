`timescale 1ns / 1ps

// ============================================================================
// Тестбенч: kpol_bram_pipeline_pynq_z1_ha_top_tb.sv
// Призначення: Топ-рівнева потактова RTL-верифікація модуля синтезу
// kpol_bram_pipeline_pynq_z1_ha_top.v (Issue #253, EXP-GPU-02 Stage 3)
// на пінах роз'ємів PMOD JA (ja1..ja4) та PMOD JB (jb1..jb4, jb7, jb8)
// з behavioral mock-моделями примітивів Zynq-7000 PS7 і BUFG.
//
// HONESTY LABEL (AGENTS.md §4.2):
//   evidence_kind = "rtl_top_simulation_iverilog" (NOT physical PYNQ-Z1 + RP2040 PIO capture).
//
// Перевіряє:
//   1) Канали PMOD JB для підключення логічного аналізатора RP2040 PIO (GP0..GP4) + jb8:
//      - jb1 (W14, Pin 1) = inject_strobe_o      (GP0: INJECT_STROBE, рівно 1 такт = 10 нс)
//      - jb2 (Y14, Pin 2) = bank_swap_commit_o   (GP1: BANK_SWAP_COMMIT, рівно 1 такт = 10 нс)
//      - jb3 (T11, Pin 3) = stimulus_accepted_o  (GP2: STIMULUS_EVENT, рівно 1 такт = 10 нс)
//      - jb4 (T10, Pin 4) = reaction_out_o       (GP3: REACTION_OUT, рівно 1 такт = 10 нс)
//      - jb7 (V16, Pin 7) = seq_cycle_done_o     (GP4: SEQ_CYCLE_DONE, рівно 1 такт = 10 нс)
//      - jb8 (W16, Pin 8) = active_bank_o        (рівень активного банку 0 -> 1 -> 0)
//   2) Усі 4 фази протоколу EXP-GPU-02 через фізичний вхід PMOD JA1 (через 2-FF CDC)
//      та AXI4-Lite транзакції PS7 GP0 (0x4000_0030, 0x4000_0034, 0x4000_0038).
//   3) Розтягнуті імпульси 100 нс (10 тактів) на ja2 (commit) і ja3 (reject),
//      індикатор зайнятості ja4 (8 тактів на подію) та нульовий рівень помилок led[3].
// ============================================================================

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
    always #5 fclk0 = ~fclk0; // 100 MHz (10 ns period)
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

module kpol_bram_pipeline_pynq_z1_ha_top_tb;
    reg        ja1 = 1'b0;
    wire       ja2, ja3, ja4;
    wire       jb1, jb2, jb3, jb4, jb7, jb8;
    reg  [3:0] btn = 4'b0000;
    reg  [1:0] sw  = 2'b00;
    wire [3:0] led;

    // Speed up button debounce for top-level simulation if needed
    kpol_bram_pipeline_pynq_z1_ha_top #(
        .BTN_DEBOUNCE_CYCLES(32'd4)
    ) dut (
        .ja1 (ja1),
        .ja2 (ja2),
        .ja3 (ja3),
        .ja4 (ja4),
        .jb1 (jb1),
        .jb2 (jb2),
        .jb3 (jb3),
        .jb4 (jb4),
        .jb7 (jb7),
        .jb8 (jb8),
        .btn (btn),
        .sw  (sw),
        .led (led)
    );

    initial begin
        #300000;
        $fatal(1, "[FAIL] WATCHDOG TIMEOUT in kpol_bram_pipeline_pynq_z1_ha_top_tb");
    end

    // W2 rule words:
    //   W2_GE_INC: pred=LT(0x04), guard=0x0B (assumption + inv + invert -> param >= W1), action=INC(0x01)
    localparam [31:0] W2_GE_INC = 32'h0100_0b04;

    // Cycle-accurate monitors on PMOD JB (RP2040 PIO GP0..GP4 + jb8) and PMOD JA (ja2..ja4)
    integer cycle_cnt = 0;
    integer jb1_pulses = 0, jb2_pulses = 0, jb3_pulses = 0, jb4_pulses = 0, jb7_pulses = 0;
    integer jb1_high_run = 0, jb2_high_run = 0, jb3_high_run = 0, jb4_high_run = 0, jb7_high_run = 0;
    integer last_jb1_cyc = -1, last_jb2_cyc = -1, last_jb3_cyc = -1, last_jb4_cyc = -1, last_jb7_cyc = -1;
    integer ja2_high_cycles = 0, ja3_high_cycles = 0;
    reg     jb8_prev = 1'b0;
    integer jb8_toggles = 0;

    always @(posedge dut.clk) begin
        if (!dut.rst_n) begin
            cycle_cnt       <= 0;
            jb1_pulses      <= 0;
            jb2_pulses      <= 0;
            jb3_pulses      <= 0;
            jb4_pulses      <= 0;
            jb7_pulses      <= 0;
            jb1_high_run    <= 0;
            jb2_high_run    <= 0;
            jb3_high_run    <= 0;
            jb4_high_run    <= 0;
            jb7_high_run    <= 0;
            ja2_high_cycles <= 0;
            ja3_high_cycles <= 0;
            jb8_prev        <= 1'b0;
            jb8_toggles     <= 0;
        end else begin
            cycle_cnt <= cycle_cnt + 1;

            // Verify every JB1..JB4, JB7 strobe is strictly 1 clock cycle (10 ns) wide
            if (jb1) begin
                jb1_pulses   <= jb1_pulses + 1;
                jb1_high_run <= jb1_high_run + 1;
                last_jb1_cyc <= cycle_cnt;
                if (jb1_high_run >= 1)
                    $fatal(1, "[FAIL] jb1 (INJECT_STROBE) high for >1 cycle at cyc=%0d", cycle_cnt);
            end else begin
                jb1_high_run <= 0;
            end

            if (jb2) begin
                jb2_pulses   <= jb2_pulses + 1;
                jb2_high_run <= jb2_high_run + 1;
                last_jb2_cyc <= cycle_cnt;
                if (jb2_high_run >= 1)
                    $fatal(1, "[FAIL] jb2 (BANK_SWAP_COMMIT) high for >1 cycle at cyc=%0d", cycle_cnt);
            end else begin
                jb2_high_run <= 0;
            end

            if (jb3) begin
                jb3_pulses   <= jb3_pulses + 1;
                jb3_high_run <= jb3_high_run + 1;
                last_jb3_cyc <= cycle_cnt;
                if (jb3_high_run >= 1)
                    $fatal(1, "[FAIL] jb3 (STIMULUS_EVENT) high for >1 cycle at cyc=%0d", cycle_cnt);
            end else begin
                jb3_high_run <= 0;
            end

            if (jb4) begin
                jb4_pulses   <= jb4_pulses + 1;
                jb4_high_run <= jb4_high_run + 1;
                last_jb4_cyc <= cycle_cnt;
                if (jb4_high_run >= 1)
                    $fatal(1, "[FAIL] jb4 (REACTION_OUT) high for >1 cycle at cyc=%0d", cycle_cnt);
                if (!jb7)
                    $fatal(1, "[FAIL] jb4 (REACTION_OUT) asserted without jb7 (SEQ_CYCLE_DONE) at cyc=%0d", cycle_cnt);
            end else begin
                jb4_high_run <= 0;
            end

            if (jb7) begin
                jb7_pulses   <= jb7_pulses + 1;
                jb7_high_run <= jb7_high_run + 1;
                last_jb7_cyc <= cycle_cnt;
                if (jb7_high_run >= 1)
                    $fatal(1, "[FAIL] jb7 (SEQ_CYCLE_DONE) high for >1 cycle at cyc=%0d", cycle_cnt);
            end else begin
                jb7_high_run <= 0;
            end

            // Verify jb8 (active_bank_o) toggles if and only if jb2 (BANK_SWAP_COMMIT) fired on the previous edge
            if (jb8 !== jb8_prev) begin
                jb8_toggles <= jb8_toggles + 1;
                if (last_jb2_cyc != (cycle_cnt - 1)) begin
                    $fatal(1, "[FAIL] jb8 (active_bank_o) toggled at cyc=%0d without preceding jb2 pulse (last_jb2=%0d)",
                           cycle_cnt, last_jb2_cyc);
                end
            end
            jb8_prev <= jb8;

            if (ja2) ja2_high_cycles <= ja2_high_cycles + 1;
            if (ja3) ja3_high_cycles <= ja3_high_cycles + 1;
        end
    end

    task automatic write_bram_sync(input [7:0] word_addr, input [31:0] val);
        dut.ps7.axi_write(32'h4000_0004, {24'd0, word_addr});
        dut.ps7.axi_write(32'h4000_0008, val);
    endtask

    task automatic read_bram_active(input [7:0] word_addr, output [31:0] val);
        dut.ps7.axi_write(32'h4000_0004, {24'd0, word_addr});
        dut.ps7.axi_read(32'h4000_0008, val);
    endtask

    task automatic wait_pipe_idle;
        reg [31:0] st;
        st = 32'd1;
        while (st[0]) dut.ps7.axi_read(32'h4000_0014, st);
    endtask

    task automatic wait_resync_idle;
        reg [31:0] st;
        st = 32'h6;
        while (st[2:1] != 2'b00) dut.ps7.axi_read(32'h4000_0038, st);
    endtask

    task automatic pulse_ja1_and_wait_done(output logic did_commit, output integer latency_cycles);
        integer jb3_before, jb4_before, jb7_before;
        begin
            jb3_before = jb3_pulses;
            jb4_before = jb4_pulses;
            jb7_before = jb7_pulses;

            @(negedge dut.clk);
            ja1 = 1'b1;
            repeat (3) @(negedge dut.clk);
            ja1 = 1'b0;

            wait (jb7_pulses == jb7_before + 1);
            @(posedge dut.clk);
            if (jb3_pulses !== jb3_before + 1)
                $fatal(1, "[FAIL] Expected exactly 1 jb3 (STIMULUS_EVENT) pulse for ja1 trigger");
            did_commit     = (jb4_pulses == jb4_before + 1);
            latency_cycles = last_jb7_cyc - last_jb3_cyc;
            if (latency_cycles !== 8)
                $fatal(1, "[FAIL] Expected STIMULUS_EVENT(jb3)->SEQ_CYCLE_DONE(jb7) = 8 cycles, got %0d", latency_cycles);
        end
    endtask

    initial begin
        reg [31:0] val;
        logic      did_commit;
        integer    lat_cyc;
        integer    jb1_before, jb2_before;

        repeat (4) @(negedge dut.clk);
        dut.ps7.MAXIGP0ARESETN = 1'b1;
        repeat (4) @(posedge dut.clk);

        // Verify ID register 0x000 == "KPHA" (0x4B504841) and initial jb8 == 0
        dut.ps7.axi_read(32'h4000_0000, val);
        if (val !== 32'h4b50_4841)
            $fatal(1, "[FAIL] Unexpected ID register 0x000: got=%h exp=4b504841", val);
        if (jb8 !== 1'b0)
            $fatal(1, "[FAIL] Initial jb8 (active_bank_o) must be 0, got %b", jb8);

        // Clear all 256 words in both banks
        for (int i = 0; i < 256; i++) begin
            write_bram_sync(i[7:0], 32'd0);
        end

        // ====================================================================
        // Phase 1 (Bank 0 calibration on CID=1 via sw=2'b01 and ja1 trigger):
        // Hardware trigger param on ja1 is fixed at +1.
        // Set initial rule on CID=1 (words 4..7): W0=10, W1=5 (threshold: param >= 5) -> param=1 REJECTS!
        // Also configure CID=2 (words 8..11): W0=50, W1=1 (threshold: param >= 1) -> param=1 COMMITS!
        // ====================================================================
        write_bram_sync(8'd4,  32'd10);      // CID=1 W0 = 10
        write_bram_sync(8'd5,  32'd5);       // CID=1 W1 = 5 (requires param >= 5)
        write_bram_sync(8'd6,  W2_GE_INC);   // CID=1 W2 = GE + INC
        write_bram_sync(8'd7,  32'hffff_ffff);

        write_bram_sync(8'd8,  32'd50);      // CID=2 W0 = 50
        write_bram_sync(8'd9,  32'd1);       // CID=2 W1 = 1 (param=1 >= 1 commits)
        write_bram_sync(8'd10, W2_GE_INC);   // CID=2 W2 = GE + INC
        write_bram_sync(8'd11, 32'hffff_ffff);

        // Select CID=1 via slide switches sw=2'b01 (wait 4 cycles for 2-FF CDC)
        sw = 2'b01;
        repeat (4) @(posedge dut.clk);

        // Phase 1a: Trigger ja1 on CID=1 (param=1 < 5 -> REJECT in 8 cycles: jb3=1, jb4=0, jb7=1, ja3 stretched 10 cycles)
        pulse_ja1_and_wait_done(did_commit, lat_cyc);
        if (did_commit !== 1'b0)
            $fatal(1, "[FAIL] Phase 1a: Expected REJECT (jb4=0) on CID=1 with threshold=5, got commit");
        wait_pipe_idle();
        repeat (12) @(posedge dut.clk);
        if (ja3_high_cycles !== 10)
            $fatal(1, "[FAIL] Phase 1a: Expected ja3 stretched for 10 cycles (100 ns), got %0d", ja3_high_cycles);

        // Phase 1b: Switch to CID=2 (sw=2'b10) and trigger ja1 (param=1 >= 1 -> COMMIT in 8 cycles: jb3=1, jb4=1, jb7=1)
        sw = 2'b10;
        repeat (4) @(posedge dut.clk);
        pulse_ja1_and_wait_done(did_commit, lat_cyc);
        if (did_commit !== 1'b1)
            $fatal(1, "[FAIL] Phase 1b: Expected COMMIT (jb4=1) on CID=2 with threshold=1, got reject");
        wait_pipe_idle();
        read_bram_active(8'd8, val);
        if (val !== 32'd51)
            $fatal(1, "[FAIL] Phase 1b: Expected CID=2 W0=51, got %0d", val);
        repeat (12) @(posedge dut.clk);
        if (ja2_high_cycles !== 10)
            $fatal(1, "[FAIL] Phase 1b: Expected ja2 stretched for 10 cycles (100 ns), got %0d", ja2_high_cycles);

        // ====================================================================
        // Phase 2 & 3: Online shadow injection (0x030, 0x034) + atomic bank swap (0x038)
        // while ja1 stimulus is active on CID=1!
        // Update CID=1 rule in shadow Bank 1 from W1=5 (rejects param=1) to W1=1 (commits param=1),
        // AND pre-increment CID=1 W0 via software event param=10 (>=5) on Bank 0 before swap to prove
        // live W0 state (10 -> 11) is preserved across the bank swap!
        // ====================================================================
        sw = 2'b01; // Target CID=1 on ja1
        repeat (4) @(posedge dut.clk);

        // Increment CID=0 or CID=1? Wait: let's also update CID=1 in shadow bank (words 5..7: W1=1, W2=W2_GE_INC, W3=0xFFFFFFFF)
        jb1_before = jb1_pulses;
        jb2_before = jb2_pulses;

        dut.ps7.axi_write(32'h4000_0030, 32'd5); // SHADOW_ADDR = word 5 (CID=1, W1)
        dut.ps7.axi_write(32'h4000_0034, 32'd1); // SHADOW_DATA W1 = 1 (fires 1-cycle jb1 INJECT_STROBE!)
        dut.ps7.axi_write(32'h4000_0034, W2_GE_INC);
        dut.ps7.axi_write(32'h4000_0034, 32'hffff_ffff);

        if (jb1_pulses !== jb1_before + 1)
            $fatal(1, "[FAIL] Phase 2: Expected exactly 1 jb1 (INJECT_STROBE) pulse during shadow injection, got %0d",
                   jb1_pulses - jb1_before);
        if (jb8 !== 1'b0)
            $fatal(1, "[FAIL] Phase 2: jb8 changed before BANK_SWAP_COMMIT");

        // Fire a physical ja1 stimulus on CID=1 BEFORE swap (still Bank 0 -> must still REJECT in 8 cycles!)
        pulse_ja1_and_wait_done(did_commit, lat_cyc);
        if (did_commit !== 1'b0)
            $fatal(1, "[FAIL] Phase 2 pre-swap: CID=1 must still reject before BANK_SWAP_COMMIT");

        // Launch another ja1 stimulus and issue BANK_SWAP_CTRL (0x038 = 1) mid-flight so swap commits at ST_IDLE boundary
        @(negedge dut.clk);
        ja1 = 1'b1;
        repeat (2) @(negedge dut.clk);
        ja1 = 1'b0;

        dut.ps7.axi_write(32'h4000_0038, 32'd1); // Request atomic bank swap
        wait (jb2_pulses == jb2_before + 1);
        @(posedge dut.clk);
        if (jb8 !== 1'b1)
            $fatal(1, "[FAIL] Phase 3: Expected jb8 (active_bank_o) == 1 after jb2 (BANK_SWAP_COMMIT), got %b", jb8);

        wait_pipe_idle();
        wait_resync_idle();

        // ====================================================================
        // Phase 4: First physical ja1 stimulus after BANK_SWAP_COMMIT on CID=1
        // Now active bank is Bank 1 (jb8 == 1) with threshold W1=1 -> param=1 COMMITS in 8 cycles!
        // ====================================================================
        pulse_ja1_and_wait_done(did_commit, lat_cyc);
        if (did_commit !== 1'b1)
            $fatal(1, "[FAIL] Phase 4: First ja1 stimulus after swap on CID=1 failed to COMMIT (jb4=0)");

        wait_pipe_idle();
        read_bram_active(8'd4, val);
        if (val !== 32'd11)
            $fatal(1, "[FAIL] Phase 4: Expected CID=1 W0=11 after commit on new bank, got %0d", val);

        // Second swap (Bank 1 -> Bank 0) to verify jb8 toggles 1 -> 0 cleanly
        jb1_before = jb1_pulses;
        jb2_before = jb2_pulses;
        dut.ps7.axi_write(32'h4000_0030, 32'd5);
        dut.ps7.axi_write(32'h4000_0034, 32'd1);
        dut.ps7.axi_write(32'h4000_0038, 32'd1);
        wait (jb2_pulses == jb2_before + 1);
        @(posedge dut.clk);
        if (jb1_pulses !== jb1_before + 1 || jb8 !== 1'b0)
            $fatal(1, "[FAIL] Second swap failed: jb1_delta=%0d jb8=%b", jb1_pulses - jb1_before, jb8);

        wait_resync_idle();

        // Check telemetry registers 0x03C (SWAP_COUNT == 2) and 0x044 (SEQ_EXEC_MONITOR == 0x0000_0008)
        dut.ps7.axi_read(32'h4000_003c, val);
        if (val !== 32'd2)
            $fatal(1, "[FAIL] Expected SWAP_COUNT (0x03C) == 2, got %0d", val);
        dut.ps7.axi_read(32'h4000_0044, val);
        if (val !== 32'h0000_0008)
            $fatal(1, "[FAIL] Expected SEQ_EXEC_MONITOR (0x044) == 0x00000008 (0 anomalies, 8 cycles), got %h", val);
        if (led[3] !== 1'b0)
            $fatal(1, "[FAIL] Unexpected FIFO overflow LED led[3]=%b", led[3]);

        $display("PASS: kpol_bram_pipeline_pynq_z1_ha_top_tb verified JA1..JA4 and JB1..JB4,JB7,JB8 across Phases 1-4 (swaps=%0d, jb8_toggles=%0d)",
                 jb2_pulses, jb8_toggles);
        $finish;
    end
endmodule
