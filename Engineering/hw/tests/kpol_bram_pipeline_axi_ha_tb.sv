`timescale 1ns/1ps

// ============================================================================
// Тестбенч: kpol_bram_pipeline_axi_ha_tb.sv
// Призначення: Потактова RTL-симуляція двобанкового ядра CFG-P-HA (B4 Варіант 2,
// Issue #252, EXP-GPU-02):
//   1) Відтворення Фаз 1–4 протоколу EXP-GPU-02 на Концепті 5 (X >= 100 -> X >= 40)
//      під потоком 1 МГц (1 подія / 100 тактів) та 12.5 МГц back-to-back (кожні 8 тактів)
//      зі збереженням компактної траси VCD п'яти стробів RP2040 PIO.
//   2) Стрес-серія з >= 10 000 послідовних гарячих перемикань правил (Bank 0 <-> Bank 1)
//      під безперервним потоком подій з незалежною еталонною моделлю, детектором torn-read,
//      перевіркою SEQ_STALL_CYCLES == 0, LAST_SEQ_EXEC_CYCLES == 8 та collision_detected == 0.
// ============================================================================

module kpol_bram_pipeline_axi_ha_tb;
    logic        clk = 1'b0;
    logic        rst_n = 1'b0;

    // Канали AXI4-Lite Slave
    logic [12:0] awaddr = 13'd0;
    logic        awvalid = 1'b0;
    wire         awready;
    logic [31:0] wdata = 32'd0;
    logic [3:0]  wstrb = 4'hf;
    logic        wvalid = 1'b0;
    wire         wready;
    wire [1:0]   bresp;
    wire         bvalid;
    logic        bready = 1'b0;

    logic [12:0] araddr = 13'd0;
    logic        arvalid = 1'b0;
    wire         arready;
    wire [31:0]  rdata;
    wire [1:0]   rresp;
    wire         rvalid;
    logic        rready = 1'b0;

    // Зовнішній тригер подій
    logic        ext_hw_trigger_valid_i = 1'b0;
    logic [5:0]  ext_hw_trigger_cid_i   = 6'd0;
    logic [31:0] ext_hw_trigger_param_i = 32'd0;
    wire         hw_trigger_ready_o;

    // Базові виходи та діагностичні строби протоколу EXP-GPU-02
    wire         hw_commit_pulse_o;
    wire         hw_reject_pulse_o;
    wire         hw_pipeline_busy_o;
    wire         fifo_overflow_o;
    wire [31:0]  events_dropped_count_o;
    wire [5:0]   hw_commit_cid_o;
    wire [31:0]  hw_last_committed_state_o;

    wire         inject_strobe_o;
    wire         bank_swap_commit_o;
    wire         stimulus_accepted_o;
    wire         reaction_out_o;
    wire         seq_cycle_done_o;
    wire         busy;

    // Канонічні імена 5 цифрових каналів протоколу EXP-GPU-02 для VCD траси
    wire INJECT_STROBE    = inject_strobe_o;
    wire BANK_SWAP_COMMIT = bank_swap_commit_o;
    wire STIMULUS_EVENT   = stimulus_accepted_o;
    wire REACTION_OUT     = reaction_out_o;
    wire SEQ_CYCLE_DONE   = seq_cycle_done_o;

    localparam logic [1:0] OKAY = 2'b00, SLVERR = 2'b10, DECERR = 2'b11;
    // W2 для правила X >= threshold з інкрементом W0: pred=LT(0x04), guard=0x0B (assumption+inv+invert), act=INC(0x01)
    localparam logic [31:0] W2_GE_INC = 32'h01000b04;
    // W2 для правила X == threshold з додаванням operand: pred=EQ(0x01), guard=0x03 (assumption+inv), act=ADD(0x03)
    localparam logic [31:0] W2_EQ_ADD = 32'h03000301;
    // W2 для правила X > threshold з інкрементом W0: pred=GT(0x03), guard=0x03 (assumption+inv), act=INC(0x01)
    localparam logic [31:0] W2_GT_INC = 32'h01000303;

    // 100 МГц тактовий генератор (період = 10 нс)
    always #5 clk = ~clk;

    kpol_bram_pipeline_axi_ha #(
        .NUM_CONCEPTS(64),
        .QUEUE_DEPTH(16),
        .DATA_WIDTH(32),
        .ADDR_WIDTH(8)
    ) dut (.*);

    // ========================================================================
    // Незалежна потактова еталонна модель (Golden Scoreboard) і детектор torn-read
    // ========================================================================
    longint unsigned cycle_counter = 0;
    logic [31:0] gold_cur_w1   [0:63];
    logic [31:0] gold_cur_w2   [0:63];
    logic [31:0] gold_cur_w3   [0:63];
    int unsigned gold_cur_gen  [0:63];

    logic [31:0] gold_stg_w0   [0:63];
    logic        gold_stg_has_w0 [0:63];
    logic [31:0] gold_stg_w1   [0:63];
    logic [31:0] gold_stg_w2   [0:63];
    logic [31:0] gold_stg_w3   [0:63];
    int unsigned gold_stg_gen  [0:63];

    logic [31:0] gold_w0       [0:63];
    int unsigned next_gen_id = 1;

    // Знімок очікуваного дескриптора для активної події секвенсера
    logic        mon_ev_active = 1'b0;
    logic [5:0]  mon_ev_cid    = 6'd0;
    logic [31:0] mon_ev_param  = 32'd0;
    logic [31:0] mon_exp_w0    = 32'd0;
    logic [31:0] mon_exp_w1    = 32'd0;
    logic [31:0] mon_exp_w2    = 32'd0;
    logic [31:0] mon_exp_w3    = 32'd0;
    int unsigned mon_exp_gen   = 0;
    int unsigned mon_ev_cycles = 0;

    // Метрики стрес-серії та протоколу
    int unsigned torn_read_errors      = 0;
    int unsigned golden_mismatch_count = 0;
    int unsigned stall_violation_count = 0;
    int unsigned collision_error_count = 0;
    int unsigned ready_drop_on_shadow  = 0;
    int unsigned total_events_checked  = 0;
    int unsigned total_commits_checked = 0;
    int unsigned total_rejects_checked = 0;
    int unsigned swap_wait_hist [1:8];
    int unsigned min_swap_wait = 999;
    int unsigned max_swap_wait = 0;
    longint unsigned sum_swap_wait = 0;

    task automatic eval_golden_cme(
        input  logic [31:0] w0,
        input  logic [31:0] w1,
        input  logic [31:0] w2,
        input  logic [31:0] param,
        output logic        committed,
        output logic [31:0] updated_w0
    );
        logic [7:0] pred_op;
        logic [7:0] guard_fl;
        logic [7:0] haz_lim;
        logic [7:0] act_op;
        logic       pred_raw;
        logic       act_valid;
        logic       arith_ovf;
        logic [31:0] cand;
        logic       assump_ok, inv_ok, haz_ok;
        begin
            pred_op  = w2[ 7: 0];
            guard_fl = w2[15: 8];
            haz_lim  = w2[23:16];
            act_op   = w2[31:24];

            case (pred_op)
                8'h00: pred_raw = 1'b1;
                8'h01: pred_raw = (param == w1);
                8'h02: pred_raw = (param != w1);
                8'h03: pred_raw = ($signed(param) > $signed(w1));
                8'h04: pred_raw = ($signed(param) < $signed(w1));
                8'h05: pred_raw = ($signed(param) >= $signed({{16{w1[15]}}, w1[15:0]})) &&
                                  ($signed(param) <= $signed({{16{w1[31]}}, w1[31:16]}));
                8'h06: pred_raw = ((param & w1) != 32'd0);
                default: pred_raw = 1'b0;
            endcase

            act_valid = 1'b1;
            arith_ovf = 1'b0;
            case (act_op)
                8'h00: cand = param;
                8'h01: begin
                    cand      = w0 + 32'd1;
                    arith_ovf = (w0 == 32'h7fffffff);
                end
                8'h02: begin
                    cand      = w0 - 32'd1;
                    arith_ovf = (w0 == 32'h80000000);
                end
                8'h03: begin
                    cand      = w0 + w1;
                    arith_ovf = (w0[31] == w1[31]) && (cand[31] != w0[31]);
                end
                8'h04: begin
                    cand      = w0 - w1;
                    arith_ovf = (w0[31] != w1[31]) && (cand[31] != w0[31]);
                end
                default: begin
                    cand      = w0;
                    act_valid = 1'b0;
                end
            endcase

            assump_ok = act_valid && guard_fl[0] && (guard_fl[3] ? ~pred_raw : pred_raw);
            inv_ok    = guard_fl[1] && !arith_ovf && ($signed(cand) >= 0);
            haz_ok    = !(guard_fl[2] && (haz_lim != 8'd0) && ($signed(param) > $signed({24'd0, haz_lim})));

            committed  = assump_ok && inv_ok && haz_ok;
            updated_w0 = committed ? cand : w0;
        end
    endtask

    always @(posedge clk) begin
        if (!rst_n) begin
            cycle_counter <= 0;
            mon_ev_active <= 1'b0;
            mon_ev_cycles <= 0;
        end else begin
            cycle_counter <= cycle_counter + 1;

            // 1. Контроль відсутності колізій BRAM та переповнень черги
            if (dut.collision_detected !== 1'b0) begin
                collision_error_count = collision_error_count + 1;
                $fatal(1, "[FAIL] BRAM port collision detected at cycle %0d", cycle_counter);
            end
            if (fifo_overflow_o !== 1'b0 || events_dropped_count_o !== 32'd0) begin
                $fatal(1, "[FAIL] Unexpected FIFO overflow or dropped event at cycle %0d", cycle_counter);
            end
            if (dut.shadow_we && (dut.sequencer.hw_trigger_ready_o === 1'b1) && (hw_trigger_ready_o !== 1'b1)) begin
                ready_drop_on_shadow = ready_drop_on_shadow + 1;
                $fatal(1, "[FAIL] Shadow write blocked hw_trigger_ready_o at cycle %0d", cycle_counter);
            end

            // 2. Атомарне просування тіньового образу в еталонну активну таблицю у такт BANK_SWAP_COMMIT
            if (bank_swap_commit_o) begin
                for (int c = 0; c < 64; c++) begin
                    gold_cur_w1[c]  = gold_stg_w1[c];
                    gold_cur_w2[c]  = gold_stg_w2[c];
                    gold_cur_w3[c]  = gold_stg_w3[c];
                    gold_cur_gen[c] = gold_stg_gen[c];
                    if (gold_stg_has_w0[c]) begin
                        gold_w0[c]         = gold_stg_w0[c];
                        gold_stg_has_w0[c] = 1'b0;
                    end
                end
            end

            // 3. Відстеження кожної події секвенсера від ST_REQ_W0 (state_q == 1) до SEQ_CYCLE_DONE
            if (dut.sequencer.state_q == 4'd1) begin
                mon_ev_active = 1'b1;
                mon_ev_cid    = dut.sequencer.active_cid_q;
                mon_ev_param  = dut.sequencer.active_param_q;
                mon_exp_w0    = gold_w0[dut.sequencer.active_cid_q];
                mon_exp_w1    = gold_cur_w1[dut.sequencer.active_cid_q];
                mon_exp_w2    = gold_cur_w2[dut.sequencer.active_cid_q];
                mon_exp_w3    = gold_cur_w3[dut.sequencer.active_cid_q];
                mon_exp_gen   = gold_cur_gen[dut.sequencer.active_cid_q];
                mon_ev_cycles = 2; // ST_IDLE(dequeue)=1, ST_REQ_W0=2
            end else if (mon_ev_active) begin
                mon_ev_cycles = mon_ev_cycles + 1;
            end

            if (seq_cycle_done_o) begin
                logic        exp_commit;
                logic [31:0] exp_next_w0;

                if (!mon_ev_active) begin
                    $fatal(1, "[FAIL] seq_cycle_done_o without active monitored event at cycle %0d", cycle_counter);
                end
                if (mon_ev_cycles != 8) begin
                    stall_violation_count = stall_violation_count + 1;
                    $fatal(1, "[FAIL] Event took %0d cycles instead of 8 at cycle %0d", mon_ev_cycles, cycle_counter);
                end

                // Пряма перевірка відсутності torn-read усіх 4 слів 128-бітного дескриптора
                if ((dut.sequencer.desc_w0_q !== mon_exp_w0) ||
                    (dut.sequencer.desc_w1_q !== mon_exp_w1) ||
                    (dut.sequencer.desc_w2_q !== mon_exp_w2) ||
                    (dut.sequencer.desc_w3_q !== mon_exp_w3)) begin
                    torn_read_errors = torn_read_errors + 1;
                    $fatal(1,
                        "[FAIL] TORN-READ at cycle %0d cid=%0d gen=%0d: got {W3..W0}={%08x,%08x,%08x,%08x}, expected {%08x,%08x,%08x,%08x}",
                        cycle_counter, mon_ev_cid, mon_exp_gen,
                        dut.sequencer.desc_w3_q, dut.sequencer.desc_w2_q, dut.sequencer.desc_w1_q, dut.sequencer.desc_w0_q,
                        mon_exp_w3, mon_exp_w2, mon_exp_w1, mon_exp_w0);
                end

                eval_golden_cme(mon_exp_w0, mon_exp_w1, mon_exp_w2, mon_ev_param, exp_commit, exp_next_w0);
                if ((hw_commit_pulse_o !== exp_commit) || (hw_reject_pulse_o !== !exp_commit)) begin
                    golden_mismatch_count = golden_mismatch_count + 1;
                    $fatal(1, "[FAIL] CME commit/reject mismatch at cycle %0d cid=%0d param=%0d",
                           cycle_counter, mon_ev_cid, $signed(mon_ev_param));
                end
                if (exp_commit) begin
                    if (dut.sequencer.cme_updated_state !== exp_next_w0) begin
                        golden_mismatch_count = golden_mismatch_count + 1;
                        $fatal(1, "[FAIL] Updated W0 mismatch at cycle %0d: got %08x expected %08x",
                               cycle_counter, dut.sequencer.cme_updated_state, exp_next_w0);
                    end
                    gold_w0[mon_ev_cid] = exp_next_w0;
                    total_commits_checked = total_commits_checked + 1;
                end else begin
                    total_rejects_checked = total_rejects_checked + 1;
                end

                total_events_checked = total_events_checked + 1;
                mon_ev_active = 1'b0;
            end
        end
    end

    // ========================================================================
    // Базові AXI4-Lite транзакційні процедури
    // ========================================================================
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
        if (bresp !== expected_resp) begin
            $fatal(1, "[FAIL] AXI write 0x%03x resp=%0b expected=%0b at cycle %0d",
                   addr, bresp, expected_resp, cycle_counter);
        end
        @(negedge clk);
        bready = 1'b0;
    endtask

    task automatic axi_read(
        input  [12:0] addr,
        output [31:0] data
    );
        @(negedge clk);
        araddr  = addr;
        arvalid = 1'b1;
        rready  = 1'b1;
        do @(posedge clk); while (!arready);
        @(negedge clk);
        arvalid = 1'b0;
        while (!rvalid) @(negedge clk);
        if (rresp !== OKAY) begin
            $fatal(1, "[FAIL] AXI read 0x%03x resp=%0b at cycle %0d", addr, rresp, cycle_counter);
        end
        data = rdata;
        @(negedge clk);
        rready = 1'b0;
    endtask

    task automatic sync_load_concept(
        input int unsigned cid,
        input logic [31:0] w0,
        input logic [31:0] w1,
        input logic [31:0] w2,
        input logic [31:0] w3
    );
        int unsigned base;
        base = cid * 4;
        axi_write(13'h004, base + 0, 4'hf, OKAY);
        axi_write(13'h008, w0,       4'hf, OKAY);
        axi_write(13'h004, base + 1, 4'hf, OKAY);
        axi_write(13'h008, w1,       4'hf, OKAY);
        axi_write(13'h004, base + 2, 4'hf, OKAY);
        axi_write(13'h008, w2,       4'hf, OKAY);
        axi_write(13'h004, base + 3, 4'hf, OKAY);
        axi_write(13'h008, w3,       4'hf, OKAY);

        gold_w0[cid]         = w0;
        gold_cur_w1[cid]     = w1;
        gold_cur_w2[cid]     = w2;
        gold_cur_w3[cid]     = w3;
        gold_cur_gen[cid]    = 0;
        gold_stg_w0[cid]     = w0;
        gold_stg_has_w0[cid] = 1'b0;
        gold_stg_w1[cid]     = w1;
        gold_stg_w2[cid]     = w2;
        gold_stg_w3[cid]     = w3;
        gold_stg_gen[cid]    = 0;
    endtask

    task automatic wait_shadow_ready();
        logic [31:0] st;
        begin
            st = 32'h6;
            while (st[2] || st[1]) begin
                axi_read(13'h038, st);
            end
        end
    endtask

    task automatic inject_shadow_rules_12b(
        input int unsigned cid,
        input logic [31:0] w1,
        input logic [31:0] w2,
        input logic [31:0] w3
    );
        int unsigned base;
        begin
            wait_shadow_ready();
            base = cid * 4 + 1;
            axi_write(13'h030, base, 4'hf, OKAY);
            axi_write(13'h034, w1,   4'hf, OKAY);
            axi_write(13'h034, w2,   4'hf, OKAY);
            axi_write(13'h034, w3,   4'hf, OKAY);

            gold_stg_w1[cid]  = w1;
            gold_stg_w2[cid]  = w2;
            gold_stg_w3[cid]  = w3;
            gold_stg_gen[cid] = next_gen_id;
            next_gen_id       = next_gen_id + 1;
        end
    endtask

    task automatic inject_shadow_full_16b(
        input int unsigned cid,
        input logic [31:0] w0,
        input logic [31:0] w1,
        input logic [31:0] w2,
        input logic [31:0] w3
    );
        int unsigned base;
        begin
            wait_shadow_ready();
            base = cid * 4;
            axi_write(13'h030, base, 4'hf, OKAY);
            axi_write(13'h034, w0,   4'hf, OKAY);
            axi_write(13'h034, w1,   4'hf, OKAY);
            axi_write(13'h034, w2,   4'hf, OKAY);
            axi_write(13'h034, w3,   4'hf, OKAY);

            gold_stg_w0[cid]     = w0;
            gold_stg_has_w0[cid] = 1'b1;
            gold_stg_w1[cid]     = w1;
            gold_stg_w2[cid]     = w2;
            gold_stg_w3[cid]     = w3;
            gold_stg_gen[cid]    = next_gen_id;
            next_gen_id          = next_gen_id + 1;
        end
    endtask

    task automatic drive_single_ext_event(
        input [5:0]  cid,
        input [31:0] param,
        output int unsigned latency_cycles,
        output logic        did_commit
    );
        longint unsigned t_accept;
        begin
            @(negedge clk);
            ext_hw_trigger_cid_i   = cid;
            ext_hw_trigger_param_i = param;
            ext_hw_trigger_valid_i = 1'b1;
            do @(posedge clk); while (!hw_trigger_ready_o);
            #1;
            t_accept = cycle_counter;
            @(negedge clk);
            ext_hw_trigger_valid_i = 1'b0;
            do @(posedge clk); while (!seq_cycle_done_o);
            did_commit = reaction_out_o;
            #1;
            latency_cycles = int'(cycle_counter - t_accept);
        end
    endtask

    // Потоковий генератор подій для Фаз 2–4 та стрес-серії 10 000 перемикань
    logic        stream_enable     = 1'b0;
    int unsigned stream_period_cyc = 100; // 100 тактів = 1 МГц @ 100 МГц; 8 тактів = 12.5 МГц
    logic        stream_fixed_cid5 = 1'b1;
    logic [31:0] prng_state        = 32'h2520_c0de;

    initial begin : proc_stimulus_stream
        int unsigned gap;
        logic [5:0]  next_cid;
        logic [31:0] next_param;
        int unsigned toggle_idx;
        toggle_idx = 0;
        forever begin
            @(negedge clk);
            if (rst_n && stream_enable) begin
                if (stream_fixed_cid5) begin
                    next_cid   = 6'd5;
                    next_param = (toggle_idx[0] == 1'b0) ? 32'd50 : 32'd120;
                    toggle_idx = toggle_idx + 1;
                end else begin
                    prng_state = (prng_state * 32'd1664525) + 32'd1013904223;
                    next_cid   = {3'b000, prng_state[18:16]}; // CID 0..7
                    next_param = {24'd0, prng_state[15:8]};   // 0..255
                end

                ext_hw_trigger_cid_i   = next_cid;
                ext_hw_trigger_param_i = next_param;
                ext_hw_trigger_valid_i = 1'b1;
                do @(posedge clk); while (!hw_trigger_ready_o);
                @(negedge clk);
                ext_hw_trigger_valid_i = 1'b0;

                if (stream_period_cyc > 1) begin
                    gap = stream_period_cyc - 1;
                    repeat (gap) @(posedge clk);
                end
            end
        end
    end

    // ========================================================================
    // Головний сценарій верифікації EXP-GPU-02 (Фази 1–4 + 10 000 перемикань)
    // ========================================================================
    int unsigned num_swaps_target = 10000;
    string vcd_phases_path = "";
    string timing_csv_path = "";
    string summary_json_path = "";
    integer csv_fd = 0;
    integer json_fd = 0;

    initial begin
        logic [31:0] rd_val, rd_mon, rd_wait, rd_swaps;
        int unsigned lat_cyc;
        logic        committed_flag;
        int unsigned phase2_swap_wait;
        int unsigned phase4_w0_before, phase4_w0_after;
        longint unsigned stress_start_cycle, stress_end_cycle;

        for (int b = 1; b <= 8; b++) swap_wait_hist[b] = 0;
        for (int c = 0; c < 64; c++) begin
            gold_w0[c]         = 32'd0;
            gold_cur_w1[c]     = 32'd0;
            gold_cur_w2[c]     = 32'd0;
            gold_cur_w3[c]     = 32'd0;
            gold_cur_gen[c]    = 0;
            gold_stg_w0[c]     = 32'd0;
            gold_stg_has_w0[c] = 1'b0;
            gold_stg_w1[c]     = 32'd0;
            gold_stg_w2[c]     = 32'd0;
            gold_stg_w3[c]     = 32'd0;
            gold_stg_gen[c]    = 0;
        end

        void'($value$plusargs("num_swaps=%d", num_swaps_target));
        void'($value$plusargs("vcd_phases=%s", vcd_phases_path));
        void'($value$plusargs("timing_csv=%s", timing_csv_path));
        void'($value$plusargs("summary_json=%s", summary_json_path));

        if (vcd_phases_path.len() > 0) begin
            $dumpfile(vcd_phases_path);
            $dumpvars(0,
                clk,
                rst_n,
                INJECT_STROBE,
                BANK_SWAP_COMMIT,
                STIMULUS_EVENT,
                REACTION_OUT,
                SEQ_CYCLE_DONE,
                ext_hw_trigger_valid_i,
                ext_hw_trigger_cid_i,
                ext_hw_trigger_param_i,
                hw_trigger_ready_o,
                busy,
                dut.active_bank,
                dut.swap_pending,
                dut.sync_busy,
                dut.seq_phase_q,
                dut.swap_count_q,
                dut.last_swap_wait_cycles_q,
                dut.last_seq_exec_cycles_q,
                dut.seq_anomaly_count_q
            );
        end

        if (timing_csv_path.len() > 0) begin
            csv_fd = $fopen(timing_csv_path, "w");
            if (csv_fd == 0) $fatal(1, "[FAIL] Cannot open timing CSV: %s", timing_csv_path);
            $fdisplay(csv_fd, "evidence_kind,phase,swap_index,cid,patch_bytes,active_bank_after,swap_wait_cycles,last_seq_exec_cycles,seq_anomaly_count,total_events,total_commits,total_rejects");
        end

        // Скидання ядра
        rst_n = 1'b0;
        repeat (5) @(posedge clk);
        rst_n = 1'b1;
        repeat (2) @(posedge clk);

        // Перевірка ідентифікатора ядра CFG-P-HA ("KPHA" = 0x4b504841)
        axi_read(13'h000, rd_val);
        if (rd_val !== 32'h4b504841) begin
            $fatal(1, "[FAIL] Unexpected CORE_ID: 0x%08x != 0x4b504841", rd_val);
        end

        // Ініціалізація концептів 0..7 у фазі PHASE_LOAD (!busy)
        for (int c = 0; c < 8; c++) begin
            if (c == 5) begin
                // Концепт 5 за протоколом EXP-GPU-02 Фаза 1: X >= 100, INC
                sync_load_concept(5, 32'd0, 32'd100, W2_GE_INC, 32'hffffffff);
            end else begin
                sync_load_concept(c, 32'd0, 32'd80 + c * 10, W2_GE_INC, 32'hffffffff);
            end
        end

        // Перевірка початкової ідентичності активного (0x008) і тіньового (0x034) банків на CID=5
        for (int w = 20; w < 24; w++) begin
            logic [31:0] v_act, v_sh;
            axi_write(13'h004, w, 4'hf, OKAY);
            axi_read(13'h008, v_act);
            axi_write(13'h030, w, 4'hf, OKAY);
            axi_read(13'h034, v_sh);
            if (v_act !== v_sh) begin
                $fatal(1, "[FAIL] Initial dual-bank mismatch at word %0d: %08x != %08x", w, v_act, v_sh);
            end
        end

        // ====================================================================
        // ФАЗА 1 (EXP-GPU-02): Калібрування Bank 0 на CID=5 (X >= 100)
        // ====================================================================
        drive_single_ext_event(6'd5, 32'd50, lat_cyc, committed_flag);
        if (committed_flag !== 1'b0 || lat_cyc != 8 || gold_w0[5] != 32'd0) begin
            $fatal(1, "[FAIL] Phase 1 (X=50): committed=%0b lat=%0d w0=%0d", committed_flag, lat_cyc, gold_w0[5]);
        end

        drive_single_ext_event(6'd5, 32'd120, lat_cyc, committed_flag);
        if (committed_flag !== 1'b1 || lat_cyc != 8 || gold_w0[5] != 32'd1) begin
            $fatal(1, "[FAIL] Phase 1 (X=120): committed=%0b lat=%0d w0=%0d", committed_flag, lat_cyc, gold_w0[5]);
        end
        if (csv_fd != 0) begin
            $fdisplay(csv_fd, "rtl_simulation_iverilog,phase1_calibration,0,5,0,0,0,8,0,%0d,%0d,%0d",
                      total_events_checked, total_commits_checked, total_rejects_checked);
        end

        // ====================================================================
        // ФАЗИ 2–3 (EXP-GPU-02): Безперервний потік 1 МГц (1 подія / 100 тактів)
        // + гаряча інжекція X >= 40 у Bank 1 під час активного секвенсера
        // ====================================================================
        stream_fixed_cid5 = 1'b1;
        stream_period_cyc = 100;
        stream_enable     = 1'b1;

        // Дочекаємось кількох подій потоку 1 МГц
        repeat (220) @(posedge clk);

        // Негативний контроль під час busy == 1: прямий запис у 0x008 та частковий строб повертають SLVERR
        wait (busy == 1'b1);
        axi_write(13'h008, 32'hdeadbeef, 4'hf, SLVERR);
        axi_write(13'h030, 32'd21,       4'h3, SLVERR);

        // Записуємо нове правило CID=5 (X >= 40) у тіньовий банк під час потоку 1 МГц
        inject_shadow_rules_12b(5, 32'd40, W2_GE_INC, 32'hffffffff);

        // Подаємо запит перемикання точно посеред активного циклу секвенсера (seq_phase_q == 2)
        wait (dut.seq_phase_q == 3'd2);
        axi_write(13'h038, 32'd1, 4'hf, OKAY);

        // Негативний контроль: під час swap_pending / sync_busy повторний запис у 0x034 повертає SLVERR
        if (dut.swap_pending || dut.sync_busy) begin
            axi_write(13'h034, 32'h12345678, 4'hf, SLVERR);
        end

        wait_shadow_ready();
        axi_read(13'h038, rd_val);
        axi_read(13'h03c, rd_swaps);
        axi_read(13'h040, rd_wait);
        axi_read(13'h044, rd_mon);
        phase2_swap_wait = rd_wait;

        if (rd_val[0] !== 1'b1 || rd_swaps != 32'd1 || rd_wait < 1 || rd_wait > 8 || rd_mon != 32'h0000_0008) begin
            $fatal(1, "[FAIL] Phase 2-3 swap telemetry unexpected: st=%08x swaps=%0d wait=%0d mon=%08x",
                   rd_val, rd_swaps, rd_wait, rd_mon);
        end
        if (csv_fd != 0) begin
            $fdisplay(csv_fd, "rtl_simulation_iverilog,phase2_3_hot_swap_1mhz,1,5,12,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
                      rd_val[0], rd_wait, rd_mon[15:0], rd_mon[31:16],
                      total_events_checked, total_commits_checked, total_rejects_checked);
        end

        // ====================================================================
        // ФАЗА 4 (EXP-GPU-02): Перевірка негайного спрацьовування X=50 за 8 тактів
        // зі збереженням накопиченого живого лічильника W0 + back-to-back 12.5 МГц
        // ====================================================================
        stream_enable = 1'b0;
        wait (!busy);
        repeat (2) @(posedge clk);

        phase4_w0_before = gold_w0[5];
        drive_single_ext_event(6'd5, 32'd50, lat_cyc, committed_flag);
        phase4_w0_after  = gold_w0[5];
        if (committed_flag !== 1'b1 || lat_cyc != 8 || (phase4_w0_after != phase4_w0_before + 1) || phase4_w0_before < 1) begin
            $fatal(1, "[FAIL] Phase 4 (X=50 post-swap): committed=%0b lat=%0d w0=%0d->%0d",
                   committed_flag, lat_cyc, phase4_w0_before, phase4_w0_after);
        end

        // Щільний стрес-потік back-to-back кожні 8 тактів (12.5 МГц) через ще 2 перемикання на CID=5
        stream_fixed_cid5 = 1'b1;
        stream_period_cyc = 8;
        stream_enable     = 1'b1;
        repeat (40) @(posedge clk);

        inject_shadow_rules_12b(5, 32'd90, W2_GE_INC, 32'hffffffff);
        axi_write(13'h038, 32'd1, 4'hf, OKAY);
        wait_shadow_ready();
        axi_read(13'h040, rd_wait);
        axi_read(13'h044, rd_mon);
        if (csv_fd != 0) begin
            $fdisplay(csv_fd, "rtl_simulation_iverilog,phase4_back_to_back_12p5mhz_swapA,2,5,12,0,%0d,%0d,%0d,%0d,%0d,%0d",
                      rd_wait, rd_mon[15:0], rd_mon[31:16],
                      total_events_checked, total_commits_checked, total_rejects_checked);
        end

        repeat (32) @(posedge clk);
        inject_shadow_rules_12b(5, 32'd40, W2_GE_INC, 32'hffffffff);
        axi_write(13'h038, 32'd1, 4'hf, OKAY);
        wait_shadow_ready();
        axi_read(13'h040, rd_wait);
        axi_read(13'h044, rd_mon);
        if (csv_fd != 0) begin
            $fdisplay(csv_fd, "rtl_simulation_iverilog,phase4_back_to_back_12p5mhz_swapB,3,5,12,1,%0d,%0d,%0d,%0d,%0d,%0d",
                      rd_wait, rd_mon[15:0], rd_mon[31:16],
                      total_events_checked, total_commits_checked, total_rejects_checked);
        end

        stream_enable = 1'b0;
        wait (!busy);
        repeat (4) @(posedge clk);

        // Завершуємо запис компактної VCD-траси Фаз 1–4 перед 10 000 перемиканнями
        if (vcd_phases_path.len() > 0) begin
            $dumpoff;
        end

        // ====================================================================
        // СТРЕС-СЕРІЯ: num_swaps_target (10 000) послідовних перемикань Bank 0 <-> Bank 1
        // під безперервним змішаним потоком подій (8..100 тактів, CID 0..7)
        // ====================================================================
        stream_fixed_cid5  = 1'b0;
        stream_period_cyc  = 8;
        stream_enable      = 1'b1;
        stress_start_cycle = cycle_counter;

        for (int unsigned sw = 1; sw <= num_swaps_target; sw++) begin
            int unsigned target_cid;
            logic [31:0] new_thresh;
            logic [31:0] new_w2;
            int unsigned patch_sz;

            // Чергуємо щільність потоку подій між back-to-back 12.5 МГц (8 тактів), 5 МГц (20 тактів) та 1 МГц (100 тактів)
            if ((sw % 16) < 10)      stream_period_cyc = 8;
            else if ((sw % 16) < 14) stream_period_cyc = 16;
            else                     stream_period_cyc = 100;

            target_cid = sw % 8;
            new_thresh = 32'd20 + ((sw * 17) % 180);
            new_w2     = ((sw % 3) == 0) ? W2_GT_INC : W2_GE_INC;

            if ((sw % 10) == 0) begin
                // Кожне 10-те оновлення — повний 16-байтний дескриптор із явним W0 override
                inject_shadow_full_16b(target_cid, 32'd10 + (sw % 50), new_thresh, new_w2, 32'hffffffff);
                patch_sz = 16;
            end else begin
                // 90% оновлень — 12-байтні правила W1..W3 зі збереженням живого лічильника W0
                inject_shadow_rules_12b(target_cid, new_thresh, new_w2, 32'hffffffff);
                patch_sz = 12;
            end

            // Зсув фази запиту swap відносно 8-тактового секвенсера для рівномірного покриття всіх 8 фаз
            repeat (sw % 8) @(posedge clk);
            axi_write(13'h038, 32'd1, 4'hf, OKAY);
            wait_shadow_ready();

            axi_read(13'h038, rd_val);
            axi_read(13'h040, rd_wait);
            axi_read(13'h044, rd_mon);

            if (rd_wait < 1 || rd_wait > 8) begin
                $fatal(1, "[FAIL] Swap #%0d wait out of bounds [1..8]: %0d", sw, rd_wait);
            end
            if (rd_mon[31:16] != 16'd0 || rd_mon[15:0] != 16'd8) begin
                $fatal(1, "[FAIL] Swap #%0d sequencer exec anomaly: 0x%08x", sw, rd_mon);
            end

            swap_wait_hist[rd_wait] = swap_wait_hist[rd_wait] + 1;
            if (rd_wait < min_swap_wait) min_swap_wait = rd_wait;
            if (rd_wait > max_swap_wait) max_swap_wait = rd_wait;
            sum_swap_wait = sum_swap_wait + rd_wait;

            if ((csv_fd != 0) && ((sw <= 20) || ((sw % 500) == 0) || (sw == num_swaps_target))) begin
                $fdisplay(csv_fd, "rtl_simulation_iverilog,stress_10k_series,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
                          sw + 3, target_cid, patch_sz, rd_val[0], rd_wait,
                          rd_mon[15:0], rd_mon[31:16],
                          total_events_checked, total_commits_checked, total_rejects_checked);
            end
        end

        stress_end_cycle = cycle_counter;
        stream_enable    = 1'b0;
        wait (!busy);
        wait_shadow_ready();
        repeat (4) @(posedge clk);

        // Фінальна побітова звірка всіх 256 слів обох банків (bank0 == bank1 == golden)
        axi_read(13'h03c, rd_swaps);
        if (rd_swaps != (num_swaps_target + 3)) begin
            $fatal(1, "[FAIL] Final SWAP_COUNT=%0d expected=%0d", rd_swaps, num_swaps_target + 3);
        end

        for (int c = 0; c < 64; c++) begin
            int unsigned base;
            logic [31:0] exp_words [0:3];
            base = c * 4;
            exp_words[0] = gold_w0[c];
            exp_words[1] = gold_cur_w1[c];
            exp_words[2] = gold_cur_w2[c];
            exp_words[3] = gold_cur_w3[c];

            for (int off = 0; off < 4; off++) begin
                logic [31:0] act_w, sh_w;
                axi_write(13'h004, base + off, 4'hf, OKAY);
                axi_read(13'h008, act_w);
                axi_write(13'h030, base + off, 4'hf, OKAY);
                axi_read(13'h034, sh_w);
                if ((act_w !== sh_w) || (act_w !== exp_words[off])) begin
                    $fatal(1, "[FAIL] Post-resync mismatch at word %0d (cid=%0d off=%0d): act=%08x sh=%08x exp=%08x",
                           base + off, c, off, act_w, sh_w, exp_words[off]);
                end
            end
        end

        if (csv_fd != 0) begin
            $fclose(csv_fd);
        end

        if (summary_json_path.len() > 0) begin
            json_fd = $fopen(summary_json_path, "w");
            if (json_fd == 0) $fatal(1, "[FAIL] Cannot open summary JSON: %s", summary_json_path);
            $fdisplay(json_fd, "{");
            $fdisplay(json_fd, "  \"evidence_kind\": \"rtl_simulation_iverilog\",");
            $fdisplay(json_fd, "  \"not_physical_hil\": true,");
            $fdisplay(json_fd, "  \"issue\": 252,");
            $fdisplay(json_fd, "  \"experiment\": \"EXP-GPU-02\",");
            $fdisplay(json_fd, "  \"dut\": \"kpol_bram_pipeline_axi_ha\",");
            $fdisplay(json_fd, "  \"clock_mhz_nominal\": 100.0,");
            $fdisplay(json_fd, "  \"phases_1_4_swaps\": 3,");
            $fdisplay(json_fd, "  \"stress_swaps\": %0d,", num_swaps_target);
            $fdisplay(json_fd, "  \"total_bank_swaps\": %0d,", rd_swaps);
            $fdisplay(json_fd, "  \"total_sim_cycles\": %0d,", cycle_counter);
            $fdisplay(json_fd, "  \"stress_window_cycles\": %0d,", stress_end_cycle - stress_start_cycle);
            $fdisplay(json_fd, "  \"total_events_evaluated\": %0d,", total_events_checked);
            $fdisplay(json_fd, "  \"total_committed_events\": %0d,", total_commits_checked);
            $fdisplay(json_fd, "  \"total_rejected_events\": %0d,", total_rejects_checked);
            $fdisplay(json_fd, "  \"torn_read_errors\": %0d,", torn_read_errors);
            $fdisplay(json_fd, "  \"golden_mismatch_count\": %0d,", golden_mismatch_count);
            $fdisplay(json_fd, "  \"seq_stall_anomaly_count\": %0d,", stall_violation_count);
            $fdisplay(json_fd, "  \"bram_collision_count\": %0d,", collision_error_count);
            $fdisplay(json_fd, "  \"ready_drop_on_shadow_count\": %0d,", ready_drop_on_shadow);
            $fdisplay(json_fd, "  \"events_dropped_count\": %0d,", events_dropped_count_o);
            $fdisplay(json_fd, "  \"last_seq_exec_cycles\": 8,");
            $fdisplay(json_fd, "  \"phase2_1mhz_swap_wait_cycles\": %0d,", phase2_swap_wait);
            $fdisplay(json_fd, "  \"stress_swap_wait_min_cycles\": %0d,", min_swap_wait);
            $fdisplay(json_fd, "  \"stress_swap_wait_max_cycles\": %0d,", max_swap_wait);
            $fdisplay(json_fd, "  \"stress_swap_wait_sum_cycles\": %0d,", sum_swap_wait);
            $fdisplay(json_fd, "  \"stress_swap_wait_histogram_cycles\": {");
            $fdisplay(json_fd, "    \"1\": %0d, \"2\": %0d, \"3\": %0d, \"4\": %0d,",
                      swap_wait_hist[1], swap_wait_hist[2], swap_wait_hist[3], swap_wait_hist[4]);
            $fdisplay(json_fd, "    \"5\": %0d, \"6\": %0d, \"7\": %0d, \"8\": %0d",
                      swap_wait_hist[5], swap_wait_hist[6], swap_wait_hist[7], swap_wait_hist[8]);
            $fdisplay(json_fd, "  },");
            $fdisplay(json_fd, "  \"phase4_cid5_w0_before_x50\": %0d,", phase4_w0_before);
            $fdisplay(json_fd, "  \"phase4_cid5_w0_after_x50\": %0d,", phase4_w0_after);
            $fdisplay(json_fd, "  \"verdict\": \"PASS\"");
            $fdisplay(json_fd, "}");
            $fclose(json_fd);
        end

        $display("PASS: CFG-P-HA EXP-GPU-02 Phases 1-4 and %0d hot bank swaps verified (%0d events, 0 torn-reads, 0 stalls, 0 collisions)",
                 num_swaps_target, total_events_checked);
        $finish;
    end

endmodule
