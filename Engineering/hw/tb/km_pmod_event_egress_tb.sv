// ============================================================================
// File: km_pmod_event_egress_tb.sv
// Description: Self-checking testbench for km_pmod_event_egress (Issue #230)
// ============================================================================

`timescale 1ns / 1ps

module km_pmod_event_egress_tb;

    reg         clk;
    reg         rst_n;
    reg         mode_par8_i;
    reg         event_valid_i;
    reg  [5:0]  event_cid_i;
    reg  [31:0] event_mask_i;
    reg  [31:0] event_state_i;

    wire        event_start_o;
    wire        spi_cs_n_o;
    wire        spi_sck_o;
    wire        spi_mosi_o;
    wire        par_valid_o;
    wire        par_clk_o;
    wire [7:0]  par_data_o;
    wire        busy_o;
    wire        ready_o;
    wire [31:0] tx_count_o;
    wire [31:0] drop_count_o;

    km_pmod_event_egress dut (
        .clk           (clk),
        .rst_n         (rst_n),
        .mode_par8_i   (mode_par8_i),
        .event_valid_i (event_valid_i),
        .event_cid_i   (event_cid_i),
        .event_mask_i  (event_mask_i),
        .event_state_i (event_state_i),
        .event_start_o (event_start_o),
        .spi_cs_n_o    (spi_cs_n_o),
        .spi_sck_o     (spi_sck_o),
        .spi_mosi_o    (spi_mosi_o),
        .par_valid_o   (par_valid_o),
        .par_clk_o     (par_clk_o),
        .par_data_o    (par_data_o),
        .busy_o        (busy_o),
        .ready_o       (ready_o),
        .tx_count_o    (tx_count_o),
        .drop_count_o  (drop_count_o)
    );

    // 100 MHz clock (10 ns period)
    always #5 clk = ~clk;

    // Global watchdog to prevent simulation hangs
    initial begin
        #200000;
        $fatal(1, "[TB] WATCHDOG TIMEOUT");
    end

    // Independent reference CRC-8 (poly 0x07, init 0x00, MSB-first)
    function automatic [7:0] ref_crc8;
        input [55:0] payload;
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

    // ------------------------------------------------------------------------
    // SPI Mode 0 Receiver/Decoder (CPOL=0, CPHA=0, MSB-first)
    // ------------------------------------------------------------------------
    reg [63:0] spi_rx_frame;
    integer    spi_rx_bits;
    reg        spi_rx_done;

    always @(posedge spi_sck_o or posedge spi_cs_n_o) begin
        if (spi_cs_n_o) begin
            // Wait for next transaction; do not clear spi_rx_frame so TB can inspect it
        end else begin
            spi_rx_frame <= {spi_rx_frame[62:0], spi_mosi_o};
            spi_rx_bits  <= spi_rx_bits + 1;
        end
    end

    always @(posedge spi_cs_n_o) begin
        if (rst_n && spi_rx_bits > 0) begin
            spi_rx_done <= 1'b1;
        end
    end

    // ------------------------------------------------------------------------
    // 8-bit Source-Synchronous Parallel Receiver/Decoder (MSB byte first)
    // ------------------------------------------------------------------------
    reg [63:0] par_rx_frame;
    reg [63:0] par_rx_captured;
    integer    par_rx_bytes;
    reg        par_rx_done;

    always @(posedge par_clk_o) begin
        if (rst_n && par_valid_o) begin
            par_rx_frame <= {par_rx_frame[55:0], par_data_o};
            par_rx_bytes <= par_rx_bytes + 1;
        end
    end

    always @(negedge par_valid_o) begin
        if (rst_n && par_rx_bytes > 0) begin
            par_rx_captured <= par_rx_frame;
            par_rx_done     <= 1'b1;
        end
    end

    // Cycle counter for transfer duration, framing, idle, and setup/hold checks
    integer active_cycles;
    integer start_pulses;
    reg     prev_spi_sck;
    reg     prev_par_clk;
    time    last_mosi_change_t;
    time    last_par_data_change_t;

    always @(posedge clk) begin
        if (!rst_n) begin
            active_cycles <= 0;
            start_pulses  <= 0;
            prev_spi_sck  <= 1'b0;
            prev_par_clk  <= 1'b0;
        end else begin
            prev_spi_sck <= spi_sck_o;
            prev_par_clk <= par_clk_o;

            if (busy_o)
                active_cycles <= active_cycles + 1;
            if (event_start_o)
                start_pulses <= start_pulses + 1;

            // Framing check: CS must stay low during S_SPI_END (1 cycle after 64th falling edge)
            if (prev_spi_sck && !spi_sck_o && (spi_rx_bits == 64)) begin
                if (spi_cs_n_o !== 1'b0) begin
                    $display("[TB] FAIL: spi_cs_n_o rose prematurely in S_SPI_END");
                    $fatal(1);
                end
            end

            // Framing check: par_valid_o must stay high during S_PAR_END (1 cycle after 8th falling edge)
            if (prev_par_clk && !par_clk_o && (par_rx_bytes == 8)) begin
                if (par_valid_o !== 1'b1) begin
                    $display("[TB] FAIL: par_valid_o dropped prematurely in S_PAR_END");
                    $fatal(1);
                end
            end
        end
    end

    // Setup/hold checks for SPI MOSI and PAR8 Data
    always @(spi_mosi_o) begin
        if (rst_n && spi_sck_o === 1'b1) begin
            $display("[TB] FAIL: spi_mosi_o changed while spi_sck_o==1 (hold violation)");
            $fatal(1);
        end
        last_mosi_change_t = $time;
    end

    always @(posedge spi_sck_o) begin
        if (rst_n) begin
            if (spi_cs_n_o !== 1'b0) begin
                $display("[TB] FAIL: spi_cs_n_o not low at posedge spi_sck_o");
                $fatal(1);
            end
            if (($time - last_mosi_change_t) < 10) begin
                $display("[TB] FAIL: spi_mosi_o setup violation (<10ns) at t=%0t", $time);
                $fatal(1);
            end
        end
    end

    always @(par_data_o) begin
        if (rst_n && par_clk_o === 1'b1) begin
            $display("[TB] FAIL: par_data_o changed while par_clk_o==1 (hold violation)");
            $fatal(1);
        end
        last_par_data_change_t = $time;
    end

    always @(posedge par_clk_o) begin
        if (rst_n) begin
            if (par_valid_o !== 1'b1) begin
                $display("[TB] FAIL: par_valid_o not high at posedge par_clk_o");
                $fatal(1);
            end
            if (($time - last_par_data_change_t) < 10) begin
                $display("[TB] FAIL: par_data_o setup violation (<10ns) at t=%0t", $time);
                $fatal(1);
            end
        end
    end

    task automatic check_idle_outputs(input [8*16-1:0] label);
        begin
            if (spi_cs_n_o !== 1'b1 || spi_sck_o !== 1'b0 ||
                par_valid_o !== 1'b0 || par_clk_o !== 1'b0) begin
                $display("[TB] FAIL (%0s): non-idle outputs cs_n=%b sck=%b par_v=%b par_c=%b",
                         label, spi_cs_n_o, spi_sck_o, par_valid_o, par_clk_o);
                $fatal(1);
            end
        end
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

            if (rx_frame[55:54] !== 2'b01) begin
                $display("[TB] FAIL (%0s): tag mismatch got=%b exp=01", label, rx_frame[55:54]);
                $fatal(1);
            end
            if (rx_frame[53:48] !== exp_cid) begin
                $display("[TB] FAIL (%0s): cid mismatch got=%0d exp=%0d", label, rx_frame[53:48], exp_cid);
                $fatal(1);
            end
            if (rx_frame[47:32] !== exp_mask16) begin
                $display("[TB] FAIL (%0s): mask16 mismatch got=%h exp=%h", label, rx_frame[47:32], exp_mask16);
                $fatal(1);
            end
            if (rx_frame[31:0] !== exp_state) begin
                $display("[TB] FAIL (%0s): state mismatch got=%h exp=%h", label, rx_frame[31:0], exp_state);
                $fatal(1);
            end
            if (rx_frame[63:56] !== exp_crc) begin
                $display("[TB] FAIL (%0s): crc8 mismatch got=%h exp=%h", label, rx_frame[63:56], exp_crc);
                $fatal(1);
            end
        end
    endtask

    task automatic send_event(
        input        p_mode,
        input [5:0]  cid,
        input [31:0] mask,
        input [31:0] state
    );
        begin
            @(negedge clk);
            mode_par8_i   = p_mode;
            event_cid_i   = cid;
            event_mask_i  = mask;
            event_state_i = state;
            event_valid_i = 1'b1;
            @(negedge clk);
            event_valid_i = 1'b0;
        end
    endtask

    initial begin
        clk           = 1'b0;
        rst_n         = 1'b0;
        mode_par8_i   = 1'b0;
        event_valid_i = 1'b0;
        event_cid_i   = 6'd0;
        event_mask_i  = 32'd0;
        event_state_i = 32'd0;
        spi_rx_frame  = 64'd0;
        spi_rx_bits   = 0;
        spi_rx_done   = 1'b0;
        par_rx_frame  = 64'd0;
        par_rx_bytes  = 0;
        par_rx_done   = 1'b0;
        last_mosi_change_t     = 0;
        last_par_data_change_t = 0;

        #25 rst_n = 1'b1;
        @(posedge clk);

        if (ready_o !== 1'b1 || busy_o !== 1'b0) begin
            $display("[TB] FAIL: invalid reset idle state");
            $fatal(1);
        end
        check_idle_outputs("RESET-IDLE");

        // --------------------------------------------------------------------
        // Test 1: SPI Mode 0 single frame (cid=5, mask=0x0000A55A, state=0x12345678)
        // --------------------------------------------------------------------
        spi_rx_bits   = 0;
        spi_rx_done   = 1'b0;
        active_cycles = 0;
        start_pulses  = 0;

        send_event(1'b0, 6'd5, 32'h0000_A55A, 32'h1234_5678);

        wait(spi_rx_done == 1'b1);
        @(posedge clk);

        if (spi_rx_bits !== 64) begin
            $display("[TB] FAIL (SPI-1): expected 64 SCK edges, got %0d", spi_rx_bits);
            $fatal(1);
        end
        if (start_pulses !== 1) begin
            $display("[TB] FAIL (SPI-1): expected 1 event_start_o pulse, got %0d", start_pulses);
            $fatal(1);
        end
        if (active_cycles !== 129) begin
            $display("[TB] FAIL (SPI-1): expected 129 busy cycles, got %0d", active_cycles);
            $fatal(1);
        end
        verify_frame(spi_rx_frame, 6'd5, 16'hA55A, 32'h1234_5678, "SPI-1");
        if (tx_count_o !== 32'd1 || drop_count_o !== 32'd0) begin
            $display("[TB] FAIL (SPI-1): counters tx=%0d drop=%0d", tx_count_o, drop_count_o);
            $fatal(1);
        end
        $display("[TB] PASS Test 1 (SPI Mode 0): bits=%0d cycles=%0d frame=%h", spi_rx_bits, active_cycles, spi_rx_frame);

        // --------------------------------------------------------------------
        // Test 2: SPI Collision during busy_o (2 dropped events must not corrupt active frame)
        // --------------------------------------------------------------------
        spi_rx_bits   = 0;
        spi_rx_done   = 1'b0;
        active_cycles = 0;
        start_pulses  = 0;

        send_event(1'b0, 6'd12, 32'hFFFF_00FF, 32'hCAFE_BABE);

        repeat (15) @(posedge clk);
        if (busy_o !== 1'b1) begin
            $display("[TB] FAIL (SPI-COL): expected busy_o == 1 during transfer");
            $fatal(1);
        end
        send_event(1'b0, 6'd63, 32'hDEAD_BEEF, 32'h1111_2222);
        repeat (5) @(posedge clk);
        send_event(1'b0, 6'd31, 32'h5555_6666, 32'h3333_4444);

        wait(spi_rx_done == 1'b1);
        @(posedge clk);

        if (spi_rx_bits !== 64 || start_pulses !== 1) begin
            $display("[TB] FAIL (SPI-COL): bits=%0d start_pulses=%0d", spi_rx_bits, start_pulses);
            $fatal(1);
        end
        verify_frame(spi_rx_frame, 6'd12, 16'h00FF, 32'hCAFE_BABE, "SPI-COL");
        if (tx_count_o !== 32'd2 || drop_count_o !== 32'd2) begin
            $display("[TB] FAIL (SPI-COL): expected tx=2 drop=2, got tx=%0d drop=%0d", tx_count_o, drop_count_o);
            $fatal(1);
        end
        $display("[TB] PASS Test 2 (SPI Collision): tx=%0d drop=%0d", tx_count_o, drop_count_o);

        // --------------------------------------------------------------------
        // Test 3: 8-bit Source-Synchronous Parallel Mode (with collision)
        // --------------------------------------------------------------------
        par_rx_bytes  = 0;
        par_rx_done   = 1'b0;
        active_cycles = 0;
        start_pulses  = 0;

        send_event(1'b1, 6'd63, 32'h0000_FFFF, 32'h8000_0001);

        repeat (4) @(posedge clk);
        send_event(1'b1, 6'd1, 32'h0000_0001, 32'h0000_0002); // Collision during parallel mode

        wait(par_rx_done == 1'b1);
        @(posedge clk);

        if (par_rx_bytes !== 8) begin
            $display("[TB] FAIL (PAR8-1): expected 8 bytes, got %0d", par_rx_bytes);
            $fatal(1);
        end
        if (start_pulses !== 1 || active_cycles !== 17) begin
            $display("[TB] FAIL (PAR8-1): start_pulses=%0d active_cycles=%0d (exp 17)", start_pulses, active_cycles);
            $fatal(1);
        end
        verify_frame(par_rx_frame, 6'd63, 16'hFFFF, 32'h8000_0001, "PAR8-1");
        if (tx_count_o !== 32'd3 || drop_count_o !== 32'd3) begin
            $display("[TB] FAIL (PAR8-1): expected tx=3 drop=3, got tx=%0d drop=%0d", tx_count_o, drop_count_o);
            $fatal(1);
        end
        $display("[TB] PASS Test 3 (PAR8 Mode): bytes=%0d cycles=%0d frame=%h", par_rx_bytes, active_cycles, par_rx_frame);

        // --------------------------------------------------------------------
        // Test 4: 8-bit Parallel Zero-Payload Boundary Case
        // --------------------------------------------------------------------
        par_rx_bytes  = 0;
        par_rx_done   = 1'b0;
        active_cycles = 0;
        start_pulses  = 0;

        send_event(1'b1, 6'd0, 32'h0000_0000, 32'h0000_0000);

        wait(par_rx_done == 1'b1);
        @(posedge clk);

        if (par_rx_bytes !== 8 || active_cycles !== 17) begin
            $display("[TB] FAIL (PAR8-ZERO): bytes=%0d cycles=%0d", par_rx_bytes, active_cycles);
            $fatal(1);
        end
        verify_frame(par_rx_frame, 6'd0, 16'h0000, 32'h0000_0000, "PAR8-ZERO");
        if (tx_count_o !== 32'd4 || drop_count_o !== 32'd3) begin
            $display("[TB] FAIL (PAR8-ZERO): expected tx=4 drop=3, got tx=%0d drop=%0d", tx_count_o, drop_count_o);
            $fatal(1);
        end
        @(posedge clk);
        check_idle_outputs("AFTER-PAR8-ZERO");
        $display("[TB] PASS Test 4 (PAR8 Zero): frame=%h tx=%0d drop=%0d", par_rx_frame, tx_count_o, drop_count_o);

        // --------------------------------------------------------------------
        // Test 5: Boundary collision in S_SPI_END (dropped) & immediate accept in first S_IDLE
        // --------------------------------------------------------------------
        spi_rx_bits   = 0;
        spi_rx_done   = 1'b0;
        active_cycles = 0;
        start_pulses  = 0;
        send_event(1'b0, 6'd7, 32'h0000_1111, 32'hAAAA_BBBB);
        // send_event returns at negedge of cycle 1 (S_SPI_LOW); 128 posedges later is S_SPI_END
        repeat (128) @(posedge clk);
        if (busy_o !== 1'b1) begin
            $display("[TB] FAIL (SPI-END-COL): expected busy_o == 1 in S_SPI_END");
            $fatal(1);
        end
        // Assert event_valid_i during S_SPI_END -> must be dropped
        @(negedge clk);
        mode_par8_i   = 1'b0;
        event_cid_i   = 6'd9;
        event_mask_i  = 32'h0000_2222;
        event_state_i = 32'hCCCC_DDDD;
        event_valid_i = 1'b1;
        // Hold for next cycle (first S_IDLE cycle) -> must be accepted!
        @(negedge clk);
        event_cid_i   = 6'd10;
        event_mask_i  = 32'h0000_3333;
        event_state_i = 32'hEEEE_FFFF;
        @(negedge clk);
        event_valid_i = 1'b0;

        wait(spi_rx_done == 1'b1);
        @(posedge clk);
        verify_frame(spi_rx_frame, 6'd7, 16'h1111, 32'hAAAA_BBBB, "SPI-END-1");

        // Wait for the immediately accepted frame (cid=10)
        spi_rx_bits = 0;
        spi_rx_done = 1'b0;
        wait(spi_rx_done == 1'b1);
        @(posedge clk);
        verify_frame(spi_rx_frame, 6'd10, 16'h3333, 32'hEEEE_FFFF, "SPI-IMM-IDLE");
        if (tx_count_o !== 32'd6 || drop_count_o !== 32'd4) begin
            $display("[TB] FAIL (SPI-END-COL): expected tx=6 drop=4, got tx=%0d drop=%0d", tx_count_o, drop_count_o);
            $fatal(1);
        end
        @(posedge clk);
        check_idle_outputs("AFTER-SPI-END");
        $display("[TB] PASS Test 5 (SPI S_SPI_END drop + first S_IDLE accept): tx=%0d drop=%0d", tx_count_o, drop_count_o);

        // --------------------------------------------------------------------
        // Test 6: Boundary collision in S_PAR_END (dropped) & multi-cycle event_valid_i (3 cycles)
        // --------------------------------------------------------------------
        par_rx_bytes  = 0;
        par_rx_done   = 1'b0;
        send_event(1'b1, 6'd11, 32'h0000_4444, 32'h1234_0001);
        // send_event returns at negedge of cycle 1 (S_PAR_LOW); 16 posedges later is S_PAR_END
        repeat (16) @(posedge clk);
        if (busy_o !== 1'b1) begin
            $display("[TB] FAIL (PAR-END-COL): expected busy_o == 1 in S_PAR_END");
            $fatal(1);
        end
        // Assert event_valid_i in S_PAR_END (drop) + keep high for 3 cycles in S_IDLE (1 accept + 2 drops)
        @(negedge clk);
        mode_par8_i   = 1'b1;
        event_cid_i   = 6'd12;
        event_mask_i  = 32'h0000_5555;
        event_state_i = 32'h1234_0002;
        event_valid_i = 1'b1;
        @(negedge clk); // 1st S_IDLE: accepted
        event_cid_i   = 6'd13;
        event_mask_i  = 32'h0000_6666;
        event_state_i = 32'h1234_0003;
        @(negedge clk); // 2nd cycle (busy): dropped
        @(negedge clk); // 3rd cycle (busy): dropped
        @(negedge clk);
        event_valid_i = 1'b0;

        wait(par_rx_done == 1'b1);
        @(posedge clk);
        verify_frame(par_rx_captured, 6'd11, 16'h4444, 32'h1234_0001, "PAR-END-1");

        par_rx_bytes = 0;
        par_rx_done  = 1'b0;
        wait(par_rx_done == 1'b1);
        @(posedge clk);
        verify_frame(par_rx_frame, 6'd13, 16'h6666, 32'h1234_0003, "PAR-MULTI-CYC");
        if (tx_count_o !== 32'd8 || drop_count_o !== 32'd7) begin
            $display("[TB] FAIL (PAR-END-COL): expected tx=8 drop=7, got tx=%0d drop=%0d", tx_count_o, drop_count_o);
            $fatal(1);
        end
        @(posedge clk);
        check_idle_outputs("AFTER-PAR-END");
        $display("[TB] PASS Test 6 (PAR S_PAR_END drop + multi-cycle valid): tx=%0d drop=%0d", tx_count_o, drop_count_o);

        $display("[TB] ALL KM_PMOD_EVENT_EGRESS SIMULATION TESTS PASSED");
        $finish;
    end

endmodule
