// ============================================================================
// File: km_pmod_event_egress.sv
// Project: Kuzmin Machine (Машина Кузьміна) — PYNQ-Z1 EXP-GPU-01 Prerequisite
// Module: km_pmod_event_egress
// Description:
//   PMOD Event Egress serializer for EXP-GPU-01 (PYNQ-Z1 -> Jetson J501).
//   Serializes a 64-bit event frame over either:
//     - mode_par8_i == 0: SPI Master (Mode 0, CPOL=0, CPHA=0, MSB-first, clk/2 = 50 MHz @ 100 MHz)
//     - mode_par8_i == 1: 8-bit source-synchronous parallel bus (MSB byte first, clk/2 = 50 MHz @ 100 MHz)
//
//   64-bit Frame Format [63:0]:
//     [63:56] : crc8[7:0]          - CRC-8 (poly 0x07, init 0x00, MSB-first over [55:0])
//     [55:54] : 2'b01              - Frame format tag (CRC8-protected event frame)
//     [53:48] : event_cid_i[5:0]   - Concept ID (0..63)
//     [47:32] : event_mask_i[15:0] - Lower 16 bits of subscriber mask
//     [31:0]  : event_state_i[31:0]- Updated 32-bit concept state
//
//   If event_valid_i is asserted while busy_o == 1, the active transfer is
//   preserved without corruption and drop_count_o is incremented by 1.
// ============================================================================

