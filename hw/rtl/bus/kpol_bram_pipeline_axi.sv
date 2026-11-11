`timescale 1ns/1ps

// Experimental MMIO interface for the KPOL BRAM pipeline.
module kpol_bram_pipeline_axi (
    input  logic        clk,
    input  logic        rst_n,
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
    input  logic [12:0] araddr,
    input  logic        arvalid,
    output logic        arready,
    output logic [31:0] rdata,
    output logic [1:0]  rresp,
    output logic        rvalid,
    input  logic        rready,
    output logic        busy
);
    localparam logic [1:0] OKAY = 2'b00, SLVERR = 2'b10, DECERR = 2'b11;

    logic aw_pending, w_pending;
    logic [12:0] awaddr_q;
    logic [31:0] wdata_q;
    logic [3:0] wstrb_q;
    wire aw_fire = awvalid && awready;
    wire w_fire = wvalid && wready;
    wire write_fire = (aw_pending || aw_fire) && (w_pending || w_fire);
    wire [12:0] write_addr = aw_pending ? awaddr_q : awaddr;
    wire [31:0] write_data = w_pending ? wdata_q : wdata;
    wire [3:0] write_strb = w_pending ? wstrb_q : wstrb;
    assign awready = !aw_pending && !bvalid;
    assign wready = !w_pending && !bvalid;
    assign arready = !rvalid && !read_pending;

    logic [7:0] bram_addr;
    logic [31:0] bram_wdata, event_param;
    logic bram_we, trigger;
    wire [31:0] bram_rdata, b_wdata, b_rdata;
    wire [7:0] b_addr;
    wire [3:0] b_wstrb;
    wire b_we, seq_busy;
    wire [31:0] events, commits, rejects, last_state;
    logic read_pending;
    logic [12:0] read_addr;
    assign busy = seq_busy || trigger || b_we;

    km_concept_bram bram (
        .clk(clk), .rst_n(rst_n), .a_addr_i(bram_addr),
        .a_wdata_i(bram_wdata), .a_wstrb_i(4'hf), .a_we_i(bram_we),
        .a_rdata_o(bram_rdata), .b_addr_i(b_addr), .b_wdata_i(b_wdata),
        .b_wstrb_i(b_wstrb), .b_we_i(b_we), .b_rdata_o(b_rdata),
        .collision_detected_o()
    );

    km_autonomous_sequencer sequencer (
        .clk(clk), .rst_n(rst_n), .hw_trigger_valid_i(trigger),
        .hw_trigger_cid_i(6'd0), .hw_trigger_param_i(event_param),
        .bram_b_addr_o(b_addr), .bram_b_wdata_o(b_wdata),
        .bram_b_wstrb_o(b_wstrb), .bram_b_we_o(b_we), .bram_b_rdata_i(b_rdata),
        .busy_o(seq_busy), .events_processed_count_o(events),
        .committed_count_o(commits), .rejected_count_o(rejects),
        .last_committed_state_o(last_state)
    );

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            aw_pending <= 0;
            w_pending <= 0;
            awaddr_q <= 0;
            wdata_q <= 0;
            wstrb_q <= 0;
            bresp <= OKAY;
            bvalid <= 0;
            rdata <= 0;
            rresp <= OKAY;
            rvalid <= 0;
            read_pending <= 0;
            read_addr <= 0;
            bram_addr <= 0;
            bram_wdata <= 0;
            bram_we <= 0;
            event_param <= 0;
            trigger <= 0;
        end else begin
            bram_we <= 0;
            trigger <= 0;
            if (bvalid && bready) bvalid <= 0;
            if (rvalid && rready) rvalid <= 0;

            if (aw_fire) begin
                awaddr_q <= awaddr;
                aw_pending <= 1;
            end
            if (w_fire) begin
                wdata_q <= wdata;
                wstrb_q <= wstrb;
                w_pending <= 1;
            end
            if (write_fire) begin
                aw_pending <= 0;
                w_pending <= 0;
                bvalid <= 1;
                bresp <= OKAY;
                if (write_strb != 4'hf) begin
                    bresp <= SLVERR;
                end else begin
                    case (write_addr)
                        13'h004: if (busy) bresp <= SLVERR;
                                  else bram_addr <= write_data[7:0];
                        13'h008: if (busy) bresp <= SLVERR;
                                  else begin
                                      bram_wdata <= write_data;
                                      bram_we <= 1;
                                  end
                        13'h00c: if (busy) bresp <= SLVERR;
                                  else event_param <= write_data;
                        13'h010: if (busy || write_data != 1) bresp <= SLVERR;
                                  else trigger <= 1;
                        default: bresp <= DECERR;
                    endcase
                end
            end

            if (arvalid && arready) begin
                read_addr <= araddr;
                read_pending <= 1;
            end else if (read_pending) begin
                read_pending <= 0;
                rvalid <= 1;
                rresp <= OKAY;
                case (read_addr)
                    13'h000: rdata <= 32'h4b504d43;
                    13'h004: rdata <= {24'b0, bram_addr};
                    13'h008: rdata <= bram_rdata;
                    13'h00c: rdata <= event_param;
                    13'h014: rdata <= {31'b0, busy};
                    13'h018: rdata <= events;
                    13'h01c: rdata <= commits;
                    13'h020: rdata <= rejects;
                    13'h024: rdata <= last_state;
                    default: begin rdata <= 0; rresp <= DECERR; end
                endcase
            end
        end
    end
endmodule
