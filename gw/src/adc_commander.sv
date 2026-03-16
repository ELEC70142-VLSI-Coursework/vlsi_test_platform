`timescale 1ns/1ps

module adc_commander #(
    parameter CLK_FREQ = 10_000_000, // 10 MHz
    parameter I2C_FREQ = 100_000      // 100 kHz
)(
    input  logic i_clk,
    input  logic i_rst_n,
    output logic o_done,
    output logic o_ack_error,

    // I2C bus
    inout  wire  scl,
    inout  wire  sda
);

    // Command memory parameters
    localparam NUM_CMDS = 6;
    localparam ADC_ADDR = 7'b1001000; // ADC I2C address (0x48)

    // DAC values to be sent to the ADC (12-bit values)
    // Reference voltage is 1.2v. 
    // Set the values in a 12 bit format with the maximum value of 4095 corresponding to 1.2v
    localparam DAC1_VALUE = 12'd2048; 
    localparam DAC2_VALUE = 12'd1024; 


    // Command memory array [address, data]
    logic [7:0] cmd_mem [0:NUM_CMDS-1];
    
    initial begin
        cmd_mem[0] = 8'b00000111;               // Write Channel H
        cmd_mem[1] = DAC1_VALUE[11:4];          // MSB of data
        cmd_mem[2] = {DAC1_VALUE[3:0],4'b0000}; // LSB of data
        cmd_mem[3] = 8'b00000101;               // Write Channel F
        cmd_mem[4] = DAC2_VALUE[11:4];          // MSB of data
        cmd_mem[5] = {DAC2_VALUE[3:0],4'b0000}; // LSB of data
    end

    typedef enum logic [2:0] {
        IDLE,
        SET_DAC1_START,
        SEND_DAC1_DATA,
        SET_DAC2_START,
        SEND_DAC2_DATA,
        DONE
    } state_t;

    state_t state, next_state;
    
    logic [7:0] cmd_index, cmd_index_next;

    logic       master_start;
    logic       master_stop, master_stop_next;
    logic [6:0] master_addr;
    logic       master_op;
    logic [7:0] master_data_wr;
    logic [7:0] master_data_rd;
    logic       master_busy;
    logic       master_busy_prev;
    logic       master_tx_complete;

    i2c_master 
    #(
        .CLK_FREQ(CLK_FREQ),
        .I2C_FREQ(I2C_FREQ)
    ) i2c_master_inst (
        .i_clk(i_clk),
        .i_rst_n(i_rst_n),
        .i_start(master_start),
        .i_addr(master_addr),
        .i_op(master_op),
        .i_stop(master_stop),
        .i_data_wr(master_data_wr),
        .o_data_rd(master_data_rd),
        .o_busy(master_busy),
        .o_ack_error(o_ack_error),
        .o_data_tx_complete(master_tx_complete),
        .scl(scl),
        .sda(sda)
    );

    always_ff @(posedge i_clk or negedge i_rst_n) begin
        if (!i_rst_n) begin
            state <= IDLE;
            cmd_index <= 0;
            master_busy_prev <= 0;
            master_stop <= 0;
        end else begin
            state <= next_state;
            cmd_index <= cmd_index_next;
            master_busy_prev <= master_busy;
            master_stop <= master_stop_next;
        end
    end

    always_comb begin
        next_state = state;
        cmd_index_next = cmd_index;
        master_start = 1'b0;
        master_addr = ADC_ADDR;
        master_op = 1'b0; // Write
        master_data_wr = cmd_mem[cmd_index[2:0]]; 
        o_done = 1'b0;
        master_stop_next = 1'b0;
       
        case (state)
            IDLE: begin
                cmd_index_next = 0;
                next_state = SET_DAC1_START;
            end


            SET_DAC1_START: begin
                master_start = 1'b1;
                next_state = SEND_DAC1_DATA;
            end

            SEND_DAC1_DATA: begin
                if(master_tx_complete) begin
                    if(o_ack_error) begin
                        next_state = DONE; // Stop on ACK error
                    end else begin
                        cmd_index_next = cmd_index + 1;
                        if(cmd_index_next == 3) begin
                            next_state = SET_DAC2_START;
                            master_stop_next = 1'b1; // Stop after first DAC commands
                        end
                    end
                end
            end

            SET_DAC2_START: begin
                master_start = 1'b1;
                if(master_busy_prev && !master_busy) begin
                    next_state = SEND_DAC2_DATA;
                    cmd_index_next = 3; // Start of second DAC commands
                end
            end

            SEND_DAC2_DATA: begin
                if(master_tx_complete) begin
                    if(o_ack_error) begin
                        next_state = DONE; // Stop on ACK error
                    end else begin
                        cmd_index_next = cmd_index + 1;
                        if(cmd_index_next == 6) begin
                            next_state = DONE;
                            master_stop_next = 1'b1; // Stop after first DAC commands
                        end
                    end
                end
            end

            DONE: begin
                o_done = 1'b1;
                next_state = DONE;
            end

            default: begin
                next_state = IDLE;
            end
        endcase
    end

endmodule