`timescale 1ns / 1ps

module km_pmod_event_egress (
    input  wire        clk,
    input  wire        rst_n,

    // Mode select: 0 = SPI Master (clk/2), 1 = 8-bit source-synchronous parallel (clk/2)
    input  wire        mode_par8_i,

    // Event input interface (100 MHz domain)
    input  wire        event_valid_i,
    input  wire [5:0]  event_cid_i,
    input  wire [31:0] event_mask_i,
    input  wire [31:0] event_state_i,

    // RP2040 PIO GP0 start strobe (1-cycle pulse on accepted event)
    output reg         event_start_o,

    // Phase 1: SPI Master interface (Mode 0: CPOL=0, CPHA=0, MSB-first)
    output reg         spi_cs_n_o,
    output reg         spi_sck_o,
    output reg         spi_mosi_o,

    // Phase 2: 8-bit source-synchronous parallel interface (MSB byte first)
    output reg         par_valid_o,
    output reg         par_clk_o,
    output reg  [7:0]  par_data_o,

    // Status & Telemetry
    output reg         busy_o,
    output reg         ready_o,
    output reg  [31:0] tx_count_o,
    output reg  [31:0] drop_count_o
);

    // Explicitly tie off unused upper 16 bits of event_mask_i for clean lint
    /* verilator lint_off UNUSEDSIGNAL */
    wire _unused_mask_hi = &{1'b0, event_mask_i[31:16]};
    /* verilator lint_on UNUSEDSIGNAL */

    // CRC-8 (polynomial 0x07, init 0x00, MSB-first over 56-bit payload)
    function automatic [7:0] calc_crc8;
        input [55:0] data_in;
        integer i;
        reg [7:0] crc;
        reg       fb;
        begin
            crc = 8'h00;
            for (i = 55; i >= 0; i = i - 1) begin
                fb = crc[7] ^ data_in[i];
                crc = {crc[6:0], 1'b0} ^ (fb ? 8'h07 : 8'h00);
            end
            calc_crc8 = crc;
        end
    endfunction

    wire [55:0] frame_payload = {2'b01, event_cid_i, event_mask_i[15:0], event_state_i};
    wire [7:0]  frame_crc8    = calc_crc8(frame_payload);
    wire [63:0] frame_64      = {frame_crc8, frame_payload};

    localparam [2:0] S_IDLE     = 3'd0;
    localparam [2:0] S_SPI_LOW  = 3'd1;
    localparam [2:0] S_SPI_HIGH = 3'd2;
    localparam [2:0] S_SPI_END  = 3'd3;
    localparam [2:0] S_PAR_LOW  = 3'd4;
    localparam [2:0] S_PAR_HIGH = 3'd5;
    localparam [2:0] S_PAR_END  = 3'd6;

    reg [2:0]  state_q;
    reg [63:0] shift_reg_q;
    reg [5:0]  bit_cnt_q;
    reg [2:0]  byte_cnt_q;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q       <= S_IDLE;
            shift_reg_q   <= 64'd0;
            bit_cnt_q     <= 6'd0;
            byte_cnt_q    <= 3'd0;
            event_start_o <= 1'b0;
            spi_cs_n_o    <= 1'b1;
            spi_sck_o     <= 1'b0;
            spi_mosi_o    <= 1'b0;
            par_valid_o   <= 1'b0;
            par_clk_o     <= 1'b0;
            par_data_o    <= 8'd0;
            busy_o        <= 1'b0;
            ready_o       <= 1'b1;
            tx_count_o    <= 32'd0;
            drop_count_o  <= 32'd0;
        end else begin
            // Default: event_start_o is a single-cycle strobe
            event_start_o <= 1'b0;

            // Collision accounting: drop incoming valid event if serializer is busy
            if (event_valid_i && (state_q != S_IDLE)) begin
                drop_count_o <= drop_count_o + 32'd1;
            end

            case (state_q)
                S_IDLE: begin
                    spi_cs_n_o  <= 1'b1;
                    spi_sck_o   <= 1'b0;
                    spi_mosi_o  <= 1'b0;
                    par_valid_o <= 1'b0;
                    par_clk_o   <= 1'b0;
                    par_data_o  <= 8'd0;

                    if (event_valid_i) begin
                        shift_reg_q   <= frame_64;
                        event_start_o <= 1'b1;
                        busy_o        <= 1'b1;
                        ready_o       <= 1'b0;
                        bit_cnt_q     <= 6'd0;
                        byte_cnt_q    <= 3'd0;

                        if (mode_par8_i) begin
                            state_q <= S_PAR_LOW;
                        end else begin
                            state_q <= S_SPI_LOW;
                        end
                    end else begin
                        busy_o  <= 1'b0;
                        ready_o <= 1'b1;
                    end
                end

                // ------------------------------------------------------------
                // SPI Master Mode 0 (CPOL=0, CPHA=0, MSB-first, 50 MHz @ 100 MHz)
                // ------------------------------------------------------------
                S_SPI_LOW: begin
                    spi_cs_n_o <= 1'b0;
                    spi_sck_o  <= 1'b0;
                    spi_mosi_o <= shift_reg_q[63];
                    state_q    <= S_SPI_HIGH;
                end

                S_SPI_HIGH: begin
                    spi_cs_n_o <= 1'b0;
                    spi_sck_o  <= 1'b1;
                    if (bit_cnt_q == 6'd63) begin
                        state_q <= S_SPI_END;
                    end else begin
                        shift_reg_q <= {shift_reg_q[62:0], 1'b0};
                        bit_cnt_q   <= bit_cnt_q + 6'd1;
                        state_q     <= S_SPI_LOW;
                    end
                end

                S_SPI_END: begin
                    spi_sck_o  <= 1'b0;
                    spi_cs_n_o <= 1'b0;
                    spi_mosi_o <= 1'b0;
                    tx_count_o <= tx_count_o + 32'd1;
                    busy_o     <= 1'b0;
                    ready_o    <= 1'b1;
                    state_q    <= S_IDLE;
                end

                // ------------------------------------------------------------
                // 8-bit Source-Synchronous Parallel Bus (MSB byte first, 50 MHz)
                // ------------------------------------------------------------
                S_PAR_LOW: begin
                    par_valid_o <= 1'b1;
                    par_clk_o   <= 1'b0;
                    par_data_o  <= shift_reg_q[63:56];
                    state_q     <= S_PAR_HIGH;
                end

                S_PAR_HIGH: begin
                    par_valid_o <= 1'b1;
                    par_clk_o   <= 1'b1;
                    if (byte_cnt_q == 3'd7) begin
                        state_q <= S_PAR_END;
                    end else begin
                        shift_reg_q <= {shift_reg_q[55:0], 8'd0};
                        byte_cnt_q  <= byte_cnt_q + 3'd1;
                        state_q     <= S_PAR_LOW;
                    end
                end

                S_PAR_END: begin
                    par_clk_o   <= 1'b0;
                    par_valid_o <= 1'b1;
                    tx_count_o  <= tx_count_o + 32'd1;
                    busy_o      <= 1'b0;
                    ready_o     <= 1'b1;
                    state_q     <= S_IDLE;
                end

                default: begin
                    state_q <= S_IDLE;
                end
            endcase
        end
    end

endmodule
