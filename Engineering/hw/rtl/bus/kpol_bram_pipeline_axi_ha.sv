`timescale 1ns/1ps

// ============================================================================
// Модуль: kpol_bram_pipeline_axi_ha.sv
// Призначення: Двобанковий MMIO інтерфейс шини AXI4-Lite та інтегратор подій
// для конфігурації високої готовності CFG-P-HA (B4 Варіант 2, Issue #252,
// експеримент EXP-GPU-02).
//
// Зберігає сумісність із базовими регістрами CFG-P (0x000..0x02C, ID "KPHA")
// і додає регістри безблокувального онлайнового оновлення правил у тіньовому
// банку BRAM (0x030..0x044) та зовнішні строби метрології RP2040 PIO.
// ============================================================================

module kpol_bram_pipeline_axi_ha #(
    parameter int NUM_CONCEPTS = 64,
    parameter int QUEUE_DEPTH  = 16,
    parameter int DATA_WIDTH   = 32,
    parameter int ADDR_WIDTH   = 8
)(
    input  logic        clk,
    input  logic        rst_n,

    // AXI4-Lite Slave Write Channel
    input  logic [12:0] awaddr,
    input  logic        awvalid,
    output logic        awready,
    input  logic [31:0] wdata,
    input  logic [3:0]  wstrb,
    input  logic        wvalid,
    output logic        wready,
    output logic [1:0]  bresp,
    output logic        bvalid,
    input  logic        bready,

    // AXI4-Lite Slave Read Channel
    input  logic [12:0] araddr,
    input  logic        arvalid,
    output logic        arready,
    output logic [31:0] rdata,
    output logic [1:0]  rresp,
    output logic        rvalid,
    input  logic        rready,

    // Зовнішній апаратний тригер події (HWE.1, HWE.2, B2)
    input  logic        ext_hw_trigger_valid_i,
    input  logic [5:0]  ext_hw_trigger_cid_i,
    input  logic [31:0] ext_hw_trigger_param_i,
    output logic        hw_trigger_ready_o,

    // Базові виходи статусу та моніторингу для PMOD/LED стенда (HWE.2)
    output logic        hw_commit_pulse_o,
    output logic        hw_reject_pulse_o,
    output logic        hw_pipeline_busy_o,
    output logic        fifo_overflow_o,
    output logic [31:0] events_dropped_count_o,
    output logic [5:0]  hw_commit_cid_o,
    output logic [31:0] hw_last_committed_state_o,

    // Діагностичні строби протоколу EXP-GPU-02 (3.3V LVCMOS / RP2040 PIO)
    output logic        inject_strobe_o,
    output logic        bank_swap_commit_o,
    output logic        stimulus_accepted_o,
    output logic        reaction_out_o,
    output logic        seq_cycle_done_o,

    // Загальний статус зайнятості конвеєра подій
    output logic        busy
);
    localparam logic [1:0] OKAY = 2'b00, SLVERR = 2'b10, DECERR = 2'b11;

    logic aw_pending, w_pending;
    logic [12:0] awaddr_q;
    logic [31:0] wdata_q;
    logic [3:0]  wstrb_q;
    logic        read_pending;
    logic [12:0] read_addr;
    logic        read_addr_sampled_q;

    wire aw_fire    = awvalid && awready;
    wire w_fire     = wvalid && wready;
    wire write_fire = (aw_pending || aw_fire) && (w_pending || w_fire);
    wire [12:0] write_addr = aw_pending ? awaddr_q : awaddr;
    wire [31:0] write_data = w_pending  ? wdata_q  : wdata;
    wire [3:0]  write_strb = w_pending  ? wstrb_q  : wstrb;

    assign awready = !aw_pending && !bvalid;
    assign wready  = !w_pending && !bvalid;
    assign arready = !rvalid && !read_pending;

    // Регістри початкового завантаження (PHASE_LOAD) та онлайн-інжекції (B4 Варіант 2)
    logic [ADDR_WIDTH-1:0] bram_addr;
    logic [31:0]           bram_wdata;
    logic                  bram_we;
    logic [31:0]           event_param;
    logic                  sw_trigger;

    logic [ADDR_WIDTH-1:0] shadow_addr;
    logic [ADDR_WIDTH-1:0] shadow_waddr;
    logic [31:0]           shadow_wdata;
    logic                  shadow_we;
    logic                  swap_req;

    // Внутрішні з'єднання секвенсера та двобанкової BRAM
    wire [31:0]           bram_a_rdata;
    wire [ADDR_WIDTH-1:0] b_addr;
    wire [31:0]           b_wdata;
    wire [3:0]            b_wstrb;
    wire                  b_we;
    wire [31:0]           b_rdata;

    wire                  seq_busy;
    /* verilator lint_off UNUSEDSIGNAL */
    wire                  seq_fifo_full_unused;
    /* verilator lint_on UNUSEDSIGNAL */
    wire                  seq_trigger_ready;
    wire                  seq_fifo_overflow;
    wire [31:0]           events;
    wire [31:0]           commits;
    wire [31:0]           rejects;
    wire [31:0]           last_state;
    wire [31:0]           seq_dropped_count;

    wire                  active_bank;
    wire                  swap_pending;
    wire                  sync_busy;
    wire                  collision_detected;

    // Регістри контролю утримання зовнішнього тригера при початковому PHASE_LOAD
    logic        ext_sw_stalled_q;
    logic        axi_sw_overflow_q;
    logic [5:0]  ext_sw_cid_q;
    logic [31:0] ext_sw_param_q;
    logic [31:0] axi_sw_dropped_q;

    // Зовнішній 3-бітний lockstep-детектор фази секвенсера (0 = ST_IDLE, 1..7 = ST_REQ_W0..ST_EVAL_GATE)
    logic [2:0] seq_phase_q;
    wire        seq_at_idle_boundary = (seq_phase_q == 3'd0);

    // Внутрішньокристальні лічильники метрології EXP-GPU-02
    logic [31:0] swap_count_q;
    logic [31:0] swap_wait_cur_q;
    logic [31:0] last_swap_wait_cycles_q;
    logic [15:0] seq_exec_cur_q;
    logic [15:0] last_seq_exec_cycles_q;
    logic [15:0] seq_anomaly_count_q;

    assign busy               = seq_busy || sw_trigger || b_we;
    assign hw_pipeline_busy_o = busy;

    // Тіньові записи (0x030, 0x034, 0x038) НЕ входять у cfg_write_fire та НЕ блокують hw_trigger_ready_o
    wire sync_cfg_locked  = busy || swap_pending || sync_busy;
    wire shadow_op_locked = swap_pending || sync_busy || bram_we || shadow_we || swap_req;

    wire cfg_write_fire = write_fire && (write_strb == 4'hf) && !sync_cfg_locked &&
                          ((write_addr == 13'h004) || (write_addr == 13'h008) ||
                           (write_addr == 13'h00c) || (write_addr == 13'h02c));
    wire w1c_clear_overflow = write_fire && (write_strb == 4'hf) && !busy &&
                              (write_addr == 13'h02c) && write_data[16];

    wire ext_trigger_blocked   = sw_trigger || bram_we || cfg_write_fire;
    wire seq_trigger_valid     = sw_trigger || (!ext_trigger_blocked && ext_hw_trigger_valid_i);
    wire [5:0]  seq_trigger_cid   = sw_trigger ? 6'd0 : ext_hw_trigger_cid_i;
    wire [31:0] seq_trigger_param = sw_trigger ? event_param : ext_hw_trigger_param_i;

    assign hw_trigger_ready_o        = seq_trigger_ready && !ext_trigger_blocked;
    assign fifo_overflow_o           = seq_fifo_overflow || axi_sw_overflow_q;
    assign events_dropped_count_o    = seq_dropped_count + axi_sw_dropped_q;
    assign hw_last_committed_state_o = last_state;

    logic [5:0] b_cid_u6;
    always_comb begin
        b_cid_u6 = 6'd0;
        b_cid_u6[ADDR_WIDTH-3:0] = b_addr[ADDR_WIDTH-1:2];
    end
    assign hw_commit_cid_o = b_cid_u6;

    // Стробові виходи протоколу EXP-GPU-02
    assign stimulus_accepted_o = seq_trigger_valid && seq_trigger_ready;
    assign reaction_out_o      = hw_commit_pulse_o;
    assign seq_cycle_done_o    = hw_commit_pulse_o || hw_reject_pulse_o;

    // Мультиплексор Порту A до двобанкової обгортки дескрипторів
    wire ar_fire            = arvalid && arready;
    wire ar_wants_shadow    = (ar_fire && (araddr == 13'h034)) ||
                              (read_pending && (read_addr == 13'h034));
    wire ar_is_bram_read    = (araddr == 13'h008) || (araddr == 13'h034);
    wire port_a_read_free   = !sync_busy && !bram_we && !shadow_we;

    wire                  dual_a_we          = bram_we || shadow_we;
    wire                  dual_a_shadow_only = shadow_we;
    wire                  dual_a_read_shadow = shadow_we ? 1'b1 : (bram_we ? 1'b0 : ar_wants_shadow);
    wire [ADDR_WIDTH-1:0] dual_a_addr        = shadow_we ? shadow_waddr :
                                               (bram_we  ? bram_addr :
                                               (ar_wants_shadow ? shadow_addr : bram_addr));
    wire [31:0]           dual_a_wdata       = shadow_we ? shadow_wdata : bram_wdata;

    km_concept_bram_dual_ha #(
        .NUM_CONCEPTS(NUM_CONCEPTS),
        .DATA_WIDTH(DATA_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) bram_dual (
        .clk(clk),
        .rst_n(rst_n),
        .a_addr_i(dual_a_addr),
        .a_wdata_i(dual_a_wdata),
        .a_wstrb_i(4'hf),
        .a_we_i(dual_a_we),
        .a_shadow_only_i(dual_a_shadow_only),
        .a_read_shadow_i(dual_a_read_shadow),
        .a_rdata_o(bram_a_rdata),
        .swap_req_i(swap_req),
        .seq_at_idle_boundary_i(seq_at_idle_boundary),
        .b_addr_i(b_addr),
        .b_wdata_i(b_wdata),
        .b_wstrb_i(b_wstrb),
        .b_we_i(b_we),
        .b_rdata_o(b_rdata),
        .active_bank_o(active_bank),
        .swap_pending_o(swap_pending),
        .sync_busy_o(sync_busy),
        .inject_strobe_o(inject_strobe_o),
        .bank_swap_commit_o(bank_swap_commit_o),
        .collision_detected_o(collision_detected)
    );

    km_autonomous_sequencer #(
        .QUEUE_DEPTH(QUEUE_DEPTH),
        .NUM_CONCEPTS(NUM_CONCEPTS),
        .DATA_WIDTH(DATA_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) sequencer (
        .clk(clk),
        .rst_n(rst_n),
        .hw_trigger_valid_i(seq_trigger_valid),
        .hw_trigger_cid_i(seq_trigger_cid),
        .hw_trigger_param_i(seq_trigger_param),
        .hw_trigger_ready_o(seq_trigger_ready),
        .bram_b_addr_o(b_addr),
        .bram_b_wdata_o(b_wdata),
        .bram_b_wstrb_o(b_wstrb),
        .bram_b_we_o(b_we),
        .bram_b_rdata_i(b_rdata),
        .clear_overflow_i(w1c_clear_overflow),
        .busy_o(seq_busy),
        .fifo_full_o(seq_fifo_full_unused),
        .fifo_overflow_o(seq_fifo_overflow),
        .events_dropped_count_o(seq_dropped_count),
        .events_processed_count_o(events),
        .committed_count_o(commits),
        .rejected_count_o(rejects),
        .last_committed_state_o(last_state),
        .commit_pulse_o(hw_commit_pulse_o),
        .reject_pulse_o(hw_reject_pulse_o)
    );

    // Розширення адрес до 32 біт для читання регістрів без попереджень про ширину
    logic [31:0] bram_addr_u32;
    logic [31:0] shadow_addr_u32;
    always_comb begin
        bram_addr_u32                 = 32'd0;
        bram_addr_u32[ADDR_WIDTH-1:0] = bram_addr;
        shadow_addr_u32                 = 32'd0;
        shadow_addr_u32[ADDR_WIDTH-1:0] = shadow_addr;
    end

    wire swap_req_will_accept = swap_req && !swap_pending && !sync_busy && !bram_we;

    // Lockstep-детектор стану секвенсера та лічильники метрології EXP-GPU-02
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            seq_phase_q             <= 3'd0;
            swap_count_q            <= 32'd0;
            swap_wait_cur_q         <= 32'd0;
            last_swap_wait_cycles_q <= 32'd0;
            seq_exec_cur_q          <= 16'd0;
            last_seq_exec_cycles_q  <= 16'd0;
            seq_anomaly_count_q     <= 16'd0;
        end else begin
            // 1. Lockstep-детектор фази секвенсера
            if (seq_phase_q == 3'd0) begin
                if (seq_busy) begin
                    seq_phase_q <= 3'd1;
                end
            end else if (seq_phase_q == 3'd7) begin
                seq_phase_q <= 3'd0;
            end else begin
                seq_phase_q <= seq_phase_q + 3'd1;
            end

            // 2. Лічильник виконаних перемикань та тактів очікування межі ST_IDLE
            if ((swap_pending || swap_req_will_accept) && seq_at_idle_boundary) begin
                swap_count_q            <= swap_count_q + 32'd1;
                last_swap_wait_cycles_q <= swap_pending ? (swap_wait_cur_q + 32'd1) : 32'd1;
                swap_wait_cur_q         <= 32'd0;
            end else if (swap_req_will_accept) begin
                swap_wait_cur_q <= 32'd1;
            end else if (swap_pending) begin
                swap_wait_cur_q <= swap_wait_cur_q + 32'd1;
            end

            // 3. Монітор тривалості обслуговування подій секвенсером (норма = 8 тактів)
            if (seq_cycle_done_o) begin
                last_seq_exec_cycles_q <= seq_exec_cur_q + 16'd1;
                if (((seq_exec_cur_q + 16'd1) != 16'd8) && (seq_anomaly_count_q != 16'hffff)) begin
                    seq_anomaly_count_q <= seq_anomaly_count_q + 16'd1;
                end
                seq_exec_cur_q <= 16'd0;
            end else if ((seq_exec_cur_q != 16'd0) || seq_busy) begin
                if (seq_exec_cur_q != 16'hffff) begin
                    seq_exec_cur_q <= seq_exec_cur_q + 16'd1;
                end
            end
        end
    end

    // AXI4-Lite Slave автомат та керування регістрами
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            aw_pending          <= 1'b0;
            w_pending           <= 1'b0;
            awaddr_q            <= 13'd0;
            wdata_q             <= 32'd0;
            wstrb_q             <= 4'd0;
            bresp               <= OKAY;
            bvalid              <= 1'b0;
            rdata               <= 32'd0;
            rresp               <= OKAY;
            rvalid              <= 1'b0;
            read_pending        <= 1'b0;
            read_addr           <= 13'd0;
            read_addr_sampled_q <= 1'b0;

            bram_addr           <= '0;
            bram_wdata          <= 32'd0;
            bram_we             <= 1'b0;
            event_param         <= 32'd0;
            sw_trigger          <= 1'b0;

            shadow_addr         <= '0;
            shadow_waddr        <= '0;
            shadow_wdata        <= 32'd0;
            shadow_we           <= 1'b0;
            swap_req            <= 1'b0;

            ext_sw_stalled_q    <= 1'b0;
            ext_sw_cid_q        <= 6'd0;
            ext_sw_param_q      <= 32'd0;
            axi_sw_overflow_q   <= 1'b0;
            axi_sw_dropped_q    <= 32'd0;
        end else begin
            bram_we    <= 1'b0;
            shadow_we  <= 1'b0;
            swap_req   <= 1'b0;
            sw_trigger <= 1'b0;

            if (w1c_clear_overflow) begin
                axi_sw_overflow_q <= 1'b0;
                axi_sw_dropped_q  <= 32'd0;
                if (ext_hw_trigger_valid_i) begin
                    ext_sw_stalled_q <= 1'b1;
                    ext_sw_cid_q     <= ext_hw_trigger_cid_i;
                    ext_sw_param_q   <= ext_hw_trigger_param_i;
                end else begin
                    ext_sw_stalled_q <= 1'b0;
                end
            end else if (!ext_sw_stalled_q) begin
                if (ext_trigger_blocked && seq_trigger_ready && ext_hw_trigger_valid_i) begin
                    ext_sw_stalled_q <= 1'b1;
                    ext_sw_cid_q     <= ext_hw_trigger_cid_i;
                    ext_sw_param_q   <= ext_hw_trigger_param_i;
                end
            end else begin
                if (!ext_hw_trigger_valid_i) begin
                    axi_sw_overflow_q <= 1'b1;
                    axi_sw_dropped_q  <= axi_sw_dropped_q + 32'd1;
                    ext_sw_stalled_q  <= 1'b0;
                end else if ((ext_hw_trigger_cid_i != ext_sw_cid_q) ||
                             (ext_hw_trigger_param_i != ext_sw_param_q)) begin
                    axi_sw_overflow_q <= 1'b1;
                    axi_sw_dropped_q  <= axi_sw_dropped_q + 32'd1;
                    if (hw_trigger_ready_o) begin
                        ext_sw_stalled_q <= 1'b0;
                    end else begin
                        ext_sw_stalled_q <= 1'b1;
                        ext_sw_cid_q     <= ext_hw_trigger_cid_i;
                        ext_sw_param_q   <= ext_hw_trigger_param_i;
                    end
                end else if (hw_trigger_ready_o) begin
                    ext_sw_stalled_q <= 1'b0;
                end
            end

            if (bvalid && bready) bvalid <= 1'b0;
            if (rvalid && rready) rvalid <= 1'b0;

            if (aw_fire) begin
                awaddr_q   <= awaddr;
                aw_pending <= 1'b1;
            end
            if (w_fire) begin
                wdata_q   <= wdata;
                wstrb_q   <= wstrb;
                w_pending <= 1'b1;
            end
            if (write_fire) begin
                aw_pending <= 1'b0;
                w_pending  <= 1'b0;
                bvalid     <= 1'b1;
                bresp      <= OKAY;
                if (write_strb != 4'hf) begin
                    bresp <= SLVERR;
                end else begin
                    case (write_addr)
                        13'h004: if (sync_cfg_locked) bresp <= SLVERR;
                                 else bram_addr <= write_data[ADDR_WIDTH-1:0];
                        13'h008: if (sync_cfg_locked) bresp <= SLVERR;
                                 else begin
                                     bram_wdata <= write_data;
                                     bram_we    <= 1'b1;
                                 end
                        13'h00c: if (busy) bresp <= SLVERR;
                                 else event_param <= write_data;
                        13'h010: if (busy || bram_we || (write_data != 32'd1)) bresp <= SLVERR;
                                 else sw_trigger <= 1'b1;
                        13'h02c: if (busy) bresp <= SLVERR;
                        13'h030: if (shadow_op_locked) bresp <= SLVERR;
                                 else shadow_addr <= write_data[ADDR_WIDTH-1:0];
                        13'h034: if (shadow_op_locked) bresp <= SLVERR;
                                 else begin
                                     shadow_waddr <= shadow_addr;
                                     shadow_wdata <= write_data;
                                     shadow_we    <= 1'b1;
                                     shadow_addr  <= shadow_addr + {{(ADDR_WIDTH-1){1'b0}}, 1'b1};
                                 end
                        13'h038: if (shadow_op_locked || (write_data != 32'd1)) bresp <= SLVERR;
                                 else swap_req <= 1'b1;
                        default: bresp <= DECERR;
                    endcase
                end
            end

            if (ar_fire) begin
                read_addr           <= araddr;
                read_pending        <= 1'b1;
                read_addr_sampled_q <= !ar_is_bram_read || port_a_read_free;
            end else if (read_pending) begin
                if (!read_addr_sampled_q) begin
                    if (port_a_read_free) begin
                        read_addr_sampled_q <= 1'b1;
                    end
                end else begin
                    read_pending        <= 1'b0;
                    read_addr_sampled_q <= 1'b0;
                    rvalid              <= 1'b1;
                    rresp               <= OKAY;
                    case (read_addr)
                        13'h000: rdata <= 32'h4b504841; // ASCII "KPHA"
                        13'h004: rdata <= bram_addr_u32;
                        13'h008: rdata <= bram_a_rdata;
                        13'h00c: rdata <= event_param;
                        13'h014: rdata <= {31'b0, busy};
                        13'h018: rdata <= events;
                        13'h01c: rdata <= commits;
                        13'h020: rdata <= rejects;
                        13'h024: rdata <= last_state;
                        13'h028: rdata <= events_dropped_count_o;
                        13'h02c: rdata <= {15'b0, fifo_overflow_o, 8'b0, hw_trigger_ready_o, 7'b0};
                        13'h030: rdata <= shadow_addr_u32;
                        13'h034: rdata <= bram_a_rdata;
                        13'h038: rdata <= {28'b0, collision_detected, sync_busy, swap_pending, active_bank};
                        13'h03c: rdata <= swap_count_q;
                        13'h040: rdata <= last_swap_wait_cycles_q;
                        13'h044: rdata <= {seq_anomaly_count_q, last_seq_exec_cycles_q};
                        default: begin
                            rdata <= 32'd0;
                            rresp <= DECERR;
                        end
                    endcase
                end
            end
        end
    end

endmodule
