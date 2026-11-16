// ============================================================================
// Формальна SMT-верифікація CFG-P-HA (B4 Варіант 2, Issue #252, EXP-GPU-02)
// Файл: cfg_p_ha_formal_props.sv
// Солвер: yosys-smtbmc + Z3 (необмежена k-індукція та BMC без вакуумних assume)
//
// Параметри трактованої моделі: NUM_CONCEPTS=4, QUEUE_DEPTH=4, ADDR_WIDTH=4.
// Властивості:
//   - H1_lockstep_phase          : seq_phase_q == sequencer.state_q[2:0]
//   - H2_zero_bram_collision     : collision_detected == 0 на обох банках
//   - H3_no_torn_descriptor_read : W0..W3 оцінюваної події цілісні з одного банку/покоління
//   - H4_zero_sequencer_stall    : кожна подія триває рівно 8 тактів, ready не блокується тіньовим записом
//   - H5_bounded_swap_latency    : bank_swap_commit_o настає за 1..8 тактів після прийнятого swap_req
//   - H6_live_state_preserved    : живий стан W0 зберігається через перемикання банків та досинхронізацію
//   - H7_multi_patch_rule_persistence : правила й стани W0..W3 зберігаються через серію часткових патчів різних концептів
//   - C1..C4 (FORMAL_COVER)      : невакуумні свідки повного циклу інжекції та збігу b_we && bank_swap_commit_o
// ============================================================================
`timescale 1ns/1ps

module cfg_p_ha_formal_props #(
    parameter int NUM_CONCEPTS = 4,
    parameter int QUEUE_DEPTH  = 4,
    parameter int DATA_WIDTH   = 32,
    parameter int ADDR_WIDTH   = 4
)(
    input  logic        clk,
    input  logic        rst_n,

    // Повністю вільні канали AXI4-Lite Slave
    input  logic [12:0] awaddr,
    input  logic        awvalid,
    input  logic [31:0] wdata,
    input  logic [3:0]  wstrb,
    input  logic        wvalid,
    input  logic        bready,
    input  logic [12:0] araddr,
    input  logic        arvalid,
    input  logic        rready,

    // Повністю вільний зовнішній тригер подій
    input  logic        ext_hw_trigger_valid_i,
    input  logic [5:0]  ext_hw_trigger_cid_i,
    input  logic [31:0] ext_hw_trigger_param_i
);

    wire        awready, wready, bvalid, arready, rvalid;
    wire [1:0]  bresp, rresp;
    wire [31:0] rdata;

    wire        hw_trigger_ready_o;
    wire        hw_commit_pulse_o;
    wire        hw_reject_pulse_o;
    wire        hw_pipeline_busy_o;
    wire        fifo_overflow_o;
    wire [31:0] events_dropped_count_o;
    wire [5:0]  hw_commit_cid_o;
    wire [31:0] hw_last_committed_state_o;

`ifdef FORMAL_COVER
    (* keep *) wire inject_strobe_o;
    (* keep *) wire reaction_out_o;
