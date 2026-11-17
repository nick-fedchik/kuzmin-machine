`timescale 1ns / 1ps

// ============================================================================
// Модуль: km_manycore_synth_top.sv
// Призначення: Компактна синтезна обгортка для фізичного Place & Route та STA
// кластера `km_manycore_cluster` (N = 1, 2, 4, 8) у середовищі OpenXC7
// (`yosys synth_xilinx -flatten -abc9 -arch xc7` + `nextpnr-himbaechel` на
// кристалі `xc7z020clg400-1`, Issue #255).
//
// Усі зовнішні сигнали мультиплексуються через 20 фізичних пінів (< 125 IOB)
// та ізолюються вхідними/вихідними тригерами, щоб:
//   1) жодне з N ядер, жоден із N блоків RAMB36E1 та жоден порт кросбара
//      не були видалені оптимізатором (`RAMB36E1 == NUM_CORES`);
//   2) критичний шлях STA вимірював внутрішню логіку й трасування кластера,
//      а не затримку виводів корпусу CLG400.
// ============================================================================

`ifndef KM_SYNTH_CORES
`define KM_SYNTH_CORES 4
`endif

`ifndef KM_SYNTH_PIPE_STAGES
`define KM_SYNTH_PIPE_STAGES 1
`endif

module km_manycore_synth_top #(
    parameter int NUM_CORES       = `KM_SYNTH_CORES,
    parameter int PIPELINE_STAGES = `KM_SYNTH_PIPE_STAGES
)(
    input  wire       clk_i,
    input  wire       rst_ni,
    input  wire       cmd_valid_i,
    input  wire [1:0] cmd_mode_i,
    input  wire [2:0] cmd_sel_i,
    input  wire [7:0] cmd_data_i,

    output wire       status_busy_o,
    output wire       status_ready_o,
    output wire [2:0] obs_data_o
);

    wire clk;
    BUFG clk_buf (
        .I(clk_i),
        .O(clk)
    );

    // Двоступеневий синхронізатор скидання та вхідні регістри межі кристала
    reg [1:0] rst_sync_q;
    wire      rst_n = rst_sync_q[1];

    reg       in_valid_q;
    reg [1:0] in_mode_q;
    reg [2:0] in_sel_q;
    reg [7:0] in_data_q;

    always @(posedge clk) begin
        rst_sync_q <= {rst_sync_q[0], rst_ni};
        in_valid_q <= cmd_valid_i;
        in_mode_q  <= cmd_mode_i;
        in_sel_q   <= cmd_sel_i;
        in_data_q  <= cmd_data_i;
    end

    // Десеріалізатор конфігурації Порту A та N зовнішніх портів тригерів
    reg [47:0]             sh_frame_q;
    reg [3:0]              cfg_bank_sel_q;
    reg [7:0]              cfg_addr_q;
    reg [31:0]             cfg_wdata_q;
    reg [3:0]              cfg_wstrb_q;
    reg                    cfg_we_q;

    reg [NUM_CORES-1:0]    ext_valid_q;
    reg [NUM_CORES*4-1:0]  ext_dst_bank_q;
    reg [NUM_CORES*6-1:0]  ext_dst_cid_q;
    reg [NUM_CORES*32-1:0] ext_param_q;
    reg [4:0]              obs_mux_sel_q;

    wire [NUM_CORES-1:0]   ext_ready_w;

    integer k;
    always @(posedge clk) begin
        if (!rst_n) begin
            sh_frame_q     <= 48'd0;
            cfg_bank_sel_q <= 4'd0;
            cfg_addr_q     <= 8'd0;
            cfg_wdata_q    <= 32'd0;
            cfg_wstrb_q    <= 4'd0;
            cfg_we_q       <= 1'b0;
            ext_valid_q    <= {NUM_CORES{1'b0}};
            ext_dst_bank_q <= {(NUM_CORES*4){1'b0}};
            ext_dst_cid_q  <= {(NUM_CORES*6){1'b0}};
            ext_param_q    <= {(NUM_CORES*32){1'b0}};
            obs_mux_sel_q  <= 5'd0;
        end else begin
            cfg_we_q <= 1'b0;

            for (k = 0; k < NUM_CORES; k = k + 1) begin
                if (ext_valid_q[k] && ext_ready_w[k]) begin
                    ext_valid_q[k] <= 1'b0;
                end
            end

            if (in_valid_q) begin
                case (in_mode_q)
                    2'b00: begin
                        sh_frame_q <= {sh_frame_q[39:0], in_data_q};
                    end
                    2'b01: begin
                        cfg_bank_sel_q <= sh_frame_q[47:44];
                        cfg_wstrb_q    <= sh_frame_q[43:40];
                        cfg_addr_q     <= sh_frame_q[39:32];
                        cfg_wdata_q    <= sh_frame_q[31:0];
                        cfg_we_q       <= in_data_q[0];
                        obs_mux_sel_q  <= in_data_q[5:1];
                    end
                    2'b10: begin
                        for (k = 0; k < NUM_CORES; k = k + 1) begin
                            if (in_sel_q == k[2:0]) begin
                                ext_valid_q[k]           <= 1'b1;
                                ext_dst_bank_q[k*4 +: 4] <= sh_frame_q[41:38];
                                ext_dst_cid_q[k*6 +: 6]  <= sh_frame_q[37:32];
                                ext_param_q[k*32 +: 32]  <= sh_frame_q[31:0];
                            end
                        end
                    end
                    default: begin
                        obs_mux_sel_q  <= {in_sel_q[1:0], in_data_q[2:0]};
                        cfg_bank_sel_q <= in_data_q[7:4];
                        cfg_addr_q     <= sh_frame_q[7:0];
                    end
                endcase
            end
        end
    end

    // Інстанціювання багатоядерного кластера Машини Кузьміна
    wire [31:0]             cfg_rdata_w;
    wire [NUM_CORES-1:0]    collision_w;
    wire [NUM_CORES-1:0]    core_busy_w;
    wire [NUM_CORES-1:0]    core_fifo_full_w;
    wire [NUM_CORES-1:0]    core_commit_w;
    wire [NUM_CORES-1:0]    core_reject_w;
    wire [NUM_CORES*32-1:0] core_last_state_w;
    wire                    cluster_busy_w;
    wire [31:0]             total_ev_w;
    wire [31:0]             total_comm_w;
    wire [31:0]             total_rej_w;
    wire [31:0]             total_loc_w;
    wire [31:0]             total_rem_w;
    wire [31:0]             xbar_routed_w;
    wire [31:0]             stall_cycles_w;
    wire [31:0]             inv_drop_w;

    km_manycore_cluster #(
        .NUM_CORES(NUM_CORES),
        .NUM_EXT_PORTS(NUM_CORES),
        .QUEUE_DEPTH(16),
        .NUM_CONCEPTS(64),
        .DATA_WIDTH(32),
        .ADDR_WIDTH(8),
        .PIPELINE_STAGES(PIPELINE_STAGES)
    ) dut_cluster (
        .clk(clk),
        .rst_n(rst_n),
        .cfg_bank_sel_i(cfg_bank_sel_q),
        .cfg_addr_i(cfg_addr_q),
        .cfg_wdata_i(cfg_wdata_q),
        .cfg_wstrb_i(cfg_wstrb_q),
        .cfg_we_i(cfg_we_q),
        .cfg_rdata_o(cfg_rdata_w),
        .collision_detected_o(collision_w),
        .ext_valid_i(ext_valid_q),
        .ext_ready_o(ext_ready_w),
        .ext_dst_bank_i(ext_dst_bank_q),
        .ext_dst_cid_i(ext_dst_cid_q),
        .ext_param_i(ext_param_q),
        .core_busy_o(core_busy_w),
        .core_fifo_full_o(core_fifo_full_w),
        .core_commit_pulse_o(core_commit_w),
        .core_reject_pulse_o(core_reject_w),
        .core_last_state_o(core_last_state_w),
        .cluster_busy_o(cluster_busy_w),
        .total_events_processed_o(total_ev_w),
        .total_committed_o(total_comm_w),
        .total_rejected_o(total_rej_w),
        .total_local_cascades_o(total_loc_w),
        .total_remote_cascades_o(total_rem_w),
        .xbar_routed_events_o(xbar_routed_w),
        .backpressure_stall_cycles_o(stall_cycles_w),
        .invalid_dst_drop_count_o(inv_drop_w)
    );

    // Згортка поядерних виходів і телеметрії без втрати спостережуваності жодного біта
    reg [31:0] core_state_mux_w;
    always @(*) begin
        core_state_mux_w = 32'd0;
        for (k = 0; k < NUM_CORES; k = k + 1) begin
            if (obs_mux_sel_q[2:0] == k[2:0]) begin
                core_state_mux_w = core_last_state_w[k*32 +: 32];
            end
        end
    end

    reg [31:0] word_mux_w;
    always @(*) begin
        case (obs_mux_sel_q[4:1])
            4'd0:  word_mux_w = cfg_rdata_w;
            4'd1:  word_mux_w = core_state_mux_w;
            4'd2:  word_mux_w = total_ev_w;
            4'd3:  word_mux_w = total_comm_w;
            4'd4:  word_mux_w = total_rej_w;
            4'd5:  word_mux_w = total_loc_w;
            4'd6:  word_mux_w = total_rem_w;
            4'd7:  word_mux_w = xbar_routed_w;
            4'd8:  word_mux_w = stall_cycles_w;
            4'd9:  word_mux_w = inv_drop_w;
            default: word_mux_w = {{(32-NUM_CORES){1'b0}}, collision_w} ^
                                  {{(32-NUM_CORES){1'b0}}, core_busy_w} ^
                                  {{(32-NUM_CORES){1'b0}}, core_fifo_full_w} ^
                                  {{(32-NUM_CORES){1'b0}}, core_commit_w} ^
                                  {{(32-NUM_CORES){1'b0}}, core_reject_w};
        endcase
    end

    reg [31:0] obs_shift_q;
    reg        out_busy_q;
    reg        out_ready_q;
    reg [2:0]  out_data_q;

    always @(posedge clk) begin
        if (!rst_n) begin
            obs_shift_q <= 32'd0;
            out_busy_q  <= 1'b0;
            out_ready_q <= 1'b0;
            out_data_q  <= 3'd0;
        end else begin
            if (in_valid_q && obs_mux_sel_q[0]) begin
                obs_shift_q <= word_mux_w;
            end else begin
                obs_shift_q <= {obs_shift_q[29:0], word_mux_w[1:0]};
            end
            out_busy_q  <= cluster_busy_w;
            out_ready_q <= (&ext_ready_w);
            out_data_q  <= {obs_shift_q[31], (^word_mux_w), (|core_commit_w) ^ (|core_reject_w)};
        end
    end

    assign status_busy_o  = out_busy_q;
    assign status_ready_o = out_ready_q;
    assign obs_data_o     = out_data_q;

endmodule
