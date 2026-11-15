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
            par_rx_done <= 1'b1;
        end
    end

    // Cycle counter for transfer duration and event_start_o strobe verification
    integer active_cycles;
    integer start_pulses;

    always @(posedge clk) begin
        if (!rst_n) begin
            active_cycles <= 0;
            start_pulses  <= 0;
        end else begin
            if (busy_o)
                active_cycles <= active_cycles + 1;
            if (event_start_o)
                start_pulses <= start_pulses + 1;
        end
    end

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

        #25 rst_n = 1'b1;
        @(posedge clk);

        if (ready_o !== 1'b1 || busy_o !== 1'b0 || spi_cs_n_o !== 1'b1) begin
            $display("[TB] FAIL: invalid reset idle state");
            $fatal(1);
        end

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
        $display("[TB] PASS Test 4 (PAR8 Zero): frame=%h tx=%0d drop=%0d", par_rx_frame, tx_count_o, drop_count_o);

        $display("[TB] ALL KM_PMOD_EVENT_EGRESS SIMULATION TESTS PASSED");
        $finish;
    end

endmodule
