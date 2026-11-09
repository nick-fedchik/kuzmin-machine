// ============================================================================
// File: km_stream_pipeline_engine.sv
// Project: Kuzmin Machine (Машина Кузьміна) — PYNQ-Z1 Open-Source Overlay
// Module: km_stream_pipeline_engine
// Description:
//   EXP-10: Hardware Streaming Dataflow Pipeline across Concepts in PL.
//   Executes a 4-stage pipelined event-driven transformation at Initiation
//   Interval II = 1 (1 event per clock cycle, 100 M events/s at 100 MHz):
//
//     Stage 0 (CID[0] Sensor): Ingestion & sample generation (1024 samples)
//     Stage 1 (CID[1] Filter): 1st-order IIR/EMA filter: y[k] = (3*y[k-1] + x[k]) >> 2
//     Stage 2 (CID[2] Deriv) : Rate-of-change / Error derivative: d[k] = y[k] - y[k-1]
//     Stage 3 (CID[3] Guard) : Actuator Safety Guard with Invariant Clamping:
//                              u[k] = y[k] + d[k];
//                              If u[k] > +500 => clamp +500, flag clamp_hi
//                              If u[k] < -500 => clamp -500, flag clamp_lo
//
//   Pipelining properties:
//     - Latency to first output: 4 clock cycles (40.0 ns)
//     - Throughput: 1 result per cycle (10.0 ns/Tx)
//     - Total duration for 1024 samples: 1027 cycles (10.27 us)
// ============================================================================

