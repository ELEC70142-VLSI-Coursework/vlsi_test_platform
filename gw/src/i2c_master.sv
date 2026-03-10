
//
// i2c_master.sv
//
// A simple I2C master module for FPGA projects.
//
`timescale 1ns/1ps


module i2c_master #(
    parameter CLK_FREQ = 10_000_000, // 10 MHz
    parameter I2C_FREQ = 100_000      // 100 kHz
) (
    input  logic        i_clk,
    input  logic        i_rst_n,

    // Control interface
    input  logic        i_start,
    input  logic [6:0]  i_addr,
    input  logic        i_op, // 0 for write, 1 for read
    input  logic        i_stop,
    input  logic [7:0]  i_data_wr,
    output logic [7:0]  o_data_rd,
    output logic        o_busy,
    output logic        o_ack_error,
    output logic        o_data_tx_complete,

    // I2C bus
    inout  wire         scl,
    inout  wire         sda
);

    // I2C timing parameters (for 100kHz from 10MHz clock)
    localparam CLK_DIV = CLK_FREQ / (I2C_FREQ * 2);

    // FSM states
    typedef enum logic [3:0] {
        IDLE,
        START,
        SEND_ADDR,
        ADDR_ACK,
        ACQUIRE_DATA,
        SEND_DATA,
        DATA_ACK,
        READ_DATA,
        READ_ACK,
        STOP
    } state_t;

    state_t state, next_state;

    logic [7:0] data_shift, data_shift_next;
    logic [2:0] bit_count, bit_count_next;
    logic [15:0] clk_counter, clk_counter_next;
    logic [6:0] addr_r;
    logic [7:0] data_r;
    logic op_r;

    logic scl_o_next, sda_o_next;
    logic scl_en_next, sda_en_next;
    logic scl_o, sda_o, scl_en, sda_en;

    always_ff @(posedge i_clk or negedge i_rst_n) begin
        if (!i_rst_n) begin
            scl_o <= 1'b1;
            sda_o <= 1'b1;
            scl_en <= 1'b0;
            sda_en <= 1'b0;
            data_shift <= 8'h00;
            bit_count <= 3'h0;
        end else begin
            scl_o <= scl_o_next;
            sda_o <= sda_o_next;
            scl_en <= scl_en_next;
            sda_en <= sda_en_next;
            data_shift <= data_shift_next;
            bit_count <= bit_count_next;
        end
    end

    assign scl = scl_en ? scl_o : 1'bz;
    assign sda = sda_en ? sda_o : 1'bz;

    assign o_busy = (state != IDLE);
    logic ack_error_reg;
    assign o_ack_error = ack_error_reg;

    always_ff @(posedge i_clk or negedge i_rst_n) begin
        if (!i_rst_n) begin
            state <= IDLE;
            ack_error_reg <= 1'b0;
            clk_counter <= 0;
        end else begin
            state <= next_state;
            if(state == START) begin
                ack_error_reg <= 1'b0; // Clear ACK error at start of transaction
            end else if (state == ADDR_ACK || state == DATA_ACK) begin
                if (clk_counter == CLK_DIV) begin
                    ack_error_reg <= sda; // Capture ACK/NACK bit
                end
            end
            
            clk_counter <= clk_counter_next;

            if (i_start && state == IDLE) begin
                addr_r <= i_addr;
                op_r <= i_op;
            end

        end
    end

    always_comb begin
        next_state = state;
        scl_o_next = scl_o;
        sda_o_next = 1'b1;
        scl_en_next = 1'b1;
        sda_en_next = 1'b1;
        bit_count_next = bit_count;
        data_shift_next = data_shift;
        o_data_rd = 0;
        clk_counter_next = clk_counter + 1;
        o_data_tx_complete = 1'b0;


        case (state)
            IDLE: begin
                scl_en_next = 0; // Let pull-up keep SCL high
                sda_en_next = 0; // Let pull-up keep SDA high
                if (i_start) begin
                    next_state = START;
                end
                clk_counter_next = 0;
            end

            START: begin
                if(clk_counter >= CLK_DIV/2) begin
                    sda_o_next = 0; // Start condition: SDA goes low while SCL is high
                end
                if (clk_counter == CLK_DIV) begin
                    scl_o_next = 0;
                    next_state = SEND_ADDR;
                    data_shift_next = {addr_r, op_r}; // Address + R/W bit
                    bit_count_next = 7;
                    clk_counter_next = 0;
                end
            end

            SEND_ADDR: begin
                sda_o_next = data_shift[bit_count_next];
                if (clk_counter == CLK_DIV) begin
                    scl_o_next = 1;
                end else if (clk_counter == 2*CLK_DIV) begin
                    if (bit_count_next == 0) begin
                        next_state = ADDR_ACK;
                    end else begin
                        bit_count_next = bit_count_next - 1;
                    end
                    clk_counter_next = 0;
                    scl_o_next = 0;
                end
            end
            
            ADDR_ACK: begin
                sda_en_next = 0; // Let slave drive SDA
                if (clk_counter == CLK_DIV) begin
                    scl_o_next = 1;
                    if (sda) begin // NACK
                        next_state = STOP;
                    end
                end else if (clk_counter == 2*CLK_DIV) begin
                    // o_data_tx_complete = 1'b1;
                    if (op_r) begin // Read
                        next_state = READ_DATA;
                    end else begin // Write
                        next_state = ACQUIRE_DATA;
                    end
                end
            end

            ACQUIRE_DATA: begin
                sda_en_next = 0; // Let slave drive SDA
                if (i_stop) begin
                    next_state = STOP;
                end else begin
                    data_shift_next = i_data_wr; // For multi-byte writes, load next byte here
                    bit_count_next = 7;
                    next_state = SEND_DATA;
                end
                clk_counter_next = 0;
                scl_o_next = 0;
            end

            SEND_DATA: begin
                sda_o_next = data_shift[bit_count_next];
                if (clk_counter == CLK_DIV) begin
                    scl_o_next = 1;
                end else if (clk_counter == 2*CLK_DIV) begin
                    scl_o_next = 0;
                    if (bit_count_next == 0) begin
                        next_state = DATA_ACK;
                    end else begin
                        bit_count_next = bit_count_next - 1;
                    end
                    clk_counter_next = 0;
                end
            end


            DATA_ACK: begin
                sda_en_next = 0; // Let slave drive SDA
                if (clk_counter == CLK_DIV) begin
                    scl_o_next = 1;
                    if (sda) begin // NACK
                        next_state = STOP;
                    end
                end else if (clk_counter == 2*CLK_DIV) begin
                    o_data_tx_complete = 1'b1;
                    next_state = ACQUIRE_DATA;
                end
            end

            READ_DATA: begin
                sda_en_next = 0; // Let slave drive SDA
                if (clk_counter == CLK_DIV) begin
                    scl_o_next = 1;
                end else if (clk_counter == 2*CLK_DIV) begin
                    data_shift_next[bit_count_next] = sda;
                    if (bit_count_next == 0) begin
                        o_data_rd = data_shift_next;
                        next_state = READ_ACK;
                    end else begin
                        next_state = READ_DATA;
                        bit_count_next = bit_count_next - 1;
                    end
                    clk_counter_next = 0;
                    scl_o_next = 0;
                end
            end

            READ_ACK: begin
                scl_o_next = 0;
                sda_o_next = 1; // NACK after read
                if (clk_counter == CLK_DIV) begin
                    scl_o_next = 1;
                end else if (clk_counter == 2*CLK_DIV) begin
                    next_state = STOP;
                    clk_counter_next = 0;
                end
            end

            STOP: begin
                sda_o_next = 0;
                if (clk_counter == CLK_DIV) begin
                    scl_o_next = 1;
                end
                if (clk_counter >= 3*CLK_DIV/2) begin
                    sda_o_next = 1;
                end
                if (clk_counter == 2*CLK_DIV) begin
                    next_state = IDLE;
                end
            end
            
            default: begin
                next_state = IDLE;
            end
        endcase
    end

endmodule
