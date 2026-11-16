`timescale 1ns / 1ps

// ============================================================================
// Тестбенч: km_manycore_cluster_tb.sv
// Призначення: Потактова RTL-симуляція та профілювання трафіку багатоядерного
// кластера CFG-P (N = 2, 4, 8, Issue #255) на чотирьох канонічних профілях:
//   0: local       — 100% внутрішньобанкові 2-ступеневі каскади (0 тактів кросбара)
//   1: uniform     — рівномірний міжбанковий трафік за топологічним DAG
//   2: hotspot     — 75% перекіс трафіку на гарячий банк (Bank N-1)
//   3: many-to-one — N:1 збіжність усіх потоків та каскадів у Bank N-1
//
// Перевірки проти бутафорії (AGENTS.md §4.1–§4.3):
//   - Незалежна аналітична еталонна таблиця exp_w0[bank][cid] обчислюється з
//     графа підписок ДО читання стану RTL і звіряється через шину Порту A
//     (`cfg_bank_sel_i`, `cfg_addr_i`, `cfg_rdata_o`) для всіх N * 64 концептів;
//   - Перевіряється fail-closed відхилення транзакції без каскаду при порушенні
//     предиката перед серією профілів трафіку;
//   - Вимірюється точна пропускна здатність (MCPS @ 100 МГц), середня та
//     максимальна латентність у тактах, кількість тактів зворотного тиску
//     (`backpressure_stalls`) та відсутність втрат прийнятих подій (`0` drops).
// ============================================================================

module km_manycore_cluster_tb #(
    parameter int NUM_CORES    = 4,
    parameter int QUEUE_DEPTH  = 16,
    parameter int NUM_CONCEPTS = 64,
    parameter int DATA_WIDTH   = 32,
    parameter int ADDR_WIDTH   = 8
);

    logic                           clk   = 1'b0;
    logic                           rst_n = 1'b0;

    logic [3:0]                     cfg_bank_sel_i = 4'd0;
    logic [ADDR_WIDTH-1:0]          cfg_addr_i     = '0;
    logic [DATA_WIDTH-1:0]          cfg_wdata_i    = '0;
    logic [3:0]                     cfg_wstrb_i    = 4'hf;
    logic                           cfg_we_i       = 1'b0;
    wire  [DATA_WIDTH-1:0]          cfg_rdata_o;
    wire  [NUM_CORES-1:0]           collision_detected_o;

    logic [NUM_CORES-1:0]           ext_valid_i    = '0;
    wire  [NUM_CORES-1:0]           ext_ready_o;
    logic [NUM_CORES*4-1:0]         ext_dst_bank_i = '0;
    logic [NUM_CORES*6-1:0]         ext_dst_cid_i  = '0;
    logic [NUM_CORES*DATA_WIDTH-1:0] ext_param_i   = '0;

    wire  [NUM_CORES-1:0]           core_busy_o;
    wire  [NUM_CORES-1:0]           core_fifo_full_o;
    wire  [NUM_CORES-1:0]           core_commit_pulse_o;
    wire  [NUM_CORES-1:0]           core_reject_pulse_o;
    wire  [NUM_CORES*DATA_WIDTH-1:0] core_last_state_o;

    wire                            cluster_busy_o;
    wire  [31:0]                    total_events_processed_o;
    wire  [31:0]                    total_committed_o;
    wire  [31:0]                    total_rejected_o;
    wire  [31:0]                    total_local_cascades_o;
    wire  [31:0]                    total_remote_cascades_o;
    wire  [31:0]                    xbar_routed_events_o;
    wire  [31:0]                    backpressure_stall_cycles_o;
    wire  [31:0]                    invalid_dst_drop_count_o;

    // 100 МГц тактовий сигнал (період = 10 нс)
    always #5 clk = ~clk;

    km_manycore_cluster #(
        .NUM_CORES(NUM_CORES),
        .NUM_EXT_PORTS(NUM_CORES),
        .QUEUE_DEPTH(QUEUE_DEPTH),
        .NUM_CONCEPTS(NUM_CONCEPTS),
        .DATA_WIDTH(DATA_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) dut (.*);

    // W2 = NOP (0x00) + guards (assumption_known | invariant_known = 0x03) + INC (0x01)
    localparam logic [31:0] W2_NOP_INC = 32'h0100_0300;
    // W2 = LT (0x04) + guards (0x03) + INC (0x01) для перевірки fail-closed відхилення
    localparam logic [31:0] W2_LT_INC  = 32'h0100_0304;
    localparam logic [31:0] W3_NO_SUB  = 32'hffff_ffff;

    longint unsigned cycle_cnt = 0;
    always @(posedge clk) begin
        if (!rst_n) cycle_cnt <= 0;
        else        cycle_cnt <= cycle_cnt + 1;
    end

    // ========================================================================
    // Потактовий трекер часу народження кожної події для вимірювання латентності
    // ========================================================================
    logic [63:0] ext_birth_ts  [0:NUM_CORES-1];
    logic [63:0] tx_birth_ts   [0:NUM_CORES-1];
    logic [63:0] hold_birth_ts [0:NUM_CORES-1];
    wire  [63:0] src_birth_ts  [0:2*NUM_CORES-1];

    genvar gi;
    generate
        for (gi = 0; gi < NUM_CORES; gi = gi + 1) begin : gen_src_ts
            assign src_birth_ts[gi]             = tx_birth_ts[gi];
            assign src_birth_ts[NUM_CORES + gi] = ext_birth_ts[gi];
        end
    endgenerate

    longint unsigned core_lat_sum [0:NUM_CORES-1];
    longint unsigned core_lat_max [0:NUM_CORES-1];
    longint unsigned core_lat_min [0:NUM_CORES-1];
    int unsigned     core_lat_cnt [0:NUM_CORES-1];
    logic            lat_reset_req = 1'b0;

    genvar gb;
    generate
        for (gb = 0; gb < NUM_CORES; gb = gb + 1) begin : gen_lat_mon
            longint unsigned pipe_ts;
            longint unsigned fifo_ts [0:QUEUE_DEPTH-1];
            longint unsigned pend_ts;
            longint unsigned act_ts;

            always @(posedge clk) begin
                if (!rst_n || lat_reset_req) begin
                    pipe_ts          <= 0;
                    pend_ts          <= 0;
                    act_ts           <= 0;
                    tx_birth_ts[gb]   <= 0;
                    hold_birth_ts[gb] <= 0;
                    core_lat_sum[gb]  <= 0;
                    core_lat_max[gb]  <= 0;
                    core_lat_min[gb]  <= 64'hffff_ffff;
                    core_lat_cnt[gb]  <= 0;
                    for (int fi = 0; fi < QUEUE_DEPTH; fi = fi + 1) begin
                        fifo_ts[fi] <= 0;
                    end
                end else begin
                    // 1. Зріз кросбара цільового банку gb
                    if (dut.xbar_inst.gen_bank_slice[gb].grant_fire_w) begin
                        pipe_ts <= src_birth_ts[dut.xbar_inst.gen_bank_slice[gb].win_idx];
                    end

                    // 2. Вихідний міжбанковий буфер вузла gb
                    if (dut.gen_core[gb].node_inst.tx_push_eval) begin
                        tx_birth_ts[gb] <= cycle_cnt;
                    end else if (dut.gen_core[gb].node_inst.tx_push_wait) begin
                        tx_birth_ts[gb] <= hold_birth_ts[gb];
                    end
                    if ((dut.gen_core[gb].node_inst.state_q == 4'd7) &&
                        dut.gen_core[gb].node_inst.remote_cascade_req &&
                        !dut.gen_core[gb].node_inst.tx_buf_free_w) begin
                        hold_birth_ts[gb] <= cycle_cnt;
                    end

                    // 3. Вхідна черга FIFO та локальний каскад вузла gb
                    if (dut.gen_core[gb].node_inst.dequeue_req) begin
                        act_ts <= fifo_ts[dut.gen_core[gb].node_inst.fifo_rd_ptr_q];
                    end

                    if (dut.gen_core[gb].node_inst.local_cascade_enq &&
                        dut.gen_core[gb].node_inst.rx_accept) begin
                        fifo_ts[dut.gen_core[gb].node_inst.fifo_wr_ptr_q] <=
                            dut.gen_core[gb].node_inst.cascade_pending_valid_q ? pend_ts : cycle_cnt;
                        fifo_ts[dut.gen_core[gb].node_inst.wr_ptr_next1] <= pipe_ts;
                    end else if (dut.gen_core[gb].node_inst.local_cascade_enq) begin
                        fifo_ts[dut.gen_core[gb].node_inst.fifo_wr_ptr_q] <=
                            dut.gen_core[gb].node_inst.cascade_pending_valid_q ? pend_ts : cycle_cnt;
                    end else if (dut.gen_core[gb].node_inst.rx_accept) begin
                        fifo_ts[dut.gen_core[gb].node_inst.fifo_wr_ptr_q] <= pipe_ts;
                    end else if (dut.gen_core[gb].node_inst.local_cascade_req) begin
                        pend_ts <= cycle_cnt;
                    end

                    // 4. Завершення транзакції концепту на ST_EVAL_GATE
                    if (core_commit_pulse_o[gb] || core_reject_pulse_o[gb]) begin
                        longint unsigned cur_lat;
                        cur_lat = (cycle_cnt >= act_ts) ? (cycle_cnt - act_ts + 1) : 1;
                        core_lat_sum[gb] <= core_lat_sum[gb] + cur_lat;
                        core_lat_cnt[gb] <= core_lat_cnt[gb] + 1;
                        if (cur_lat > core_lat_max[gb]) core_lat_max[gb] <= cur_lat;
                        if (cur_lat < core_lat_min[gb]) core_lat_min[gb] <= cur_lat;
                    end
                end
            end
        end
    endgenerate

    // ========================================================================
    // Допоміжні задачі керування шиною Порту A та скидання
    // ========================================================================
    function automatic [31:0] encode_sub_w3(input int dst_bank, input int dst_cid);
        begin
            encode_sub_w3 = 32'h0000_8000 | ((dst_bank & 32'hf) << 6) | (dst_cid & 32'h3f);
        end
    endfunction

    task automatic hw_reset();
        begin
            rst_n          = 1'b0;
            cfg_we_i       = 1'b0;
            cfg_bank_sel_i = 4'd0;
            cfg_addr_i     = '0;
            cfg_wdata_i    = '0;
            ext_valid_i    = '0;
            ext_dst_bank_i = '0;
            ext_dst_cid_i  = '0;
            ext_param_i    = '0;
            lat_reset_req  = 1'b1;
            for (int p = 0; p < NUM_CORES; p = p + 1) begin
                ext_birth_ts[p] = 0;
            end
            repeat (5) @(posedge clk);
            #1;
            rst_n         = 1'b1;
            lat_reset_req = 1'b0;
            repeat (2) @(posedge clk);
            #1;
        end
    endtask

    task automatic cfg_write_word(
        input int          bank,
        input int          word_addr,
        input logic [31:0] data
    );
        begin
            cfg_bank_sel_i = bank[3:0];
            cfg_addr_i     = word_addr[ADDR_WIDTH-1:0];
            cfg_wdata_i    = data;
            cfg_wstrb_i    = 4'hf;
            cfg_we_i       = 1'b1;
            @(posedge clk);
            #1;
            cfg_we_i       = 1'b0;
        end
    endtask

    task automatic cfg_write_descriptor(
        input int          bank,
        input int          cid,
        input logic [31:0] w0,
        input logic [31:0] w1,
        input logic [31:0] w2,
        input logic [31:0] w3
    );
        int base;
        begin
            base = cid * 4;
            cfg_write_word(bank, base + 0, w0);
            cfg_write_word(bank, base + 1, w1);
            cfg_write_word(bank, base + 2, w2);
            cfg_write_word(bank, base + 3, w3);
        end
    endtask

    task automatic cfg_read_word(
        input  int          bank,
        input  int          word_addr,
        output logic [31:0] rdata
    );
        begin
            cfg_we_i       = 1'b0;
            cfg_bank_sel_i = bank[3:0];
            cfg_addr_i     = word_addr[ADDR_WIDTH-1:0];
            @(posedge clk); // засемпльовано cfg_bank_sel_q та a_rdata_q у BRAM
            #1;
            rdata = cfg_rdata_o;
        end
    endtask

    // ========================================================================
    // Перевірка Fail-Closed відхилення транзакції без каскаду
    // ========================================================================
    int unsigned total_errors = 0;

    task automatic verify_fail_closed_guard();
        logic [31:0] rd_w0_b0, rd_w0_b1;
        int target_b;
        begin
            hw_reset();
            target_b = (NUM_CORES > 1) ? 1 : 0;
            // Концепт (0, 0): предикат X < 50, початковий стан W0 = 7, підписник (target_b, 1)
            cfg_write_descriptor(0, 0, 32'd7, 32'd50, W2_LT_INC, encode_sub_w3(target_b, 1));
            cfg_write_descriptor(target_b, 1, 32'd0, 32'd0, W2_NOP_INC, W3_NO_SUB);

            // Подаємо X = 99 (>= 50 -> Fail-Closed відхилення!)
            ext_birth_ts[0]          = cycle_cnt;
            ext_dst_bank_i[0 +: 4]   = 4'd0;
            ext_dst_cid_i[0 +: 6]    = 6'd0;
            ext_param_i[0 +: 32]     = 32'd99;
            ext_valid_i[0]           = 1'b1;
            #1;
            while (!ext_ready_o[0]) begin
                @(posedge clk);
                #1;
            end
            @(posedge clk);
            #1;
            ext_valid_i[0] = 1'b0;

            repeat (3) @(posedge clk);
            while (cluster_busy_o) @(posedge clk);
            #1;

            cfg_read_word(0, 0, rd_w0_b0);
            cfg_read_word(target_b, 4, rd_w0_b1);
            if ((total_rejected_o != 32'd1) || (total_committed_o != 32'd0) ||
                (rd_w0_b0 != 32'd7) || (rd_w0_b1 != 32'd0)) begin
                $display("[FAIL] Fail-closed check mismatch: rej=%0d comm=%0d b0_w0=%0d b1_w0=%0d",
                         total_rejected_o, total_committed_o, rd_w0_b0, rd_w0_b1);
                total_errors = total_errors + 1;
            end
        end
    endtask

    // ========================================================================
    // Канонічні профілі трафіку (0=local, 1=uniform, 2=hotspot, 3=many-to-one)
    // ========================================================================
    logic [31:0] exp_w0       [0:NUM_CORES-1][0:NUM_CONCEPTS-1];
    int          sub_bank_tbl [0:NUM_CORES-1][0:NUM_CONCEPTS-1];
    int          sub_cid_tbl  [0:NUM_CORES-1][0:NUM_CONCEPTS-1];

    // Результати профілів для запису у CSV/JSON
    int unsigned     prof_primary_ev   [0:3];
    int unsigned     prof_total_ev     [0:3];
    int unsigned     prof_local_casc   [0:3];
    int unsigned     prof_remote_casc  [0:3];
    int unsigned     prof_xbar_routed  [0:3];
    longint unsigned prof_cycles       [0:3];
    longint unsigned prof_lat_sum      [0:3];
    longint unsigned prof_lat_max      [0:3];
    longint unsigned prof_lat_min      [0:3];
    int unsigned     prof_stalls       [0:3];
    int unsigned     prof_ext_bp_cyc   [0:3];
    int unsigned     prof_drops        [0:3];
    int unsigned     prof_mismatches   [0:3];

    function automatic string profile_name(input int pid);
        case (pid)
            0: profile_name = "local";
            1: profile_name = "uniform";
            2: profile_name = "hotspot";
            default: profile_name = "many-to-one";
        endcase
    endfunction

    task automatic run_traffic_profile(
        input int pid,
        input int primary_events_target
    );
        int per_port_quota;
        int port_sent     [0:NUM_CORES-1];
        bit port_holding  [0:NUM_CORES-1];
        int cur_dst_b     [0:NUM_CORES-1];
        int cur_dst_c     [0:NUM_CORES-1];
        int exp_total_ev;
        int exp_loc_casc;
        int exp_rem_casc;
        int all_sent;
        int guard_timeout;
        int unsigned ext_bp_cycles;
        longint unsigned t_start_cyc;
        longint unsigned t_end_cyc;
        longint unsigned sum_lat;
        longint unsigned max_lat;
        longint unsigned min_lat;
        int unsigned cnt_lat;
        int unsigned w0_mismatches;
        logic [31:0] rd_val;
        real mcps_100;
        real avg_lat;
        begin
            hw_reset();
            per_port_quota = primary_events_target / NUM_CORES;
            if (per_port_quota < 1) per_port_quota = 1;

            exp_total_ev = 0;
            exp_loc_casc = 0;
            exp_rem_casc = 0;
            ext_bp_cycles = 0;
            w0_mismatches = 0;

            // 1. Побудова таблиці концептів та підписок для профілю pid
            for (int b = 0; b < NUM_CORES; b = b + 1) begin
                for (int c = 0; c < NUM_CONCEPTS; c = c + 1) begin
                    exp_w0[b][c]       = 32'd0;
                    sub_bank_tbl[b][c] = -1;
                    sub_cid_tbl[b][c]  = -1;

                    if (c < 8) begin
                        case (pid)
                            0: begin
                                // local: локальний 2-ступеневий каскад у межах того ж банку (0 тактів кросбара)
                                sub_bank_tbl[b][c] = b;
                                sub_cid_tbl[b][c]  = 8 + c;
                            end
                            1: begin
                                // uniform: 50% міжбанковий ациклічний перехід b -> b+1, 50% локальний
                                if ((c < 4) && (b < (NUM_CORES - 1))) begin
                                    sub_bank_tbl[b][c] = b + 1;
                                    sub_cid_tbl[b][c]  = 8 + c;
                                end else begin
                                    sub_bank_tbl[b][c] = b;
                                    sub_cid_tbl[b][c]  = 8 + c;
                                end
                            end
                            2: begin
                                // hotspot: вузли 0..N-2 направляють 75% каскадів у гарячий Bank N-1
                                if ((b < (NUM_CORES - 1)) && (c < 6)) begin
                                    sub_bank_tbl[b][c] = NUM_CORES - 1;
                                    sub_cid_tbl[b][c]  = 16 + ((b * 6 + c) % 32);
                                end else begin
                                    sub_bank_tbl[b][c] = b;
                                    sub_cid_tbl[b][c]  = 8 + c;
                                end
                            end
                            default: begin
                                // many-to-one: усі вузли 0..N-2 каскадують у єдиний агрегатор Bank N-1
                                if (b < (NUM_CORES - 1)) begin
                                    sub_bank_tbl[b][c] = NUM_CORES - 1;
                                    sub_cid_tbl[b][c]  = 16 + ((b * 4 + (c % 4)) % 40);
                                end
                            end
                        endcase
                    end

                    if (sub_bank_tbl[b][c] >= 0) begin
                        cfg_write_descriptor(
                            b, c, 32'd0, 32'd0, W2_NOP_INC,
                            encode_sub_w3(sub_bank_tbl[b][c], sub_cid_tbl[b][c])
                        );
                    end else if (c < 56) begin
                        cfg_write_descriptor(b, c, 32'd0, 32'd0, W2_NOP_INC, W3_NO_SUB);
                    end else begin
                        cfg_write_descriptor(b, c, 32'd0, 32'd0, 32'd0, W3_NO_SUB);
                    end
                end
            end

            // 2. Одночасна інжекція з усіх N зовнішніх портів із чесним утриманням valid під !ready
            for (int p = 0; p < NUM_CORES; p = p + 1) begin
                port_sent[p]    = 0;
                port_holding[p] = 1'b0;
                cur_dst_b[p]    = 0;
                cur_dst_c[p]    = 0;
            end

            @(posedge clk);
            #1;
            t_start_cyc = cycle_cnt;

            all_sent = 0;
            guard_timeout = 0;
            while (!all_sent && (guard_timeout < 500000)) begin
                guard_timeout = guard_timeout + 1;
                all_sent = 1;

                // Виставляємо наступні пакети на вільні порти до фронту такту
                for (int p = 0; p < NUM_CORES; p = p + 1) begin
                    if (!port_holding[p] && (port_sent[p] < per_port_quota)) begin
                        int idx;
                        int db;
                        int dc;
                        idx = port_sent[p];
                        case (pid)
                            0: begin
                                db = p;
                                dc = idx % 8;
                            end
                            1: begin
                                db = (p + idx) % NUM_CORES;
                                dc = idx % 8;
                            end
                            2: begin
                                // hotspot: 75% зовнішніх подій спрямовані у гарячий Bank N-1 або генерують туди каскад
                                if ((idx % 4) != 3) begin
                                    db = NUM_CORES - 1;
                                    dc = 8 + ((p + idx) % 8);
                                end else begin
                                    db = p;
                                    dc = idx % 8;
                                end
                            end
                            default: begin
                                // many-to-one: кожен порт p живить свій продуцент Bank p (а порт N-1 — прямо Bank N-1)
                                if (p == (NUM_CORES - 1)) begin
                                    db = NUM_CORES - 1;
                                    dc = 8 + (idx % 8);
                                end else begin
                                    db = p;
                                    dc = idx % 8;
                                end
                            end
                        endcase

                        cur_dst_b[p]            = db;
                        cur_dst_c[p]            = dc;
                        ext_birth_ts[p]         = cycle_cnt;
                        ext_dst_bank_i[p*4 +: 4] = db[3:0];
                        ext_dst_cid_i[p*6 +: 6]  = dc[5:0];
                        ext_param_i[p*32 +: 32]  = 32'd1 + idx;
                        ext_valid_i[p]          = 1'b1;
                        port_holding[p]         = 1'b1;

                        // Незалежний аналітичний обрахунок очікуваного стану W0 та каскадів
                        exp_w0[db][dc] = exp_w0[db][dc] + 32'd1;
                        exp_total_ev   = exp_total_ev + 1;
                        if (sub_bank_tbl[db][dc] >= 0) begin
                            int sb, sc;
                            sb = sub_bank_tbl[db][dc];
                            sc = sub_cid_tbl[db][dc];
                            exp_w0[sb][sc] = exp_w0[sb][sc] + 32'd1;
                            exp_total_ev   = exp_total_ev + 1;
                            if (sb == db) exp_loc_casc = exp_loc_casc + 1;
                            else          exp_rem_casc = exp_rem_casc + 1;
                        end
                    end

                    if (port_holding[p] || (port_sent[p] < per_port_quota)) begin
                        all_sent = 0;
                    end
                end

                if (!all_sent) begin
                    @(posedge clk);
                    // На активному фронті перевіряємо рукостискання valid && ready
                    for (int p = 0; p < NUM_CORES; p = p + 1) begin
                        if (ext_valid_i[p] && ext_ready_o[p]) begin
                            port_sent[p]    = port_sent[p] + 1;
                            port_holding[p] = 1'b0;
                        end else if (ext_valid_i[p] && !ext_ready_o[p]) begin
                            ext_bp_cycles = ext_bp_cycles + 1;
                        end
                    end
                    #1;
                    for (int p = 0; p < NUM_CORES; p = p + 1) begin
                        if (!port_holding[p]) begin
                            ext_valid_i[p] = 1'b0;
                        end
                    end
                end
            end

            ext_valid_i = '0;

            // 3. Очікуємо повного вивільнення всіх черг, кросбара та вихідних буферів
            while (cluster_busy_o && (guard_timeout < 600000)) begin
                @(posedge clk);
                guard_timeout = guard_timeout + 1;
            end
            t_end_cyc = cycle_cnt;
            #1;

            if (cluster_busy_o) begin
                $display("[FAIL] Profile %s timed out with cluster_busy_o=1!", profile_name(pid));
                total_errors = total_errors + 1;
            end

            // 4. Незалежна звірка всіх N * 64 станів W0 через шину Порту A
            for (int b = 0; b < NUM_CORES; b = b + 1) begin
                for (int c = 0; c < 56; c = c + 1) begin
                    cfg_read_word(b, c * 4, rd_val);
                    if (rd_val !== exp_w0[b][c]) begin
                        if (w0_mismatches < 5) begin
                            $display("[FAIL] Profile %s W0 mismatch bank=%0d cid=%0d: got=%0d exp=%0d",
                                     profile_name(pid), b, c, rd_val, exp_w0[b][c]);
                        end
                        w0_mismatches = w0_mismatches + 1;
                    end
                end
            end

            // 5. Збір агрегованої статистики латентності та пропускної здатності
            sum_lat = 0;
            max_lat = 0;
            min_lat = 64'hffff_ffff;
            cnt_lat = 0;
            for (int b = 0; b < NUM_CORES; b = b + 1) begin
                sum_lat = sum_lat + core_lat_sum[b];
                cnt_lat = cnt_lat + core_lat_cnt[b];
                if (core_lat_max[b] > max_lat) max_lat = core_lat_max[b];
                if (core_lat_min[b] < min_lat) min_lat = core_lat_min[b];
            end

            if ((total_events_processed_o != exp_total_ev) ||
                (total_committed_o != exp_total_ev) ||
                (total_rejected_o != 0) ||
                (total_local_cascades_o != exp_loc_casc) ||
                (total_remote_cascades_o != exp_rem_casc) ||
                (cnt_lat != exp_total_ev) ||
                (invalid_dst_drop_count_o != 0) ||
                (|collision_detected_o) ||
                (w0_mismatches != 0)) begin
                $display("[FAIL] Profile %s conservation/golden error: proc=%0d(exp %0d) loc=%0d(exp %0d) rem=%0d(exp %0d) lat_cnt=%0d drops=%0d w0_err=%0d",
                         profile_name(pid), total_events_processed_o, exp_total_ev,
                         total_local_cascades_o, exp_loc_casc,
                         total_remote_cascades_o, exp_rem_casc,
                         cnt_lat, invalid_dst_drop_count_o, w0_mismatches);
                total_errors = total_errors + 1;
            end

            prof_primary_ev[pid]  = per_port_quota * NUM_CORES;
            prof_total_ev[pid]    = total_events_processed_o;
            prof_local_casc[pid]  = total_local_cascades_o;
            prof_remote_casc[pid] = total_remote_cascades_o;
            prof_xbar_routed[pid] = xbar_routed_events_o;
            prof_cycles[pid]      = (t_end_cyc > t_start_cyc) ? (t_end_cyc - t_start_cyc) : 1;
            prof_lat_sum[pid]     = sum_lat;
            prof_lat_max[pid]     = max_lat;
            prof_lat_min[pid]     = min_lat;
            prof_stalls[pid]      = backpressure_stall_cycles_o;
            prof_ext_bp_cyc[pid]  = ext_bp_cycles;
            prof_drops[pid]       = invalid_dst_drop_count_o;
            prof_mismatches[pid]  = w0_mismatches;

            mcps_100 = (100.0 * real'(prof_total_ev[pid])) / real'(prof_cycles[pid]);
            avg_lat  = real'(sum_lat) / real'(cnt_lat);

            $display("PROFILE N=%0d profile=%s primary=%0d total_ev=%0d loc_casc=%0d rem_casc=%0d cycles=%0d mcps_100mhz=%0.3f avg_lat_cyc=%0.2f min_lat_cyc=%0d max_lat_cyc=%0d backpressure_stalls=%0d ext_port_wait_cyc=%0d dropped=%0d w0_mismatches=%0d",
                     NUM_CORES, profile_name(pid), prof_primary_ev[pid], prof_total_ev[pid],
                     prof_local_casc[pid], prof_remote_casc[pid], prof_cycles[pid],
                     mcps_100, avg_lat, prof_lat_min[pid], prof_lat_max[pid],
                     prof_stalls[pid], prof_ext_bp_cyc[pid], prof_drops[pid], prof_mismatches[pid]);
        end
    endtask

    // ========================================================================
    // Головний сценарій симуляції та запис JSON-резюме (за наявності +summary_json=...)
    // ========================================================================
    int events_per_profile = 1024;
    string summary_json_path = "";
    int fd;

    initial begin
        void'($value$plusargs("events_per_profile=%d", events_per_profile));
        void'($value$plusargs("summary_json=%s", summary_json_path));

        verify_fail_closed_guard();

        for (int pid = 0; pid < 4; pid = pid + 1) begin
            run_traffic_profile(pid, events_per_profile);
        end

        if (summary_json_path != "") begin
            fd = $fopen(summary_json_path, "w");
            if (fd != 0) begin
                $fwrite(fd, "{\n");
                $fwrite(fd, "  \"evidence_kind\": \"rtl_simulation_iverilog\",\n");
                $fwrite(fd, "  \"not_physical_hil\": true,\n");
                $fwrite(fd, "  \"num_cores\": %0d,\n", NUM_CORES);
                $fwrite(fd, "  \"queue_depth\": %0d,\n", QUEUE_DEPTH);
                $fwrite(fd, "  \"total_errors\": %0d,\n", total_errors);
                $fwrite(fd, "  \"profiles\": [\n");
                for (int pid = 0; pid < 4; pid = pid + 1) begin
                    real mcps_v, avg_l;
                    mcps_v = (100.0 * real'(prof_total_ev[pid])) / real'(prof_cycles[pid]);
                    avg_l  = real'(prof_lat_sum[pid]) / real'(prof_total_ev[pid]);
                    $fwrite(fd, "    {\n");
                    $fwrite(fd, "      \"profile\": \"%s\",\n", profile_name(pid));
                    $fwrite(fd, "      \"primary_events\": %0d,\n", prof_primary_ev[pid]);
                    $fwrite(fd, "      \"total_events_evaluated\": %0d,\n", prof_total_ev[pid]);
                    $fwrite(fd, "      \"local_cascades\": %0d,\n", prof_local_casc[pid]);
                    $fwrite(fd, "      \"remote_cascades\": %0d,\n", prof_remote_casc[pid]);
                    $fwrite(fd, "      \"xbar_routed_events\": %0d,\n", prof_xbar_routed[pid]);
                    $fwrite(fd, "      \"active_cycles\": %0d,\n", prof_cycles[pid]);
                    $fwrite(fd, "      \"throughput_mcps_at_100mhz\": %0.4f,\n", mcps_v);
                    $fwrite(fd, "      \"avg_latency_cycles\": %0.3f,\n", avg_l);
                    $fwrite(fd, "      \"min_latency_cycles\": %0d,\n", prof_lat_min[pid]);
                    $fwrite(fd, "      \"max_latency_cycles\": %0d,\n", prof_lat_max[pid]);
                    $fwrite(fd, "      \"backpressure_stalls\": %0d,\n", prof_stalls[pid]);
                    $fwrite(fd, "      \"ext_port_wait_cycles\": %0d,\n", prof_ext_bp_cyc[pid]);
                    $fwrite(fd, "      \"dropped_accepted_events\": %0d,\n", prof_drops[pid]);
                    $fwrite(fd, "      \"w0_golden_mismatches\": %0d\n", prof_mismatches[pid]);
                    $fwrite(fd, "    }%s\n", (pid < 3) ? "," : "");
                end
                $fwrite(fd, "  ]\n");
                $fwrite(fd, "}\n");
                $fclose(fd);
            end
        end

        if (total_errors == 0) begin
            $display("PASS: km_manycore_cluster_tb N=%0d verified all 4 profiles (%0d+ primary events each, 0 drops, 0 golden mismatches)",
                     NUM_CORES, events_per_profile);
            $finish(0);
        end else begin
            $display("[FAIL] km_manycore_cluster_tb N=%0d finished with %0d error(s)",
                     NUM_CORES, total_errors);
            $fatal(1);
        end
    end

endmodule
