`timescale 1ns/1ps

module kpol_bram_pipeline_axi_tb;
    logic clk = 0, rst_n = 0;
    logic [12:0] awaddr = 0, araddr = 0;
    logic awvalid = 0, wvalid = 0, bready = 0, arvalid = 0, rready = 0;
    logic [31:0] wdata = 0;
    logic [3:0] wstrb = 4'hf;
    wire awready, wready, bvalid, arready, rvalid, busy;
    wire [1:0] bresp, rresp;
    wire [31:0] rdata;
    logic [31:0] image [0:255];
    reg [4095:0] image_a, image_b;

    // Сигнали зовнішнього тригера та апаратної телеметрії
    logic ext_hw_trigger_valid_i = 0;
    logic [5:0] ext_hw_trigger_cid_i = 0;
    logic [31:0] ext_hw_trigger_param_i = 0;
    wire hw_trigger_ready_o;
    wire hw_commit_pulse_o;
    wire hw_reject_pulse_o;
    wire hw_pipeline_busy_o;
    wire fifo_overflow_o;
    wire [31:0] events_dropped_count_o;

    always #5 clk = ~clk;

    kpol_bram_pipeline_axi dut (.*);

    task automatic write_reg(input [12:0] addr, input [31:0] data,
                             input [3:0] strb, input [1:0] expected_resp);
        @(negedge clk);
        awaddr = addr;
        wdata = data;
        wstrb = strb;
        awvalid = 1;
        wvalid = 1;
        bready = 1;
        do @(posedge clk); while (!awready || !wready);
        @(negedge clk);
        awvalid = 0;
        wvalid = 0;
        while (!bvalid) @(negedge clk);
        if (bresp !== expected_resp)
            $fatal(1, "write %h response %h expected %h", addr, bresp, expected_resp);
        @(negedge clk);
        bready = 0;
    endtask

    task automatic read_reg(input [12:0] addr, output [31:0] data);
        @(negedge clk);
        araddr = addr;
        arvalid = 1;
        rready = 1;
        do @(posedge clk); while (!arready);
        @(negedge clk);
        arvalid = 0;
        while (!rvalid) @(negedge clk);
        if (rresp !== 0) $fatal(1, "read %h response %h", addr, rresp);
        data = rdata;
        @(negedge clk);
        rready = 0;
    endtask

    task automatic write_split(input bit data_first);
        @(negedge clk);
        awaddr = 'h00c;
        wdata = 123;
        wstrb = 4'hf;
        if (data_first) wvalid = 1;
        else awvalid = 1;
        @(negedge clk);
        awvalid = 0;
        wvalid = 0;
        repeat (2) @(negedge clk);
        if (data_first) awvalid = 1;
        else wvalid = 1;
        @(negedge clk);
        awvalid = 0;
        wvalid = 0;
        while (!bvalid) @(negedge clk);
        repeat (3) begin
            if (!bvalid || bresp !== 0 || awready || wready)
                $fatal(1, "write response did not hold under backpressure");
            @(negedge clk);
        end
        bready = 1;
        @(negedge clk);
        bready = 0;
    endtask

    task automatic load_image(input reg [4095:0] filename);
        $readmemh(filename, image);
        for (int i = 0; i < 256; i++) begin
            write_reg('h004, i, 4'hf, 0);
            write_reg('h008, image[i], 4'hf, 0);
        end
    endtask

    task automatic wait_idle;
        reg [31:0] status;
        status = 1;
        while (status[0]) read_reg('h014, status);
    endtask

    task automatic send_event(input [31:0] value);
        write_reg('h00c, value, 4'hf, 0);
        write_reg('h010, 1, 4'hf, 0);
        wait_idle();
    endtask

    task automatic send_hw_trigger(input [5:0] cid, input [31:0] value);
        @(negedge clk);
        ext_hw_trigger_cid_i = cid;
        ext_hw_trigger_param_i = value;
        ext_hw_trigger_valid_i = 1;
        @(negedge clk);
        ext_hw_trigger_valid_i = 0;
        wait_idle();
    endtask

    task automatic check_state(input [31:0] expected, input reg [63:0] label);
        reg [31:0] actual;
        write_reg('h004, 0, 4'hf, 0);
        read_reg('h008, actual);
        if (actual !== expected)
            $fatal(1, "%0s: expected state %0d, got %0d", label, expected, actual);
    endtask

    initial begin : run
        reg [31:0] value;
        if (!$value$plusargs("image_a=%s", image_a) ||
            !$value$plusargs("image_b=%s", image_b))
            $fatal(1, "two image paths are required");
        repeat (3) @(negedge clk);
        rst_n = 1;

        read_reg('h000, value);
        if (value !== 32'h4b504d43) $fatal(1, "incorrect ID");
        write_reg('h004, 1, 4'h1, 2);
        write_reg('h028, 0, 4'hf, 3);
        write_split(0);
        write_split(1);
        read_reg('h00c, value);
        if (value !== 123) $fatal(1, "split writes lost data");

        load_image(image_a);
        write_reg('h00c, 5, 4'hf, 0);
        write_reg('h010, 1, 4'hf, 0);
        write_reg('h004, 0, 4'hf, 2);
        wait_idle();
        check_state(11, "image A");
        send_event(25);
        check_state(11, "image A");

        // Перевірка апаратного зовнішнього тригера (REQ-SYS-011)
        send_hw_trigger(6'd0, 5);
        check_state(12, "image A via HW trigger");

        load_image(image_b);
        send_event(5);
        check_state(9, "image B");
        send_event(25);
        check_state(9, "image B");

        read_reg('h018, value);
        if (value !== 5) $fatal(1, "incorrect event count: %0d", value);
        read_reg('h01c, value);
        if (value !== 3) $fatal(1, "incorrect commit count: %0d", value);
        read_reg('h020, value);
        if (value !== 2) $fatal(1, "incorrect reject count: %0d", value);

        // Перевірка регістрів телеметрії черги
        read_reg('h028, value);
        if (value !== 0) $fatal(1, "expected 0 dropped events, got %0d", value);
        read_reg('h02c, value);
        // ready повинен бути 1
        if (value[7] !== 1'b1) $fatal(1, "expected ready flag in reg 0x02c, got %h", value);

        $display("PASS: both compiled images");
        $finish;
    end
    initial begin
        #1000000;
        $fatal(1, "simulation timed out");
    end
endmodule