`else
    wire            inject_strobe_o;
    wire            reaction_out_o;
`endif
    (* keep *) wire bank_swap_commit_o;
    wire            stimulus_accepted_o;
    (* keep *) wire seq_cycle_done_o;
    (* keep *) wire busy;

    kpol_bram_pipeline_axi_ha #(
        .NUM_CONCEPTS(NUM_CONCEPTS),
        .QUEUE_DEPTH(QUEUE_DEPTH),
        .DATA_WIDTH(DATA_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .awaddr(awaddr),
        .awvalid(awvalid),
        .awready(awready),
        .wdata(wdata),
        .wstrb(wstrb),
        .wvalid(wvalid),
        .wready(wready),
        .bresp(bresp),
        .bvalid(bvalid),
        .bready(bready),
        .araddr(araddr),
        .arvalid(arvalid),
        .arready(arready),
        .rdata(rdata),
        .rresp(rresp),
        .rvalid(rvalid),
        .rready(rready),
        .ext_hw_trigger_valid_i(ext_hw_trigger_valid_i),
        .ext_hw_trigger_cid_i(ext_hw_trigger_cid_i),
        .ext_hw_trigger_param_i(ext_hw_trigger_param_i),
        .hw_trigger_ready_o(hw_trigger_ready_o),
        .hw_commit_pulse_o(hw_commit_pulse_o),
        .hw_reject_pulse_o(hw_reject_pulse_o),
        .hw_pipeline_busy_o(hw_pipeline_busy_o),
        .fifo_overflow_o(fifo_overflow_o),
        .events_dropped_count_o(events_dropped_count_o),
        .hw_commit_cid_o(hw_commit_cid_o),
        .hw_last_committed_state_o(hw_last_committed_state_o),
        .inject_strobe_o(inject_strobe_o),
        .bank_swap_commit_o(bank_swap_commit_o),
        .stimulus_accepted_o(stimulus_accepted_o),
        .reaction_out_o(reaction_out_o),
        .seq_cycle_done_o(seq_cycle_done_o),
        .busy(busy)
    );

    // Внутрішні спостережні дроти (підключаються через Yosys `connect -set` після flatten + memory_map)
    (* keep *) wire [2:0]  obs_seq_phase_q;
    (* keep *) wire [3:0]  obs_state_q;
    (* keep *) wire [2:0]  obs_fifo_count_q;
    (* keep *) wire [1:0]  obs_fifo_wr_ptr_q;
    (* keep *) wire [1:0]  obs_fifo_rd_ptr_q;
    (* keep *) wire        obs_cascade_pending_valid_q;
    (* keep *) wire        obs_seq_busy;
    (* keep *) wire        obs_seq_trigger_ready;
    (* keep *) wire        obs_sw_trigger;
    (* keep *) wire        obs_bram_we;
    (* keep *) wire        obs_shadow_we;
    (* keep *) wire        obs_cfg_write_fire;

    (* keep *) wire        obs_cme_event_valid;
    (* keep *) wire        obs_cme_committed;
    (* keep *) wire [5:0]  obs_active_cid_q;
    (* keep *) wire [31:0] obs_desc_w0_q;
    (* keep *) wire [31:0] obs_desc_w1_q;
    (* keep *) wire [31:0] obs_desc_w2_q;
    (* keep *) wire [31:0] obs_desc_w3_q;

    (* keep *) wire [3:0]  obs_b_addr;
    (* keep *) wire [31:0] obs_b_wdata;
    (* keep *) wire [3:0]  obs_b_wstrb;
    (* keep *) wire        obs_b_we;
    (* keep *) wire [3:0]  obs_dual_a_addr;
    (* keep *) wire [31:0] obs_dual_a_wdata;

    (* keep *) wire        obs_active_bank;
    (* keep *) wire        obs_swap_pending;
    (* keep *) wire        obs_sync_busy;
    (* keep *) wire [1:0]  obs_sync_state_q;
    (* keep *) wire [3:0]  obs_sync_addr_q;
    (* keep *) wire [15:0] obs_dirty_word_q;
    (* keep *) wire [3:0]  obs_shadow_w0_override_q;
    (* keep *) wire        obs_collision_detected;
    (* keep *) wire        obs_bank0_col;
    (* keep *) wire        obs_bank1_col;
    (* keep *) wire        obs_bank0_a_we;
    (* keep *) wire        obs_bank0_b_we;
    (* keep *) wire [3:0]  obs_bank0_a_addr;
    (* keep *) wire        obs_bank1_a_we;
    (* keep *) wire        obs_bank1_b_we;
    (* keep *) wire [3:0]  obs_bank1_a_addr;
    (* keep *) wire [31:0] obs_bank0_a_rdata;
    (* keep *) wire [31:0] obs_bank1_a_rdata;
    (* keep *) wire [31:0] obs_bank0_b_rdata;
    (* keep *) wire [31:0] obs_bank1_b_rdata;
    (* keep *) wire [31:0] obs_bank0_a_wdata;
    (* keep *) wire [31:0] obs_bank1_a_wdata;

    (* keep *) wire        obs_sync_load_accept;
    (* keep *) wire        obs_hot_write_accept;
    (* keep *) wire        obs_swap_req_accept;
    (* keep *) wire        obs_swap_commit_w;

    (* keep *) wire [31:0] obs_swap_wait_cur_q;
    (* keep *) wire [31:0] obs_last_swap_wait_cycles_q;
    (* keep *) wire [15:0] obs_seq_exec_cur_q;
    (* keep *) wire [15:0] obs_last_seq_exec_cycles_q;
    (* keep *) wire [15:0] obs_seq_anomaly_count_q;

    // Мінімальні зовнішні припущення середовища (жодних припущень на внутрішні стани!)
    wire init_step_w = $initstate;
    logic past_valid = 1'b0;

    always_ff @(posedge clk) begin
        past_valid <= 1'b1;
    end

    always @(*) begin
        if (init_step_w) begin
            assume (!rst_n);
        end else begin
            assume (rst_n);
        end
        assume (ext_hw_trigger_cid_i < NUM_CONCEPTS);
    end

    wire [1:0] act_cid2_w = obs_active_cid_q[1:0];


    (* keep *) wire [31:0] obs_b0_ram_0,  obs_b0_ram_1,  obs_b0_ram_2,  obs_b0_ram_3;
    (* keep *) wire [31:0] obs_b0_ram_4,  obs_b0_ram_5,  obs_b0_ram_6,  obs_b0_ram_7;
    (* keep *) wire [31:0] obs_b0_ram_8,  obs_b0_ram_9,  obs_b0_ram_10, obs_b0_ram_11;
    (* keep *) wire [31:0] obs_b0_ram_12, obs_b0_ram_13, obs_b0_ram_14, obs_b0_ram_15;

    (* keep *) wire [31:0] obs_b1_ram_0,  obs_b1_ram_1,  obs_b1_ram_2,  obs_b1_ram_3;
    (* keep *) wire [31:0] obs_b1_ram_4,  obs_b1_ram_5,  obs_b1_ram_6,  obs_b1_ram_7;
    (* keep *) wire [31:0] obs_b1_ram_8,  obs_b1_ram_9,  obs_b1_ram_10, obs_b1_ram_11;
    (* keep *) wire [31:0] obs_b1_ram_12, obs_b1_ram_13, obs_b1_ram_14, obs_b1_ram_15;

    assign obs_b0_ram_0 = obs_b0_ram_0;  assign obs_b0_ram_1 = obs_b0_ram_1;
    assign obs_b0_ram_2 = obs_b0_ram_2;  assign obs_b0_ram_3 = obs_b0_ram_3;
    assign obs_b0_ram_4 = obs_b0_ram_4;  assign obs_b0_ram_5 = obs_b0_ram_5;
    assign obs_b0_ram_6 = obs_b0_ram_6;  assign obs_b0_ram_7 = obs_b0_ram_7;
    assign obs_b0_ram_8 = obs_b0_ram_8;  assign obs_b0_ram_9 = obs_b0_ram_9;
    assign obs_b0_ram_10 = obs_b0_ram_10; assign obs_b0_ram_11 = obs_b0_ram_11;
    assign obs_b0_ram_12 = obs_b0_ram_12; assign obs_b0_ram_13 = obs_b0_ram_13;
    assign obs_b0_ram_14 = obs_b0_ram_14; assign obs_b0_ram_15 = obs_b0_ram_15;

    assign obs_b1_ram_0 = obs_b1_ram_0;  assign obs_b1_ram_1 = obs_b1_ram_1;
    assign obs_b1_ram_2 = obs_b1_ram_2;  assign obs_b1_ram_3 = obs_b1_ram_3;
    assign obs_b1_ram_4 = obs_b1_ram_4;  assign obs_b1_ram_5 = obs_b1_ram_5;
    assign obs_b1_ram_6 = obs_b1_ram_6;  assign obs_b1_ram_7 = obs_b1_ram_7;
    assign obs_b1_ram_8 = obs_b1_ram_8;  assign obs_b1_ram_9 = obs_b1_ram_9;
    assign obs_b1_ram_10 = obs_b1_ram_10; assign obs_b1_ram_11 = obs_b1_ram_11;
    assign obs_b1_ram_12 = obs_b1_ram_12; assign obs_b1_ram_13 = obs_b1_ram_13;
    assign obs_b1_ram_14 = obs_b1_ram_14; assign obs_b1_ram_15 = obs_b1_ram_15;


    function automatic [31:0] sel_b0(input [3:0] idx);
        case (idx)
            4'd0:  sel_b0 = obs_b0_ram_0;  4'd1:  sel_b0 = obs_b0_ram_1;
            4'd2:  sel_b0 = obs_b0_ram_2;  4'd3:  sel_b0 = obs_b0_ram_3;
            4'd4:  sel_b0 = obs_b0_ram_4;  4'd5:  sel_b0 = obs_b0_ram_5;
            4'd6:  sel_b0 = obs_b0_ram_6;  4'd7:  sel_b0 = obs_b0_ram_7;
            4'd8:  sel_b0 = obs_b0_ram_8;  4'd9:  sel_b0 = obs_b0_ram_9;
            4'd10: sel_b0 = obs_b0_ram_10; 4'd11: sel_b0 = obs_b0_ram_11;
            4'd12: sel_b0 = obs_b0_ram_12; 4'd13: sel_b0 = obs_b0_ram_13;
            4'd14: sel_b0 = obs_b0_ram_14; default: sel_b0 = obs_b0_ram_15;
        endcase
    endfunction

    function automatic [31:0] sel_b1(input [3:0] idx);
        case (idx)
            4'd0:  sel_b1 = obs_b1_ram_0;  4'd1:  sel_b1 = obs_b1_ram_1;
            4'd2:  sel_b1 = obs_b1_ram_2;  4'd3:  sel_b1 = obs_b1_ram_3;
            4'd4:  sel_b1 = obs_b1_ram_4;  4'd5:  sel_b1 = obs_b1_ram_5;
            4'd6:  sel_b1 = obs_b1_ram_6;  4'd7:  sel_b1 = obs_b1_ram_7;
            4'd8:  sel_b1 = obs_b1_ram_8;  4'd9:  sel_b1 = obs_b1_ram_9;
            4'd10: sel_b1 = obs_b1_ram_10; 4'd11: sel_b1 = obs_b1_ram_11;
            4'd12: sel_b1 = obs_b1_ram_12; 4'd13: sel_b1 = obs_b1_ram_13;
            4'd14: sel_b1 = obs_b1_ram_14; default: sel_b1 = obs_b1_ram_15;
        endcase
    endfunction

    wire [31:0] cur_b0_w0 = sel_b0({act_cid2_w, 2'b00});
    wire [31:0] cur_b0_w1 = sel_b0({act_cid2_w, 2'b01});
    wire [31:0] cur_b0_w2 = sel_b0({act_cid2_w, 2'b10});
    wire [31:0] cur_b0_w3 = sel_b0({act_cid2_w, 2'b11});

    wire [31:0] cur_b1_w0 = sel_b1({act_cid2_w, 2'b00});
    wire [31:0] cur_b1_w1 = sel_b1({act_cid2_w, 2'b01});
    wire [31:0] cur_b1_w2 = sel_b1({act_cid2_w, 2'b10});
    wire [31:0] cur_b1_w3 = sel_b1({act_cid2_w, 2'b11});
    wire        snap_cid_match_w = 1'b1;

    // ========================================================================
    // Спостережні еталонні трекери для H3, H4, H5, H6 та Cover
    // ========================================================================

`ifndef ONLY_CTRL
    // 1. Атомарний знімок дескриптора на початку вичитування події (ST_REQ_W0, state_q == 1)
    logic        snap_valid_q = 1'b0;
    logic        snap_bank_q  = 1'b0;
    logic [31:0] snap_act_w0_q = 32'd0;
    logic [31:0] snap_act_w1_q = 32'd0;
    logic [31:0] snap_act_w2_q = 32'd0;
    logic [31:0] snap_act_w3_q = 32'd0;
    logic [95:0] snap_b0_rules_q = 96'd0;
    logic [95:0] snap_b1_rules_q = 96'd0;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            snap_valid_q    <= 1'b0;
            snap_bank_q     <= 1'b0;
            snap_act_w0_q   <= 32'd0;
            snap_act_w1_q   <= 32'd0;
            snap_act_w2_q   <= 32'd0;
            snap_act_w3_q   <= 32'd0;
            snap_b0_rules_q <= 96'd0;
            snap_b1_rules_q <= 96'd0;
        end else if (obs_state_q == 4'd1) begin
            snap_valid_q    <= snap_cid_match_w;
            snap_bank_q     <= obs_active_bank;
            snap_act_w0_q   <= obs_active_bank ? cur_b1_w0 : cur_b0_w0;
            snap_act_w1_q   <= obs_active_bank ? cur_b1_w1 : cur_b0_w1;
            snap_act_w2_q   <= obs_active_bank ? cur_b1_w2 : cur_b0_w2;
            snap_act_w3_q   <= obs_active_bank ? cur_b1_w3 : cur_b0_w3;
            snap_b0_rules_q <= {cur_b0_w3, cur_b0_w2, cur_b0_w1};
            snap_b1_rules_q <= {cur_b1_w3, cur_b1_w2, cur_b1_w1};
        end else if (obs_state_q == 4'd0) begin
            snap_valid_q <= 1'b0;
        end
    end
`endif

`ifdef FORMAL_SAFETY
`ifndef ONLY_H2_H3
    // 2. Незалежні формальні лічильники H4 (тривалість події) та H5 (очікування swap)
    logic [3:0] f_exec_cnt_q  = 4'd0;
    logic [3:0] f_swap_wait_q = 4'd0;
    logic [3:0] f_swap_last_q = 4'd0;
    logic       p_swap_pending = 1'b0;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            f_exec_cnt_q   <= 4'd0;
            f_swap_wait_q  <= 4'd0;
            f_swap_last_q  <= 4'd0;
            p_swap_pending <= 1'b0;
        end else begin
            p_swap_pending <= obs_swap_pending;

            if (seq_cycle_done_o) begin
                f_exec_cnt_q <= 4'd0;
            end else if ((f_exec_cnt_q != 4'd0) || obs_seq_busy) begin
                if (f_exec_cnt_q != 4'hf) begin
                    f_exec_cnt_q <= f_exec_cnt_q + 4'd1;
                end
            end

            if ((obs_swap_pending || obs_swap_req_accept) && (obs_seq_phase_q == 3'd0)) begin
                f_swap_last_q <= obs_swap_pending ? (f_swap_wait_q + 4'd1) : 4'd1;
                f_swap_wait_q <= 4'd0;
            end else if (obs_swap_req_accept) begin
                f_swap_wait_q <= 4'd1;
            end else if (obs_swap_pending) begin
                if (f_swap_wait_q != 4'hf) begin
                    f_swap_wait_q <= f_swap_wait_q + 4'd1;
                end
            end
        end
    end

`ifndef ONLY_CTRL
    // 3. Еталонна архітектурна модель живих станів W0 (H6) та повної таблиці W0..W3 (H7)
    logic [31:0] gold_active_w0    [0:3];
    logic [31:0] gold_staged_w0    [0:3];
    logic [3:0]  gold_has_override;

    logic [31:0] gold_active_ram   [0:15];
    logic [31:0] gold_staged_ram   [0:15];
    logic [15:0] gold_word_staged;

    integer g_idx;
    integer g_w;
    initial begin
        gold_has_override = 4'b0000;
        gold_word_staged  = 16'd0;
        for (g_idx = 0; g_idx < 4; g_idx = g_idx + 1) begin
            gold_active_w0[g_idx] = 32'd0;
            gold_staged_w0[g_idx] = 32'd0;
        end
        for (g_w = 0; g_w < 16; g_w = g_w + 1) begin
            gold_active_ram[g_w] = 32'd0;
            gold_staged_ram[g_w] = 32'd0;
        end
    end

    wire [1:0] dual_a_cid_w = obs_dual_a_addr[3:2];
    wire [1:0] b_cid_w      = obs_b_addr[3:2];

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            gold_has_override <= 4'b0000;
            gold_word_staged  <= 16'd0;
            for (g_idx = 0; g_idx < 4; g_idx = g_idx + 1) begin
                gold_active_w0[g_idx] <= 32'd0;
                gold_staged_w0[g_idx] <= 32'd0;
            end
            for (g_w = 0; g_w < 16; g_w = g_w + 1) begin
                gold_active_ram[g_w] <= 32'd0;
                gold_staged_ram[g_w] <= 32'd0;
            end
        end else if (obs_swap_commit_w) begin
            for (g_idx = 0; g_idx < 4; g_idx = g_idx + 1) begin
                if (gold_has_override[g_idx]) begin
                    gold_active_w0[g_idx] <= gold_staged_w0[g_idx];
                end else if (obs_b_we && (obs_b_addr == {g_idx[1:0], 2'b00})) begin
                    gold_active_w0[g_idx] <= obs_b_wdata;
                end
            end
            for (g_w = 0; g_w < 16; g_w = g_w + 1) begin
                if (gold_word_staged[g_w]) begin
                    gold_active_ram[g_w] <= gold_staged_ram[g_w];
                end else if (obs_b_we && (obs_b_addr == g_w[3:0])) begin
                    gold_active_ram[g_w] <= obs_b_wdata;
                end
            end
            gold_has_override <= 4'b0000;
            gold_word_staged  <= 16'd0;
        end else begin
            if (obs_sync_load_accept) begin
                gold_active_ram[obs_dual_a_addr]  <= obs_dual_a_wdata;
                gold_word_staged[obs_dual_a_addr] <= 1'b0;
                if (obs_dual_a_addr[1:0] == 2'b00) begin
                    gold_active_w0[dual_a_cid_w]    <= obs_dual_a_wdata;
                    gold_has_override[dual_a_cid_w] <= 1'b0;
                end
            end
            if (obs_hot_write_accept) begin
                gold_staged_ram[obs_dual_a_addr]  <= obs_dual_a_wdata;
                gold_word_staged[obs_dual_a_addr] <= 1'b1;
                if (obs_dual_a_addr[1:0] == 2'b00) begin
                    gold_staged_w0[dual_a_cid_w]    <= obs_dual_a_wdata;
                    gold_has_override[dual_a_cid_w] <= 1'b1;
                end
            end
            if (obs_b_we && (obs_b_addr[1:0] == 2'b00)) begin
                gold_active_w0[b_cid_w]     <= obs_b_wdata;
                gold_active_ram[obs_b_addr] <= obs_b_wdata;
            end
        end
    end
`endif
`endif
`endif

`ifdef FORMAL_INDUCTION
    // ========================================================================
    // Допоміжні індуктивні леми досяжного простору станів (ВИКЛЮЧНО assert, 0 assume!)
    // ========================================================================
    wire [1:0] wr_rd_sum_w      = obs_fifo_rd_ptr_q + obs_fifo_count_q[1:0];
    wire [31:0] sync_act_word_w = obs_active_bank ? sel_b1(obs_sync_addr_q) : sel_b0(obs_sync_addr_q);
    wire [31:0] sync_act_rdata_w = obs_active_bank ? obs_bank1_a_rdata : obs_bank0_a_rdata;
    wire [31:0] act_b_rdata_w    = obs_active_bank ? obs_bank1_b_rdata : obs_bank0_b_rdata;
    wire [31:0] cur_act_w0_w     = obs_active_bank ? cur_b1_w0 : cur_b0_w0;
    wire [31:0] cur_act_w1_w     = obs_active_bank ? cur_b1_w1 : cur_b0_w1;
    wire [31:0] cur_act_w2_w     = obs_active_bank ? cur_b1_w2 : cur_b0_w2;
    wire [31:0] cur_act_w3_w     = obs_active_bank ? cur_b1_w3 : cur_b0_w3;

    integer inv_w;
    always @(*) begin
        if (rst_n) begin
            INV_state_range:
                assert (obs_state_q <= 4'd7);
            INV_fifo_count:
                assert (obs_fifo_count_q <= 3'd4);
            INV_fifo_ptrs:
                assert (wr_rd_sum_w == obs_fifo_wr_ptr_q);
            INV_pending_nonempty:
                assert (!obs_cascade_pending_valid_q || ((obs_state_q == 4'd0) && (obs_fifo_count_q == 3'd4)));
            INV_cme_ev_valid:
                assert (obs_cme_event_valid == (obs_state_q == 4'd6));
            INV_cme_mutex:
                assert (!(hw_commit_pulse_o && hw_reject_pulse_o));
            INV_b_we_state:
                assert (!obs_b_we || ((obs_state_q == 4'd0) && (obs_b_addr[1:0] == 2'b00) && (obs_b_wstrb == 4'hf)));
            INV_swap_pulse_after_idle:
                assert (!bank_swap_commit_o || !obs_b_we);
            INV_no_sync_load_busy:
                assert (!(obs_bram_we && busy));
            INV_no_dual_we_overlap:
                assert (!(obs_bram_we && obs_shadow_we));
            INV_b_addr_seq_w0:
                assert ((obs_state_q != 4'd1) || (obs_b_addr == {act_cid2_w, 2'b00}));
            INV_b_addr_seq_w1:
                assert ((obs_state_q != 4'd2) || (obs_b_addr == {act_cid2_w, 2'b01}));
            INV_b_addr_seq_w2:
                assert ((obs_state_q != 4'd3) || (obs_b_addr == {act_cid2_w, 2'b10}));
            INV_b_addr_seq_w3:
                assert ((obs_state_q != 4'd4) || (obs_b_addr == {act_cid2_w, 2'b11}));

            // Покрокові індуктивні леми конвеєра читання дескриптора ST_REQ_W1..ST_WAIT_GATE (H3 за k=2)
            INV_snap_valid_mid_event:
                assert ((obs_state_q < 4'd2) || snap_valid_q);
            INV_active_bank_stable_mid_event:
                assert ((obs_state_q < 4'd2) || (obs_active_bank == snap_bank_q));
            INV_snap_matches_active_ram:
                assert ((obs_state_q < 4'd2) ||
                        ((snap_act_w0_q == cur_act_w0_w) &&
                         (snap_act_w1_q == cur_act_w1_w) &&
                         (snap_act_w2_q == cur_act_w2_w) &&
                         (snap_act_w3_q == cur_act_w3_w) &&
                         ({snap_act_w3_q, snap_act_w2_q, snap_act_w1_q} ==
                          (snap_bank_q ? snap_b1_rules_q : snap_b0_rules_q))));
            INV_pipe_w0_rdata:
                assert ((obs_state_q != 4'd2) || (act_b_rdata_w == snap_act_w0_q));
            INV_pipe_w1_rdata:
                assert ((obs_state_q != 4'd3) || ((obs_desc_w0_q == snap_act_w0_q) && (act_b_rdata_w == snap_act_w1_q)));
            INV_pipe_w2_rdata:
                assert ((obs_state_q != 4'd4) || ((obs_desc_w0_q == snap_act_w0_q) && (obs_desc_w1_q == snap_act_w1_q) && (act_b_rdata_w == snap_act_w2_q)));
            INV_pipe_w3_rdata:
                assert ((obs_state_q != 4'd5) || ((obs_desc_w0_q == snap_act_w0_q) && (obs_desc_w1_q == snap_act_w1_q) && (obs_desc_w2_q == snap_act_w2_q) && (act_b_rdata_w == snap_act_w3_q)));
            INV_pipe_eval_valid:
                assert ((obs_state_q != 4'd6) || ((obs_desc_w0_q == snap_act_w0_q) && (obs_desc_w1_q == snap_act_w1_q) && (obs_desc_w2_q == snap_act_w2_q) && (obs_desc_w3_q == snap_act_w3_q)));

            // Індуктивні інваріанти лічильників H4 та H5
            INV_exec_cnt_lockstep:
                assert ((obs_seq_exec_cur_q == {12'd0, obs_state_q}) && (f_exec_cnt_q == obs_state_q));
            INV_swap_wait_lockstep:
                assert (obs_swap_wait_cur_q == {28'd0, f_swap_wait_q});
            INV_swap_wait_bound:
                assert (obs_swap_pending
                    ? ((f_swap_wait_q >= 4'd1) &&
                       ((obs_state_q == 4'd0) ? (f_swap_wait_q <= 4'd7) : (f_swap_wait_q < obs_state_q)))
                    : (f_swap_wait_q == 4'd0));
            INV_swap_last_bound:
                assert ((f_swap_last_q == 4'd0) || ((f_swap_last_q >= 4'd1) && (f_swap_last_q <= 4'd8)));
            INV_swap_last_match:
                assert (obs_last_swap_wait_cycles_q == {28'd0, f_swap_last_q});

            // Індуктивні інваріанти двобанкової пам'яті та фонової досинхронізації (H6)
            INV_sync_state_valid:
                assert (obs_sync_state_q <= 2'd2);
            INV_sync_not_pending:
                assert (!(obs_sync_busy && obs_swap_pending));
            INV_sync_has_dirty:
                assert (!obs_sync_busy || obs_dirty_word_q[obs_sync_addr_q]);
            INV_sync_no_override:
                assert (!obs_sync_busy || (obs_shadow_w0_override_q == 4'b0000));
            INV_sync_no_staged:
                assert (!obs_sync_busy || (gold_word_staged == 16'd0));
            INV_dirty_eq_staged_when_idle:
                assert (obs_sync_busy || (obs_dirty_word_q == gold_word_staged));
            INV_sync_write_rdata:
                assert ((obs_sync_state_q != 2'd2) || (sync_act_rdata_w == sync_act_word_w));
            INV_gold_override_eq:
                assert (gold_has_override == obs_shadow_w0_override_q);
            INV_live_w0_all_cycles:
                assert (((obs_active_bank ? obs_b1_ram_0 : obs_b0_ram_0) == gold_active_w0[0]) &&
                        ((obs_active_bank ? obs_b1_ram_4 : obs_b0_ram_4) == gold_active_w0[1]) &&
                        ((obs_active_bank ? obs_b1_ram_8 : obs_b0_ram_8) == gold_active_w0[2]) &&
                        ((obs_active_bank ? obs_b1_ram_12 : obs_b0_ram_12) == gold_active_w0[3]));

            for (inv_w = 0; inv_w < 16; inv_w = inv_w + 1) begin
                assert (obs_dirty_word_q[inv_w] || (sel_b0(inv_w[3:0]) == sel_b1(inv_w[3:0])));
                assert (!gold_word_staged[inv_w] ||
                        ((obs_active_bank ? sel_b0(inv_w[3:0]) : sel_b1(inv_w[3:0])) == gold_staged_ram[inv_w]));
                assert ((obs_active_bank ? sel_b1(inv_w[3:0]) : sel_b0(inv_w[3:0])) == gold_active_ram[inv_w]);
            end

            for (inv_w = 0; inv_w < 4; inv_w = inv_w + 1) begin
                assert (obs_sync_busy || (obs_shadow_w0_override_q[inv_w] == obs_dirty_word_q[{inv_w[1:0], 2'b00}]));
                assert (gold_word_staged[{inv_w[1:0], 2'b00}] == obs_shadow_w0_override_q[inv_w]);
                assert (!obs_shadow_w0_override_q[inv_w] ||
                        ((obs_active_bank ? sel_b0({inv_w[1:0], 2'b00}) : sel_b1({inv_w[1:0], 2'b00})) == gold_staged_w0[inv_w]));
            end
        end
    end
`endif

`ifdef FORMAL_SAFETY
    // ========================================================================
    // Основні формальні гіпотези H1 .. H6 (доводяться як BMC, так і k-індукцією)
    // ========================================================================
`ifndef ONLY_H2_H3
`ifndef ONLY_CTRL
    logic seen_b_we_q = 1'b0;
    always_ff @(posedge clk) begin
        if (!rst_n) seen_b_we_q <= 1'b0;
        else if (obs_b_we) seen_b_we_q <= 1'b1;
    end

`ifdef ONLY_H7
    // Спостережний трекер серії двох часткових патчів на різних концептах для контрприкладу M5 (0 assume)
    logic [3:0] cur_patch_cids_q  = 4'b0000;
    logic [3:0] prev_patch_cids_q = 4'b0000;
    logic       seen_distinct_partial_patch_q = 1'b0;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            cur_patch_cids_q              <= 4'b0000;
            prev_patch_cids_q             <= 4'b0000;
            seen_distinct_partial_patch_q <= 1'b0;
        end else if (obs_swap_commit_w) begin
            if ((prev_patch_cids_q != 4'b0000) &&
                (cur_patch_cids_q != 4'b0000) &&
                ((cur_patch_cids_q & prev_patch_cids_q) == 4'b0000)) begin
                seen_distinct_partial_patch_q <= 1'b1;
            end
            prev_patch_cids_q <= cur_patch_cids_q;
            cur_patch_cids_q  <= 4'b0000;
        end else if (obs_hot_write_accept && (obs_dual_a_addr[1:0] != 2'b00)) begin
            cur_patch_cids_q[dual_a_cid_w] <= 1'b1;
        end
    end
`endif
`endif
`endif

`ifndef ONLY_CTRL
    wire [95:0] eval_rules_w = {obs_desc_w3_q, obs_desc_w2_q, obs_desc_w1_q};
    wire [95:0] snap_act_rules_w = {snap_act_w3_q, snap_act_w2_q, snap_act_w1_q};
`endif

    always @(*) begin
        if (rst_n) begin
`ifndef ONLY_H2_H3
`ifndef ONLY_H6
`ifndef ONLY_H7
            // H1: Зовнішній 3-бітний детектор фази секвенсера тотожний внутрішньому стану FSM
            H1_lockstep_phase:
                assert ({1'b0, obs_seq_phase_q} == obs_state_q);
`endif
`endif
`endif

`ifndef ONLY_H6
`ifndef ONLY_H7
            // H2: Нуль колізій портів A/B на обох банках BRAM у будь-якому стані
            H2_zero_bram_collision:
                assert (!obs_collision_detected && !obs_bank0_col && !obs_bank1_col &&
                        !(obs_bank0_a_we && obs_bank0_b_we && (obs_bank0_a_addr == obs_b_addr)) &&
                        !(obs_bank1_a_we && obs_bank1_b_we && (obs_bank1_a_addr == obs_b_addr)));
`endif
`endif

`ifndef ONLY_H6
`ifndef ONLY_H7
`ifndef ONLY_CTRL
            // H3: Відсутність torn-read 128-бітного дескриптора на такті оцінки cme_event_valid
            if (obs_cme_event_valid && snap_valid_q) begin
`ifdef WOLPER_1BIT_SLICE
                H3_no_torn_descriptor_read:
                    assert ((obs_desc_w0_q[0] == snap_act_w0_q[0]) &&
                            (obs_desc_w1_q[0] == snap_act_w1_q[0]) &&
                            (obs_desc_w2_q[0] == snap_act_w2_q[0]) &&
                            (obs_desc_w3_q[0] == snap_act_w3_q[0]) &&
                            (({obs_desc_w3_q[0], obs_desc_w2_q[0], obs_desc_w1_q[0]} ==
                              {snap_b0_rules_q[64], snap_b0_rules_q[32], snap_b0_rules_q[0]}) ||
                             ({obs_desc_w3_q[0], obs_desc_w2_q[0], obs_desc_w1_q[0]} ==
                              {snap_b1_rules_q[64], snap_b1_rules_q[32], snap_b1_rules_q[0]})));
`else
                H3_no_torn_descriptor_read:
                    assert ((obs_desc_w0_q == snap_act_w0_q) &&
                            (eval_rules_w == snap_act_rules_w) &&
                            ((eval_rules_w == snap_b0_rules_q) || (eval_rules_w == snap_b1_rules_q)));
`endif
            end
`endif
`endif
`endif

`ifndef ONLY_H2_H3
`ifndef ONLY_H6
`ifndef ONLY_H7
            // H4: Нульовий простій секвенсера (рівно 8 тактів на подію, ready не блокується тіньовими записами)
            H4_zero_sequencer_stall:
                assert ((obs_seq_anomaly_count_q == 16'd0) &&
                        ((obs_last_seq_exec_cycles_q == 16'd0) || (obs_last_seq_exec_cycles_q == 16'd8)) &&
                        (f_exec_cnt_q <= 4'd7) &&
                        (!seq_cycle_done_o || (f_exec_cnt_q == 4'd7)) &&
                        ((obs_sw_trigger || obs_bram_we || obs_cfg_write_fire) ||
                         (hw_trigger_ready_o == obs_seq_trigger_ready)));

            // H5: Обмежена затримка перемикання активного банку (1..8 тактів від прийняття swap_req)
            H5_bounded_swap_latency:
                assert ((f_swap_wait_q <= 4'd7) &&
                        (!bank_swap_commit_o ||
                         ((f_swap_last_q >= 4'd1) && (f_swap_last_q <= 4'd8) &&
                          (obs_last_swap_wait_cycles_q == {28'd0, f_swap_last_q}))));
`endif
`endif

`ifndef ONLY_CTRL
`ifndef ONLY_H7
            // H6: Повне збереження живих лічильників W0 у всіх концептів після перемикання правил (bank_swap_commit_o)
`ifdef ONLY_H6
            if (bank_swap_commit_o && seen_b_we_q) begin
`else
            if (bank_swap_commit_o) begin
`endif
                H6_live_state_preserved:
                    assert (((obs_active_bank ? obs_b1_ram_0 : obs_b0_ram_0) == gold_active_w0[0]) &&
                            ((obs_active_bank ? obs_b1_ram_4 : obs_b0_ram_4) == gold_active_w0[1]) &&
                            ((obs_active_bank ? obs_b1_ram_8 : obs_b0_ram_8) == gold_active_w0[2]) &&
                            ((obs_active_bank ? obs_b1_ram_12 : obs_b0_ram_12) == gold_active_w0[3]));
            end
`endif

`ifndef ONLY_H6
            // H7: Повне збереження правил і станів W0..W3 усіх концептів після серії часткових патчів (#259, N1)
`ifdef ONLY_H7
            if (bank_swap_commit_o && seen_distinct_partial_patch_q) begin
`else
            if (bank_swap_commit_o) begin
`endif
                H7_multi_patch_rule_persistence:
                    assert (((obs_active_bank ? obs_b1_ram_0  : obs_b0_ram_0)  == gold_active_ram[0])  &&
                            ((obs_active_bank ? obs_b1_ram_1  : obs_b0_ram_1)  == gold_active_ram[1])  &&
                            ((obs_active_bank ? obs_b1_ram_2  : obs_b0_ram_2)  == gold_active_ram[2])  &&
                            ((obs_active_bank ? obs_b1_ram_3  : obs_b0_ram_3)  == gold_active_ram[3])  &&
                            ((obs_active_bank ? obs_b1_ram_4  : obs_b0_ram_4)  == gold_active_ram[4])  &&
                            ((obs_active_bank ? obs_b1_ram_5  : obs_b0_ram_5)  == gold_active_ram[5])  &&
                            ((obs_active_bank ? obs_b1_ram_6  : obs_b0_ram_6)  == gold_active_ram[6])  &&
                            ((obs_active_bank ? obs_b1_ram_7  : obs_b0_ram_7)  == gold_active_ram[7])  &&
                            ((obs_active_bank ? obs_b1_ram_8  : obs_b0_ram_8)  == gold_active_ram[8])  &&
                            ((obs_active_bank ? obs_b1_ram_9  : obs_b0_ram_9)  == gold_active_ram[9])  &&
                            ((obs_active_bank ? obs_b1_ram_10 : obs_b0_ram_10) == gold_active_ram[10]) &&
                            ((obs_active_bank ? obs_b1_ram_11 : obs_b0_ram_11) == gold_active_ram[11]) &&
                            ((obs_active_bank ? obs_b1_ram_12 : obs_b0_ram_12) == gold_active_ram[12]) &&
                            ((obs_active_bank ? obs_b1_ram_13 : obs_b0_ram_13) == gold_active_ram[13]) &&
                            ((obs_active_bank ? obs_b1_ram_14 : obs_b0_ram_14) == gold_active_ram[14]) &&
                            ((obs_active_bank ? obs_b1_ram_15 : obs_b0_ram_15) == gold_active_ram[15]));
            end
`endif
`endif

`ifdef FORMAL_INDUCTION
            // Додатково: повна ідентичність обох банків по завершенні фонової досинхронізації
            if (!obs_sync_busy && !obs_swap_pending && (obs_dirty_word_q == 16'd0)) begin
                H6b_banks_identical_after_resync:
                    assert ((obs_b0_ram_0 == obs_b1_ram_0) && (obs_b0_ram_1 == obs_b1_ram_1) &&
                            (obs_b0_ram_2 == obs_b1_ram_2) && (obs_b0_ram_3 == obs_b1_ram_3) &&
                            (obs_b0_ram_4 == obs_b1_ram_4) && (obs_b0_ram_5 == obs_b1_ram_5) &&
                            (obs_b0_ram_6 == obs_b1_ram_6) && (obs_b0_ram_7 == obs_b1_ram_7) &&
                            (obs_b0_ram_8 == obs_b1_ram_8) && (obs_b0_ram_9 == obs_b1_ram_9) &&
                            (obs_b0_ram_10 == obs_b1_ram_10) && (obs_b0_ram_11 == obs_b1_ram_11) &&
                            (obs_b0_ram_12 == obs_b1_ram_12) && (obs_b0_ram_13 == obs_b1_ram_13) &&
                            (obs_b0_ram_14 == obs_b1_ram_14) && (obs_b0_ram_15 == obs_b1_ram_15));
            end
`endif
`endif
        end
    end
`endif

`ifdef FORMAL_COVER
    // ========================================================================
    // Невакуумні свідки досяжності повного циклу онлайнової інжекції EXP-GPU-02
    // ========================================================================
    logic cov_p_swap_pending       = 1'b0;
    logic cov_s1_old_event_q       = 1'b0;
    logic cov_s2_hot_inject_busy_q = 1'b0;
    logic cov_s3_swap_committed_q  = 1'b0;
    logic cov_s4_resync_started_q  = 1'b0;
    logic cov_s5_resync_done_q     = 1'b0;
    logic cov_s6_new_commit_q      = 1'b0;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            cov_p_swap_pending       <= 1'b0;
            cov_s1_old_event_q       <= 1'b0;
            cov_s2_hot_inject_busy_q <= 1'b0;
            cov_s3_swap_committed_q  <= 1'b0;
            cov_s4_resync_started_q  <= 1'b0;
            cov_s5_resync_done_q     <= 1'b0;
            cov_s6_new_commit_q      <= 1'b0;
        end else begin
            cov_p_swap_pending <= obs_swap_pending;
            if (!obs_active_bank && hw_reject_pulse_o) begin
                cov_s1_old_event_q <= 1'b1;
            end
            if (cov_s1_old_event_q && inject_strobe_o && (obs_state_q != 4'd0)) begin
                cov_s2_hot_inject_busy_q <= 1'b1;
            end
            if (cov_s2_hot_inject_busy_q && bank_swap_commit_o && obs_active_bank) begin
                cov_s3_swap_committed_q <= 1'b1;
            end
            if (cov_s3_swap_committed_q && obs_sync_busy) begin
                cov_s4_resync_started_q <= 1'b1;
            end
            if (cov_s4_resync_started_q && !obs_sync_busy) begin
                cov_s5_resync_done_q <= 1'b1;
            end
            if (cov_s3_swap_committed_q && obs_active_bank && reaction_out_o) begin
                cov_s6_new_commit_q <= 1'b1;
            end
        end
    end

    always @(*) begin
        if (past_valid && rst_n) begin
            C1_full_online_update_lifecycle:
                cover (cov_s5_resync_done_q && cov_s6_new_commit_q && !busy);
            C2_swap_after_pending_wait:
                cover (cov_p_swap_pending && bank_swap_commit_o);
            C3_back_to_back_events_across_swap:
                cover (bank_swap_commit_o && (obs_state_q == 4'd1));
            C4_b_we_at_swap:
                cover (obs_b_we && obs_swap_commit_w);
        end
    end
`endif

endmodule