`timescale 1ns / 1ps

module km_stream_pipeline_engine #(
    parameter int BURST_SIZE = 1024
) (
    input  wire        clk_i,
    input  wire        rst_ni,

    // Control & Command interface
    input  wire        start_i,
    input  wire [1:0]  mode_i,       // 00 = Normal, 01 = With Glitch Injection
    input  wire [15:0] count_cfg_i,  // 0 = default BURST_SIZE (1024)

    // Status & Telemetry
    output reg         busy_o,
    output reg         done_o,
    output reg         pass_o,
    output reg  [31:0] cycle_count_o,
    output reg  [15:0] processed_count_o,
    output reg  [15:0] clamped_count_o,
    output reg  [31:0] checksum_o,
    output reg  [31:0] last_val_o    // {stage3_u[15:0], stage1_y[15:0]}
);

    // Operational FSM states
    localparam [2:0] S_IDLE     = 3'b000;
    localparam [2:0] S_RUNNING  = 3'b001;
    localparam [2:0] S_DRAIN    = 3'b010;
    localparam [2:0] S_FINISH   = 3'b011;

    reg [2:0] state_q;

    // Registers for pipeline
    reg [15:0] target_count_q;
    reg [15:0] sample_gen_cnt_q;
    reg [31:0] cycles_q;
    reg [15:0] out_cnt_q;
    reg [15:0] clamp_cnt_q;
    reg [31:0] accum_sum_q;

    // Stage 0: Sample Generator
    reg signed [15:0] s0_sample_q;
    reg               s0_valid_q;

    // Stage 1: EMA Filter: y[k] = (3*y[k-1] + x[k]) / 4
    reg signed [15:0] s1_y_prev_q;
    reg signed [15:0] s1_y_q;
    reg signed [15:0] s1_x_q;
    reg               s1_valid_q;
    wire signed [17:0] ema_calc = ($signed(s1_y_prev_q) * 3) + $signed(s0_sample_q);

    // Stage 2: Derivative: d[k] = y[k] - y[k-1]
    reg signed [15:0] s2_y_q;
    reg signed [15:0] s2_y_prev_q;
    reg signed [15:0] s2_d_q;
    reg               s2_valid_q;

    // Stage 3: Actuator Guard: u[k] = y[k] + d[k], clamped to [-500, +500]
    reg signed [15:0] s3_u_q;
    reg               s3_clamped_q;
    reg               s3_valid_q;
    wire signed [17:0] u_raw = $signed(s2_y_q) + $signed(s2_d_q);

    // Sample generation logic: Triangular wave oscillating between -200 and +200
    // If mode == 01, at samples 500..509 inject huge spike of +2500
    reg signed [15:0] gen_val_q;
    reg               gen_dir_q; // 0 = up, 1 = down

    wire [15:0] active_burst = (count_cfg_i == 16'd0) ? BURST_SIZE[15:0] : count_cfg_i;

    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state_q            <= S_IDLE;
            busy_o             <= 1'b0;
            done_o             <= 1'b0;
            pass_o             <= 1'b0;
            cycle_count_o      <= 32'd0;
            processed_count_o  <= 16'd0;
            clamped_count_o    <= 16'd0;
            checksum_o         <= 32'd0;
            last_val_o         <= 32'd0;
            target_count_q     <= 16'd0;
            sample_gen_cnt_q   <= 16'd0;
            cycles_q           <= 32'd0;
            out_cnt_q          <= 16'd0;
            clamp_cnt_q        <= 16'd0;
            accum_sum_q        <= 32'd0;
            gen_val_q          <= 16'sd0;
            gen_dir_q          <= 1'b0;

            s0_sample_q        <= 16'sd0;
            s0_valid_q         <= 1'b0;
            s1_y_prev_q        <= 16'sd0;
            s1_y_q             <= 16'sd0;
            s1_x_q             <= 16'sd0;
            s1_valid_q         <= 1'b0;
            s2_y_q             <= 16'sd0;
            s2_y_prev_q        <= 16'sd0;
            s2_d_q             <= 16'sd0;
            s2_valid_q         <= 1'b0;
            s3_u_q             <= 16'sd0;
            s3_clamped_q       <= 1'b0;
            s3_valid_q         <= 1'b0;
        end else begin
            case (state_q)
                S_IDLE: begin
                    busy_o <= 1'b0;
                    if (start_i) begin
                        state_q            <= S_RUNNING;
                        busy_o             <= 1'b1;
                        done_o             <= 1'b0;
                        pass_o             <= 1'b0;
                        target_count_q     <= active_burst;
                        sample_gen_cnt_q   <= 16'd0;
                        cycles_q           <= 32'd0;
                        out_cnt_q          <= 16'd0;
                        clamp_cnt_q        <= 16'd0;
                        accum_sum_q        <= 32'd0;
                        gen_val_q          <= 16'sd0;
                        gen_dir_q          <= 1'b0;
                        s1_y_prev_q        <= 16'sd0;
                        s2_y_prev_q        <= 16'sd0;
                        s0_valid_q         <= 1'b0;
                        s1_valid_q         <= 1'b0;
                        s2_valid_q         <= 1'b0;
                        s3_valid_q         <= 1'b0;
                    end
                end

                S_RUNNING, S_DRAIN: begin
                    cycles_q <= cycles_q + 32'd1;

                    // --------------------------------------------------------
                    // Stage 0: Sample Generation (Autonomous source)
                    // --------------------------------------------------------
                    if (state_q == S_RUNNING) begin
                        sample_gen_cnt_q <= sample_gen_cnt_q + 16'd1;
                        s0_valid_q       <= 1'b1;

                        // Check for glitch injection
                        if (mode_i[0] && (sample_gen_cnt_q >= 16'd500 && sample_gen_cnt_q < 16'd510)) begin
                            s0_sample_q <= 16'sd2500; // Out-of-bounds anomaly!
                        end else begin
                            s0_sample_q <= gen_val_q;
                            // Update triangular generator: step by 10 between -200 and +200
                            if (!gen_dir_q) begin
                                if (gen_val_q >= 16'sd190) begin
                                    gen_val_q <= 16'sd200;
                                    gen_dir_q <= 1'b1;
                                end else begin
                                    gen_val_q <= gen_val_q + 16'sd10;
                                end
                            end else begin
                                if (gen_val_q <= -16'sd190) begin
                                    gen_val_q <= -16'sd200;
                                    gen_dir_q <= 1'b0;
                                end else begin
                                    gen_val_q <= gen_val_q - 16'sd10;
                                end
                            end
                        end

                        if (sample_gen_cnt_q + 16'd1 >= target_count_q) begin
                            state_q <= S_DRAIN;
                        end
                    end else begin
                        s0_valid_q  <= 1'b0;
                        s0_sample_q <= 16'sd0;
                    end

                    // --------------------------------------------------------
                    // Stage 1: Concept[1] Filter (EMA Filter)
                    // y[k] = (3 * y[k-1] + x[k]) / 4
                    // --------------------------------------------------------
                    s1_valid_q <= s0_valid_q;
                    if (s0_valid_q) begin
                        s1_y_q      <= ema_calc[17:2];
                        s1_y_prev_q <= ema_calc[17:2];
                        s1_x_q      <= s0_sample_q;
                    end

                    // --------------------------------------------------------
                    // Stage 2: Concept[2] Derivative (d[k] = y[k] - y[k-1])
                    // --------------------------------------------------------
                    s2_valid_q <= s1_valid_q;
                    if (s1_valid_q) begin
                        s2_y_q      <= s1_y_q;
                        s2_d_q      <= s1_y_q - s2_y_prev_q; // rate-of-change
                        s2_y_prev_q <= s1_y_q;
                    end

                    // --------------------------------------------------------
                    // Stage 3: Concept[3] Actuator Guard & Invariant Enforcement
                    // Target u = y + d. Clamped to [-500, +500].
                    // --------------------------------------------------------
                    s3_valid_q <= s2_valid_q;
                    if (s2_valid_q) begin
                        if (u_raw > 18'sd500) begin
                            s3_u_q       <= 16'sd500;
                            s3_clamped_q <= 1'b1;
                        end else if (u_raw < -18'sd500) begin
                            s3_u_q       <= -16'sd500;
                            s3_clamped_q <= 1'b1;
                        end else begin
                            s3_u_q       <= u_raw[15:0];
                            s3_clamped_q <= 1'b0;
                        end
                    end

                    // --------------------------------------------------------
                    // Output Collector & Invariant Verification
                    // --------------------------------------------------------
                    if (s3_valid_q) begin
                        out_cnt_q   <= out_cnt_q + 16'd1;
                        accum_sum_q <= accum_sum_q + {16'd0, s3_u_q};
                        if (s3_clamped_q) begin
                            clamp_cnt_q <= clamp_cnt_q + 16'd1;
                        end

                        if (out_cnt_q + 16'd1 >= target_count_q) begin
                            state_q <= S_FINISH;
                        end
                    end
                end

                S_FINISH: begin
                    busy_o            <= 1'b0;
                    done_o            <= 1'b1;
                    cycle_count_o     <= cycles_q;
                    processed_count_o <= out_cnt_q;
                    clamped_count_o   <= clamp_cnt_q;
                    checksum_o        <= accum_sum_q;
                    last_val_o        <= {s3_u_q, s1_y_q};

                    // Pass condition: exactly target_count_q samples processed;
                    // If mode == 01 (glitch), at least 1 clamp event occurred;
                    // If mode == 00 (normal), zero clamp events occurred.
                    if (out_cnt_q == target_count_q) begin
                        if (mode_i[0]) begin
                            pass_o <= (clamp_cnt_q > 16'd0);
                        end else begin
                            pass_o <= (clamp_cnt_q == 16'd0);
                        end
                    end else begin
                        pass_o <= 1'b0;
                    end

                    state_q <= S_IDLE;
                end

                default: state_q <= S_IDLE;
            endcase
        end
    end

endmodule
