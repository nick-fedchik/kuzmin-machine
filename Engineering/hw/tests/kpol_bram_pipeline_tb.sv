`timescale 1ns/1ps

module kpol_bram_pipeline_tb;
    logic clk = 0;
    logic rst_n = 0;
    logic trigger = 0;
    logic [31:0] param = 0;
    logic [7:0] a_addr = 0;
    logic [31:0] a_wdata = 0;
    logic a_we = 0;
    wire [31:0] a_rdata;
    wire [7:0] b_addr;
    wire [31:0] b_wdata, b_rdata;
    wire [3:0] b_wstrb;
    wire b_we, busy;
    wire [31:0] events_count, committed_count, rejected_count, last_state;
    logic [31:0] image [0:255];
    reg [4095:0] image_a, image_b;

    always #5 clk = ~clk;

    km_concept_bram bram (
        .clk(clk), .rst_n(rst_n),
        .a_addr_i(a_addr), .a_wdata_i(a_wdata), .a_wstrb_i(4'hf),
        .a_we_i(a_we), .a_rdata_o(a_rdata),
        .b_addr_i(b_addr), .b_wdata_i(b_wdata), .b_wstrb_i(b_wstrb),
        .b_we_i(b_we), .b_rdata_o(b_rdata), .collision_detected_o()
    );

    km_autonomous_sequencer sequencer (
        .clk(clk), .rst_n(rst_n), .hw_trigger_valid_i(trigger),
        .hw_trigger_cid_i(6'd0), .hw_trigger_param_i(param),
        .bram_b_addr_o(b_addr), .bram_b_wdata_o(b_wdata),
        .bram_b_wstrb_o(b_wstrb), .bram_b_we_o(b_we), .bram_b_rdata_i(b_rdata),
        .busy_o(busy), .events_processed_count_o(events_count),
        .committed_count_o(committed_count), .rejected_count_o(rejected_count),
        .last_committed_state_o(last_state)
    );

    task automatic load_image(input reg [4095:0] filename);
        $readmemh(filename, image);
        for (int i = 0; i < 256; i++) begin
            @(negedge clk);
            a_addr = i[7:0];
            a_wdata = image[i];
            a_we = 1;
        end
        @(negedge clk);
        a_we = 0;
    endtask

    task automatic send_event(input logic [31:0] value);
        logic [31:0] previous_events;
        previous_events = events_count;
        @(negedge clk);
        param = value;
        trigger = 1;
        @(negedge clk);
        trigger = 0;
        wait (events_count == previous_events + 1);
        wait (!busy);
        repeat (3) @(negedge clk);
    endtask

    task automatic check_state(input logic [31:0] expected, input reg [63:0] label);
        @(negedge clk);
        a_addr = 0;
        repeat (2) @(negedge clk);
        if (a_rdata !== expected)
            $fatal(1, "%0s: expected state %0d, got %0d", label, expected, a_rdata);
    endtask

    initial begin
        if (!$value$plusargs("image_a=%s", image_a) ||
            !$value$plusargs("image_b=%s", image_b))
            $fatal(1, "two image paths are required");
        repeat (3) @(negedge clk);
        rst_n = 1;

        load_image(image_a);
        send_event(5);
        check_state(11, "image A");
        send_event(25);
        check_state(11, "image A");
        if (committed_count != 1 || rejected_count != 1)
            $fatal(1, "image A: incorrect transaction counts");

        load_image(image_b);
        send_event(5);
        check_state(9, "image B");
        send_event(25);
        check_state(9, "image B");
        if (committed_count != 2 || rejected_count != 2 || events_count != 4)
            $fatal(1, "image B: incorrect transaction counts");

        $display("PASS: both compiled images");
        $finish;
    end

    initial begin
        #200000;
        $fatal(1, "simulation timed out");
    end
endmodule
