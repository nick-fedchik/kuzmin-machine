`timescale 1ns/1ps

module kpol_txn_gate_axi_lite_tb;
    localparam logic [1:0] AXI_RESP_OKAY = 2'b00;
    localparam logic [1:0] AXI_RESP_SLVERR = 2'b10;
    localparam logic [1:0] AXI_RESP_DECERR = 2'b11;

    logic clk = 1'b0;
    logic resetn = 1'b0;
    logic [12:0] awaddr = 13'b0;
    logic awvalid = 1'b0;
    logic awready;
    logic [31:0] wdata = 32'b0;
    logic [3:0] wstrb = 4'b0;
    logic wvalid = 1'b0;
    logic wready;
    logic [1:0] bresp;
    logic bvalid;
    logic bready = 1'b0;
    logic [12:0] araddr = 13'b0;
    logic arvalid = 1'b0;
    logic arready;
    logic [31:0] rdata;
    logic [1:0] rresp;
    logic rvalid;
    logic rready = 1'b0;

    always #5 clk <= ~clk;

    kpol_txn_gate_axi_lite dut (
        .s_axi_aclk(clk),
        .s_axi_aresetn(resetn),
        .s_axi_awaddr(awaddr),
        .s_axi_awvalid(awvalid),
        .s_axi_awready(awready),
        .s_axi_wdata(wdata),
        .s_axi_wstrb(wstrb),
        .s_axi_wvalid(wvalid),
        .s_axi_wready(wready),
        .s_axi_bresp(bresp),
        .s_axi_bvalid(bvalid),
        .s_axi_bready(bready),
        .s_axi_araddr(araddr),
        .s_axi_arvalid(arvalid),
        .s_axi_arready(arready),
        .s_axi_rdata(rdata),
        .s_axi_rresp(rresp),
        .s_axi_rvalid(rvalid),
        .s_axi_rready(rready),
        .status_monitor_o(),
        .state_monitor_o(),
        .ext_event_valid_i(1'b0),
        .ext_candidate_value_i(32'b0),
        .ext_conditions_i(7'b0)
    );

    task automatic send_aw(input logic [12:0] address);
        begin
            @(negedge clk);
            awaddr = address;
            awvalid = 1'b1;
            do @(posedge clk); while (awready !== 1'b1);
            @(negedge clk);
            awvalid = 1'b0;
        end
    endtask

    task automatic send_w(
        input logic [31:0] data,
        input logic [3:0] strobe
    );
        begin
            @(negedge clk);
            wdata = data;
            wstrb = strobe;
            wvalid = 1'b1;
            do @(posedge clk); while (wready !== 1'b1);
            @(negedge clk);
            wvalid = 1'b0;
        end
    endtask

    task automatic axi_write(
        input logic [12:0] address,
        input logic [31:0] data,
        input logic [3:0] strobe,
        input logic data_first,
        input logic [1:0] expected_response
    );
        begin
            if (data_first) begin
                send_w(data, strobe);
                send_aw(address);
            end else begin
                send_aw(address);
                send_w(data, strobe);
            end

            while (bvalid !== 1'b1) @(posedge clk);
            if (bresp !== expected_response) begin
                $fatal(1, "write response mismatch at 0x%02x: expected 2'b%b, got 2'b%b",
                       address, expected_response, bresp);
            end
            @(negedge clk);
            bready = 1'b1;
            @(posedge clk);
            @(negedge clk);
            bready = 1'b0;
        end
    endtask

    task automatic send_ar(input logic [12:0] address);
        begin
            @(negedge clk);
            araddr = address;
            arvalid = 1'b1;
            do @(posedge clk); while (arready !== 1'b1);
            @(negedge clk);
            arvalid = 1'b0;
        end
    endtask

    task automatic axi_read(
        input logic [12:0] address,
        output logic [31:0] data,
        output logic [1:0] response
    );
        begin
            send_ar(address);
            while (rvalid !== 1'b1) @(posedge clk);
            data = rdata;
            response = rresp;
            @(negedge clk);
            rready = 1'b1;
            @(posedge clk);
            @(negedge clk);
            rready = 1'b0;
        end
    endtask

    task automatic wait_for_result(output logic [31:0] result);
        integer spins;
        logic [1:0] read_rsp;
        begin
            spins = 0;
            result = 32'b0;
            while (spins < 20) begin
                axi_read(6'h0C, result, read_rsp);
                if (read_rsp !== AXI_RESP_OKAY) begin
                    $fatal(1, "status read returned error response");
                end
                if (result[0] && !result[8]) begin
                    disable wait_for_result;
                end
                spins = spins + 1;
            end
            if (!result[0] || result[8]) begin
                $fatal(1, "transaction did not complete: status=0x%08x", result);
            end
        end
    endtask

    logic [31:0] value;
    logic [1:0] response;

    initial begin
        repeat (2) @(posedge clk);
        @(negedge clk);
        resetn = 1'b1;

        // 1. Identification check
        axi_read(6'h14, value, response);
        if (response !== AXI_RESP_OKAY || value !== 32'h4B504F4C) begin
            $fatal(1, "KPOL identification register mismatch");
        end

        // 2. Byte strobes test
        axi_write(6'h00, 32'hAABBCCDD, 4'b0101, 1'b0, AXI_RESP_OKAY);
        axi_read(6'h00, value, response);
        if (response !== AXI_RESP_OKAY || value !== 32'h00BB00DD) begin
            $fatal(1, "byte strobes were not applied to candidate register");
        end

        // 3. Nominal commit test (Manual mode)
        axi_write(6'h00, 32'h00001234, 4'b1111, 1'b1, AXI_RESP_OKAY);
        axi_write(6'h04, 32'h0000003F, 4'b0001, 1'b1, AXI_RESP_OKAY);
        axi_write(6'h08, 32'h00000001, 4'b0001, 1'b0, AXI_RESP_OKAY);
        wait_for_result(value);
        if (!value[1] || !value[5] || value[2]) begin
            $fatal(1, "valid transaction did not commit: status=0x%08x", value);
        end
        axi_read(6'h10, value, response);
        if (response !== AXI_RESP_OKAY || value !== 32'h00001234) begin
            $fatal(1, "committed state mismatch");
        end

        // 4. Invalid input rejection test
        axi_write(6'h00, 32'h00005678, 4'b1111, 1'b0, AXI_RESP_OKAY);
        axi_write(6'h04, 32'h0000003B, 4'b0001, 1'b0, AXI_RESP_OKAY);
        axi_write(6'h08, 32'h00000001, 4'b0001, 1'b1, AXI_RESP_OKAY);
        wait_for_result(value);
        if (!value[2] || !value[3] || value[1]) begin
            $fatal(1, "invalid input was not rejected: status=0x%08x", value);
        end
        axi_read(6'h10, value, response);
        if (value !== 32'h00001234) begin
            $fatal(1, "rejected transaction changed state");
        end

        // 5. Invariant rejection test (Manual mode)
        axi_write(6'h00, 32'h00009999, 4'b1111, 1'b1, AXI_RESP_OKAY);
        axi_write(6'h04, 32'h0000002F, 4'b0001, 1'b0, AXI_RESP_OKAY);
        axi_write(6'h08, 32'h00000001, 4'b0001, 1'b0, AXI_RESP_OKAY);
        wait_for_result(value);
        if (!value[2] || !value[4] || value[3] || value[1]) begin
            $fatal(1, "invalid invariant was not rejected: status=0x%08x", value);
        end
        axi_read(6'h10, value, response);
        if (value !== 32'h00001234) begin
            $fatal(1, "invariant rejection changed state");
        end

        // 6. Hazard observation test
        axi_write(6'h00, 32'h0000CAFE, 4'b1111, 1'b1, AXI_RESP_OKAY);
        axi_write(6'h04, 32'h0000007F, 4'b0001, 1'b0, AXI_RESP_OKAY);
        axi_write(6'h08, 32'h00000001, 4'b0001, 1'b0, AXI_RESP_OKAY);
        wait_for_result(value);
        if (!value[1] || !value[5] || !value[6]) begin
            $fatal(1, "hazard observation or commit status mismatch: 0x%08x", value);
        end

        // -------------------------------------------------------------
        // 7. HARDWARE PREDICATE EVALUATOR & BIG DOT (•) TESTS (H1 & H6)
        // -------------------------------------------------------------
        // Read initial default lower and upper bounds
        axi_read(6'h18, value, response);
        if (response !== AXI_RESP_OKAY || value !== 32'sd0) begin
            $fatal(1, "lower bound default mismatch: 0x%08x", value);
        end
        axi_read(6'h1C, value, response);
        if (response !== AXI_RESP_OKAY || value !== 32'h7FFFFFFF) begin
            $fatal(1, "upper bound default mismatch: 0x%08x", value);
        end

        // Test 7A: Live Predicate Vector inspection for Candidate = 0x00000004
        // (4 is Even, Positive, Non-Null, Range-valid, Changed from state 0xCAFE)
        axi_write(6'h00, 32'd4, 4'b1111, 1'b0, AXI_RESP_OKAY);
        axi_read(6'h24, value, response);
        // Bit 0: uninit=0, 1: null=0, 2: pos=1, 3: neg=0, 4: even=1, 5: uneven=0, 6: changed=1, 7: range=1
        // Expected byte: 8'b1101_0100 = 0xD4
        if (response !== AXI_RESP_OKAY || value[7:0] !== 8'hD4) begin
            $fatal(1, "predicate vector mismatch for 4: expected 0xD4, got 0x%02x", value[7:0]);
        end

        // Test 7B: Configure Invariant Rule = USE_HW_EVAL (bit 5) | REQUIRE_EVEN (bit 0) -> 0x21
        axi_write(6'h20, 32'h00000021, 4'b0001, 1'b1, AXI_RESP_OKAY);
        axi_read(6'h28, value, response);
        if (value[0] !== 1'b1) begin
            $fatal(1, "Big Dot • should be TRUE (1) for even candidate 4");
        end

        // Commit candidate 4 via Hardware Evaluation (conditions[0]=1 candidate known, [1..2]=1 assumption valid)
        axi_write(6'h04, 32'h00000007, 4'b0001, 1'b0, AXI_RESP_OKAY);
        axi_write(6'h08, 32'h00000001, 4'b0001, 1'b0, AXI_RESP_OKAY);
        wait_for_result(value);
        if (!value[1] || value[2]) begin
            $fatal(1, "Hardware Evaluator failed to commit even candidate 4: status=0x%08x", value);
        end
        axi_read(6'h10, value, response);
        if (value !== 32'd4) begin
            $fatal(1, "State was not updated to 4: state=0x%08x", value);
        end

        // Test 7C: Candidate = 5 (Uneven) with REQUIRE_EVEN active -> Hardware Big Dot drops to 0 (Fail-closed!)
        axi_write(6'h00, 32'd5, 4'b1111, 1'b0, AXI_RESP_OKAY);
        axi_read(6'h28, value, response);
        if (value[0] !== 1'b0) begin
            $fatal(1, "Big Dot • should be FALSE (0) for uneven candidate 5 when REQUIRE_EVEN is active");
        end

        // Attempt transaction with Candidate = 5 -> MUST BE REJECTED BY HARDWARE INVARIANT!
        axi_write(6'h08, 32'h00000001, 4'b0001, 1'b0, AXI_RESP_OKAY);
        wait_for_result(value);
        if (!value[2] || !value[4] || value[1]) begin
            $fatal(1, "Hardware Evaluator did NOT reject uneven candidate 5! status=0x%08x", value);
        end
        // Invariant Fail-Closed check: state MUST remain strictly 4!
        axi_read(6'h10, value, response);
        if (value !== 32'd4) begin
            $fatal(1, "FAIL-CLOSED VIOLATION: State changed from 4 to 0x%08x after invariant rejection!", value);
        end

        // Test 7D: Range Invariant Check: Rule = USE_HW_EVAL (bit 5) | REQUIRE_RANGE (bit 3) -> 0x28
        // Lower = 10, Upper = 100
        axi_write(6'h18, 32'd10, 4'b1111, 1'b0, AXI_RESP_OKAY);
        axi_write(6'h1C, 32'd100, 4'b1111, 1'b1, AXI_RESP_OKAY);
        axi_write(6'h20, 32'h00000028, 4'b0001, 1'b0, AXI_RESP_OKAY);

        // Candidate = 50 (In range [10, 100]) -> Commit OK
        axi_write(6'h00, 32'd50, 4'b1111, 1'b0, AXI_RESP_OKAY);
        axi_write(6'h08, 32'h00000001, 4'b0001, 1'b0, AXI_RESP_OKAY);
        wait_for_result(value);
        if (!value[1] || value[2]) begin
            $fatal(1, "In-range candidate 50 did not commit: status=0x%08x", value);
        end
        axi_read(6'h10, value, response);
        if (value !== 32'd50) begin
            $fatal(1, "State was not updated to 50: state=0x%08x", value);
        end

        // Candidate = 200 (Out of range > 100) -> MUST BE REJECTED BY RANGE INVARIANT!
        axi_write(6'h00, 32'd200, 4'b1111, 1'b0, AXI_RESP_OKAY);
        axi_write(6'h08, 32'h00000001, 4'b0001, 1'b0, AXI_RESP_OKAY);
        wait_for_result(value);
        if (!value[2] || !value[4] || value[1]) begin
            $fatal(1, "Out-of-range candidate 200 was not rejected! status=0x%08x", value);
        end
        axi_read(6'h10, value, response);
        if (value !== 32'd50) begin
            $fatal(1, "FAIL-CLOSED VIOLATION: State changed from 50 to 0x%08x after range rejection!", value);
        end

        // 8. Error handling checks
        axi_write(6'h0C, 32'h00000000, 4'b1111, 1'b0, AXI_RESP_DECERR);
        axi_write(6'h08, 32'h00000002, 4'b1111, 1'b1, AXI_RESP_SLVERR);
        // 0x2C is REG_CYCLE_CNT_LO (EXP-04): mapped, must return OKAY
        axi_read(13'h002C, value, response);
        if (response !== AXI_RESP_OKAY) begin
            $fatal(1, "mapped read address 0x2C (REG_CYCLE_CNT_LO) did not return OKAY");
        end
        // 0x7C: aligned gap between 0x78 (RCFC_RESULT) and 0x80 (SUITE_B_CTRL)
        axi_read(13'h007C, value, response);
        if (response !== AXI_RESP_DECERR) begin
            $fatal(1, "unmapped read address 0x7C did not return DECERR");
        end
        // 0x0100: [12:8] != 0 and outside the BRAM window (addr[12:10] != 3'b100)
        axi_read(13'h0100, value, response);
        if (response !== AXI_RESP_DECERR) begin
            $fatal(1, "unmapped read address 0x0100 did not return DECERR");
        end

        $display("========================================================================");
        $display("PASS: All KPOL AXI4-Lite & Hardware Predicate Evaluator tests succeeded!");
        $display(">> Verified H1: Zero-side-effect parallel predicate evaluation");
        $display(">> Verified H6: Big Dot (•) Invariant Fail-Closed state protection");
        $display("========================================================================");
        $finish;
    end

    initial begin
        #15000;
        $fatal(1, "testbench timeout");
    end
endmodule
